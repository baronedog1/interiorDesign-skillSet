#!/usr/bin/env python3
"""Export a Blender-native semantic scene package for the common camera solver."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def property_value(value):
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def blender_to_three(point: Vector) -> tuple[float, float, float]:
    return float(point.x), float(point.z), -float(point.y)


def renderable_groups() -> dict[str, list]:
    groups: dict[str, list] = {}
    for obj in bpy.context.scene.objects:
        entity_id = property_value(obj.get("interiorEntityId"))
        if not entity_id or obj.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            continue
        groups.setdefault(str(entity_id), []).append(obj)
    return groups


def group_bounds(objects) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return minimum, maximum


def native_entities(model: dict) -> list[dict]:
    model_furniture = {item["id"]: item for item in model.get("furniture", [])}
    entities = []
    for entity_id, objects in sorted(renderable_groups().items()):
        minimum, maximum = group_bounds(objects)
        center = (minimum + maximum) / 2
        source = model_furniture.get(entity_id, {})
        entity_type = property_value(objects[0].get("interiorEntityType", "unknown"))
        kind = (
            "furniture" if str(entity_type).startswith("component")
            else "opening" if str(entity_type).startswith("opening")
            else "floor" if str(entity_type) == "floor"
            else "ceiling" if str(entity_type) == "ceiling"
            else "wall"
        )
        tmin, tmax, tcenter = blender_to_three(minimum), blender_to_three(maximum), blender_to_three(center)
        entities.append({
            "id": entity_id,
            "kind": kind,
            "roomIds": [source.get("roomId")] if source.get("roomId") else property_value(objects[0].get("adjacentRoomIds", [])),
            "functionalClass": source.get("functionalClass"),
            "world": {
                "center": {"x": round(tcenter[0], 6), "y": round(tcenter[1], 6), "z": round(tcenter[2], 6)},
                "dimensionsMeters": {
                    "width": round(abs(tmax[0] - tmin[0]), 6),
                    "height": round(abs(tmax[1] - tmin[1]), 6),
                    "depth": round(abs(tmax[2] - tmin[2]), 6),
                },
                "rotationY": float(source.get("rotationY", 0.0)),
            },
            "meshCount": len(objects),
            "geometrySource": "current-blender-native-measured-envelope",
        })
    return entities


def semantic_item(item: dict, native: dict) -> dict:
    height = float(item.get("height", 0.8))
    bottom = float(item.get("y", 0.0))
    return {
        "id": item["id"], "name": item.get("name", item["id"]), "kind": "furniture",
        "roomId": item.get("roomId", "unknown"), "roomIds": [item.get("roomId", "unknown")],
        "functionalClass": item.get("functionalClass", item.get("type", "unknown")),
        "semantic": item.get("semantic"), "componentId": item.get("componentId"),
        "placementWorld": {
            "center": {"x": float(item.get("x", 0)), "y": bottom + height / 2, "z": float(item.get("z", 0))},
            "dimensionsMeters": {
                "width": float(item.get("width", 0.6)), "height": height, "depth": float(item.get("depth", 0.6)),
            },
            "rotationY": float(item.get("rotationY", 0)),
            "frame": "source-local-oriented-footprint",
        },
        "world": native["world"],
    }


def build_semantic(model: dict, structure: dict, native: dict) -> dict:
    native_by_id = {item["id"]: item for item in native["entities"]}
    furniture = [semantic_item(item, native_by_id[item["id"]]) for item in model.get("furniture", [])]
    shots = []
    for sequence, room in enumerate(structure.get("rooms", []), 1):
        room_id = str(room["id"])
        inventory = [item for item in furniture if item["roomId"] == room_id]
        shots.append({
            "semanticInventory": inventory,
            "roomName": str(room.get("name", room_id)),
            "sequenceOrder": sequence,
            "roomId": room_id,
            "roomKind": str(room.get("spaceType", "unknown")),
            "expectedRoomElementIds": [item["id"] for item in inventory],
            "composition": "subject-facing-space-envelope-frontal",
            "anchorElementIds": [],
            "shotId": f"{sequence:02d}-{room_id}",
            "compositionIntent": "完整展示该空间主要功能主体与空间上下文",
        })
    return {
        "schema": "interior.semantic-room-facts.v1", "schemaVersion": "1.0",
        "floorplanId": structure.get("floorplanId"),
        "roomGeometry": [{
            "roomId": str(room["id"]), "roomName": room.get("name"),
            "roomKind": str(room.get("spaceType", "unknown")), "polygon": room.get("polygon", []),
        } for room in structure.get("rooms", [])],
        "shots": shots, "cameraFactsPresent": False,
    }


def main() -> int:
    args = parse_args()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    if scene.get("interiorModelBackend") != "blender":
        raise ValueError("current .blend is not an accepted interior Blender model")
    model = json.loads(scene["interiorCurrentModel"])
    structure = json.loads(scene["interiorStructureData"])
    entities = native_entities(model)
    native = {
        "schema": "interior.native-scene-geometry.v1", "schemaVersion": "1.0",
        "generation": {"method": "current-blender-native-gltf-export-v1", "imageRecognitionUsed": False},
        "entities": entities,
        "coverage": {
            "furnitureCount": len(model.get("furniture", [])),
            "wallCount": len(model.get("walls", [])), "openingCount": len(model.get("openings", [])),
            "roomCount": len(structure.get("rooms", [])),
        },
    }
    furniture_ids = {item["id"] for item in model.get("furniture", [])}
    native_furniture_ids = {item["id"] for item in entities if item["kind"] == "furniture"}
    if furniture_ids != native_furniture_ids:
        raise ValueError(f"Blender furniture/native mismatch: {sorted(furniture_ids ^ native_furniture_ids)}")
    model_path = out / "current-model-export.json"
    native_path = out / "native-scene-geometry.json"
    semantic_path = out / "semantic-room-facts.json"
    scene_path = out / "camera-semantic-scene.gltf"
    write(model_path, model)
    write(native_path, native)
    semantic = build_semantic(model, structure, native)
    write(semantic_path, semantic)

    selected_before = [obj for obj in bpy.context.selected_objects]
    names_before = {obj: obj.name for obj in bpy.context.scene.objects}
    bpy.ops.object.select_all(action="DESELECT")
    for entity_id, objects in renderable_groups().items():
        for index, obj in enumerate(objects, 1):
            obj.select_set(True)
            obj.name = f"camera-entity::{entity_id}::{index}"
    bpy.ops.export_scene.gltf(
        filepath=str(scene_path), export_format="GLTF_SEPARATE", export_yup=True,
        use_selection=True, export_cameras=False, export_lights=False,
    )
    for obj, name in names_before.items():
        obj.name = name
    bpy.ops.object.select_all(action="DESELECT")
    for obj in selected_before:
        obj.select_set(True)
    receipt = {
        "schema": "interior.camera-scene-generation-receipt.v1", "status": "complete",
        "downstreamReady": True, "modelBackend": "blender",
        "generator": "interior-blender-modeling/scripts/export_camera_scene.py",
        "nativeModel": {"path": bpy.data.filepath, "sha256": sha256(Path(bpy.data.filepath))},
        "currentModel": {"path": str(model_path), "sha256": sha256(model_path)},
        "structure": {"embeddedInBlend": True, "floorplanId": structure.get("floorplanId")},
        "scene": {"path": str(scene_path), "sha256": sha256(scene_path)},
        "nativeGeometry": {"path": str(native_path), "sha256": sha256(native_path)},
        "semanticFacts": {"path": str(semantic_path), "sha256": sha256(semantic_path)},
        "counts": {"rooms": len(structure.get("rooms", [])), "furniture": len(furniture_ids)},
    }
    write(out / "camera-scene-generation-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
