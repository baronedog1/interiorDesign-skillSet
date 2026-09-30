#!/usr/bin/env python3
"""Render the common frozen v3 camera plan directly from the accepted .blend."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera-plan", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--viewport", default="1600x1000")
    parser.add_argument("--sequence", type=int)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        signature = stream.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", signature[16:24])


def safe_stem(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value).strip("-") or "shot"


def to_blender(point) -> Vector:
    return Vector((float(point[0]), -float(point[2]), float(point[1])))


def entity_objects(entity_id: str):
    return [obj for obj in bpy.context.scene.objects if str(obj.get("interiorEntityId", "")) == entity_id]


def set_visibility(hidden_ids: set[str]) -> dict:
    states = {}
    for obj in bpy.context.scene.objects:
        if obj.type in {"CAMERA", "LIGHT"}:
            continue
        states[obj.name] = obj.hide_render
        entity_id = str(obj.get("interiorEntityId", ""))
        obj.hide_render = entity_id in hidden_ids
    return states


def restore_visibility(states: dict) -> None:
    for name, hidden in states.items():
        obj = bpy.data.objects.get(name)
        if obj:
            obj.hide_render = hidden


def ensure_camera():
    collection = bpy.data.collections.get("CAMERAS")
    if not collection:
        raise ValueError("accepted Blender scene lacks CAMERAS collection")
    camera = bpy.data.objects.get("algorithmic-camera")
    if not camera:
        data = bpy.data.cameras.new("algorithmic-camera-data")
        camera = bpy.data.objects.new("algorithmic-camera", data)
        collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def configure_camera(camera, shot: dict, aspect: float) -> None:
    position, target = to_blender(shot["position"]), to_blender(shot["target"])
    camera.location = position
    camera.rotation_euler = (target - position).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "PERSP"
    camera.data.sensor_fit = "VERTICAL"
    camera.data.angle_y = math.radians(float(shot["fov"]))
    # With a vertical sensor fit Blender's projection matrix terms are:
    # P[0][2] = 2 * shift_x / aspect and P[1][2] = 2 * shift_y.
    # Three.js stores the frozen VTK window center directly in these terms.
    camera.data.shift_x = float((shot.get("windowCenter") or [0, 0])[0]) * aspect / 2
    camera.data.shift_y = float((shot.get("windowCenter") or [0, 0])[1]) / 2
    camera.data.clip_start = 0.03
    camera.data.clip_end = 500


def ensure_camera_fill(camera, shot: dict):
    collection = bpy.data.collections.get("LIGHTS")
    if not collection:
        raise ValueError("accepted Blender scene lacks LIGHTS collection")
    light = bpy.data.objects.get("algorithmic-camera-fill")
    if not light:
        data = bpy.data.lights.new("algorithmic-camera-fill-data", "AREA")
        data.shape = "DISK"
        data.size = 3.0
        light = bpy.data.objects.new("algorithmic-camera-fill", data)
        collection.objects.link(light)
    target = to_blender(shot["target"])
    direction = (target - camera.location).normalized()
    light.location = camera.location + direction * 0.35 + Vector((0, 0, 0.25))
    light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()
    style = json.loads(str(bpy.context.scene.get("interiorStylePreset", "{}")))
    light.data.energy = float(style.get("render", {}).get("cameraFillEnergy", 520))
    light.hide_render = False
    return light


def ensure_room_light(shot: dict):
    collection = bpy.data.collections.get("LIGHTS")
    light = bpy.data.objects.get("algorithmic-room-key")
    if not light:
        data = bpy.data.lights.new("algorithmic-room-key-data", "AREA")
        data.shape = "DISK"
        data.size = 3.2
        light = bpy.data.objects.new("algorithmic-room-key", data)
        collection.objects.link(light)
    target = to_blender(shot["target"])
    light.location = (target.x, target.y, max(2.55, target.z + 1.1))
    light.rotation_euler = (0, 0, 0)
    style = json.loads(str(bpy.context.scene.get("interiorStylePreset", "{}")))
    light.data.energy = float(style.get("render", {}).get("roomKeyEnergy", 300))
    light.hide_render = False
    return light


def component_identity(obj) -> tuple[str, str]:
    current = obj
    while current is not None:
        entity_id = str(current.get("interiorEntityId", ""))
        room_id = str(current.get("roomId", ""))
        if entity_id and room_id:
            return entity_id, room_id
        current = current.parent
    return "", ""


def prune_scene_for_shot(shot: dict) -> dict:
    """Remove foreign-room asset datablocks before Eevee allocates textures."""
    target_room = str(shot["roomId"])
    keep_ids = set(shot.get("primarySubjectElementIds", [])) | set(shot.get("framingElementIds", []))
    removed_objects = 0
    furniture = bpy.data.collections.get("FURNITURE")
    for obj in list(furniture.all_objects if furniture else []):
        entity_id, room_id = component_identity(obj)
        if room_id and room_id != target_room and entity_id not in keep_ids:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed_objects += 1
    floors = bpy.data.collections.get("FLOORS")
    for obj in list(floors.all_objects if floors else []):
        room_id = str(obj.get("roomId", ""))
        if room_id and room_id != target_room:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed_objects += 1
    purge_rounds = 0
    for _ in range(4):
        removed = bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        purge_rounds += 1
        if removed == 0:
            break
    bpy.context.view_layer.update()
    return {
        "policy": "target-room-assets-only-v1", "targetRoomId": target_room,
        "removedObjects": removed_objects, "purgeRounds": purge_rounds,
        "foreignFurnitureRendered": False,
    }


def configure_crop(scene, crop: dict | None) -> dict:
    normalized = crop or {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0, "source": "none"}
    left = max(0.0, min(1.0, float(normalized.get("left", 0))))
    top = max(0.0, min(1.0, float(normalized.get("top", 0))))
    right = max(left + 0.001, min(1.0, float(normalized.get("right", 1))))
    bottom = max(top + 0.001, min(1.0, float(normalized.get("bottom", 1))))
    active = left > 0.0001 or top > 0.0001 or right < 0.9999 or bottom < 0.9999
    scene.render.use_border = active
    scene.render.use_crop_to_border = active
    scene.render.border_min_x = left
    scene.render.border_max_x = right
    scene.render.border_min_y = 1.0 - bottom
    scene.render.border_max_y = 1.0 - top
    return {"left": left, "top": top, "right": right, "bottom": bottom, "source": normalized.get("source")}


def main() -> int:
    args = parse_args()
    plan_path = Path(args.camera_plan).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = read(plan_path)
    if plan.get("schema") != "interior.algorithmic-camera-plan.v3":
        raise ValueError("Blender capture requires interior.algorithmic-camera-plan.v3")
    scene = bpy.context.scene
    if scene.get("interiorModelBackend") != "blender":
        raise ValueError("current file is not an accepted interior Blender model")
    if str(plan.get("floorplanId")) != str(scene.get("interiorFloorplanId")):
        raise ValueError("camera plan and Blender model floorplan identities differ")
    width, height = [int(value) for value in args.viewport.lower().split("x", 1)]
    style = json.loads(str(scene.get("interiorStylePreset", "{}")))
    render = style.get("render", {})
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = int(render.get("samples", 16))
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.exposure = float(render.get("exposure", 0.7))
    try:
        scene.view_settings.look = render.get("look", "AgX - Medium High Contrast")
    except TypeError:
        pass
    camera = ensure_camera()
    blend_path = Path(bpy.data.filepath)
    blend_sha = sha256(blend_path)
    shots = sorted(plan.get("shots", []), key=lambda item: int(item.get("sequenceOrder", 0)))
    if args.sequence is not None:
        shots = [shot for shot in shots if int(shot.get("sequenceOrder", 0)) == args.sequence]
        if not shots:
            raise ValueError(f"camera plan has no sequence {args.sequence}")
    if len(shots) != 1:
        raise ValueError("material Blender capture requires one isolated process per shot")
    records = []
    for shot in shots:
        sequence = int(shot.get("sequenceOrder", len(records) + 1))
        stem = f"{sequence:02d}-{safe_stem(str(shot.get('roomName') or shot.get('roomId')))}"
        image_path = out / f"{stem}.png"
        facts_path = out / f"{stem}.json"
        hidden = set(shot.get("hiddenWallIds", [])) | set(shot.get("hiddenOpeningIds", [])) | set(shot.get("hiddenElementIds", []))
        pruning = prune_scene_for_shot(shot)
        visibility = set_visibility(hidden)
        try:
            configure_camera(camera, shot, width / height)
            ensure_camera_fill(camera, shot)
            ensure_room_light(shot)
            crop = configure_crop(scene, (shot.get("targetSpacePolicy") or {}).get("projectionCrop"))
            scene.render.filepath = str(image_path)
            started = time.perf_counter()
            bpy.ops.render.render(write_still=True)
            elapsed = round(time.perf_counter() - started, 3)
        finally:
            restore_visibility(visibility)
        if not image_path.is_file() or image_path.stat().st_size == 0:
            raise ValueError(f"Blender render missing: {image_path}")
        final_width, final_height = png_size(image_path)
        projection = camera.calc_matrix_camera(
            bpy.context.evaluated_depsgraph_get(), x=width, y=height, scale_x=1, scale_y=1
        )
        facts = {
            "schema": "interior.camera-image-facts.v3", "schemaVersion": "3.0",
            "modelBackend": "blender", "shotId": shot["shotId"], "roomId": shot["roomId"],
            "sourceModel": {"path": str(blend_path), "sha256": blend_sha},
            "cameraPlan": {"path": str(plan_path), "sha256": sha256(plan_path)},
            "camera": {
                "position": shot["position"], "target": shot["target"], "fov": shot["fov"],
                "windowCenter": shot.get("windowCenter", [0, 0]),
                "projectionCenter": [round(float(projection[0][2]), 6), round(float(projection[1][2]), 6)],
            },
            "projectionCrop": crop,
            "hiddenElementIds": sorted(hidden),
            "primarySubjectElementIds": shot.get("primarySubjectElementIds", []),
            "framingElementIds": shot.get("framingElementIds", []),
            "semanticInventory": shot.get("semanticInventory", []),
            "targetSpacePolicy": shot.get("targetSpacePolicy", {}),
            "image": {
                "path": str(image_path), "sha256": sha256(image_path), "bytes": image_path.stat().st_size,
                "width": final_width, "height": final_height,
            },
            "render": {"engine": scene.render.engine, "samples": int(render.get("samples", 16)), "seconds": elapsed, "imageRecognitionUsed": False, "pruning": pruning},
            "deliveryBlocked": False,
        }
        write(facts_path, facts)
        records.append({"shotId": shot["shotId"], "roomId": shot["roomId"], "ok": True, "image": str(image_path), "facts": str(facts_path)})
        print(f"[{sequence}/{len(plan.get('shots', []))}] {shot.get('roomName', shot['roomId'])}: ok")
    index = {
        "schema": "interior.camera-delivery-index.v1", "modelBackend": "blender",
        "sourceModelSha256": blend_sha, "records": records,
        "summary": {"requested": len(plan.get("shots", [])), "delivered": len(records), "failed": 0, "deliveryBlocked": False},
    }
    write(out / "camera-delivery-index.json", index)
    print(json.dumps(index["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
