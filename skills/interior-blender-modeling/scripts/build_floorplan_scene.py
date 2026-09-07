#!/usr/bin/env python3
"""Compile HTML structure and furniture facts with Blender-native precision assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


COLLECTIONS = (
    "STRUCTURE", "OPENINGS", "FLOORS", "CEILINGS", "FURNITURE",
    "LIGHTS", "CAMERAS", "ANNOTATIONS",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--blender-catalog", required=True)
    parser.add_argument("--material-catalog", required=True)
    parser.add_argument("--style-preset", required=True)
    parser.add_argument("--backend-options", required=True)
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--out-glb", required=True)
    parser.add_argument("--out-report", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tag(obj, entity_id: str, entity_type: str, **fields) -> None:
    obj["interiorEntityId"] = entity_id
    obj["interiorEntityType"] = entity_type
    for key, value in fields.items():
        obj[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value


def material(name: str, rgba: tuple[float, float, float, float], roughness: float, metallic: float = 0.0):
    value = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    value.diffuse_color = rgba
    value.use_nodes = True
    bsdf = value.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if rgba[3] < 1:
        bsdf.inputs["Alpha"].default_value = rgba[3]
        value.surface_render_method = "DITHERED"
    return value


def pbr_material(name: str, template: dict, material_catalog: dict):
    entries = {entry["materialId"]: entry for entry in material_catalog.get("materials", [])}
    entry = entries.get(template.get("materialId"))
    if not entry:
        raise ValueError(f"material template is missing from catalog: {template.get('materialId')}")
    asset_root = Path(material_catalog["assetRoot"])
    loaded = {}
    for role in ("diffuse", "roughness", "normal"):
        map_entry = entry.get("maps", {}).get(role)
        if not map_entry:
            raise ValueError(f"{entry['materialId']}: required PBR map missing: {role}")
        path = asset_root / map_entry["path"]
        if not path.is_file() or sha256(path) != map_entry["sha256"]:
            raise ValueError(f"{entry['materialId']}: PBR map missing or changed: {role}")
        image = bpy.data.images.load(str(path), check_existing=True)
        if role != "diffuse":
            image.colorspace_settings.name = "Non-Color"
        loaded[role] = image

    tint = tuple(template.get("tint", [1, 1, 1, 1]))
    value = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    value.diffuse_color = tint
    value.use_nodes = True
    nodes, links = value.node_tree.nodes, value.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    physical_width = max(0.05, float(entry.get("physicalWidthMeters", 1.0)))
    mapping.inputs["Scale"].default_value = (1.0 / physical_width, 1.0 / physical_width, 1.0 / physical_width)
    mapping.inputs["Rotation"].default_value[2] = math.radians(float(template.get("mappingRotationDegrees", 0)))
    links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])

    diffuse = nodes.new("ShaderNodeTexImage")
    diffuse.image = loaded["diffuse"]
    diffuse.projection = "BOX"
    diffuse.projection_blend = 0.20
    tint_node = nodes.new("ShaderNodeMixRGB")
    tint_node.blend_type = str(template.get("tintMode", "MULTIPLY"))
    tint_node.inputs[0].default_value = float(template.get("tintStrength", 1.0))
    tint_node.inputs[2].default_value = tint
    links.new(mapping.outputs["Vector"], diffuse.inputs["Vector"])
    links.new(diffuse.outputs["Color"], tint_node.inputs[1])
    links.new(tint_node.outputs["Color"], bsdf.inputs["Base Color"])

    roughness = nodes.new("ShaderNodeTexImage")
    roughness.image = loaded["roughness"]
    roughness.projection = "BOX"
    roughness.projection_blend = 0.20
    roughness_math = nodes.new("ShaderNodeMath")
    roughness_math.operation = "MULTIPLY"
    roughness_math.use_clamp = True
    roughness_math.inputs[1].default_value = float(template.get("roughnessMultiplier", 1.0))
    links.new(mapping.outputs["Vector"], roughness.inputs["Vector"])
    links.new(roughness.outputs["Color"], roughness_math.inputs[0])
    links.new(roughness_math.outputs["Value"], bsdf.inputs["Roughness"])

    normal = nodes.new("ShaderNodeTexImage")
    normal.image = loaded["normal"]
    normal.projection = "BOX"
    normal.projection_blend = 0.20
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = float(template.get("normalStrength", 0.3))
    bump.inputs["Distance"].default_value = float(template.get("bumpDistance", 0.025))
    links.new(mapping.outputs["Vector"], normal.inputs["Vector"])
    links.new(normal.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    value["interiorMaterialId"] = entry["materialId"]
    value["interiorMaterialSource"] = entry.get("sourcePage", "")
    value["interiorMaterialLicense"] = entry.get("license", "")
    return value


def relink(obj, collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def box(name, location, dimensions, rotation_z, mat, collection, entity_id, entity_type, **fields):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0, 0, rotation_z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    relink(obj, collection)
    tag(obj, entity_id, entity_type, **fields)
    return obj


def polygon_prism(name, points, z0, height, mat, collection, entity_id, entity_type, **fields):
    verts = [(x, y, z0) for x, y in points] + [(x, y, z0 + height) for x, y in points]
    count = len(points)
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(f"{name}-mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(mat)
    tag(obj, entity_id, entity_type, **fields)
    return obj


def to_blender_plan(point) -> tuple[float, float]:
    return float(point[0]), -float(point[1])


def wall_basis(wall: dict) -> tuple[Vector, Vector, float]:
    start = Vector((float(wall["a"]["x"]), float(wall["a"]["z"])))
    end = Vector((float(wall["b"]["x"]), float(wall["b"]["z"])))
    delta = end - start
    length = max(delta.length, 1e-9)
    return start, delta / length, length


def wall_piece(wall, left, right, z0, z1, suffix, mat, collection):
    start, direction, _ = wall_basis(wall)
    a = start + direction * left
    b = start + direction * right
    ax, ay = to_blender_plan(a)
    bx, by = to_blender_plan(b)
    length = max(math.hypot(bx - ax, by - ay), 0.001)
    angle = math.atan2(by - ay, bx - ax)
    return box(
        f"{wall['id']}::{suffix}", ((ax + bx) / 2, (ay + by) / 2, (z0 + z1) / 2),
        (length, float(wall.get("thickness", 0.16)), z1 - z0), angle, mat, collection,
        wall["id"], "wall-piece", adjacentRoomIds=wall.get("adjacentRoomIds", []),
    )


def build_walls(model: dict, mat, collection) -> int:
    openings = model.get("openings", [])
    count = 0
    for wall in model.get("walls", []):
        _, _, length = wall_basis(wall)
        hosted = [opening for opening in openings if opening.get("wallId") == wall["id"]]
        cuts = {0.0, length}
        for opening in hosted:
            center = float(opening.get("center", 0))
            width = float(opening.get("width", 0))
            cuts.add(max(0.0, center - width / 2))
            cuts.add(min(length, center + width / 2))
        ordered = sorted(cuts)
        height = float(wall.get("height", model.get("settings", {}).get("wallHeight", 2.8)))
        for index, (left, right) in enumerate(zip(ordered, ordered[1:])):
            if right - left < 0.005:
                continue
            midpoint = (left + right) / 2
            active = [
                opening for opening in hosted
                if float(opening.get("center", 0)) - float(opening.get("width", 0)) / 2 < midpoint
                < float(opening.get("center", 0)) + float(opening.get("width", 0)) / 2
            ]
            if not active:
                wall_piece(wall, left, right, 0, height, f"full-{index}", mat, collection)
                count += 1
                continue
            vertical = {0.0, height}
            for opening in active:
                bottom = float(opening.get("bottom", 0))
                vertical.add(max(0.0, bottom))
                vertical.add(min(height, bottom + float(opening.get("height", 2.1))))
            levels = sorted(vertical)
            for level_index, (low, high) in enumerate(zip(levels, levels[1:])):
                middle = (low + high) / 2
                if any(
                    float(opening.get("bottom", 0)) < middle
                    < float(opening.get("bottom", 0)) + float(opening.get("height", 2.1))
                    for opening in active
                ):
                    continue
                if high - low >= 0.005:
                    wall_piece(wall, left, right, low, high, f"split-{index}-{level_index}", mat, collection)
                    count += 1
    return count


def build_openings(model: dict, mats: dict, collection) -> int:
    walls = {wall["id"]: wall for wall in model.get("walls", [])}
    count = 0
    for opening in model.get("openings", []):
        wall = walls.get(opening.get("wallId"))
        if not wall:
            continue
        start, direction, _ = wall_basis(wall)
        center = start + direction * float(opening.get("center", 0))
        x, y = to_blender_plan(center)
        dx, dy = to_blender_plan(direction)
        angle = math.atan2(dy, dx)
        width = float(opening.get("width", 0.8))
        height = float(opening.get("height", 2.1))
        bottom = float(opening.get("bottom", 0))
        root = bpy.data.objects.new(opening["id"], None)
        collection.objects.link(root)
        root.location = (x, y, bottom + height / 2)
        root.rotation_euler.z = angle
        tag(root, opening["id"], "opening", hostWallId=opening.get("wallId"), openingType=opening.get("type"))
        frame = min(0.06, width * 0.08)
        depth = max(0.04, float(wall.get("thickness", 0.16)) * 0.55)

        def child(suffix, location, dimensions, mat):
            value = box(
                f"{opening['id']}::{suffix}", (0, 0, 0), dimensions, 0, mat, collection,
                opening["id"], "opening-part", hostWallId=opening.get("wallId"), part=suffix,
            )
            value.parent = root
            value.location = location
            return value

        child("left", (-width / 2 + frame / 2, 0, 0), (frame, depth, height), mats["frame"])
        child("right", (width / 2 - frame / 2, 0, 0), (frame, depth, height), mats["frame"])
        child("top", (0, 0, height / 2 - frame / 2), (width, depth, frame), mats["frame"])
        if opening.get("type") == "window":
            child("bottom", (0, 0, -height / 2 + frame / 2), (width, depth, frame), mats["frame"])
            child("glass", (0, 0, 0), (max(0.05, width - frame * 2), 0.018, max(0.05, height - frame * 2)), mats["glass"])
        elif opening.get("type") == "sliding":
            leaf_width = max(0.05, width / 2 - frame)
            child("leaf-a", (-width / 4, -0.018, -frame / 2), (leaf_width, 0.025, height - frame), mats["door"])
            child("leaf-b", (width / 4, 0.018, -frame / 2), (leaf_width, 0.025, height - frame), mats["door"])
        elif opening.get("type") != "passage":
            child("leaf", (0, 0, -frame / 2), (width - frame * 2, 0.035, height - frame), mats["door"])
        count += 1
    return count


def load_blend_prototypes(asset_path: Path):
    with bpy.data.libraries.load(str(asset_path), link=False) as (source, target):
        target.objects = list(source.objects)
    imported = [obj for obj in target.objects if obj]
    for obj in list(imported):
        if obj.type in {"CAMERA", "LIGHT", "SPEAKER"}:
            bpy.data.objects.remove(obj, do_unlink=True)
            imported.remove(obj)
            continue
    geometry = [obj for obj in imported if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}]
    if not geometry:
        raise ValueError(f"asset imported no renderable geometry: {asset_path}")
    return imported


def instantiate_blend(prototypes, collection):
    """Instance exact asset geometry while sharing mesh, material and image data."""
    copies = {prototype: prototype.copy() for prototype in prototypes}
    for prototype, obj in copies.items():
        obj.parent = copies.get(prototype.parent)
        obj.hide_viewport = False
        obj.hide_render = False
        collection.objects.link(obj)
    imported = list(copies.values())
    geometry = [obj for obj in imported if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}]
    return imported, geometry


def world_bounds(objects):
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return minimum, maximum


def nearest_wall(item: dict, walls: list[dict]):
    px, pz = float(item["x"]), float(item["z"])
    best = None
    for wall in walls:
        ax, az = float(wall["a"]["x"]), float(wall["a"]["z"]); bx, bz = float(wall["b"]["x"]), float(wall["b"]["z"])
        dx, dz = bx - ax, bz - az; length2 = dx * dx + dz * dz
        t = 0 if length2 <= 1e-9 else max(0, min(1, ((px - ax) * dx + (pz - az) * dz) / length2))
        qx, qz = ax + t * dx, az + t * dz; distance = math.hypot(qx - px, qz - pz)
        if best is None or distance < best[0]: best = (distance, wall, qx, qz)
    return best


def orientation_for(item: dict, asset: dict, model: dict):
    mode = asset.get("orientationMode", "source-yaw")
    target_id = None; wall_id = None
    if mode in {"back-to-nearest-wall", "headboard-to-nearest-wall"}:
        found = nearest_wall(item, model.get("walls", []))
        if found:
            _, wall, qx, qz = found; wall_id = wall["id"]
            dx = float(wall["b"]["x"]) - float(wall["a"]["x"])
            dy = -(float(wall["b"]["z"]) - float(wall["a"]["z"]))
            length = max(math.hypot(dx, dy), 1e-9)
            tangent = Vector((dx / length, dy / length))
            normals = (Vector((-tangent.y, tangent.x)), Vector((tangent.y, -tangent.x)))
            to_wall = Vector((qx - float(item["x"]), -(qz - float(item["z"]))))
            back = max(normals, key=lambda normal: normal.dot(to_wall))
            rotation = math.atan2(-back.x, back.y)
            return rotation, mode, wall_id, target_id
    target_classes = {"face-nearest-dining-table": {"dining-table"}, "face-nearest-desk": {"desk"}, "face-room-anchor": {"coffee-table", "dining-table", "desk"}}
    if mode in target_classes:
        candidates = [other for other in model.get("furniture", []) if other.get("roomId") == item.get("roomId") and other.get("functionalClass") in target_classes[mode] and other.get("id") != item.get("id")]
        if candidates:
            target = min(candidates, key=lambda other: math.hypot(float(other["x"]) - float(item["x"]), float(other["z"]) - float(item["z"])))
            target_id = target["id"]
            front_angle = math.atan2(-(float(target["z"]) - float(item["z"])), float(target["x"]) - float(item["x"]))
            return front_angle + math.pi / 2, mode, wall_id, target_id
    return float(item.get("rotationY", 0)), "source-yaw", wall_id, target_id


def room_style_tags(room_id: str, style: dict) -> set[str]:
    selection = style.get("assetSelection", {})
    room_tags = selection.get("roomTags", {})
    if room_id in room_tags:
        return set(room_tags[room_id])
    lowered = room_id.lower()
    for key, tags in room_tags.items():
        if key in lowered:
            return set(tags)
    return set(selection.get("defaultTags", []))


def choose_asset(item: dict, candidates: list[dict], style: dict) -> tuple[dict, dict]:
    room_id = str(item.get("roomId", ""))
    allowed = [asset for asset in candidates if not asset.get("roomIds") or room_id in asset.get("roomIds", [])]
    candidates = allowed or candidates
    requested = room_style_tags(room_id, style)
    ranked = []
    for asset in candidates:
        tags = set(asset.get("styleTags", []))
        overlap = sorted(requested & tags)
        ranked.append((len(overlap), int(asset.get("priority", 0)), asset, overlap))
    best_score = max((value[0], value[1]) for value in ranked)
    tied = sorted(
        [value for value in ranked if (value[0], value[1]) == best_score],
        key=lambda value: value[2]["assetId"],
    )
    digest = hashlib.sha256(f"{item.get('roomId')}::{item.get('functionalClass')}".encode()).digest()
    chosen = tied[int.from_bytes(digest[:4], "big") % len(tied)]
    return chosen[2], {
        "policy": "room-style-score-v1", "requestedTags": sorted(requested),
        "matchedTags": chosen[3], "score": chosen[0], "candidateCount": len(candidates),
    }


def build_furniture(model: dict, catalog: dict, style: dict, collection) -> list[dict]:
    assets = {}
    for asset in catalog.get("assets", []):
        if asset.get("selectionStatus", "accepted") != "accepted":
            continue
        for functional_class in asset.get("functionalClasses", []):
            assets.setdefault(functional_class, []).append(asset)
    asset_root = Path(catalog["assetRoot"])
    prototype_cache = {}
    records = []
    for item in model.get("furniture", []):
        candidates = assets.get(item.get("functionalClass"), [])
        if not candidates:
            raise ValueError(f"{item['id']}: Blender precision catalog misses {item.get('functionalClass')}")
        asset, selection = choose_asset(item, candidates, style)
        asset_path = asset_root / asset["path"]
        if not asset_path.is_file() or sha256(asset_path) != asset["sha256"]:
            raise ValueError(f"{item['id']}: Blender precision asset missing or changed")
        root = bpy.data.objects.new(item["id"], None)
        collection.objects.link(root)
        frame = bpy.data.objects.new(f"{item['id']}::asset-frame", None)
        collection.objects.link(frame)
        frame.parent = root
        cache_key = str(asset_path)
        if cache_key not in prototype_cache:
            prototype_cache[cache_key] = load_blend_prototypes(asset_path)
        imported, geometry = instantiate_blend(prototype_cache[cache_key], collection)
        imported_set = set(imported)
        for obj in imported:
            if obj.parent not in imported_set:
                obj.parent = frame
            if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
                tag(
                    obj, item["id"], "component-part", componentId=asset["assetId"],
                    roomId=item.get("roomId"), functionalClass=item.get("functionalClass"),
                    semantic=item.get("semantic"), sourceTraceId=item.get("sourceTraceId"),
                )
        pre_rotation = [math.radians(float(value)) for value in asset.get("preRotationEulerDegrees", [0, 0, 0])]
        frame.rotation_euler = pre_rotation
        bpy.context.view_layer.update()
        minimum, maximum = world_bounds(geometry)
        size = maximum - minimum
        target = Vector((float(item["width"]), float(item["depth"]), float(item["height"])))
        if min(size) <= 1e-7 or min(target) <= 0:
            raise ValueError(f"{item['id']}: invalid source or target dimensions")
        ratios = (target.x / size.x, target.y / size.y, target.z / size.z)
        if asset.get("scalePolicy") != "exact-dimensions":
            raise ValueError(f"{item['id']}: Blender asset must declare exact-dimensions scaling")
        frame.scale = ratios
        resolved_rotation, orientation_mode, wall_id, target_id = orientation_for(item, asset, model)
        root.rotation_euler.z = resolved_rotation
        root.location = (float(item["x"]), -float(item["z"]), float(item.get("y", 0)))
        bpy.context.view_layer.update()
        placed_minimum, placed_maximum = world_bounds(geometry)
        desired = Vector((float(item["x"]), -float(item["z"]), float(item.get("y", 0))))
        center = (placed_minimum + placed_maximum) / 2
        root.location.x += desired.x - center.x
        root.location.y += desired.y - center.y
        root.location.z += desired.z - placed_minimum.z + float(item.get("richComponent", {}).get("elevation", 0))
        bpy.context.view_layer.update()
        placed_minimum, placed_maximum = world_bounds(geometry)
        tag(
            root, item["id"], "component", componentId=asset["assetId"], roomId=item.get("roomId"),
            functionalClass=item.get("functionalClass"), semantic=item.get("semantic"),
            sourceTraceId=item.get("sourceTraceId"), assetSha256=asset["sha256"], sourceComponentId=item.get("componentId"),
            sourceModelDimensions={"width": item["width"], "depth": item["depth"], "height": item["height"]},
            frontAxisLocal=asset.get("frontAxis", "-Y"), orientationMode=orientation_mode,
            preferredWallId=wall_id or "", orientationTargetId=target_id or "",
            sourceRotationY=float(item.get("rotationY", 0)), resolvedRotationRadians=resolved_rotation,
            assetSelection=selection, assetStyleTags=asset.get("styleTags", []),
            sourceUpAxis=asset.get("sourceUpAxis", "Z"), preRotationEulerDegrees=asset.get("preRotationEulerDegrees", [0, 0, 0]),
        )
        root["interiorCollisionGuard"] = True
        records.append({
            "id": item["id"], "componentId": asset["assetId"], "roomId": item.get("roomId"),
            "functionalClass": item.get("functionalClass"), "meshCount": len(geometry),
            "assetSelection": selection, "assetStyleTags": asset.get("styleTags", []),
            "sourceUpAxis": asset.get("sourceUpAxis", "Z"), "preRotationEulerDegrees": asset.get("preRotationEulerDegrees", [0, 0, 0]),
            "orientation": {"mode": orientation_mode, "preferredWallId": wall_id, "targetId": target_id, "sourceRotationY": item.get("rotationY", 0), "resolvedRotationRadians": resolved_rotation, "frontAxisLocal": asset.get("frontAxis", "-Y")},
            "boundsBlender": {
                "minimum": [round(value, 6) for value in placed_minimum],
                "maximum": [round(value, 6) for value in placed_maximum],
            },
        })
    for prototypes in prototype_cache.values():
        for prototype in prototypes:
            bpy.data.objects.remove(prototype, do_unlink=True)
    return records


def configure_render(scene, style: dict) -> None:
    render = style.get("render", {})
    scene.render.engine = render.get("engine", "BLENDER_EEVEE_NEXT")
    resolution = render.get("resolution", [960, 600])
    scene.render.resolution_x, scene.render.resolution_y = [int(value) for value in resolution]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = bool(render.get("transparent", False))
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = int(render.get("samples", 16))
    if scene.world is None:
        scene.world = bpy.data.worlds.new("InteriorWorld")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.12, 0.14, 0.17, 1)
    background.inputs["Strength"].default_value = float(render.get("ambientStrength", 0.32))
    scene.view_settings.exposure = float(render.get("exposure", 0.0))
    try:
        scene.view_settings.look = render.get("look", "AgX - Medium High Contrast")
    except TypeError:
        pass


def normalize_texture_memory(max_dimension: int) -> dict:
    """Bound render memory without changing geometry or material assignments."""
    changed = []
    for image in list(bpy.data.images):
        width, height = [int(value) for value in image.size]
        if width <= 0 or height <= 0 or max(width, height) <= max_dimension:
            continue
        factor = max_dimension / max(width, height)
        target_width = max(1, round(width * factor))
        target_height = max(1, round(height * factor))
        image.scale(target_width, target_height)
        try:
            image.pack()
        except RuntimeError:
            pass
        changed.append({"name": image.name, "source": [width, height], "runtime": [target_width, target_height]})
    return {"maxDimension": max_dimension, "resizedCount": len(changed), "images": changed}


def add_lighting(collections, center: Vector, span: float, style: dict) -> None:
    render = style.get("render", {})
    sun_data = bpy.data.lights.new("inspection-sun-data", "SUN")
    sun_data.energy = 0.85
    sun = bpy.data.objects.new("inspection-sun", sun_data)
    sun.rotation_euler = (math.radians(35), 0, math.radians(-30))
    collections["LIGHTS"].objects.link(sun)
    fill_data = bpy.data.lights.new("inspection-fill-data", "AREA")
    fill_data.energy = max(float(render.get("cameraFillEnergy", 520)) * 1.4, span * 70)
    fill_data.shape = "DISK"
    fill_data.size = max(4, span * 0.8)
    fill = bpy.data.objects.new("inspection-fill", fill_data)
    fill.location = (center.x, center.y, max(3.0, span * 0.6))
    collections["LIGHTS"].objects.link(fill)


def main() -> int:
    args = parse_args()
    model_path = Path(args.model).resolve()
    structure_path = Path(args.structure).resolve()
    catalog_path = Path(args.blender_catalog).resolve()
    material_catalog_path = Path(args.material_catalog).resolve()
    style_path = Path(args.style_preset).resolve()
    options_path = Path(args.backend_options).resolve()
    model, structure, catalog, material_catalog, style, options = map(
        read_json,
        (model_path, structure_path, catalog_path, material_catalog_path, style_path, options_path),
    )
    if model.get("meta", {}).get("sourceFloorplanId") != structure.get("floorplanId"):
        raise ValueError("current HTML model and structure floorplan identities differ")
    if catalog.get("schema") != "interior.blender-component-catalog.v4":
        raise ValueError("Blender catalog must be interior.blender-component-catalog.v4")
    if material_catalog.get("schema") != "interior.blender-material-catalog.v1":
        raise ValueError("material catalog must be interior.blender-material-catalog.v1")
    if style.get("schema") != "interior.blender-style-preset.v3":
        raise ValueError("style preset must be interior.blender-style-preset.v3")
    if options.get("schema") != "interior.blender-backend-options.v5":
        raise ValueError("backend options must be interior.blender-backend-options.v5")
    covered = {value for asset in catalog.get("assets", []) for value in asset.get("functionalClasses", [])}
    required = {str(item.get("functionalClass")) for item in model.get("furniture", [])}
    if required - covered:
        raise ValueError(f"Blender precision catalog lacks functional classes: {sorted(required-covered)}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = bpy.context.scene.collection
    collections = {}
    for name in COLLECTIONS:
        collection = bpy.data.collections.new(name)
        root.children.link(collection)
        collections[name] = collection
    templates = style.get("materialTemplates", {})
    mats = {
        "wall": pbr_material("M_Wall_Plaster_PBR", templates["wall"], material_catalog),
        "wood-floor": pbr_material("M_Floor_Warm_Oak_PBR", templates["dryFloor"], material_catalog),
        "tile-floor": pbr_material("M_Floor_Interior_Ceramic_PBR", templates["wetFloor"], material_catalog),
        "ceiling": pbr_material("M_Ceiling_Soft_Plaster_PBR", templates["ceiling"], material_catalog),
        "glass": material("M_Glass", tuple(style["glass"]["baseColor"]), style["glass"]["roughness"]),
        "frame": material("M_Frame", tuple(style["frame"]["baseColor"]), style["frame"]["roughness"], style["frame"]["metallic"]),
        "door": material("M_Door", tuple(style["door"]["baseColor"]), style["door"]["roughness"]),
    }
    wall_piece_count = build_walls(model, mats["wall"], collections["STRUCTURE"])
    opening_count = build_openings(model, mats, collections["OPENINGS"])
    boundary = [to_blender_plan(point) for point in model.get("floorBoundary", [])]
    if len(boundary) < 3:
        raise ValueError("current HTML model lacks floorBoundary")
    wet_types = set(style.get("wetRoomTypes", []))
    floor_count = 0
    for room in structure.get("rooms", []):
        polygon = room.get("polygon", [])
        if len(polygon) < 3: continue
        room_id = str(room["id"]); room_type = str(room.get("spaceType", room_id)).lower()
        floor_material = mats["tile-floor"] if room_type in wet_types or any(token in room_id for token in ("bath", "kitchen", "balcony")) else mats["wood-floor"]
        polygon_prism(f"floor::{room_id}", [to_blender_plan(point) for point in polygon], -0.06, 0.06, floor_material, collections["FLOORS"], f"floor::{room_id}", "floor", roomId=room_id, finish="tile" if floor_material == mats["tile-floor"] else "wood")
        floor_count += 1
    ceiling_height = max([float(wall.get("height", 2.8)) for wall in model.get("walls", [])] or [2.8])
    ceiling = polygon_prism(
        "ceiling::whole", boundary, ceiling_height, 0.04, mats["ceiling"], collections["CEILINGS"],
        "ceiling::whole", "ceiling", heightMeters=ceiling_height,
    )
    ceiling.hide_viewport = options.get("ceilings", {}).get("visibleByDefault") is not True
    furniture = build_furniture(model, catalog, style, collections["FURNITURE"])
    print(f"stage=furniture-ready count={len(furniture)}", flush=True)
    texture_policy = normalize_texture_memory(int(style.get("maxTextureDimension", 1024)))
    print(f"stage=textures-ready resized={texture_policy['resizedCount']}", flush=True)
    xs = [point[0] for point in boundary]
    ys = [point[1] for point in boundary]
    center = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0))
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    add_lighting(collections, center, span, style)
    configure_render(bpy.context.scene, style)
    print("stage=scene-ready", flush=True)

    out_blend, out_glb, out_report = map(
        lambda value: Path(value).resolve(), (args.out_blend, args.out_glb, args.out_report)
    )
    for path in (out_blend, out_glb, out_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene["interiorFloorplanId"] = structure["floorplanId"]
    scene["interiorModelBackend"] = "blender"
    scene["interiorSourceHtmlModelSha256"] = sha256(model_path)
    scene["interiorCurrentModel"] = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    scene["interiorStructureData"] = json.dumps(structure, ensure_ascii=False, separators=(",", ":"))
    scene["interiorBlenderCatalogSha256"] = sha256(catalog_path)
    scene["interiorMaterialCatalogSha256"] = sha256(material_catalog_path)
    scene["interiorStylePresetSha256"] = sha256(style_path)
    scene["interiorStylePreset"] = json.dumps(style, ensure_ascii=False, separators=(",", ":"))
    print("stage=packing", flush=True)
    bpy.ops.file.pack_all()
    print("stage=saving-blend", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    print("stage=exporting-glb", flush=True)
    bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB", export_yup=True)
    report = {
        "schema": "interior.blender-build-report.v5", "accepted": True, "backend": "blender",
        "compiler": "html-facts-to-blender-pbr-material-v3", "floorplanId": structure["floorplanId"],
        "sourceHtmlModel": {"path": str(model_path), "sha256": sha256(model_path)},
        "structure": {"path": str(structure_path), "sha256": sha256(structure_path)},
        "blenderCatalog": {"path": str(catalog_path), "sha256": sha256(catalog_path)},
        "materialCatalog": {"path": str(material_catalog_path), "sha256": sha256(material_catalog_path)},
        "stylePreset": {"path": str(style_path), "sha256": sha256(style_path), "styleId": style["styleId"]},
        "texturePolicy": texture_policy,
        "nativeModelPath": str(out_blend), "nativeModelSha256": sha256(out_blend),
        "derivedGlbPath": str(out_glb), "derivedGlbSha256": sha256(out_glb),
        "blenderVersion": bpy.app.version_string,
        "coordinateTransform": {
            "source": "threejs-world-y-up-meters", "target": "blender-world-z-up-meters",
            "point": "[x,y,z] -> [x,-z,y]", "inverse": "[x,y,z] -> [x,z,-y]",
        },
        "collections": {name: len(collections[name].objects) for name in COLLECTIONS},
        "counts": {
            "walls": len(model.get("walls", [])), "wallPieces": wall_piece_count,
            "openings": opening_count, "furniture": len(furniture), "floors": floor_count, "ceilings": 1,
        },
        "furniture": furniture, "unmatchedFurnitureCount": 0, "primitiveFurnitureFallbackCount": 0,
        "previewPolicy": "formal-eevee-camera-delivery-only",
    }
    write_json(out_report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
