#!/usr/bin/env python3
"""Compile room topology from wall evidence, openings, semantic dividers and room seeds."""

from __future__ import annotations

from copy import deepcopy

import cv2
import numpy as np


TOPOLOGY_CLASSES = {"enclosed", "open-zone", "circulation", "attached"}
SPACE_TYPES = {
    "living",
    "dining",
    "kitchen",
    "bedroom",
    "bathroom",
    "study",
    "balcony",
    "entrance",
    "corridor",
    "closet",
    "storage",
    "utility",
    "multipurpose",
    "other",
}
ENCLOSED_SPACE_TYPES = {"bedroom", "bathroom", "study", "closet", "storage"}
TRAVERSABLE_CONNECTION_KINDS = {"door", "open-passage", "sliding-door"}
ENCLOSED_ACCESS_KINDS = {"door", "sliding-door"}
ALL_CONNECTION_KINDS = TRAVERSABLE_CONNECTION_KINDS | {"glazing", "window"}
OPENING_CLASSIFICATIONS = ALL_CONNECTION_KINDS | {"not-opening", "unresolved"}
DIVIDER_TRAVERSAL_TYPES = {"open-passage", "boundary-only"}
CONTOUR_APPROXIMATION_EPSILON_PX = 1.0
MAX_SHARED_BOUNDARY_SNAP_PX = CONTOUR_APPROXIMATION_EPSILON_PX * 2
SOURCE_EVIDENCE_SCHEMA = "interior.floorplan-source-evidence.v4"


def point_segment_distance(
    point: list[float],
    start: list[float],
    end: list[float],
) -> float:
    _, distance = project_point_to_segment(point, start, end)
    return distance


def project_point_to_segment(
    point: list[float],
    start: list[float],
    end: list[float],
) -> tuple[list[float], float]:
    point_vector = np.asarray(point, dtype=float)
    start_vector = np.asarray(start, dtype=float)
    segment_vector = np.asarray(end, dtype=float) - start_vector
    denominator = float(np.dot(segment_vector, segment_vector))
    if denominator == 0:
        return start_vector.tolist(), float(np.linalg.norm(point_vector - start_vector))
    position = float(
        np.clip(
            np.dot(point_vector - start_vector, segment_vector) / denominator,
            0,
            1,
        )
    )
    projection = start_vector + position * segment_vector
    return projection.tolist(), float(np.linalg.norm(point_vector - projection))


def endpoint_on_wall_candidate(point: list[float], candidate: dict) -> bool:
    distances = [
        point_segment_distance(point, start, end)
        for face_name in ("faceA", "faceB")
        for start, end in zip(
            candidate.get(face_name, []),
            candidate.get(face_name, [])[1:],
        )
    ]
    return bool(distances) and min(distances) <= 3


def divider_labels_are_opposite(
    candidate: dict,
    label_candidate_by_id: dict[str, dict],
) -> bool:
    segment = candidate.get("segment", [])
    if not valid_segment(segment):
        return False
    start = np.asarray(segment[0], dtype=float)
    direction = np.asarray(segment[1], dtype=float) - start
    sides = []
    for label_id in candidate.get("sourceLabelIds", []):
        label = label_candidate_by_id.get(label_id)
        if label is None:
            return False
        offset = np.asarray(label.get("point"), dtype=float) - start
        sides.append(float(direction[0] * offset[1] - direction[1] * offset[0]))
    return (
        len(sides) == 2
        and sides[0] != 0
        and sides[1] != 0
        and sides[0] * sides[1] < 0
    )


def divider_endpoints_match_anchors(
    candidate: dict,
    wall_candidate_by_id: dict[str, dict],
) -> bool:
    segment = candidate.get("segment", [])
    anchor_ids = candidate.get("anchorWallCandidateIds", [])
    if not valid_segment(segment) or len(anchor_ids) != 2:
        return False
    anchors = [wall_candidate_by_id.get(anchor_id) for anchor_id in anchor_ids]
    if any(anchor is None for anchor in anchors):
        return False
    direct = (
        endpoint_on_wall_candidate(segment[0], anchors[0])
        and endpoint_on_wall_candidate(segment[1], anchors[1])
    )
    reverse = (
        endpoint_on_wall_candidate(segment[0], anchors[1])
        and endpoint_on_wall_candidate(segment[1], anchors[0])
    )
    return direct or reverse


def bind_wall_geometry(trace_spec: dict, wall_geometry: dict) -> dict:
    """Materialize both rendered wall layers from the frozen wall geometry."""
    if wall_geometry.get("schema") != "interior.floorplan-wall-geometry.v1":
        raise ValueError("invalid wall geometry schema")
    compiled = deepcopy(trace_spec)
    walls = deepcopy(wall_geometry.get("walls", []))
    compiled.setdefault("cleanStructure", {})["walls"] = walls
    compiled.setdefault("layers", {})["walls"] = deepcopy(walls)
    return compiled


def bind_source_openings(
    trace_spec: dict,
    source_evidence: dict,
    semantic_decisions: dict,
) -> dict:
    """Materialize physical openings and non-physical space dividers."""
    if source_evidence.get("schema") != SOURCE_EVIDENCE_SCHEMA:
        raise ValueError("invalid source evidence schema")
    if semantic_decisions.get("schema") != "interior.floorplan-semantic-decisions.v1":
        raise ValueError("invalid semantic decisions schema")

    candidates = source_evidence.get("openingCandidates", [])
    candidate_by_id = {item.get("id"): item for item in candidates}
    decision_rows = semantic_decisions.get("openings", [])
    decision_by_id = {item.get("candidateId"): item for item in decision_rows}
    if (
        len(candidate_by_id) != len(candidates)
        or None in candidate_by_id
        or len(decision_by_id) != len(decision_rows)
        or None in decision_by_id
        or set(candidate_by_id) != set(decision_by_id)
    ):
        raise ValueError(
            "every source opening candidate needs exactly one semantic decision"
        )
    for candidate_id, decision in decision_by_id.items():
        if decision.get("classification") not in OPENING_CLASSIFICATIONS:
            raise ValueError(f"{candidate_id}: unsupported opening classification")
        if decision.get("classification") == "unresolved":
            raise ValueError(f"{candidate_id}: unresolved opening classification")
        if not valid_segment(candidate_by_id[candidate_id].get("segment")):
            raise ValueError(f"{candidate_id}: opening candidate needs one source segment")

    divider_candidates = source_evidence.get("semanticDividerCandidates", [])
    divider_candidate_by_id = {
        item.get("id"): item for item in divider_candidates
    }
    divider_decisions = semantic_decisions.get("dividers", [])
    divider_decision_by_id = {
        item.get("candidateId"): item for item in divider_decisions
    }
    if (
        len(divider_candidate_by_id) != len(divider_candidates)
        or None in divider_candidate_by_id
        or len(divider_decision_by_id) != len(divider_decisions)
        or None in divider_decision_by_id
        or set(divider_candidate_by_id) != set(divider_decision_by_id)
    ):
        raise ValueError(
            "every semantic divider candidate needs exactly one semantic decision"
        )
    label_candidates = source_evidence.get("spaceLabelCandidates", [])
    label_candidate_by_id = {item.get("id"): item for item in label_candidates}
    label_ids = [item.get("id") for item in label_candidates]
    if (
        len(label_ids) != len(label_candidates)
        or None in label_ids
        or len(label_ids) != len(set(label_ids))
    ):
        raise ValueError("space label candidates need unique non-empty IDs")
    known_label_ids = set(label_ids)
    wall_candidates = source_evidence.get("wallCandidates", [])
    wall_candidate_by_id = {item.get("id"): item for item in wall_candidates}
    known_wall_candidate_ids = set(wall_candidate_by_id)
    all_evidence_ids = [
        *(item.get("id") for item in source_evidence.get("wallCandidates", [])),
        *candidate_by_id,
        *divider_candidate_by_id,
        *known_label_ids,
    ]
    if (
        None in all_evidence_ids
        or len(all_evidence_ids) != len(set(all_evidence_ids))
    ):
        raise ValueError("all source evidence IDs must be globally unique")
    for candidate_id, candidate in divider_candidate_by_id.items():
        decision = divider_decision_by_id[candidate_id]
        if decision.get("classification") not in {
            "semantic-divider",
            "not-divider",
            "unresolved",
        }:
            raise ValueError(f"{candidate_id}: unsupported divider classification")
        if decision.get("classification") == "unresolved":
            raise ValueError(f"{candidate_id}: unresolved divider classification")
        traversal = decision.get("traversal")
        if (
            decision.get("classification") == "semantic-divider"
            and traversal not in DIVIDER_TRAVERSAL_TYPES
        ):
            raise ValueError(
                f"{candidate_id}: accepted semantic divider needs traversal "
                "open-passage or boundary-only"
            )
        if (
            decision.get("classification") != "semantic-divider"
            and traversal is not None
        ):
            raise ValueError(
                f"{candidate_id}: rejected divider must not declare traversal"
            )
        if not valid_segment(candidate.get("segment")):
            raise ValueError(f"{candidate_id}: semantic divider needs one segment")
        if (
            len(set(candidate.get("sourceLabelIds", []))) != 2
            or not set(candidate.get("sourceLabelIds", [])) <= known_label_ids
        ):
            raise ValueError(
                f"{candidate_id}: semantic divider needs exactly two known source labels"
            )
        if (
            len(set(candidate.get("anchorWallCandidateIds", []))) != 2
            or not set(candidate.get("anchorWallCandidateIds", []))
            <= known_wall_candidate_ids
        ):
            raise ValueError(
                f"{candidate_id}: semantic divider needs exactly two known wall anchors"
            )
        if not divider_labels_are_opposite(candidate, label_candidate_by_id):
            raise ValueError(
                f"{candidate_id}: source room labels must lie on opposite sides "
                "of the semantic divider"
            )
        if not divider_endpoints_match_anchors(candidate, wall_candidate_by_id):
            raise ValueError(
                f"{candidate_id}: divider endpoints must terminate on the two "
                "declared wall anchors within 3px"
            )

    compiled = deepcopy(trace_spec)
    clean = compiled.setdefault("cleanStructure", {})
    seed_label_by_room = {
        seed.get("id"): seed.get("sourceLabelId")
        for seed in compiled.get("spaceSeeds", [])
    }
    room_by_seed_label: dict[str, str] = {}
    for room_id, label_id in seed_label_by_room.items():
        if not room_id or label_id not in known_label_ids:
            raise ValueError(
                f"{room_id or '<missing-room>'}: space seed must reference one "
                "known immutable source room label"
            )
        if label_id in room_by_seed_label:
            raise ValueError(
                f"{label_id}: one source room label may bind only one space seed"
            )
        room_by_seed_label[label_id] = room_id
    bound_connections = []
    consumed_opening_ids: list[str] = []
    connected_divider_ids: list[str] = []
    for binding in clean.get("connections", []):
        bound = deepcopy(binding)
        source_opening_id = binding.get("sourceOpeningId")
        source_divider_id = binding.get("sourceDividerId")
        if bool(source_opening_id) == bool(source_divider_id):
            raise ValueError(
                f"{binding.get('id')}: connection needs exactly one of "
                "sourceOpeningId or sourceDividerId"
            )
        if source_opening_id:
            candidate = candidate_by_id.get(source_opening_id)
            decision = decision_by_id.get(source_opening_id)
            classification = decision.get("classification") if decision else None
            if candidate is None or classification not in (
                TRAVERSABLE_CONNECTION_KINDS | {"glazing"}
            ):
                raise ValueError(
                    f"{binding.get('id')}: sourceOpeningId must name one classified "
                    "door, sliding-door, open-passage or glazing candidate"
                )
            bound["kind"] = classification
            bound["segment"] = deepcopy(candidate["segment"])
            bound["sourceTraceIds"] = [source_opening_id]
            bound["openingStyle"] = deepcopy(candidate.get("symbolEvidence", {}))
            consumed_opening_ids.append(source_opening_id)
        else:
            candidate = divider_candidate_by_id.get(source_divider_id)
            decision = divider_decision_by_id.get(source_divider_id)
            if (
                candidate is None
                or decision.get("classification") != "semantic-divider"
                or decision.get("traversal") != "open-passage"
            ):
                raise ValueError(
                    f"{binding.get('id')}: sourceDividerId must name one accepted "
                    "open-passage semantic divider candidate"
                )
            endpoint_room_ids = {
                binding.get("fromRoomId"),
                binding.get("toRoomId"),
            }
            endpoint_label_ids = {
                seed_label_by_room.get(room_id) for room_id in endpoint_room_ids
            }
            if (
                "exterior" in endpoint_room_ids
                or None in endpoint_label_ids
                or endpoint_label_ids != set(candidate.get("sourceLabelIds", []))
            ):
                raise ValueError(
                    f"{binding.get('id')}: semantic divider endpoints must be the "
                    "two rooms bound to its source labels"
                )
            bound["kind"] = "open-passage"
            bound["segment"] = deepcopy(candidate["segment"])
            bound["sourceDividerIds"] = [source_divider_id]
            connected_divider_ids.append(source_divider_id)
        bound_connections.append(bound)

    bound_windows = []
    for binding in clean.get("windows", []):
        source_id = binding.get("sourceOpeningId")
        candidate = candidate_by_id.get(source_id)
        decision = decision_by_id.get(source_id)
        if candidate is None or decision.get("classification") != "window":
            raise ValueError(
                f"{binding.get('id')}: sourceOpeningId must name one window candidate"
            )
        bound = deepcopy(binding)
        bound["type"] = "line"
        bound["points"] = deepcopy(candidate["segment"])
        bound["width"] = 5
        bound["sourceTraceIds"] = [source_id]
        bound["openingStyle"] = deepcopy(candidate.get("symbolEvidence", {}))
        bound_windows.append(bound)
        consumed_opening_ids.append(source_id)

    active_opening_ids = {
        candidate_id
        for candidate_id, decision in decision_by_id.items()
        if decision.get("classification") not in {"not-opening", "unresolved"}
    }
    if len(consumed_opening_ids) != len(set(consumed_opening_ids)):
        raise ValueError("one source opening candidate may be consumed only once")
    if set(consumed_opening_ids) != active_opening_ids:
        missing = sorted(active_opening_ids - set(consumed_opening_ids))
        extra = sorted(set(consumed_opening_ids) - active_opening_ids)
        raise ValueError(
            f"opening bindings must consume every and only active source candidate; "
            f"missing={missing}, extra={extra}"
        )
    traversable_divider_ids = {
        candidate_id
        for candidate_id, decision in divider_decision_by_id.items()
        if (
            decision.get("classification") == "semantic-divider"
            and decision.get("traversal") == "open-passage"
        )
    }
    if len(connected_divider_ids) != len(set(connected_divider_ids)):
        raise ValueError(
            "one open-passage semantic divider may compile to only one connection"
        )
    if set(connected_divider_ids) != traversable_divider_ids:
        missing = sorted(traversable_divider_ids - set(connected_divider_ids))
        extra = sorted(set(connected_divider_ids) - traversable_divider_ids)
        raise ValueError(
            "connection bindings must consume every and only traversable semantic "
            f"divider candidate; missing={missing}, extra={extra}"
        )

    clean["connections"] = bound_connections
    clean["windows"] = bound_windows
    connection_by_id = {
        connection.get("id"): connection for connection in bound_connections
    }
    bound_dividers = []
    consumed_divider_ids: list[str] = []
    for divider in compiled.get("semanticDividers", []):
        source_divider_id = divider.get("sourceDividerId")
        candidate = divider_candidate_by_id.get(source_divider_id)
        decision = divider_decision_by_id.get(source_divider_id)
        if (
            candidate is None
            or decision.get("classification") != "semantic-divider"
        ):
            raise ValueError(
                f"{divider.get('id')}: semantic divider must reference one accepted "
                "sourceDividerId"
            )
        label_room_ids = {
            room_by_seed_label.get(label_id)
            for label_id in candidate.get("sourceLabelIds", [])
        }
        if None in label_room_ids or len(label_room_ids) != 2:
            raise ValueError(
                f"{divider.get('id')}: source divider labels must bind exactly "
                "two authored spaces"
            )
        traversal = decision["traversal"]
        connection_id = divider.get("connectionId")
        connection = connection_by_id.get(connection_id) if connection_id else None
        if traversal == "open-passage":
            if (
                connection is None
                or connection.get("kind") != "open-passage"
                or connection.get("sourceDividerId") != source_divider_id
                or {
                    connection.get("fromRoomId"),
                    connection.get("toRoomId"),
                }
                != label_room_ids
            ):
                raise ValueError(
                    f"{divider.get('id')}: open-passage divider must reference its "
                    "same-source connection between the two source-labelled spaces"
                )
        elif connection_id is not None:
            raise ValueError(
                f"{divider.get('id')}: boundary-only divider must not reference "
                "a traversable connection"
            )
        bound = deepcopy(divider)
        bound["traversal"] = traversal
        bound["roomIds"] = sorted(label_room_ids)
        bound["segment"] = deepcopy(candidate["segment"])
        bound_dividers.append(bound)
        consumed_divider_ids.append(source_divider_id)
    active_divider_ids = {
        candidate_id
        for candidate_id, decision in divider_decision_by_id.items()
        if decision.get("classification") == "semantic-divider"
    }
    if len(consumed_divider_ids) != len(set(consumed_divider_ids)):
        raise ValueError("one semantic divider candidate may be consumed only once")
    if set(consumed_divider_ids) != active_divider_ids:
        missing = sorted(active_divider_ids - set(consumed_divider_ids))
        extra = sorted(set(consumed_divider_ids) - active_divider_ids)
        raise ValueError(
            "semanticDividers must consume every and only accepted source divider; "
            f"missing={missing}, extra={extra}"
        )
    compiled["semanticDividers"] = bound_dividers
    layers = compiled.setdefault("layers", {})
    layers["doors"] = [
        {
            "id": connection["sourceOpeningId"],
            "type": "line",
            "points": deepcopy(connection["segment"]),
            "width": 2,
        }
        for connection in bound_connections
        if (
            connection["kind"] in TRAVERSABLE_CONNECTION_KINDS
            and connection.get("sourceOpeningId")
        )
    ]
    layers["windows"] = [
        {
            "id": window["sourceOpeningId"],
            "type": "line",
            "points": deepcopy(window["points"]),
            "width": 5,
        }
        for window in bound_windows
    ]
    return compiled


def polygon_mask(shape: tuple[int, int], points: list[list[float]]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    pts = np.rint(np.asarray(points, dtype=float)).astype(np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def valid_segment(segment: object) -> bool:
    return (
        isinstance(segment, list)
        and len(segment) == 2
        and all(
            isinstance(point, list)
            and len(point) == 2
            and all(isinstance(axis, (int, float)) for axis in point)
            for point in segment
        )
        and segment[0] != segment[1]
    )


def draw_segment(mask: np.ndarray, segment: list[list[float]], width: int = 5) -> None:
    points = np.rint(np.asarray(segment, dtype=float)).astype(np.int32)
    cv2.line(mask, tuple(points[0]), tuple(points[1]), 255, width)


def physical_opening_closure(
    shape: tuple[int, int],
    segment: list[list[float]],
    walls: list[dict],
) -> tuple[np.ndarray | None, dict | None]:
    """Bridge an opening across its source wall band, including off-center traces."""
    start, end = np.asarray(segment, dtype=float)
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length <= 0:
        return None, None
    tangent = direction / length
    normal = np.asarray([-tangent[1], tangent[0]])
    spans: list[tuple[float, float]] = []
    anchor_ids: list[str] = []
    thicknesses: list[float] = []
    for wall in walls:
        points = wall.get("points", [])
        if len(points) != 4:
            continue
        polygon = np.asarray(points, dtype=float)
        center_start = (polygon[0] + polygon[3]) / 2
        center_end = (polygon[1] + polygon[2]) / 2
        wall_axis = center_end - center_start
        wall_length = float(np.linalg.norm(wall_axis))
        if wall_length <= 0 or abs(float(np.dot(wall_axis / wall_length, tangent))) < 0.9:
            continue
        thickness = (
            float(np.linalg.norm(polygon[0] - polygon[3]))
            + float(np.linalg.norm(polygon[1] - polygon[2]))
        ) / 2
        contour = polygon.astype(np.float32).reshape((-1, 1, 2))
        endpoint_distance = min(
            abs(float(cv2.pointPolygonTest(contour, tuple(start), True))),
            abs(float(cv2.pointPolygonTest(contour, tuple(end), True))),
        )
        if endpoint_distance > max(4.0, thickness * 0.75):
            continue
        offsets = (polygon - start) @ normal
        spans.append((float(offsets.min()), float(offsets.max())))
        anchor_ids.append(str(wall.get("id")))
        thicknesses.append(thickness)
    if not spans:
        return None, None

    minimum = min(span[0] for span in spans)
    maximum = max(span[1] for span in spans)
    extended_start = start - tangent * 2.0
    extended_end = end + tangent * 2.0
    polygon = np.asarray(
        [
            extended_start + normal * minimum,
            extended_end + normal * minimum,
            extended_end + normal * maximum,
            extended_start + normal * maximum,
        ],
        dtype=float,
    )
    mask = polygon_mask(shape, polygon.tolist())
    return mask, {
        "minimumNormalOffsetPx": round(minimum, 3),
        "maximumNormalOffsetPx": round(maximum, 3),
        "sourceWallBandThicknessPx": round(max(thicknesses), 3),
        "anchorWallIds": sorted(set(anchor_ids)),
    }


def draw_semantic_divider(
    mask: np.ndarray,
    segment: list[list[float]],
) -> None:
    """Extend a non-physical divider into its already validated wall anchors."""
    start, end = np.asarray(segment, dtype=float)
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length <= 0:
        return
    tangent = direction / length
    points = np.rint(
        np.asarray([start - tangent * 4.0, end + tangent * 4.0])
    ).astype(np.int32)
    cv2.line(mask, tuple(points[0]), tuple(points[1]), 255, 3)


def border_connected_mask(traversable: np.ndarray) -> np.ndarray:
    count, labels = cv2.connectedComponents(traversable.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros(traversable.shape, dtype=np.uint8)
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border_labels.discard(0)
    return np.isin(labels, list(border_labels)).astype(np.uint8)


def contour_polygon(
    mask: np.ndarray,
    label: str,
    errors: list[str],
    *,
    allow_internal_wall_holes: bool = False,
) -> list[list[int]]:
    contours, hierarchy = cv2.findContours(
        (mask > 0).astype(np.uint8),
        cv2.RETR_CCOMP,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    if hierarchy is None:
        errors.append(f"{label}: no polygon could be compiled")
        return []
    outer = [
        contour
        for contour, row in zip(contours, hierarchy[0])
        if row[3] == -1 and cv2.contourArea(contour) >= 4
    ]
    holes = [
        contour
        for contour, row in zip(contours, hierarchy[0])
        if row[3] != -1 and cv2.contourArea(contour) >= 4
    ]
    if len(outer) != 1:
        errors.append(f"{label}: expected one connected polygon, found {len(outer)}")
        return []
    if holes and not allow_internal_wall_holes:
        errors.append(f"{label}: room polygon contains unsupported holes")
    approximated = cv2.approxPolyDP(
        outer[0],
        CONTOUR_APPROXIMATION_EPSILON_PX,
        True,
    )
    points = [[int(point[0][0]), int(point[0][1])] for point in approximated]
    if len(points) < 3:
        errors.append(f"{label}: compiled polygon has fewer than three points")
        return []
    return points


def share_container_boundary_vertices(
    polygon: list[list[float]],
    container: list[list[float]],
    label: str,
    errors: list[str],
) -> list[list[float]]:
    """Make simplified subset polygons share exact vertices with their container."""
    if len(polygon) < 3 or len(container) < 3:
        return polygon

    shared = [list(map(float, point)) for point in polygon]
    for point_index, point in enumerate(shared):
        contour = np.asarray(container, dtype=np.float32).reshape((-1, 1, 2))
        if cv2.pointPolygonTest(contour, tuple(point), True) >= -1e-6:
            continue

        candidates = []
        for edge_index, start in enumerate(container):
            end = container[(edge_index + 1) % len(container)]
            projection, distance = project_point_to_segment(point, start, end)
            candidates.append((distance, edge_index, projection))
        distance, edge_index, projection = min(candidates, key=lambda row: row[0])
        if distance > MAX_SHARED_BOUNDARY_SNAP_PX + 1e-6:
            errors.append(
                f"{label}: simplified polygon leaves floorBoundary by "
                f"{distance:.3f}px"
            )
            continue

        start = container[edge_index]
        end = container[(edge_index + 1) % len(container)]
        if np.linalg.norm(np.asarray(projection) - np.asarray(start)) <= 1e-6:
            boundary_point = list(map(float, start))
        elif np.linalg.norm(np.asarray(projection) - np.asarray(end)) <= 1e-6:
            boundary_point = list(map(float, end))
        else:
            boundary_point = [round(float(axis), 6) for axis in projection]
            container.insert(edge_index + 1, boundary_point)
        shared[point_index] = boundary_point

    return [
        [int(axis) if float(axis).is_integer() else axis for axis in point]
        for point in shared
    ]


def dominant_side_label(
    assignment: np.ndarray,
    exterior_mask: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    normal: np.ndarray,
    offsets: tuple[float, ...] = (3, 5, 7, 10, 14),
) -> int | str | None:
    votes: list[int | str] = []
    height, width = assignment.shape
    for offset in offsets:
        for ratio in (0.18, 0.36, 0.5, 0.64, 0.82):
            point = start + (end - start) * ratio + normal * offset
            x, y = int(round(point[0])), int(round(point[1]))
            if x < 0 or y < 0 or x >= width or y >= height:
                votes.append("exterior")
                continue
            value = int(assignment[y, x])
            if value > 0:
                votes.append(value)
            elif exterior_mask[y, x] > 0:
                votes.append("exterior")
    if not votes:
        return None
    return max(set(votes), key=votes.count)


def labels_on_side(
    assignment: np.ndarray,
    exterior_mask: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    normal: np.ndarray,
) -> set[int | str]:
    labels: set[int | str] = set()
    height, width = assignment.shape
    for offset in (3, 5, 7, 10, 14):
        for ratio in (0.08, 0.18, 0.3, 0.42, 0.5, 0.58, 0.7, 0.82, 0.92):
            point = start + (end - start) * ratio + normal * offset
            x, y = int(round(point[0])), int(round(point[1]))
            if x < 0 or y < 0 or x >= width or y >= height:
                labels.add("exterior")
                continue
            value = int(assignment[y, x])
            if value > 0:
                labels.add(value)
            elif exterior_mask[y, x] > 0:
                labels.add("exterior")
    return labels


def wall_side_labels(
    wall: dict,
    assignment: np.ndarray,
    exterior_mask: np.ndarray,
) -> tuple[int | str | None, int | str | None]:
    points = np.asarray(wall.get("points", []), dtype=float)
    if points.shape != (4, 2):
        return None, None
    center = points.mean(axis=0)
    faces = ((points[0], points[1]), (points[3], points[2]))
    labels: list[int | str | None] = []
    for start, end in faces:
        midpoint = (start + end) / 2
        outward = midpoint - center
        length = float(np.linalg.norm(outward))
        if length <= 0:
            labels.append(None)
            continue
        labels.append(dominant_side_label(
            assignment,
            exterior_mask,
            start,
            end,
            outward / length,
        ))
    return labels[0], labels[1]


def wall_side_label_sets(
    wall: dict,
    assignment: np.ndarray,
    exterior_mask: np.ndarray,
) -> tuple[set[int | str], set[int | str]]:
    points = np.asarray(wall.get("points", []), dtype=float)
    if points.shape != (4, 2):
        return set(), set()
    center = points.mean(axis=0)
    labels = []
    for start, end in ((points[0], points[1]), (points[3], points[2])):
        midpoint = (start + end) / 2
        outward = midpoint - center
        length = float(np.linalg.norm(outward))
        labels.append(
            labels_on_side(assignment, exterior_mask, start, end, outward / length)
            if length > 0 else set()
        )
    return labels[0], labels[1]


def segment_side_labels(
    segment: list[list[float]],
    assignment: np.ndarray,
    exterior_mask: np.ndarray,
    closure_metrics: dict | None = None,
) -> tuple[int | str | None, int | str | None]:
    start, end = np.asarray(segment, dtype=float)
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length <= 0:
        return None, None
    normal = np.asarray([-direction[1], direction[0]]) / length
    positive_offsets = (3, 5, 7, 10, 14)
    negative_offsets = positive_offsets
    if closure_metrics is not None:
        maximum = float(closure_metrics["maximumNormalOffsetPx"])
        minimum = float(closure_metrics["minimumNormalOffsetPx"])
        positive_offsets = tuple(maximum + delta for delta in (2, 4, 7, 10))
        negative_offsets = tuple(-minimum + delta for delta in (2, 4, 7, 10))
    return (
        dominant_side_label(
            assignment,
            exterior_mask,
            start,
            end,
            normal,
            positive_offsets,
        ),
        dominant_side_label(
            assignment,
            exterior_mask,
            start,
            end,
            -normal,
            negative_offsets,
        ),
    )


def compile_space_topology(
    trace_spec: dict,
    shape: tuple[int, int],
    wall_geometry: dict | None = None,
    source_evidence: dict | None = None,
    semantic_decisions: dict | None = None,
) -> dict:
    """Return the deterministically compiled trace spec and its pixel assignment."""
    errors: list[str] = []
    height, width = shape
    if wall_geometry is not None:
        trace_spec = bind_wall_geometry(trace_spec, wall_geometry)
    if (source_evidence is None) != (semantic_decisions is None):
        raise ValueError(
            "source evidence and semantic decisions must be provided together"
        )
    if source_evidence is not None and semantic_decisions is not None:
        trace_spec = bind_source_openings(
            trace_spec,
            source_evidence,
            semantic_decisions,
        )
    walls = trace_spec.get("cleanStructure", {}).get("walls", [])
    connections = trace_spec.get("cleanStructure", {}).get("connections", [])
    semantic_dividers = trace_spec.get("semanticDividers", [])
    seeds = trace_spec.get("spaceSeeds", [])
    seed_ids = [seed.get("id") for seed in seeds if isinstance(seed, dict)]
    if not seeds:
        errors.append("trace-spec requires one independent space seed per actual space")
    if len(seed_ids) != len(seeds) or None in seed_ids or len(seed_ids) != len(set(seed_ids)):
        errors.append("space seeds need unique non-empty IDs")

    for seed in seeds:
        space_type = seed.get("spaceType")
        if space_type not in SPACE_TYPES:
            errors.append(f"{seed.get('id')}: unsupported spaceType")
        if seed.get("topologyClass") not in TOPOLOGY_CLASSES:
            errors.append(f"{seed.get('id')}: unsupported topologyClass")
        if space_type in ENCLOSED_SPACE_TYPES and seed.get("topologyClass") != "enclosed":
            errors.append(
                f"{seed.get('id')}: {space_type} must use enclosed topologyClass"
            )
        point = seed.get("point")
        if (
            not isinstance(point, list)
            or len(point) != 2
            or not all(isinstance(axis, (int, float)) for axis in point)
        ):
            errors.append(f"{seed.get('id')}: seed needs one source-pixel point")

    wall_mask = np.zeros(shape, dtype=np.uint8)
    for wall in walls:
        points = wall.get("points", [])
        if len(points) != 4:
            errors.append(f"{wall.get('id')}: clean wall must be a four-point wall band")
            continue
        wall_mask = cv2.bitwise_or(wall_mask, polygon_mask(shape, points))

    physical_closures: dict[str, np.ndarray] = {}
    physical_closure_metrics: dict[str, dict] = {}
    for connection in connections:
        segment = connection.get("segment")
        if (
            connection.get("kind") not in TRAVERSABLE_CONNECTION_KINDS
            or connection.get("sourceDividerId")
            or not valid_segment(segment)
        ):
            continue
        closure, closure_metrics = physical_opening_closure(shape, segment, walls)
        connection_id = str(connection.get("id"))
        if closure is None or closure_metrics is None:
            errors.append(
                f"{connection_id}: physical opening is not anchored to a parallel "
                "source wall band"
            )
            continue
        physical_closures[connection_id] = closure
        physical_closure_metrics[connection_id] = closure_metrics

    floor_barrier = wall_mask.copy()
    for connection in connections:
        if (
            connection.get("kind") in TRAVERSABLE_CONNECTION_KINDS
            and "exterior" in {connection.get("fromRoomId"), connection.get("toRoomId")}
        ):
            closure = physical_closures.get(str(connection.get("id")))
            if closure is not None:
                floor_barrier = cv2.bitwise_or(floor_barrier, closure)
    exterior = border_connected_mask((floor_barrier == 0).astype(np.uint8))
    interior = ((floor_barrier == 0) & (exterior == 0)).astype(np.uint8)
    if not int(interior.sum()):
        errors.append("walls and evidenced exterior openings do not enclose a usable interior")

    room_barrier = wall_mask.copy()
    for connection in connections:
        closure = physical_closures.get(str(connection.get("id")))
        if closure is not None:
            room_barrier = cv2.bitwise_or(room_barrier, closure)
    for divider in semantic_dividers:
        segment = divider.get("segment")
        if divider.get("kind") != "open-zone-boundary":
            errors.append(f"{divider.get('id')}: semantic divider kind must be open-zone-boundary")
            continue
        if not valid_segment(segment):
            errors.append(f"{divider.get('id')}: semantic divider needs one non-zero segment")
            continue
        if not divider.get("reason"):
            errors.append(f"{divider.get('id')}: semantic divider needs a source-plan reason")
        traversal = divider.get("traversal")
        if traversal not in DIVIDER_TRAVERSAL_TYPES:
            errors.append(
                f"{divider.get('id')}: semantic divider needs a compiled traversal type"
            )
        connection_id = divider.get("connectionId")
        connection = (
            next(
                (item for item in connections if item.get("id") == connection_id),
                None,
            )
            if connection_id
            else None
        )
        if traversal == "open-passage" and (
            connection is None
            or connection.get("kind") != "open-passage"
            or connection.get("segment") != segment
        ):
            errors.append(
                f"{divider.get('id')}: traversable boundary must share its "
                "open-passage connection"
            )
        if traversal == "boundary-only" and connection_id is not None:
            errors.append(
                f"{divider.get('id')}: boundary-only divider must not be traversable"
            )
        draw_semantic_divider(room_barrier, segment)

    room_walkable = ((interior > 0) & (room_barrier == 0)).astype(np.uint8)
    component_count, components = cv2.connectedComponents(room_walkable, connectivity=8)
    component_areas = {
        label: int((components == label).sum())
        for label in range(1, component_count)
    }
    seed_component: dict[str, int] = {}
    component_seeds: dict[int, list[str]] = {}
    source_label_by_id = {
        item.get("id"): item
        for item in (
            source_evidence.get("spaceLabelCandidates", [])
            if source_evidence is not None
            else []
        )
    }
    for seed in seeds:
        point = seed.get("point")
        if not isinstance(point, list) or len(point) != 2:
            continue
        x, y = int(round(point[0])), int(round(point[1]))
        if x < 0 or y < 0 or x >= width or y >= height:
            errors.append(f"{seed.get('id')}: seed lies outside the source image")
            continue
        label = int(components[y, x])
        if label <= 0:
            errors.append(f"{seed.get('id')}: seed lies on a wall, opening closure or exterior")
            continue
        seed_component[seed["id"]] = label
        component_seeds.setdefault(label, []).append(seed["id"])
        if source_evidence is not None:
            source_label = source_label_by_id.get(seed.get("sourceLabelId"))
            source_label_point = (
                source_label.get("point") if isinstance(source_label, dict) else None
            )
            if (
                not isinstance(source_label_point, list)
                or len(source_label_point) != 2
            ):
                errors.append(
                    f"{seed.get('id')}: sourceLabelId does not resolve to one "
                    "source-pixel room-label anchor"
                )
                continue
            label_x = int(round(source_label_point[0]))
            label_y = int(round(source_label_point[1]))
            if (
                label_x < 0
                or label_y < 0
                or label_x >= width
                or label_y >= height
            ):
                errors.append(
                    f"{seed.get('id')}: source room-label anchor lies outside the image"
                )
                continue
            source_label_component = int(components[label_y, label_x])
            if source_label_component <= 0:
                errors.append(
                    f"{seed.get('id')}: immutable source room-label anchor lies on "
                    "a wall, opening closure or exterior"
                )
            elif source_label_component != label:
                errors.append(
                    f"{seed.get('id')}: topology seed and immutable source room-label "
                    "anchor lie in different compiled regions; repair the source "
                    "boundary instead of moving the label"
                )
    merged_seed_groups = [
        room_ids for room_ids in component_seeds.values() if len(room_ids) > 1
    ]
    for room_ids in merged_seed_groups:
        errors.append(
            "missing wall or semantic boundary merges independent spaces: "
            + ", ".join(sorted(room_ids))
        )
    unassigned_components = [
        label for label in component_areas if label not in component_seeds
    ]
    for label in unassigned_components:
        errors.append(
            f"usable region {label} ({component_areas[label]}px) has no space seed"
        )

    assignment = np.zeros(shape, dtype=np.int32)
    seed_order = {seed["id"]: index + 1 for index, seed in enumerate(seeds) if seed.get("id")}
    for seed_id, component_label in seed_component.items():
        if len(component_seeds.get(component_label, [])) == 1:
            assignment[components == component_label] = seed_order[seed_id]
    unassigned_floor = (interior > 0) & (assignment == 0)
    valid_seed_ids = [
        seed_id
        for seed_id, component_label in seed_component.items()
        if len(component_seeds.get(component_label, [])) == 1
    ]
    if valid_seed_ids and np.any(unassigned_floor):
        distances = []
        for seed_id in valid_seed_ids:
            source_mask = (assignment != seed_order[seed_id]).astype(np.uint8)
            distances.append(cv2.distanceTransform(source_mask, cv2.DIST_L2, 5))
        nearest = np.argmin(np.stack(distances), axis=0)
        for index, seed_id in enumerate(valid_seed_ids):
            assignment[unassigned_floor & (nearest == index)] = seed_order[seed_id]

    bounds = trace_spec.get("planBounds", [])
    known_size = trace_spec.get("knownSizeMm", {})
    if (
        len(bounds) != 4
        or float(bounds[2]) <= float(bounds[0])
        or float(bounds[3]) <= float(bounds[1])
        or not known_size.get("width")
        or not known_size.get("depth")
    ):
        errors.append("trace-spec needs valid planBounds and knownSizeMm")
        pixel_area_m2 = 0
    else:
        pixel_area_m2 = (
            float(known_size["width"]) / 1000 / (float(bounds[2]) - float(bounds[0]))
            * float(known_size["depth"]) / 1000 / (float(bounds[3]) - float(bounds[1]))
        )

    floor_boundary = (
        contour_polygon(
            interior,
            "floorBoundary",
            errors,
            allow_internal_wall_holes=True,
        )
        if interior.any()
        else []
    )

    compiled_spaces = []
    for seed in seeds:
        seed_id = seed.get("id")
        ordinal = seed_order.get(seed_id)
        room_mask = (assignment == ordinal).astype(np.uint8) if ordinal else np.zeros(shape, np.uint8)
        polygon = contour_polygon(room_mask, seed_id or "unknown-space", errors) if room_mask.any() else []
        polygon = share_container_boundary_vertices(
            polygon,
            floor_boundary,
            seed_id or "unknown-space",
            errors,
        )
        compiled_spaces.append({
            "id": seed_id,
            "name": seed.get("name"),
            "spaceType": seed.get("spaceType"),
            "topologyClass": seed.get("topologyClass"),
            "polygon": polygon,
            "labelPosition": seed.get("point"),
            "areaPixels": int(room_mask.sum()),
            "areaM2": round(float(room_mask.sum()) * pixel_area_m2, 3),
        })

    ordinal_to_room = {ordinal: room_id for room_id, ordinal in seed_order.items()}
    wall_adjacency: dict[str, list[str]] = {}
    wall_sides: dict[str, list[list[str]]] = {}
    orphan_wall_ids: list[str] = []
    for wall in walls:
        left, right = wall_side_labels(wall, assignment, exterior)
        dominant = [
            ordinal_to_room.get(value, value)
            for value in (left, right)
            if value is not None
        ]
        side_a, side_b = wall_side_label_sets(wall, assignment, exterior)
        resolved_sides = [
            sorted(
                {str(ordinal_to_room.get(value, value)) for value in side},
            )
            for side in (side_a, side_b)
        ]
        resolved = sorted(set(resolved_sides[0]) | set(resolved_sides[1]))
        wall_adjacency[wall.get("id")] = resolved
        wall_sides[wall.get("id")] = resolved_sides
        if len(dominant) != 2:
            errors.append(f"{wall.get('id')}: wall does not have two resolvable sides")
        elif dominant[0] == dominant[1]:
            orphan_wall_ids.append(wall.get("id"))
            errors.append(
                f"{wall.get('id')}: wall lies inside one space ({dominant[0]}); "
                "reclassify carpet, cabinet or furniture edges instead of building a wall"
            )

    opening_endpoint_mismatches: list[str] = []
    connection_endpoint_audit: list[dict] = []
    for connection in connections:
        connection_id = connection.get("id")
        left = connection.get("fromRoomId")
        right = connection.get("toRoomId")
        if left == right or left not in set(seed_ids) | {"exterior"} or right not in set(seed_ids) | {"exterior"}:
            errors.append(f"{connection_id}: connection endpoints must name two different spaces")
            opening_endpoint_mismatches.append(connection_id)
            continue
        if connection.get("kind") not in ALL_CONNECTION_KINDS:
            errors.append(f"{connection_id}: unsupported connection kind")
        segment = connection.get("segment")
        if not valid_segment(segment):
            errors.append(f"{connection_id}: connection needs one non-zero segment")
            opening_endpoint_mismatches.append(connection_id)
            continue
        side_a, side_b = segment_side_labels(
            segment,
            assignment,
            exterior,
            physical_closure_metrics.get(str(connection_id)),
        )
        resolved_side_a = ordinal_to_room.get(side_a, side_a) if side_a is not None else None
        resolved_side_b = ordinal_to_room.get(side_b, side_b) if side_b is not None else None
        actual = {
            value for value in (resolved_side_a, resolved_side_b) if value is not None
        }
        expected = {left, right}
        endpoint_row = {
            "connectionId": connection_id,
            "sourceSegment": deepcopy(segment),
            "derivedSideA": resolved_side_a,
            "derivedSideB": resolved_side_b,
            "derivedEndpointIds": sorted(map(str, actual)),
            "declaredEndpointIds": sorted(map(str, expected)),
            "passed": actual == expected and len(actual) == 2,
            "method": "closed-opening-side-sampling-from-compiled-pixel-assignment",
        }
        connection_endpoint_audit.append(endpoint_row)
        if actual != expected:
            errors.append(
                f"{connection_id}: opening separates {sorted(map(str, actual))}, "
                f"not declared {sorted(map(str, expected))}"
            )
            opening_endpoint_mismatches.append(connection_id)

    room_access_ids: dict[str, set[str]] = {
        seed_id: set() for seed_id in seed_ids if seed_id
    }
    room_access_kinds: dict[str, list[str]] = {
        seed_id: [] for seed_id in seed_ids if seed_id
    }
    for connection in connections:
        if connection.get("kind") not in TRAVERSABLE_CONNECTION_KINDS:
            continue
        for endpoint in (
            connection.get("fromRoomId"),
            connection.get("toRoomId"),
        ):
            if endpoint in room_access_ids:
                room_access_ids[endpoint].add(connection.get("id"))
                room_access_kinds[endpoint].append(connection.get("kind"))
    enclosed_extra_access_ids: list[str] = []
    for seed in seeds:
        seed_id = seed.get("id")
        access_ids = room_access_ids.get(seed_id, set())
        if not access_ids:
            errors.append(
                f"{seed_id}: {seed.get('topologyClass')} space has no traversable connection"
            )
        if (
            seed.get("topologyClass") == "enclosed"
            and not ENCLOSED_ACCESS_KINDS.intersection(
                room_access_kinds.get(seed_id, [])
            )
        ):
            errors.append(
                f"{seed_id}: enclosed space needs an evidenced door or "
                "sliding-door access"
            )
        if seed.get("topologyClass") == "enclosed" and len(access_ids) > 1:
            enclosed_extra_access_ids.append(seed_id)

    compiled = deepcopy(trace_spec)
    compiled["floorBoundary"] = floor_boundary
    compiled["spaces"] = compiled_spaces
    compiled["compiledTopology"] = {
        "method": "wall-mask-opening-closure-space-seed",
        "interiorPixels": int(interior.sum()),
        "assignedInteriorPixels": int(((interior > 0) & (assignment > 0)).sum()),
        "spaceSeedCount": len(seeds),
        "roomCount": len(compiled_spaces),
        "semanticDividerCount": len(semantic_dividers),
        "traversableSemanticDividerCount": sum(
            divider.get("traversal") == "open-passage"
            for divider in semantic_dividers
        ),
        "boundaryOnlySemanticDividerCount": sum(
            divider.get("traversal") == "boundary-only"
            for divider in semantic_dividers
        ),
        "mergedSeedGroups": merged_seed_groups,
        "unassignedRegionCount": len(unassigned_components),
        "orphanWallIds": orphan_wall_ids,
        "openingEndpointMismatches": opening_endpoint_mismatches,
        "connectionEndpointAudit": connection_endpoint_audit,
        "physicalOpeningClosures": physical_closure_metrics,
        "roomAccessConnectionIds": {
            room_id: sorted(connection_ids)
            for room_id, connection_ids in room_access_ids.items()
        },
        "enclosedRoomsWithExtraAccess": sorted(enclosed_extra_access_ids),
        "wallAdjacency": wall_adjacency,
        "wallSides": wall_sides,
    }
    return {
        "traceSpec": compiled,
        "errors": errors,
        "interior": interior,
        "assignment": assignment,
        "metrics": compiled["compiledTopology"],
    }
