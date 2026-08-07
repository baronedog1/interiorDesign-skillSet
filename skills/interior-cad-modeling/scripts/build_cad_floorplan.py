#!/usr/bin/env python3
"""Build a native STEP apartment directly from floorplan-handoff.v3."""

from __future__ import annotations

import argparse
import importlib.metadata
import math
from pathlib import Path

from common import (
    coordinate_transform,
    load_handoff,
    load_layout_overrides,
    read_json,
    sha256,
    source_objects,
    to_cad_xy,
    write_json,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--handoff", required=True)
    value.add_argument("--selection", required=True)
    value.add_argument("--catalog", required=True)
    value.add_argument("--asset-store", required=True)
    value.add_argument("--options", required=True)
    value.add_argument("--layout-overrides")
    value.add_argument("--out-step", required=True)
    value.add_argument("--out-glb", help="Optional binary glTF derived from the accepted B-rep")
    value.add_argument("--out-mesh", help="Optional derived .3mf or .stl review mesh")
    value.add_argument("--out-report", required=True)
    value.add_argument("--out-entities", required=True)
    return value


def safe_label(shape, label: str):
    try:
        shape.label = label
    except Exception:
        pass
    return shape


def shape_bounds(shape) -> tuple[float, float, float]:
    bbox = shape.bounding_box()
    size = bbox.size
    return float(size.X), float(size.Y), float(size.Z)


def shape_bounds_record(shape) -> dict:
    """Record one B-rep entity in both CAD and canonical camera coordinates."""
    bbox = shape.bounding_box()
    cad_min = [float(bbox.min.X), float(bbox.min.Y), float(bbox.min.Z)]
    cad_max = [float(bbox.max.X), float(bbox.max.Y), float(bbox.max.Z)]
    return {
        "cadBoundsMm": {"min": cad_min, "max": cad_max},
        "worldBoundsMeters": {
            "min": [cad_min[0] / 1000, cad_min[2] / 1000, -cad_max[1] / 1000],
            "max": [cad_max[0] / 1000, cad_max[2] / 1000, -cad_min[1] / 1000],
        },
    }


def place_shape(shape, center_xy, rotation_radians, z_offset=0.0):
    from build123d import Axis, Location

    placed = shape.rotate(Axis.Z, -math.degrees(float(rotation_radians)))
    return placed.moved(Location((float(center_xy[0]), float(center_xy[1]), float(z_offset))))


def rectangle_solid(length, depth, height, center, angle, z0=0.0):
    from build123d import Align, Box, Location

    solid = Box(
        float(length),
        float(depth),
        float(height),
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    return solid.moved(Location((float(center[0]), float(center[1]), float(z0)), (0, 0, math.degrees(angle))))


def polygon_solid(points, height, z0=0.0):
    from build123d import Face, Location, Vector, Wire, extrude

    wire = Wire.make_polygon([Vector(float(x), float(y), 0) for x, y in points], close=True)
    result = extrude(Face(wire), amount=float(height))
    return result.moved(Location((0, 0, float(z0))))


def build_wall(structure, wall, windows):
    start = to_cad_xy(structure, wall["start"])
    end = to_cad_xy(structure, wall["end"])
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    angle = math.atan2(dy, dx)
    center = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    result = rectangle_solid(length, float(wall["thickness"]) * 1000, float(wall["height"]) * 1000, center, angle)
    source_start_x, source_start_y = start
    unit = (dx / length, dy / length)
    for opening in windows:
        if opening.get("wallId") != wall["id"]:
            continue
        offset = (float(opening["offset"]) + float(opening["width"]) / 2) * 1000
        opening_center = (source_start_x + unit[0] * offset, source_start_y + unit[1] * offset)
        cutter = rectangle_solid(
            float(opening["width"]) * 1000 + 2,
            float(wall["thickness"]) * 1000 + 20,
            float(opening["openingHeight"]) * 1000,
            opening_center,
            angle,
            float(opening["sill"]) * 1000,
        )
        result = result - cutter
    return safe_label(result, wall["id"])


def build_window(structure, opening, wall, style):
    from build123d import Compound

    start = to_cad_xy(structure, wall["start"])
    end = to_cad_xy(structure, wall["end"])
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    unit = (dx / length, dy / length)
    angle = math.atan2(dy, dx)
    offset = (float(opening["offset"]) + float(opening["width"]) / 2) * 1000
    center = (start[0] + unit[0] * offset, start[1] + unit[1] * offset)
    width = float(opening["width"]) * 1000
    height = float(opening["openingHeight"]) * 1000
    sill = float(opening["sill"]) * 1000
    frame = 50.0
    depth = max(float(opening.get("frameDepth", 0.08)) * 1000, float(wall["thickness"]) * 550)
    pieces = [rectangle_solid(max(width - 2 * frame, 20), 12, max(height - 2 * frame, 20), center, angle, sill + frame)]
    if style != "frameless-glass":
        across = (-unit[1], unit[0])
        for sign in (-1, 1):
            edge_center = (center[0] + unit[0] * sign * (width - frame) / 2, center[1] + unit[1] * sign * (width - frame) / 2)
            pieces.append(rectangle_solid(frame, depth, height, edge_center, angle, sill))
        pieces.append(rectangle_solid(width, depth, frame, center, angle, sill))
        pieces.append(rectangle_solid(width, depth, frame, center, angle, sill + height - frame))
        if style in {"casement", "sliding"}:
            pieces.append(rectangle_solid(frame, depth, height - 2 * frame, center, angle, sill + frame))
    return safe_label(Compound(children=pieces), opening["id"])


def balcony_mode_for_wall(structure, wall, options):
    rooms = {room["id"]: room for room in structure.get("rooms", [])}
    balcony_id = next(
        (
            room_id
            for room_id in wall.get("adjacentRoomIds", [])
            if room_id in rooms and rooms[room_id].get("spaceType") in {"balcony", "terrace", "loggia"}
        ),
        None,
    )
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
    mode = balcony.get("overrides", {}).get(
        wall["id"],
        balcony.get("overrides", {}).get(balcony_id, balcony.get("defaultEnclosureMode", "source")),
    )
    return {
        "roomId": balcony_id,
        "mode": mode,
        "railingHeightMm": float(balcony.get("railingHeightMm", 1100)),
    }


def build_balcony_envelope(structure, wall, envelope):
    from build123d import Compound

    if not envelope or envelope["mode"] in {"source", "source-structure"}:
        return None
    start = to_cad_xy(structure, wall["start"])
    end = to_cad_xy(structure, wall["end"])
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    unit = (dx / length, dy / length)
    angle = math.atan2(dy, dx)
    center = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    depth = max(45.0, float(wall["thickness"]) * 280)
    pieces = []
    if envelope["mode"] == "open-railing":
        height = envelope["railingHeightMm"]
        pieces.extend(
            [
                rectangle_solid(length, depth, 120, center, angle, 0),
                rectangle_solid(length, depth, 65, center, angle, height - 65),
            ]
        )
        post_count = max(2, math.ceil(length / 820))
        for index in range(post_count + 1):
            offset = length * index / post_count
            point = (start[0] + unit[0] * offset, start[1] + unit[1] * offset)
            pieces.append(rectangle_solid(45, depth, height - 120, point, angle, 120))
    elif envelope["mode"] == "closed-glazing":
        height = float(wall["height"]) * 1000
        pieces.append(rectangle_solid(length, 28, height, center, angle, 0))
        panel_count = max(2, math.ceil(length / 1250))
        for index in range(panel_count + 1):
            offset = length * index / panel_count
            point = (start[0] + unit[0] * offset, start[1] + unit[1] * offset)
            pieces.append(rectangle_solid(50, float(wall["thickness"]) * 1000, height, point, angle, 0))
    else:
        raise ValueError(f"unsupported balcony enclosure mode {envelope['mode']}")
    return safe_label(Compound(children=pieces), f"balcony::{wall['id']}")


def is_light_component(source):
    semantic = str(source.get("semantic", "")).lower()
    return any(token in semantic for token in ("light", "lamp", "pendant", "chandelier", "sconce"))


def import_and_fit_asset(asset_path, source, axis_adapter):
    from build123d import Location, import_step

    shape = import_step(asset_path)
    width, depth, height = shape_bounds(shape)
    front_rotation = {
        "-Y": 0.0,
        "+Y": math.pi,
        "+X": math.pi / 2,
        "-X": -math.pi / 2,
    }.get(axis_adapter.get("front"))
    if front_rotation is None:
        raise ValueError(f"{source['id']}: unsupported reviewed asset front axis")
    if front_rotation:
        shape = place_shape(shape, (0, 0), front_rotation)
    target_width = float(source["bbox"]["width"]) * 1000
    target_depth = float(source["bbox"]["depth"]) * 1000
    target_height = float(source["bbox"]["height"]) * 1000
    factor = min(
        target_width / max(width, 1e-6),
        target_depth / max(depth, 1e-6),
        target_height / max(height, 1e-6),
    )
    if not 0.1 <= factor <= 10:
        raise ValueError(f"{source['id']}: uniform asset scale is outside reviewed range: {factor}")
    scaled = shape.scale(factor)
    bbox = scaled.bounding_box()
    local_center_x = (float(bbox.min.X) + float(bbox.max.X)) / 2
    local_center_y = (float(bbox.min.Y) + float(bbox.max.Y)) / 2
    normalized = scaled.moved(Location((-local_center_x, -local_center_y, -float(bbox.min.Z))))
    center = to_cad_xy(CURRENT_STRUCTURE, source["center"])
    placed = place_shape(normalized, center, source.get("rotationY", 0), 0)
    placed_bbox = placed.bounding_box()
    placed_center = (
        (float(placed_bbox.min.X) + float(placed_bbox.max.X)) / 2,
        (float(placed_bbox.min.Y) + float(placed_bbox.max.Y)) / 2,
    )
    if math.dist(placed_center, center) > 2:
        raise ValueError(f"{source['id']}: placed asset center differs from the source placement")
    if abs(float(placed_bbox.min.Z)) > 2:
        raise ValueError(f"{source['id']}: placed asset is not grounded at z=0")
    return safe_label(placed, source["id"]), factor


CURRENT_STRUCTURE = {}


def main() -> int:
    global CURRENT_STRUCTURE
    args = parser().parse_args()
    handoff_path, selection_path, catalog_path = map(lambda p: Path(p).resolve(), (args.handoff, args.selection, args.catalog))
    handoff, structure, traces = load_handoff(handoff_path)
    CURRENT_STRUCTURE = structure
    selection, catalog, options = read_json(selection_path), read_json(catalog_path), read_json(Path(args.options).resolve())
    if selection.get("handoffDigestSha256") != handoff["handoffDigestSha256"]:
        raise ValueError("selection does not belong to the current handoff")
    if selection.get("catalogSha256") != sha256(catalog_path):
        raise ValueError("selection catalog digest mismatch")
    sources = source_objects(traces)
    selected = {row["sourceObjectCandidateId"]: row for row in selection.get("items", [])}
    assets = {row["id"]: row for row in catalog.get("assets", [])}
    if set(selected) != set(sources):
        raise ValueError("selection must cover every accepted source object exactly once")
    overrides_path = Path(args.layout_overrides).resolve() if args.layout_overrides else None
    layout_overrides = load_layout_overrides(
        overrides_path,
        backend="cad-step",
        floorplan_id=handoff["floorplanId"],
        entity_ids={source["id"] for source in sources.values()},
    )
    store = Path(args.asset_store).resolve()
    groups: dict[str, list] = {name: [] for name in ("STRUCTURE", "OPENINGS", "FLOORS", "CEILINGS", "FURNITURE", "LIGHTS", "CAMERAS", "ANNOTATIONS")}
    entities = []
    walls = {row["id"]: row for row in structure.get("walls", [])}
    replaced_balcony_walls = set()
    for wall in walls.values():
        envelope = balcony_mode_for_wall(structure, wall, options)
        shape = build_balcony_envelope(structure, wall, envelope)
        if shape is not None:
            replaced_balcony_walls.add(wall["id"])
        else:
            shape = build_wall(structure, wall, structure.get("windows", []))
        groups["STRUCTURE"].append(shape)
        entities.append({
            "id": wall["id"],
            "type": "balcony-envelope" if envelope and envelope["mode"] not in {"source", "source-structure"} else "wall",
            "group": "STRUCTURE",
            "sourceTraceIds": wall.get("sourceTraceIds", []),
            "roomId": envelope.get("roomId") if envelope else None,
            "roomIds": wall.get("adjacentRoomIds", []),
            "enclosureMode": envelope.get("mode") if envelope else "source-structure",
        })
    default_window_style = options.get("windows", {}).get("defaultStyle", "frameless-glass")
    window_overrides = options.get("windows", {}).get("overrides", {})
    for opening in structure.get("windows", []):
        if opening["wallId"] in replaced_balcony_walls:
            continue
        style = window_overrides.get(opening["id"], default_window_style)
        shape = build_window(structure, opening, walls[opening["wallId"]], style)
        groups["OPENINGS"].append(shape)
        entities.append({
            "id": opening["id"], "type": "window", "group": "OPENINGS",
            "hostWallId": opening["wallId"], "windowStyle": style,
            "roomIds": walls[opening["wallId"]].get("adjacentRoomIds", []),
        })
    for connection in structure.get("connections", []):
        entities.append({"id": connection["id"], "type": "connection", "group": "OPENINGS", "fromRoomId": connection.get("fromRoomId"), "toRoomId": connection.get("toRoomId"), "kind": connection.get("kind")})
    for room in structure.get("rooms", []):
        points = [to_cad_xy(structure, point) for point in room["polygon"]]
        floor = safe_label(polygon_solid(points, 80, -80), f"floor::{room['id']}")
        groups["FLOORS"].append(floor)
        entities.append({
            "id": f"floor::{room['id']}", "type": "floor", "group": "FLOORS",
            "roomId": room["id"], "roomIds": [room["id"]], "roomName": room.get("name", room["id"]),
            "roomType": room.get("spaceType", "room"),
        })
        if options.get("ceilings", {}).get("enabled", True):
            heights = [float(wall["height"]) * 1000 for wall in walls.values() if room["id"] in wall.get("adjacentRoomIds", [])]
            ceiling_z = max(heights or [float(structure["coordinateSystem"].get("defaultWallHeightMeters", 3)) * 1000])
            ceiling = safe_label(polygon_solid(points, 40, ceiling_z), f"ceiling::{room['id']}")
            groups["CEILINGS"].append(ceiling)
            entities.append({
                "id": f"ceiling::{room['id']}", "type": "ceiling", "group": "CEILINGS",
                "roomId": room["id"], "roomIds": [room["id"]], "heightMm": ceiling_z,
                "inspectionHidden": options.get("ceilings", {}).get("visibleByDefault") is not True,
            })
    component_scales = {}
    for source_id, source in sources.items():
        item = selected[source_id]
        asset = assets[item["assetId"]]
        effective_source = dict(source)
        override = layout_overrides.get(source["id"])
        if override:
            effective_source["center"] = override["target"]["position"]
            effective_source["rotationY"] = override["target"]["rotationYRadians"]
        step = asset["formats"]["step"]
        path = store / step["path"]
        if not path.is_file() or sha256(path) != step["sha256"]:
            raise ValueError(f"{source_id}: selected STEP file/hash mismatch")
        shape, factor = import_and_fit_asset(path, effective_source, item["axisAdapter"])
        group_name = "LIGHTS" if is_light_component(source) else "FURNITURE"
        groups[group_name].append(shape)
        component_scales[source_id] = factor
        entities.append({
            "id": source["id"], "type": "component", "group": group_name,
            "sourceObjectCandidateId": source_id, "traceId": source["traceId"],
            "assetId": item["assetId"], "assetSha256": step["sha256"],
            "roomId": source["roomId"], "roomIds": [source["roomId"]], "semanticType": source["semantic"],
            "category": source.get("categoryHint") or source.get("typeHint") or source["semantic"],
            "functionalClass": source["functionalClass"],
            "quantity": 1,
            "localAxes": asset.get("directionalAxes", {}),
            "dimensionsMeters": [source["bbox"]["width"], source["bbox"]["depth"], source["bbox"]["height"]],
            "worldTransform": {
                "position": [to_cad_xy(structure, effective_source["center"])[0] / 1000, 0, -to_cad_xy(structure, effective_source["center"])[1] / 1000],
                "yawRadians": float(effective_source.get("rotationY", 0)),
            },
            "uniformScale": factor,
            "reviewedAdjustment": override.get("reviewedAdjustment") if override else None,
        })
    from build123d import Compound, Mesher, export_gltf, export_step

    assembly_children = []
    group_selectors = {}
    for name, children in groups.items():
        if children:
            rows = [row for row in entities if row.get("group") == name and row.get("type") != "connection"]
            if len(rows) != len(children):
                raise ValueError(f"{name}: entity/shape count differs before STEP export")
            group_selectors[name] = []
            for row, child_shape in zip(rows, children):
                selector = f"#o1.{len(assembly_children) + 1}"
                row["selector"] = selector
                group_selectors[name].append(selector)
                row.update(shape_bounds_record(child_shape))
                assembly_children.append(child_shape)
    # Keep semantic groups in the entity index, while exporting every
    # renderable object as a top-level occurrence. This avoids ambiguous
    # nested STEP selection where hiding one component can hide its parent.
    assembly = safe_label(Compound(children=assembly_children), f"interior-floorplan::{handoff['floorplanId']}")
    out_step = Path(args.out_step).resolve()
    out_report = Path(args.out_report).resolve()
    out_entities = Path(args.out_entities).resolve()
    for path in (out_step, out_report, out_entities):
        path.parent.mkdir(parents=True, exist_ok=True)
    export_step(assembly, out_step)
    derived = []
    if args.out_glb:
        out_glb = Path(args.out_glb).resolve()
        if out_glb.suffix.lower() != ".glb":
            raise ValueError("--out-glb must use the .glb extension")
        out_glb.parent.mkdir(parents=True, exist_ok=True)
        if not export_gltf(assembly, out_glb, binary=True):
            raise ValueError("build123d export_gltf failed")
        derived.append({"format": "glb", "path": str(out_glb), "sha256": sha256(out_glb), "source": "same-brep-export_gltf"})
    if args.out_mesh:
        out_mesh = Path(args.out_mesh).resolve()
        if out_mesh.suffix.lower() not in {".3mf", ".stl"}:
            raise ValueError("--out-mesh must use a build123d-supported .3mf or .stl extension")
        out_mesh.parent.mkdir(parents=True, exist_ok=True)
        mesher = Mesher()
        mesher.add_shape(assembly)
        mesher.write(out_mesh)
        derived.append({"format": out_mesh.suffix.lower().lstrip("."), "path": str(out_mesh), "sha256": sha256(out_mesh), "source": "same-brep-mesher"})
    directional_axes = []
    seen_asset_roles = set()
    for row in entities:
        if row.get("type") != "component":
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
                "evidence": "cad-native-preview-reviewed-authored-model",
            })
    write_json(out_entities, {
        "schema": "interior.cad-entity-index.v1",
        "floorplanId": handoff["floorplanId"],
        "groupSelectors": group_selectors,
        "relationHints": {
            "schema": "interior.layout-relation-hints.v2",
            "directionalAxes": directional_axes,
            "facing": [],
            "wallAttachment": [],
        },
        "entities": entities,
    })
    report = {
        "schema": "interior.cad-build-report.v1",
        "accepted": True,
        "backend": "cad-step",
        "floorplanId": handoff["floorplanId"],
        "handoffDigestSha256": handoff["handoffDigestSha256"],
        "sourceArtifacts": {
            "handoff": {"path": str(handoff_path), "sha256": sha256(handoff_path)},
            "structureData": {
                "path": str((handoff_path.parent / handoff["artifacts"]["structureData"]["path"]).resolve()),
                "sha256": handoff["artifacts"]["structureData"]["sha256"],
            },
            "traceComponents": {
                "path": str((handoff_path.parent / handoff["artifacts"]["traceComponents"]["path"]).resolve()),
                "sha256": handoff["artifacts"]["traceComponents"]["sha256"],
            },
        },
        "nativeModelPath": str(out_step),
        "nativeModelSha256": sha256(out_step),
        "runtime": {"build123d": importlib.metadata.version("build123d"), "kernel": "OpenCascade/OCP"},
        "coordinateTransform": coordinate_transform(structure),
        "groups": {name: len(children) for name, children in groups.items()},
        "counts": {
            "rooms": len(structure.get("rooms", [])),
            "walls": len(walls),
            "windows": len(structure.get("windows", [])) - sum(opening["wallId"] in replaced_balcony_walls for opening in structure.get("windows", [])),
            "connections": len(structure.get("connections", [])),
            "components": len(sources),
            "lightFixtures": sum(is_light_component(source) for source in sources.values()),
            "ceilings": len(groups["CEILINGS"]),
            "balconyEnvelopes": len(replaced_balcony_walls),
        },
        "entityIndexPath": str(out_entities),
        "entityIndexSha256": sha256(out_entities),
        "selectionSha256": sha256(selection_path),
        "catalogSha256": sha256(catalog_path),
        "backendOptionsSha256": sha256(Path(args.options).resolve()),
        "layoutOverrides": {
            "path": str(overrides_path) if overrides_path else None,
            "sha256": sha256(overrides_path) if overrides_path else None,
            "appliedEntityCount": len(layout_overrides),
        },
        "usageContext": selection.get("usageContext"),
        "redistributionAllowed": all(item.get("licenseDecision") != "research-only" for item in selection.get("items", [])),
        "primitiveFurnitureFallbackCount": 0,
        "derivedModels": derived,
    }
    write_json(out_report, report)
    print(out_step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
