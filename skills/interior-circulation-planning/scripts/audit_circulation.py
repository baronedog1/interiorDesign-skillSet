#!/usr/bin/env python3
"""Compare structural circulation capacity with the current furniture layout."""

from __future__ import annotations

import argparse
import heapq
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from common import (
    ArtifactDiscoveryError,
    Point,
    bbox_intersects,
    canonical_sha256,
    discover_semantic_list,
    downsample_path,
    normalize_polygon,
    path_bounds,
    point_in_polygon,
    point_polygon_edge_distance,
    point_segment_distance,
    polygon_bounds,
    polygon_centroid,
    read_json,
    require_schema,
    sha256_file,
    write_json,
)


STRUCTURE_SCHEMA = "interior.floorplan-structure.v3"
SCENE_SCHEMA = "interior.circulation-scene.v2"
POLICY_SCHEMA = "interior.circulation-policy.v2"
AUDIT_SCHEMA = "interior.circulation-audit.v2"

LOCAL_AXES = {
    "+X": (1.0, 0.0),
    "-X": (-1.0, 0.0),
    "+Z": (0.0, 1.0),
    "-Z": (0.0, -1.0),
}


@dataclass(frozen=True)
class Grid:
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    resolution: float
    columns: int
    rows: int

    @classmethod
    def from_polygon(cls, polygon: list[Point], resolution: float, max_cells: int) -> "Grid":
        min_x, min_y, max_x, max_y = polygon_bounds(polygon)
        padding = resolution * 2
        min_x -= padding
        min_y -= padding
        max_x += padding
        max_y += padding
        columns = max(1, math.ceil((max_x - min_x) / resolution))
        rows = max(1, math.ceil((max_y - min_y) / resolution))
        if columns * rows > max_cells:
            raise ValueError(
                f"circulation grid would contain {columns * rows} cells, above policy maximum {max_cells}"
            )
        return cls(min_x, min_y, max_x, max_y, resolution, columns, rows)

    @property
    def size(self) -> int:
        return self.columns * self.rows

    def index(self, column: int, row: int) -> int:
        return row * self.columns + column

    def coordinates(self, index: int) -> tuple[int, int]:
        return (index % self.columns, index // self.columns)

    def center(self, index: int) -> Point:
        column, row = self.coordinates(index)
        return (
            self.min_x + (column + 0.5) * self.resolution,
            self.min_y + (row + 0.5) * self.resolution,
        )

    def point_to_index(self, point: Point) -> int | None:
        column = math.floor((point[0] - self.min_x) / self.resolution)
        row = math.floor((point[1] - self.min_y) / self.resolution)
        if column < 0 or row < 0 or column >= self.columns or row >= self.rows:
            return None
        return self.index(column, row)

    def neighbors(self, index: int) -> Iterable[tuple[int, float]]:
        column, row = self.coordinates(index)
        for delta_x, delta_y, weight in (
            (-1, 0, 1.0),
            (1, 0, 1.0),
            (0, -1, 1.0),
            (0, 1, 1.0),
            (-1, -1, math.sqrt(2)),
            (1, -1, math.sqrt(2)),
            (-1, 1, math.sqrt(2)),
            (1, 1, math.sqrt(2)),
        ):
            next_column = column + delta_x
            next_row = row + delta_y
            if 0 <= next_column < self.columns and 0 <= next_row < self.rows:
                yield self.index(next_column, next_row), weight * self.resolution

    def path_neighbors(self, index: int, free: list[bool]) -> Iterable[int]:
        """Yield free neighbors without allowing diagonal corner cutting."""
        column, row = self.coordinates(index)
        for neighbor, _ in self.neighbors(index):
            if not free[neighbor]:
                continue
            next_column, next_row = self.coordinates(neighbor)
            delta_x = next_column - column
            delta_y = next_row - row
            if delta_x and delta_y:
                horizontal = self.index(column + delta_x, row)
                vertical = self.index(column, row + delta_y)
                if not free[horizontal] or not free[vertical]:
                    continue
            yield neighbor


def projection_parameter(point: Point, start: Point, end: Point) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1e-12:
        return 0.0
    return ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denominator


def nearest_point_on_segment(point: Point, start: Point, end: Point) -> Point:
    parameter = max(0.0, min(1.0, projection_parameter(point, start, end)))
    return (
        start[0] + (end[0] - start[0]) * parameter,
        start[1] + (end[1] - start[1]) * parameter,
    )


def normalize_vector(vector: Point) -> Point:
    length = math.hypot(*vector)
    if length <= 1e-9:
        raise ValueError("cannot normalize zero-length layout direction")
    return vector[0] / length, vector[1] / length


def world_axis(component: dict[str, Any], role: str) -> Point | None:
    local = LOCAL_AXES.get(component.get("localAxes", {}).get(role))
    if local is None:
        return None
    angle = float(component.get("activeTransform", {}).get("rotationRadians", 0))
    return (
        local[0] * math.cos(angle) + local[1] * math.sin(angle),
        -local[0] * math.sin(angle) + local[1] * math.cos(angle),
    )


def class_matches(component: dict[str, Any], rule: dict[str, Any], key: str) -> bool:
    functional_class = str(component.get("functionalClass", ""))
    exact = set(rule.get(f"{key}FunctionalClasses", []))
    prefixes = tuple(rule.get(f"{key}ClassPrefixes", []))
    return functional_class in exact or any(functional_class.startswith(prefix) for prefix in prefixes)


def classify_room_probe(
    point: Point,
    rooms: dict[str, dict[str, Any]],
    floor_boundary: list[Point],
) -> str | None:
    room_hits = [
        room_id
        for room_id, room in rooms.items()
        if point_in_polygon(point, normalize_polygon(room["polygon"], f"room {room_id} polygon"))
    ]
    if len(room_hits) == 1:
        return room_hits[0]
    if not room_hits and not point_in_polygon(point, floor_boundary):
        return "exterior"
    return None


def independently_audit_connection_endpoints(
    structure: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rooms = {room["id"]: room for room in structure.get("rooms", [])}
    floor_boundary = normalize_polygon(structure["floorBoundary"], "floorBoundary")
    depths = [float(value) for value in policy.get("topologyEndpointProbeMeters", [])]
    audits: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    connection_ids = {connection.get("id") for connection in structure.get("connections", [])}

    def valid_compiled_row(row: Any) -> bool:
        return (
            isinstance(row, dict)
            and row.get("connectionId") in connection_ids
            and isinstance(row.get("derivedEndpointIds"), list)
            and isinstance(row.get("passed"), bool)
        )

    compiled_audit, discovery = discover_semantic_list(
        structure,
        "connectionEndpointAudit",
        item_validator=valid_compiled_row,
        preferred_paths=(
            "topology.connectionEndpointAudit",
            "compiledTopology.connectionEndpointAudit",
        ),
    )
    compiled_rows = {row.get("connectionId"): row for row in compiled_audit}
    for connection in structure.get("connections", []):
        start = tuple(map(float, connection.get("start", [])))
        end = tuple(map(float, connection.get("end", [])))
        if len(start) != 2 or len(end) != 2 or math.dist(start, end) <= 1e-9:
            derived = []
            side_labels = [None, None]
        else:
            midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
            tangent = normalize_vector((end[0] - start[0], end[1] - start[1]))
            normal = (-tangent[1], tangent[0])
            side_labels = []
            side_probe_audits = []
            for sign in (1.0, -1.0):
                samples = []
                for depth in depths:
                    point = (
                        midpoint[0] + normal[0] * depth * sign,
                        midpoint[1] + normal[1] * depth * sign,
                    )
                    label = classify_room_probe(point, rooms, floor_boundary)
                    samples.append({"depthMeters": depth, "label": label})
                decisive_samples = [sample for sample in samples if sample["label"] is not None]
                room_labels = sorted({sample["label"] for sample in decisive_samples if sample["label"] in rooms})
                exterior_seen = any(sample["label"] == "exterior" for sample in decisive_samples)
                selected_label = decisive_samples[-1]["label"] if decisive_samples else None
                trailing_count = 0
                for sample in reversed(decisive_samples):
                    if sample["label"] != selected_label:
                        break
                    trailing_count += 1
                ignored_labels = sorted({
                    sample["label"]
                    for sample in decisive_samples[:-trailing_count or None]
                    if sample["label"] is not None and sample["label"] != selected_label
                })
                side_labels.append(selected_label)
                side_probe_audits.append({
                    "selectedLabel": selected_label,
                    "roomLabels": room_labels,
                    "stableTrailingSampleCount": trailing_count,
                    "lowConfidenceSingleDeepSample": bool(selected_label is not None and trailing_count == 1),
                    "ignoredNearOpeningLabels": ignored_labels,
                    "wallBandOrUnassignedSampleCount": sum(sample["label"] is None for sample in samples),
                    "ignoredExteriorNearWall": bool(room_labels and exterior_seen),
                    "samples": samples,
                })
            derived = sorted({value for value in side_labels if value is not None})
        if len(start) != 2 or len(end) != 2 or math.dist(start, end) <= 1e-9:
            side_probe_audits = []
        declared = sorted({connection.get("fromRoomId"), connection.get("toRoomId")})
        compiled = compiled_rows.get(connection.get("id"))
        passed = (
            len(derived) == 2
            and derived == declared
            and isinstance(compiled, dict)
            and compiled.get("passed") is True
            and compiled.get("derivedEndpointIds") == declared
        )
        row = {
            "connectionId": connection.get("id"),
            "derivedSideA": side_labels[0],
            "derivedSideB": side_labels[1],
            "derivedEndpointIds": derived,
            "declaredEndpointIds": declared,
            "compiledPixelAuditPresent": isinstance(compiled, dict),
            "compiledPixelAuditPassed": compiled.get("passed") if isinstance(compiled, dict) else False,
            "sideProbeAudit": side_probe_audits,
            "passed": passed,
            "method": "meter-space-normal-probes-ignore-wall-band-cross-checked-with-semantically-discovered-pixel-audit",
        }
        audits.append(row)
        if not passed:
            findings.append({
                "code": "connection-endpoints-not-independently-proven",
                "responsibility": "input-integrity",
                "severity": "error",
                "connectionId": connection.get("id"),
                "message": "Connection endpoints differ from one or both independent geometry audits.",
            })
    return audits, findings, discovery


def ray_hits_polygon(origin: Point, direction: Point, polygon: list[Point], maximum: float) -> bool:
    if point_in_polygon(origin, polygon):
        return True
    step = 0.02
    distance = step
    while distance <= maximum + 1e-9:
        point = (origin[0] + direction[0] * distance, origin[1] + direction[1] * distance)
        if point_in_polygon(point, polygon):
            return True
        distance += step
    return False


def relation_target(
    source: dict[str, Any],
    candidates: list[dict[str, Any]],
    scene: dict[str, Any],
    axis_role: str,
) -> tuple[dict[str, Any] | None, str | None]:
    hints = [
        hint
        for hint in scene.get("relationHints", {}).get("facing", [])
        if hint.get("sourceId") == source.get("id") and hint.get("axisRole") == axis_role
    ]
    if len(hints) > 1:
        return None, "multiple explicit relation targets"
    if hints:
        target_id = hints[0].get("targetId")
        matches = [candidate for candidate in candidates if candidate.get("id") == target_id]
        return (matches[0], None) if len(matches) == 1 else (None, "explicit target has the wrong class or room")
    if not candidates:
        return None, "no compatible target in the same room"
    source_center = tuple(map(float, source["activeTransform"]["position"]))
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            math.dist(
                source_center,
                tuple(map(float, candidate["activeTransform"]["position"])),
            ),
            str(candidate.get("id", "")),
        ),
    )
    return ranked[0], None


def audit_layout_relationships(
    structure: dict[str, Any],
    scene: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    walls = {wall["id"]: wall for wall in structure.get("walls", [])}
    components = scene.get("components", [])
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def add_finding(code: str, component_id: str, responsibility: str, message: str) -> None:
        findings.append({
            "code": code,
            "responsibility": responsibility,
            "severity": "error",
            "componentId": component_id,
            "message": message,
        })

    for rule_id, rule in policy.get("relationshipRules", {}).items():
        sources = [component for component in components if class_matches(component, rule, "source")]
        for source in sources:
            axis_role = rule["axisRole"]
            axis = world_axis(source, axis_role)
            if axis is None:
                results.append({"ruleId": rule_id, "sourceId": source["id"], "passed": False, "reason": "missing-reviewed-axis"})
                add_finding(
                    "asset-orientation-axis-missing",
                    source["id"],
                    "input-integrity",
                    f"{source['assetId']} lacks reviewed {axis_role} axis evidence.",
                )
                continue
            center = tuple(map(float, source["activeTransform"]["position"]))
            footprint = normalize_polygon(source["footprint"], f"{source['id']} footprint")
            if "maximumGapMeters" in rule:
                support_value = max(point[0] * axis[0] + point[1] * axis[1] for point in footprint)
                support_points = [
                    point for point in footprint
                    if abs(point[0] * axis[0] + point[1] * axis[1] - support_value) <= 0.02
                ]
                hint_rows = [
                    hint for hint in scene.get("relationHints", {}).get("wallAttachment", [])
                    if hint.get("sourceId") == source["id"] and hint.get("axisRole") == axis_role
                ]
                candidate_walls = [walls[hint_rows[0]["wallId"]]] if len(hint_rows) == 1 and hint_rows[0].get("wallId") in walls else list(walls.values())
                measurements = []
                for wall in candidate_walls:
                    start = tuple(map(float, wall["start"]))
                    end = tuple(map(float, wall["end"]))
                    gap = max(0.0, min(point_segment_distance(point, start, end) for point in support_points) - float(wall.get("thickness", 0.2)) / 2)
                    nearest = nearest_point_on_segment(center, start, end)
                    toward_wall = normalize_vector((nearest[0] - center[0], nearest[1] - center[1]))
                    direction_dot = axis[0] * toward_wall[0] + axis[1] * toward_wall[1]
                    measurements.append((gap, -direction_dot, wall["id"], direction_dot))
                if not measurements:
                    results.append({"ruleId": rule_id, "sourceId": source["id"], "passed": False, "reason": "no-real-wall-candidate"})
                    add_finding(
                        "required-wall-candidate-missing",
                        source["id"],
                        "input-integrity",
                        "No real wall geometry exists for the required attachment check.",
                    )
                    continue
                measurements.sort()
                gap, _, wall_id, direction_dot = measurements[0]
                passed = gap <= float(rule["maximumGapMeters"]) + 1e-6 and direction_dot >= 0.8
                results.append({
                    "ruleId": rule_id,
                    "sourceId": source["id"],
                    "wallId": wall_id,
                    "axisRole": axis_role,
                    "gapMeters": round(gap, 4),
                    "directionDot": round(direction_dot, 6),
                    "maximumGapMeters": rule["maximumGapMeters"],
                    "passed": passed,
                })
                if not passed:
                    add_finding(
                        "required-wall-attachment-failed",
                        source["id"],
                        "current-layout",
                        f"{axis_role} is not tight and square to a real wall.",
                    )
                continue

            targets = [
                component
                for component in components
                if component.get("roomId") == source.get("roomId")
                and component.get("id") != source.get("id")
                and class_matches(component, rule, "target")
            ]
            # A sofa only needs a TV-facing relation when a TV console exists in its room.
            if rule_id == "sofaFacesTvConsole" and not targets:
                continue
            target, target_error = relation_target(source, targets, scene, axis_role)
            if target is None:
                results.append({"ruleId": rule_id, "sourceId": source["id"], "passed": False, "reason": target_error})
                add_finding(
                    "required-facing-target-unresolved",
                    source["id"],
                    "current-layout",
                    target_error or "required target is unresolved",
                )
                continue
            target_center = tuple(map(float, target["activeTransform"]["position"]))
            direction = normalize_vector((target_center[0] - center[0], target_center[1] - center[1]))
            dot = axis[0] * direction[0] + axis[1] * direction[1]
            target_polygon = normalize_polygon(target["footprint"], f"{target['id']} footprint")
            ray_pass = (
                not rule.get("rayMustIntersectTargetFootprint")
                or ray_hits_polygon(center, axis, target_polygon, float(rule.get("maximumRayDistanceMeters", 8.0)))
            )
            passed = dot >= float(rule["minimumDot"]) - 1e-6 and ray_pass
            results.append({
                "ruleId": rule_id,
                "sourceId": source["id"],
                "targetId": target["id"],
                "axisRole": axis_role,
                "directionDot": round(dot, 6),
                "minimumDot": rule["minimumDot"],
                "rayIntersectsTargetFootprint": ray_pass,
                "passed": passed,
            })
            if not passed:
                add_finding(
                    "required-facing-relation-failed",
                    source["id"],
                    "current-layout",
                    f"{axis_role} does not face {target['id']} with the required ray and dot product.",
                )
    return results, findings


def in_opening_carve(point: Point, connections: list[dict[str, Any]], depth: float) -> bool:
    for connection in connections:
        start = tuple(map(float, connection.get("start", [])))
        end = tuple(map(float, connection.get("end", [])))
        if len(start) != 2 or len(end) != 2:
            continue
        parameter = projection_parameter(point, start, end)
        if -0.05 <= parameter <= 1.05 and point_segment_distance(point, start, end) <= depth:
            return True
    return False


def build_shell_grid(
    grid: Grid,
    floor_boundary: list[Point],
    walls: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> list[bool]:
    maximum_half_wall = max((float(wall.get("thickness", 0.2)) / 2 for wall in walls), default=0.1)
    carve_depth = maximum_half_wall + grid.resolution * 1.5
    free = [False] * grid.size
    wall_segments = [
        (
            tuple(map(float, wall["start"])),
            tuple(map(float, wall["end"])),
            float(wall.get("thickness", 0.2)) / 2,
        )
        for wall in walls
    ]
    for index in range(grid.size):
        point = grid.center(index)
        if not point_in_polygon(point, floor_boundary):
            continue
        blocked_by_wall = any(point_segment_distance(point, start, end) <= half for start, end, half in wall_segments)
        if blocked_by_wall and not in_opening_carve(point, connections, carve_depth):
            continue
        free[index] = True
    return free


def component_polygons(scene: dict[str, Any], excluded_ids: set[str] | None = None) -> list[tuple[str, list[Point]]]:
    excluded = excluded_ids or set()
    result: list[tuple[str, list[Point]]] = []
    for component in scene.get("components", []):
        if component.get("id") in excluded or component.get("blockingClass") != "floor-obstacle":
            continue
        result.append((component["id"], normalize_polygon(component["footprint"], f"{component['id']} footprint")))
    return result


def apply_layout_obstacles(grid: Grid, shell_free: list[bool], polygons: list[tuple[str, list[Point]]]) -> list[bool]:
    free = shell_free.copy()
    for _, polygon in polygons:
        min_x, min_y, max_x, max_y = polygon_bounds(polygon)
        start_column = max(0, math.floor((min_x - grid.min_x) / grid.resolution) - 1)
        end_column = min(grid.columns - 1, math.ceil((max_x - grid.min_x) / grid.resolution) + 1)
        start_row = max(0, math.floor((min_y - grid.min_y) / grid.resolution) - 1)
        end_row = min(grid.rows - 1, math.ceil((max_y - grid.min_y) / grid.resolution) + 1)
        for row in range(start_row, end_row + 1):
            for column in range(start_column, end_column + 1):
                index = grid.index(column, row)
                if free[index] and point_in_polygon(grid.center(index), polygon):
                    free[index] = False
    return free


def clearance_field(grid: Grid, free: list[bool]) -> list[float]:
    distances = [math.inf] * grid.size
    queue: list[tuple[float, int]] = []
    for index, is_free in enumerate(free):
        if not is_free:
            distances[index] = 0.0
            heapq.heappush(queue, (0.0, index))
    while queue:
        current_distance, index = heapq.heappop(queue)
        if current_distance != distances[index]:
            continue
        for neighbor, step in grid.neighbors(index):
            candidate = current_distance + step
            if candidate + 1e-12 < distances[neighbor]:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return distances


def cells_near_points(grid: Grid, free: list[bool], points: list[Point], radius: float) -> set[int]:
    result: set[int] = set()
    radius_cells = max(1, math.ceil(radius / grid.resolution))
    for point in points:
        base = grid.point_to_index(point)
        if base is None:
            continue
        column, row = grid.coordinates(base)
        for candidate_row in range(max(0, row - radius_cells), min(grid.rows, row + radius_cells + 1)):
            for candidate_column in range(max(0, column - radius_cells), min(grid.columns, column + radius_cells + 1)):
                candidate = grid.index(candidate_column, candidate_row)
                if free[candidate] and math.dist(grid.center(candidate), point) <= radius:
                    result.add(candidate)
    return result


def room_target_cells(grid: Grid, free: list[bool], room: dict[str, Any], interior_depth: float) -> set[int]:
    polygon = normalize_polygon(room["polygon"], f"room {room['id']} polygon")
    min_x, min_y, max_x, max_y = polygon_bounds(polygon)
    candidates: set[int] = set()
    fallback: set[int] = set()
    for row in range(max(0, math.floor((min_y - grid.min_y) / grid.resolution) - 1), min(grid.rows, math.ceil((max_y - grid.min_y) / grid.resolution) + 1)):
        for column in range(max(0, math.floor((min_x - grid.min_x) / grid.resolution) - 1), min(grid.columns, math.ceil((max_x - grid.min_x) / grid.resolution) + 1)):
            index = grid.index(column, row)
            if not free[index]:
                continue
            point = grid.center(index)
            if not point_in_polygon(point, polygon):
                continue
            fallback.add(index)
            if point_polygon_edge_distance(point, polygon) >= interior_depth:
                candidates.add(index)
    return candidates or fallback


def widest_path(
    grid: Grid,
    free: list[bool],
    clearance: list[float],
    starts: set[int],
    targets: set[int],
) -> tuple[float, list[Point]]:
    starts = {index for index in starts if free[index]}
    targets = {index for index in targets if free[index]}
    if not starts or not targets:
        return 0.0, []
    best = [-1.0] * grid.size
    parent: dict[int, int] = {}
    queue: list[tuple[float, int]] = []
    for index in starts:
        best[index] = clearance[index]
        heapq.heappush(queue, (-best[index], index))
    reached: int | None = None
    while queue:
        negative_score, index = heapq.heappop(queue)
        score = -negative_score
        if score + 1e-12 < best[index]:
            continue
        if index in targets:
            reached = index
            break
        for neighbor in grid.path_neighbors(index, free):
            candidate = min(score, clearance[neighbor])
            if candidate > best[neighbor] + 1e-12:
                best[neighbor] = candidate
                parent[neighbor] = index
                heapq.heappush(queue, (-candidate, neighbor))
    if reached is None:
        return 0.0, []
    path_indices = [reached]
    while path_indices[-1] not in starts:
        previous = parent.get(path_indices[-1])
        if previous is None:
            break
        path_indices.append(previous)
    path_indices.reverse()
    return best[reached] * 2.0, [grid.center(index) for index in path_indices]


def connection_sides(connection: dict[str, Any], rooms: dict[str, dict[str, Any]], depth: float) -> dict[str, Point]:
    start = tuple(map(float, connection["start"]))
    end = tuple(map(float, connection["end"]))
    midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    length = math.dist(start, end)
    if length <= 1e-9:
        raise ValueError(f"connection {connection.get('id')} has zero length")
    normal = (-(end[1] - start[1]) / length, (end[0] - start[0]) / length)
    candidates = [
        (midpoint[0] + normal[0] * depth, midpoint[1] + normal[1] * depth),
        (midpoint[0] - normal[0] * depth, midpoint[1] - normal[1] * depth),
    ]
    result: dict[str, Point] = {}
    for room_id in (connection.get("fromRoomId"), connection.get("toRoomId")):
        if room_id == "exterior" or room_id not in rooms:
            continue
        polygon = normalize_polygon(rooms[room_id]["polygon"], f"room {room_id} polygon")
        matching = [point for point in candidates if point_in_polygon(point, polygon)]
        if not matching:
            for factor in (0.75, 0.5, 0.25, 0.1):
                reduced = [
                    (midpoint[0] + normal[0] * depth * factor, midpoint[1] + normal[1] * depth * factor),
                    (midpoint[0] - normal[0] * depth * factor, midpoint[1] - normal[1] * depth * factor),
                ]
                matching = [point for point in reduced if point_in_polygon(point, polygon)]
                if matching:
                    break
        if matching:
            result[room_id] = matching[0]
    return result


def graph_reachable(connections: list[dict[str, Any]], excluded_connections: set[str] | None = None) -> set[str]:
    excluded = excluded_connections or set()
    adjacency: dict[str, set[str]] = {}
    for connection in connections:
        if connection.get("id") in excluded:
            continue
        first = connection.get("fromRoomId")
        second = connection.get("toRoomId")
        if not first or not second:
            continue
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)
    if "exterior" not in adjacency:
        return set()
    seen = {"exterior"}
    stack = ["exterior"]
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, set()):
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return seen


def route_profile(room: dict[str, Any], policy: dict[str, Any]) -> str:
    mapping = policy.get("roomRouteProfiles", {})
    profile = mapping.get(room.get("spaceType"), "secondary")
    if profile not in policy["routeProfiles"]:
        raise ValueError(f"unknown route profile {profile}")
    return profile


def derive_routes(
    grid: Grid,
    shell_free: list[bool],
    layout_free: list[bool],
    structure: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Point]], list[dict[str, Any]]]:
    rooms = {room["id"]: room for room in structure.get("rooms", [])}
    connections = structure.get("connections", [])
    depth = float(policy["portalApproachDepthMeters"])
    sides: dict[str, dict[str, Point]] = {}
    findings: list[dict[str, Any]] = []
    for connection in connections:
        side_map = connection_sides(connection, rooms, depth)
        sides[connection["id"]] = side_map
        expected_rooms = {
            room_id for room_id in (connection.get("fromRoomId"), connection.get("toRoomId")) if room_id != "exterior"
        }
        missing = sorted(expected_rooms - set(side_map))
        if missing:
            findings.append(
                {
                    "code": "portal-approach-not-in-room",
                    "responsibility": "input-integrity",
                    "severity": "error",
                    "connectionId": connection["id"],
                    "roomIds": missing,
                }
            )

    routes: list[dict[str, Any]] = []
    for connection in connections:
        first = connection.get("fromRoomId")
        second = connection.get("toRoomId")
        if first == "exterior" or second == "exterior":
            continue
        side_map = sides.get(connection["id"], {})
        if first not in side_map or second not in side_map:
            continue
        profile = "primary" if any(
            rooms[room_id].get("topologyClass") in {"circulation", "open-zone"} for room_id in (first, second)
        ) else "secondary"
        routes.append(
            {
                "id": f"portal::{connection['id']}",
                "kind": "portal-crossing",
                "connectionId": connection["id"],
                "roomIds": [first, second],
                "profile": profile,
                "startPoints": [side_map[first]],
                "targetPoints": [side_map[second]],
            }
        )

    exterior_connections = [
        connection for connection in connections if "exterior" in {connection.get("fromRoomId"), connection.get("toRoomId")}
    ]
    entry_points: list[Point] = []
    for connection in exterior_connections:
        side_map = sides.get(connection["id"], {})
        entry_points.extend(side_map.values())
    source_reachable = graph_reachable(connections)
    for room_id, room in rooms.items():
        if room_id not in source_reachable or not entry_points:
            continue
        routes.append(
            {
                "id": f"entry-to-room::{room_id}",
                "kind": "entry-to-room",
                "roomIds": [room_id],
                "profile": route_profile(room, policy),
                "startPoints": entry_points,
                "targetRoomId": room_id,
                "targetAnchor": "reachable-free-room-interior-region",
            }
        )

    connections_by_room: dict[str, list[tuple[str, Point]]] = {room_id: [] for room_id in rooms}
    for connection in connections:
        for room_id, point in sides.get(connection["id"], {}).items():
            connections_by_room.setdefault(room_id, []).append((connection["id"], point))
    for room_id, portals in connections_by_room.items():
        if len(portals) < 2:
            continue
        profile = route_profile(rooms[room_id], policy)
        for first_index in range(len(portals)):
            for second_index in range(first_index + 1, len(portals)):
                first_id, first_point = portals[first_index]
                second_id, second_point = portals[second_index]
                routes.append(
                    {
                        "id": f"through-room::{room_id}::{first_id}::{second_id}",
                        "kind": "through-room",
                        "roomIds": [room_id],
                        "connectionIds": [first_id, second_id],
                        "profile": profile,
                        "startPoints": [first_point],
                        "targetPoints": [second_point],
                    }
                )
    return routes, sides, findings


def route_cells(
    route: dict[str, Any],
    grid: Grid,
    free: list[bool],
    rooms: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[set[int], set[int]]:
    radius = grid.resolution * 2.25
    starts = cells_near_points(grid, free, route["startPoints"], radius)
    if route.get("targetRoomId"):
        targets = room_target_cells(
            grid,
            free,
            rooms[route["targetRoomId"]],
            float(policy["roomInteriorDepthMeters"]),
        )
    else:
        targets = cells_near_points(grid, free, route["targetPoints"], radius)
    return starts, targets


def evaluate_route(
    route: dict[str, Any],
    grid: Grid,
    free: list[bool],
    clearance: list[float],
    rooms: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[float, list[Point]]:
    starts, targets = route_cells(route, grid, free, rooms, policy)
    return widest_path(grid, free, clearance, starts, targets)


def component_candidates_for_path(scene: dict[str, Any], path: list[Point], margin: float, limit: int) -> list[str]:
    if not path:
        return []
    corridor_bounds = path_bounds(path, margin)
    candidates = []
    for component in scene.get("components", []):
        if component.get("blockingClass") != "floor-obstacle":
            continue
        footprint = normalize_polygon(component["footprint"], f"{component['id']} footprint")
        if bbox_intersects(corridor_bounds, polygon_bounds(footprint)):
            candidates.append(component["id"])
    return sorted(candidates)[:limit]


def svg_report(
    path: Path,
    structure: dict[str, Any],
    scene: dict[str, Any],
    route_rows: list[dict[str, Any]],
) -> None:
    floor = normalize_polygon(structure["floorBoundary"], "floorBoundary")
    min_x, min_y, max_x, max_y = polygon_bounds(floor)
    width = max_x - min_x
    height = max_y - min_y
    canvas_width = 1200
    canvas_height = max(560, round(canvas_width * height / max(width, 1e-6)))
    padding = 42
    scale = min((canvas_width - 2 * padding) / max(width, 1e-6), (canvas_height - 2 * padding) / max(height, 1e-6))

    def map_point(point: Point) -> tuple[float, float]:
        return (padding + (point[0] - min_x) * scale, padding + (point[1] - min_y) * scale)

    def points_text(points: Iterable[Point]) -> str:
        return " ".join(f"{map_point(point)[0]:.2f},{map_point(point)[1]:.2f}" for point in points)

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}" height="{canvas_height}" viewBox="0 0 {canvas_width} {canvas_height}">',
        '<rect width="100%" height="100%" fill="#f5f4ef"/>',
        f'<polygon points="{points_text(floor)}" fill="#ffffff" stroke="#a8a69e" stroke-width="2"/>',
    ]
    for wall in structure.get("walls", []):
        start = tuple(map(float, wall["start"]))
        end = tuple(map(float, wall["end"]))
        mapped_start = map_point(start)
        mapped_end = map_point(end)
        stroke_width = max(2.0, float(wall.get("thickness", 0.2)) * scale)
        elements.append(
            f'<line x1="{mapped_start[0]:.2f}" y1="{mapped_start[1]:.2f}" x2="{mapped_end[0]:.2f}" y2="{mapped_end[1]:.2f}" stroke="#c74432" stroke-width="{stroke_width:.2f}" stroke-linecap="square" opacity="0.82"/>'
        )
    for connection in structure.get("connections", []):
        start = map_point(tuple(map(float, connection["start"])))
        end = map_point(tuple(map(float, connection["end"])))
        elements.append(
            f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" x2="{end[0]:.2f}" y2="{end[1]:.2f}" stroke="#158da5" stroke-width="7" stroke-linecap="round"/>'
        )
    for component in scene.get("components", []):
        if component.get("blockingClass") != "floor-obstacle":
            continue
        color = "#7550a8" if "fixed" in str(component.get("semantic")) else "#2f8058"
        footprint = normalize_polygon(component["footprint"], f"{component['id']} footprint")
        elements.append(
            f'<polygon points="{points_text(footprint)}" fill="{color}" fill-opacity="0.42" stroke="{color}" stroke-width="2"/>'
        )
        center = map_point(polygon_centroid(footprint))
        elements.append(
            f'<text x="{center[0]:.2f}" y="{center[1]:.2f}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#20201d">{component["id"]}</text>'
        )
    failing = [row for row in route_rows if row["disposition"] == "layout-regression"]
    representative = failing[0] if failing else (route_rows[0] if route_rows else None)
    if representative:
        shell_path = [tuple(point) for point in representative.get("shellPath", [])]
        layout_path = [tuple(point) for point in representative.get("layoutPath", [])]
        if shell_path:
            elements.append(
                f'<polyline points="{points_text(shell_path)}" fill="none" stroke="#b1842d" stroke-width="4" stroke-dasharray="10 7"/>'
            )
        if layout_path:
            color = "#b83a32" if representative["disposition"] == "layout-regression" else "#246b8f"
            elements.append(
                f'<polyline points="{points_text(layout_path)}" fill="none" stroke="{color}" stroke-width="4"/>'
            )
    elements.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(elements), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--svg-out")
    args = parser.parse_args()
    structure_path = Path(args.structure).expanduser().resolve()
    scene_path = Path(args.scene).expanduser().resolve()
    policy_path = Path(args.policy).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    structure = read_json(structure_path)
    scene = read_json(scene_path)
    policy = read_json(policy_path)
    require_schema(structure, STRUCTURE_SCHEMA, "structure data")
    require_schema(scene, SCENE_SCHEMA, "circulation scene")
    require_schema(policy, POLICY_SCHEMA, "circulation policy")
    if structure.get("floorplanId") != scene.get("floorplanId"):
        raise ValueError("structure and circulation scene floorplanId differ")
    if scene.get("bindings", {}).get("structureDataSha256") != sha256_file(structure_path):
        raise ValueError("circulation scene is not bound to the supplied structure data")
    if policy.get("principle") != "cap-layout-target-by-structural-baseline" or policy.get("forbiddenRoomSizeGates") is not True:
        raise ValueError("policy must use baseline-capped targets and forbid room-size gates")

    floor_boundary = normalize_polygon(structure["floorBoundary"], "floorBoundary")
    resolution = float(policy["gridResolutionMeters"])
    grid = Grid.from_polygon(floor_boundary, resolution, int(policy["maxGridCells"]))
    connections = structure.get("connections", [])
    shell_free = build_shell_grid(grid, floor_boundary, structure.get("walls", []), connections)
    layout_free = apply_layout_obstacles(grid, shell_free, component_polygons(scene))
    shell_clearance = clearance_field(grid, shell_free)
    layout_clearance = clearance_field(grid, layout_free)
    rooms = {room["id"]: room for room in structure.get("rooms", [])}
    try:
        endpoint_audit, endpoint_findings, endpoint_source = independently_audit_connection_endpoints(
            structure, policy
        )
    except ArtifactDiscoveryError as error:
        raise SystemExit(str(error)) from error
    relationship_audit, relationship_findings = audit_layout_relationships(
        structure, scene, policy
    )
    route_definitions, connection_sides_map, route_findings = derive_routes(
        grid, shell_free, layout_free, structure, policy
    )
    findings = endpoint_findings + relationship_findings + route_findings
    tolerance = float(policy["numericToleranceMeters"])
    route_rows: list[dict[str, Any]] = []
    for route in route_definitions:
        shell_width, shell_path = evaluate_route(route, grid, shell_free, shell_clearance, rooms, policy)
        layout_width, layout_path = evaluate_route(route, grid, layout_free, layout_clearance, rooms, policy)
        target = float(policy["routeProfiles"][route["profile"]]["targetWidthMeters"])
        effective_required = min(target, shell_width)
        if shell_width <= tolerance:
            disposition = "source-only-limitation"
            reason = "structural shell has no measurable route; report but do not reject the layout"
        elif layout_width + tolerance < effective_required:
            disposition = "layout-regression"
            reason = "current floor obstacles reduce the route below the baseline-capped target"
        elif shell_width + tolerance < target:
            disposition = "accepted-with-source-constraint"
            reason = "the layout preserves the narrow structural baseline"
        else:
            disposition = "accepted"
            reason = "the current layout preserves the required circulation capacity"
        row = {
            "id": route["id"],
            "kind": route["kind"],
            "roomIds": route.get("roomIds", []),
            "connectionId": route.get("connectionId"),
            "connectionIds": route.get("connectionIds", []),
            "profile": route["profile"],
            "configuredTargetWidthMeters": round(target, 4),
            "structuralBaselineWidthMeters": round(shell_width, 4),
            "effectiveRequiredWidthMeters": round(effective_required, 4),
            "currentLayoutWidthMeters": round(layout_width, 4),
            "layoutDeltaMeters": round(layout_width - shell_width, 4),
            "disposition": disposition,
            "reason": reason,
            "shellPath": downsample_path(shell_path),
            "layoutPath": downsample_path(layout_path),
            "attribution": {"candidateComponentIds": [], "singleRemovalRecovery": []},
        }
        route_rows.append(row)
        if disposition in {"source-only-limitation", "accepted-with-source-constraint"}:
            findings.append(
                {
                    "code": "inherited-structural-circulation-limit",
                    "responsibility": "source-structure",
                    "severity": "warning",
                    "routeId": route["id"],
                    "message": "The structural baseline is narrow or disconnected; keep designing and disclose the limitation.",
                }
            )
        elif disposition == "layout-regression":
            findings.append(
                {
                    "code": "layout-caused-circulation-regression",
                    "responsibility": "current-layout",
                    "severity": "error",
                    "routeId": route["id"],
                    "message": "Furniture or cabinetry reduced circulation below what the structural shell can support.",
                }
            )

    attribution_policy = policy.get("attribution", {})
    failing_rows = [row for row in route_rows if row["disposition"] == "layout-regression"]
    route_by_id = {route["id"]: route for route in route_definitions}
    for row in failing_rows:
        shell_path = [tuple(point) for point in row["shellPath"]]
        candidates = component_candidates_for_path(
            scene,
            shell_path,
            float(attribution_policy.get("pathCorridorMarginMeters", 0.75)),
            int(attribution_policy.get("maxCandidatesPerRoute", 12)),
        )
        recoveries = []
        for component_id in candidates:
            candidate_free = apply_layout_obstacles(
                grid,
                shell_free,
                component_polygons(scene, {component_id}),
            )
            candidate_clearance = clearance_field(grid, candidate_free)
            width, _ = evaluate_route(
                route_by_id[row["id"]], grid, candidate_free, candidate_clearance, rooms, policy
            )
            if width > row["currentLayoutWidthMeters"] + tolerance:
                recoveries.append(
                    {
                        "componentId": component_id,
                        "recoveredWidthMeters": round(width, 4),
                        "restoresRequirement": width + tolerance >= row["effectiveRequiredWidthMeters"],
                    }
                )
        recoveries.sort(key=lambda item: (-item["recoveredWidthMeters"], item["componentId"]))
        row["attribution"] = {
            "candidateComponentIds": candidates,
            "singleRemovalRecovery": recoveries,
            "provenSingleCulpritIds": [item["componentId"] for item in recoveries if item["restoresRequirement"]],
            "contributorIds": [item["componentId"] for item in recoveries],
        }

    source_reachable = graph_reachable(connections)
    portal_failures = {
        row["connectionId"]
        for row in route_rows
        if row["kind"] == "portal-crossing" and row["disposition"] == "layout-regression" and row.get("connectionId")
    }
    operational_reachable = graph_reachable(connections, portal_failures)
    room_openings = []
    for room_id, room in rooms.items():
        structural_connections = [
            connection["id"]
            for connection in connections
            if room_id in {connection.get("fromRoomId"), connection.get("toRoomId")}
        ]
        operational_connections = [identifier for identifier in structural_connections if identifier not in portal_failures]
        source_accessible = room_id in source_reachable
        layout_accessible = room_id in operational_reachable
        if not source_accessible:
            findings.append(
                {
                    "code": "room-not-connected-in-source-topology",
                    "responsibility": "source-structure",
                    "severity": "warning",
                    "roomId": room_id,
                    "message": "The accepted source topology has no route from an exterior entry; disclose it and continue.",
                }
            )
        elif not layout_accessible:
            findings.append(
                {
                    "code": "room-disconnected-by-layout",
                    "responsibility": "current-layout",
                    "severity": "error",
                    "roomId": room_id,
                    "message": "The source topology reaches this room, but current furniture/cabinet placement closes every operational route.",
                }
            )
        room_openings.append(
            {
                "roomId": room_id,
                "spaceType": room.get("spaceType"),
                "structuralOpeningCount": len(structural_connections),
                "structuralConnectionIds": structural_connections,
                "operationalOpeningCount": len(operational_connections),
                "operationalConnectionIds": operational_connections,
                "sourceAccessibleFromExterior": source_accessible,
                "layoutAccessibleFromExterior": layout_accessible,
            }
        )

    layout_errors = [finding for finding in findings if finding["responsibility"] == "current-layout" and finding["severity"] == "error"]
    integrity_errors = [finding for finding in findings if finding["responsibility"] == "input-integrity" and finding["severity"] == "error"]
    source_warnings = [finding for finding in findings if finding["responsibility"] == "source-structure"]
    if integrity_errors:
        status = "blocked-input-integrity"
    elif layout_errors:
        status = "needs-layout-adjustment"
    elif source_warnings:
        status = "accepted-with-source-constraints"
    else:
        status = "accepted"

    audit = {
        "schema": AUDIT_SCHEMA,
        "producer": {"skill": "interior-circulation-planning", "version": "3.1.0"},
        "floorplanId": structure["floorplanId"],
        "modelBackend": scene["modelBackend"],
        "bindings": {
            **scene["bindings"],
            "circulationScenePath": str(scene_path),
            "circulationSceneSha256": sha256_file(scene_path),
            "policyPath": str(policy_path),
            "policySha256": sha256_file(policy_path),
        },
        "method": {
            "id": "structure-topology-layout-relations-and-maximin-v3",
            "principle": "effectiveRequiredWidth=min(configuredTargetWidth,structuralBaselineWidth)",
            "gridResolutionMeters": resolution,
            "numericToleranceMeters": tolerance,
            "roomAreaGateCount": 0,
            "structuralMutationAllowed": False,
        },
        "topologyAudit": {
            "connectionCount": len(connections),
            "exteriorEntryConnectionIds": [
                connection["id"]
                for connection in connections
                if "exterior" in {connection.get("fromRoomId"), connection.get("toRoomId")}
            ],
            "sourceReachableRoomIds": sorted(source_reachable - {"exterior"}),
            "layoutReachableRoomIds": sorted(operational_reachable - {"exterior"}),
            "layoutBlockedConnectionIds": sorted(portal_failures),
            "roomOpenings": room_openings,
            "roundTripModel": "undirected-static-free-space; every accepted edge is checked from both approach zones",
            "compiledEndpointAuditDiscovery": endpoint_source,
            "connectionEndpointAudit": endpoint_audit,
        },
        "layoutRelationshipAudit": {
            "authority": "interior-circulation-planning",
            "backendOnlySupplies": ["functionalClass", "roomId", "footprint", "activeTransform", "localAxes"],
            "results": relationship_audit,
            "passed": all(row.get("passed") is True for row in relationship_audit),
        },
        "routes": route_rows,
        "findings": findings,
        "counts": {
            "routes": len(route_rows),
            "acceptedRoutes": sum(row["disposition"] == "accepted" for row in route_rows),
            "sourceConstrainedRoutes": sum(
                row["disposition"] in {"source-only-limitation", "accepted-with-source-constraint"}
                for row in route_rows
            ),
            "layoutRegressionRoutes": sum(row["disposition"] == "layout-regression" for row in route_rows),
            "sourceWarnings": len(source_warnings),
            "layoutErrors": len(layout_errors),
            "integrityErrors": len(integrity_errors),
            "relationshipChecks": len(relationship_audit),
            "layoutRelationshipFailures": sum(row.get("passed") is not True for row in relationship_audit),
            "connectionEndpointFailures": sum(row.get("passed") is not True for row in endpoint_audit),
        },
        "verdict": {
            "status": status,
            "cameraWorkflowAllowed": status in {"accepted", "accepted-with-source-constraints"},
            "sourceConstraintsAreBlocking": False,
            "layoutRegressionsRequireAdjustment": True,
        },
    }
    audit["auditDigestSha256"] = canonical_sha256(audit)
    write_json(out_path, audit)
    if args.svg_out:
        svg_report(Path(args.svg_out).expanduser().resolve(), structure, scene, route_rows)
    print(
        f"circulation audit {status}: {audit['counts']['layoutRegressionRoutes']} layout regressions, "
        f"{audit['counts']['sourceConstrainedRoutes']} inherited constraints"
    )
    if status == "blocked-input-integrity":
        return 2
    if status == "needs-layout-adjustment":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
