#!/usr/bin/env python3
"""Validate template data or a project imported from the current floorplan handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_digest(payload: dict) -> str:
    copy = dict(payload)
    copy.pop("handoffDigestSha256", None)
    encoded = json.dumps(copy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def wall_frame(wall: dict) -> dict:
    dx = wall["end"][0] - wall["start"][0]
    dz = wall["end"][1] - wall["start"][1]
    length = math.hypot(dx, dz)
    assert length > 0.01, f"{wall['id']} must have non-zero physical length"
    return {"length": length, "dx": dx / length, "dz": dz / length}


def polygon_area(points: list[list[float]]) -> float:
    return abs(sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )) / 2


def point_on_segment(
    point: list[float],
    start: list[float],
    end: list[float],
    tolerance: float = 1e-6,
) -> bool:
    px, pz = point
    ax, az = start
    bx, bz = end
    cross = abs((px - ax) * (bz - az) - (pz - az) * (bx - ax))
    if cross > tolerance:
        return False
    return (
        min(ax, bx) - tolerance <= px <= max(ax, bx) + tolerance
        and min(az, bz) - tolerance <= pz <= max(az, bz) + tolerance
    )


def point_in_polygon(point: list[float], polygon: list[list[float]]) -> bool:
    x, z = point
    if any(
        point_on_segment(point, polygon[index], polygon[(index + 1) % len(polygon)])
        for index in range(len(polygon))
    ):
        return True
    inside = False
    for current, previous in zip(polygon, polygon[-1:] + polygon[:-1]):
        x1, z1 = current
        x2, z2 = previous
        if (z1 > z) != (z2 > z):
            crossing = (x2 - x1) * (z - z1) / (z2 - z1) + x1
            if x < crossing:
                inside = not inside
    return inside


def duplicate_parallel_walls(walls: list[dict]) -> list[str]:
    errors = []
    for index, first in enumerate(walls):
        a = wall_frame(first)
        for second in walls[index + 1:]:
            b = wall_frame(second)
            parallel = abs(a["dx"] * b["dz"] - a["dz"] * b["dx"])
            if parallel > 0.015:
                continue
            normal_x, normal_z = -a["dz"], a["dx"]
            separation = abs(
                (second["start"][0] - first["start"][0]) * normal_x
                + (second["start"][1] - first["start"][1]) * normal_z
            )
            if separation > max(first["thickness"], second["thickness"]) * 0.75:
                continue
            def projection(point: list[float]) -> float:
                return point[0] * a["dx"] + point[1] * a["dz"]
            first_range = sorted((projection(first["start"]), projection(first["end"])))
            second_range = sorted((projection(second["start"]), projection(second["end"])))
            overlap = min(first_range[1], second_range[1]) - max(first_range[0], second_range[0])
            if overlap > min(a["length"], b["length"]) * 0.5:
                errors.append(
                    f"{first['id']} and {second['id']} are duplicate near-collinear wall centerlines; "
                    "a wall band must compile to one semantic wall"
                )
    return errors


def validate_handoff(manifest_path: Path, structure_path: Path, data: dict) -> dict:
    manifest = load(manifest_path)
    assert manifest.get("schema") == "interior.floorplan-handoff.v3"
    producer = manifest.get("producer", {})
    version = str(producer.get("version", ""))
    assert producer.get("skill") == "interior-floorplan-planning" and version.startswith("6."), (
        "project handoff must use one schema-compatible floorplan 6.x producer"
    )
    assert canonical_digest(manifest) == manifest.get("handoffDigestSha256"), "handoff manifest digest mismatch"
    assert manifest.get("validation") == {
        "sourceModel": True,
        "agentVisualReview": True,
    }, "source model and Agent visual review must pass"
    entry = manifest.get("artifacts", {}).get("structureData", {})
    assert digest(structure_path) == entry.get("sha256"), "project structure-data differs from verified handoff"
    assert data.get("floorplanId") == manifest.get("floorplanId"), "floorplanId differs from handoff"
    registry = set(manifest.get("sourceTraceRegistry", {}).get("structureTraceIds", []))
    assert registry, "handoff structure source registry is empty"
    for item in data.get("walls", []) + data.get("windows", []) + data.get("connections", []):
        for trace_id in item.get("sourceTraceIds", []) + item.get("sourceDividerIds", []):
            assert trace_id in registry, f"{item.get('id')}: unresolved sourceTraceId {trace_id}"
    root = manifest_path.parent
    assert set(manifest.get("reports", {})) == {"sourceModelValidation"}
    floor_report_entry = manifest["reports"]["sourceModelValidation"]
    report_path = (root / floor_report_entry.get("path", "")).resolve()
    assert report_path.is_file(), "missing source-model report"
    assert digest(report_path) == floor_report_entry.get("sha256"), "source-model report changed"
    floor_report = load((root / floor_report_entry["path"]).resolve())
    assert floor_report.get("schema") == "interior.floorplan-source-model-validation.v1"
    assert floor_report.get("traceSpecSha256") == manifest["artifacts"]["traceSpec"]["sha256"]
    assert floor_report.get("passed") is True and not floor_report.get("errors")
    metrics = floor_report.get("independentFloorMetrics", {})
    for field in ("missedPixels", "outsidePixels", "overlapCorePixels"):
        assert metrics.get(field) == 0, f"upstream floor metric {field} must be zero"
    topology = floor_report.get("topologyMetrics", {})
    assert topology == data.get("topology"), "structure topology differs from the compiled handoff"
    assert topology.get("method") == "wall-mask-opening-closure-space-seed"
    assert topology.get("interiorPixels", 0) > 0
    assert topology.get("assignedInteriorPixels") == topology.get("interiorPixels")
    assert topology.get("spaceSeedCount") == len(data.get("rooms", []))
    assert topology.get("roomCount") == len(data.get("rooms", []))
    assert topology.get("mergedSeedGroups") == []
    assert topology.get("unassignedRegionCount") == 0
    assert topology.get("orphanWallIds") == []
    assert topology.get("openingEndpointMismatches") == []
    return {
        "handoffDigestSha256": manifest["handoffDigestSha256"],
        "producerVersion": manifest["producer"]["version"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--template", action="store_true")
    mode.add_argument("--handoff")
    parser.add_argument("structure")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.structure).resolve()
    data = load(path)
    assert data.get("schema") == "interior.floorplan-structure.v3", "only interior.floorplan-structure.v3 is accepted"
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", data.get("floorplanId", "")), "invalid floorplanId"
    assert "rectangles" not in data, "pixel-cell rectangles are retired; use semantic walls"
    assert "furnitureCatalog" not in data, "structure-data must not embed a component catalog"
    assert "furniturePlacements" not in data, "component placements belong in component-layout.json"

    handoff = None
    if args.template:
        assert data.get("floorplanId") == "template-floorplan", "--template is only valid for the shipped base template"
    else:
        handoff = validate_handoff(Path(args.handoff).resolve(), path, data)

    cfg = data["coordinateSystem"]
    assert cfg["units"] == "m"
    assert cfg["realWidthMeters"] > 0 and cfg["realDepthMeters"] > 0
    boundary = data["floorBoundary"]
    assert len(boundary) >= 3 and polygon_area(boundary) > 0.5
    rooms = data.get("rooms", [])
    space_types = {
        "living", "dining", "kitchen", "bedroom", "bathroom", "study",
        "balcony", "entrance", "corridor", "closet", "storage", "utility",
        "multipurpose", "other",
    }
    enclosed_space_types = {"bedroom", "bathroom", "study", "closet", "storage"}
    room_ids = [room.get("id") for room in rooms]
    assert rooms, "compiled structure must contain actual rooms"
    assert None not in room_ids and len(room_ids) == len(set(room_ids)), "rooms need unique non-empty IDs"
    for room in rooms:
        polygon = room.get("polygon", [])
        assert len(polygon) >= 3 and polygon_area(polygon) > 0.05, f"{room.get('id')}: invalid room polygon"
        assert all(point_in_polygon(point, boundary) for point in polygon), f"{room.get('id')}: room leaves floorBoundary"
        assert room.get("topologyClass") in {
            "enclosed", "open-zone", "circulation", "attached",
        }, f"{room.get('id')}: invalid topologyClass"
        assert room.get("spaceType") in space_types, f"{room.get('id')}: invalid spaceType"
        if room["spaceType"] in enclosed_space_types:
            assert room["topologyClass"] == "enclosed", (
                f"{room.get('id')}: {room['spaceType']} must be an enclosed room"
            )
        assert abs(float(room.get("areaM2", 0)) - polygon_area(polygon)) <= 0.35, (
            f"{room.get('id')}: areaM2 differs from compiled polygon"
        )
    layers = data.get("layers", {})
    if "annotations" in layers:
        assert isinstance(layers["annotations"], bool)

    walls = data["walls"]
    windows = data.get("windows", [])
    connections = data.get("connections", [])
    semantic_dividers = data.get("semanticDividers", [])
    assert walls, "walls must not be empty"
    ids: set[str] = set()
    wall_map: dict[str, dict] = {}
    for wall in walls:
        assert wall["id"] not in ids, f"duplicate id: {wall['id']}"
        ids.add(wall["id"])
        wall_map[wall["id"]] = wall
        wall_frame(wall)
        assert wall["height"] >= 0.5
        assert 0.06 <= wall["thickness"] <= 0.8
        assert wall.get("sourceTraceIds"), f"{wall['id']} must preserve trace provenance"
        adjacent = wall.get("adjacentRoomIds", [])
        assert len(adjacent) >= 2 and len(adjacent) == len(set(adjacent)), (
            f"{wall['id']}: every wall must separate distinct room/exterior sides"
        )
        assert set(adjacent) <= set(room_ids) | {"exterior"}, (
            f"{wall['id']}: wall adjacency references unknown rooms"
        )
        assert any(room_id in set(room_ids) for room_id in adjacent), (
            f"{wall['id']}: wall is not adjacent to usable space"
        )
    duplicate_errors = duplicate_parallel_walls(walls)
    assert not duplicate_errors, "; ".join(duplicate_errors)

    windows_by_wall: dict[str, list[dict]] = {}
    for window in windows:
        assert window["id"] not in ids, f"duplicate id: {window['id']}"
        ids.add(window["id"])
        assert window["wallId"] in wall_map, f"{window['id']} host wall missing"
        wall = wall_map[window["wallId"]]
        length = wall_frame(wall)["length"]
        assert 0.01 < window["width"] <= length + 1e-6
        assert window["offset"] - window["width"] / 2 >= -1e-6
        assert window["offset"] + window["width"] / 2 <= length + 1e-6
        assert window["sill"] >= 0
        assert window["openingHeight"] > 0.3
        assert window["sill"] + window["openingHeight"] < wall["height"] - 0.04
        assert window.get("sourceTraceIds"), f"{window['id']} must preserve trace provenance"
        windows_by_wall.setdefault(window["wallId"], []).append(window)
    for wall_id, items in windows_by_wall.items():
        items.sort(key=lambda item: item["offset"])
        for previous, current in zip(items, items[1:]):
            previous_end = previous["offset"] + previous["width"] / 2
            current_start = current["offset"] - current["width"] / 2
            assert previous_end + 0.08 <= current_start, f"window openings overlap on {wall_id}"

    room_id_set = set(room_ids)
    graph: dict[str, set[str]] = {room_id: set() for room_id in room_id_set}
    room_connections: dict[str, set[str]] = {room_id: set() for room_id in room_id_set}
    room_connection_kinds: dict[str, list[str]] = {room_id: [] for room_id in room_id_set}
    graph["exterior"] = set()
    connection_map: dict[str, dict] = {}
    for connection in connections:
        assert connection["id"] not in ids, f"duplicate id: {connection['id']}"
        ids.add(connection["id"])
        left = connection.get("fromRoomId")
        right = connection.get("toRoomId")
        assert left != right
        assert left in room_id_set | {"exterior"} and right in room_id_set | {"exterior"}, (
            f"{connection['id']}: unknown connection room"
        )
        assert connection.get("kind") in {
            "door", "open-passage", "glazing", "window", "sliding-door",
        }
        connection_map[connection["id"]] = connection
        start = connection.get("start", [])
        end = connection.get("end", [])
        assert len(start) == 2 and len(end) == 2 and start != end, (
            f"{connection['id']}: invalid opening segment"
        )
        assert float(connection.get("bottom", -1)) >= 0
        assert float(connection.get("height", 0)) > 0.3
        physical_ids = connection.get("sourceTraceIds", [])
        divider_ids = connection.get("sourceDividerIds", [])
        assert bool(physical_ids) != bool(divider_ids), (
            f"{connection['id']} needs exactly one physical-opening or semantic-divider provenance"
        )
        if divider_ids:
            assert connection.get("kind") == "open-passage", (
                f"{connection['id']}: semantic divider provenance only permits open-passage"
            )
        if connection.get("kind") in {"door", "open-passage", "sliding-door"}:
            graph.setdefault(left, set()).add(right)
            graph.setdefault(right, set()).add(left)
            if left in room_id_set:
                room_connections[left].add(connection["id"])
                room_connection_kinds[left].append(connection["kind"])
            if right in room_id_set:
                room_connections[right].add(connection["id"])
                room_connection_kinds[right].append(connection["kind"])
    divider_ids: set[str] = set()
    divider_source_ids: set[str] = set()
    for divider in semantic_dividers:
        divider_id = divider.get("id")
        source_divider_id = divider.get("sourceDividerId")
        assert divider_id and divider_id not in divider_ids, (
            "semantic dividers need unique non-empty IDs"
        )
        divider_ids.add(divider_id)
        assert source_divider_id and source_divider_id not in divider_source_ids, (
            f"{divider_id}: sourceDividerId must be unique"
        )
        divider_source_ids.add(source_divider_id)
        room_pair = divider.get("roomIds", [])
        assert len(room_pair) == 2 and len(set(room_pair)) == 2, (
            f"{divider_id}: semantic divider must separate exactly two rooms"
        )
        assert set(room_pair) <= room_id_set, (
            f"{divider_id}: semantic divider references an unknown room"
        )
        assert divider.get("traversal") in {"open-passage", "boundary-only"}, (
            f"{divider_id}: invalid divider traversal"
        )
        start = divider.get("start", [])
        end = divider.get("end", [])
        assert len(start) == 2 and len(end) == 2 and start != end, (
            f"{divider_id}: invalid divider segment"
        )
        connection_id = divider.get("connectionId")
        if divider["traversal"] == "open-passage":
            connection = connection_map.get(connection_id)
            assert (
                connection is not None
                and connection.get("kind") == "open-passage"
                and connection.get("sourceDividerIds") == [source_divider_id]
                and {
                    connection.get("fromRoomId"),
                    connection.get("toRoomId"),
                }
                == set(room_pair)
            ), f"{divider_id}: open-passage divider lacks its same-source connection"
        else:
            assert connection_id is None, (
                f"{divider_id}: boundary-only divider must not create a connection"
            )
    reachable = {"exterior"}
    queue = ["exterior"]
    while queue:
        current = queue.pop(0)
        for neighbor in graph.get(current, set()):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)
    assert room_id_set <= reachable, (
        f"every room needs an evidenced path to exterior; missing {sorted(room_id_set - reachable)}"
    )
    for room in rooms:
        assert room_connections[room["id"]], (
            f"{room['id']}: every room needs at least one traversable connection"
        )
        if room["topologyClass"] == "enclosed":
            assert {"door", "sliding-door"}.intersection(
                room_connection_kinds[room["id"]]
            ), f"{room['id']}: enclosed room needs a door or sliding-door access"

    print(json.dumps({
        "ok": True,
        "mode": "template" if args.template else "verified-floorplan-handoff",
        "schema": data["schema"],
        "floorplanId": data["floorplanId"],
        "walls": len(walls),
        "windows": len(windows),
        "connections": len(connections),
        "semanticDividers": len(semantic_dividers),
        "traversableSemanticDividers": sum(
            item.get("traversal") == "open-passage"
            for item in semantic_dividers
        ),
        "boundaryOnlySemanticDividers": sum(
            item.get("traversal") == "boundary-only"
            for item in semantic_dividers
        ),
        "rooms": len(rooms),
        "roomAreasM2": {
            room["id"]: round(polygon_area(room["polygon"]), 3)
            for room in rooms
        },
        "embeddedComponentCatalog": False,
        "embeddedComponentPlacements": False,
        "handoff": handoff,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
