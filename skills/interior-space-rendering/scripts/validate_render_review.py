#!/usr/bin/env python3
"""Validate an independent, measured review of one generated space image."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from render_contract import load_json, resolve, sha256_file, validate_closed_world_view, verify_document_digest
from validate_generation_receipt import validate_receipt
from validate_imagegen_request import validate_request


MAX_CAMERA_KEYPOINT_ERROR = 0.02
MAX_WALL_LINE_ANGLE_ERROR_DEG = 1.0
MAX_OBJECT_CENTER_ERROR = 0.02
MAX_OBJECT_REGION_EDGE_ERROR = 0.025
MAX_OBJECT_ORIENTATION_ERROR_DEG = 3.0
MAX_STRUCTURE_REGION_EDGE_ERROR = 0.02
MAX_CONNECTION_REGION_EDGE_ERROR = 0.02
MIN_ORIENTATION_COVERAGE = 0.01
MIN_STRUCTURE_LINE_COVERAGE = 0.02
COORDINATE_TOLERANCE = 1e-9


def exact_list(value: object, expected: set, label: str) -> None:
    if not isinstance(value, list) or len(value) != len(expected):
        raise ValueError(f"{label} must enumerate the expected set exactly once")
    normalized = [tuple(row) if isinstance(row, list) else row for row in value]
    if len(normalized) != len(set(normalized)) or set(normalized) != expected:
        raise ValueError(f"{label} must enumerate the expected set exactly once")


def point(value: object) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("comparison point must contain x and y")
    x, y = value
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in (x, y)):
        raise ValueError("comparison point is not finite")
    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("comparison point must use normalized image coordinates")
    return float(x), float(y)


def bbox(value: object, label: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{label} must contain x1, y1, x2 and y2")
    if any(
        not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item)
        for item in value
    ):
        raise ValueError(f"{label} is not finite")
    x1, y1, x2, y2 = (float(item) for item in value)
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError(f"{label} must be a non-empty normalized box")
    return x1, y1, x2, y2


def bbox_center(value: tuple[float, float, float, float]) -> tuple[float, float]:
    return (value[0] + value[2]) / 2, (value[1] + value[3]) / 2


def bbox_edge_error(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    return max(abs(a - b) for a, b in zip(left, right))


def assert_point_matches(actual: tuple[float, float], expected: tuple[float, float], label: str) -> None:
    if math.dist(actual, expected) > COORDINATE_TOLERANCE:
        raise ValueError(f"{label} does not match the scene-map-derived center")


def assert_bbox_matches(
    actual: tuple[float, float, float, float],
    expected: tuple[float, float, float, float],
    label: str,
) -> None:
    if bbox_edge_error(actual, expected) > COORDINATE_TOLERANCE:
        raise ValueError(f"{label} does not match the scene-map region")


def point_inside_bbox(
    value: tuple[float, float],
    region: tuple[float, float, float, float],
) -> bool:
    return (
        region[0] - COORDINATE_TOLERANCE <= value[0] <= region[2] + COORDINATE_TOLERANCE
        and region[1] - COORDINATE_TOLERANCE <= value[1] <= region[3] + COORDINATE_TOLERANCE
    )


def exact_rows(rows: object, key: str, expected: set[str], label: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} must be a list")
    ids = [row.get(key) if isinstance(row, dict) else None for row in rows]
    if len(ids) != len(expected) or len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError(f"{label} must enumerate every expected ID exactly once")
    return {row[key]: row for row in rows}


def line_angle(value: object) -> float:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("comparison line must contain two points")
    a, b = point(value[0]), point(value[1])
    if a == b:
        raise ValueError("comparison line has zero length")
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def angle_delta(left: float, right: float) -> float:
    value = (left - right + 90) % 180 - 90
    return abs(value)


def measured_camera_errors(
    comparison: dict,
    scene: dict,
    structure_render_bboxes: dict[str, tuple[float, float, float, float]],
) -> tuple[float, float]:
    keypoints = comparison.get("keypointPairs")
    if not isinstance(keypoints, list) or len(keypoints) < 4:
        raise ValueError("camera review requires at least four named point pairs")
    labels = [row.get("label") for row in keypoints]
    if any(not label for label in labels) or len(labels) != len(set(labels)):
        raise ValueError("camera keypoint labels must be unique")
    distances = []
    for row in keypoints:
        source = point(row.get("source"))
        render = point(row.get("render"))
        distances.append(math.dist(source, render))
    structures = {row["structureId"]: row for row in scene.get("structures", [])}
    required_line_ids = {
        structure_id
        for structure_id, row in structures.items()
        if row.get("region", {}).get("coverage", 0) >= MIN_STRUCTURE_LINE_COVERAGE
    }
    lines = exact_rows(comparison.get("wallLinePairs"), "structureId", required_line_ids, "wallLinePairs")
    angle_errors = []
    for structure_id, row in lines.items():
        source_line, render_line = row.get("source"), row.get("render")
        source_angle, render_angle = line_angle(source_line), line_angle(render_line)
        source_region = bbox(structures[structure_id]["region"]["bbox"], f"{structure_id}.sceneBBox")
        render_region = structure_render_bboxes[structure_id]
        for value in source_line:
            if not point_inside_bbox(point(value), source_region):
                raise ValueError(f"{structure_id} source wall line is outside its scene-map region")
        for value in render_line:
            if not point_inside_bbox(point(value), render_region):
                raise ValueError(f"{structure_id} render wall line is outside its measured render region")
        angle_errors.append(angle_delta(source_angle, render_angle))
    return max(distances), max(angle_errors, default=0.0)


def validate_projection_audit(scene: dict, review: dict) -> dict[str, object]:
    audit = review.get("measuredProjectionAudit")
    if not isinstance(audit, dict) or audit.get("method") != "complete-scene-map-region-correspondence-v1":
        raise ValueError("measuredProjectionAudit must use the complete scene-map correspondence method")

    slots = {row["slotId"]: row for row in scene.get("placementSlots", [])}
    structures = {row["structureId"]: row for row in scene.get("structures", [])}
    connections = {row["connectionId"]: row for row in scene.get("connections", [])}
    rooms = {row["roomId"] for row in scene.get("rooms", [])}
    slot_ids, structure_ids, connection_ids = set(slots), set(structures), set(connections)

    expected_counts = {
        "sourceObjectCount": len(slot_ids),
        "renderObjectCount": len(slot_ids),
        "sourceStructureCount": len(structure_ids),
        "renderStructureCount": len(structure_ids),
        "openingCountSource": len(connection_ids),
        "openingCountRender": len(connection_ids),
    }
    for key, expected in expected_counts.items():
        if audit.get(key) != expected:
            raise ValueError(f"{key} must equal the complete current-shot scene-map count")

    exact_list(audit.get("visibleRoomIdsSource"), rooms, "visibleRoomIdsSource")
    exact_list(audit.get("visibleRoomIdsRender"), rooms, "visibleRoomIdsRender")

    object_centers = exact_rows(audit.get("objectCenterPairs"), "slotId", slot_ids, "objectCenterPairs")
    object_regions = exact_rows(audit.get("objectRegionPairs"), "slotId", slot_ids, "objectRegionPairs")
    object_center_errors = []
    object_edge_errors = []
    object_render_bboxes: dict[str, tuple[float, float, float, float]] = {}
    for slot_id, slot in slots.items():
        expected_bbox = bbox(slot["region"]["bbox"], f"{slot_id}.sceneBBox")
        region_row = object_regions[slot_id]
        source_bbox = bbox(region_row.get("sourceBBox"), f"{slot_id}.sourceBBox")
        render_bbox = bbox(region_row.get("renderBBox"), f"{slot_id}.renderBBox")
        assert_bbox_matches(source_bbox, expected_bbox, f"{slot_id}.sourceBBox")
        object_render_bboxes[slot_id] = render_bbox
        object_edge_errors.append(bbox_edge_error(source_bbox, render_bbox))

        center_row = object_centers[slot_id]
        source_center = point(center_row.get("source"))
        render_center = point(center_row.get("render"))
        assert_point_matches(source_center, bbox_center(source_bbox), f"{slot_id}.source center")
        assert_point_matches(render_center, bbox_center(render_bbox), f"{slot_id}.render center")
        object_center_errors.append(math.dist(source_center, render_center))

    orientation_ids = {
        slot_id
        for slot_id, slot in slots.items()
        if slot.get("slotLock", {}).get("orientation") is True
        and slot.get("region", {}).get("coverage", 0) >= MIN_ORIENTATION_COVERAGE
    }
    orientation_rows = exact_rows(
        audit.get("orientationLinePairs"), "slotId", orientation_ids, "orientationLinePairs"
    )
    orientation_errors = []
    for slot_id, row in orientation_rows.items():
        source_line, render_line = row.get("source"), row.get("render")
        source_angle, render_angle = line_angle(source_line), line_angle(render_line)
        source_bbox = bbox(slots[slot_id]["region"]["bbox"], f"{slot_id}.sceneBBox")
        render_bbox = object_render_bboxes[slot_id]
        for value in source_line:
            if not point_inside_bbox(point(value), source_bbox):
                raise ValueError(f"{slot_id} source orientation line is outside its source region")
        for value in render_line:
            if not point_inside_bbox(point(value), render_bbox):
                raise ValueError(f"{slot_id} render orientation line is outside its render region")
        orientation_errors.append(angle_delta(source_angle, render_angle))

    structure_regions = exact_rows(
        audit.get("structureRegionPairs"), "structureId", structure_ids, "structureRegionPairs"
    )
    structure_edge_errors = []
    structure_render_bboxes: dict[str, tuple[float, float, float, float]] = {}
    for structure_id, structure in structures.items():
        row = structure_regions[structure_id]
        expected_bbox = bbox(structure["region"]["bbox"], f"{structure_id}.sceneBBox")
        source_bbox = bbox(row.get("sourceBBox"), f"{structure_id}.sourceBBox")
        render_bbox = bbox(row.get("renderBBox"), f"{structure_id}.renderBBox")
        assert_bbox_matches(source_bbox, expected_bbox, f"{structure_id}.sourceBBox")
        structure_render_bboxes[structure_id] = render_bbox
        structure_edge_errors.append(bbox_edge_error(source_bbox, render_bbox))

    connection_regions = exact_rows(
        audit.get("connectionRegionPairs"), "connectionId", connection_ids, "connectionRegionPairs"
    )
    connection_edge_errors = []
    for connection_id, connection in connections.items():
        row = connection_regions[connection_id]
        expected_bbox = bbox(connection["region"]["bbox"], f"{connection_id}.sceneBBox")
        source_bbox = bbox(row.get("sourceBBox"), f"{connection_id}.sourceBBox")
        render_bbox = bbox(row.get("renderBBox"), f"{connection_id}.renderBBox")
        assert_bbox_matches(source_bbox, expected_bbox, f"{connection_id}.sourceBBox")
        connection_edge_errors.append(bbox_edge_error(source_bbox, render_bbox))

    metrics = {
        "maximumObjectCenterError": max(object_center_errors, default=0.0),
        "maximumObjectRegionEdgeError": max(object_edge_errors, default=0.0),
        "maximumObjectOrientationErrorDeg": max(orientation_errors, default=0.0),
        "maximumStructureRegionEdgeError": max(structure_edge_errors, default=0.0),
        "maximumConnectionRegionEdgeError": max(connection_edge_errors, default=0.0),
    }
    computed = audit.get("computed")
    if not isinstance(computed, dict) or set(computed) != set(metrics):
        raise ValueError("measuredProjectionAudit.computed must contain the complete metric set")
    for key, value in metrics.items():
        reported = computed.get(key)
        if not isinstance(reported, (int, float)) or isinstance(reported, bool) or abs(reported - value) > 1e-9:
            raise ValueError(f"{key} was not computed from the complete correspondence set")

    limits = {
        "maximumObjectCenterError": MAX_OBJECT_CENTER_ERROR,
        "maximumObjectRegionEdgeError": MAX_OBJECT_REGION_EDGE_ERROR,
        "maximumObjectOrientationErrorDeg": MAX_OBJECT_ORIENTATION_ERROR_DEG,
        "maximumStructureRegionEdgeError": MAX_STRUCTURE_REGION_EDGE_ERROR,
        "maximumConnectionRegionEdgeError": MAX_CONNECTION_REGION_EDGE_ERROR,
    }
    for key, limit in limits.items():
        if metrics[key] > limit:
            raise ValueError(f"{key} exceeds tolerance: {metrics[key]:.6f} > {limit:.6f}")
    return {"metrics": metrics, "structureRenderBBoxes": structure_render_bboxes}


def validate_review(scene_path: Path, request_path: Path, receipt_path: Path, review_path: Path) -> dict:
    scene_path, request_path, receipt_path, review_path = [
        path.resolve() for path in (scene_path, request_path, receipt_path, review_path)
    ]
    scene = load_json(scene_path)
    request = validate_request(request_path)
    receipt = validate_receipt(request_path, receipt_path)
    review = load_json(review_path)
    if scene.get("schema") != "interior.shot-scene-map.v9" or review.get("schema") != "interior.render-agent-review.v4":
        raise ValueError("scene map or review schema mismatch")
    closed_world = validate_closed_world_view(scene)
    verify_document_digest(review, "reviewDigestSha256")
    if review.get("generationReceiptSha256") != sha256_file(receipt_path):
        raise ValueError("review is not bound to this generation receipt")
    if review.get("reviewerInvocationId") == request.get("generationInvocationId") or not review.get("reviewerInvocationId"):
        raise ValueError("render review must use an independent invocation")

    exact_list(review.get("observedRoomIds"), {row["roomId"] for row in scene.get("rooms", [])}, "observedRoomIds")
    exact_list(review.get("observedConnectionIds"), {row["connectionId"] for row in scene.get("connections", [])}, "observedConnectionIds")
    exact_list(review.get("observedStructureIds"), {row["structureId"] for row in scene.get("structures", [])}, "observedStructureIds")
    observed_rows = review.get("observedSlots")
    if not isinstance(observed_rows, list):
        raise ValueError("observedSlots must be a list")
    expected_slots = {
        (row["slotId"], row["functionalClass"], row["quantity"])
        for row in scene.get("placementSlots", [])
    }
    observed_slots = {
        (row.get("slotId"), row.get("functionalClass"), row.get("quantity"))
        for row in observed_rows
    }
    if observed_slots != expected_slots or len(observed_rows) != len(expected_slots):
        raise ValueError("review slot inventory differs from the current-shot scene map")
    for row in observed_rows:
        if any(row.get(flag) is not True for flag in (
            "identityMatchesCurrentFurnishedReference",
            "placementMatchesCurrentFurnishedReference",
            "orientationMatchesCurrentFurnishedReference",
        )):
            raise ValueError(f"slot {row.get('slotId')} differs from current-shot Q2")

    architecture = review.get("architectureComparison")
    if architecture != {
        "cameraAndCropMatchCurrentConcreteReference": True,
        "wallsAndOpeningsMatchCurrentConcreteReference": True,
        "noWallOpeningRoomOrBoundaryMutation": True,
    }:
        raise ValueError("render architecture differs from current-shot Q1")

    unexpected = review.get("unexpectedElements")
    expected_unexpected_keys = {
        "roomIds", "connectionIds", "structureIds", "placementSlotIds",
        "architecturalElements", "functionalObjects",
    }
    if not isinstance(unexpected, dict) or set(unexpected) != expected_unexpected_keys:
        raise ValueError("unexpectedElements must enumerate every closed-world category")
    if any(unexpected[key] != [] for key in expected_unexpected_keys):
        raise ValueError("generated render contains unlisted scene elements")
    if review.get("absenceAssertions") != {
        "noUnlistedRoomOrInteriorSpace": True,
        "noUnlistedDoorWindowOrPassage": True,
        "noUnlistedStructure": True,
        "noUnlistedFurnitureCabinetApplianceOrFixture": True,
        "noInteriorContinuationBeyondExteriorBoundary": True,
    }:
        raise ValueError("closed-world absence assertions are incomplete")

    expected_boundaries = {row["connectionId"]: row for row in closed_world["boundaryTerminations"]}
    observed_boundaries = review.get("observedBoundaryTerminations")
    if not isinstance(observed_boundaries, list):
        raise ValueError("observedBoundaryTerminations must be a list")
    boundary_ids = [row.get("connectionId") for row in observed_boundaries]
    if len(boundary_ids) != len(set(boundary_ids)) or set(boundary_ids) != set(expected_boundaries):
        raise ValueError("render review did not enumerate every exterior boundary exactly once")
    for row in observed_boundaries:
        expected = expected_boundaries[row["connectionId"]]
        if row.get("depiction") not in expected["allowedDepictions"] or row.get("farSide") != "exterior":
            raise ValueError("exterior boundary depiction violates the scene map")

    additions = review.get("observedAdditions")
    if not isinstance(additions, list):
        raise ValueError("observedAdditions must be a list")
    allowed_additions = set(closed_world["additionPolicy"]["allowedClasses"])
    addition_ids = []
    for row in additions:
        addition_ids.append(row.get("additionId"))
        if not row.get("additionId") or row.get("class") not in allowed_additions:
            raise ValueError("render contains an addition outside the finite allowlist")
        if row.get("nonstructural") is not True or row.get("createsRoomOpeningOrPlacementSlot") is not False:
            raise ValueError("render addition changes structure")
        if row.get("obstructsOpeningOrClearance") is not False:
            raise ValueError("render addition obstructs an opening or clearance")
    if len(addition_ids) != len(set(addition_ids)):
        raise ValueError("render addition IDs must be unique")

    projection = validate_projection_audit(scene, review)
    comparison = review.get("cameraComparison")
    if not isinstance(comparison, dict):
        raise ValueError("cameraComparison must contain measured correspondences")
    keypoint_error, angle_error = measured_camera_errors(
        comparison, scene, projection["structureRenderBBoxes"]
    )
    computed = comparison.get("computed")
    if not isinstance(computed, dict):
        raise ValueError("cameraComparison.computed is missing")
    if set(computed) != {"maximumNormalizedKeypointError", "maximumWallLineAngleErrorDeg"}:
        raise ValueError("cameraComparison.computed must contain the complete metric set")
    if abs(computed.get("maximumNormalizedKeypointError", -1) - keypoint_error) > 1e-9:
        raise ValueError("reported keypoint error was not computed from the supplied pairs")
    if abs(computed.get("maximumWallLineAngleErrorDeg", -1) - angle_error) > 1e-9:
        raise ValueError("reported line angle error was not computed from the supplied pairs")
    if keypoint_error > MAX_CAMERA_KEYPOINT_ERROR or angle_error > MAX_WALL_LINE_ANGLE_ERROR_DEG:
        raise ValueError("render camera or architecture alignment exceeds tolerance")

    expected_reference_ids = {
        row.get("referenceId")
        for row in request.get("submittedImageAttachments", [])
        if row.get("role") == "accepted-space-identity-reference"
    }
    identity_rows = review.get("identityReferenceComparisons")
    if not isinstance(identity_rows, list) or {row.get("referenceShotId") for row in identity_rows} != expected_reference_ids:
        raise ValueError("identity reference review differs from submitted dependencies")
    for row in identity_rows:
        if row.get("sharedFurnitureIdentityPreserved") is not True or row.get("sharedFinishIdentityPreserved") is not True:
            raise ValueError("an overlapping shot changed accepted space identity")

    evidence_roles = set()
    for row in review.get("evidence", []):
        target = resolve(review_path.parent, row.get("path", ""))
        if row.get("role") in evidence_roles or not target.is_file() or sha256_file(target) != row.get("sha256"):
            raise ValueError("render review evidence is duplicated, missing, or stale")
        evidence_roles.add(row["role"])
    if evidence_roles != {
        "q1-concrete-structure-source", "q2-furnished-layout-source", "generated-render",
        "entity-mask", "room-mask", "camera-comparison-overlay",
    }:
        raise ValueError("review evidence must show both authorities, render, masks and measured overlay")
    if review.get("decision") != "accept":
        raise ValueError("render review decision is not accept")
    return review


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit("usage: validate_render_review.py scene-map.json request.json receipt.json review.json")
    paths = [Path(value) for value in sys.argv[1:]]
    scene = load_json(paths[0].resolve())
    validate_review(*paths)
    print(f"render review accepted: {scene['shotId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
