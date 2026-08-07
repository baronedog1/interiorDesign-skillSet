#!/usr/bin/env python3
"""Project STEP B-Rep triangles to source pixels and compare binary masks."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

try:
    from build123d import import_step
except ImportError as exc:  # pragma: no cover - exercised by interpreter gate
    raise SystemExit(
        "build123d is required; run with /home/agentops/.local/share/codex-cad-runtime/bin/python"
    ) from exc

from common import (
    ContractError,
    artifact_record,
    ensure_within,
    load_json,
    object_hash,
    project_root_from_document,
    resolve_in,
    sha256_file,
    write_json,
)


def read_mask(path: Path, width: int, height: int, mode: str) -> np.ndarray:
    with Image.open(path) as image:
        if image.size != (width, height):
            raise ContractError(f"Evidence mask size {image.size} != {(width, height)}: {path}")
        if mode == "alpha":
            return np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3] > 0
        gray = np.asarray(image.convert("L"), dtype=np.uint8)
    if mode == "white":
        return gray >= 128
    if mode == "black":
        return gray < 128
    raise ContractError(f"Unsupported foregroundMode: {mode}")


def validate_matrix(raw: Any) -> list[list[float]]:
    if not isinstance(raw, list) or len(raw) != 2 or any(not isinstance(row, list) or len(row) != 4 for row in raw):
        raise ContractError("cadToSource must be a 2x4 numeric matrix")
    matrix = [[float(value) for value in row] for row in raw]
    if any(not math.isfinite(value) for row in matrix for value in row):
        raise ContractError("cadToSource contains a non-finite value")
    return matrix


def project_point(matrix: list[list[float]], vector: Any, scale: int) -> tuple[float, float]:
    xyz1 = [float(vector.X), float(vector.Y), float(vector.Z), 1.0]
    u = sum(matrix[0][index] * xyz1[index] for index in range(4))
    v = sum(matrix[1][index] * xyz1[index] for index in range(4))
    return u * scale, v * scale


def rasterize(solids: list[Any], indices: list[int], matrix: list[list[float]], width: int, height: int, supersample: int, tolerance: float, angular_tolerance: float) -> np.ndarray:
    canvas = Image.new("L", (width * supersample, height * supersample), 0)
    draw = ImageDraw.Draw(canvas)
    for index in indices:
        if index < 0 or index >= len(solids):
            raise ContractError(f"solidIndices contains out-of-range index {index}; solid count={len(solids)}")
        vertices, triangles = solids[index].tessellate(tolerance, angular_tolerance)
        for triangle in triangles:
            points = [project_point(matrix, vertices[vertex_index], supersample) for vertex_index in triangle]
            area = abs(
                points[0][0] * (points[1][1] - points[2][1])
                + points[1][0] * (points[2][1] - points[0][1])
                + points[2][0] * (points[0][1] - points[1][1])
            )
            if area > 1e-8:
                draw.polygon(points, fill=255)
    if supersample > 1:
        canvas = canvas.resize((width, height), resample=Image.Resampling.NEAREST)
    return np.asarray(canvas, dtype=np.uint8) > 0


def bbox(mask: np.ndarray) -> list[int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def centroid(mask: np.ndarray) -> list[float] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return [float(xs.mean()), float(ys.mean())]


def compare(target: np.ndarray, actual: np.ndarray) -> dict[str, Any]:
    intersection = np.logical_and(target, actual)
    union = np.logical_or(target, actual)
    xor = np.logical_xor(target, actual)
    target_bbox, actual_bbox = bbox(target), bbox(actual)
    target_centroid, actual_centroid = centroid(target), centroid(actual)
    if target_bbox is None or actual_bbox is None or target_centroid is None or actual_centroid is None:
        bbox_delta = math.inf
        centroid_delta = math.inf
    else:
        bbox_delta = max(abs(left - right) for left, right in zip(target_bbox, actual_bbox))
        centroid_delta = math.hypot(
            target_centroid[0] - actual_centroid[0],
            target_centroid[1] - actual_centroid[1],
        )
    union_count = int(union.sum())
    return {
        "targetPixels": int(target.sum()),
        "actualPixels": int(actual.sum()),
        "intersectionPixels": int(intersection.sum()),
        "unionPixels": union_count,
        "xorPixels": int(xor.sum()),
        "xorRatio": float(xor.sum() / union_count) if union_count else 0.0,
        "iou": float(intersection.sum() / union_count) if union_count else 1.0,
        "targetBBox": target_bbox,
        "actualBBox": actual_bbox,
        "bboxMaxDeltaPx": bbox_delta,
        "targetCentroid": target_centroid,
        "actualCentroid": actual_centroid,
        "centroidDeltaPx": centroid_delta,
    }


def save_overlay(path: Path, target: np.ndarray, actual: np.ndarray) -> None:
    height, width = target.shape
    overlay = np.full((height, width, 3), 255, dtype=np.uint8)
    intersection = np.logical_and(target, actual)
    target_only = np.logical_and(target, np.logical_not(actual))
    actual_only = np.logical_and(actual, np.logical_not(target))
    overlay[intersection] = [50, 170, 85]
    overlay[target_only] = [225, 65, 65]
    overlay[actual_only] = [55, 105, 220]
    Image.fromarray(overlay, mode="RGB").save(path)


def build_report(job_path: Path, output_path: Path) -> dict[str, Any]:
    job = load_json(job_path)
    if job.get("schema") != "interior.cad-object-projection-job.v1":
        raise ContractError("Projection job schema must be interior.cad-object-projection-job.v1")
    project_root = project_root_from_document(job_path, str(job.get("projectRoot", ".")))
    output_path = ensure_within(project_root, output_path)
    step_path = resolve_in(project_root, job.get("step", ""))
    if step_path.suffix.lower() not in {".step", ".stp"} or not step_path.is_file():
        raise ContractError(f"Projection input is not a STEP file: {step_path}")
    step_sha = sha256_file(step_path)
    if job.get("stepSha256") != step_sha:
        raise ContractError("Projection job stepSha256 does not match STEP")
    try:
        shape = import_step(str(step_path))
    except Exception as exc:
        raise ContractError(f"Cannot import STEP: {exc}") from exc
    solids = list(shape.solids())
    if not solids:
        raise ContractError("STEP contains no solids")
    targets = job.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ContractError("Projection job targets must be a non-empty array")
    projection_dir = output_path.parent / f"{output_path.stem}-artifacts"
    projection_dir.mkdir(parents=True, exist_ok=True)
    target_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    tolerance = float(job.get("meshToleranceMm", 0.2))
    angular_tolerance = float(job.get("meshAngularTolerance", 0.08))
    supersample = int(job.get("supersample", 1))
    if tolerance <= 0 or angular_tolerance <= 0 or supersample < 1 or supersample > 8:
        raise ContractError("Invalid tessellation or supersample settings")
    for target_job in targets:
        target_id = target_job.get("targetId")
        if not isinstance(target_id, str) or not target_id or target_id in target_ids:
            raise ContractError(f"Invalid or duplicate targetId: {target_id!r}")
        target_ids.add(target_id)
        width, height = int(target_job["sourceSize"]["width"]), int(target_job["sourceSize"]["height"])
        if width <= 0 or height <= 0:
            raise ContractError(f"Invalid sourceSize for {target_id}")
        matrix = validate_matrix(target_job.get("cadToSource"))
        evidence_path = resolve_in(project_root, target_job.get("evidenceMask", ""))
        target_mask = read_mask(
            evidence_path,
            width,
            height,
            target_job.get("foregroundMode", "white"),
        )
        indices = target_job.get("solidIndices")
        if indices is None:
            indices = list(range(len(solids)))
        if not isinstance(indices, list) or not indices or any(not isinstance(index, int) for index in indices):
            raise ContractError(f"solidIndices must be a non-empty integer array for {target_id}")
        actual_mask = rasterize(
            solids,
            indices,
            matrix,
            width,
            height,
            supersample,
            tolerance,
            angular_tolerance,
        )
        metrics = compare(target_mask, actual_mask)
        thresholds = {
            "maxXorPixels": int(target_job.get("maxXorPixels", 0)),
            "maxXorRatio": float(target_job.get("maxXorRatio", 0.0)),
            "maxBBoxDeltaPx": float(target_job.get("maxBBoxDeltaPx", 0.0)),
            "maxCentroidDeltaPx": float(target_job.get("maxCentroidDeltaPx", 0.5)),
        }
        if any(value < 0 for value in thresholds.values()):
            raise ContractError(f"Negative projection threshold for {target_id}")
        passed = (
            metrics["xorPixels"] <= thresholds["maxXorPixels"]
            and metrics["xorRatio"] <= thresholds["maxXorRatio"]
            and metrics["bboxMaxDeltaPx"] <= thresholds["maxBBoxDeltaPx"]
            and metrics["centroidDeltaPx"] <= thresholds["maxCentroidDeltaPx"]
        )
        mask_path = projection_dir / f"{target_id}-actual.png"
        overlay_path = projection_dir / f"{target_id}-overlay.png"
        Image.fromarray(np.where(actual_mask, 255, 0).astype(np.uint8), mode="L").save(mask_path)
        save_overlay(overlay_path, target_mask, actual_mask)
        results.append(
            {
                "targetId": target_id,
                "viewId": target_job.get("viewId", target_id),
                "required": bool(target_job.get("required", True)),
                "solidIndices": indices,
                "evidenceMask": artifact_record(project_root, evidence_path),
                "actualMask": artifact_record(project_root, mask_path),
                "overlay": artifact_record(project_root, overlay_path),
                "metrics": metrics,
                "thresholds": thresholds,
                "passed": passed,
            }
        )
    overall = all(result["passed"] for result in results if result["required"])
    report: dict[str, Any] = {
        "schema": "interior.cad-object-projection-report.v1",
        "objectId": job.get("objectId"),
        "step": artifact_record(project_root, step_path),
        "solidCount": len(solids),
        "meshToleranceMm": tolerance,
        "meshAngularTolerance": angular_tolerance,
        "targets": results,
        "overallPassed": overall,
        "projectionHash": "",
    }
    report["projectionHash"] = object_hash(report, "projectionHash")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args.job.resolve(), args.output.resolve())
        write_json(args.output.resolve(), report)
        if not report["overallPassed"]:
            print("STEP projection gates failed", file=sys.stderr)
            return 1
        print(f"STEP projection passed: targets={len(report['targets'])}")
        return 0
    except ContractError as exc:
        print(f"STEP projection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
