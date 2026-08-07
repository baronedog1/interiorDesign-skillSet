#!/usr/bin/env python3
"""Compile CAD semantic evidence from the accepted STEP topology sidecar."""

from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import struct
import time

import numpy as np
from PIL import Image

from common import read_json, sha256, write_json


COMPONENT_DTYPES = {
    5120: np.dtype("<i1"),
    5121: np.dtype("<u1"),
    5122: np.dtype("<i2"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
ACCESSOR_WIDTHS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


def semantic_color(index: int) -> tuple[int, int, int]:
    # Black remains the only background ID.
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


def world_dimensions(bounds: dict) -> list[float]:
    minimum, maximum = bounds["min"], bounds["max"]
    return [round(float(maximum[index]) - float(minimum[index]), 8) for index in range(3)]


def world_center(bounds: dict) -> list[float]:
    minimum, maximum = bounds["min"], bounds["max"]
    return [round((float(minimum[index]) + float(maximum[index])) / 2, 8) for index in range(3)]


def component_semantic_type(entity: dict) -> str:
    raw = " ".join(str(entity.get(key, "")).lower() for key in ("semanticType", "category", "group"))
    return "fixed-cabinet" if any(token in raw for token in ("fixed", "cabinet", "purple", "built-in")) else "movable-furniture"


def entity_payload(entity: dict, screen: dict, color: dict) -> dict:
    bounds = entity["worldBoundsMeters"]
    is_component = entity.get("type") == "component"
    semantic_type = component_semantic_type(entity) if is_component else "structure"
    yaw = float(entity.get("worldTransform", {}).get("yawRadians", 0))
    position = entity.get("worldTransform", {}).get("position", world_center(bounds))
    dimensions = entity.get("dimensionsMeters", world_dimensions(bounds))
    room_ids = entity.get("roomIds") or ([entity["roomId"]] if entity.get("roomId") else [])
    return {
        "entityId": entity["id"],
        "sourceModelId": entity["id"],
        "semanticType": semantic_type,
        "category": entity.get("category", entity.get("type", "structure")),
        "functionalClass": entity.get("functionalClass") if is_component else None,
        "quantity": entity.get("quantity") if is_component else None,
        "assetId": entity.get("assetId") if is_component else None,
        "sourceObjectCandidateId": entity.get("sourceObjectCandidateId") if is_component else None,
        "localAxes": entity.get("localAxes", {}) if is_component else {},
        "displayName": entity["id"],
        "roomIds": room_ids,
        "visibilityState": "visible-in-shot" if screen["visiblePixelCount"] else "not-visible-in-shot",
        "sourceGeometry": "cad-step-occurrence-topology",
        "placementRole": "source-trace-placement" if is_component else None,
        "priority": None,
        "mustPreserve": False,
        "forbiddenInferences": [],
        "worldBounds": bounds,
        "worldTransform": {
            "position": position,
            "quaternion": [0, round(math.sin(yaw / 2), 10), 0, round(math.cos(yaw / 2), 10)],
            "scale": [1, 1, 1],
            "yawRadians": yaw,
        },
        "dimensionsMeters": dimensions,
        "screen": {
            "semanticId": color["semanticId"],
            "semanticColor": color["semanticColor"],
            "encodedColorValue": color["encodedColorValue"],
            **screen,
        },
    }


def read_glb(path: Path) -> tuple[dict, bytes]:
    payload = path.read_bytes()
    if len(payload) < 20:
        raise RuntimeError("CAD semantic topology GLB is truncated")
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(payload):
        raise RuntimeError("CAD semantic topology is not a valid GLB 2.0 file")
    offset = 12
    document = None
    binary = None
    while offset < len(payload):
        chunk_length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunk = payload[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
        elif chunk_type == 0x004E4942:
            binary = chunk
    if not isinstance(document, dict) or binary is None:
        raise RuntimeError("CAD semantic topology lacks JSON or BIN chunks")
    return document, binary


def accessor_array(document: dict, binary: bytes, accessor_index: int) -> np.ndarray:
    accessor = document["accessors"][accessor_index]
    if accessor.get("sparse"):
        raise RuntimeError("sparse GLB accessors are not supported for CAD semantics")
    view = document["bufferViews"][accessor["bufferView"]]
    if int(view.get("buffer", 0)) != 0:
        raise RuntimeError("external GLB buffers are not supported for CAD semantics")
    dtype = COMPONENT_DTYPES.get(accessor["componentType"])
    width = ACCESSOR_WIDTHS.get(accessor["type"])
    if dtype is None or width is None:
        raise RuntimeError("unsupported CAD semantic topology accessor")
    count = int(accessor["count"])
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    packed_stride = dtype.itemsize * width
    stride = int(view.get("byteStride", packed_stride))
    if stride == packed_stride:
        values = np.frombuffer(binary, dtype=dtype, count=count * width, offset=offset)
        return values.reshape((count, width)).copy()
    return np.ndarray(
        shape=(count, width),
        dtype=dtype,
        buffer=binary,
        offset=offset,
        strides=(stride, dtype.itemsize),
    ).copy()


def quaternion_matrix(values: list[float]) -> np.ndarray:
    x, y, z, w = (float(value) for value in values)
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 1e-12:
        return np.identity(4)
    x, y, z, w = x / length, y / length, z / length, w / length
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1],
        ],
        dtype=np.float64,
    )


def node_matrix(node: dict) -> np.ndarray:
    if isinstance(node.get("matrix"), list) and len(node["matrix"]) == 16:
        return np.asarray(node["matrix"], dtype=np.float64).reshape((4, 4), order="F")
    translation = np.identity(4)
    translation[:3, 3] = np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float64)
    rotation = quaternion_matrix(node.get("rotation", [0, 0, 0, 1]))
    scale = np.identity(4)
    scale_values = np.asarray(node.get("scale", [1, 1, 1]), dtype=np.float64)
    scale[0, 0], scale[1, 1], scale[2, 2] = scale_values
    return translation @ rotation @ scale


def topology_nodes(document: dict) -> tuple[dict[str, int], dict[int, np.ndarray]]:
    nodes = document.get("nodes", [])
    selector_nodes = {}
    world_matrices = {}

    def visit(index: int, parent: np.ndarray) -> None:
        node = nodes[index]
        world = parent @ node_matrix(node)
        world_matrices[index] = world
        selector = str(node.get("extras", {}).get("cadOccurrenceId") or node.get("name") or "").strip()
        if selector:
            selector_nodes[selector] = index
        for child in node.get("children", []):
            visit(int(child), world)

    scene_index = int(document.get("scene", 0))
    for root in document.get("scenes", [])[scene_index].get("nodes", []):
        visit(int(root), np.identity(4))
    return selector_nodes, world_matrices


def descendant_indices(document: dict, root: int) -> list[int]:
    nodes = document["nodes"]
    result = []
    pending = [root]
    while pending:
        index = pending.pop()
        result.append(index)
        pending.extend(int(child) for child in nodes[index].get("children", []))
    return result


def entity_triangles(
    document: dict,
    binary: bytes,
    selector_nodes: dict[str, int],
    world_matrices: dict[int, np.ndarray],
    selector: str,
) -> np.ndarray:
    normalized = selector.removeprefix("#")
    if normalized not in selector_nodes:
        raise RuntimeError(f"CAD semantic topology lacks selector {selector}")
    triangles = []
    for node_index in descendant_indices(document, selector_nodes[normalized]):
        node = document["nodes"][node_index]
        if "mesh" not in node:
            continue
        mesh = document["meshes"][int(node["mesh"])]
        for primitive in mesh.get("primitives", []):
            if int(primitive.get("mode", 4)) != 4:
                raise RuntimeError("CAD semantic topology must use triangle primitives")
            positions = accessor_array(document, binary, int(primitive["attributes"]["POSITION"])).astype(np.float64)
            homogeneous = np.column_stack((positions, np.ones(len(positions))))
            positions = (world_matrices[node_index] @ homogeneous.T).T[:, :3]
            if "indices" in primitive:
                indices = accessor_array(document, binary, int(primitive["indices"])).reshape(-1).astype(np.int64)
            else:
                indices = np.arange(len(positions), dtype=np.int64)
            if len(indices) % 3:
                raise RuntimeError("CAD semantic topology index count is not divisible by three")
            triangles.append(positions[indices].reshape((-1, 3, 3)))
    if not triangles:
        raise RuntimeError(f"CAD semantic topology selector has no triangles: {selector}")
    return np.concatenate(triangles, axis=0)


def camera_basis(camera: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    position = np.asarray(camera["position"], dtype=np.float64) / 1000.0
    target = np.asarray(camera["target"], dtype=np.float64) / 1000.0
    up_seed = np.asarray(camera.get("up", [0, 0, 1]), dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up_seed)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    up /= np.linalg.norm(up)
    return position, right, up, forward


def rasterize_semantics(
    entity_rows: list[dict],
    triangles_by_id: dict[str, np.ndarray],
    shot: dict,
    camera: dict,
    width: int,
    height: int,
    hidden_ids: set[str],
) -> tuple[np.ndarray, np.ndarray, int]:
    position, right, up, forward = camera_basis(camera)
    tan_vertical = math.tan(math.radians(24.0)) / float(camera["zoom"])
    tan_horizontal = tan_vertical * (width / height)
    depth_buffer = np.full((height, width), np.inf, dtype=np.float32)
    entity_buffer = np.full((height, width), -1, dtype=np.int32)
    room_buffer = np.full((height, width), -1, dtype=np.int32)
    room_ids = sorted({room_id for entity in entity_rows for room_id in entity.get("roomIds", [])})
    room_index = {room_id: index for index, room_id in enumerate(room_ids)}
    triangle_count = 0

    for entity_index, entity in enumerate(entity_rows):
        if entity["id"] in hidden_ids:
            continue
        entity_rooms = entity.get("roomIds", [])
        selected_room = shot["roomId"] if shot["roomId"] in entity_rooms else (entity_rooms[0] if entity_rooms else None)
        selected_room_index = room_index.get(selected_room, -1)
        triangles = triangles_by_id[entity["id"]]
        triangle_count += len(triangles)
        relative = triangles - position
        camera_x = relative @ right
        camera_y = relative @ up
        camera_z = relative @ forward
        for points_x, points_y, points_z in zip(camera_x, camera_y, camera_z):
            if np.any(points_z <= 0.01):
                continue
            screen_x = (points_x / (points_z * tan_horizontal) + 1.0) * 0.5 * width
            screen_y = (1.0 - points_y / (points_z * tan_vertical)) * 0.5 * height
            min_x = max(0, int(math.floor(float(screen_x.min()))))
            max_x = min(width - 1, int(math.ceil(float(screen_x.max()))))
            min_y = max(0, int(math.floor(float(screen_y.min()))))
            max_y = min(height - 1, int(math.ceil(float(screen_y.max()))))
            if min_x > max_x or min_y > max_y:
                continue
            x0, x1, x2 = screen_x
            y0, y1, y2 = screen_y
            denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(denominator) <= 1e-12:
                continue
            grid_y, grid_x = np.mgrid[min_y : max_y + 1, min_x : max_x + 1]
            sample_x = grid_x + 0.5
            sample_y = grid_y + 0.5
            weight0 = ((y1 - y2) * (sample_x - x2) + (x2 - x1) * (sample_y - y2)) / denominator
            weight1 = ((y2 - y0) * (sample_x - x2) + (x0 - x2) * (sample_y - y2)) / denominator
            weight2 = 1.0 - weight0 - weight1
            inside = (weight0 >= -1e-7) & (weight1 >= -1e-7) & (weight2 >= -1e-7)
            if not inside.any():
                continue
            inverse_depth = weight0 / points_z[0] + weight1 / points_z[1] + weight2 / points_z[2]
            depth = np.where(inverse_depth > 0, 1.0 / inverse_depth, np.inf)
            target_depth = depth_buffer[min_y : max_y + 1, min_x : max_x + 1]
            closer = inside & (depth < target_depth - 1e-5)
            if not closer.any():
                continue
            target_depth[closer] = depth[closer]
            entity_target = entity_buffer[min_y : max_y + 1, min_x : max_x + 1]
            room_target = room_buffer[min_y : max_y + 1, min_x : max_x + 1]
            entity_target[closer] = entity_index
            room_target[closer] = selected_room_index
    return entity_buffer, room_buffer, triangle_count


def canonical_point(structure: dict, source_point: list[float], height: float) -> list[float]:
    coordinate = structure["coordinateSystem"]
    if coordinate.get("origin") == "north-west":
        return [
            float(source_point[0]) - float(coordinate["realWidthMeters"]) / 2,
            float(height),
            float(source_point[1]) - float(coordinate["realDepthMeters"]) / 2,
        ]
    return [float(source_point[0]), float(height), float(source_point[1])]


def project_point(point: list[float], shot: dict, image_size: tuple[int, int]) -> list[float] | None:
    position = np.asarray(shot["position"], dtype=np.float64)
    target = np.asarray(shot["target"], dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.asarray([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    camera_up = np.cross(right, forward)
    relative = np.asarray(point, dtype=np.float64) - position
    depth = float(relative @ forward)
    if depth <= 1e-6:
        return None
    aspect = image_size[0] / image_size[1]
    horizontal_tangent = 36.0 / (2 * float(shot["focalLengthMm"]))
    vertical_tangent = horizontal_tangent / aspect
    x_ndc = float(relative @ right) / (depth * horizontal_tangent)
    y_ndc = float(relative @ camera_up) / (depth * vertical_tangent)
    return [max(0.0, min(1.0, (x_ndc + 1) / 2)), max(0.0, min(1.0, (1 - y_ndc) / 2))]


def projected_connections(structure: dict, shot: dict, image_size: tuple[int, int]) -> list[dict]:
    result = []
    position = np.asarray(shot["position"], dtype=np.float64)
    target = np.asarray(shot["target"], dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    for connection in structure.get("connections", []):
        segment = connection.get("segment")
        if not isinstance(segment, list) or len(segment) != 2:
            raise RuntimeError(f"{connection.get('id')}: CAD connection lacks source segment geometry")
        bottom = float(connection.get("bottom", 0))
        top = bottom + float(connection.get("height", 2.1))
        corners = [
            canonical_point(structure, segment[0], bottom),
            canonical_point(structure, segment[1], bottom),
            canonical_point(structure, segment[1], top),
            canonical_point(structure, segment[0], top),
        ]
        depths = [float((np.asarray(point, dtype=np.float64) - position) @ forward) for point in corners]
        if any(depth <= 1e-6 for depth in depths):
            continue
        polygon = [project_point(point, shot, image_size) for point in corners]
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
    command: list[str],
    manifest: dict,
    entity_index: dict,
    shot: dict,
    camera: dict,
    model: Path,
    slot_guided_image: Path,
    furnished_qa_image: Path,
    out: Path,
    base_hidden: set[str],
) -> dict:
    del command, model
    started = time.perf_counter()
    with Image.open(furnished_qa_image) as reference:
        width, height = reference.size
    structure_artifact = Path(manifest["sourceArtifacts"]["structureData"]["path"]).resolve()
    if not structure_artifact.is_file() or sha256(structure_artifact) != manifest["sourceArtifacts"]["structureData"]["sha256"]:
        raise RuntimeError("CAD semantic projection structure artifact/hash mismatch")
    structure = read_json(structure_artifact)
    topology_record = manifest.get("semanticTopology", {})
    topology_path = Path(topology_record.get("path", "")).resolve()
    if not topology_path.is_file() or sha256(topology_path) != topology_record.get("sha256"):
        raise RuntimeError("CAD semantic topology file/hash mismatch")
    document, binary = read_glb(topology_path)
    selector_nodes, world_matrices = topology_nodes(document)
    renderable = [row for row in entity_index.get("entities", []) if row.get("selector") and row.get("type") != "connection"]
    triangles_by_id = {
        entity["id"]: entity_triangles(document, binary, selector_nodes, world_matrices, entity["selector"])
        for entity in renderable
    }
    hidden_ids = {
        entity["id"]
        for entity in renderable
        if entity["selector"] in base_hidden
    }
    entity_buffer, room_buffer, triangle_count = rasterize_semantics(
        renderable,
        triangles_by_id,
        shot,
        camera,
        width,
        height,
        hidden_ids,
    )

    ordered_entities = sorted(renderable, key=lambda row: row.get("type") == "component")
    original_index = {entity["id"]: index for index, entity in enumerate(renderable)}
    entity_image = np.zeros((height, width, 3), dtype=np.uint8)
    entity_rows = []
    for semantic_index, entity in enumerate(ordered_entities, start=1):
        mask = entity_buffer == original_index[entity["id"]]
        color = color_payload(semantic_index)
        entity_image[mask] = color["rgb"]
        entity_rows.append(entity_payload(entity, mask_stats(mask), color))

    room_ids = sorted({room_id for entity in renderable for room_id in (entity.get("roomIds") or [])})
    room_index = {room_id: index for index, room_id in enumerate(room_ids)}
    room_image = np.zeros((height, width, 3), dtype=np.uint8)
    room_rows = []
    for semantic_index, room in enumerate(structure.get("rooms", []), start=4097):
        mask = room_buffer == room_index.get(room["id"], -2)
        screen = mask_stats(mask)
        if screen["visiblePixelCount"] <= 0:
            continue
        color = color_payload(semantic_index)
        room_image[mask] = color["rgb"]
        room_rows.append({
            "roomId": room["id"],
            "displayName": room.get("name", room["id"]),
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
    entity_mask_path = out / "images" / f"{shot['shotId']}.semantic-entity-id.png"
    room_mask_path = out / "images" / f"{shot['shotId']}.semantic-room-id.png"
    Image.fromarray(entity_image).resize((raster_width, raster_height), Image.Resampling.NEAREST).save(entity_mask_path)
    Image.fromarray(room_image).resize((raster_width, raster_height), Image.Resampling.NEAREST).save(room_mask_path)

    evidence_image_path = out / "images" / f"{shot['shotId']}.camera-plan-evidence.png"
    evidence_json_path = out / "images" / f"{shot['shotId']}.camera-plan-evidence.json"
    shutil.copy2(furnished_qa_image, evidence_image_path)
    write_json(evidence_json_path, {
        "schema": "interior.camera-plan-evidence.v2",
        "source": "same-native-model-camera-state",
        "modelBackend": "cad-step",
        "sourceModelSha256": manifest["nativeModel"]["sha256"],
        "shotId": shot["shotId"],
        "position": shot["position"],
        "target": shot["target"],
        "fov": shot["fov"],
        "focalLengthMm": shot["focalLengthMm"],
    })

    frame_path = out / "images" / f"{shot['shotId']}.semantic-frame.json"
    frame = {
        "schema": "interior.scene-semantic-frame.v4",
        "modelBackend": "cad-step",
        "sourceModelSha256": manifest["nativeModel"]["sha256"],
        "floorplanId": manifest["floorplanId"],
        "modelRevision": manifest["nativeModel"]["sha256"][:16],
        "shotId": shot["shotId"],
        "guidanceImages": {
            "slotGuided": slot_guided_image.name,
            "furnishedQa": furnished_qa_image.name,
        },
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
            "near": 0.01,
            "far": 120,
            "aspect": width / height,
        },
        "presentation": {
            "sourceState": "same-model-dual-capture-evidence-on-concrete-shell",
            "defaultGenerationMode": "slot-guided",
            "evidenceStates": {
                "slot-guided": {
                    "componentPresentation": "hidden",
                    "slotFactsRetained": True,
                    "structureAppearance": "concrete-shell",
                    "generationAuthority": True,
                },
                "furnished-qa": {
                    "componentPresentation": "visible",
                    "structureAppearance": "concrete-shell",
                    "generationAuthority": False,
                },
            },
            "styleState": "none",
            "componentAppearanceAuthority": "json-slots-only-for-generation",
        },
        "entitySemanticMask": {
            "encoding": "stable-rgb-entity-id-from-step-topology-zbuffer",
            "backgroundColor": "#000000",
            "image": entity_mask_path.name,
            "byteLength": entity_mask_path.stat().st_size,
        },
        "roomSemanticMask": {
            "encoding": "stable-rgb-room-id-from-step-topology-zbuffer",
            "backgroundColor": "#000000",
            "image": room_mask_path.name,
            "byteLength": room_mask_path.stat().st_size,
        },
        "rooms": room_rows,
        "connections": projected_connections(structure, shot, (width, height)),
        "entities": entity_rows,
        "projectionEvidence": {
            "method": "cad-same-brep-topology-zbuffer-to-room-polygon",
            "elapsedMs": round((time.perf_counter() - started) * 1000, 3),
            "generatedMaskBytes": entity_mask_path.stat().st_size + room_mask_path.stat().st_size,
            "semanticTopologySha256": topology_record["sha256"],
            "topologyTriangleCount": triangle_count,
            "softwareZBufferResolution": [width, height],
            "overlapRule": "nearest-visible-step-triangle",
            "roomSearchDirection": "same-step-topology-visible-surface-membership",
        },
        "interpretationConstraints": [
            "No screenshot image recognition may alter CAD slot or room coordinates.",
            "Every visible region comes from the STEP-derived occurrence topology and the same native camera.",
        ],
    }
    write_json(frame_path, frame)
    return {
        "semanticFrame": str(frame_path),
        "entitySemanticMask": str(entity_mask_path),
        "roomSemanticMask": str(room_mask_path),
        "cameraPlanEvidence": str(evidence_image_path),
        "cameraPlanEvidenceJson": str(evidence_json_path),
        "visibleEntityCount": sum(row["screen"]["visiblePixelCount"] > 0 for row in entity_rows),
        "visibleRoomCount": len(room_rows),
        "topologyTriangleCount": triangle_count,
    }
