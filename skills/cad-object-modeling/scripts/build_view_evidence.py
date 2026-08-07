#!/usr/bin/env python3
"""Rasterize component boundaries and enforce exact visible-region coverage."""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from common import (
    ContractError,
    artifact_record,
    ensure_within,
    load_json,
    object_hash,
    project_root_from_document,
    relative_path,
    resolve_in,
    sha256_file,
    validate_schema,
    write_json,
)
from validate_source_inventory import validate_inventory


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
        and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9
        and abs(cross(a, b, p)) <= 1e-9
    )


def segments_intersect(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    ab_c, ab_d = cross(a, b, c), cross(a, b, d)
    cd_a, cd_b = cross(c, d, a), cross(c, d, b)
    if ((ab_c > 0 > ab_d) or (ab_d > 0 > ab_c)) and ((cd_a > 0 > cd_b) or (cd_b > 0 > cd_a)):
        return True
    return any(
        (
            abs(value) <= 1e-9,
            on_segment(seg_a, seg_b, point),
        )
        == (True, True)
        for value, seg_a, seg_b, point in (
            (ab_c, a, b, c),
            (ab_d, a, b, d),
            (cd_a, c, d, a),
            (cd_b, c, d, b),
        )
    )


def normalize_ring(raw: Any, width: int, height: int, label: str) -> list[list[float]]:
    if not isinstance(raw, list) or len(raw) < 3:
        raise ContractError(f"{label} must contain at least three points")
    ring: list[tuple[float, float]] = []
    for point in raw:
        if not isinstance(point, list) or len(point) != 2:
            raise ContractError(f"{label} contains an invalid point")
        x, y = float(point[0]), float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise ContractError(f"{label} contains a non-finite point")
        if x < 0 or y < 0 or x > width - 1 or y > height - 1:
            raise ContractError(f"{label} point {(x, y)} lies outside source pixels")
        ring.append((x, y))
    if ring[0] == ring[-1]:
        ring.pop()
    if len(ring) < 3 or len(set(ring)) < 3:
        raise ContractError(f"{label} does not define a valid area")
    area = sum(
        ring[index][0] * ring[(index + 1) % len(ring)][1]
        - ring[(index + 1) % len(ring)][0] * ring[index][1]
        for index in range(len(ring))
    )
    if abs(area) <= 1e-9:
        raise ContractError(f"{label} has zero area")
    count = len(ring)
    for first in range(count):
        a, b = ring[first], ring[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count} or (second + 1) % count == first:
                continue
            c, d = ring[second], ring[(second + 1) % count]
            if segments_intersect(a, b, c, d):
                raise ContractError(f"{label} self-intersects")
    return [[point[0], point[1]] for point in ring]


def read_binary_mask(path: Path, width: int, height: int, mode: str) -> np.ndarray:
    with Image.open(path) as image:
        if image.size != (width, height):
            raise ContractError(f"Mask size {image.size} does not match source {(width, height)}: {path}")
        if mode == "alpha":
            array = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
            return array > 0
        array = np.asarray(image.convert("L"), dtype=np.uint8)
    if mode == "black":
        return array < 128
    if mode != "white":
        raise ContractError(f"Unsupported foregroundMode: {mode}")
    return array >= 128


def bbox(mask: np.ndarray) -> list[int]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise ContractError("Component mask is empty")
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def render_component(component: dict[str, Any], width: int, height: int, label: str) -> tuple[Image.Image, list[list[list[float]]], list[list[list[float]]]]:
    boundary_rings = [
        normalize_ring(ring, width, height, f"{label}.boundaryRings[{index}]")
        for index, ring in enumerate(component.get("boundaryRings", []))
    ]
    if not boundary_rings:
        raise ContractError(f"{label} requires at least one boundary ring")
    hole_rings = [
        normalize_ring(ring, width, height, f"{label}.holeRings[{index}]")
        for index, ring in enumerate(component.get("holeRings", []))
    ]
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    for ring in boundary_rings:
        draw.polygon([tuple(point) for point in ring], fill=255)
    for ring in hole_rings:
        draw.polygon([tuple(point) for point in ring], fill=0)
    return image, boundary_rings, hole_rings


def build_evidence(job_path: Path, output_path: Path) -> dict[str, Any]:
    job = load_json(job_path)
    if job.get("schema") != "interior.cad-object-boundary-job.v1":
        raise ContractError("Boundary job schema must be interior.cad-object-boundary-job.v1")
    project_root = project_root_from_document(job_path, str(job.get("projectRoot", ".")))
    output_path = ensure_within(project_root, output_path)
    inventory_path = resolve_in(project_root, job.get("sourceInventory", ""))
    inventory = validate_inventory(inventory_path)
    inventory_file_hash = sha256_file(inventory_path)
    expected_inventory_hash = job.get("sourceInventorySha256")
    if expected_inventory_hash and expected_inventory_hash != inventory_file_hash:
        raise ContractError("Boundary job source inventory SHA-256 mismatch")
    if job.get("objectId") != inventory["objectId"]:
        raise ContractError("Boundary job objectId does not match source inventory")
    sources = {source["sourceId"]: source for source in inventory["sources"]}
    views_job = job.get("views")
    if not isinstance(views_job, list) or not views_job:
        raise ContractError("Boundary job views must be a non-empty array")
    output_dir = output_path.parent / "view-evidence"
    output_dir.mkdir(parents=True, exist_ok=True)
    view_ids: set[str] = set()
    compiled_views: list[dict[str, Any]] = []
    for raw_view in views_job:
        view_id = raw_view.get("viewId")
        source_id = raw_view.get("sourceId")
        if not isinstance(view_id, str) or not view_id or view_id in view_ids:
            raise ContractError(f"Invalid or duplicate viewId in boundary job: {view_id!r}")
        view_ids.add(view_id)
        if source_id not in sources:
            raise ContractError(f"View {view_id} references unknown sourceId")
        source = sources[source_id]
        if source["view"]["viewId"] != view_id:
            raise ContractError(f"View {view_id} does not match frozen source viewId")
        if source["imageSize"] is None:
            raise ContractError(f"View {view_id} source is not a raster")
        width, height = source["imageSize"]["width"], source["imageSize"]["height"]
        target_path = resolve_in(project_root, raw_view.get("foregroundMask", ""))
        foreground_mode = raw_view.get("foregroundMode", "white")
        target = read_binary_mask(target_path, width, height, foreground_mode)
        components_job = raw_view.get("components")
        if not isinstance(components_job, list) or not components_job:
            raise ContractError(f"View {view_id} requires component boundaries")
        component_ids: set[str] = set()
        masks: list[np.ndarray] = []
        components: list[dict[str, Any]] = []
        view_dir = output_dir / view_id
        view_dir.mkdir(parents=True, exist_ok=True)
        for index, raw_component in enumerate(components_job):
            component_id = raw_component.get("componentId")
            if not isinstance(component_id, str) or not SAFE_ID.fullmatch(component_id) or component_id in component_ids:
                raise ContractError(f"Invalid or duplicate componentId in {view_id}: {component_id!r}")
            component_ids.add(component_id)
            component_image, boundaries, holes = render_component(
                raw_component, width, height, f"{view_id}.components[{index}]"
            )
            component_mask = np.asarray(component_image, dtype=np.uint8) > 0
            count = int(component_mask.sum())
            if count <= 0:
                raise ContractError(f"Component {component_id} has no visible pixels in {view_id}")
            mask_path = view_dir / f"{component_id}.png"
            component_image.save(mask_path)
            masks.append(component_mask)
            components.append(
                {
                    "componentId": component_id,
                    "boundaryRings": boundaries,
                    "holeRings": holes,
                    "mask": artifact_record(project_root, mask_path),
                    "pixelCount": count,
                    "bbox": bbox(component_mask),
                }
            )
        stack = np.stack(masks, axis=0)
        overlap_pixels = int((stack.sum(axis=0) > 1).sum())
        union = stack.any(axis=0)
        missing_pixels = int(np.logical_and(target, np.logical_not(union)).sum())
        extra_pixels = int(np.logical_and(union, np.logical_not(target)).sum())
        tolerance = raw_view.get("tolerance", {})
        maximums = {
            "maxMissingPixels": int(tolerance.get("maxMissingPixels", 0)),
            "maxExtraPixels": int(tolerance.get("maxExtraPixels", 0)),
            "maxOverlapPixels": int(tolerance.get("maxOverlapPixels", 0)),
        }
        if any(value < 0 for value in maximums.values()):
            raise ContractError(f"View {view_id} tolerances cannot be negative")
        rationale = str(tolerance.get("rationale", ""))
        if any(value > 0 for value in maximums.values()) and not rationale:
            raise ContractError(f"View {view_id} non-zero tolerance requires a rationale")
        passed = (
            missing_pixels <= maximums["maxMissingPixels"]
            and extra_pixels <= maximums["maxExtraPixels"]
            and overlap_pixels <= maximums["maxOverlapPixels"]
        )
        union_path = view_dir / "union.png"
        Image.fromarray(np.where(union, 255, 0).astype(np.uint8), mode="L").save(union_path)
        compiled_views.append(
            {
                "viewId": view_id,
                "sourceId": source_id,
                "sourceSha256": source["sha256"],
                "sourceSize": {"width": width, "height": height},
                "foregroundMask": artifact_record(project_root, target_path),
                "components": components,
                "unionMask": artifact_record(project_root, union_path),
                "gates": {
                    "missingPixels": missing_pixels,
                    "extraPixels": extra_pixels,
                    "overlapPixels": overlap_pixels,
                    **maximums,
                    "toleranceRationale": rationale,
                },
                "passed": passed,
            }
        )
    report: dict[str, Any] = {
        "schema": "interior.cad-object-view-evidence.v1",
        "objectId": inventory["objectId"],
        "sourceInventory": {
            "path": relative_path(project_root, inventory_path),
            "sha256": inventory_file_hash,
        },
        "views": compiled_views,
        "overallPassed": all(view["passed"] for view in compiled_views),
        "evidenceHash": "",
    }
    report["evidenceHash"] = object_hash(report, "evidenceHash")
    validate_schema(report, "view-evidence.schema.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = build_evidence(args.job.resolve(), args.output.resolve())
        write_json(args.output.resolve(), report)
        if not report["overallPassed"]:
            print("view evidence failed pixel gates", file=sys.stderr)
            return 1
        print(f"view evidence passed: views={len(report['views'])}")
        return 0
    except ContractError as exc:
        print(f"view evidence failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
