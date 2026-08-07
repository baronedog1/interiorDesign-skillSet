#!/usr/bin/env python3
"""Native Blender capture adapter for camera-plan.v8 shots."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blender_semantic_projection import compile_semantic_frame


RENDERABLE_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT"}


def canonical_to_blender(point):
    """Convert interior-world-y-up [east, up, south] to Blender Z-up."""
    if not isinstance(point, list) or len(point) != 3:
        raise ValueError("camera coordinates must be 3-number arrays")
    return Vector((float(point[0]), -float(point[2]), float(point[1])))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera-plan", required=True)
    parser.add_argument("--out", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def property_value(value):
    if isinstance(value, str) and value[:1] in {"[", "{"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def entity_objects(entity_id: str):
    return [obj for obj in bpy.data.objects if obj.get("interiorEntityId") == entity_id]


def renderable_bounds(objects) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type in RENDERABLE_TYPES and hasattr(obj, "bound_box")
        for corner in obj.bound_box
    ]
    if not points:
        raise RuntimeError("Blender entity has no renderable world bounds")
    return (
        Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points))),
        Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points))),
    )


def canonical_bounds(minimum: Vector, maximum: Vector) -> dict:
    return {
        "min": [round(minimum.x, 8), round(minimum.z, 8), round(-maximum.y, 8)],
        "max": [round(maximum.x, 8), round(maximum.z, 8), round(-minimum.y, 8)],
    }


def canonical_position(location: Vector) -> list[float]:
    return [round(location.x, 8), round(location.z, 8), round(-location.y, 8)]


def merged_metadata(objects) -> dict:
    ordered = sorted(objects, key=lambda obj: (obj.type in RENDERABLE_TYPES, obj.name))
    metadata = {}
    room_ids = []
    for obj in ordered:
        for key in obj.keys():
            if key.startswith("_") or key in {"interiorEntityId", "interiorEntityType"}:
                continue
            value = property_value(obj[key])
            if key in {"roomId", "roomIds", "adjacentRoomIds"}:
                values = value if isinstance(value, list) else [value]
                room_ids.extend(str(item) for item in values if item and item not in {"exterior", "outside", "outdoor"})
            elif key not in metadata:
                metadata[key] = value
    metadata["roomIds"] = sorted(set(room_ids))
    return metadata


def entity_row(entity_id: str, pass_index: int, objects) -> dict:
    renderables = [obj for obj in objects if obj.type in RENDERABLE_TYPES]
    minimum, maximum = renderable_bounds(renderables)
    bounds = canonical_bounds(minimum, maximum)
    metadata = merged_metadata(objects)
    root = next((obj for obj in objects if obj.get("interiorEntityType") == "component"), None)
    if root is None:
        center = Vector(((minimum.x + maximum.x) / 2, (minimum.y + maximum.y) / 2, (minimum.z + maximum.z) / 2))
        yaw = 0.0
        scale = [1, 1, 1]
    else:
        center = root.matrix_world.translation
        yaw = -float(root.rotation_euler.z)
        scale = [round(float(value), 8) for value in root.scale]
    entity_type = "component" if root is not None else renderables[0].get("interiorEntityType")
    dimensions = [round(bounds["max"][index] - bounds["min"][index], 8) for index in range(3)]
    return {
        "passIndex": pass_index,
        "entityId": entity_id,
        "entityType": entity_type,
        "semanticType": metadata.get("semanticType"),
        "category": metadata.get("category") or metadata.get("semanticType") or entity_type,
        "roomIds": metadata["roomIds"],
        "traceId": metadata.get("traceId"),
        "sourceObjectCandidateId": metadata.get("sourceObjectCandidateId"),
        "assetId": metadata.get("assetId"),
        "functionalClass": metadata.get("functionalClass"),
        "quantity": metadata.get("quantity"),
        "localAxes": metadata.get("localAxes") or {},
        "mustPreserve": bool(metadata.get("mustPreserve", False)),
        "worldBounds": bounds,
        "dimensionsMeters": dimensions,
        "worldTransform": {
            "position": canonical_position(center),
            "quaternion": [0, round(math.sin(yaw / 2), 10), 0, round(math.cos(yaw / 2), 10)],
            "scale": scale,
            "yawRadians": round(yaw, 10),
        },
    }


def set_visibility(hidden_ids, show_components):
    for obj in bpy.data.objects:
        entity_id = obj.get("interiorEntityId")
        entity_type = obj.get("interiorEntityType")
        hidden = entity_id in hidden_ids or (entity_type in {"component", "component-part"} and not show_components)
        obj.hide_render = hidden


def file_output(nodes, links, render_layers, socket_name: str, name: str, out: Path):
    socket = next((value for value in render_layers.outputs if value.name == socket_name), None)
    if socket is None:
        available = [value.name for value in render_layers.outputs]
        raise RuntimeError(f"required native {socket_name} pass is unavailable: {available}")
    output = nodes.new("CompositorNodeOutputFile")
    output.name = name
    output.base_path = str(out)
    output.format.file_format = "OPEN_EXR"
    output.format.color_mode = "RGB"
    output.format.color_depth = "32"
    output.format.exr_codec = "ZIP"
    links.new(socket, output.inputs[0])
    return output


def configure_native_passes(scene, out: Path):
    view_layer = scene.view_layers[0]
    view_layer.use_pass_z = True
    view_layer.use_pass_object_index = True
    groups = {}
    for obj in sorted(bpy.data.objects, key=lambda value: value.name):
        entity_id = obj.get("interiorEntityId")
        if entity_id and obj.type in RENDERABLE_TYPES:
            groups.setdefault(entity_id, entity_objects(entity_id))
    entity_rows = []
    for pass_index, entity_id in enumerate(sorted(groups), start=1):
        row = entity_row(entity_id, pass_index, groups[entity_id])
        entity_rows.append(row)
        for obj in groups[entity_id]:
            if obj.type in RENDERABLE_TYPES:
                obj.pass_index = pass_index
    scene.use_nodes = True
    nodes = scene.node_tree.nodes
    links = scene.node_tree.links
    nodes.clear()
    render_layers = nodes.new("CompositorNodeRLayers")
    depth_output = file_output(nodes, links, render_layers, "Depth", "InteriorDepthOutput", out)
    return depth_output, entity_rows


def render_semantic_pass(scene, out: Path, prefix: str) -> tuple[Path, Path]:
    old_engine = scene.render.engine
    old_samples = scene.cycles.samples
    nodes = scene.node_tree.nodes
    links = scene.node_tree.links
    nodes.clear()
    render_layers = nodes.new("CompositorNodeRLayers")
    depth_output = file_output(nodes, links, render_layers, "Depth", "InteriorSemanticDepthOutput", out)
    index_output = file_output(nodes, links, render_layers, "IndexOB", "InteriorSemanticObjectIndexOutput", out)
    depth_prefix = f"{prefix}.semantic-depth-"
    index_prefix = f"{prefix}.object-index-"
    depth_output.file_slots[0].path = depth_prefix
    index_output.file_slots[0].path = index_prefix
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    bpy.ops.render.render()
    depth_path = out / f"{prefix}.semantic-depth.exr"
    index_path = out / f"{prefix}.object-index.exr"
    finalize_pass(depth_output, depth_prefix, depth_path)
    finalize_pass(index_output, index_prefix, index_path)
    scene.render.engine = old_engine
    scene.cycles.samples = old_samples
    return depth_path, index_path


def furnished_qa_material():
    value = bpy.data.materials.get("M_NativeCapture_White") or bpy.data.materials.new("M_NativeCapture_White")
    value.diffuse_color = (0.78, 0.78, 0.76, 1)
    value.use_nodes = True
    bsdf = value.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = value.diffuse_color
    bsdf.inputs["Roughness"].default_value = 0.82
    bsdf.inputs["Metallic"].default_value = 0.0
    return value


def apply_furnished_qa_material(material):
    snapshots = {}
    for obj in bpy.data.objects:
        if obj.get("interiorEntityType") != "component-part" or not hasattr(obj.data, "materials"):
            continue
        snapshots[obj.name] = list(obj.data.materials)
        obj.data.materials.clear()
        obj.data.materials.append(material)
    return snapshots


def restore_component_materials(snapshots):
    for name, materials in snapshots.items():
        obj = bpy.data.objects.get(name)
        if obj is None or not hasattr(obj.data, "materials"):
            continue
        obj.data.materials.clear()
        for material in materials:
            if material is not None:
                obj.data.materials.append(material)


def finalize_pass(output_node, slot_prefix: str, destination: Path):
    candidates = sorted(destination.parent.glob(f"{slot_prefix}*.exr"))
    if not candidates:
        raise RuntimeError(f"Blender did not write native pass {slot_prefix}")
    candidates[-1].replace(destination)


def main() -> int:
    args = parse_args()
    plan = read(Path(args.camera_plan).resolve())
    if plan.get("schema") != "interior.camera-plan.v8" or plan.get("modelBackend") != "blender":
        raise ValueError("camera plan must be accepted Blender camera-plan.v8")
    if plan.get("coordinateSystem") != "interior-world-y-up.v1":
        raise ValueError("camera plan must use interior-world-y-up.v1")
    native_model = Path(bpy.data.filepath).resolve()
    if not native_model.is_file() or sha256(native_model) != plan.get("sourceModelSha256"):
        raise ValueError("opened .blend does not match camera-plan sourceModelSha256")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.frame_set(1)
    depth_output, entity_index = configure_native_passes(scene, out)
    neutral_material = furnished_qa_material()
    entity_index_path = out / "entity-index.json"
    directional_axes = []
    seen_asset_roles = set()
    for row in entity_index:
        if row.get("entityType") != "component":
            continue
        for role, local_axis in sorted((row.get("localAxes") or {}).items()):
            key = (row.get("assetId"), role)
            if key in seen_asset_roles:
                continue
            seen_asset_roles.add(key)
            directional_axes.append({
                "assetId": row["assetId"],
                "role": role,
                "localAxis": local_axis,
                "evidence": "blender-native-preview-reviewed-authored-model",
            })
    entity_index_path.write_text(json.dumps({
        "schema": "interior.blender-entity-index.v2",
        "sourceModelSha256": plan["sourceModelSha256"],
        "projectionProfile": "blender-native-object-index-depth-room-v1",
        "relationHints": {
            "schema": "interior.layout-relation-hints.v2",
            "directionalAxes": directional_axes,
            "facing": [],
            "wallAttachment": [],
        },
        "entities": entity_index,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    records = []
    for shot in plan.get("shots", []):
        camera_data = bpy.data.cameras.new(f"{shot['shotId']}-data")
        camera = bpy.data.objects.new(shot["shotId"], camera_data)
        bpy.data.collections["CAMERAS"].objects.link(camera)
        camera.location = canonical_to_blender(shot["position"])
        target = canonical_to_blender(shot["target"])
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera_data.lens = float(shot["focalLengthMm"])
        camera_data.sensor_width = 36
        camera_data.sensor_fit = "HORIZONTAL"
        camera_data.clip_start = 0.01
        camera_data.clip_end = 120
        camera_data.dof.use_dof = False
        scene.camera = camera
        hidden = set(shot.get("visibility", {}).get("hiddenElementIds", []))
        paths = {}
        semantic_projection = None
        for suffix, components, appearance in (("slot-guided", False, "concrete-shell"), ("furnished-qa", True, "concrete-shell")):
            if suffix == "slot-guided" and depth_output is None:
                depth_output, _ = configure_native_passes(scene, out)
            set_visibility(hidden, components)
            scene["interiorAppearance"] = appearance
            material_snapshot = apply_furnished_qa_material(neutral_material) if suffix == "furnished-qa" else {}
            image_path = out / f"{shot['shotId']}.{suffix}.png"
            depth_prefix = f"{shot['shotId']}.{suffix}.depth-"
            depth_output.file_slots[0].path = depth_prefix
            scene.render.filepath = str(image_path)
            bpy.ops.render.render(write_still=True)
            depth_path = out / f"{shot['shotId']}.{suffix}.depth.exr"
            finalize_pass(depth_output, depth_prefix, depth_path)
            paths[suffix] = str(image_path)
            paths[f"{suffix}-depth"] = str(depth_path)
            if suffix == "furnished-qa":
                semantic_depth_path, index_path = render_semantic_pass(scene, out, f"{shot['shotId']}.furnished-qa")
                paths["furnished-qa-semantic-depth"] = str(semantic_depth_path)
                paths["furnished-qa-object-index"] = str(index_path)
                semantic_projection = compile_semantic_frame(
                    plan=plan,
                    shot=shot,
                    camera=camera,
                    entity_index=entity_index,
                    slot_guided_image=Path(paths["slot-guided"]),
                    furnished_qa_image=image_path,
                    depth_path=semantic_depth_path,
                    index_path=index_path,
                    out=out,
                )
                depth_output = None
            restore_component_materials(material_snapshot)
        if semantic_projection is None:
            raise RuntimeError(f"{shot['shotId']}: semantic projection was not compiled")
        records.append({
            "shotId": shot["shotId"],
            "cameraObject": camera.name,
            "canonicalCamera": {"position": shot["position"], "target": shot["target"]},
            "nativeCamera": {"position": list(camera.location), "target": list(target)},
            "images": paths,
            "nativeRaycastSource": "blender-depsgraph",
            "semanticProjection": semantic_projection,
        })
    manifest = {
        "schema": "interior.native-capture-result.v1",
        "modelBackend": "blender",
        "sourceModelSha256": plan["sourceModelSha256"],
        "coordinateSystem": "interior-world-y-up.v1",
        "accepted": True,
        "projectionProfile": "blender-native-object-index-depth-room-v1",
        "projectionEvidenceAccepted": all(record["semanticProjection"]["visibleRoomCount"] > 0 for record in records),
        "entityIndex": str(entity_index_path),
        "records": records,
    }
    (out / "capture-result.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
