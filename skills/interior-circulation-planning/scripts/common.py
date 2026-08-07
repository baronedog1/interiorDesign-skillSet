#!/usr/bin/env python3
"""Shared deterministic geometry and JSON helpers for circulation planning."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence


Point = tuple[float, float]


class ArtifactDiscoveryError(ValueError):
    """Raised when a semantic artifact is absent or has conflicting candidates."""


def _one_edit_or_equal(left: str, right: str) -> bool:
    """Return true when two field names differ by at most one edit."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = sum(a != b for a, b in zip(left, right))
        return differences <= 1
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = 0
    long_index = 0
    edits = 0
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        edits += 1
        long_index += 1
        if edits > 1:
            return False
    return True


def discover_semantic_list(
    document: dict[str, Any],
    field_name: str,
    *,
    item_validator,
    preferred_paths: Sequence[str] = (),
) -> tuple[list[Any], dict[str, Any]]:
    """Find one valid list by meaning, without treating one JSON path as identity.

    Exact field names are searched recursively first. A field name with one missing,
    extra, or substituted character is accepted only when its list items validate.
    Identical copies are aliases; conflicting valid copies remain ambiguous.
    """
    candidates: list[dict[str, Any]] = []

    def walk(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = (*path, str(key))
                if _one_edit_or_equal(str(key), field_name) and isinstance(child, list):
                    if all(item_validator(item) for item in child):
                        candidates.append({
                            "path": ".".join(child_path),
                            "fieldName": str(key),
                            "exactFieldName": str(key) == field_name,
                            "value": child,
                            "digestSha256": canonical_sha256(child),
                        })
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, (*path, str(index)))

    walk(document, ())
    if not candidates:
        raise ArtifactDiscoveryError(
            f"未发现语义有效的 {field_name}；请先询问用户是否已有该文件或数据，并请求上传或提供实际路径"
        )
    by_digest: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_digest.setdefault(candidate["digestSha256"], []).append(candidate)
    if len(by_digest) != 1:
        paths = sorted(candidate["path"] for candidate in candidates)
        raise ArtifactDiscoveryError(
            f"发现内容冲突的 {field_name} 候选 {paths}；必须询问用户选择，不能按路径或文件名猜测"
        )
    preferred_rank = {path: index for index, path in enumerate(preferred_paths)}
    selected = min(
        candidates,
        key=lambda item: (
            preferred_rank.get(item["path"], len(preferred_rank)),
            0 if item["exactFieldName"] else 1,
            item["path"],
        ),
    )
    aliases = sorted(candidate["path"] for candidate in candidates if candidate is not selected)
    return selected["value"], {
        "semanticField": field_name,
        "selectedPath": selected["path"],
        "selectedFieldName": selected["fieldName"],
        "normalizedFieldName": selected["fieldName"] != field_name,
        "contentDigestSha256": selected["digestSha256"],
        "equivalentAliasPaths": aliases,
        "candidateCount": len(candidates),
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def as_point(value: Sequence[float], label: str = "point") -> Point:
    if len(value) < 2:
        raise ValueError(f"{label} must contain two coordinates")
    point = (float(value[0]), float(value[1]))
    if not all(math.isfinite(item) for item in point):
        raise ValueError(f"{label} contains a non-finite coordinate")
    return point


def normalize_polygon(value: Iterable[Sequence[float]], label: str = "polygon") -> list[Point]:
    polygon = [as_point(point, label) for point in value]
    if len(polygon) >= 2 and distance(polygon[0], polygon[-1]) <= 1e-9:
        polygon.pop()
    if len(polygon) < 3:
        raise ValueError(f"{label} must contain at least three unique points")
    if abs(polygon_area(polygon)) <= 1e-9:
        raise ValueError(f"{label} has zero area")
    return polygon


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polygon_area(polygon: Sequence[Point]) -> float:
    total = 0.0
    for index, current in enumerate(polygon):
        following = polygon[(index + 1) % len(polygon)]
        total += current[0] * following[1] - following[0] * current[1]
    return total / 2.0


def polygon_centroid(polygon: Sequence[Point]) -> Point:
    area = polygon_area(polygon)
    if abs(area) <= 1e-12:
        return (
            sum(point[0] for point in polygon) / len(polygon),
            sum(point[1] for point in polygon) / len(polygon),
        )
    factor = 1.0 / (6.0 * area)
    x = 0.0
    y = 0.0
    for index, current in enumerate(polygon):
        following = polygon[(index + 1) % len(polygon)]
        cross = current[0] * following[1] - following[0] * current[1]
        x += (current[0] + following[0]) * cross
        y += (current[1] + following[1]) * cross
    return (x * factor, y * factor)


def point_on_segment(point: Point, start: Point, end: Point, tolerance: float = 1e-9) -> bool:
    return point_segment_distance(point, start, end) <= tolerance


def point_in_polygon(point: Point, polygon: Sequence[Point], include_boundary: bool = True) -> bool:
    inside = False
    x, y = point
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        if include_boundary and point_on_segment(point, start, end, 1e-9):
            return True
        if (start[1] > y) != (end[1] > y):
            crossing_x = (end[0] - start[0]) * (y - start[1]) / (end[1] - start[1]) + start[0]
            if x < crossing_x:
                inside = not inside
    return inside


def point_segment_distance(point: Point, start: Point, end: Point) -> float:
    vx = end[0] - start[0]
    vy = end[1] - start[1]
    length_squared = vx * vx + vy * vy
    if length_squared <= 1e-18:
        return distance(point, start)
    t = ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / length_squared
    t = max(0.0, min(1.0, t))
    projection = (start[0] + t * vx, start[1] + t * vy)
    return distance(point, projection)


def point_polygon_edge_distance(point: Point, polygon: Sequence[Point]) -> float:
    return min(
        point_segment_distance(point, polygon[index], polygon[(index + 1) % len(polygon)])
        for index in range(len(polygon))
    )


def orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a: Point, b: Point, c: Point, d: Point, tolerance: float = 1e-9) -> bool:
    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    if ((o1 > tolerance and o2 < -tolerance) or (o1 < -tolerance and o2 > tolerance)) and (
        (o3 > tolerance and o4 < -tolerance) or (o3 < -tolerance and o4 > tolerance)
    ):
        return True
    return (
        (abs(o1) <= tolerance and point_on_segment(c, a, b, tolerance))
        or (abs(o2) <= tolerance and point_on_segment(d, a, b, tolerance))
        or (abs(o3) <= tolerance and point_on_segment(a, c, d, tolerance))
        or (abs(o4) <= tolerance and point_on_segment(b, c, d, tolerance))
    )


def polygons_intersect(first: Sequence[Point], second: Sequence[Point]) -> bool:
    for first_index, first_start in enumerate(first):
        first_end = first[(first_index + 1) % len(first)]
        for second_index, second_start in enumerate(second):
            second_end = second[(second_index + 1) % len(second)]
            if segments_intersect(first_start, first_end, second_start, second_end):
                return True
    return point_in_polygon(first[0], second) or point_in_polygon(second[0], first)


def polygon_inside_polygon(inner: Sequence[Point], outer: Sequence[Point], tolerance: float = 1e-6) -> bool:
    return all(
        point_in_polygon(point, outer) or point_polygon_edge_distance(point, outer) <= tolerance
        for point in inner
    )


def transform_outline(
    outline: Sequence[Sequence[float]],
    width: float,
    depth: float,
    center: Point,
    rotation_radians: float,
) -> list[Point]:
    if width <= 0 or depth <= 0:
        raise ValueError("footprint width and depth must be positive")
    points = [as_point(point, "normalized outline point") for point in outline]
    if len(points) < 3:
        raise ValueError("normalized outline requires at least three points")
    if any(abs(value) > 0.5001 for point in points for value in point):
        raise ValueError("bbox-normalized outline coordinates must be centered in [-0.5, 0.5]")
    cosine = math.cos(rotation_radians)
    sine = math.sin(rotation_radians)
    result: list[Point] = []
    for x_value, y_value in points:
        local_x = x_value * width
        local_y = y_value * depth
        result.append(
            (
                center[0] + local_x * cosine - local_y * sine,
                center[1] + local_x * sine + local_y * cosine,
            )
        )
    return result


def translate_polygon(polygon: Sequence[Point], delta: Point) -> list[Point]:
    return [(point[0] + delta[0], point[1] + delta[1]) for point in polygon]


def polygon_bounds(polygon: Sequence[Point]) -> tuple[float, float, float, float]:
    return (
        min(point[0] for point in polygon),
        min(point[1] for point in polygon),
        max(point[0] for point in polygon),
        max(point[1] for point in polygon),
    )


def bbox_intersects(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    return not (
        first[2] < second[0]
        or second[2] < first[0]
        or first[3] < second[1]
        or second[3] < first[1]
    )


def path_bounds(path: Sequence[Point], margin: float) -> tuple[float, float, float, float]:
    bounds = polygon_bounds(path)
    return (bounds[0] - margin, bounds[1] - margin, bounds[2] + margin, bounds[3] + margin)


def downsample_path(path: Sequence[Point], limit: int = 96) -> list[list[float]]:
    if not path:
        return []
    if len(path) <= limit:
        selected = path
    else:
        step = (len(path) - 1) / (limit - 1)
        selected = [path[round(index * step)] for index in range(limit)]
    return [[round(point[0], 4), round(point[1], 4)] for point in selected]


def require_schema(value: dict[str, Any], expected: str, label: str) -> None:
    actual = value.get("schema")
    if actual != expected:
        raise ValueError(f"{label} schema must be {expected}, got {actual!r}")


def require_sha256(value: str | None, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value.lower()
