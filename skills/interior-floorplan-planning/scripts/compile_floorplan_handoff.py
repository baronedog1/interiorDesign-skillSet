#!/usr/bin/env python3
"""Compile one reviewed source-bound floorplan model into floorplan-handoff.v3."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from validate_source_model import build_normalized_ink_mask


SOURCE_SCHEMA = "interior.floorplan-source-model.v2"
REVIEW_SCHEMA = "interior.floorplan-agent-review.v1"
HANDOFF_SCHEMA = "interior.floorplan-handoff.v3"
PRODUCER_VERSION = "9.0.0"
SOURCE_ORIENTATION_ANGLE_UNIT = "degrees"
OPENING_KINDS = {
    "door",
    "sliding-door",
    "open-passage",
    "window",
    "fixed-glazing",
}
TRAVERSABLE_KINDS = {"door", "sliding-door", "open-passage"}
BOUNDARY_KINDS = {"railing", "parapet", "open-edge", "full-height-glazing"}
SEMANTIC_DIVIDER_TRAVERSALS = {"open-passage", "boundary-only"}
SEMANTICS = {"movable-green", "fixed-purple"}
ORIENTATION_ROLES = {"front", "back", "headboard"}
AXES = {"+X", "-X", "+Z", "-Z"}
ENCLOSED_SPACE_TYPES = {"bedroom", "bathroom", "study", "closet", "storage"}
MODULAR_RUN_CLASSES = {"base-cabinet", "wall-cabinet"}
MODULE_TARGET_WIDTH_M = 0.6
MODULE_SPLIT_MIN_WIDTH_M = 0.9

PIXEL_SUPPORT_TOLERANCE_PX = 3.0
PIXEL_SUPPORT_MIN_RATIO = 0.90
OBJECT_INK_RECALL_MIN_RATIO = 0.62


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _polyline_mask(shape: tuple[int, int], points: list[list[float]], *, closed: bool = False) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    if len(points) < 2:
        return mask
    line = np.round(np.asarray(points, dtype=np.float32)).astype(np.int32)
    cv2.polylines(mask, [line], closed, 1, 1, cv2.LINE_AA)
    return mask


def _support_metrics(distance: np.ndarray, points: list[list[float]], *, closed: bool = False) -> dict:
    mask = _polyline_mask(distance.shape, points, closed=closed)
    values = distance[mask > 0]
    if not values.size:
        return {"samplePixels": 0, "p95DistancePx": None, "within3PxRatio": 0.0}
    return {
        "samplePixels": int(values.size),
        "p95DistancePx": round(float(np.percentile(values, 95)), 3),
        "within3PxRatio": round(float((values <= PIXEL_SUPPORT_TOLERANCE_PX).mean()), 4),
    }


def _wall_faces(wall: dict) -> tuple[list[list[float]], list[list[float]]]:
    start, end = wall["centerline"]
    dx = float(end[0]) - float(start[0])
    dy = float(end[1]) - float(start[1])
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return [], []
    half = float(wall["thicknessPx"]) / 2
    nx, ny = -dy / length * half, dx / length * half
    return (
        [[start[0] + nx, start[1] + ny], [end[0] + nx, end[1] + ny]],
        [[start[0] - nx, start[1] - ny], [end[0] - nx, end[1] - ny]],
    )


def source_pixel_audit(model: dict, image: Image.Image) -> tuple[dict, list[str]]:
    """Independently prove authored vectors are supported by source ink.

    This is deliberately separate from topology and Agent review. A self-consistent
    room graph cannot make a red wall or furniture box true when it lands on the
    source background.
    """
    rgb = np.asarray(image.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    _, ink, _ = build_normalized_ink_mask(bgr)
    distance = cv2.distanceTransform(1 - ink, cv2.DIST_L2, 5)
    errors: list[str] = []
    unsupported_trace_pixels = 0
    supported_trace_pixels = 0
    unexplained_object_pixels = 0
    wall_metrics: list[dict] = []
    opening_metrics: list[dict] = []
    object_metrics: list[dict] = []

    def inspect(entity_id: str, role: str, points: list[list[float]], *, closed: bool = False) -> dict:
        nonlocal unsupported_trace_pixels, supported_trace_pixels
        metrics = _support_metrics(distance, points, closed=closed)
        mask = _polyline_mask(distance.shape, points, closed=closed)
        values = distance[mask > 0]
        unsupported_trace_pixels += int((values > PIXEL_SUPPORT_TOLERANCE_PX).sum())
        supported_trace_pixels += int((values <= PIXEL_SUPPORT_TOLERANCE_PX).sum())
        if (
            metrics["samplePixels"] == 0
            or metrics["p95DistancePx"] is None
            or metrics["p95DistancePx"] > PIXEL_SUPPORT_TOLERANCE_PX
            or metrics["within3PxRatio"] < PIXEL_SUPPORT_MIN_RATIO
        ):
            errors.append(
                f"{entity_id}/{role}: authored line is not on source ink "
                f"(p95={metrics['p95DistancePx']}, within3={metrics['within3PxRatio']})"
            )
        return {"entityId": entity_id, "role": role, **metrics}

    for wall in model.get("walls", []):
        face_a, face_b = _wall_faces(wall)
        wall_metrics.append(inspect(wall["id"], "wall-face-a", face_a))
        wall_metrics.append(inspect(wall["id"], "wall-face-b", face_b))

    for opening in model.get("openings", []):
        if opening.get("kind") == "open-passage":
            continue
        opening_metrics.append(
            inspect(opening["id"], f"{opening.get('kind')}-symbol", opening.get("segment", []))
        )

    for item in model.get("objects", []):
        outline = item.get("outline", [])
        row = inspect(item["id"], "object-outline", outline, closed=True)
        trace_mask = _polyline_mask(distance.shape, outline, closed=True)
        for detail_index, detail in enumerate(item.get("details", [])):
            detail_row = inspect(item["id"], f"object-detail-{detail_index + 1}", detail)
            row.setdefault("details", []).append(detail_row)
            trace_mask = np.maximum(trace_mask, _polyline_mask(distance.shape, detail))
        polygon_mask = np.zeros(distance.shape, dtype=np.uint8)
        if len(outline) >= 3:
            polygon = np.round(np.asarray(outline, dtype=np.float32)).astype(np.int32)
            cv2.fillPoly(polygon_mask, [polygon], 1)
        explained = cv2.dilate(trace_mask, np.ones((7, 7), np.uint8), iterations=1)
        source_inside = (ink > 0) & (polygon_mask > 0)
        source_ink_pixels = int(source_inside.sum())
        explained_ink_pixels = int((source_inside & (explained > 0)).sum())
        ink_recall = explained_ink_pixels / source_ink_pixels if source_ink_pixels else 1.0
        unexplained = max(0, source_ink_pixels - explained_ink_pixels)
        unexplained_object_pixels += unexplained
        row.update({
            "sourceInkPixels": source_ink_pixels,
            "explainedInkPixels": explained_ink_pixels,
            "sourceInkRecall": round(ink_recall, 4),
            "detailCount": len(item.get("details", [])),
        })
        if source_ink_pixels >= 24 and ink_recall < OBJECT_INK_RECALL_MIN_RATIO:
            errors.append(
                f"{item['id']}: object trace explains only {ink_recall:.1%} of source ink; "
                "a bounding rectangle without visible internal lines is forbidden"
            )
        object_metrics.append(row)

    return {
        "schema": "interior.floorplan-source-pixel-audit.v1",
        "method": "normalized-source-ink-independent-recompute-v1",
        "tolerancePx": PIXEL_SUPPORT_TOLERANCE_PX,
        "minimumSupportRatio": PIXEL_SUPPORT_MIN_RATIO,
        "objectInkRecallMinimum": OBJECT_INK_RECALL_MIN_RATIO,
        "wallFaces": wall_metrics,
        "openingSymbols": opening_metrics,
        "objects": object_metrics,
        "unsupportedTracePixels": unsupported_trace_pixels,
        "supportedTracePixels": supported_trace_pixels,
        "unexplainedObjectPixels": unexplained_object_pixels,
        "passed": not errors,
    }, errors


def canonical_digest(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def polygon_area(points: list[list[float]]) -> float:
    return abs(sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )) / 2


def point_in_polygon(point: list[float], polygon: list[list[float]]) -> bool:
    x, y = point
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        x1, y1 = first
        x2, y2 = second
        cross = abs((x - x1) * (y2 - y1) - (y - y1) * (x2 - x1))
        if cross <= 1e-6 and min(x1, x2) - 1e-6 <= x <= max(x1, x2) + 1e-6 \
                and min(y1, y2) - 1e-6 <= y <= max(y1, y2) + 1e-6:
            return True
    inside = False
    for first, second in zip(polygon, polygon[-1:] + polygon[:-1]):
        x1, y1 = first
        x2, y2 = second
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
    return inside


def polygon_inside_polygon(subject: list[list[float]], boundary: list[list[float]], step_px: float = 2.0) -> bool:
    """Check complete edges, not only vertices, against a concave boundary."""
    for first, second in zip(subject, subject[1:] + subject[:1]):
        length = math.hypot(second[0] - first[0], second[1] - first[1])
        steps = max(1, math.ceil(length / step_px))
        for index in range(steps + 1):
            ratio = index / steps
            if not point_in_polygon([
                first[0] + (second[0] - first[0]) * ratio,
                first[1] + (second[1] - first[1]) * ratio,
            ], boundary):
                return False
    return True


def finite_point(point: object) -> bool:
    return (
        isinstance(point, list)
        and len(point) == 2
        and all(isinstance(value, (int, float)) and math.isfinite(value) for value in point)
    )


def signed_polygon_area(points: list[list[float]]) -> float:
    return sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    ) / 2


def polygon_perimeter(points: list[list[float]]) -> float:
    return sum(
        math.dist(points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )


def concavity_count(points: list[list[float]]) -> int:
    orientation = 1 if signed_polygon_area(points) >= 0 else -1
    count = 0
    for index, current in enumerate(points):
        previous = points[(index - 1) % len(points)]
        following = points[(index + 1) % len(points)]
        cross = (
            (current[0] - previous[0]) * (following[1] - current[1])
            - (current[1] - previous[1]) * (following[0] - current[0])
        )
        if abs(cross) > 1e-9 and (1 if cross > 0 else -1) != orientation:
            count += 1
    return count


def computed_curve_edge_ratio(points: list[list[float]]) -> float:
    """Measure genuinely diagonal sampled perimeter after axis normalization."""
    if len(points) < 8:
        return 0.0
    total = polygon_perimeter(points)
    if total <= 1e-9:
        return 0.0
    curved = 0.0
    for first, second in zip(points, points[1:] + points[:1]):
        dx = abs(second[0] - first[0])
        dy = abs(second[1] - first[1])
        length = math.hypot(dx, dy)
        # Source yaw is rounded. Classify by edge angle, so tiny residual rotation
        # cannot turn a four-sided straight object into a curved one.
        if length > 1e-9 and min(dx, dy) / length > math.sin(math.radians(2)):
            curved += length
    return curved / total


def derived_l_shape_handedness(points: list[list[float]], item: dict) -> str:
    """Derive the extended side from the source footprint and declared local front."""
    front_axis = item.get("orientation", {}).get("localAxes", {}).get("front", "+Z")
    front_value = max(point[1] for point in points) if front_axis == "+Z" else min(
        point[1] for point in points
    )
    tolerance = max(1e-6, (max(point[1] for point in points) - min(
        point[1] for point in points
    )) * 0.05)
    front_points = [
        point for point in points
        if abs(point[1] - front_value) <= tolerance
    ]
    if not front_points:
        front_points = points
    return "left" if sum(point[0] for point in front_points) / len(front_points) < 0 else "right"


def derive_shape_class(
    normalized: list[list[float]],
    item: dict,
    curve_ratio: float,
    circularity: float,
    concavities: int,
) -> tuple[str, str]:
    """Compile the only shape classification from source geometry."""
    if concavities:
        if curve_ratio >= 0.35:
            return "organic", "none"
        if concavities == 1:
            return "l-shaped", derived_l_shape_handedness(normalized, item)
        return "u-shaped", "none"
    if len(normalized) >= 8 and curve_ratio >= 0.8 and circularity >= 0.72:
        return "round", "none"
    if len(normalized) >= 8 and curve_ratio >= 0.35:
        return "curved", "none"
    return "rectilinear", "none"


def inspect_shape_contract(item: dict, normalized: list[list[float]]) -> tuple[dict, list[str]]:
    """Own the same shape facts consumed by the HTML asset matcher."""
    object_id = item.get("id", "<object>")
    errors: list[str] = []
    if len({tuple(point) for point in normalized}) < 4:
        errors.append(f"{object_id}: normalized outline needs four unique points")
        return {}, errors
    area = abs(signed_polygon_area(normalized))
    perimeter = polygon_perimeter(normalized)
    circularity = 4 * math.pi * area / (perimeter * perimeter) if perimeter > 0 else 0.0
    curve_ratio = computed_curve_edge_ratio(normalized)
    concavities = concavity_count(normalized)
    shape_class, handedness = derive_shape_class(
        normalized,
        item,
        curve_ratio,
        circularity,
        concavities,
    )
    if not (0.08 < area <= 1.001):
        errors.append(f"{object_id}: normalized outline area is outside the valid range")
    return {
        "shapeClass": shape_class,
        "classificationSource": "compiled-source-outline-v1",
        "curveEdgeRatio": round(curve_ratio, 6),
        "handedness": handedness,
        "areaRatio": round(area, 6),
        "circularity": round(circularity, 6),
        "concavityCount": concavities,
        "pointCount": len(normalized),
    }, errors


def inspect_source_object_shape(item: dict, model: dict) -> tuple[dict, list[str]]:
    try:
        x0, y0, x1, y1 = map(float, model["planBounds"])
        known = model["knownSizeMm"]
        scale_x = float(known["width"]) / 1000 / (x1 - x0)
        scale_z = float(known["depth"]) / 1000 / (y1 - y0)
        points = [
            [(point[0] - x0) * scale_x, (point[1] - y0) * scale_z]
            for point in item.get("outline", [])
        ]
        yaw, _ = canonical_object_orientation(
            item,
            model.get("orientationAngleUnit"),
        )
        geometry = oriented_geometry(points, yaw)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        return {}, [f"{item.get('id', '<object>')}: cannot normalize shape outline: {error}"]
    return inspect_shape_contract(item, geometry["normalized"])


def segment_frame(segment: list[list[float]]) -> dict:
    dx = float(segment[1][0]) - float(segment[0][0])
    dy = float(segment[1][1]) - float(segment[0][1])
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        raise ValueError("segment must have non-zero length")
    return {"length": length, "ux": dx / length, "uy": dy / length}


def segment_binding(
    segment: list[list[float]],
    wall: dict,
    room_pair: set[str] | None = None,
    minimum_tolerance: float = 2.0,
    minimum_overlap: float = 2.0,
) -> dict | None:
    """Return a complete source-space binding, never a clipped partial overlap."""
    adjacent = set(wall.get("adjacentRoomIds", []))
    if room_pair is not None and not room_pair <= adjacent:
        return None
    centerline = wall.get("centerline", [])
    if len(segment) != 2 or len(centerline) != 2:
        return None
    try:
        frame = segment_frame(centerline)
    except (TypeError, ValueError):
        return None
    tolerance = max(minimum_tolerance, float(wall.get("thicknessPx", 0)) * 0.65)

    def projection(point: list[float]) -> float:
        return (
            (float(point[0]) - float(centerline[0][0])) * frame["ux"]
            + (float(point[1]) - float(centerline[0][1])) * frame["uy"]
        )

    def line_distance(point: list[float]) -> float:
        return abs(
            (float(point[0]) - float(centerline[0][0])) * frame["uy"]
            - (float(point[1]) - float(centerline[0][1])) * frame["ux"]
        )

    if any(line_distance(point) > tolerance for point in segment):
        return None
    lower, upper = sorted(projection(point) for point in segment)
    if lower < -tolerance or upper > frame["length"] + tolerance:
        return None
    lower = max(0.0, lower)
    upper = min(frame["length"], upper)
    if upper - lower <= minimum_overlap:
        return None
    return {
        "wallId": wall["id"],
        "offset": (lower + upper) / 2,
        "start": lower,
        "end": upper,
    }


def duplicate_source_walls(walls: list[dict], context: str = "source") -> list[str]:
    errors: list[str] = []
    usable = [wall for wall in walls if len(wall.get("centerline", [])) == 2]
    for index, first in enumerate(usable):
        try:
            first_frame = segment_frame(first["centerline"])
        except (TypeError, ValueError):
            continue
        for second in usable[index + 1:]:
            try:
                second_frame = segment_frame(second["centerline"])
            except (TypeError, ValueError):
                continue
            parallel = abs(
                first_frame["ux"] * second_frame["uy"]
                - first_frame["uy"] * second_frame["ux"]
            )
            if parallel > 0.015:
                continue
            normal_x, normal_y = -first_frame["uy"], first_frame["ux"]
            separation = abs(
                (second["centerline"][0][0] - first["centerline"][0][0]) * normal_x
                + (second["centerline"][0][1] - first["centerline"][0][1]) * normal_y
            )
            tolerance = max(
                float(first.get("thicknessPx", 0)),
                float(second.get("thicknessPx", 0)),
            ) * 0.75
            if separation > tolerance:
                continue

            def projection(point: list[float]) -> float:
                return point[0] * first_frame["ux"] + point[1] * first_frame["uy"]

            first_range = sorted(projection(point) for point in first["centerline"])
            second_range = sorted(projection(point) for point in second["centerline"])
            overlap = min(first_range[1], second_range[1]) - max(first_range[0], second_range[0])
            if overlap > min(first_frame["length"], second_frame["length"]) * 0.5:
                errors.append(
                    f"{first['id']} and {second['id']}: duplicate near-collinear wall centerlines; "
                    f"split the {context} boundary into non-overlapping semantic wall segments"
                )
    return errors


def validate_source_geometry(model: dict) -> list[str]:
    """Validate the producer contract before drawing or writing a handoff."""
    errors = duplicate_source_walls(model.get("walls", []))
    walls = [wall for wall in model.get("walls", []) if wall.get("id")]
    wall_by_id = {wall["id"]: wall for wall in walls}
    apertures_by_wall: dict[str, list[dict]] = {}
    for opening in model.get("openings", []):
        opening_id = opening.get("id", "<opening>")
        segment = opening.get("segment", [])
        if len(segment) != 2 or not all(finite_point(point) for point in segment):
            continue
        room_pair = {opening.get("fromRoomId"), opening.get("toRoomId")}
        host_id = opening.get("hostWallId")
        host = wall_by_id.get(host_id)
        if host is None:
            continue
        host_binding = segment_binding(segment, host, room_pair)
        if host_binding is None:
            errors.append(
                f"{opening_id}: segment, hostWallId and room endpoints do not describe the same wall aperture"
            )
        bindings = [
            binding
            for wall in walls
            if (binding := segment_binding(segment, wall, room_pair)) is not None
        ]
        if len(bindings) != 1:
            errors.append(
                f"{opening_id}: physical aperture must bind exactly one wall; "
                f"found {[binding['wallId'] for binding in bindings]}"
            )
        elif bindings[0]["wallId"] != host_id:
            errors.append(
                f"{opening_id}: declared host {host_id} differs from geometric host {bindings[0]['wallId']}"
            )
        else:
            apertures_by_wall.setdefault(host_id, []).append({
                "id": opening_id,
                "start": bindings[0]["start"],
                "end": bindings[0]["end"],
            })
    for wall_id, apertures in apertures_by_wall.items():
        apertures.sort(key=lambda row: (row["start"], row["id"]))
        for previous, current in zip(apertures, apertures[1:]):
            if previous["end"] + 2.0 > current["start"]:
                errors.append(
                    f"{wall_id}: physical apertures overlap: {previous['id']} / {current['id']}"
                )
    return errors


def validate_compiled_structure(structure: dict) -> list[str]:
    """Mirror the cross-Skill geometry contract at the producing Skill boundary."""
    errors: list[str] = []
    walls = structure.get("walls", [])
    windows = structure.get("windows", [])
    connections = structure.get("connections", [])
    wall_by_id = {wall.get("id"): wall for wall in walls}
    metric_walls = [{
        "id": wall["id"],
        "centerline": [wall["start"], wall["end"]],
        "thicknessPx": wall.get("thickness", 0.12),
        "adjacentRoomIds": wall.get("adjacentRoomIds", []),
    } for wall in walls]
    errors.extend(duplicate_source_walls(metric_walls, context="compiled"))
    for window in windows:
        wall = wall_by_id.get(window.get("wallId"))
        if wall is None:
            errors.append(f"{window.get('id')}: compiled host wall is missing")
            continue
        length = math.dist(wall["start"], wall["end"])
        start = float(window.get("offset", 0)) - float(window.get("width", 0)) / 2
        end = float(window.get("offset", 0)) + float(window.get("width", 0)) / 2
        if start < -1e-6 or end > length + 1e-6:
            errors.append(f"{window.get('id')}: compiled window leaves host wall {wall['id']}")

    def metric_binding(connection: dict, wall: dict) -> dict | None:
        room_pair = {connection.get("fromRoomId"), connection.get("toRoomId")}
        if not room_pair <= set(wall.get("adjacentRoomIds", [])):
            return None
        segment = [connection.get("start", []), connection.get("end", [])]
        source_wall = {
            "id": wall["id"],
            "centerline": [wall["start"], wall["end"]],
            "thicknessPx": max(0.054, float(wall.get("thickness", 0.12))) / 0.65,
            "adjacentRoomIds": wall.get("adjacentRoomIds", []),
        }
        return segment_binding(
            segment,
            source_wall,
            room_pair,
            minimum_tolerance=0.035,
            minimum_overlap=0.04,
        )

    for connection in connections:
        if not connection.get("sourceTraceIds"):
            continue
        bindings = [
            binding
            for wall in walls
            if (binding := metric_binding(connection, wall)) is not None
        ]
        if len(bindings) != 1:
            errors.append(
                f"{connection.get('id')}: compiled physical aperture must bind exactly one wall; "
                f"found {[binding['wallId'] for binding in bindings]}"
            )
    room_ids = {room.get("id") for room in structure.get("rooms", []) if room.get("id")}
    graph: dict[str, set[str]] = {room_id: set() for room_id in room_ids}
    graph["exterior"] = set()
    room_connection_kinds: dict[str, set[str]] = {room_id: set() for room_id in room_ids}
    for connection in connections:
        if connection.get("kind") not in TRAVERSABLE_KINDS:
            continue
        left = connection.get("fromRoomId")
        right = connection.get("toRoomId")
        if left in graph and right in graph:
            graph[left].add(right)
            graph[right].add(left)
        if left in room_connection_kinds:
            room_connection_kinds[left].add(connection.get("kind"))
        if right in room_connection_kinds:
            room_connection_kinds[right].add(connection.get("kind"))
    reachable = {"exterior"}
    pending = ["exterior"]
    while pending:
        current = pending.pop()
        for neighbor in graph.get(current, set()):
            if neighbor not in reachable:
                reachable.add(neighbor)
                pending.append(neighbor)
    missing = sorted(room_ids - reachable)
    if missing:
        errors.append(
            f"every room needs an evidenced traversable path to exterior; missing {missing}"
        )
    for room in structure.get("rooms", []):
        room_id = room.get("id")
        if room.get("topologyClass") == "enclosed" and not {
            "door", "sliding-door",
        }.intersection(room_connection_kinds.get(room_id, set())):
            errors.append(f"{room_id}: enclosed room needs a real door or sliding-door access")
    return errors


def validate_source_model(model: dict, source: Path, image: Image.Image) -> list[str]:
    errors: list[str] = []
    if model.get("schema") != SOURCE_SCHEMA:
        errors.append(f"schema must be {SOURCE_SCHEMA}")
    if model.get("orientationAngleUnit") != SOURCE_ORIENTATION_ANGLE_UNIT:
        errors.append(
            "orientationAngleUnit must be explicitly set to degrees; "
            "unitless or alternate rotationY conventions are ambiguous"
        )
    if model.get("sourceSha256") != digest(source):
        errors.append("sourceSha256 does not match the supplied source image")
    if not model.get("floorplanId"):
        errors.append("floorplanId is required")
    bounds = model.get("planBounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        errors.append("planBounds must be [x0,y0,x1,y1]")
    elif not all(isinstance(value, (int, float)) for value in bounds):
        errors.append("planBounds must be numeric")
    elif not (0 <= bounds[0] < bounds[2] <= image.width and 0 <= bounds[1] < bounds[3] <= image.height):
        errors.append("planBounds leaves the active source region")
    known = model.get("knownSizeMm", {})
    if not (known.get("width", 0) > 0 and known.get("depth", 0) > 0):
        errors.append("knownSizeMm.width/depth must be positive")

    ids: set[str] = set()
    room_ids = {room.get("id") for room in model.get("rooms", [])}
    if not room_ids or None in room_ids:
        errors.append("rooms need unique non-empty IDs")
    if len(room_ids) != len(model.get("rooms", [])):
        errors.append("room IDs must be unique")
    for room in model.get("rooms", []):
        if room.get("id") in ids:
            errors.append(f"duplicate ID: {room.get('id')}")
        ids.add(room.get("id"))
        polygon = room.get("polygon", [])
        if len(polygon) < 3 or not all(finite_point(point) for point in polygon):
            errors.append(f"{room.get('id')}: room polygon is invalid")
        elif polygon_area(polygon) <= 16:
            errors.append(f"{room.get('id')}: room polygon has no usable area")
        if room.get("topologyClass") not in {"enclosed", "open-zone", "circulation", "attached"}:
            errors.append(f"{room.get('id')}: invalid topologyClass")
        if not room.get("spaceType"):
            errors.append(f"{room.get('id')}: spaceType is required")
        if room.get("spaceType") in ENCLOSED_SPACE_TYPES and room.get("topologyClass") != "enclosed":
            errors.append(
                f"{room.get('id')}: {room.get('spaceType')} must use topologyClass=enclosed"
            )

    wall_ids = set()
    for wall in model.get("walls", []):
        wall_id = wall.get("id")
        if not wall_id or wall_id in ids:
            errors.append(f"duplicate or missing wall ID: {wall_id}")
        ids.add(wall_id)
        wall_ids.add(wall_id)
        centerline = wall.get("centerline", [])
        if len(centerline) != 2 or not all(finite_point(point) for point in centerline) or centerline[0] == centerline[1]:
            errors.append(f"{wall_id}: centerline needs two distinct source points")
        if not (wall.get("thicknessPx", 0) > 0):
            errors.append(f"{wall_id}: thicknessPx must be positive")
        adjacent = wall.get("adjacentRoomIds", [])
        if len(set(adjacent)) < 2 or not set(adjacent) <= room_ids | {"exterior"}:
            errors.append(f"{wall_id}: adjacentRoomIds are invalid")
        if not wall.get("evidence"):
            errors.append(f"{wall_id}: source evidence description is required")

    opening_ids = set()
    room_access_kinds: dict[str, set[str]] = {room_id: set() for room_id in room_ids}
    for opening in model.get("openings", []):
        opening_id = opening.get("id")
        if not opening_id or opening_id in ids:
            errors.append(f"duplicate or missing opening ID: {opening_id}")
        ids.add(opening_id)
        opening_ids.add(opening_id)
        kind = opening.get("kind")
        if kind not in OPENING_KINDS:
            errors.append(f"{opening_id}: unsupported opening kind {kind}")
        segment = opening.get("segment", [])
        if len(segment) != 2 or not all(finite_point(point) for point in segment) or segment[0] == segment[1]:
            errors.append(f"{opening_id}: segment needs two distinct source points")
        if opening.get("hostWallId") not in wall_ids:
            errors.append(f"{opening_id}: hostWallId is missing")
        left = opening.get("fromRoomId")
        right = opening.get("toRoomId")
        if left == right or left not in room_ids | {"exterior"} or right not in room_ids | {"exterior"}:
            errors.append(f"{opening_id}: room connection is invalid")
        signature = opening.get("sourceSignature", {})
        if not signature.get("type") or not signature.get("evidence"):
            errors.append(f"{opening_id}: sourceSignature type/evidence is required")
        if kind in {"window", "fixed-glazing"} and opening.get("panelMaterial") != "glass":
            errors.append(f"{opening_id}: window/fixed glazing must record glass material")
        if kind in TRAVERSABLE_KINDS:
            if left in room_access_kinds:
                room_access_kinds[left].add(kind)
            if right in room_access_kinds:
                room_access_kinds[right].add(kind)

    for room in model.get("rooms", []):
        room_id = room.get("id")
        if room.get("topologyClass") == "enclosed" and not {
            "door", "sliding-door",
        }.intersection(room_access_kinds.get(room_id, set())):
            errors.append(
                f"{room_id}: enclosed room needs a source-evidenced door or sliding-door; "
                "an open passage cannot be relabeled as enclosed access"
            )

    for divider in model.get("semanticDividers", []):
        divider_id = divider.get("id")
        if not divider_id or divider_id in ids:
            errors.append(f"duplicate or missing semantic divider ID: {divider_id}")
        ids.add(divider_id)
        segment = divider.get("segment", [])
        if len(segment) != 2 or not all(finite_point(point) for point in segment) or segment[0] == segment[1]:
            errors.append(f"{divider_id}: segment needs two distinct source points")
        room_pair = divider.get("roomIds", [])
        if len(room_pair) != 2 or len(set(room_pair)) != 2 or not set(room_pair) <= room_ids:
            errors.append(f"{divider_id}: roomIds must name two distinct interior spaces")
        if divider.get("traversal") not in SEMANTIC_DIVIDER_TRAVERSALS:
            errors.append(f"{divider_id}: traversal must be open-passage or boundary-only")
        if not divider.get("evidence"):
            errors.append(f"{divider_id}: source evidence description is required")

    for boundary in model.get("boundaryFeatures", []):
        boundary_id = boundary.get("id")
        if not boundary_id or boundary_id in ids:
            errors.append(f"duplicate or missing boundary ID: {boundary_id}")
        ids.add(boundary_id)
        if boundary.get("kind") not in BOUNDARY_KINDS:
            errors.append(f"{boundary_id}: invalid boundary kind")
        if boundary.get("roomId") not in room_ids:
            errors.append(f"{boundary_id}: roomId is invalid")
        segment = boundary.get("segment", [])
        if len(segment) != 2 or not all(finite_point(point) for point in segment) or segment[0] == segment[1]:
            errors.append(f"{boundary_id}: segment needs two distinct source points")
        if not boundary.get("evidence"):
            errors.append(f"{boundary_id}: source evidence description is required")

    object_ids = set()
    assembly_members: dict[str, list[dict]] = {}
    for item in model.get("objects", []):
        object_id = item.get("id")
        if not object_id or object_id in ids:
            errors.append(f"duplicate or missing object ID: {object_id}")
        ids.add(object_id)
        object_ids.add(object_id)
        if item.get("roomId") not in room_ids:
            errors.append(f"{object_id}: roomId is invalid")
        if item.get("semantic") not in SEMANTICS:
            errors.append(f"{object_id}: semantic must be movable-green or fixed-purple")
        if not item.get("functionalClass"):
            errors.append(f"{object_id}: functionalClass is required")
        outline = item.get("outline", [])
        if len(outline) < 4 or not all(finite_point(point) for point in outline):
            errors.append(f"{object_id}: source outline needs at least four points")
        elif polygon_area(outline) <= 1:
            errors.append(f"{object_id}: source outline has no usable area")
        if not isinstance(item.get("rotationY"), (int, float)):
            errors.append(f"{object_id}: rotationY must be explicit")
        orientation = item.get("orientation", {})
        axes = orientation.get("localAxes", {})
        if orientation.get("evidence") not in {"source-symbol", "source-outline-axis", "user-explicit-layout"}:
            errors.append(f"{object_id}: source-bound orientation evidence is required")
        if not axes or any(role not in ORIENTATION_ROLES or axis not in AXES for role, axis in axes.items()):
            errors.append(f"{object_id}: local orientation axes are invalid")
        if not set(item.get("hostWallIds", [])) <= wall_ids:
            errors.append(f"{object_id}: hostWallIds contain an unknown wall")
        if item.get("assemblyId"):
            assembly_members.setdefault(item["assemblyId"], []).append(item)
        if len(outline) >= 4 and all(finite_point(point) for point in outline):
            shape_metrics, shape_errors = inspect_source_object_shape(item, model)
            errors.extend(shape_errors)
            if item.get("functionalClass") == "sofa" and shape_metrics.get("shapeClass") == "l-shaped":
                errors.append(
                    f"{object_id}: an L-shaped sofa must use functionalClass sectional-sofa; "
                    "do not downgrade a corner/sectional sofa to generic sofa"
                )
    for assembly_id, members in assembly_members.items():
        if len(members) < 2:
            errors.append(f"{assembly_id}: an assembly needs at least two atomic members")
        if len({member.get("assemblyRole") for member in members}) != len(members):
            errors.append(f"{assembly_id}: assembly roles must be unique")

    floor_boundary = model.get("floorBoundary", [])
    if len(floor_boundary) < 3 or not all(finite_point(point) for point in floor_boundary):
        errors.append("floorBoundary needs at least three source points")
    else:
        for room in model.get("rooms", []):
            if not polygon_inside_polygon(room.get("polygon", []), floor_boundary):
                errors.append(f"{room.get('id')}: room leaves floorBoundary")
        for item in model.get("objects", []):
            if not polygon_inside_polygon(item.get("outline", []), floor_boundary):
                errors.append(
                    f"{item.get('id')}: object outline leaves floorBoundary; "
                    "correct the reviewed floorplan object before modeling"
                )
    errors.extend(validate_source_geometry(model))
    return errors


def active_source_image(model: dict, source: Path) -> Image.Image:
    image = Image.open(source).convert("RGB")
    region = model.get("sourceRegion")
    if region is None:
        return image
    if not isinstance(region, list) or len(region) != 4:
        raise ValueError("sourceRegion must be [x,y,width,height]")
    x, y, width, height = map(int, region)
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > image.width or y + height > image.height:
        raise ValueError("sourceRegion leaves the source image")
    return image.crop((x, y, x + width, y + height))


def font(size: int = 16) -> ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def render_overlay(model: dict, source: Image.Image, clean: bool = False, objects_only: bool = False) -> Image.Image:
    canvas = Image.new("RGB", source.size, "white") if clean or objects_only else source.copy()
    draw = ImageDraw.Draw(canvas, "RGBA")
    if not objects_only:
        for room in model.get("rooms", []):
            draw.polygon(room["polygon"], fill=(255, 216, 0, 38), outline=(198, 145, 0, 180), width=2)
            label = room.get("name", room["id"])
            anchor = room.get("labelPoint") or room["polygon"][0]
            draw.text((anchor[0] + 4, anchor[1] + 4), label, fill=(90, 65, 0, 255), font=font(14))
        for wall in model.get("walls", []):
            draw.line(wall["centerline"], fill=(220, 35, 35, 255), width=max(3, int(round(wall["thicknessPx"]))))
        opening_colors = {
            "door": (220, 145, 24, 255),
            "sliding-door": (232, 133, 24, 255),
            "open-passage": (235, 184, 24, 255),
            "window": (0, 110, 255, 255),
            "fixed-glazing": (0, 190, 220, 255),
        }
        for opening in model.get("openings", []):
            draw.line(opening["segment"], fill=opening_colors[opening["kind"]], width=5)
        for divider in model.get("semanticDividers", []):
            first, second = divider["segment"]
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            length = math.hypot(dx, dy)
            steps = max(1, int(math.ceil(length / 12)))
            for index in range(steps):
                if index % 2:
                    continue
                start_t = index / steps
                end_t = min(1, (index + 1) / steps)
                draw.line([
                    [first[0] + dx * start_t, first[1] + dy * start_t],
                    [first[0] + dx * end_t, first[1] + dy * end_t],
                ], fill=(235, 155, 0, 255), width=4)
        boundary_colors = {
            "railing": (255, 145, 0, 255),
            "parapet": (160, 90, 30, 255),
            "open-edge": (235, 50, 190, 255),
            "full-height-glazing": (0, 190, 220, 255),
        }
        for boundary in model.get("boundaryFeatures", []):
            draw.line(boundary["segment"], fill=boundary_colors[boundary["kind"]], width=5)
    for item in model.get("objects", []):
        color = (36, 180, 72, 220) if item["semantic"] == "movable-green" else (135, 70, 190, 220)
        draw.line(item["outline"] + [item["outline"][0]], fill=color, width=3)
        for detail in item.get("details", []):
            draw.line(detail, fill=color, width=2)
    return canvas


def render_quadrants(source: Image.Image, overlay: Image.Image, structure: Image.Image, objects: Image.Image) -> Image.Image:
    width, height = source.size
    output = Image.new("RGB", (width * 2, height * 2), "white")
    for index, image in enumerate((source, overlay, structure, objects)):
        output.paste(image, ((index % 2) * width, (index // 2) * height))
    draw = ImageDraw.Draw(output)
    labels = ("Q1 原始户型", "Q2 语义回绘", "Q3 墙/开口/边界", "Q4 家具/柜体")
    for index, label in enumerate(labels):
        x = (index % 2) * width + 12
        y = (index // 2) * height + 10
        box = draw.textbbox((x, y), label, font=font(18))
        draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill="white")
        draw.text((x, y), label, fill="black", font=font(18))
    return output


def transform_functions(model: dict):
    x0, y0, x1, y1 = map(float, model["planBounds"])
    width_m = float(model["knownSizeMm"]["width"]) / 1000
    depth_m = float(model["knownSizeMm"]["depth"]) / 1000
    scale_x = width_m / (x1 - x0)
    scale_z = depth_m / (y1 - y0)

    def point(value: list[float]) -> list[float]:
        return [round((value[0] - x0) * scale_x, 6), round((value[1] - y0) * scale_z, 6)]

    return point, scale_x, scale_z, width_m, depth_m


def normalized_outline(points: list[list[float]]) -> tuple[list[list[float]], dict]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    depth = max_y - min_y
    outline = [
        [round((point[0] - min_x) / width - 0.5, 6), round((point[1] - min_y) / depth - 0.5, 6)]
        for point in points
    ]
    return outline, {
        "minX": min_x,
        "maxX": max_x,
        "minY": min_y,
        "maxY": max_y,
    }


def canonical_curve_outline(
    points: list[list[float]], minimum_points: int = 12,
) -> list[list[float]]:
    """Return one open, uniquely sampled outline without changing its polygon."""
    result: list[list[float]] = []
    for point in points:
        candidate = [round(float(point[0]), 6), round(float(point[1]), 6)]
        if not result or candidate != result[-1]:
            result.append(candidate)
    while len(result) > 1 and result[0] == result[-1]:
        result.pop()
    if len({tuple(point) for point in result}) < 4:
        raise ValueError("curved outline requires at least four unique points")
    while len(result) < minimum_points:
        edge_index = max(
            range(len(result)),
            key=lambda index: math.dist(result[index], result[(index + 1) % len(result)]),
        )
        following_index = (edge_index + 1) % len(result)
        midpoint = [
            round((result[edge_index][0] + result[following_index][0]) / 2, 6),
            round((result[edge_index][1] + result[following_index][1]) / 2, 6),
        ]
        if midpoint in result:
            raise ValueError("curved outline cannot be uniquely resampled at six-decimal precision")
        result.insert(edge_index + 1, midpoint)
    return result


def rotate_plan_point(point: list[float], yaw: float) -> list[float]:
    cosine = math.cos(yaw)
    sine = math.sin(yaw)
    return [
        point[0] * cosine - point[1] * sine,
        point[0] * sine + point[1] * cosine,
    ]


ORIENTATION_AXIS_VECTORS = {
    "+X": [1.0, 0.0],
    "-X": [-1.0, 0.0],
    "+Z": [0.0, 1.0],
    "-Z": [0.0, -1.0],
}
CANONICAL_ORIENTATION_AXES = {
    "headboard": "-Z",
    "front": "+Z",
    "back": "-Z",
}


def normalize_yaw(value: float) -> float:
    result = value
    while result > math.pi:
        result -= math.pi * 2
    while result <= -math.pi:
        result += math.pi * 2
    return result


def source_rotation_radians(item: dict, orientation_angle_unit: object) -> float:
    """Convert the sole accepted source orientation unit to handoff radians once."""
    if orientation_angle_unit != SOURCE_ORIENTATION_ANGLE_UNIT:
        raise ValueError(
            "orientationAngleUnit must be explicitly set to degrees; "
            "unitless or alternate rotationY conventions are ambiguous"
        )
    value = item.get("rotationY")
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{item.get('id', '<object>')}: rotationY must be finite degrees")
    return math.radians(float(value))


def canonical_object_orientation(
    item: dict,
    orientation_angle_unit: object,
) -> tuple[float, dict]:
    """Preserve world facing while emitting one canonical local-axis frame."""
    source = item["orientation"]
    source_axes = source["localAxes"]
    reference_role = next(
        (role for role in ("headboard", "front", "back") if role in source_axes),
        None,
    )
    if reference_role is None:
        raise ValueError(f"{item['id']}: orientation needs headboard, front or back")
    source_yaw = source_rotation_radians(item, orientation_angle_unit)
    desired = rotate_plan_point(
        ORIENTATION_AXIS_VECTORS[source_axes[reference_role]], source_yaw,
    )
    canonical = ORIENTATION_AXIS_VECTORS[CANONICAL_ORIENTATION_AXES[reference_role]]
    yaw = normalize_yaw(
        math.atan2(desired[1], desired[0]) - math.atan2(canonical[1], canonical[0]),
    )
    canonical_axes = {
        role: CANONICAL_ORIENTATION_AXES[role]
        for role in source_axes
    }
    for role, source_axis in source_axes.items():
        source_world = rotate_plan_point(ORIENTATION_AXIS_VECTORS[source_axis], source_yaw)
        canonical_world = rotate_plan_point(
            ORIENTATION_AXIS_VECTORS[canonical_axes[role]], yaw,
        )
        if math.dist(source_world, canonical_world) > 1e-5:
            raise ValueError(f"{item['id']}: orientation roles disagree in world space")
    return yaw, {
        "evidence": source["evidence"],
        "localAxes": canonical_axes,
    }


def oriented_geometry(points: list[list[float]], yaw: float) -> dict:
    local_points = [rotate_plan_point(point, -yaw) for point in points]
    normalized, bounds = normalized_outline(local_points)
    center_local = [
        (bounds["minX"] + bounds["maxX"]) / 2,
        (bounds["minY"] + bounds["maxY"]) / 2,
    ]
    return {
        "localPoints": local_points,
        "normalized": normalized,
        "bounds": bounds,
        "center": rotate_plan_point(center_local, yaw),
        "width": bounds["maxX"] - bounds["minX"],
        "depth": bounds["maxY"] - bounds["minY"],
    }


def horizontal_polygon_strips(points: list[list[float]]) -> list[dict]:
    """Return exact non-overlapping horizontal strips for an orthogonal polygon."""
    levels = sorted({round(point[1], 9) for point in points})
    strips: list[dict] = []
    for lower, upper in zip(levels, levels[1:]):
        if upper - lower <= 1e-8:
            continue
        probe = (lower + upper) / 2
        crossings = []
        for first, second in zip(points, points[1:] + points[:1]):
            if abs(first[1] - second[1]) <= 1e-8:
                continue
            if min(first[1], second[1]) < probe < max(first[1], second[1]):
                ratio = (probe - first[1]) / (second[1] - first[1])
                crossings.append(first[0] + ratio * (second[0] - first[0]))
        crossings.sort()
        for left, right in zip(crossings[::2], crossings[1::2]):
            if right - left > 1e-8:
                strips.append({"minX": left, "maxX": right, "minY": lower, "maxY": upper})
    return strips


def source_outline_from_world(
    world_points: list[list[float]],
    model: dict,
    scale_x: float,
    scale_z: float,
) -> list[list[float]]:
    x0, y0, _, _ = map(float, model["planBounds"])
    return [
        [round(point[0] / scale_x + x0, 6), round(point[1] / scale_z + y0, 6)]
        for point in world_points
    ]


def point_segment_distance(point: list[float], start: list[float], end: list[float]) -> float:
    dx = end[0] - start[0]
    dz = end[1] - start[1]
    length_squared = dx * dx + dz * dz
    if length_squared <= 1e-12:
        return math.dist(point, start)
    ratio = max(0.0, min(1.0, (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dz
    ) / length_squared))
    return math.dist(point, [start[0] + dx * ratio, start[1] + dz * ratio])


def orientation(first: list[float], second: list[float], third: list[float]) -> float:
    return (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def point_on_segment(point: list[float], start: list[float], end: list[float]) -> bool:
    return (
        abs(orientation(start, end, point)) <= 1e-9
        and min(start[0], end[0]) - 1e-9 <= point[0] <= max(start[0], end[0]) + 1e-9
        and min(start[1], end[1]) - 1e-9 <= point[1] <= max(start[1], end[1]) + 1e-9
    )


def segments_intersect(
    first_start: list[float],
    first_end: list[float],
    second_start: list[float],
    second_end: list[float],
) -> bool:
    first_cross = orientation(first_start, first_end, second_start)
    second_cross = orientation(first_start, first_end, second_end)
    third_cross = orientation(second_start, second_end, first_start)
    fourth_cross = orientation(second_start, second_end, first_end)
    if first_cross * second_cross < -1e-12 and third_cross * fourth_cross < -1e-12:
        return True
    return (
        (abs(first_cross) <= 1e-9 and point_on_segment(second_start, first_start, first_end))
        or (abs(second_cross) <= 1e-9 and point_on_segment(second_end, first_start, first_end))
        or (abs(third_cross) <= 1e-9 and point_on_segment(first_start, second_start, second_end))
        or (abs(fourth_cross) <= 1e-9 and point_on_segment(first_end, second_start, second_end))
    )


def segment_distance(
    first_start: list[float],
    first_end: list[float],
    second_start: list[float],
    second_end: list[float],
) -> float:
    if segments_intersect(first_start, first_end, second_start, second_end):
        return 0.0
    return min(
        point_segment_distance(first_start, second_start, second_end),
        point_segment_distance(first_end, second_start, second_end),
        point_segment_distance(second_start, first_start, first_end),
        point_segment_distance(second_end, first_start, first_end),
    )


def footprint_wall_distance(footprint: list[list[float]], wall: dict) -> float:
    return min(
        segment_distance(first, second, wall["start"], wall["end"])
        for first, second in zip(footprint, footprint[1:] + footprint[:1])
    )


def parallel_host_walls(
    item: dict,
    yaw: float,
    wall_by_id: dict[str, dict],
    footprint: list[list[float]],
) -> list[str]:
    width_axis = [math.cos(yaw), math.sin(yaw)]
    hosts = []
    for wall_id in item.get("hostWallIds", []):
        wall = wall_by_id.get(wall_id)
        if not wall:
            continue
        dx = wall["end"][0] - wall["start"][0]
        dz = wall["end"][1] - wall["start"][1]
        length = math.hypot(dx, dz)
        parallel = length > 0 and abs(
            (dx / length) * width_axis[0] + (dz / length) * width_axis[1]
        ) >= 0.95
        contact_tolerance = wall["thickness"] / 2 + 0.08
        if parallel and footprint_wall_distance(footprint, wall) <= contact_tolerance:
            hosts.append(wall_id)
    return hosts


def component_specs(
    item: dict,
    model: dict,
    to_world,
    scale_x: float,
    scale_z: float,
    wall_by_id: dict[str, dict],
) -> list[dict]:
    world_outline = [to_world(point) for point in item["outline"]]
    yaw, canonical_orientation = canonical_object_orientation(
        item,
        model.get("orientationAngleUnit"),
    )
    geometry = oriented_geometry(world_outline, yaw)
    shape_metrics, shape_errors = inspect_shape_contract(item, geometry["normalized"])
    if shape_errors:
        raise ValueError("; ".join(shape_errors))
    shape_outline = geometry["normalized"]
    if shape_metrics["shapeClass"] in {"round", "curved", "organic"}:
        shape_outline = canonical_curve_outline(shape_outline)
        shape_metrics = {**shape_metrics, "pointCount": len(shape_outline)}
    should_partition_shape = (
        item["functionalClass"] in MODULAR_RUN_CLASSES
        and shape_metrics["shapeClass"] == "l-shaped"
    )
    if should_partition_shape:
        rectangles = horizontal_polygon_strips(geometry["localPoints"])
    else:
        rectangles = [{**geometry["bounds"], "preserveOutline": True}]

    derived = should_partition_shape or (
        item["functionalClass"] in MODULAR_RUN_CLASSES
        and geometry["width"] > MODULE_SPLIT_MIN_WIDTH_M
        and geometry["width"] / max(geometry["depth"], 1e-6) >= 1.45
    )
    assembly_id = item.get("assemblyId") or (f"{item['id']}-assembly" if derived else None)
    specs: list[dict] = []
    sequence = 0
    for run_index, rectangle in enumerate(rectangles, start=1):
        local_width = rectangle["maxX"] - rectangle["minX"]
        local_depth = rectangle["maxY"] - rectangle["minY"]
        center_local = [
            (rectangle["minX"] + rectangle["maxX"]) / 2,
            (rectangle["minY"] + rectangle["maxY"]) / 2,
        ]
        run_center = rotate_plan_point(center_local, yaw)
        # Only an L-shaped modular run may rotate an individual derived leg.
        # Atomic objects keep the source yaw and axis meaning even when depth is
        # numerically larger than width; otherwise beds, sofas and chairs can
        # silently turn 90 degrees between planning and native modeling.
        if should_partition_shape and local_depth > local_width:
            run_yaw = yaw + math.pi / 2
            run_width, run_depth = local_depth, local_width
        else:
            run_yaw = yaw
            run_width, run_depth = local_width, local_depth
        split_run = (
            item["functionalClass"] in MODULAR_RUN_CLASSES
            and run_width > MODULE_SPLIT_MIN_WIDTH_M
            and run_width / max(run_depth, 1e-6) >= 1.45
        )
        module_count = max(2, round(run_width / MODULE_TARGET_WIDTH_M)) if split_run else 1
        module_width = run_width / module_count
        for module_index in range(module_count):
            sequence += 1
            offset = -run_width / 2 + module_width * (module_index + 0.5)
            module_center = [
                run_center[0] + math.cos(run_yaw) * offset,
                run_center[1] + math.sin(run_yaw) * offset,
            ]
            half_width = module_width / 2
            half_depth = run_depth / 2
            local_corners = [
                [-half_width, -half_depth],
                [half_width, -half_depth],
                [half_width, half_depth],
                [-half_width, half_depth],
            ]
            world_corners = [
                [
                    module_center[0] + rotate_plan_point(point, run_yaw)[0],
                    module_center[1] + rotate_plan_point(point, run_yaw)[1],
                ]
                for point in local_corners
            ]
            is_derived = derived or split_run or len(rectangles) > 1
            trace_id = item["id"] if not is_derived else f"{item['id']}-module-{sequence:02d}"
            source_candidate_id = item["id"] if not is_derived else f"{item['id']}::module-{sequence:02d}"
            role_base = item.get("assemblyRole", item["functionalClass"])
            footprint = world_corners if is_derived else world_outline
            spec = {
                "traceId": trace_id,
                "sourceObjectCandidateId": source_candidate_id,
                "name": item.get("name", item["id"]) if not is_derived else f"{item.get('name', item['id'])} 模块{sequence}",
                "sourceItem": item,
                "shapeClass": shape_metrics["shapeClass"] if not is_derived else "rectilinear",
                "shapeOutline": shape_outline if not is_derived else [
                    [-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5],
                ],
                "shapeMetrics": shape_metrics if not is_derived else {
                    "curveEdgeRatio": 0.0,
                    "handedness": "none",
                },
                "bbox": {"width": round(module_width, 6), "depth": round(run_depth, 6)},
                "center": [round(module_center[0], 6), round(module_center[1], 6)],
                "rotationY": round(run_yaw, 6),
                "orientation": canonical_orientation,
                "sourceOutline": item["outline"] if not is_derived else source_outline_from_world(
                    world_corners, model, scale_x, scale_z,
                ),
                "hostWallIds": parallel_host_walls(item, run_yaw, wall_by_id, footprint),
                "assemblyId": assembly_id,
                "assemblyRole": item.get("assemblyRole") if not is_derived else f"{role_base}-module-{sequence:02d}",
                "derivation": None if not is_derived else {
                    "mode": "exact-modular-partition-v1",
                    "parentSourceObjectCandidateId": item["id"],
                    "runIndex": run_index,
                    "moduleIndex": module_index + 1,
                    "moduleCountInRun": module_count,
                    "aggregateFootprintPreserved": True,
                },
            }
            specs.append(spec)
    return specs


def build_outputs(model: dict) -> tuple[dict, dict, dict]:
    to_world, scale_x, scale_z, width_m, depth_m = transform_functions(model)
    rooms = []
    for room in model["rooms"]:
        polygon = [to_world(point) for point in room["polygon"]]
        rooms.append({
            "id": room["id"],
            "name": room.get("name", room["id"]),
            "spaceType": room["spaceType"],
            "topologyClass": room["topologyClass"],
            "polygon": polygon,
            "areaM2": round(polygon_area(polygon), 3),
        })
    room_ids = {room["id"] for room in rooms}
    walls = []
    for wall in model["walls"]:
        walls.append({
            "id": wall["id"],
            "name": wall.get("name", wall["id"]),
            "start": to_world(wall["centerline"][0]),
            "end": to_world(wall["centerline"][1]),
            "thickness": round(max(0.06, wall["thicknessPx"] * (scale_x + scale_z) / 2), 4),
            "height": float(wall.get("height", 2.8)),
            "type": wall.get("type", "partition"),
            "adjacentRoomIds": wall["adjacentRoomIds"],
            "sourceTraceIds": [wall["id"]],
        })
    wall_by_id = {wall["id"]: wall for wall in walls}
    windows = []
    connections = []
    for opening in model.get("openings", []):
        segment = [to_world(point) for point in opening["segment"]]
        if opening["kind"] in TRAVERSABLE_KINDS:
            connections.append({
                "id": opening["id"],
                "name": opening.get("name", opening["id"]),
                "fromRoomId": opening["fromRoomId"],
                "toRoomId": opening["toRoomId"],
                "kind": opening["kind"],
                "start": segment[0],
                "end": segment[1],
                "bottom": float(opening.get("bottom", 0)),
                "height": float(opening.get("height", 2.2)),
                "panelMaterial": opening.get("panelMaterial", "opaque"),
                "sourceTraceIds": [opening["id"]],
            })
            continue
        host = wall_by_id[opening["hostWallId"]]
        dx = host["end"][0] - host["start"][0]
        dz = host["end"][1] - host["start"][1]
        length = math.hypot(dx, dz)
        ux, uz = dx / length, dz / length
        midpoint = [(segment[0][0] + segment[1][0]) / 2, (segment[0][1] + segment[1][1]) / 2]
        offset = (midpoint[0] - host["start"][0]) * ux + (midpoint[1] - host["start"][1]) * uz
        opening_width = math.hypot(segment[1][0] - segment[0][0], segment[1][1] - segment[0][1])
        windows.append({
            "id": opening["id"],
            "name": opening.get("name", opening["id"]),
            "wallId": opening["hostWallId"],
            "offset": round(offset, 6),
            "width": round(opening_width, 6),
            "sill": float(opening.get("sill", 0.75 if opening["kind"] == "window" else 0)),
            "openingHeight": float(opening.get("height", 1.6 if opening["kind"] == "window" else 2.5)),
            "kind": "fixed-glazing" if opening["kind"] == "fixed-glazing" else opening.get("windowKind", "standard"),
            "frameDepth": float(opening.get("frameDepth", 0.08)),
            "sourceTraceIds": [opening["id"]],
        })
    semantic_dividers = []
    for divider in model.get("semanticDividers", []):
        segment = [to_world(point) for point in divider["segment"]]
        connection_id = None
        if divider["traversal"] == "open-passage":
            connection_id = f"connection-{divider['id']}"
            connections.append({
                "id": connection_id,
                "name": divider.get("name", divider["id"]),
                "fromRoomId": divider["roomIds"][0],
                "toRoomId": divider["roomIds"][1],
                "kind": "open-passage",
                "start": segment[0],
                "end": segment[1],
                "bottom": 0.0,
                "height": float(divider.get("height", 2.8)),
                "panelMaterial": "none",
                "sourceTraceIds": [],
                "sourceDividerIds": [divider["id"]],
            })
        semantic_dividers.append({
            "id": divider["id"],
            "sourceDividerId": divider["id"],
            "roomIds": list(divider["roomIds"]),
            "traversal": divider["traversal"],
            "start": segment[0],
            "end": segment[1],
            "reason": divider["evidence"],
            **({"connectionId": connection_id} if connection_id else {}),
        })
    boundary_features = [{
        "id": item["id"],
        "name": item.get("name", item["id"]),
        "kind": item["kind"],
        "roomId": item["roomId"],
        "start": to_world(item["segment"][0]),
        "end": to_world(item["segment"][1]),
        "height": float(item.get("height", 1.1 if item["kind"] in {"railing", "parapet"} else 2.8)),
        "sourceTraceIds": [item["id"]],
    } for item in model.get("boundaryFeatures", [])]
    room_connections = {room_id: [] for room_id in room_ids}
    for connection in connections:
        if connection["fromRoomId"] in room_connections:
            room_connections[connection["fromRoomId"]].append(connection["id"])
        if connection["toRoomId"] in room_connections:
            room_connections[connection["toRoomId"]].append(connection["id"])
    for room in rooms:
        room["connectionIds"] = room_connections[room["id"]]

    topology = {
        # structure.v4/handoff.v3 retain their established deterministic
        # provenance family; source-model.v2 only changes the pre-handoff
        # orientation-unit contract.
        "method": "semantic-source-model-v1",
        "interiorPixels": int(round(polygon_area(model["floorBoundary"]))),
        "assignedInteriorPixels": int(round(polygon_area(model["floorBoundary"]))),
        "spaceSeedCount": len(rooms),
        "roomCount": len(rooms),
        "mergedSeedGroups": [],
        "unassignedRegionCount": 0,
        "orphanWallIds": [],
        "openingEndpointMismatches": [],
        "wallAdjacency": {wall["id"]: wall["adjacentRoomIds"] for wall in walls},
        "wallSides": {},
    }
    structure = {
        "schema": "interior.floorplan-structure.v4",
        "floorplanId": model["floorplanId"],
        "name": model.get("name", model["floorplanId"]),
        "source": {
            "kind": "reviewed-source-model-v2",
            "image": "source-image.png",
            "sourceModel": "floorplan-source-model.json",
            "sourceOrientationAngleUnit": SOURCE_ORIENTATION_ANGLE_UNIT,
            "acceptedRotationUnit": "radians",
        },
        "coordinateSystem": {
            "units": "m",
            "origin": "north-west",
            "realWidthMeters": width_m,
            "realDepthMeters": depth_m,
            "defaultWallHeightMeters": 2.8,
        },
        "dimensionAnnotations": {
            "widthMeters": width_m,
            "depthMeters": depth_m,
            "widthLabel": "总宽",
            "depthLabel": "总深",
        },
        "floorBoundary": [to_world(point) for point in model["floorBoundary"]],
        "rooms": rooms,
        "walls": walls,
        "windows": windows,
        "boundaryFeatures": boundary_features,
        "connections": connections,
        "semanticDividers": semantic_dividers,
        "topology": topology,
        "layers": {
            "walls": True,
            "windows": True,
            "boundaryFeatures": True,
            "fixedFixtures": True,
            "movableFurniture": True,
            "grid": True,
            "annotations": False,
        },
    }

    component_objects = []
    trace_layers = {"movableFurniture": [], "fixedFixtures": [], "other": []}
    assemblies: dict[str, list[str]] = {}
    assembly_metadata: dict[str, dict] = {}
    all_specs = [
        spec
        for item in model.get("objects", [])
        for spec in component_specs(item, model, to_world, scale_x, scale_z, wall_by_id)
    ]
    for spec in all_specs:
        item = spec["sourceItem"]
        trace_id = spec["traceId"]
        component = {
            "traceId": trace_id,
            "sourceObjectCandidateId": spec["sourceObjectCandidateId"],
            "name": spec["name"],
            "semantic": item["semantic"],
            "functionalClass": item["functionalClass"],
            "shapeClass": spec["shapeClass"],
            "shapeEvidence": {
                "coordinateSpace": "bbox-normalized",
                "outline": spec["shapeOutline"],
                "curveEdgeRatio": spec["shapeMetrics"]["curveEdgeRatio"],
                "handedness": spec["shapeMetrics"]["handedness"],
                "outlineSource": "exact-modular-partition-v1" if spec["derivation"] else "reviewed-source-model-outline",
            },
            "bbox": spec["bbox"],
            "center": spec["center"],
            "roomId": item["roomId"],
            "rotationY": spec["rotationY"],
            "orientation": spec["orientation"],
            "quantity": 1,
            "atomicObject": True,
            "keywords": item.get("keywords", []),
        }
        if spec["derivation"]:
            component["derivation"] = spec["derivation"]
        if item.get("componentHint"):
            component["componentHint"] = item["componentHint"]
        if spec["hostWallIds"]:
            component["hostWallIds"] = list(spec["hostWallIds"])
        if spec["assemblyId"]:
            component["assemblyId"] = spec["assemblyId"]
            component["assemblyRole"] = spec["assemblyRole"]
            assemblies.setdefault(spec["assemblyId"], []).append(trace_id)
            assembly_metadata.setdefault(spec["assemblyId"], {
                "functionalClass": item.get("assemblyFunctionalClass", f"{item['functionalClass']}-group"),
                "roomId": item["roomId"],
            })
        component_objects.append(component)
        layer_name = "movableFurniture" if item["semantic"] == "movable-green" else "fixedFixtures"
        layer = {
            "id": trace_id,
            "traceId": trace_id,
            "sourceObjectCandidateId": spec["sourceObjectCandidateId"],
            "sourceLabelId": item["roomId"],
            "name": spec["name"],
            "functionalClass": item["functionalClass"],
            "quantity": 1,
            "type": "polygon",
            "points": spec["sourceOutline"],
            "details": [] if spec["derivation"] else item.get("details", []),
            "strokeOnly": True,
            "width": 2,
            **({"assemblyId": spec["assemblyId"], "assemblyRole": spec["assemblyRole"]} if spec["assemblyId"] else {}),
        }
        if spec["derivation"]:
            layer["derivation"] = spec["derivation"]
        trace_layers[layer_name].append(layer)
    trace_components = {
        "schema": "interior.trace-components.v2",
        "floorplanId": model["floorplanId"],
        "objects": component_objects,
        "assemblies": [{
            "id": assembly_id,
            "functionalClass": assembly_metadata[assembly_id]["functionalClass"],
            "roomId": assembly_metadata[assembly_id]["roomId"],
            "compositionPolicy": "source-evidenced-atomic-members",
            "childTraceIds": children,
        } for assembly_id, children in assemblies.items()],
    }
    trace_spec = {
        "schema": "interior.floorplan-trace.v3",
        "floorplanId": model["floorplanId"],
        "name": model.get("name", model["floorplanId"]),
        "sourceImage": "source-image.png",
        "planBounds": model["planBounds"],
        "knownSizeMm": model["knownSizeMm"],
        "floorBoundary": model["floorBoundary"],
        "spaces": model["rooms"],
        "layers": trace_layers,
        "cleanStructure": {
            "walls": model["walls"],
            "openings": model.get("openings", []),
            "semanticDividers": model.get("semanticDividers", []),
            "boundaryFeatures": model.get("boundaryFeatures", []),
        },
    }
    return structure, trace_components, trace_spec


def artifact_entry(path: Path, relative: str) -> dict:
    return {"path": relative, "sha256": digest(path), "bytes": path.stat().st_size}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-model", required=True)
    parser.add_argument("--review")
    parser.add_argument("--out", required=True)
    parser.add_argument("--draft-only", action="store_true")
    parser.add_argument("--release-regression", action="store_true")
    return parser.parse_args()


def main() -> int:
    started = time.perf_counter()
    stage_started = started
    stage_durations: dict[str, int] = {}

    def finish_stage(name: str) -> None:
        nonlocal stage_started
        now = time.perf_counter()
        stage_durations[name] = round((now - stage_started) * 1000)
        stage_started = now

    args = parse_args()
    source = Path(args.source).resolve()
    source_model_path = Path(args.source_model).resolve()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = load(source_model_path)
    active_image = active_source_image(model, source)
    finish_stage("load-input")
    # Production compiles the reviewed image interpretation directly.  The
    # expensive/strict audits belong to Skill release regression, not to each
    # customer task.  This keeps one algorithmic source of truth: when a
    # regression fails we repair the compiler and release it, while a released
    # compiler always produces an editable coauthoring draft.
    errors: list[str] = []
    pixel_audit = {
        "mode": "release-regression-only",
        "passed": None,
        "unexplainedObjectPixels": None,
        "unsupportedTracePixels": None,
        "supportedTracePixels": None,
    }
    if args.release_regression:
        errors.extend(validate_source_model(model, source, active_image))
        pixel_audit, pixel_errors = source_pixel_audit(model, active_image)
        errors.extend(pixel_errors)
    finish_stage("algorithm-input-normalization")
    structure, components, trace_spec = build_outputs(model)
    if args.release_regression:
        errors.extend(validate_compiled_structure(structure))
    finish_stage("deterministic-compile")
    if errors:
        raise SystemExit("release regression rejected the compiler output:\n" + "\n".join(errors))

    overlay = render_overlay(model, active_image)
    structure_image = render_overlay(model, active_image, clean=True)
    object_image = render_overlay(model, active_image, objects_only=True)
    quadrants = render_quadrants(active_image, overlay, structure_image, object_image)
    finish_stage("render-review-images")
    active_image.save(output / "source-image.png")
    overlay.save(output / "floorplan-review-overlay.png")
    structure_image.save(output / "floorplan-structure.png")
    object_image.save(output / "floorplan-objects.png")
    quadrants.save(output / "floorplan-four-quadrants.png")
    shutil.copy2(source_model_path, output / "floorplan-source-model.json")
    review_path = Path(args.review).resolve() if args.review else None
    review = load(review_path) if review_path else None
    expected_counts = {
        "rooms": len(model["rooms"]),
        "walls": len(model["walls"]),
        "openings": len(model.get("openings", [])),
        "semanticDividers": len(model.get("semanticDividers", [])),
        "boundaryFeatures": len(model.get("boundaryFeatures", [])),
        "objects": len(model.get("objects", [])),
    }
    if review_path:
        shutil.copy2(review_path, output / "agent-visual-review.json")

    assert structure is not None and components is not None and trace_spec is not None
    write_json(output / "structure-data.json", structure)
    write_json(output / "trace-components.json", components)
    write_json(output / "trace-spec.json", trace_spec)
    class_counts = Counter(item["functionalClass"] for item in model.get("objects", []))
    report = {
        "schema": "interior.floorplan-source-model-validation.v1",
        "passed": None if not args.release_regression else True,
        "mode": "release-regression" if args.release_regression else "production-algorithm",
        "errors": [],
        "sourceSha256": digest(source),
        "sourceModelSha256": digest(source_model_path),
        "traceSpecSha256": digest(output / "trace-spec.json"),
        "reviewSha256": digest(review_path) if review_path else None,
        "independentFloorMetrics": {
            "missedPixels": pixel_audit.get("unexplainedObjectPixels"),
            "outsidePixels": pixel_audit.get("unsupportedTracePixels"),
            "overlapCorePixels": pixel_audit.get("supportedTracePixels"),
        },
        "sourcePixelAudit": pixel_audit,
        "topologyMetrics": structure["topology"],
        "objectMetrics": {
            "acceptedObjects": len(components["objects"]),
            "traceComponents": len(components["objects"]),
            "functionalClassCounts": dict(sorted(class_counts.items())),
        },
        "review": ({
            "status": review.get("status"),
            "finding": review.get("finding"),
            "confirmedCounts": review.get("confirmedCounts"),
        } if review else {"status": "pending-user-coauthoring", "confirmedCounts": expected_counts}),
        "orientationContract": {
            "sourceSchema": SOURCE_SCHEMA,
            "sourceAngleUnit": SOURCE_ORIENTATION_ANGLE_UNIT,
            "acceptedHandoffAngleUnit": "radians",
            "normalizationCount": 1,
        },
    }
    write_json(output / "reports/source-model-validation.json", report)
    finish_stage("write-accepted-artifacts")
    timing_path = output / "reports/stage-timing.json"
    write_json(timing_path, {
        "schema": "interior.floorplan-stage-timing.v1",
        "stageDurationsMs": stage_durations,
        "totalDurationMs": round((time.perf_counter() - started) * 1000),
        "mode": "release-regression" if args.release_regression else "coauthoring-draft",
    })

    artifacts = {
        "sourceImage": artifact_entry(output / "source-image.png", "source-image.png"),
        "sourceModel": artifact_entry(output / "floorplan-source-model.json", "floorplan-source-model.json"),
        "visualOverlay": artifact_entry(output / "floorplan-review-overlay.png", "floorplan-review-overlay.png"),
        "quadrantsImage": artifact_entry(output / "floorplan-four-quadrants.png", "floorplan-four-quadrants.png"),
        "structureImage": artifact_entry(output / "floorplan-structure.png", "floorplan-structure.png"),
        "objectImage": artifact_entry(output / "floorplan-objects.png", "floorplan-objects.png"),
        "traceSpec": artifact_entry(output / "trace-spec.json", "trace-spec.json"),
        "structureData": artifact_entry(output / "structure-data.json", "structure-data.json"),
        "traceComponents": artifact_entry(output / "trace-components.json", "trace-components.json"),
    }
    if review_path:
        artifacts["agentVisualReview"] = artifact_entry(output / "agent-visual-review.json", "agent-visual-review.json")
    report_entry = artifact_entry(
        output / "reports/source-model-validation.json",
        "reports/source-model-validation.json",
    )
    structure_ids = [
        item["id"]
        for group in (
            model["walls"],
            model.get("openings", []),
            model.get("semanticDividers", []),
            model.get("boundaryFeatures", []),
        )
        for item in group
    ]
    manifest = {
        "schema": HANDOFF_SCHEMA,
        "floorplanId": model["floorplanId"],
        "producer": {"skill": "interior-floorplan-planning", "version": PRODUCER_VERSION},
        "workflowStage": "coauthoring-draft",
        "validationMode": "release-regression-only",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
        "reports": {
            "sourceModelValidation": report_entry,
            "stageTiming": artifact_entry(timing_path, "reports/stage-timing.json"),
        },
        "sourceTraceRegistry": {
            "structureTraceIds": sorted(structure_ids),
            "componentTraceIds": sorted(item["traceId"] for item in components["objects"]),
            "sourceObjectCandidateIds": sorted(item["sourceObjectCandidateId"] for item in components["objects"]),
        },
        "layoutAuthority": model["layoutAuthority"],
        "validation": {
            "algorithmCompiled": True,
            "releaseRegression": True if args.release_regression else None,
            "userCoauthoringConfirmed": review.get("status") == "accepted" if review else False,
        },
    }
    manifest["handoffDigestSha256"] = canonical_digest(manifest)
    write_json(output / "floorplan-handoff.json", manifest)
    print(json.dumps({
        "ok": True,
        "handoff": str(output / "floorplan-handoff.json"),
        "rooms": len(model["rooms"]),
        "objects": len(model.get("objects", [])),
        "workflowStage": "coauthoring-draft",
        "next": "compile editable HTML; user may correct the draft in place",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
