#!/usr/bin/env python3
"""Shared deterministic mask, hashing, and registration helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np


AXES = ("x", "y", "z")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any, omit_keys: Iterable[str] = ()) -> bytes:
    omitted = set(omit_keys)

    def cleaned(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: cleaned(val)
                for key, val in sorted(item.items())
                if key not in omitted
            }
        if isinstance(item, list):
            return [cleaned(val) for val in item]
        return item

    return json.dumps(
        cleaned(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: Any, omit_keys: Iterable[str] = ()) -> str:
    return sha256_bytes(canonical_bytes(value, omit_keys))


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve(base_file: str | Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (Path(base_file).resolve().parent / path).resolve()


def mask_sha256(mask: np.ndarray) -> str:
    binary = np.ascontiguousarray(mask.astype(np.uint8))
    header = f"{binary.shape[1]}x{binary.shape[0]}:row-major:u8\n".encode()
    return sha256_bytes(header + binary.tobytes())


def mask_to_rle(mask: np.ndarray) -> dict[str, Any]:
    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 2:
        raise ValueError("mask must be 2D")
    height, width = binary.shape
    runs: list[list[int]] = []
    for y in range(height):
        row = binary[y]
        padded = np.pad(row.astype(np.int8), (1, 1))
        transitions = np.flatnonzero(np.diff(padded))
        for start, end in transitions.reshape(-1, 2):
            runs.append([int(y), int(start), int(end)])
    return {
        "encoding": "row-rle-v1",
        "width": int(width),
        "height": int(height),
        "runs": runs,
        "pixelCount": int(binary.sum()),
        "sha256": mask_sha256(binary),
    }


def rle_to_mask(encoded: dict[str, Any], *, validate: bool = True) -> np.ndarray:
    if encoded.get("encoding") != "row-rle-v1":
        raise ValueError("unsupported mask encoding")
    width = int(encoded["width"])
    height = int(encoded["height"])
    mask = np.zeros((height, width), dtype=bool)
    previous = (-1, -1)
    for run in encoded.get("runs", []):
        if len(run) != 3:
            raise ValueError("each row-rle run must contain y,x0,x1")
        y, x0, x1 = map(int, run)
        if not (0 <= y < height and 0 <= x0 < x1 <= width):
            raise ValueError(f"out-of-range run: {run}")
        if (y, x0) <= previous:
            raise ValueError("runs must be strictly row-major sorted")
        if np.any(mask[y, x0:x1]):
            raise ValueError("overlapping row-rle runs")
        mask[y, x0:x1] = True
        previous = (y, x0)
    if validate:
        if int(mask.sum()) != int(encoded.get("pixelCount", -1)):
            raise ValueError("mask pixelCount mismatch")
        if mask_sha256(mask) != encoded.get("sha256"):
            raise ValueError("mask sha256 mismatch")
    return mask


def component_index(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for component in evidence.get("components", []):
        component_id = component["componentId"]
        if component_id in result:
            raise ValueError(f"duplicate componentId {component_id}")
        result[component_id] = component
    return result


def registration_axes(registration: dict[str, Any]) -> tuple[str, str, str]:
    axes = (
        registration["uAxis"],
        registration["vAxis"],
        registration["rayAxis"],
    )
    if set(axes) != set(AXES):
        raise ValueError(f"registration axes must be a permutation of {AXES}: {axes}")
    return axes


def pixel_boundary_to_world(
    pixel: float, pixel_range: list[float], world_range: list[float]
) -> float:
    p0, p1 = map(float, pixel_range)
    w0, w1 = map(float, world_range)
    if p1 == p0:
        raise ValueError("zero-length pixel range")
    return w0 + (pixel - p0) * (w1 - w0) / (p1 - p0)


def world_to_pixel_index(
    values: np.ndarray,
    pixel_range: list[float],
    world_range: list[float],
    limit: int,
) -> tuple[np.ndarray, np.ndarray]:
    p0, p1 = map(float, pixel_range)
    w0, w1 = map(float, world_range)
    if w1 == w0:
        raise ValueError("zero-length world range")
    pixels = p0 + (values - w0) * (p1 - p0) / (w1 - w0)
    indices = np.floor(pixels).astype(np.int64)
    valid = (indices >= 0) & (indices < limit)
    return np.clip(indices, 0, max(0, limit - 1)), valid


def axis_coordinates_from_registration(
    registration: dict[str, Any], axis: str
) -> list[float]:
    if registration["uAxis"] == axis:
        pixel_range = registration["uPixelRange"]
        world_range = registration["uWorldRange"]
    elif registration["vAxis"] == axis:
        pixel_range = registration["vPixelRange"]
        world_range = registration["vWorldRange"]
    else:
        return []
    p0, p1 = map(float, pixel_range)
    start = int(round(min(p0, p1)))
    end = int(round(max(p0, p1)))
    if abs(start - min(p0, p1)) > 1e-8 or abs(end - max(p0, p1)) > 1e-8:
        raise ValueError("pixel ranges must use integer boundaries")
    return [
        pixel_boundary_to_world(float(pixel), pixel_range, world_range)
        for pixel in range(start, end + 1)
    ]


def mask_metrics(target: np.ndarray, actual: np.ndarray) -> dict[str, Any]:
    target = np.asarray(target, dtype=bool)
    actual = np.asarray(actual, dtype=bool)
    if target.shape != actual.shape:
        raise ValueError("mask shapes differ")
    true_positive = int(np.logical_and(target, actual).sum())
    false_positive = int(np.logical_and(~target, actual).sum())
    false_negative = int(np.logical_and(target, ~actual).sum())
    union = true_positive + false_positive + false_negative
    precision = 1.0 if true_positive + false_positive == 0 else true_positive / (true_positive + false_positive)
    recall = 1.0 if true_positive + false_negative == 0 else true_positive / (true_positive + false_negative)
    iou = 1.0 if union == 0 else true_positive / union
    xor_pixels = false_positive + false_negative
    return {
        "targetPixels": int(target.sum()),
        "actualPixels": int(actual.sum()),
        "truePositive": true_positive,
        "falsePositive": false_positive,
        "falseNegative": false_negative,
        "xorPixels": xor_pixels,
        "precision": precision,
        "recall": recall,
        "IoU": iou,
        "pass": xor_pixels == 0 and precision == 1.0 and recall == 1.0 and iou == 1.0,
    }
