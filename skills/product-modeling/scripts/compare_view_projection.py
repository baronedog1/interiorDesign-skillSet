#!/usr/bin/env python3
"""Project the final occupied cells and enforce source-resolution zero-XOR gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_utils import (  # noqa: E402
    AXES,
    canonical_sha256,
    component_index,
    dump_json,
    load_json,
    mask_metrics,
    mask_sha256,
    registration_axes,
    resolve,
    rle_to_mask,
)


AXIS_INDEX = {axis: index for index, axis in enumerate(AXES)}


def occupancy_from_runs(component: dict[str, Any], shape: tuple[int, int, int]) -> np.ndarray:
    occupancy = np.zeros(shape, dtype=bool)
    for run in component["voxelRuns"]:
        if len(run) != 4:
            raise ValueError("voxel run must be [z,y,x0,x1]")
        z, y, x0, x1 = map(int, run)
        if not (0 <= z < shape[2] and 0 <= y < shape[1] and 0 <= x0 < x1 <= shape[0]):
            raise ValueError(f"invalid voxel run {run}")
        occupancy[x0:x1, y, z] = True
    if int(occupancy.sum()) != int(component["voxelCount"]):
        raise ValueError(f"voxelCount mismatch for {component['componentId']}")
    return occupancy


def world_to_source_pixel(
    values: np.ndarray,
    pixel_range: list[float],
    world_range: list[float],
) -> np.ndarray:
    p0, p1 = map(float, pixel_range)
    w0, w1 = map(float, world_range)
    pixels = p0 + (values - w0) * (p1 - p0) / (w1 - w0)
    return np.floor(pixels + 1e-10).astype(np.int64)


def project_to_source(
    occupancy: np.ndarray,
    axes: dict[str, list[float]],
    evidence: dict[str, Any],
) -> np.ndarray:
    registration = evidence["registration"]
    u_axis, v_axis, ray_axis = registration_axes(registration)
    ray_index = AXIS_INDEX[ray_axis]
    plane = occupancy.any(axis=ray_index)
    plane_axes = [axis for axis in AXES if axis != ray_axis]
    active = np.argwhere(plane)
    output = np.zeros(
        (int(evidence["source"]["height"]), int(evidence["source"]["width"])), dtype=bool
    )
    if active.size == 0:
        return output
    centers = {
        axis: (np.asarray(axes[axis][:-1]) + np.asarray(axes[axis][1:])) / 2
        for axis in plane_axes
    }
    index_by_axis = {axis: active[:, plane_axes.index(axis)] for axis in plane_axes}
    u_world = centers[u_axis][index_by_axis[u_axis]]
    v_world = centers[v_axis][index_by_axis[v_axis]]
    u_pixels = world_to_source_pixel(
        u_world, registration["uPixelRange"], registration["uWorldRange"]
    )
    v_pixels = world_to_source_pixel(
        v_world, registration["vPixelRange"], registration["vWorldRange"]
    )
    valid = (
        (u_pixels >= 0)
        & (u_pixels < output.shape[1])
        & (v_pixels >= 0)
        & (v_pixels < output.shape[0])
    )
    output[v_pixels[valid], u_pixels[valid]] = True
    return output


def save_mask(path: Path, mask: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), mask.astype(np.uint8) * 255):
        raise ValueError(f"failed to write {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("state")
    parser.add_argument("output")
    parser.add_argument("--mask-dir")
    arguments = parser.parse_args()
    plan_path = Path(arguments.plan).resolve()
    state_path = Path(arguments.state).resolve()
    plan = load_json(plan_path)
    state = load_json(state_path)
    if state.get("planSha256") != canonical_sha256(plan):
        raise SystemExit("state does not bind the supplied carving plan")
    if state.get("stateSha256") != canonical_sha256(state, {"stateSha256"}):
        raise SystemExit("state SHA-256 mismatch")

    axes = state["axes"]
    shape = tuple(len(axes[axis]) - 1 for axis in AXES)
    occupancies = {
        component["componentId"]: occupancy_from_runs(component, shape)
        for component in state["components"]
    }
    mask_dir = Path(arguments.mask_dir).resolve() if arguments.mask_dir else None
    view_reports = []
    all_gates_pass = True
    for reference in plan["evidence"]:
        if not reference.get("useForProjectionGate", True):
            continue
        evidence_path = resolve(plan_path, reference["path"])
        evidence = load_json(evidence_path)
        if evidence["viewType"] != "orthographic":
            continue
        target_product = rle_to_mask(evidence["productMask"])
        component_targets = component_index(evidence)
        actual_components: dict[str, np.ndarray] = {
            component_id: project_to_source(occupancy, axes, evidence)
            for component_id, occupancy in occupancies.items()
        }
        component_reports = []
        for component_id, target_component in component_targets.items():
            if component_id not in occupancies:
                raise SystemExit(f"evidence component {component_id} missing from state")
            actual = actual_components[component_id]
            if not target_component.get("projectionRequired", True):
                continue
            target = rle_to_mask(target_component["visibleMask"])
            metrics = mask_metrics(target, actual)
            metrics.update(
                {
                    "componentId": component_id,
                    "targetMaskSha256": target_component["visibleMask"]["sha256"],
                    "actualMaskSha256": mask_sha256(actual),
                }
            )
            component_reports.append(metrics)
            all_gates_pass &= metrics["pass"]
            if mask_dir:
                save_mask(mask_dir / f"{evidence['viewId']}-{component_id}-actual.png", actual)

        actual_product = np.zeros_like(target_product)
        for actual in actual_components.values():
            actual_product |= actual
        product_metrics = mask_metrics(target_product, actual_product)
        all_gates_pass &= product_metrics["pass"]
        product_metrics.update(
            {
                "targetMaskSha256": evidence["productMask"]["sha256"],
                "actualMaskSha256": mask_sha256(actual_product),
            }
        )
        if mask_dir:
            save_mask(mask_dir / f"{evidence['viewId']}-assembly-actual.png", actual_product)
            save_mask(mask_dir / f"{evidence['viewId']}-assembly-xor.png", target_product ^ actual_product)
        view_reports.append(
            {
                "viewId": evidence["viewId"],
                "evidenceCanonicalSha256": evidence["canonicalSha256"],
                "assembly": product_metrics,
                "components": component_reports,
                "pass": product_metrics["pass"] and all(item["pass"] for item in component_reports),
            }
        )

    report = {
        "schema": "interior.product-zero-xor-projection-report.v1",
        "planId": plan["planId"],
        "planSha256": canonical_sha256(plan),
        "stateSha256": state["stateSha256"],
        "gate": {
            "xorPixels": 0,
            "precision": 1.0,
            "recall": 1.0,
            "IoU": 1.0,
            "relaxationAllowed": False,
        },
        "views": view_reports,
        "pass": bool(all_gates_pass and view_reports),
        "reportSha256": "",
    }
    report["reportSha256"] = canonical_sha256(report, {"reportSha256"})
    dump_json(arguments.output, report)
    if not report["pass"]:
        raise SystemExit("zero-XOR projection gate failed")


if __name__ == "__main__":
    main()
