#!/usr/bin/env python3
"""Select one deterministic, reversible layout correction for the active backend."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any, Iterable

from common import (
    Point,
    canonical_sha256,
    point_in_polygon,
    point_polygon_edge_distance,
    point_segment_distance,
    polygon_centroid,
    polygon_inside_polygon,
    polygons_intersect,
    read_json,
    require_schema,
    sha256_file,
    translate_polygon,
    write_json,
)


STRUCTURE_SCHEMA = "interior.floorplan-structure.v3"
SCENE_SCHEMA = "interior.circulation-scene.v2"
AUDIT_SCHEMA = "interior.circulation-audit.v2"
POLICY_SCHEMA = "interior.circulation-policy.v2"
PLAN_SCHEMA = "interior.circulation-adjustment-plan.v2"
LOCAL_AXES = {
    "+X": (1.0, 0.0),
    "-X": (-1.0, 0.0),
    "+Z": (0.0, 1.0),
    "-Z": (0.0, -1.0),
}


def verified_document_digest(document: dict[str, Any], key: str, label: str) -> str:
    expected = document.get(key)
    payload = dict(document)
    payload.pop(key, None)
    actual = canonical_sha256(payload)
    if expected != actual:
        raise ValueError(f"{label} canonical digest is invalid")
    return actual


def operation_digest(operation: dict[str, Any]) -> str:
    target = operation.get("target", {})
    identifier = operation.get("targetPlacementId") or operation.get("targetEntityId")
    material = {
        "backend": str(operation.get("backend", "")),
        "operation": str(operation.get("operation", "")),
        "targetId": str(identifier or ""),
        "position": [f"{float(value):.6f}" for value in target.get("position", [])],
        "rotationYRadians": f"{float(target.get('rotationYRadians', 0)):.9f}",
    }
    return canonical_sha256(material)


def plan_execution_digest(document: dict[str, Any]) -> str:
    material = {
        "schema": str(document.get("schema", "")),
        "floorplanId": str(document.get("floorplanId", "")),
        "modelBackend": str(document.get("modelBackend", "")),
        "auditDigestSha256": str(document.get("bindings", {}).get("auditDigestSha256", "")),
        "circulationSceneSha256": str(document.get("bindings", {}).get("circulationSceneSha256", "")),
        "inputStateDigestSha256": str(document.get("inputStateDigestSha256", "")),
        "workflowStatus": str(document.get("workflowStatus", "")),
        "selectedCandidateId": str(document.get("automaticDecision", {}).get("selectedCandidateId") or ""),
        "operationDigestSha256": str(document.get("automaticDecision", {}).get("operationDigestSha256") or ""),
    }
    return canonical_sha256(material)


def verified_plan_digest(document: dict[str, Any]) -> str:
    declared = document.get("planDigestSha256")
    actual = plan_execution_digest(document)
    if declared != actual:
        raise ValueError("previous adjustment plan canonical digest is invalid")
    return actual


def active_position(component: dict[str, Any]) -> Point:
    active = component.get("activeTransform", {}).get("position")
    if isinstance(active, list) and len(active) >= 2:
        return float(active[0]), float(active[1])
    return polygon_centroid([tuple(map(float, point)) for point in component["footprint"]])


def normalize_vector(vector: Point) -> Point:
    length = math.hypot(*vector)
    if length <= 1e-9:
        raise ValueError("cannot normalize a zero-length direction")
    return vector[0] / length, vector[1] / length


def normalize_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def target_rotation(component: dict[str, Any], axis_role: str, desired_axis: Point) -> float:
    local_name = component.get("localAxes", {}).get(axis_role)
    local = LOCAL_AXES.get(local_name)
    if local is None:
        raise ValueError(f"{component.get('id')} lacks reviewed {axis_role} axis")
    local_angle = math.atan2(local[1], local[0])
    desired_angle = math.atan2(desired_axis[1], desired_axis[0])
    return normalize_angle(local_angle - desired_angle)


def rotate_polygon_clockwise(
    polygon: list[Point], center: Point, delta_radians: float
) -> list[Point]:
    cosine = math.cos(delta_radians)
    sine = math.sin(delta_radians)
    rotated = []
    for point in polygon:
        x = point[0] - center[0]
        y = point[1] - center[1]
        rotated.append(
            (
                center[0] + x * cosine + y * sine,
                center[1] - x * sine + y * cosine,
            )
        )
    return rotated


def nearest_point_on_segment(point: Point, start: Point, end: Point) -> Point:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    denominator = delta_x * delta_x + delta_y * delta_y
    if denominator <= 1e-12:
        return start
    parameter = ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y) / denominator
    parameter = max(0.0, min(1.0, parameter))
    return start[0] + delta_x * parameter, start[1] + delta_y * parameter


def translation_offsets(step: float, maximum: float) -> Iterable[Point]:
    rings = max(1, math.floor(maximum / step + 1e-9))
    for ring in range(1, rings + 1):
        offsets: list[Point] = []
        for x_index in range(-ring, ring + 1):
            for y_index in range(-ring, ring + 1):
                if max(abs(x_index), abs(y_index)) != ring:
                    continue
                offsets.append((round(x_index * step, 6), round(y_index * step, 6)))
        offsets.sort(key=lambda value: (math.hypot(*value), math.atan2(value[1], value[0]), value))
        yield from offsets


def path_clearance(path: list[Point], footprint: list[Point]) -> float:
    if not path:
        return math.inf
    distances = []
    for point in path:
        if point_in_polygon(point, footprint):
            return 0.0
        distances.append(point_polygon_edge_distance(point, footprint))
    return min(distances, default=math.inf)


def transform_is_valid(
    component_id: str,
    footprint: list[Point],
    floor_boundary: list[Point],
    room_polygon: list[Point],
    obstacles: dict[str, list[Point]],
) -> bool:
    if not polygon_inside_polygon(footprint, floor_boundary):
        return False
    if not polygon_inside_polygon(footprint, room_polygon):
        return False
    return not any(
        other_id != component_id and polygons_intersect(footprint, other_polygon)
        for other_id, other_polygon in obstacles.items()
    )


def backend_operation(
    backend: str,
    component: dict[str, Any],
    center: Point,
    rotation_radians: float,
) -> dict[str, Any]:
    identifier = component["id"]
    target = {
        "position": [round(center[0], 6), round(center[1], 6)],
        "rotationYRadians": round(normalize_angle(rotation_radians), 9),
    }
    if backend == "html-threejs":
        return {
            "backend": backend,
            "operation": "set-component-plan-transform",
            "targetPlacementId": identifier,
            "target": target,
        }
    if backend in {"blender", "cad-step"}:
        return {
            "backend": backend,
            "operation": "set-native-entity-plan-transform",
            "targetEntityId": identifier,
            "target": target,
        }
    raise ValueError(f"unsupported backend: {backend}")


def candidate_record(
    *,
    candidate_id: str,
    kind: str,
    priority: int,
    component: dict[str, Any],
    center: Point,
    rotation: float,
    footprint: list[Point],
    backend: str,
    protected_route_ids: list[str] | None = None,
    relationship_key: str | None = None,
    proof: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_center = active_position(component)
    previous_rotation = float(component.get("activeTransform", {}).get("rotationRadians", 0.0))
    movement = math.dist(previous_center, center)
    rotation_change = abs(normalize_angle(rotation - previous_rotation))
    record = {
        "candidateId": candidate_id,
        "correctionKind": kind,
        "priority": priority,
        "componentId": component["id"],
        "roomId": component.get("roomId"),
        "previousPlanCenter": [round(previous_center[0], 6), round(previous_center[1], 6)],
        "previousRotationYRadians": round(normalize_angle(previous_rotation), 9),
        "movementDistanceMeters": round(movement, 6),
        "rotationChangeRadians": round(rotation_change, 9),
        "targetPlanCenter": [round(center[0], 6), round(center[1], 6)],
        "targetRotationYRadians": round(normalize_angle(rotation), 9),
        "targetFootprint": [[round(point[0], 6), round(point[1], 6)] for point in footprint],
        "protectedRouteIds": protected_route_ids or [],
        "relationshipKey": relationship_key,
        "proof": proof or {},
        "backendOperation": backend_operation(backend, component, center, rotation),
        "proofLevel": "deterministic-geometric-candidate",
        "requiresBackendApplyAndFullReaudit": True,
    }
    record["operationDigestSha256"] = operation_digest(record["backendOperation"])
    return record


def relationship_candidate(
    relation: dict[str, Any],
    component: dict[str, Any],
    components: dict[str, dict[str, Any]],
    walls: dict[str, dict[str, Any]],
    obstacles: dict[str, list[Point]],
    floor_boundary: list[Point],
    room_polygon: list[Point],
    backend: str,
) -> dict[str, Any] | None:
    component_id = component["id"]
    center = active_position(component)
    current_rotation = float(component.get("activeTransform", {}).get("rotationRadians", 0.0))
    footprint = obstacles.get(component_id)
    if footprint is None:
        return None
    axis_role = relation.get("axisRole")
    rule_id = relation.get("ruleId")
    relationship_key = "::".join(
        str(value or "-")
        for value in (rule_id, component_id, relation.get("targetId"), relation.get("wallId"))
    )

    if relation.get("wallId"):
        wall = walls.get(relation["wallId"])
        if wall is None:
            return None
        start = tuple(map(float, wall["start"]))
        end = tuple(map(float, wall["end"]))
        nearest = nearest_point_on_segment(center, start, end)
        desired_axis = normalize_vector((nearest[0] - center[0], nearest[1] - center[1]))
        rotation = target_rotation(component, axis_role, desired_axis)
        rotated = rotate_polygon_clockwise(footprint, center, rotation - current_rotation)
        support = max(point[0] * desired_axis[0] + point[1] * desired_axis[1] for point in rotated)
        support_points = [
            point
            for point in rotated
            if abs(point[0] * desired_axis[0] + point[1] * desired_axis[1] - support) <= 0.02
        ]
        gap = max(
            0.0,
            min(point_segment_distance(point, start, end) for point in support_points)
            - float(wall.get("thickness", 0.2)) / 2,
        )
        maximum_gap = float(relation.get("maximumGapMeters", 0.08))
        target_gap = min(0.02, maximum_gap / 2)
        travel = max(0.0, gap - target_gap)
        delta = desired_axis[0] * travel, desired_axis[1] * travel
        moved = translate_polygon(rotated, delta)
        target_center = center[0] + delta[0], center[1] + delta[1]
        if not transform_is_valid(component_id, moved, floor_boundary, room_polygon, obstacles):
            return None
        return candidate_record(
            candidate_id=f"relation::{rule_id}::{component_id}",
            kind="relationship-wall-attachment",
            priority=1,
            component=component,
            center=target_center,
            rotation=rotation,
            footprint=moved,
            backend=backend,
            relationship_key=relationship_key,
            proof={
                "wallId": wall["id"],
                "axisRole": axis_role,
                "measuredGapBeforeMeters": round(gap, 6),
                "targetGapMeters": round(target_gap, 6),
                "targetAxis": [round(value, 6) for value in desired_axis],
            },
        )

    target = components.get(relation.get("targetId"))
    if target is None:
        return None
    target_center = active_position(target)
    desired_axis = normalize_vector((target_center[0] - center[0], target_center[1] - center[1]))
    rotation = target_rotation(component, axis_role, desired_axis)
    rotated = rotate_polygon_clockwise(footprint, center, rotation - current_rotation)
    if not transform_is_valid(component_id, rotated, floor_boundary, room_polygon, obstacles):
        return None
    return candidate_record(
        candidate_id=f"relation::{rule_id}::{component_id}",
        kind="relationship-facing",
        priority=2,
        component=component,
        center=center,
        rotation=rotation,
        footprint=rotated,
        backend=backend,
        relationship_key=relationship_key,
        proof={
            "targetId": target["id"],
            "axisRole": axis_role,
            "targetAxis": [round(value, 6) for value in desired_axis],
        },
    )


def failure_vector(audit: dict[str, Any]) -> dict[str, int]:
    counts = audit.get("counts", {})
    return {
        "integrityErrors": int(counts.get("integrityErrors", 0)),
        "layoutRegressionRoutes": int(counts.get("layoutRegressionRoutes", 0)),
        "layoutRelationshipFailures": int(counts.get("layoutRelationshipFailures", 0)),
    }


def failure_score(vector: dict[str, int]) -> int:
    return vector["integrityErrors"] * 10000 + vector["layoutRegressionRoutes"] * 100 + vector["layoutRelationshipFailures"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--previous-plan")
    args = parser.parse_args()

    structure_path = Path(args.structure).expanduser().resolve()
    scene_path = Path(args.scene).expanduser().resolve()
    audit_path = Path(args.audit).expanduser().resolve()
    policy_path = Path(args.policy).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    structure = read_json(structure_path)
    scene = read_json(scene_path)
    audit = read_json(audit_path)
    policy = read_json(policy_path)
    require_schema(structure, STRUCTURE_SCHEMA, "structure data")
    require_schema(scene, SCENE_SCHEMA, "circulation scene")
    require_schema(audit, AUDIT_SCHEMA, "circulation audit")
    require_schema(policy, POLICY_SCHEMA, "circulation policy")
    verified_document_digest(audit, "auditDigestSha256", "circulation audit")
    if len({structure.get("floorplanId"), scene.get("floorplanId"), audit.get("floorplanId")}) != 1:
        raise ValueError("structure, scene, and audit floorplanId differ")
    if audit.get("bindings", {}).get("circulationSceneSha256") != sha256_file(scene_path):
        raise ValueError("audit is not bound to the supplied circulation scene")
    if audit.get("bindings", {}).get("policySha256") != sha256_file(policy_path):
        raise ValueError("audit is not bound to the supplied policy")
    if scene.get("bindings", {}).get("structureDataSha256") != sha256_file(structure_path):
        raise ValueError("scene is not bound to the supplied structure")

    rooms = {
        room["id"]: [tuple(map(float, point)) for point in room["polygon"]]
        for room in structure.get("rooms", [])
    }
    walls = {wall["id"]: wall for wall in structure.get("walls", [])}
    floor_boundary = [tuple(map(float, point)) for point in structure["floorBoundary"]]
    components = {component["id"]: component for component in scene.get("components", [])}
    obstacles = {
        identifier: [tuple(map(float, point)) for point in component["footprint"]]
        for identifier, component in components.items()
        if component.get("blockingClass") == "floor-obstacle"
    }
    failed_routes = [
        route for route in audit.get("routes", []) if route.get("disposition") == "layout-regression"
    ]
    adjustment_policy = policy.get("adjustment", {})
    step = float(adjustment_policy.get("translationStepMeters", 0.1))
    maximum = float(adjustment_policy.get("maxTranslationMeters", 1.5))
    maximum_candidates = int(adjustment_policy.get("maxCandidatesPerComponent", 1200))
    tolerance = float(policy.get("numericToleranceMeters", 0.05))

    route_map = {route["id"]: route for route in failed_routes}
    component_routes: dict[str, set[str]] = {}
    for route in failed_routes:
        attribution = route.get("attribution", {})
        identifiers = (
            attribution.get("provenSingleCulpritIds")
            or attribution.get("contributorIds")
            or attribution.get("candidateComponentIds", [])
        )
        for identifier in identifiers:
            component_routes.setdefault(identifier, set()).add(route["id"])

    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for component_id in sorted(component_routes):
        component = components.get(component_id)
        if component is None or component_id not in obstacles:
            unresolved.append(
                {
                    "componentId": component_id,
                    "blockingKind": "invalid-component-evidence",
                    "reason": "attributed component is missing or not a floor obstacle",
                    "requiresUserDecision": False,
                }
            )
            continue
        if (component.get("reviewedAdjustment") or {}).get("authority") == "user-explicit-layout-correction":
            unresolved.append(
                {
                    "componentId": component_id,
                    "blockingKind": "explicit-user-transform",
                    "reason": "deterministic correction may not override an explicit user transform",
                    "requiresUserDecision": True,
                }
            )
            continue
        room_polygon = rooms.get(component.get("roomId"))
        if room_polygon is None:
            unresolved.append(
                {
                    "componentId": component_id,
                    "blockingKind": "invalid-room-binding",
                    "reason": "component has no valid declared room",
                    "requiresUserDecision": False,
                }
            )
            continue
        footprint = obstacles[component_id]
        protected_routes = [route_map[identifier] for identifier in sorted(component_routes[component_id])]
        tested = 0
        for delta in translation_offsets(step, maximum):
            tested += 1
            if tested > maximum_candidates:
                break
            moved = translate_polygon(footprint, delta)
            if not transform_is_valid(component_id, moved, floor_boundary, room_polygon, obstacles):
                continue
            route_clearances: dict[str, float] = {}
            protects_all = True
            for route in protected_routes:
                shell_path = [tuple(map(float, point)) for point in route.get("shellPath", [])]
                original_clearance = path_clearance(shell_path, footprint)
                clearance = path_clearance(shell_path, moved)
                route_clearances[route["id"]] = round(clearance, 4)
                if clearance <= original_clearance + min(step / 2, tolerance) - 1e-9:
                    protects_all = False
                    break
            if not protects_all:
                continue
            center = active_position(component)
            center = center[0] + delta[0], center[1] + delta[1]
            rotation = float(component.get("activeTransform", {}).get("rotationRadians", 0.0))
            candidates.append(
                candidate_record(
                    candidate_id=f"route::{component_id}::{len(candidates) + 1}",
                    kind="route-clearance-translation",
                    priority=0,
                    component=component,
                    center=center,
                    rotation=rotation,
                    footprint=moved,
                    backend=scene["modelBackend"],
                    protected_route_ids=sorted(component_routes[component_id]),
                    proof={"pathClearanceMeters": route_clearances},
                )
            )
            break
        else:
            tested = maximum_candidates
        if not any(candidate["componentId"] == component_id and candidate["priority"] == 0 for candidate in candidates):
            unresolved.append(
                {
                    "componentId": component_id,
                    "routeIds": sorted(component_routes[component_id]),
                    "blockingKind": "no-safe-transform-within-policy",
                    "reason": "no collision-free translation inside the declared room cleared every protected route",
                    "requiresUserDecision": True,
                }
            )

    for relation in audit.get("layoutRelationshipAudit", {}).get("results", []):
        if relation.get("passed") is True:
            continue
        component_id = relation.get("sourceId")
        component = components.get(component_id)
        room_polygon = rooms.get(component.get("roomId")) if component else None
        if component is None or room_polygon is None:
            unresolved.append(
                {
                    "componentId": component_id,
                    "relationshipRuleId": relation.get("ruleId"),
                    "blockingKind": "invalid-component-evidence",
                    "reason": "relationship source or declared room is missing",
                    "requiresUserDecision": False,
                }
            )
            continue
        if (component.get("reviewedAdjustment") or {}).get("authority") == "user-explicit-layout-correction":
            unresolved.append(
                {
                    "componentId": component_id,
                    "relationshipRuleId": relation.get("ruleId"),
                    "blockingKind": "explicit-user-transform",
                    "reason": "deterministic correction may not override an explicit user transform",
                    "requiresUserDecision": True,
                }
            )
            continue
        try:
            candidate = relationship_candidate(
                relation,
                component,
                components,
                walls,
                obstacles,
                floor_boundary,
                room_polygon,
                scene["modelBackend"],
            )
        except ValueError as exc:
            candidate = None
            reason = str(exc)
        else:
            reason = "no collision-free deterministic transform satisfies the relationship"
        if candidate:
            candidates.append(candidate)
        else:
            unresolved.append(
                {
                    "componentId": component_id,
                    "relationshipRuleId": relation.get("ruleId"),
                    "blockingKind": "relationship-transform-unavailable",
                    "reason": reason,
                    "requiresUserDecision": False,
                }
            )

    candidates.sort(
        key=lambda item: (
            item["priority"],
            item["movementDistanceMeters"],
            item["rotationChangeRadians"],
            item["componentId"],
            item["candidateId"],
        )
    )
    vector = failure_vector(audit)
    score = failure_score(vector)
    state = {
        "circulationSceneSha256": sha256_file(scene_path),
        "auditDigestSha256": audit["auditDigestSha256"],
        "failureVector": vector,
    }
    state_digest = canonical_sha256(state)
    stalled = False
    previous_binding = None
    if args.previous_plan:
        previous_path = Path(args.previous_plan).expanduser().resolve()
        previous = read_json(previous_path)
        require_schema(previous, PLAN_SCHEMA, "previous adjustment plan")
        verified_plan_digest(previous)
        previous_binding = {
            "path": str(previous_path),
            "sha256": sha256_file(previous_path),
            "planDigestSha256": previous["planDigestSha256"],
        }
        previous_score = failure_score(previous.get("failureVector", {}))
        previous_scene_hash = previous.get("bindings", {}).get("circulationSceneSha256")
        stalled = (
            previous.get("automaticDecision", {}).get("action") == "apply-without-user-confirmation"
            and previous_scene_hash != sha256_file(scene_path)
            and score >= previous_score
        )

    audit_status = audit.get("verdict", {}).get("status")
    if audit_status in {"accepted", "accepted-with-source-constraints"}:
        workflow_status = "no-correction-required"
        decision = {"action": "proceed", "selectedCandidateId": None}
    elif audit_status == "blocked-input-integrity":
        workflow_status = "blocked-input-integrity"
        decision = {"action": "stop-on-input-integrity", "selectedCandidateId": None}
    elif stalled:
        workflow_status = "algorithm-stalled"
        decision = {"action": "stop-and-report-algorithm-stalled", "selectedCandidateId": None}
    elif candidates:
        workflow_status = "correction-ready"
        decision = {
            "action": "apply-without-user-confirmation",
            "selectedCandidateId": candidates[0]["candidateId"],
            "operationDigestSha256": candidates[0]["operationDigestSha256"],
        }
    else:
        workflow_status = "algorithm-blocked"
        decision = {"action": "stop-and-report-one-consolidated-blocker", "selectedCandidateId": None}

    user_decision_blockers = [row for row in unresolved if row.get("requiresUserDecision") is True]
    plan = {
        "schema": PLAN_SCHEMA,
        "producer": {"skill": "interior-circulation-planning", "version": "3.1.0"},
        "floorplanId": scene["floorplanId"],
        "modelBackend": scene["modelBackend"],
        "bindings": {
            "structureDataPath": str(structure_path),
            "structureDataSha256": sha256_file(structure_path),
            "circulationScenePath": str(scene_path),
            "circulationSceneSha256": sha256_file(scene_path),
            "circulationAuditPath": str(audit_path),
            "circulationAuditSha256": sha256_file(audit_path),
            "auditDigestSha256": audit["auditDigestSha256"],
            "policyPath": str(policy_path),
            "policySha256": sha256_file(policy_path),
            "previousPlan": previous_binding,
        },
        "authority": {
            "mayChange": ["current furniture/cabinet position and rotation through the active native backend"],
            "mustNotChange": ["red walls", "doors/openings", "windows", "room polygons", "source floorplan evidence"],
            "automaticMutationPerformed": False,
            "selectedOperationIsReversible": decision["action"] == "apply-without-user-confirmation",
        },
        "confirmationPolicy": {
            "deterministicReversibleCorrectionRequiresUserConfirmation": False,
            "repeatConfirmationForbidden": True,
            "askOnlyFor": [
                "conflicting source evidence",
                "missing hard requirement that changes design intent",
                "irreversible, paid, or public action",
                "no safe transform after deterministic search",
            ],
            "consolidateAllQuestionsIntoOne": True,
        },
        "workflowStatus": workflow_status,
        "planDigestScope": "bound-input-state-and-selected-operation-v1",
        "inputStateDigestSha256": state_digest,
        "failureVector": vector,
        "failureScore": score,
        "failedRouteIds": sorted(route["id"] for route in failed_routes),
        "candidates": candidates,
        "unresolved": unresolved,
        "automaticDecision": decision,
        "userDecision": {
            "required": workflow_status == "algorithm-blocked" and bool(user_decision_blockers),
            "questionCountMaximum": 1 if user_decision_blockers else 0,
            "blockers": user_decision_blockers,
        },
        "workflow": [
            "Apply only automaticDecision.selectedCandidateId through the active backend without asking the user.",
            "Export a new native model manifest, rebuild circulation-scene, and rerun the complete audit.",
            "Repeat only while the failure vector strictly improves; algorithm-stalled stops the loop.",
            "Discard this plan after any unbound input change.",
        ],
    }
    plan["planDigestSha256"] = plan_execution_digest(plan)
    write_json(out_path, plan)
    print(
        f"adjustment plan {workflow_status}: {len(candidates)} deterministic candidates, "
        f"{len(unresolved)} unresolved components"
    )
    return {
        "no-correction-required": 0,
        "correction-ready": 0,
        "blocked-input-integrity": 2,
        "algorithm-stalled": 4,
        "algorithm-blocked": 5,
    }[workflow_status]


if __name__ == "__main__":
    raise SystemExit(main())
