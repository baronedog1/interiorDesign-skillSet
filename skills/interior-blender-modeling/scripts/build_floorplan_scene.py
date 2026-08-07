#!/usr/bin/env python3
"""Compile floorplan-handoff.v3 directly into a native Blender scene."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    blender_transform,
    load_handoff,
    load_layout_overrides,
    read_json,
    sha256,
    source_object_index,
    to_blender_xy,
    write_json,
)


COLLECTIONS = ("STRUCTURE", "OPENINGS", "FLOORS", "CEILINGS", "FURNITURE", "LIGHTS", "CAMERAS", "ANNOTATIONS")


def args_after_double_dash() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--asset-store", required=True)
    parser.add_argument("--backend-options", required=True)
    parser.add_argument("--layout-overrides")
    parser.add_argument("--out-blend", required=True)
    parser.add_argument("--out-glb", required=True)
    parser.add_argument("--out-report", required=True)
    parser.add_argument("--preview-dir", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def material(name: str, rgba: tuple[float, float, float, float], roughness: float, metallic: float = 0.0):
    value = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    value.diffuse_color = rgba
    value.use_nodes = True
    bsdf = value.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return value


def relink(obj, collection):
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def box(name, location, dimensions, rotation_z, mat, collection):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0, 0, rotation_z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    relink(obj, collection)
    return obj


def polygon_prism(name, points, z0, height, mat, collection):
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
    return obj


def tag(obj, entity_id, entity_type, **fields):
    obj["interiorEntityId"] = entity_id
    obj["interiorEntityType"] = entity_type
    for key, value in fields.items():
        obj[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value


def wall_piece(structure, wall, start_offset, end_offset, z0, z1, suffix, mat, collection):
    source_start = Vector(wall["start"])
    source_end = Vector(wall["end"])
    direction = (source_end - source_start).normalized()
    a = source_start + direction * start_offset
    b = source_start + direction * end_offset
    ax, ay = to_blender_xy(structure, [a.x, a.y])
    bx, by = to_blender_xy(structure, [b.x, b.y])
    length = max(math.hypot(bx - ax, by - ay), 0.001)
    angle = math.atan2(by - ay, bx - ax)
    obj = box(
        f"{wall['id']}::{suffix}",
        ((ax + bx) / 2, (ay + by) / 2, (z0 + z1) / 2),
        (length, float(wall["thickness"]), z1 - z0),
        angle,
        mat,
        collection,
    )
    tag(obj, wall["id"], "wall-piece", sourceWallId=wall["id"], adjacentRoomIds=wall.get("adjacentRoomIds", []))
    return obj


def build_wall(structure, wall, windows, mat, collection):
    source_start, source_end = Vector(wall["start"]), Vector(wall["end"])
    length = (source_end - source_start).length
    hosted = sorted((row for row in windows if row.get("wallId") == wall["id"]), key=lambda row: row["offset"])
    cuts = sorted({0.0, length, *[max(0.0, float(row["offset"])) for row in hosted], *[min(length, float(row["offset"]) + float(row["width"])) for row in hosted]})
    pieces = []
    for index, (left, right) in enumerate(zip(cuts, cuts[1:])):
        if right - left < 0.005:
            continue
        midpoint = (left + right) / 2
        active = [row for row in hosted if row["offset"] <= midpoint <= row["offset"] + row["width"]]
        if not active:
            pieces.append(wall_piece(structure, wall, left, right, 0, wall["height"], f"full-{index}", mat, collection))
            continue
        cursor = 0.0
        for opening in sorted(active, key=lambda row: row["sill"]):
            bottom = float(opening["sill"])
            top = bottom + float(opening["openingHeight"])
            if bottom > cursor + 0.005:
                pieces.append(wall_piece(structure, wall, left, right, cursor, bottom, f"low-{index}", mat, collection))
            cursor = max(cursor, top)
        if cursor < float(wall["height"]) - 0.005:
            pieces.append(wall_piece(structure, wall, left, right, cursor, wall["height"], f"high-{index}", mat, collection))
    return pieces


def build_window(structure, opening, wall, style, mats, collection):
    source_start = Vector(wall["start"])
    source_end = Vector(wall["end"])
    direction = (source_end - source_start).normalized()
    center = source_start + direction * (float(opening["offset"]) + float(opening["width"]) / 2)
    x, y = to_blender_xy(structure, [center.x, center.y])
    angle = math.atan2(-direction.y, direction.x)
    parent = bpy.data.objects.new(opening["id"], None)
    collection.objects.link(parent)
    parent.location = (x, y, float(opening["sill"]) + float(opening["openingHeight"]) / 2)
    parent.rotation_euler.z = angle
    tag(
        parent,
        opening["id"],
        "window",
        hostWallId=opening["wallId"],
        windowStyle=style,
        roomIds=wall.get("adjacentRoomIds", []),
    )
    frame = 0.05
    depth = max(float(opening.get("frameDepth", 0.08)), float(wall["thickness"]) * 0.55)

    def child(suffix, location, dimensions, mat):
        value = box(f"{opening['id']}::{suffix}", (0, 0, 0), dimensions, 0, mat, collection)
        value.parent = parent
        value.location = location
        tag(
            value,
            opening["id"],
            "window-part",
            hostWallId=opening["wallId"],
            part=suffix,
            roomIds=wall.get("adjacentRoomIds", []),
        )
        return value

    child("glass", (0, 0, 0), (max(opening["width"] - frame * 2, 0.05), 0.018, max(opening["openingHeight"] - frame * 2, 0.05)), mats["glass"])
    if style != "frameless-glass":
        child("left", (-opening["width"] / 2 + frame / 2, 0, 0), (frame, depth, opening["openingHeight"]), mats["frame"])
        child("right", (opening["width"] / 2 - frame / 2, 0, 0), (frame, depth, opening["openingHeight"]), mats["frame"])
        child("top", (0, 0, opening["openingHeight"] / 2 - frame / 2), (opening["width"], depth, frame), mats["frame"])
        child("bottom", (0, 0, -opening["openingHeight"] / 2 + frame / 2), (opening["width"], depth, frame), mats["frame"])
    if style in {"casement", "sliding"}:
        child("mullion", (0, 0, 0), (frame, depth, opening["openingHeight"] - frame * 2), mats["frame"])
    return parent


def balcony_mode_for_wall(structure, wall, options):
    rooms = {room["id"]: room for room in structure.get("rooms", [])}
    balcony_id = next((
        room_id for room_id in wall.get("adjacentRoomIds", [])
        if room_id in rooms and rooms[room_id].get("spaceType") in {"balcony", "terrace", "loggia"}
    ), None)
    if not balcony_id:
        return None
    exterior = (
        wall.get("type") == "external"
        or any(room_id in {"exterior", "outside", "outdoor"} for room_id in wall.get("adjacentRoomIds", []))
        or len(wall.get("adjacentRoomIds", [])) == 1
    )
    if not exterior:
        return None
    balcony = options.get("balconies", {})
    mode = balcony.get("overrides", {}).get(wall["id"], balcony.get("overrides", {}).get(balcony_id, balcony.get("defaultEnclosureMode", "source")))
    return {"roomId": balcony_id, "mode": mode, "railingHeightMeters": float(balcony.get("railingHeightMeters", 1.1))}


def build_balcony_envelope(structure, wall, envelope, mats, collection):
    if not envelope or envelope["mode"] in {"source", "source-structure"}:
        return []
    sx, sy = to_blender_xy(structure, wall["start"])
    ex, ey = to_blender_xy(structure, wall["end"])
    length = math.hypot(ex - sx, ey - sy)
    angle = math.atan2(ey - sy, ex - sx)
    center = ((sx + ex) / 2, (sy + ey) / 2)
    root = bpy.data.objects.new(f"balcony::{wall['id']}", None)
    collection.objects.link(root)
    tag(root, wall["id"], "balcony-envelope", roomId=envelope["roomId"], enclosureMode=envelope["mode"])
    objects = [root]
    if envelope["mode"] == "open-railing":
        height = envelope["railingHeightMeters"]
        depth = max(0.045, float(wall["thickness"]) * 0.28)
        for name, z, size in (
            ("base", 0.06, (length, depth, 0.12)),
            ("top", height - 0.0325, (length, depth, 0.065)),
        ):
            obj = box(f"{wall['id']}::railing-{name}", (center[0], center[1], z), size, angle, mats["frame"], collection)
            obj.parent = root
            tag(obj, wall["id"], "balcony-envelope-part", roomId=envelope["roomId"], part=name)
            objects.append(obj)
        post_count = max(2, math.ceil(length / 0.82))
        tangent = Vector((ex - sx, ey - sy)).normalized()
        for index in range(post_count + 1):
            offset = length * index / post_count
            point = Vector((sx, sy)) + tangent * offset
            obj = box(f"{wall['id']}::railing-post-{index + 1}", (point.x, point.y, 0.12 + (height - 0.12) / 2), (0.045, depth, height - 0.12), angle, mats["frame"], collection)
            obj.parent = root
            tag(obj, wall["id"], "balcony-envelope-part", roomId=envelope["roomId"], part="post")
            objects.append(obj)
    elif envelope["mode"] == "closed-glazing":
        height = float(wall["height"])
        glass = box(f"{wall['id']}::balcony-glass", (center[0], center[1], height / 2), (length, 0.028, height), angle, mats["glass"], collection)
        glass.parent = root
        tag(glass, wall["id"], "balcony-envelope-part", roomId=envelope["roomId"], part="glass")
        objects.append(glass)
        panel_count = max(2, math.ceil(length / 1.25))
        tangent = Vector((ex - sx, ey - sy)).normalized()
        for index in range(panel_count + 1):
            offset = length * index / panel_count
            point = Vector((sx, sy)) + tangent * offset
            post = box(f"{wall['id']}::glazing-post-{index + 1}", (point.x, point.y, height / 2), (0.05, float(wall["thickness"]), height), angle, mats["frame"], collection)
            post.parent = root
            tag(post, wall["id"], "balcony-envelope-part", roomId=envelope["roomId"], part="post")
            objects.append(post)
    else:
        raise ValueError(f"unsupported balcony enclosure mode {envelope['mode']}")
    return objects


def append_asset(asset_path: Path, collection):
    before = set(bpy.data.objects)
    if asset_path.suffix.lower() == ".blend":
        with bpy.data.libraries.load(str(asset_path), link=False) as (source, target):
            target.objects = [name for name in source.objects if name]
        imported = [obj for obj in target.objects if obj is not None]
        for obj in imported:
            if not obj.users_collection:
                collection.objects.link(obj)
            else:
                relink(obj, collection)
    else:
        bpy.ops.import_scene.gltf(filepath=str(asset_path))
        imported = [obj for obj in bpy.data.objects if obj not in before]
        for obj in imported:
            relink(obj, collection)
    unsupported = [obj for obj in imported if obj.type in {"CAMERA", "LIGHT", "SPEAKER"}]
    for obj in unsupported:
        bpy.data.objects.remove(obj, do_unlink=True)
    imported = [obj for obj in imported if obj not in unsupported]
    geometry = [obj for obj in imported if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}]
    if not geometry:
        raise ValueError(f"asset imported no objects: {asset_path}")
    return imported


def world_bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects if hasattr(obj, "bound_box") for corner in obj.bound_box]
    if not points:
        raise ValueError("asset has no measurable geometry")
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return minimum, maximum


def build_component(structure, source, item, asset, store, collection, handoff):
    root = bpy.data.objects.new(source["id"], None)
    collection.objects.link(root)
    asset_frame = bpy.data.objects.new(f"{source['id']}::asset-frame", None)
    collection.objects.link(asset_frame)
    asset_frame.parent = root
    front_rotation = {
        "-Y": 0.0,
        "+Y": math.pi,
        "+X": -math.pi / 2,
        "-X": math.pi / 2,
    }.get(item["axisAdapter"].get("front"))
    if front_rotation is None:
        raise ValueError(f"{source['id']}: unsupported reviewed asset front axis")
    asset_frame.rotation_euler.z = front_rotation
    imported = append_asset(store / asset["relativePath"], collection)
    for obj in imported:
        if obj.parent is None:
            obj.parent = asset_frame
        if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            tag(
                obj,
                source["id"],
                "component-part",
                sourceObjectCandidateId=source["sourceObjectCandidateId"],
                traceId=source["traceId"],
                assetId=item["assetId"],
                roomId=source["roomId"],
                semanticType=source["semantic"],
                category=asset["category"],
                functionalClass=source["functionalClass"],
                quantity=1,
                localAxes=asset.get("directionalAxes", {}),
            )
    bpy.context.view_layer.update()
    minimum, maximum = world_bounds(imported)
    size = maximum - minimum
    target_width = float(source["bbox"]["width"])
    target_depth = float(source["bbox"]["depth"])
    target_height = float(source["bbox"]["height"])
    scale = min(
        target_width / max(size.x, 1e-6),
        target_depth / max(size.y, 1e-6),
        target_height / max(size.z, 1e-6),
    )
    if not 0.1 <= scale <= 10:
        raise ValueError(f"{source['id']}: uniform asset scale is outside reviewed range: {scale}")
    target_x, target_y = to_blender_xy(structure, source["center"])
    root.scale = (scale, scale, scale)
    root.location = (target_x, target_y, -minimum.z * scale)
    root.rotation_euler.z = -float(source.get("rotationY", 0))
    bpy.context.view_layer.update()
    placed_minimum, placed_maximum = world_bounds(imported)
    root.location.x += target_x - (placed_minimum.x + placed_maximum.x) / 2
    root.location.y += target_y - (placed_minimum.y + placed_maximum.y) / 2
    root.location.z -= placed_minimum.z
    bpy.context.view_layer.update()
    placed_minimum, placed_maximum = world_bounds(imported)
    placed_center = (placed_minimum + placed_maximum) / 2
    if math.hypot(placed_center.x - target_x, placed_center.y - target_y) > 0.002:
        raise ValueError(f"{source['id']}: placed asset center differs from the source placement")
    if abs(placed_minimum.z) > 0.002:
        raise ValueError(f"{source['id']}: placed asset is not grounded at z=0")
    if placed_maximum.z > target_height + 0.002:
        raise ValueError(f"{source['id']}: placed asset exceeds the source height")
    tag(
        root,
        source["id"],
        "component",
        sourceObjectCandidateId=source["sourceObjectCandidateId"],
        traceId=source["traceId"],
        assetId=item["assetId"],
        assetSha256=asset["sha256"],
        roomId=source["roomId"],
        semanticType=source["semantic"],
        category=asset["category"],
        functionalClass=source["functionalClass"],
        quantity=1,
        localAxes=asset.get("directionalAxes", {}),
        handoffDigestSha256=handoff["handoffDigestSha256"],
        uniformScale=scale,
    )
    root["interiorCollisionGuard"] = True
    return root


def is_light_component(source):
    semantic = str(source.get("semantic", "")).lower()
    return any(token in semantic for token in ("light", "lamp", "pendant", "chandelier", "sconce"))


def set_render_defaults(scene):
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("InteriorWorld")
    scene.world.color = (0.15, 0.15, 0.15)


def create_overview_camera(structure, collections, preview_path):
    width = float(structure["coordinateSystem"]["realWidthMeters"])
    depth = float(structure["coordinateSystem"]["realDepthMeters"])
    data = bpy.data.cameras.new("overview-camera-data")
    camera = bpy.data.objects.new("overview-camera", data)
    collections["CAMERAS"].objects.link(camera)
    camera.location = (width * 0.7, -depth * 0.8, max(width, depth) * 0.75)
    camera.rotation_euler = (Vector((0, 0, 1.2)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.lens = 35
    bpy.context.scene.camera = camera
    bpy.context.scene.render.filepath = str(preview_path)
    ceiling_states = [(obj, obj.hide_render) for obj in collections["CEILINGS"].objects]
    for obj, _ in ceiling_states:
        obj.hide_render = True
    bpy.ops.render.render(write_still=True)
    for obj, state in ceiling_states:
        obj.hide_render = state
    tag(camera, "overview-camera", "camera")


def main() -> int:
    args = args_after_double_dash()
    handoff_path = Path(args.handoff).resolve()
    selection_path = Path(args.selection).resolve()
    catalog_path = Path(args.catalog).resolve()
    options_path = Path(args.backend_options).resolve()
    store = Path(args.asset_store).resolve()
    handoff, structure, traces = load_handoff(handoff_path)
    selection = read_json(selection_path)
    catalog = read_json(catalog_path)
    options = read_json(options_path)
    if selection.get("handoffDigestSha256") != handoff["handoffDigestSha256"]:
        raise ValueError("selection does not belong to this handoff")
    if selection.get("catalogSha256") != sha256(catalog_path):
        raise ValueError("selection catalog digest mismatch")
    sources = source_object_index(traces)
    selected = {row["sourceObjectCandidateId"]: row for row in selection["items"]}
    assets = {row["assetId"]: row for row in catalog["assets"]}
    if set(sources) != set(selected):
        raise ValueError("selection must cover every source object exactly once")
    overrides_path = Path(args.layout_overrides).resolve() if args.layout_overrides else None
    overrides = load_layout_overrides(
        overrides_path,
        backend="blender",
        floorplan_id=handoff["floorplanId"],
        entity_ids={source["id"] for source in sources.values()},
    )

    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = bpy.context.scene.collection
    collections = {}
    for name in COLLECTIONS:
        value = bpy.data.collections.new(name)
        root.children.link(value)
        collections[name] = value
    mats = {
        "wall": material("M_Wall_Concrete", (0.59, 0.57, 0.53, 1), 0.9),
        "floor": material("M_Floor_Concrete", (0.47, 0.45, 0.42, 1), 0.92),
        "ceiling": material("M_Ceiling", (0.76, 0.75, 0.72, 1), 0.82),
        "glass": material("M_Glass", (0.45, 0.66, 0.74, 0.24), 0.12),
        "frame": material("M_Frame", (0.08, 0.09, 0.09, 1), 0.35, 0.5),
    }
    walls = {row["id"]: row for row in structure.get("walls", [])}
    wall_piece_count = 0
    replaced_balcony_walls = set()
    for wall in walls.values():
        balcony_objects = build_balcony_envelope(
            structure,
            wall,
            balcony_mode_for_wall(structure, wall, options),
            mats,
            collections["STRUCTURE"],
        )
        if balcony_objects:
            replaced_balcony_walls.add(wall["id"])
            wall_piece_count += len(balcony_objects)
        else:
            wall_piece_count += len(build_wall(structure, wall, structure.get("windows", []), mats["wall"], collections["STRUCTURE"]))
    window_overrides = options.get("windows", {}).get("overrides", {})
    default_window = options.get("windows", {}).get("defaultStyle", "frameless-glass")
    for opening in structure.get("windows", []):
        if opening["wallId"] in replaced_balcony_walls:
            continue
        build_window(structure, opening, walls[opening["wallId"]], window_overrides.get(opening["id"], default_window), mats, collections["OPENINGS"])
    for connection in structure.get("connections", []):
        root_obj = bpy.data.objects.new(connection["id"], None)
        collections["OPENINGS"].objects.link(root_obj)
        tag(root_obj, connection["id"], "connection", fromRoomId=connection.get("fromRoomId"), toRoomId=connection.get("toRoomId"), connectionKind=connection.get("kind"))
    ceiling_enabled = options.get("ceilings", {}).get("enabled", True)
    for room in structure.get("rooms", []):
        points = [to_blender_xy(structure, point) for point in room["polygon"]]
        floor = polygon_prism(f"floor::{room['id']}", points, -0.08, 0.08, mats["floor"], collections["FLOORS"])
        tag(floor, f"floor::{room['id']}", "floor", roomId=room["id"])
        if ceiling_enabled:
            adjacent_heights = [float(wall["height"]) for wall in walls.values() if room["id"] in wall.get("adjacentRoomIds", [])]
            ceiling_z = max(adjacent_heights or [float(structure["coordinateSystem"].get("defaultWallHeightMeters", 3.0))])
            ceiling = polygon_prism(f"ceiling::{room['id']}", points, ceiling_z, 0.04, mats["ceiling"], collections["CEILINGS"])
            ceiling.hide_viewport = options.get("ceilings", {}).get("visibleByDefault") is not True
            ceiling.hide_render = False
            tag(ceiling, f"ceiling::{room['id']}", "ceiling", roomId=room["id"], heightMeters=ceiling_z, inspectionHidden=ceiling.hide_viewport)
    built_components = []
    for source_id, source in sources.items():
        item = selected[source_id]
        asset = assets[item["assetId"]]
        effective_source = dict(source)
        override = overrides.get(source["id"])
        if override:
            effective_source["center"] = override["target"]["position"]
            effective_source["rotationY"] = override["target"]["rotationYRadians"]
        target_collection = collections["LIGHTS"] if is_light_component(source) else collections["FURNITURE"]
        component = build_component(
            structure,
            effective_source,
            item,
            asset,
            store,
            target_collection,
            handoff,
        )
        if override:
            component["interiorReviewedAdjustment"] = json.dumps(
                override["reviewedAdjustment"], ensure_ascii=False, sort_keys=True
            )
        built_components.append(component)
    sun_data = bpy.data.lights.new("inspection-sun-data", "SUN")
    sun_data.energy = 2.0
    sun = bpy.data.objects.new("inspection-sun", sun_data)
    sun.rotation_euler = (math.radians(35), 0, math.radians(-30))
    collections["LIGHTS"].objects.link(sun)
    tag(sun, "inspection-sun", "light", authored=False)
    set_render_defaults(bpy.context.scene)
    preview_dir = Path(args.preview_dir).resolve()
    preview_dir.mkdir(parents=True, exist_ok=True)
    create_overview_camera(structure, collections, preview_dir / "overview.png")
    out_blend = Path(args.out_blend).resolve()
    out_glb = Path(args.out_glb).resolve()
    out_report = Path(args.out_report).resolve()
    for path in (out_blend, out_glb, out_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene["interiorFloorplanId"] = handoff["floorplanId"]
    bpy.context.scene["interiorHandoffDigestSha256"] = handoff["handoffDigestSha256"]
    bpy.context.scene["interiorCoordinateTransform"] = json.dumps(blender_transform(structure))
    bpy.context.scene["interiorStructureData"] = json.dumps(structure, ensure_ascii=False)
    bpy.context.scene["interiorTraceComponents"] = json.dumps(traces, ensure_ascii=False)
    bpy.context.scene["interiorSourceArtifacts"] = json.dumps({
        "structureData": {
            "path": str((handoff_path.parent / handoff["artifacts"]["structureData"]["path"]).resolve()),
            "sha256": handoff["artifacts"]["structureData"]["sha256"],
        },
        "traceComponents": {
            "path": str((handoff_path.parent / handoff["artifacts"]["traceComponents"]["path"]).resolve()),
            "sha256": handoff["artifacts"]["traceComponents"]["sha256"],
        },
    }, ensure_ascii=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB", export_yup=True)
    report = {
        "schema": "interior.blender-build-report.v1",
        "accepted": True,
        "backend": "blender",
        "floorplanId": handoff["floorplanId"],
        "handoffDigestSha256": handoff["handoffDigestSha256"],
        "nativeModelPath": str(out_blend),
        "nativeModelSha256": sha256(out_blend),
        "derivedGlbPath": str(out_glb),
        "derivedGlbSha256": sha256(out_glb),
        "blenderVersion": bpy.app.version_string,
        "coordinateTransform": blender_transform(structure),
        "collections": {name: len(collections[name].objects) for name in COLLECTIONS},
        "counts": {
            "rooms": len(structure.get("rooms", [])),
            "walls": len(walls),
            "wallPieces": wall_piece_count,
            "windows": len(structure.get("windows", [])) - sum(opening["wallId"] in replaced_balcony_walls for opening in structure.get("windows", [])),
            "connections": len(structure.get("connections", [])),
            "components": len(built_components),
            "lightFixtures": sum(is_light_component(source) for source in sources.values()),
            "ceilings": len(collections["CEILINGS"].objects),
            "balconyEnvelopes": len(replaced_balcony_walls),
        },
        "selectionSha256": sha256(selection_path),
        "catalogSha256": sha256(catalog_path),
        "backendOptionsSha256": sha256(options_path),
        "layoutOverrides": {
            "path": str(overrides_path) if overrides_path else None,
            "sha256": sha256(overrides_path) if overrides_path else None,
            "appliedEntityCount": len(overrides),
        },
        "sourceArtifacts": {
            "structureData": {"path": str((handoff_path.parent / handoff["artifacts"]["structureData"]["path"]).resolve()), "sha256": handoff["artifacts"]["structureData"]["sha256"]},
            "traceComponents": {"path": str((handoff_path.parent / handoff["artifacts"]["traceComponents"]["path"]).resolve()), "sha256": handoff["artifacts"]["traceComponents"]["sha256"]},
        },
        "primitiveFurnitureFallbackCount": 0,
        "previewPath": str(preview_dir / "overview.png"),
    }
    write_json(out_report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
