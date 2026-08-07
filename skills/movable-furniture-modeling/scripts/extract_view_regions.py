#!/usr/bin/env python3
"""Segment a frozen source view into source-resolution component regions.

The operator supplies only rough semantic seeds and explicit annotation/background
exclusions. GrabCut establishes the product region and a marker watershed assigns
every product pixel to exactly one component. No final boundary polyline is accepted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_utils import (  # noqa: E402
    canonical_sha256,
    dump_json,
    mask_to_rle,
    resolve,
    sha256_file,
)


def seed_tuple(seed: dict) -> tuple[int, int, int]:
    return int(seed["x"]), int(seed["y"]), int(seed.get("radius", 3))


def paint_seed(mask: np.ndarray, seed: dict, value: int) -> None:
    x, y, radius = seed_tuple(seed)
    if not (0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]):
        raise ValueError(f"seed outside source: {(x, y)}")
    cv2.circle(mask, (x, y), max(1, radius), int(value), thickness=-1)


def paint_rect(mask: np.ndarray, rect: list[int], value: int) -> None:
    if len(rect) != 4:
        raise ValueError("rectangle must be [x,y,width,height]")
    x, y, width, height = map(int, rect)
    if width <= 0 or height <= 0:
        raise ValueError("rectangle width/height must be positive")
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(mask.shape[1], x + width), min(mask.shape[0], y + height)
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"rectangle outside source: {rect}")
    mask[y0:y1, x0:x1] = value


def retain_seeded_islands(product: np.ndarray, seed_points: list[tuple[int, int]]) -> np.ndarray:
    count, labels = cv2.connectedComponents(product.astype(np.uint8), connectivity=8)
    accepted: set[int] = set()
    for x, y in seed_points:
        label = int(labels[y, x])
        if label > 0:
            accepted.add(label)
    if not accepted:
        raise ValueError("foreground/component seeds did not land in the product mask")
    return np.isin(labels, list(accepted))


def fill_unassigned(labels: np.ndarray, product: np.ndarray, component_labels: list[int]) -> np.ndarray:
    assigned = product & np.isin(labels, component_labels)
    missing = product & ~assigned
    if not np.any(missing):
        return labels
    distances = []
    for label in component_labels:
        region = labels == label
        if not np.any(region):
            raise ValueError(f"watershed component label {label} is empty")
        distances.append(cv2.distanceTransform((~region).astype(np.uint8), cv2.DIST_L2, 5))
    nearest = np.argmin(np.stack(distances, axis=0), axis=0)
    for index, label in enumerate(component_labels):
        labels[missing & (nearest == index)] = label
    return labels


def save_review_images(
    image: np.ndarray,
    product: np.ndarray,
    component_masks: list[np.ndarray],
    colors: list[str],
    outputs: dict,
    job_path: Path,
) -> dict:
    written: dict[str, str] = {}
    palette = []
    for color in colors:
        value = color.lstrip("#")
        if len(value) != 6:
            raise ValueError(f"invalid component color {color}")
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
        palette.append((blue, green, red))

    label_image = np.zeros_like(image)
    overlay = image.copy()
    for component_mask, color in zip(component_masks, palette):
        label_image[component_mask] = color
        overlay[component_mask] = np.round(
            overlay[component_mask].astype(np.float32) * 0.46
            + np.array(color, dtype=np.float32) * 0.54
        ).astype(np.uint8)
    boundary = np.zeros(product.shape, np.uint8)
    for component_mask in component_masks:
        contour, _ = cv2.findContours(
            component_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        cv2.drawContours(boundary, contour, -1, 255, 1)
    overlay[boundary > 0] = (16, 16, 16)

    images = {
        "productMask": product.astype(np.uint8) * 255,
        "componentLabels": label_image,
        "overlay": overlay,
    }
    for name, output_value in outputs.items():
        if name not in images:
            continue
        target = resolve(job_path, output_value)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), images[name]):
            raise ValueError(f"failed to write {target}")
        written[name] = str(output_value)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job")
    parser.add_argument("output")
    arguments = parser.parse_args()
    job_path = Path(arguments.job).resolve()
    output_path = Path(arguments.output).resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    if job.get("schema") != "interior.product-view-segmentation-job.v1":
        raise SystemExit("unsupported segmentation job schema")

    source_path = resolve(job_path, job["sourcePath"])
    actual_source_hash = sha256_file(source_path)
    if actual_source_hash != job.get("sourceSha256"):
        raise SystemExit("source SHA-256 mismatch")
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"cannot read source {source_path}")
    height, width = image.shape[:2]
    settings = job["segmentation"]

    grab_mask = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)
    roi = settings["roi"]
    x, y, roi_width, roi_height = map(int, roi)
    if not (0 <= x < width and 0 <= y < height and x + roi_width <= width and y + roi_height <= height):
        raise SystemExit("roi outside source")
    grab_mask[y : y + roi_height, x : x + roi_width] = cv2.GC_PR_FGD

    exclusion = np.ones((height, width), dtype=np.uint8)
    exclusion[y : y + roi_height, x : x + roi_width] = False
    for rect in settings.get("backgroundRects", []):
        paint_rect(grab_mask, rect, cv2.GC_BGD)
        paint_rect(exclusion, rect, True)
    for seed in settings.get("backgroundSeeds", []):
        paint_seed(grab_mask, seed, cv2.GC_BGD)
        paint_seed(exclusion, seed, True)

    component_seeds: list[tuple[int, int]] = []
    for component in job["components"]:
        for seed in component["seeds"]:
            paint_seed(grab_mask, seed, cv2.GC_FGD)
            component_seeds.append(seed_tuple(seed)[:2])
    for seed in settings.get("foregroundSeeds", []):
        paint_seed(grab_mask, seed, cv2.GC_FGD)
        component_seeds.append(seed_tuple(seed)[:2])

    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(
        image,
        grab_mask,
        None,
        background_model,
        foreground_model,
        int(settings.get("grabCutIterations", 8)),
        cv2.GC_INIT_WITH_MASK,
    )
    exclusion = exclusion.astype(bool)
    product = np.isin(grab_mask, (cv2.GC_FGD, cv2.GC_PR_FGD))
    product &= ~exclusion
    close_kernel = settings.get("productCloseKernel")
    if close_kernel:
        kernel_width, kernel_height = map(int, close_kernel)
        if kernel_width < 1 or kernel_height < 1 or kernel_width % 2 == 0 or kernel_height % 2 == 0:
            raise SystemExit("productCloseKernel must contain positive odd width/height")
        kernel = np.ones((kernel_height, kernel_width), np.uint8)
        product = cv2.morphologyEx(product.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
        product &= ~exclusion
    if settings.get("fillEnclosedHoles", False):
        contours, _ = cv2.findContours(product.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        filled = np.zeros(product.shape, np.uint8)
        cv2.drawContours(filled, contours, -1, 1, thickness=-1)
        product = (filled > 0) & ~exclusion
    product = retain_seeded_islands(product, component_seeds)

    markers = np.zeros((height, width), np.int32)
    markers[~product] = 1
    component_labels = []
    for component_index, component in enumerate(job["components"], start=2):
        component_labels.append(component_index)
        for seed in component["seeds"]:
            paint_seed(markers, seed, component_index)
    watershed_image = image.copy()
    cv2.watershed(watershed_image, markers)
    markers = fill_unassigned(markers, product, component_labels)

    component_masks: list[np.ndarray] = []
    components = []
    for label, component in zip(component_labels, job["components"]):
        component_mask = product & (markers == label)
        if not np.any(component_mask):
            raise SystemExit(f"component {component['componentId']} is empty")
        component_masks.append(component_mask)
        carving_role = component.get("carvingMaskRole", "component-region")
        if carving_role not in {"component-region", "assembly-silhouette"}:
            raise SystemExit(f"unsupported carvingMaskRole {carving_role}")
        carving_mask = product if carving_role == "assembly-silhouette" else component_mask
        components.append(
            {
                "componentId": component["componentId"],
                "label": component["label"],
                "visibleMask": mask_to_rle(component_mask),
                "carvingMask": mask_to_rle(carving_mask),
                "carvingMaskRole": carving_role,
                "depthOrder": int(component.get("depthOrder", 0)),
                "projectionRequired": bool(component.get("projectionRequired", True)),
                "occlusion": component.get("occlusion", "none"),
                "seedCount": len(component["seeds"]),
                "color": component.get("color", "#66a3ff"),
            }
        )

    union = np.zeros_like(product)
    overlap_pixels = 0
    for component_mask in component_masks:
        overlap_pixels += int(np.logical_and(union, component_mask).sum())
        union |= component_mask
    if overlap_pixels or not np.array_equal(union, product):
        raise SystemExit("component partition invariant failed")

    output_images = save_review_images(
        image,
        product,
        component_masks,
        [component.get("color", "#66a3ff") for component in job["components"]],
        job.get("outputs", {}),
        job_path,
    )
    evidence = {
        "schema": "interior.product-view-region-evidence.v1",
        "viewId": job["viewId"],
        "viewType": job["viewType"],
        "source": {
            "path": os.path.relpath(source_path, output_path.parent),
            "sha256": actual_source_hash,
            "width": width,
            "height": height,
        },
        "registration": job["registration"],
        "segmentation": {
            "algorithm": "grabcut-product-plus-marker-watershed-components-v1",
            "jobSha256": canonical_sha256(job),
            "roi": roi,
            "grabCutIterations": int(settings.get("grabCutIterations", 8)),
            "productCloseKernel": close_kernel,
            "fillEnclosedHoles": bool(settings.get("fillEnclosedHoles", False)),
            "finalBoundaryCoordinatesAuthoredByAgent": False,
        },
        "productMask": mask_to_rle(product),
        "backgroundExclusionMask": mask_to_rle(exclusion),
        "components": components,
        "quality": {
            "productPixels": int(product.sum()),
            "componentCoverage": 1.0,
            "overlapPixels": 0,
            "sourceResolution": [width, height],
        },
        "reviewImages": output_images,
        "canonicalSha256": "",
    }
    evidence["canonicalSha256"] = canonical_sha256(evidence, {"canonicalSha256"})
    dump_json(output_path, evidence)


if __name__ == "__main__":
    main()
