#!/usr/bin/env python3
"""Deterministically choose one wall-normal primary-camera seed per requested room."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SEED_SCHEMA = "interior.camera-frontal-seed-set.v1"
STRUCTURE_SCHEMA = "interior.floorplan-structure.v3"
SCENE_SCHEMA = "interior.circulation-scene.v2"
RESULT_SCHEMA = "interior.circulation-result.v2"
MANIFEST_SCHEMA = "interior.native-model-manifest.v1"
METHOD_VERSION = "deterministic-wall-normal-camera-v7"
ROOM_TYPE_MAP = {
    "living": "living",
    "dining": "dining",
    "kitchen": "kitchen",
    "entrance": "entry",
    "entry": "entry",
    "corridor": "corridor",
    "bedroom": "bedroom",
    "bathroom": "bathroom",
    "study": "study",
    "multipurpose": "study",
    "balcony": "balcony",
}
ANCHOR_PRIORITY = {
    "living": ("sofa", "tv-console", "tea-table", "accent-chair"),
    "dining": ("dining-table", "dining-chair", "sideboard"),
    "kitchen": ("kitchen-cabinet", "base-cabinet", "cooktop", "sink", "refrigerator"),
    "entry": ("shoe-cabinet", "sideboard", "entry-bench"),
    "corridor": ("sideboard", "console", "wall-art"),
    "bedroom": ("bed", "double-bed", "single-bed", "wardrobe", "bedside-table"),
    "bathroom": ("vanity", "toilet", "washbasin", "shower"),
    "study": ("desk", "worktable", "bookcase", "chair"),
    "balcony": ("balcony-seat", "outdoor-chair", "plant", "side-table"),
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verify_digest(document: dict[str, Any], key: str, label: str) -> str:
    payload = dict(document)
    declared = payload.pop(key, None)
    actual = canonical_sha256(payload)
    if declared != actual:
        raise ValueError(f"{label} {key} is invalid")
    return actual


def require_schema(document: dict[str, Any], schema: str, label: str) -> None:
    if document.get("schema") != schema:
        raise ValueError(f"{label} must use {schema}")


def polygon_centroid(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    area_twice = 0.0
    x_total = 0.0
    y_total = 0.0
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        cross = start[0] * end[1] - end[0] * start[1]
        area_twice += cross
        x_total += (start[0] + end[0]) * cross
        y_total += (start[1] + end[1]) * cross
    if abs(area_twice) <= 1e-9:
        return (
            sum(point[0] for point in polygon) / len(polygon),
            sum(point[1] for point in polygon) / len(polygon),
        )
    return x_total / (3 * area_twice), y_total / (3 * area_twice)


def polygon_area(polygon: list[tuple[float, float]]) -> float:
    return abs(
        sum(
            start[0] * polygon[(index + 1) % len(polygon)][1]
            - polygon[(index + 1) % len(polygon)][0] * start[1]
            for index, start in enumerate(polygon)
        )
    ) / 2


def normalize(vector: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*vector)
    if length <= 1e-9:
        raise ValueError("cannot normalize a zero-length vector")
    return vector[0] / length, vector[1] / length


def cross2(left: tuple[float, float], right: tuple[float, float]) -> float:
    return left[0] * right[1] - left[1] * right[0]


def nearest_point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float]:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    denominator = delta_x * delta_x + delta_y * delta_y
    if denominator <= 1e-12:
        return start
    parameter = ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y) / denominator
    parameter = max(0.0, min(1.0, parameter))
    return start[0] + delta_x * parameter, start[1] + delta_y * parameter


def point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    nearest = nearest_point_on_segment(point, start, end)
    return math.dist(point, nearest)


def ray_polygon_distances(
    origin: tuple[float, float],
    direction: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> list[float]:
    distances = []
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        segment = end[0] - start[0], end[1] - start[1]
        denominator = cross2(direction, segment)
        if abs(denominator) <= 1e-9:
            continue
        relative = start[0] - origin[0], start[1] - origin[1]
        distance = cross2(relative, segment) / denominator
        segment_parameter = cross2(relative, direction) / denominator
        if distance > 1e-6 and -1e-6 <= segment_parameter <= 1 + 1e-6:
            distances.append(distance)
    return sorted(distances)


def plan_to_world(structure: dict[str, Any], point: tuple[float, float]) -> tuple[float, float]:
    coordinates = structure.get("coordinateSystem", {})
    if coordinates.get("units") != "m":
        raise ValueError("structure coordinates must use metres")
    if coordinates.get("origin") == "world-center":
        return point
    if coordinates.get("origin") == "north-west":
        return (
            point[0] - float(coordinates["realWidthMeters"]) / 2,
            point[1] - float(coordinates["realDepthMeters"]) / 2,
        )
    raise ValueError(f"unsupported structure origin: {coordinates.get('origin')!r}")


def functional_rank(functional_class: str, room_type: str) -> int:
    priorities = ANCHOR_PRIORITY.get(room_type, ())
    for index, expected in enumerate(priorities):
        if functional_class == expected or functional_class.startswith(f"{expected}-"):
            return index
    return len(priorities) + 100


def select_anchor(components: list[dict[str, Any]], room_type: str) -> dict[str, Any] | None:
    if not components:
        return None
    ranked = sorted(
        components,
        key=lambda component: (
            functional_rank(str(component.get("functionalClass", "")), room_type),
            -polygon_area([tuple(map(float, point)) for point in component.get("footprint", [])]),
            str(component.get("id", "")),
        ),
    )
    return ranked[0]


def select_reference_wall(
    room_id: str,
    target: tuple[float, float],
    anchor_id: str | None,
    walls: list[dict[str, Any]],
    relation_hints: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    explicit_ids = sorted(
        {
            row.get("wallId")
            for row in relation_hints.get("wallAttachment", [])
            if row.get("sourceId") == anchor_id and row.get("wallId")
        }
    )
    by_id = {wall.get("id"): wall for wall in walls}
    explicit = [by_id[identifier] for identifier in explicit_ids if identifier in by_id]
    if explicit:
        return explicit[0], "accepted-wall-attachment-hint"
    adjacent = [wall for wall in walls if room_id in wall.get("adjacentRoomIds", [])]
    if not adjacent:
        return None, "no-real-wall-adjacent-to-room"
    adjacent.sort(
        key=lambda wall: (
            point_segment_distance(target, tuple(map(float, wall["start"])), tuple(map(float, wall["end"]))),
            -math.dist(tuple(map(float, wall["start"])), tuple(map(float, wall["end"]))),
            str(wall.get("id", "")),
        )
    )
    return adjacent[0], "nearest-adjacent-real-wall-with-longest-wall-and-id-tiebreak"


def build_seed_set(
    *,
    structure_path: Path,
    scene_path: Path,
    circulation_result_path: Path,
    native_manifest_path: Path,
    requested_room_ids: list[str] | None = None,
) -> dict[str, Any]:
    paths = {
        key: Path(value).expanduser().resolve()
        for key, value in {
            "structure": structure_path,
            "scene": scene_path,
            "circulationResult": circulation_result_path,
            "nativeManifest": native_manifest_path,
        }.items()
    }
    structure = read_json(paths["structure"])
    scene = read_json(paths["scene"])
    circulation = read_json(paths["circulationResult"])
    manifest = read_json(paths["nativeManifest"])
    require_schema(structure, STRUCTURE_SCHEMA, "structure")
    require_schema(scene, SCENE_SCHEMA, "circulation scene")
    require_schema(circulation, RESULT_SCHEMA, "circulation result")
    require_schema(manifest, MANIFEST_SCHEMA, "native manifest")
    verify_digest(circulation, "resultDigestSha256", "circulation result")
    if circulation.get("verdict", {}).get("cameraWorkflowAllowed") is not True:
        raise ValueError("circulation result does not allow camera work")
    floorplan_ids = {
        structure.get("floorplanId"),
        scene.get("floorplanId"),
        circulation.get("floorplanId"),
        manifest.get("floorplanId"),
    }
    if len(floorplan_ids) != 1:
        raise ValueError("camera seed inputs belong to different floorplans")
    if scene.get("bindings", {}).get("structureDataSha256") != sha256_file(paths["structure"]):
        raise ValueError("circulation scene is not bound to structure")
    native_hash = manifest.get("nativeModel", {}).get("sha256")
    if not native_hash or native_hash != scene.get("bindings", {}).get("nativeModelSha256"):
        raise ValueError("circulation scene and native manifest model hashes differ")
    if native_hash != circulation.get("bindings", {}).get("nativeModelSha256"):
        raise ValueError("circulation result and native manifest model hashes differ")
    if manifest.get("modelBackend") != scene.get("modelBackend"):
        raise ValueError("circulation scene and native manifest backends differ")

    rooms = {room["id"]: room for room in structure.get("rooms", [])}
    requested = list(requested_room_ids) if requested_room_ids is not None else sorted(rooms)
    if not requested or len(requested) != len(set(requested)):
        raise ValueError("requested room IDs must be non-empty and unique")
    unknown = sorted(set(requested) - set(rooms))
    if unknown:
        raise ValueError(f"unknown requested room IDs: {unknown}")

    components_by_room: dict[str, list[dict[str, Any]]] = {}
    for component in scene.get("components", []):
        components_by_room.setdefault(component.get("roomId"), []).append(component)
    walls = structure.get("walls", [])
    relation_hints = scene.get("relationHints", {})
    seeds = []
    blockers = []
    for room_id in requested:
        room = rooms[room_id]
        room_type = ROOM_TYPE_MAP.get(str(room.get("spaceType", "")), "corridor")
        polygon = [tuple(map(float, point)) for point in room["polygon"]]
        room_center = polygon_centroid(polygon)
        room_components = components_by_room.get(room_id, [])
        anchor = select_anchor(room_components, room_type)
        if anchor is None:
            blockers.append({"roomId": room_id, "code": "missing-functional-anchor"})
            continue
        target_plan = tuple(map(float, anchor["activeTransform"]["position"]))
        wall, wall_method = select_reference_wall(
            room_id,
            target_plan,
            anchor.get("id"),
            walls,
            relation_hints,
        )
        if wall is None:
            blockers.append({"roomId": room_id, "code": wall_method})
            continue
        wall_start = tuple(map(float, wall["start"]))
        wall_end = tuple(map(float, wall["end"]))
        nearest_wall_point = nearest_point_on_segment(target_plan, wall_start, wall_end)
        view_direction = normalize(
            (nearest_wall_point[0] - room_center[0], nearest_wall_point[1] - room_center[1])
        )
        retreat_direction = -view_direction[0], -view_direction[1]
        retreat_distances = ray_polygon_distances(target_plan, retreat_direction, polygon)
        estimated_depth = max(0.0, (retreat_distances[0] if retreat_distances else 0.0) - 0.15)
        camera_side_plan = (
            target_plan[0] + retreat_direction[0] * max(0.35, estimated_depth * 0.5),
            target_plan[1] + retreat_direction[1] * max(0.35, estimated_depth * 0.5),
        )
        target_world = plan_to_world(structure, target_plan)
        camera_side_world = plan_to_world(structure, camera_side_plan)
        context_ids = sorted(
            component["id"] for component in room_components if component["id"] != anchor["id"]
        )
        seed = {
            "seedId": f"frontal::{room_id}",
            "roomId": room_id,
            "roomType": room_type,
            "role": "primary",
            "composition": "one-point-frontal",
            "referenceWallId": wall["id"],
            "referenceWallSelectionMethod": wall_method,
            "anchorElementIds": [anchor["id"]],
            "anchorFunctionalClass": anchor.get("functionalClass"),
            "referenceFacadeElementIds": [wall["id"]],
            "contextElementIds": context_ids,
            "targetPlanXZ": [round(value, 6) for value in target_plan],
            "targetWorldXZ": [round(value, 6) for value in target_world],
            "cameraSideWorldXZ": [round(value, 6) for value in camera_side_world],
            "estimatedRetreatDepthMeters": round(estimated_depth, 6),
            "nativeMeasurementRequired": {
                "anchorObbEightCorners": True,
                "referenceFacadeObbEightCorners": True,
                "contextObbEightCorners": True,
                "availableRetreatDepth": True,
                "projectionAndOcclusion": True,
            },
            "calculatorArguments": {
                "composition": "one-point-frontal",
                "roomType": room_type,
                "structureData": str(paths["structure"]),
                "referenceWallId": wall["id"],
                "targetXZ": ",".join(f"{value:.6f}" for value in target_world),
                "cameraSideXZ": ",".join(f"{value:.6f}" for value in camera_side_world),
            },
        }
        seed["seedDigestSha256"] = canonical_sha256(seed)
        seeds.append(seed)

    status = "ready" if len(seeds) == len(requested) else "algorithm-blocked"
    output = {
        "schema": SEED_SCHEMA,
        "producer": {"skill": "interior-camera-capture", "version": "20.0.0"},
        "methodVersion": METHOD_VERSION,
        "floorplanId": structure["floorplanId"],
        "modelBackend": manifest["modelBackend"],
        "sourceModelSha256": native_hash,
        "bindings": {
            "structureDataPath": str(paths["structure"]),
            "structureDataSha256": sha256_file(paths["structure"]),
            "circulationScenePath": str(paths["scene"]),
            "circulationSceneSha256": sha256_file(paths["scene"]),
            "circulationResultPath": str(paths["circulationResult"]),
            "circulationResultSha256": sha256_file(paths["circulationResult"]),
            "circulationResultDigestSha256": circulation["resultDigestSha256"],
            "nativeManifestPath": str(paths["nativeManifest"]),
            "nativeManifestSha256": sha256_file(paths["nativeManifest"]),
        },
        "algorithm": {
            "status": status,
            "requestedRoomCount": len(requested),
            "solvedRoomCount": len(seeds),
            "complexity": "bounded-sort-per-room-plus-linear-wall-and-component-scan",
            "timeGateSeconds": None,
            "humanCandidateSelectionRequired": False,
            "oneFrontalPrimaryRequiredPerRoom": True,
        },
        "requestedRoomIds": requested,
        "seeds": seeds,
        "blockers": blockers,
        "nextStep": (
            "Measure all native OBBs and retreat depths once, then run compile_camera_candidates.py once for the full scope."
            if status == "ready"
            else "Repair the listed structural evidence; do not invent a reference wall or ask repeated confirmation questions."
        ),
    }
    output["seedSetDigestSha256"] = canonical_sha256(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--circulation-result", required=True)
    parser.add_argument("--native-manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--room-ids", help="comma-separated requested rooms; default is every structure room")
    args = parser.parse_args()

    requested = None
    if args.room_ids:
        requested = [value.strip() for value in args.room_ids.split(",") if value.strip()]
    output = build_seed_set(
        structure_path=Path(args.structure),
        scene_path=Path(args.scene),
        circulation_result_path=Path(args.circulation_result),
        native_manifest_path=Path(args.native_manifest),
        requested_room_ids=requested,
    )
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    algorithm = output["algorithm"]
    print(
        f"frontal seed solver {algorithm['status']}: "
        f"{algorithm['solvedRoomCount']}/{algorithm['requestedRoomCount']} rooms"
    )
    return 0 if algorithm["status"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
