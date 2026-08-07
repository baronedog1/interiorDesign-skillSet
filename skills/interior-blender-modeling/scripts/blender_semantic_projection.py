#!/usr/bin/env python3
"""Compile backend-neutral semantic evidence from native Blender passes."""

from __future__ import annotations

import json
import math
import shutil
import struct
import time
import zlib
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


def semantic_color(index: int) -> tuple[int, int, int]:
    return (
        32 + (index * 73) % 208,
        32 + (index * 151) % 208,
        32 + (index * 199) % 208,
    )


def color_payload(index: int) -> dict:
    red, green, blue = semantic_color(index)
    return {
        "semanticId": index,
        "semanticColor": f"#{red:02x}{green:02x}{blue:02x}",
        "encodedColorValue": (red << 16) | (green << 8) | blue,
        "rgb": (red, green, blue),
    }


def mask_stats(mask: np.ndarray) -> dict:
    rows, columns = np.nonzero(mask)
    height, width = mask.shape
    if not len(columns):
        return {"bbox": None, "visiblePixelCount": 0, "coverage": 0.0}
    return {
        "bbox": [
            round(float(columns.min()) / width, 8),
            round(float(rows.min()) / height, 8),
            round(float(columns.max() + 1) / width, 8),
            round(float(rows.max() + 1) / height, 8),
        ],
        "visiblePixelCount": int(mask.sum()),
        "coverage": round(float(mask.mean()), 8),
    }


def read_scalar_exr(path: Path) -> np.ndarray:
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        width, height = (int(value) for value in image.size)
        pixels = np.asarray(image.pixels[:], dtype=np.float32).reshape((height, width, 4))
        return np.flipud(pixels[:, :, 0].copy())
    finally:
        bpy.data.images.remove(image)


def resize_nearest(image: np.ndarray, width: int, height: int) -> np.ndarray:
    source_height, source_width = image.shape[:2]
    x = np.minimum((np.arange(width) * source_width / width).astype(np.int64), source_width - 1)
    y = np.minimum((np.arange(height) * source_height / height).astype(np.int64), source_height - 1)
    return image[y[:, None], x[None, :]]


def write_rgb_png(path: Path, image: np.ndarray) -> None:
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise RuntimeError("semantic PNG source must be an RGB8 array")
    height, width = image.shape[:2]
    raw = b"".join(b"\x00" + image[row].tobytes() for row in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def canonical_point(structure: dict, source_point: list[float], height: float) -> list[float]:
    coordinate = structure["coordinateSystem"]
    if coordinate.get("origin") == "north-west":
        return [
            float(source_point[0]) - float(coordinate["realWidthMeters"]) / 2,
            float(height),
            float(source_point[1]) - float(coordinate["realDepthMeters"]) / 2,
        ]
    return [float(source_point[0]), float(height), float(source_point[1])]


def room_polygons(structure: dict) -> dict[str, list[tuple[float, float]]]:
    result = {}
    for room in structure.get("rooms", []):
        result[room["id"]] = [
            (point[0], point[2])
            for point in (canonical_point(structure, source, 0) for source in room["polygon"])
        ]
    return result


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]], tolerance: float = 0.003) -> bool:
    x, y = point
    inside = False
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        sx, sy = start
        ex, ey = end
        dx, dy = ex - sx, ey - sy
        cross = abs(dx * (y - sy) - dy * (x - sx))
        if cross <= tolerance * max(math.hypot(dx, dy), 1.0) and min(sx, ex) - tolerance <= x <= max(sx, ex) + tolerance and min(sy, ey) - tolerance <= y <= max(sy, ey) + tolerance:
            return True
        if (sy > y) != (ey > y):
            boundary_x = sx + (y - sy) * dx / dy
            if x < boundary_x:
                inside = not inside
    return inside


def blender_depth_to_canonical(camera, depth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = depth.shape
    columns = (np.arange(width, dtype=np.float64) + 0.5) / width * 2 - 1
    rows = 1 - (np.arange(height, dtype=np.float64) + 0.5) / height * 2
    x, y = np.meshgrid(columns * math.tan(camera.data.angle_x / 2), rows * math.tan(camera.data.angle_y / 2))
    local = np.stack((x, y, -np.ones_like(x)), axis=-1)
    local /= np.linalg.norm(local, axis=-1, keepdims=True)
    rotation = np.asarray(camera.matrix_world.to_3x3(), dtype=np.float64)
    world_direction = local @ rotation.T
    origin = np.asarray(camera.matrix_world.translation, dtype=np.float64)
    world = origin + world_direction * depth[:, :, None]
    canonical = np.empty_like(world)
    canonical[:, :, 0] = world[:, :, 0]
    canonical[:, :, 1] = world[:, :, 2]
    canonical[:, :, 2] = -world[:, :, 1]
    valid = np.isfinite(depth) & (depth > float(camera.data.clip_start)) & (depth < float(camera.data.clip_end))
    return canonical, valid


def room_membership(
    structure: dict,
    shot: dict,
    entity_buffer: np.ndarray,
    entity_rows: list[dict],
    canonical: np.ndarray,
    valid_depth: np.ndarray,
) -> tuple[np.ndarray, list[str]]:
    polygons = room_polygons(structure)
    ordered_rooms = [room["id"] for room in structure.get("rooms", [])]
    room_lookup = {room_id: index for index, room_id in enumerate(ordered_rooms)}
    room_buffer = np.full(entity_buffer.shape, -1, dtype=np.int32)
    entity_by_pass = {int(row["passIndex"]): row for row in entity_rows}
    visible = np.argwhere((entity_buffer > 0) & valid_depth)
    primary = shot["roomId"]
    for row, column in visible:
        point = (float(canonical[row, column, 0]), float(canonical[row, column, 2]))
        candidates = [room_id for room_id in ordered_rooms if point_in_polygon(point, polygons[room_id])]
        entity = entity_by_pass.get(int(entity_buffer[row, column]), {})
        declared = [room_id for room_id in entity.get("roomIds", []) if room_id in room_lookup]
        selected = primary if primary in candidates else (candidates[0] if candidates else None)
        if selected is None:
            selected = primary if primary in declared else (declared[0] if declared else None)
        if selected is not None:
            room_buffer[row, column] = room_lookup[selected]
    return room_buffer, ordered_rooms


def component_semantic_type(entity: dict) -> str:
    raw = " ".join(str(entity.get(key, "")).lower() for key in ("semanticType", "category", "entityType"))
    fixed_tokens = ("fixed", "cabinet", "wardrobe", "vanity", "built-in", "kitchen-unit", "storage-unit")
    return "fixed-cabinet" if any(token in raw for token in fixed_tokens) else "movable-furniture"


def normalized_structure_category(entity: dict) -> str:
    raw = entity.get("category") or entity.get("semanticType") or entity.get("entityType", "structure")
    return {
        "wall-piece": "wall",
        "window-part": "window",
        "balcony-envelope-part": "balcony",
    }.get(raw, raw)


def trace_slot_payload(structure: dict, trace: dict) -> dict:
    center = canonical_point(structure, trace["center"], 0)
    bbox = trace["bbox"]
    width = float(bbox["width"])
    height = float(bbox["height"])
    depth = float(bbox["depth"])
    yaw = float(trace.get("rotationY", 0))
    half_x = abs(math.cos(yaw)) * width / 2 + abs(math.sin(yaw)) * depth / 2
    half_z = abs(math.sin(yaw)) * width / 2 + abs(math.cos(yaw)) * depth / 2
    return {
        "worldBounds": {
            "min": [round(center[0] - half_x, 8), 0.0, round(center[2] - half_z, 8)],
            "max": [round(center[0] + half_x, 8), round(height, 8), round(center[2] + half_z, 8)],
        },
        "worldTransform": {
            "position": [round(center[0], 8), 0.0, round(center[2], 8)],
            "quaternion": [0.0, round(math.sin(yaw / 2), 8), 0.0, round(math.cos(yaw / 2), 8)],
            "scale": [1.0, 1.0, 1.0],
            "yawRadians": round(yaw, 8),
        },
        "dimensionsMeters": [round(width, 8), round(height, 8), round(depth, 8)],
    }


def entity_payload(entity: dict, screen: dict, color: dict, structure: dict, trace_by_id: dict[str, dict]) -> dict:
    is_component = entity.get("entityType") in {"component", "component-part"}
    semantic_type = component_semantic_type(entity) if is_component else "structure"
    trace = trace_by_id.get(entity["entityId"]) if is_component else None
    if is_component and trace is None:
        raise RuntimeError(f"{entity['entityId']}: Blender component has no frozen trace-component fact")
    slot = trace_slot_payload(structure, trace) if trace else {
        "worldBounds": entity["worldBounds"],
        "worldTransform": entity["worldTransform"],
        "dimensionsMeters": entity["dimensionsMeters"],
    }
    return {
        "entityId": entity["entityId"],
        "sourceModelId": entity["entityId"],
        "semanticType": semantic_type,
        "category": trace.get("semantic") if trace else normalized_structure_category(entity),
        "functionalClass": trace.get("functionalClass") if trace else None,
        "quantity": trace.get("quantity") if trace else None,
        "assetId": entity.get("assetId") if is_component else None,
        "sourceObjectCandidateId": trace.get("sourceObjectCandidateId") if trace else None,
        "localAxes": entity.get("localAxes", {}) if is_component else {},
        "displayName": entity["entityId"],
        "roomIds": entity.get("roomIds", []),
        "visibilityState": "visible-in-shot" if screen["visiblePixelCount"] else "not-visible-in-shot",
        "sourceGeometry": "blender-native-object-index-and-depth",
        "placementRole": "source-trace-placement" if is_component else None,
        "priority": None,
        "mustPreserve": bool(entity.get("mustPreserve", False)),
        "forbiddenInferences": [],
        "worldBounds": slot["worldBounds"],
        "worldTransform": slot["worldTransform"],
        "dimensionsMeters": slot["dimensionsMeters"],
        "renderedWorldBounds": entity["worldBounds"] if is_component else None,
        "screen": {
            "semanticId": color["semanticId"],
            "semanticColor": color["semanticColor"],
            "encodedColorValue": color["encodedColorValue"],
            **screen,
        },
    }


def project_point(point: list[float], shot: dict, image_size: tuple[int, int]) -> list[float] | None:
    position = np.asarray(shot["position"], dtype=np.float64)
    target = np.asarray(shot["target"], dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.asarray([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    relative = np.asarray(point, dtype=np.float64) - position
    depth = float(relative @ forward)
    if depth <= 1e-6:
        return None
    horizontal_tangent = 36.0 / (2 * float(shot["focalLengthMm"]))
    vertical_tangent = horizontal_tangent / (image_size[0] / image_size[1])
    x = float(relative @ right) / (depth * horizontal_tangent)
    y = float(relative @ up) / (depth * vertical_tangent)
    return [max(0.0, min(1.0, (x + 1) / 2)), max(0.0, min(1.0, (1 - y) / 2))]


def projected_connections(structure: dict, shot: dict, image_size: tuple[int, int]) -> list[dict]:
    result = []
    position = np.asarray(shot["position"], dtype=np.float64)
    target = np.asarray(shot["target"], dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    for connection in structure.get("connections", []):
        segment = connection.get("segment")
        if not isinstance(segment, list) or len(segment) != 2:
            raise RuntimeError(f"{connection.get('id')}: Blender connection lacks source segment geometry")
        bottom = float(connection.get("bottom", 0))
        top = bottom + float(connection.get("height", 2.1))
        corners = [
            canonical_point(structure, segment[0], bottom),
            canonical_point(structure, segment[1], bottom),
            canonical_point(structure, segment[1], top),
            canonical_point(structure, segment[0], top),
        ]
        depths = [float((np.asarray(corner, dtype=np.float64) - position) @ forward) for corner in corners]
        if any(depth <= 1e-6 for depth in depths):
            continue
        polygon = [project_point(corner, shot, image_size) for corner in corners]
        xs, ys = [point[0] for point in polygon], [point[1] for point in polygon]
        room_ids = [value for value in (connection.get("fromRoomId"), connection.get("toRoomId")) if value]
        result.append({
            "connectionId": connection["id"],
            "sourceModelId": connection["id"],
            "kind": connection.get("kind", "opening"),
            "displayName": connection["id"],
            "roomIds": room_ids,
            "forbiddenInferences": connection.get("forbiddenInferences", []),
            "screen": {
                "polygon": [[round(point[0], 8), round(point[1], 8)] for point in polygon],
                "bbox": [round(min(xs), 8), round(min(ys), 8), round(max(xs), 8), round(max(ys), 8)],
                "source": "front-clipped-projected-model-opening-corners",
                "visibilityEvidence": {
                    "method": "all-opening-corners-in-front-of-camera",
                    "allCornersInFrontOfCamera": True,
                    "minimumForwardDepthMeters": round(min(depths), 8),
                    "maximumForwardDepthMeters": round(max(depths), 8),
                },
            },
        })
    return result


def compile_semantic_frame(
    *,
    plan: dict,
    shot: dict,
    camera,
    entity_index: list[dict],
    slot_guided_image: Path,
    furnished_qa_image: Path,
    depth_path: Path,
    index_path: Path,
    out: Path,
) -> dict:
    started = time.perf_counter()
    structure = json.loads(bpy.context.scene["interiorStructureData"])
    traces = json.loads(bpy.context.scene["interiorTraceComponents"])
    trace_by_id = {row["id"]: row for row in traces.get("objects", [])}
    index_pass = np.rint(read_scalar_exr(index_path)).astype(np.int32)
    depth = read_scalar_exr(depth_path)
    if index_pass.shape != depth.shape:
        raise RuntimeError("Blender Object Index and Depth passes differ in size")
    height, width = depth.shape
    if width != bpy.context.scene.render.resolution_x or height != bpy.context.scene.render.resolution_y:
        raise RuntimeError("Blender native pass resolution differs from the color render")
    valid_indices = {int(row["passIndex"]) for row in entity_index}
    unexpected = set(int(value) for value in np.unique(index_pass)) - valid_indices - {0}
    if unexpected:
        raise RuntimeError(f"Blender Object Index contains unknown IDs: {sorted(unexpected)}")
    canonical, valid_depth = blender_depth_to_canonical(camera, depth)
    room_buffer, ordered_room_ids = room_membership(structure, shot, index_pass, entity_index, canonical, valid_depth)

    ordered_entities = sorted(entity_index, key=lambda row: (row.get("entityType") in {"component", "component-part"}, row["entityId"]))
    entity_image = np.zeros((height, width, 3), dtype=np.uint8)
    entity_rows = []
    for semantic_index, entity in enumerate(ordered_entities, start=1):
        mask = index_pass == int(entity["passIndex"])
        color = color_payload(semantic_index)
        entity_image[mask] = color["rgb"]
        entity_rows.append(entity_payload(entity, mask_stats(mask), color, structure, trace_by_id))

    room_image = np.zeros((height, width, 3), dtype=np.uint8)
    room_rows = []
    structure_rooms = {room["id"]: room for room in structure.get("rooms", [])}
    for room_index, room_id in enumerate(ordered_room_ids):
        mask = room_buffer == room_index
        screen = mask_stats(mask)
        if screen["visiblePixelCount"] <= 0:
            continue
        color = color_payload(4097 + room_index)
        room_image[mask] = color["rgb"]
        room = structure_rooms[room_id]
        room_rows.append({
            "roomId": room_id,
            "displayName": room.get("name", room_id),
            "roomType": room.get("spaceType", "room"),
            "sourcePolygon": room["polygon"],
            "screen": {
                "semanticId": color["semanticId"],
                "semanticColor": color["semanticColor"],
                "encodedColorValue": color["encodedColorValue"],
                **screen,
            },
        })

    raster_width = min(800, width)
    raster_height = max(1, round(height * raster_width / width))
    entity_mask_path = out / f"{shot['shotId']}.semantic-entity-id.png"
    room_mask_path = out / f"{shot['shotId']}.semantic-room-id.png"
    write_rgb_png(entity_mask_path, resize_nearest(entity_image, raster_width, raster_height))
    write_rgb_png(room_mask_path, resize_nearest(room_image, raster_width, raster_height))

    evidence_image_path = out / f"{shot['shotId']}.camera-plan-evidence.png"
    evidence_json_path = out / f"{shot['shotId']}.camera-plan-evidence.json"
    shutil.copy2(furnished_qa_image, evidence_image_path)
    evidence_json_path.write_text(json.dumps({
        "schema": "interior.camera-plan-evidence.v2",
        "source": "same-native-model-camera-state",
        "modelBackend": "blender",
        "sourceModelSha256": plan["sourceModelSha256"],
        "shotId": shot["shotId"],
        "position": shot["position"],
        "target": shot["target"],
        "fov": shot["fov"],
        "focalLengthMm": shot["focalLengthMm"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    frame_path = out / f"{shot['shotId']}.semantic-frame.json"
    frame = {
        "schema": "interior.scene-semantic-frame.v4",
        "modelBackend": "blender",
        "sourceModelSha256": plan["sourceModelSha256"],
        "floorplanId": plan["floorplanId"],
        "modelRevision": plan["sourceModelSha256"][:16],
        "shotId": shot["shotId"],
        "guidanceImages": {"slotGuided": slot_guided_image.name, "furnishedQa": furnished_qa_image.name},
        "imageSize": [width, height],
        "semanticRaster": {
            "size": [raster_width, raster_height],
            "normalizedToImageSize": True,
            "maximumSourcePixelError": round(width / raster_width, 6),
            "policy": "fixed-800px-maximum-width",
        },
        "coordinateSystem": "image-top-left-normalized",
        "camera": {
            "position": shot["position"],
            "target": shot["target"],
            "up": [0, 1, 0],
            "fov": shot["fov"],
            "near": float(camera.data.clip_start),
            "far": float(camera.data.clip_end),
            "aspect": width / height,
        },
        "presentation": {
            "sourceState": "same-model-dual-capture-evidence-on-concrete-shell",
            "defaultGenerationMode": "slot-guided",
            "evidenceStates": {
                "slot-guided": {"componentPresentation": "hidden", "slotFactsRetained": True, "structureAppearance": "concrete-shell", "generationAuthority": True},
                "furnished-qa": {"componentPresentation": "visible", "structureAppearance": "concrete-shell", "generationAuthority": False},
            },
            "styleState": "none",
            "componentAppearanceAuthority": "json-slots-only-for-generation",
        },
        "entitySemanticMask": {
            "encoding": "stable-rgb-entity-id-from-blender-object-index",
            "backgroundColor": "#000000",
            "image": entity_mask_path.name,
            "byteLength": entity_mask_path.stat().st_size,
        },
        "roomSemanticMask": {
            "encoding": "stable-rgb-room-id-from-blender-depth-reprojection",
            "backgroundColor": "#000000",
            "image": room_mask_path.name,
            "byteLength": room_mask_path.stat().st_size,
        },
        "rooms": room_rows,
        "connections": projected_connections(structure, shot, (width, height)),
        "entities": entity_rows,
        "projectionEvidence": {
            "method": "blender-native-object-index-plus-depth-to-room-polygon",
            "elapsedMs": round((time.perf_counter() - started) * 1000, 3),
            "generatedMaskBytes": entity_mask_path.stat().st_size + room_mask_path.stat().st_size,
            "objectIndexPass": index_path.name,
            "depthPass": depth_path.name,
            "nativePassResolution": [width, height],
            "overlapRule": "nearest-visible-blender-surface",
            "roomSearchDirection": "same-frame-depth-reprojection-to-room-polygon",
        },
        "interpretationConstraints": [
            "No screenshot image recognition may alter Blender slot or room coordinates.",
            "Every visible region comes from native Object Index, native Depth, and the same Blender camera frame.",
        ],
    }
    frame_path.write_text(json.dumps(frame, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "semanticFrame": str(frame_path),
        "entitySemanticMask": str(entity_mask_path),
        "roomSemanticMask": str(room_mask_path),
        "cameraPlanEvidence": str(evidence_image_path),
        "cameraPlanEvidenceJson": str(evidence_json_path),
        "visibleEntityCount": sum(row["screen"]["visiblePixelCount"] > 0 for row in entity_rows),
        "visibleRoomCount": len(room_rows),
        "projectionProfile": "blender-native-object-index-depth-room-v1",
    }
