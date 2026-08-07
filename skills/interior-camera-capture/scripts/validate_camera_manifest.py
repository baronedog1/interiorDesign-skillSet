#!/usr/bin/env python3
"""Validate camera-plan.v8 against one accepted native model and the frozen structure."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path

from compile_camera_candidates import compile_batch
from solve_frontal_camera_seeds import build_seed_set


METHOD_VERSION = "deterministic-wall-normal-camera-v7"
BACKENDS = {"html-threejs", "blender", "cad-step"}
SENSOR_WIDTH_MM = 36.0
SENSOR_HEIGHT_MM = 22.5
DISTANCE_SAFETY = 1.05
DEPTH_SCALE_LIMIT = 1.18
YAW_LIMIT = 1.0
PITCH_LIMIT = 0.25
ROLL_LIMIT = 0.1
RESIDUAL_LIMIT = 0.25
MIN_MARGIN = 0.06
MARGIN_DIFFERENCE_LIMIT = 0.03
FOREGROUND_LIMIT = 0.08
GEOMETRY_TOLERANCE = 0.002


def fail(message: str) -> None:
    raise AssertionError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_model_scope(
    manifest: dict,
    structure: dict,
    structure_path: Path,
) -> dict:
    room_ids = {room.get("id") for room in structure.get("rooms", [])}
    scope = manifest.get("modelScope")
    if scope is None:
        if manifest.get("modelBackend") == "html-threejs":
            fail("HTML native model manifest must bind interior.model-scope.v1")
        return {
            "schema": "interior.model-scope.v1",
            "mode": "whole-floor",
            "requestedRoomIds": sorted(room_ids),
            "allowedContextRoomIds": [],
            "excludedRoomIds": [],
        }
    if scope.get("schema") != "interior.model-scope.v1":
        fail("native model scope schema mismatch")
    payload = dict(scope)
    declared_digest = payload.pop("scopeDigestSha256", None)
    if canonical_digest(payload) != declared_digest:
        fail("native model scope digest mismatch")
    if scope.get("sameTemplateAsWholeFloor") is not True or scope.get("customProjectGeometryAllowed") is not False:
        fail("native model scope permits a second project geometry/template path")
    requested = scope.get("requestedRoomIds")
    context = scope.get("allowedContextRoomIds")
    excluded = scope.get("excludedRoomIds")
    for value, label in (
        (requested, "requestedRoomIds"),
        (context, "allowedContextRoomIds"),
        (excluded, "excludedRoomIds"),
    ):
        if not isinstance(value, list) or len(value) != len(set(value)):
            fail(f"modelScope.{label} must be a unique list")
    if set(requested) & set(context):
        fail("model scope requested and context rooms overlap")
    if set(requested) | set(context) | set(excluded) != room_ids:
        fail("model scope must partition every structure room")
    if (set(requested) | set(context)) & set(excluded):
        fail("model scope included and excluded rooms overlap")
    if scope.get("mode") == "whole-floor":
        if set(requested) != room_ids or context or excluded:
            fail("whole-floor model scope must include every room")
    elif scope.get("mode") == "room-subset":
        if not requested or not str(scope.get("reason", "")).strip():
            fail("room-subset model scope needs requested rooms and a reason")
    else:
        fail("unsupported native model scope mode")
    bindings = scope.get("bindings", {})
    if bindings.get("floorplanId") != structure.get("floorplanId"):
        fail("model scope floorplan binding mismatch")
    if bindings.get("handoffDigestSha256") != manifest.get("handoffDigestSha256"):
        fail("model scope handoff binding mismatch")
    if bindings.get("structureDataSha256") != sha256(structure_path):
        fail("model scope structure binding mismatch")
    return scope


def number(value, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        fail(f"{field} must be a finite number")
    return float(value)


def vector(value, length: int, field: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        fail(f"{field} must contain {length} numbers")
    return tuple(number(item, f"{field}[{index}]") for index, item in enumerate(value))


def normalize2(value: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*value)
    if length <= 1e-9:
        fail("cannot normalize a zero-length 2D vector")
    return value[0] / length, value[1] / length


def normalize3(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in value))
    if length <= 1e-9:
        fail("cannot normalize a zero-length 3D vector")
    return tuple(component / length for component in value)


def cross2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def close(actual: float, expected: float, tolerance: float = GEOMETRY_TOLERANCE) -> bool:
    return abs(actual - expected) <= tolerance


def close_vector(actual, expected, tolerance: float = GEOMETRY_TOLERANCE) -> bool:
    return len(actual) == len(expected) and all(close(a, b, tolerance) for a, b in zip(actual, expected))


def wall_world_segment(structure: dict, wall_id: str) -> tuple[tuple[float, float], tuple[float, float]]:
    walls = {wall.get("id"): wall for wall in structure.get("walls", [])}
    if wall_id not in walls:
        fail(f"unknown reference wall {wall_id}")
    coordinate_system = structure.get("coordinateSystem", {})
    if coordinate_system.get("units") != "m":
        fail("structure coordinate units must be metres")
    origin = coordinate_system.get("origin")
    if origin == "north-west":
        half_width = number(coordinate_system.get("realWidthMeters"), "realWidthMeters") / 2
        half_depth = number(coordinate_system.get("realDepthMeters"), "realDepthMeters") / 2

        def convert(point):
            point = vector(point, 2, f"wall {wall_id} point")
            return point[0] - half_width, point[1] - half_depth
    elif origin == "world-center":

        def convert(point):
            return vector(point, 2, f"wall {wall_id} point")
    else:
        fail(f"unsupported structure origin {origin!r}")
    wall = walls[wall_id]
    return convert(wall.get("start")), convert(wall.get("end"))


def floorplan_world_point(structure: dict, point, field: str) -> tuple[float, float]:
    coordinate_system = structure.get("coordinateSystem", {})
    source = vector(point, 2, field)
    if coordinate_system.get("units") != "m":
        fail("structure coordinate units must be metres")
    if coordinate_system.get("origin") == "north-west":
        return (
            source[0] - number(coordinate_system.get("realWidthMeters"), "realWidthMeters") / 2,
            source[1] - number(coordinate_system.get("realDepthMeters"), "realDepthMeters") / 2,
        )
    if coordinate_system.get("origin") == "world-center":
        return source
    fail(f"unsupported structure origin {coordinate_system.get('origin')!r}")


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        sx, sy = start
        ex, ey = end
        segment = (ex - sx, ey - sy)
        relative = (x - sx, y - sy)
        cross = abs(cross2(segment, relative))
        if cross <= GEOMETRY_TOLERANCE and min(sx, ex) - GEOMETRY_TOLERANCE <= x <= max(sx, ex) + GEOMETRY_TOLERANCE and min(sy, ey) - GEOMETRY_TOLERANCE <= y <= max(sy, ey) + GEOMETRY_TOLERANCE:
            return True
        if (sy > y) != (ey > y):
            boundary_x = sx + (y - sy) * (ex - sx) / (ey - sy)
            if x < boundary_x:
                inside = not inside
    return inside


def ray_polygon_distances(origin: tuple[float, float], direction: tuple[float, float], polygon: list[tuple[float, float]]) -> list[float]:
    distances = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        segment = (end[0] - start[0], end[1] - start[1])
        denominator = cross2(direction, segment)
        if abs(denominator) <= 1e-9:
            continue
        relative = (start[0] - origin[0], start[1] - origin[1])
        distance = cross2(relative, segment) / denominator
        segment_t = cross2(relative, direction) / denominator
        if distance > GEOMETRY_TOLERANCE and -GEOMETRY_TOLERANCE <= segment_t <= 1 + GEOMETRY_TOLERANCE:
            distances.append(distance)
    return sorted(distances)


def rooms_connected(structure: dict, start: str, target: str) -> bool:
    if start == target:
        return True
    graph: dict[str, set[str]] = {}
    for connection in structure.get("connections", []):
        left = connection.get("fromRoomId")
        right = connection.get("toRoomId")
        if left and right:
            graph.setdefault(left, set()).add(right)
            graph.setdefault(right, set()).add(left)
    visited = {start}
    frontier = [start]
    while frontier:
        room_id = frontier.pop()
        for neighbor in graph.get(room_id, set()):
            if neighbor == target:
                return True
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    return False


def validate_camera_host(shot: dict, structure: dict) -> dict:
    shot_id = shot["shotId"]
    host_id = shot.get("cameraHostRoomId")
    if not host_id:
        fail(f"{shot_id}: cameraHostRoomId is required")
    rooms = {room.get("id"): room for room in structure.get("rooms", [])}
    if host_id not in rooms:
        fail(f"{shot_id}: unknown cameraHostRoomId {host_id}")
    if not rooms_connected(structure, shot.get("roomId"), host_id):
        fail(f"{shot_id}: camera host room is not connected to the photographed room")
    polygon = [floorplan_world_point(structure, point, f"room {host_id} polygon") for point in rooms[host_id].get("polygon", [])]
    if len(polygon) < 3:
        fail(f"{shot_id}: camera host room has no valid polygon")
    position = vector(shot.get("position"), 3, f"{shot_id}.position")
    target = vector(shot.get("target"), 3, f"{shot_id}.target")
    camera_xz = (position[0], position[2])
    target_xz = (target[0], target[2])
    if not point_in_polygon(camera_xz, polygon):
        fail(f"{shot_id}: camera position is outside cameraHostRoomId={host_id}")
    retreat_direction = normalize2((camera_xz[0] - target_xz[0], camera_xz[1] - target_xz[1]))
    distances = ray_polygon_distances(target_xz, retreat_direction, polygon)
    if not distances:
        fail(f"{shot_id}: cannot derive retreat depth from camera host polygon")
    actual_distance = math.dist(camera_xz, target_xz)
    exit_distances = [distance for distance in distances if distance >= actual_distance - GEOMETRY_TOLERANCE]
    if not exit_distances:
        fail(f"{shot_id}: camera lies beyond the native room retreat boundary")
    # Use the first room exit beyond the camera. Taking the farthest hit would
    # incorrectly bridge disconnected lobes of a concave room polygon.
    available_depth = min(exit_distances)
    declared = number(shot.get("framing", {}).get("availableDepthMeters"), f"{shot_id}.availableDepthMeters")
    if not close(declared, available_depth, 0.02):
        fail(f"{shot_id}: available retreat depth was not derived from the camera host polygon")
    if actual_distance > available_depth + GEOMETRY_TOLERANCE:
        fail(f"{shot_id}: camera lies beyond the native room retreat boundary")
    return {"cameraHostRoomId": host_id, "availableDepthMeters": round(available_depth, 6)}


def validate_native_manifest(manifest: dict, manifest_path: Path) -> tuple[str, str]:
    if manifest.get("schema") != "interior.native-model-manifest.v1":
        fail("native model manifest schema mismatch")
    backend = manifest.get("modelBackend")
    if backend not in BACKENDS:
        fail(f"unsupported modelBackend {backend!r}")
    if manifest.get("validation", {}).get("accepted") is not True:
        fail("native model manifest is not accepted")
    if manifest.get("validation", {}).get("primitiveFurnitureFallbackCount") != 0:
        fail("native model contains primitive furniture fallback")
    capabilities = manifest.get("capabilities", {})
    for capability in ("visibilityStates", "nativeCameraRender"):
        if capabilities.get(capability) is not True:
            fail(f"native model is missing {capability} capability")
    if backend == "cad-step":
        if capabilities.get("projectionProfile") != "cad-same-brep-topology-zbuffer-v1":
            fail("CAD native model is missing the accepted same-B-rep topology Z-buffer profile")
        if capabilities.get("semanticProjection") is not True:
            fail("CAD native model cannot compile same-B-rep topology semantic evidence")
        entity_index = manifest.get("entityIndex", {})
        entity_path = Path(entity_index.get("path", ""))
        if not entity_path.is_absolute():
            entity_path = (manifest_path.parent / entity_path).resolve()
        if not entity_path.is_file() or entity_index.get("sha256") != sha256(entity_path):
            fail("CAD native model entity index is missing or has the wrong hash")
        semantic_topology = manifest.get("semanticTopology", {})
        topology_path = Path(semantic_topology.get("path", ""))
        if not topology_path.is_absolute():
            topology_path = (manifest_path.parent / topology_path).resolve()
        if (
            semantic_topology.get("format") != "step-derived-occurrence-glb"
            or not topology_path.is_file()
            or semantic_topology.get("sha256") != sha256(topology_path)
        ):
            fail("CAD STEP-derived occurrence topology is missing or has the wrong hash")
        entities = json.loads(entity_path.read_text(encoding="utf-8")).get("entities", [])
        renderable = [row for row in entities if row.get("type") != "connection"]
        if not renderable or any(not str(row.get("selector", "")).startswith("#o1.") for row in renderable):
            fail("CAD renderable entities lack native STEP occurrence selectors")
    else:
        for capability in ("raycast", "depth", "entityId"):
            if capabilities.get(capability) is not True:
                fail(f"native model is missing {capability} capability")
        if backend == "blender":
            if capabilities.get("projectionProfile") != "blender-native-object-index-depth-room-v1":
                fail("Blender native model is missing the accepted Object Index/Depth projection profile")
            if capabilities.get("semanticProjection") is not True:
                fail("Blender native model cannot compile native Object Index/Depth semantic evidence")
    native = manifest.get("nativeModel", {})
    model_path = Path(native.get("path", ""))
    if not model_path.is_absolute():
        model_path = (manifest_path.parent / model_path).resolve()
    if not model_path.is_file():
        fail(f"native model does not exist: {model_path}")
    actual_hash = sha256(model_path)
    if native.get("sha256") != actual_hash:
        fail("native model hash mismatch")
    adapter = manifest.get("captureAdapter", {})
    adapter_path = Path(adapter.get("script", ""))
    if not adapter_path.is_absolute():
        adapter_path = (manifest_path.parent / adapter_path).resolve()
    if adapter.get("interface") != "interior.native-capture-adapter.v1" or not adapter_path.is_file():
        fail("native capture adapter is missing or has the wrong interface")
    return backend, actual_hash


def validate_framing(shot: dict) -> dict:
    shot_id = shot["shotId"]
    framing = shot.get("framing")
    if not isinstance(framing, dict):
        fail(f"{shot_id}: framing is required")
    if framing.get("measurementBasis") != "native-model-obb-eight-corners":
        fail(f"{shot_id}: framing must come from all eight native OBB corners")
    envelopes = framing.get("envelopes")
    if not isinstance(envelopes, dict):
        fail(f"{shot_id}: anchor/reference/context envelopes are required")
    anchor = envelopes.get("anchor", {})
    reference = envelopes.get("referenceFacade", {})
    context = envelopes.get("context", {})
    aw = number(anchor.get("widthMeters"), f"{shot_id}.anchor.widthMeters")
    ah = number(anchor.get("heightMeters"), f"{shot_id}.anchor.heightMeters")
    rw = number(reference.get("widthMeters"), f"{shot_id}.reference.widthMeters")
    rh = number(reference.get("heightMeters"), f"{shot_id}.reference.heightMeters")
    cw = number(context.get("widthMeters", 0), f"{shot_id}.context.widthMeters")
    oa = number(framing.get("targetOccupancy"), f"{shot_id}.targetOccupancy")
    of = number(framing.get("referenceOccupancyPolicy"), f"{shot_id}.referenceOccupancyPolicy")
    oc = number(framing.get("contextOccupancyPolicy"), f"{shot_id}.contextOccupancyPolicy")
    ov = number(framing.get("verticalOccupancyPolicy"), f"{shot_id}.verticalOccupancyPolicy")
    if not all(0 < value < 1 for value in (oa, of, oc, ov)):
        fail(f"{shot_id}: occupancy policies must be between zero and one")
    terms = [aw / oa, rw / of, cw / oc if cw else 0, ah / ov * 36 / 22.5, rh / ov * 36 / 22.5]
    frame_width = max(terms)
    declared_width = number(framing.get("frameWidthMeters"), f"{shot_id}.frameWidthMeters")
    if not close(declared_width, frame_width, 0.003):
        fail(f"{shot_id}: frame width is not derived from the three measured envelopes")
    focal = number(shot.get("focalLengthMm"), f"{shot_id}.focalLengthMm")
    if focal == 16 or focal < 18:
        fail(f"{shot_id}: 16mm and shorter lenses are prohibited")
    if focal == 18 and shot.get("tinyRoomAudit", {}).get("accepted") is not True:
        fail(f"{shot_id}: 18mm requires an accepted tiny-room audit")
    expected_distance = frame_width * focal / SENSOR_WIDTH_MM * DISTANCE_SAFETY
    declared_distance = number(framing.get("targetPlaneDistanceMeters"), f"{shot_id}.targetPlaneDistanceMeters")
    if not close(declared_distance, expected_distance, 0.005):
        fail(f"{shot_id}: target distance does not include the fixed 5% safety factor")
    actual_distance = math.dist(vector(shot.get("position"), 3, f"{shot_id}.position"), vector(shot.get("target"), 3, f"{shot_id}.target"))
    if not close(actual_distance, declared_distance, 0.01):
        fail(f"{shot_id}: actual camera distance differs from framing distance")
    if declared_distance > number(framing.get("availableDepthMeters"), f"{shot_id}.availableDepthMeters") + 0.001:
        fail(f"{shot_id}: camera does not fit the measured retreat depth")
    audit = shot.get("projectionAudit")
    if not isinstance(audit, dict):
        fail(f"{shot_id}: native projectionAudit is required")
    margins = audit.get("frameMargins")
    if not isinstance(margins, dict):
        fail(f"{shot_id}: four frame margins are required")
    margin_values = {key: number(margins.get(key), f"{shot_id}.frameMargins.{key}") for key in ("left", "right", "top", "bottom")}
    if min(margin_values.values()) < MIN_MARGIN:
        fail(f"{shot_id}: all frame margins must be at least 6%")
    if abs(margin_values["left"] - margin_values["right"]) > MARGIN_DIFFERENCE_LIMIT:
        fail(f"{shot_id}: left/right margin difference exceeds 3%")
    depth_ratio = number(audit.get("depthScaleRatio"), f"{shot_id}.depthScaleRatio")
    if depth_ratio > DEPTH_SCALE_LIMIT:
        fail(f"{shot_id}: near/far scale ratio exceeds {DEPTH_SCALE_LIMIT}")
    foreground = number(audit.get("foregroundBlockerShare"), f"{shot_id}.foregroundBlockerShare")
    if foreground > FOREGROUND_LIMIT:
        fail(f"{shot_id}: foreground blockers cover more than 8% of the frame")
    if audit.get("mustShowComplete") is not True:
        fail(f"{shot_id}: mustShow elements are not all fully visible")
    return {"frameWidthMeters": round(frame_width, 6), "distanceMeters": round(actual_distance, 6)}


def validate_frontal(shot: dict, structure: dict) -> dict:
    shot_id = shot["shotId"]
    alignment = shot.get("frontalAlignment")
    if not isinstance(alignment, dict) or alignment.get("mode") != "reference-wall-normal":
        fail(f"{shot_id}: selected primary shot must declare reference-wall-normal alignment")
    position = vector(shot.get("position"), 3, f"{shot_id}.position")
    target = vector(shot.get("target"), 3, f"{shot_id}.target")
    axis = normalize3(tuple(target[index] - position[index] for index in range(3)))
    axis_xz = normalize2((axis[0], axis[2]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, axis[1]))))
    wall_start, wall_end = wall_world_segment(structure, alignment.get("referenceWallId"))
    wall_delta = (wall_end[0] - wall_start[0], wall_end[1] - wall_start[1])
    tangent = normalize2(wall_delta)
    normal_a = (-tangent[1], tangent[0])
    normal = normal_a if sum(normal_a[i] * axis_xz[i] for i in range(2)) >= 0 else (-normal_a[0], -normal_a[1])
    yaw = math.degrees(math.asin(max(0.0, min(1.0, abs(sum(axis_xz[i] * tangent[i] for i in range(2)))))))
    denominator = cross2(axis_xz, wall_delta)
    if abs(denominator) <= 1e-9:
        fail(f"{shot_id}: optical axis cannot intersect the reference wall")
    ray_to_wall = (wall_start[0] - position[0], wall_start[1] - position[2])
    ray_distance = cross2(ray_to_wall, wall_delta) / denominator
    segment_t = cross2(ray_to_wall, axis_xz) / denominator
    if ray_distance <= 0 or not -GEOMETRY_TOLERANCE <= segment_t <= 1 + GEOMETRY_TOLERANCE:
        fail(f"{shot_id}: optical ray does not hit the declared wall segment")
    roll = number(alignment.get("rollDeg"), f"{shot_id}.rollDeg")
    residual = number(alignment.get("alignmentResidualDeg"), f"{shot_id}.alignmentResidualDeg")
    if yaw > YAW_LIMIT or abs(pitch) > PITCH_LIMIT or abs(roll) > ROLL_LIMIT or residual > RESIDUAL_LIMIT:
        fail(f"{shot_id}: camera is not square to the background wall")
    if abs(position[1] - target[1]) > GEOMETRY_TOLERANCE:
        fail(f"{shot_id}: camera and target heights differ")
    if not close_vector(vector(alignment.get("wallTangentXZ"), 2, f"{shot_id}.wallTangentXZ"), tangent):
        fail(f"{shot_id}: wall tangent is not derived from structure data")
    if not close_vector(vector(alignment.get("wallNormalXZ"), 2, f"{shot_id}.wallNormalXZ"), normal):
        fail(f"{shot_id}: wall normal is not derived from structure data")
    if not close_vector(vector(alignment.get("opticalAxisXYZ"), 3, f"{shot_id}.opticalAxisXYZ"), axis):
        fail(f"{shot_id}: optical axis does not match position and target")
    fixed_tolerances = {"yawErrorDeg": YAW_LIMIT, "pitchAbsDeg": PITCH_LIMIT, "rollAbsDeg": ROLL_LIMIT, "alignmentResidualDeg": RESIDUAL_LIMIT}
    if alignment.get("tolerances") != fixed_tolerances:
        fail(f"{shot_id}: frontal tolerances are not the Skill constants")
    return {"yawErrorDeg": round(yaw, 6), "pitchDeg": round(pitch, 6), "rollDeg": round(roll, 6), "referenceWallId": alignment["referenceWallId"]}


def validate_candidate_audit(
    group: dict,
    compiled_group: dict,
    backend: str,
    model_hash: str,
    plan_root: Path,
) -> dict:
    group_id = group.get("candidateGroupId")
    audit = group.get("candidateAudit")
    if not isinstance(audit, dict):
        fail(f"{group_id}: candidateAudit is required")
    if audit.get("modelBackend") != backend or audit.get("sourceModelSha256") != model_hash:
        fail(f"{group_id}: candidate previews are not from the selected native model")
    if audit.get("selectionMethod") != "deterministic-first-fitting-with-one-bounded-fallback":
        fail(f"{group_id}: unsupported candidate selection method")
    ordered = audit.get("orderedFittingCandidateIds")
    evidence = audit.get("nativePreviewEvidence")
    if not isinstance(ordered, list) or not ordered or len(set(ordered)) != len(ordered):
        fail(f"{group_id}: ordered fitting candidate IDs are required")
    candidate_set = compiled_group.get("candidateSet", {})
    if ordered != candidate_set.get("fittingCandidateIds"):
        fail(f"{group_id}: fitting order differs from the deterministic batch compiler")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 2:
        fail(f"{group_id}: exactly one primary preview and at most one fallback are allowed")
    if [row.get("candidateId") for row in evidence] != ordered[:len(evidence)]:
        fail(f"{group_id}: native previews do not follow deterministic fitting order")
    if [row.get("candidateId") for row in evidence] != candidate_set.get(
        "nativePreviewCandidateIds", []
    )[:len(evidence)]:
        fail(f"{group_id}: native previews differ from the bounded batch output")
    ids = set()
    for row in evidence:
        candidate_id = row.get("candidateId")
        if not candidate_id or candidate_id in ids:
            fail(f"{group_id}: candidate IDs must be unique")
        ids.add(candidate_id)
        if row.get("modelBackend") != backend or row.get("sourceModelSha256") != model_hash:
            fail(f"{group_id}: candidate evidence backend/hash mismatch")
        image_path = Path(row.get("imagePath", ""))
        if not image_path.is_absolute():
            image_path = (plan_root / image_path).resolve()
        if not image_path.is_file() or sha256(image_path) != row.get("imageSha256"):
            fail(f"{group_id}: native candidate screenshot/hash mismatch")
        if not isinstance(row.get("projectionAccepted"), bool):
            fail(f"{group_id}: every native preview requires a projectionAccepted result")
        if row.get("projectionAccepted") is False and not row.get("failureCodes"):
            fail(f"{group_id}: rejected native preview requires machine-readable failureCodes")
        camera_evidence_path = Path(row.get("cameraEvidencePath", ""))
        if not camera_evidence_path.is_absolute():
            camera_evidence_path = (plan_root / camera_evidence_path).resolve()
        if (
            not camera_evidence_path.is_file()
            or sha256(camera_evidence_path) != row.get("cameraEvidenceSha256")
        ):
            fail(f"{group_id}: native camera evidence file/hash mismatch")
        camera_evidence = read_json(camera_evidence_path)
        if (
            camera_evidence.get("schema") != "interior.camera-plan-evidence.v2"
            or camera_evidence.get("source") != "same-native-model-camera-state"
            or camera_evidence.get("coordinateSystem") != "interior-world-y-up.v1"
            or camera_evidence.get("modelBackend") != backend
            or camera_evidence.get("sourceModelSha256") != model_hash
        ):
            fail(f"{group_id}: native camera evidence identity is invalid")
        row["_validatedCameraEvidence"] = camera_evidence
    accepted_ids = [row["candidateId"] for row in evidence if row.get("projectionAccepted") is True]
    selected = audit.get("selectedCandidateId")
    if not accepted_ids or selected != accepted_ids[0]:
        fail(f"{group_id}: selected candidate must be the first accepted deterministic preview")
    if len(evidence) == 2 and evidence[0].get("projectionAccepted") is not False:
        fail(f"{group_id}: fallback preview is forbidden when the primary projection passed")
    selected_row = next(row for row in evidence if row.get("candidateId") == selected)
    compiled_candidates = {
        row.get("candidateId"): row for row in candidate_set.get("candidates", [])
    }
    if selected not in compiled_candidates:
        fail(f"{group_id}: selected candidate is absent from the deterministic batch")
    return {
        "candidateId": selected,
        "cameraEvidence": selected_row["_validatedCameraEvidence"],
        "compiledCandidate": compiled_candidates[selected],
    }


def validate_candidate_compilation(
    plan: dict,
    plan_root: Path,
    backend: str,
    model_hash: str,
) -> dict[str, dict]:
    descriptor = plan.get("candidateCompilation")
    if not isinstance(descriptor, dict):
        fail("camera plan requires one candidateCompilation binding")
    batch_path = Path(descriptor.get("path", ""))
    if not batch_path.is_absolute():
        batch_path = (plan_root / batch_path).resolve()
    if not batch_path.is_file() or sha256(batch_path) != descriptor.get("sha256"):
        fail("camera candidate compilation file/hash mismatch")
    batch = read_json(batch_path)
    if batch.get("schema") != "interior.camera-candidate-batch.v1":
        fail("camera candidate compilation must use v1")
    unsigned = dict(batch)
    declared_digest = unsigned.pop("batchDigestSha256", None)
    encoded = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    actual_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if declared_digest != actual_digest or descriptor.get("batchDigestSha256") != actual_digest:
        fail("camera candidate compilation digest mismatch")
    if (
        batch.get("methodVersion") != METHOD_VERSION
        or batch.get("modelBackend") != backend
        or batch.get("sourceModelSha256") != model_hash
        or batch.get("floorplanId") != plan.get("floorplanId")
    ):
        fail("camera candidate compilation identity differs from the camera plan")
    seed_descriptor = plan.get("frontalSeedSet", {})
    bindings = batch.get("bindings", {})
    if (
        bindings.get("seedSetSha256") != seed_descriptor.get("sha256")
        or bindings.get("seedSetDigestSha256") != seed_descriptor.get("seedSetDigestSha256")
    ):
        fail("camera candidate compilation belongs to a different frontal seed set")
    seed_path = Path(bindings.get("seedSetPath", ""))
    if not seed_path.is_absolute():
        seed_path = (batch_path.parent / seed_path).resolve()
    if not seed_path.is_file() or sha256(seed_path) != bindings.get("seedSetSha256"):
        fail("camera frontal seed file/hash mismatch in the candidate compilation")
    measurement_path = Path(bindings.get("measurementsPath", ""))
    if not measurement_path.is_absolute():
        measurement_path = (batch_path.parent / measurement_path).resolve()
    if not measurement_path.is_file() or sha256(measurement_path) != bindings.get("measurementsSha256"):
        fail("camera envelope measurements file/hash mismatch")
    measurements = read_json(measurement_path)
    if measurements.get("schema") != "interior.native-camera-envelope-measurements.v1":
        fail("camera envelope measurements must use v1")
    measurement_unsigned = dict(measurements)
    measurement_digest = measurement_unsigned.pop("measurementDigestSha256", None)
    measurement_encoded = json.dumps(
        measurement_unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if (
        measurement_digest
        != hashlib.sha256(measurement_encoded.encode("utf-8")).hexdigest()
        or measurement_digest != bindings.get("measurementDigestSha256")
    ):
        fail("camera envelope measurement digest mismatch")
    recomputed = compile_batch(seed_path, measurement_path)
    if (
        recomputed.get("rooms") != batch.get("rooms")
        or recomputed.get("policy") != batch.get("policy")
        or recomputed.get("methodVersion") != batch.get("methodVersion")
    ):
        fail("camera candidate compilation differs from the deterministic algorithm result")
    rooms = batch.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        fail("camera candidate compilation has no room groups")
    by_group = {row.get("candidateGroupId"): row for row in rooms}
    if len(by_group) != len(rooms) or None in by_group:
        fail("camera candidate compilation group IDs must be unique")
    return by_group


def validate_circulation_binding(plan: dict, plan_root: Path, backend: str, model_hash: str) -> dict:
    descriptor = plan.get("circulationResult")
    if not isinstance(descriptor, dict):
        fail("camera plan requires one circulationResult binding")
    result_path = Path(descriptor.get("path", ""))
    if not result_path.is_absolute():
        result_path = (plan_root / result_path).resolve()
    if not result_path.is_file() or sha256(result_path) != descriptor.get("sha256"):
        fail("camera plan circulationResult file/hash mismatch")
    result = read_json(result_path)
    if result.get("schema") != "interior.circulation-result.v2":
        fail("camera plan circulation result must use v2")
    unsigned = dict(result)
    digest = unsigned.pop("resultDigestSha256", None)
    encoded = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    actual_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if digest != actual_digest or descriptor.get("resultDigestSha256") != digest:
        fail("camera plan circulation result digest mismatch")
    if result.get("modelBackend") != backend or result.get("bindings", {}).get("nativeModelSha256") != model_hash:
        fail("camera plan circulation result belongs to a different native model")
    if result.get("verdict", {}).get("cameraWorkflowAllowed") is not True:
        fail("camera plan circulation result does not allow camera work")
    for key in ("topologyAuditDigestSha256", "layoutRelationshipAuditDigestSha256"):
        if descriptor.get(key) != result.get("bindings", {}).get(key):
            fail(f"camera plan circulation binding differs for {key}")
    return result


def validate_frontal_seed_binding(
    plan: dict,
    plan_root: Path,
    backend: str,
    model_hash: str,
    circulation: dict,
    structure_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, dict], set[str]]:
    descriptor = plan.get("frontalSeedSet")
    if not isinstance(descriptor, dict):
        fail("camera plan requires one frontalSeedSet binding")
    seed_path = Path(descriptor.get("path", ""))
    if not seed_path.is_absolute():
        seed_path = (plan_root / seed_path).resolve()
    if not seed_path.is_file() or sha256(seed_path) != descriptor.get("sha256"):
        fail("camera plan frontalSeedSet file/hash mismatch")
    seed_set = read_json(seed_path)
    if seed_set.get("schema") != "interior.camera-frontal-seed-set.v1":
        fail("camera plan frontal seed set must use v1")
    unsigned = dict(seed_set)
    digest = unsigned.pop("seedSetDigestSha256", None)
    encoded = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    actual_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if digest != actual_digest or descriptor.get("seedSetDigestSha256") != digest:
        fail("camera frontal seed set digest mismatch")
    if seed_set.get("methodVersion") != METHOD_VERSION:
        fail("camera frontal seed set uses the wrong algorithm version")
    if seed_set.get("modelBackend") != backend or seed_set.get("sourceModelSha256") != model_hash:
        fail("camera frontal seed set belongs to a different native model")
    if seed_set.get("algorithm", {}).get("status") != "ready":
        fail("camera frontal seed solver is not ready")
    if seed_set.get("bindings", {}).get("circulationResultDigestSha256") != circulation.get("resultDigestSha256"):
        fail("camera frontal seed set belongs to a different circulation result")
    bindings = seed_set.get("bindings", {})
    bound_paths = {}
    for field, hash_field in (
        ("structureDataPath", "structureDataSha256"),
        ("circulationScenePath", "circulationSceneSha256"),
        ("circulationResultPath", "circulationResultSha256"),
        ("nativeManifestPath", "nativeManifestSha256"),
    ):
        bound_path = Path(bindings.get(field, ""))
        if not bound_path.is_absolute():
            bound_path = (seed_path.parent / bound_path).resolve()
        if not bound_path.is_file() or sha256(bound_path) != bindings.get(hash_field):
            fail(f"camera frontal seed binding differs for {field}")
        bound_paths[field] = bound_path
    if bound_paths["structureDataPath"] != structure_path.resolve():
        fail("camera frontal seed structure differs from the validated structure")
    if bound_paths["nativeManifestPath"] != manifest_path.resolve():
        fail("camera frontal seed manifest differs from the validated native manifest")
    if read_json(bound_paths["circulationResultPath"]) != circulation:
        fail("camera frontal seed circulation result differs from the camera-plan binding")
    seeds = seed_set.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        fail("camera frontal seed set has no solved rooms")
    by_id = {}
    room_ids = set()
    for seed in seeds:
        seed_id = seed.get("seedId")
        room_id = seed.get("roomId")
        if not seed_id or seed_id in by_id or not room_id or room_id in room_ids:
            fail("camera frontal seed IDs and room IDs must be unique")
        if seed.get("role") != "primary" or seed.get("composition") != "one-point-frontal":
            fail(f"{seed_id}: frontal seed must be a one-point-frontal primary")
        seed_unsigned = dict(seed)
        seed_digest = seed_unsigned.pop("seedDigestSha256", None)
        seed_encoded = json.dumps(seed_unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if seed_digest != hashlib.sha256(seed_encoded.encode("utf-8")).hexdigest():
            fail(f"{seed_id}: seed digest is invalid")
        by_id[seed_id] = seed
        room_ids.add(room_id)
    if set(seed_set.get("requestedRoomIds", [])) != room_ids:
        fail("camera frontal seed requested rooms differ from solved seeds")
    try:
        recomputed = build_seed_set(
            structure_path=bound_paths["structureDataPath"],
            scene_path=bound_paths["circulationScenePath"],
            circulation_result_path=bound_paths["circulationResultPath"],
            native_manifest_path=bound_paths["nativeManifestPath"],
            requested_room_ids=list(seed_set["requestedRoomIds"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        fail(f"camera frontal seed algorithm could not be recomputed: {exc}")
    if recomputed.get("seedSetDigestSha256") != seed_set.get("seedSetDigestSha256"):
        fail("camera frontal seed set differs from the deterministic algorithm result")
    return by_id, room_ids


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: validate_camera_manifest.py <camera-plan.json> <native-model-manifest.json> <structure-data.json>")
    plan_path, manifest_path, structure_path = map(lambda value: Path(value).resolve(), sys.argv[1:])
    plan = read_json(plan_path)
    manifest = read_json(manifest_path)
    structure = read_json(structure_path)
    backend, model_hash = validate_native_manifest(manifest, manifest_path)
    if structure.get("schema") != "interior.floorplan-structure.v3":
        fail("structure must use interior.floorplan-structure.v3")
    model_scope = validate_model_scope(manifest, structure, structure_path)
    required_plan = {
        "schema": "interior.camera-plan.v8",
        "schemaVersion": "8.0",
        "methodVersion": METHOD_VERSION,
        "coordinateSystem": "interior-world-y-up.v1",
        "modelBackend": backend,
        "sourceModelSha256": model_hash,
        "floorplanId": manifest.get("floorplanId"),
    }
    for field, expected in required_plan.items():
        if plan.get(field) != expected:
            fail(f"camera plan {field} must be {expected!r}")
    if structure.get("floorplanId") != plan.get("floorplanId"):
        fail("camera plan, native model and structure belong to different floorplans")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", plan.get("seriesId", "")):
        fail("invalid seriesId")
    if plan.get("planPhase") != "final-selection":
        fail("only final-selection camera plans may pass the handoff gate")
    circulation = validate_circulation_binding(plan, plan_path.parent, backend, model_hash)
    if circulation.get("floorplanId") != plan.get("floorplanId"):
        fail("camera plan and circulation result belong to different floorplans")
    frontal_seeds, frontal_seed_room_ids = validate_frontal_seed_binding(
        plan,
        plan_path.parent,
        backend,
        model_hash,
        circulation,
        structure_path,
        manifest_path,
    )
    compiled_groups = validate_candidate_compilation(
        plan,
        plan_path.parent,
        backend,
        model_hash,
    )

    room_ids = {room.get("id") for room in structure.get("rooms", [])}
    groups = plan.get("candidateGroups")
    if not isinstance(groups, list) or not groups:
        fail("candidateGroups are required")
    group_ids = set()
    selected_candidate_by_group = {}
    for group in groups:
        group_id = group.get("candidateGroupId")
        if not group_id or group_id in group_ids:
            fail("candidateGroupId values must be unique")
        group_ids.add(group_id)
        compiled_group = compiled_groups.get(group_id)
        if compiled_group is None or compiled_group.get("roomId") != group.get("roomId"):
            fail(f"{group_id}: candidate group differs from the deterministic batch")
        selected_candidate_by_group[group_id] = validate_candidate_audit(
            group, compiled_group, backend, model_hash, plan_path.parent
        )
    if set(compiled_groups) != group_ids:
        fail("camera plan candidate groups must exactly equal the deterministic batch")

    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        fail("camera plan must contain shots")
    shot_ids = set()
    selected_by_room: dict[str, int] = {}
    selected_primary_by_room: dict[str, int] = {}
    selected_shot_ids_by_room: dict[str, set[str]] = {}
    audits = []
    for shot in shots:
        shot_id = shot.get("shotId")
        if not shot_id or shot_id in shot_ids:
            fail("shotId values must be unique")
        shot_ids.add(shot_id)
        if shot.get("candidateGroupId") not in group_ids:
            fail(f"{shot_id}: unknown candidate group")
        if shot.get("roomId") not in room_ids:
            fail(f"{shot_id}: unknown roomId")
        if shot.get("modelBackend") != backend or shot.get("sourceModelSha256") != model_hash:
            fail(f"{shot_id}: backend/native model hash mismatch")
        if shot.get("selectionStatus") != "selected":
            continue
        selected_candidate = selected_candidate_by_group[shot.get("candidateGroupId")]
        if shot.get("candidateId") != selected_candidate["candidateId"]:
            fail(f"{shot_id}: selected shot does not use the deterministic group selection")
        camera_evidence = selected_candidate["cameraEvidence"]
        compiled_candidate = selected_candidate["compiledCandidate"]
        for field in (
            "position",
            "target",
            "focalLengthMm",
            "fov",
            "framing",
            "frontalAlignment",
        ):
            if shot.get(field) != compiled_candidate.get(field):
                fail(f"{shot_id}: {field} differs from the deterministic batch candidate")
        if camera_evidence.get("shotId") != shot_id:
            fail(f"{shot_id}: native camera evidence belongs to a different shot")
        if not close_vector(
            vector(camera_evidence.get("position"), 3, f"{shot_id}.evidence.position"),
            vector(shot.get("position"), 3, f"{shot_id}.position"),
        ) or not close_vector(
            vector(camera_evidence.get("target"), 3, f"{shot_id}.evidence.target"),
            vector(shot.get("target"), 3, f"{shot_id}.target"),
        ):
            fail(f"{shot_id}: native screenshot camera pose differs from the selected shot")
        if not close(
            number(camera_evidence.get("focalLengthMm"), f"{shot_id}.evidence.focalLengthMm"),
            number(shot.get("focalLengthMm"), f"{shot_id}.focalLengthMm"),
            0.001,
        ):
            fail(f"{shot_id}: native screenshot focal length differs from the selected shot")
        selected_by_room[shot["roomId"]] = selected_by_room.get(shot["roomId"], 0) + 1
        selected_shot_ids_by_room.setdefault(shot["roomId"], set()).add(shot_id)
        if shot.get("role") == "primary":
            if shot.get("composition") != "one-point-frontal":
                fail(f"{shot_id}: primary shot composition must be one-point-frontal")
            seed = frontal_seeds.get(shot.get("frontalSeedId"))
            if not seed or seed.get("roomId") != shot.get("roomId"):
                fail(f"{shot_id}: primary shot is not bound to its deterministic frontal seed")
            if seed.get("referenceWallId") != shot.get("frontalAlignment", {}).get("referenceWallId"):
                fail(f"{shot_id}: primary reference wall differs from the deterministic seed")
            target = vector(shot.get("target"), 3, f"{shot_id}.target")
            seed_target = vector(seed.get("targetWorldXZ"), 2, f"{shot_id}.seed.targetWorldXZ")
            if not close_vector((target[0], target[2]), seed_target):
                fail(f"{shot_id}: primary target differs from the deterministic seed")
            framing_envelopes = shot.get("framing", {}).get("envelopes", {})
            seed_anchor_ids = set(seed.get("anchorElementIds", []))
            measured_anchor_ids = set(framing_envelopes.get("anchor", {}).get("elementIds", []))
            if seed_anchor_ids and measured_anchor_ids != seed_anchor_ids:
                fail(f"{shot_id}: measured anchor envelope differs from the deterministic seed")
            measured_reference_ids = set(
                framing_envelopes.get("referenceFacade", {}).get("elementIds", [])
            )
            if seed.get("referenceWallId") not in measured_reference_ids:
                fail(f"{shot_id}: measured reference facade omits the deterministic seed wall")
            selected_primary_by_room[shot["roomId"]] = selected_primary_by_room.get(shot["roomId"], 0) + 1
        elif shot.get("composition") == "one-point-frontal":
            fail(f"{shot_id}: one-point-frontal is reserved for the unique room primary")
        elif shot.get("frontalSeedId") is not None:
            fail(f"{shot_id}: only a primary shot may bind a frontalSeedId")
        host = validate_camera_host(shot, structure)
        framing = validate_framing(shot)
        frontal = validate_frontal(shot, structure) if shot.get("role") == "primary" else None
        visibility = shot.get("visibility", {})
        if visibility.get("contextPolicy") != "preserve-visible-adjacent-spaces" or visibility.get("occlusionPolicy") != "ray-blocking-local-elements-only":
            fail(f"{shot_id}: visibility must preserve context and hide only proven local blockers")
        for hidden in visibility.get("hiddenElementEvidence", []):
            if hidden.get("decision") != "hide-local-ray-blocker" or hidden.get("nativeRaycastConfirmed") is not True:
                fail(f"{shot_id}: every hidden object needs native raycast evidence")
        must_show = shot.get("mustShowElements")
        if not isinstance(must_show, list) or not must_show or len(must_show) != len(set(must_show)):
            fail(f"{shot_id}: mustShowElements must be a non-empty unique list")
        envelopes = shot["framing"]["envelopes"]
        required_must_show = {
            element_id
            for envelope_name in ("anchor", "referenceFacade")
            for element_id in envelopes.get(envelope_name, {}).get("elementIds", [])
        } | set(visibility.get("preserveElementIds", []))
        missing_must_show = sorted(required_must_show - set(must_show))
        if missing_must_show:
            fail(
                f"{shot_id}: framing/context elements are missing from mustShowElements: "
                f"{missing_must_show}"
            )
        if shot.get("role") == "primary":
            seed_anchor_ids = set(frontal_seeds[shot["frontalSeedId"]].get("anchorElementIds", []))
            if not seed_anchor_ids.issubset(set(must_show)):
                fail(f"{shot_id}: deterministic seed anchors are missing from mustShowElements")
        audits.append({"shotId": shot_id, "cameraHost": host, "framing": framing, "frontal": frontal})

    capture_scope = plan.get("captureScope")
    if capture_scope is None:
        requested_room_ids = set(room_ids)
    else:
        if capture_scope.get("mode") != "requested-room-subset":
            fail("captureScope.mode must be requested-room-subset")
        requested = capture_scope.get("requestedRoomIds")
        context = capture_scope.get("allowedContextRoomIds", [])
        excluded = capture_scope.get("excludedRoomIds")
        if (
            not isinstance(requested, list)
            or not requested
            or len(requested) != len(set(requested))
            or not set(requested).issubset(room_ids)
        ):
            fail("captureScope.requestedRoomIds must be one non-empty unique structure-room subset")
        if (
            not isinstance(context, list)
            or len(context) != len(set(context))
            or not set(context).issubset(room_ids)
            or set(context) & set(requested)
        ):
            fail("captureScope.allowedContextRoomIds must be a disjoint unique structure-room subset")
        if (
            not isinstance(excluded, list)
            or len(excluded) != len(set(excluded))
            or set(excluded) != room_ids - set(requested) - set(context)
        ):
            fail("captureScope must partition requested, allowed-context, and excluded rooms")
        if not str(capture_scope.get("reason", "")).strip():
            fail("a requested-room-subset captureScope requires a reason")
        requested_room_ids = set(requested)
        unexpected_selected = set(selected_by_room) - requested_room_ids
        if unexpected_selected:
            fail(f"selected shots exist outside captureScope: {sorted(unexpected_selected)}")

    if model_scope.get("mode") == "room-subset":
        if capture_scope is None:
            fail("room-subset native models require a matching camera captureScope")
        if set(capture_scope.get("requestedRoomIds", [])) != set(model_scope["requestedRoomIds"]):
            fail("camera requested rooms differ from the native model scope")
        if set(capture_scope.get("allowedContextRoomIds", [])) != set(model_scope["allowedContextRoomIds"]):
            fail("camera allowed context differs from the native model scope")

    if frontal_seed_room_ids != requested_room_ids:
        fail("frontal seed rooms must exactly equal the camera capture scope")

    coverage = plan.get("roomCoverage")
    if not isinstance(coverage, list) or not coverage:
        fail("roomCoverage is required")
    coverage_ids = [row.get("roomId") for row in coverage]
    if len(coverage_ids) != len(set(coverage_ids)) or set(coverage_ids) != requested_room_ids:
        fail("roomCoverage must enumerate every requested capture-scope room exactly once")
    for row in coverage:
        room_id = row.get("roomId")
        if row.get("requiredFrontalPrimary") is not True:
            fail(f"room {room_id} must require one frontal primary")
        if selected_primary_by_room.get(room_id, 0) != 1:
            fail(f"room {room_id} must have exactly one accepted wall-normal primary shot")
        if set(row.get("selectedShotIds", [])) != selected_shot_ids_by_room.get(room_id, set()):
            fail(f"room {room_id} coverage selectedShotIds differ from selected shots")
    result = {
        "schema": "interior.camera-plan-validation.v1",
        "accepted": True,
        "modelBackend": backend,
        "sourceModelSha256": model_hash,
        "selectedShotCount": sum(selected_by_room.values()),
        "audits": audits,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        raise SystemExit(f"camera plan rejected: {exc}") from exc
