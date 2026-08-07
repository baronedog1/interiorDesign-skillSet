#!/usr/bin/env python3
"""Build the unique multi-view visual-hull state by mask-prism intersection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_utils import (  # noqa: E402
    AXES,
    axis_coordinates_from_registration,
    canonical_sha256,
    component_index,
    dump_json,
    load_json,
    registration_axes,
    resolve,
    rle_to_mask,
)


AXIS_INDEX = {axis: index for index, axis in enumerate(AXES)}


def rounded_unique(values: list[float]) -> list[float]:
    return sorted({round(float(value), 12) for value in values})


def load_evidence(plan_path: Path, plan: dict[str, Any]) -> list[tuple[dict, dict, Path]]:
    loaded = []
    for reference in plan["evidence"]:
        path = resolve(plan_path, reference["path"])
        evidence = load_json(path)
        if evidence.get("schema") != "interior.product-view-region-evidence.v1":
            raise ValueError(f"unsupported evidence schema in {path}")
        if evidence["viewId"] != reference["viewId"]:
            raise ValueError(f"viewId mismatch for {path}")
        expected = canonical_sha256(evidence, {"canonicalSha256"})
        if expected != evidence.get("canonicalSha256"):
            raise ValueError(f"evidence canonical hash mismatch for {path}")
        registration_axes(evidence["registration"])
        loaded.append((reference, evidence, path))
    return loaded


def build_axes(plan: dict[str, Any], loaded: list[tuple[dict, dict, Path]]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {axis: [] for axis in AXES}
    for reference, evidence, _ in loaded:
        if not reference.get("useForCarving", True) or evidence["viewType"] != "orthographic":
            continue
        for axis in AXES:
            values[axis].extend(axis_coordinates_from_registration(evidence["registration"], axis))
    for component in plan["components"]:
        for axis, bounds in component.get("axisBounds", {}).items():
            if axis not in values or len(bounds) != 2:
                raise ValueError(f"invalid {axis} axisBounds for {component['componentId']}")
            values[axis].extend(map(float, bounds))
    for axis in AXES:
        if not values[axis]:
            fallback = plan["axisFallbacks"].get(axis)
            if fallback is None:
                raise ValueError(f"axis {axis} has no view evidence or fallback")
            start, end = float(fallback["min"]), float(fallback["max"])
            cells = int(fallback["cells"])
            values[axis].extend(np.linspace(start, end, cells + 1).tolist())
        values[axis] = rounded_unique(values[axis])
        if len(values[axis]) < 2 or any(
            right <= left for left, right in zip(values[axis], values[axis][1:])
        ):
            raise ValueError(f"axis {axis} is not strictly increasing")
    return values


def world_to_pixel_index(
    values: np.ndarray,
    pixel_range: list[float],
    world_range: list[float],
    limit: int,
) -> tuple[np.ndarray, np.ndarray]:
    p0, p1 = map(float, pixel_range)
    w0, w1 = map(float, world_range)
    pixels = p0 + (values - w0) * (p1 - p0) / (w1 - w0)
    indices = np.floor(pixels + 1e-10).astype(np.int64)
    valid = (indices >= 0) & (indices < limit)
    return np.clip(indices, 0, max(0, limit - 1)), valid


def mask_prism(mask: np.ndarray, registration: dict, axes: dict[str, list[float]]) -> np.ndarray:
    centers = {
        axis: (np.asarray(coordinates[:-1]) + np.asarray(coordinates[1:])) / 2
        for axis, coordinates in axes.items()
    }
    u_axis, v_axis, _ = registration_axes(registration)
    u_indices, u_valid = world_to_pixel_index(
        centers[u_axis], registration["uPixelRange"], registration["uWorldRange"], mask.shape[1]
    )
    v_indices, v_valid = world_to_pixel_index(
        centers[v_axis], registration["vPixelRange"], registration["vWorldRange"], mask.shape[0]
    )
    u_shape = [1, 1, 1]
    v_shape = [1, 1, 1]
    u_shape[AXIS_INDEX[u_axis]] = len(u_indices)
    v_shape[AXIS_INDEX[v_axis]] = len(v_indices)
    u_grid = u_indices.reshape(u_shape)
    v_grid = v_indices.reshape(v_shape)
    valid = u_valid.reshape(u_shape) & v_valid.reshape(v_shape)
    return valid & mask[v_grid, u_grid]


def apply_axis_bounds(occupancy: np.ndarray, component: dict, axes: dict[str, list[float]]) -> None:
    for axis, bounds in component.get("axisBounds", {}).items():
        coordinates = np.asarray(axes[axis])
        centers = (coordinates[:-1] + coordinates[1:]) / 2
        low, high = sorted(map(float, bounds))
        allowed = (centers >= low - 1e-12) & (centers <= high + 1e-12)
        shape = [1, 1, 1]
        shape[AXIS_INDEX[axis]] = len(allowed)
        occupancy &= allowed.reshape(shape)


def voxel_runs(occupancy: np.ndarray) -> list[list[int]]:
    nx, ny, nz = occupancy.shape
    runs: list[list[int]] = []
    for z in range(nz):
        for y in range(ny):
            row = occupancy[:, y, z]
            padded = np.pad(row.astype(np.int8), (1, 1))
            transitions = np.flatnonzero(np.diff(padded))
            for start, end in transitions.reshape(-1, 2):
                runs.append([z, y, int(start), int(end)])
    return runs


def greedy_rectangles(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    work = np.asarray(mask, dtype=bool).copy()
    rows, columns = work.shape
    rectangles: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        column = 0
        while column < columns:
            if not work[row, column]:
                column += 1
                continue
            end_column = column + 1
            while end_column < columns and work[row, end_column]:
                end_column += 1
            end_row = row + 1
            while end_row < rows and np.all(work[end_row, column:end_column]):
                end_row += 1
            work[row:end_row, column:end_column] = False
            rectangles.append((row, end_row, column, end_column))
            column = end_column
    return rectangles


def append_quad(
    positions: list[float], indices: list[int], corners: list[tuple[float, float, float]], flip: bool
) -> None:
    base = len(positions) // 3
    for corner in corners:
        positions.extend(round(float(value), 8) for value in corner)
    if flip:
        indices.extend([base, base + 3, base + 2, base, base + 2, base + 1])
    else:
        indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])


def mesh_from_voxels(occupancy: np.ndarray, axes: dict[str, list[float]]) -> dict[str, Any]:
    x_coordinates = axes["x"]
    y_coordinates = axes["y"]
    z_coordinates = axes["z"]
    nx, ny, nz = occupancy.shape
    positions: list[float] = []
    indices: list[int] = []

    for x_index in range(nx + 1):
        left = occupancy[x_index - 1, :, :] if x_index > 0 else np.zeros((ny, nz), bool)
        right = occupancy[x_index, :, :] if x_index < nx else np.zeros((ny, nz), bool)
        for mask, flip in ((left & ~right, False), (right & ~left, True)):
            for y0, y1, z0, z1 in greedy_rectangles(mask):
                x = x_coordinates[x_index]
                corners = [
                    (x, y_coordinates[y0], z_coordinates[z0]),
                    (x, y_coordinates[y1], z_coordinates[z0]),
                    (x, y_coordinates[y1], z_coordinates[z1]),
                    (x, y_coordinates[y0], z_coordinates[z1]),
                ]
                append_quad(positions, indices, corners, flip)

    for y_index in range(ny + 1):
        near = occupancy[:, y_index - 1, :] if y_index > 0 else np.zeros((nx, nz), bool)
        far = occupancy[:, y_index, :] if y_index < ny else np.zeros((nx, nz), bool)
        for mask, flip in ((near & ~far, False), (far & ~near, True)):
            for x0, x1, z0, z1 in greedy_rectangles(mask):
                y = y_coordinates[y_index]
                corners = [
                    (x_coordinates[x0], y, z_coordinates[z0]),
                    (x_coordinates[x0], y, z_coordinates[z1]),
                    (x_coordinates[x1], y, z_coordinates[z1]),
                    (x_coordinates[x1], y, z_coordinates[z0]),
                ]
                append_quad(positions, indices, corners, flip)

    for z_index in range(nz + 1):
        below = occupancy[:, :, z_index - 1] if z_index > 0 else np.zeros((nx, ny), bool)
        above = occupancy[:, :, z_index] if z_index < nz else np.zeros((nx, ny), bool)
        for mask, flip in ((below & ~above, False), (above & ~below, True)):
            for x0, x1, y0, y1 in greedy_rectangles(mask):
                z = z_coordinates[z_index]
                corners = [
                    (x_coordinates[x0], y_coordinates[y0], z),
                    (x_coordinates[x1], y_coordinates[y0], z),
                    (x_coordinates[x1], y_coordinates[y1], z),
                    (x_coordinates[x0], y_coordinates[y1], z),
                ]
                append_quad(positions, indices, corners, flip)
    welded_positions: list[float] = []
    welded_indices: list[int] = []
    vertex_lookup: dict[tuple[float, float, float], int] = {}
    for old_index in indices:
        offset = old_index * 3
        key = tuple(positions[offset : offset + 3])
        new_index = vertex_lookup.get(key)
        if new_index is None:
            new_index = len(welded_positions) // 3
            vertex_lookup[key] = new_index
            welded_positions.extend(key)
        welded_indices.append(new_index)
    return {
        "positions": welded_positions,
        "indices": welded_indices,
        "vertexCount": len(welded_positions) // 3,
        "triangleCount": len(welded_indices) // 3,
        "generator": "deterministic-greedy-welded-voxel-surface-v1",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("output")
    arguments = parser.parse_args()
    plan_path = Path(arguments.plan).resolve()
    plan = load_json(plan_path)
    skill_root = Path(__file__).resolve().parents[1]
    plan_schema = json.loads((skill_root / "schemas/carving-plan.schema.json").read_text())
    jsonschema.Draft202012Validator(plan_schema).validate(plan)
    loaded = load_evidence(plan_path, plan)
    if plan["primaryViewId"] not in {evidence["viewId"] for _, evidence, _ in loaded}:
        raise SystemExit("primaryViewId not present in evidence")
    axes = build_axes(plan, loaded)
    shape = tuple(len(axes[axis]) - 1 for axis in AXES)
    plan_component_ids = {component["componentId"] for component in plan["components"]}

    state_components = []
    for component in plan["components"]:
        component_id = component["componentId"]
        occupancy = np.ones(shape, dtype=bool)
        constrained_views: list[str] = []
        primary_constrained = False
        for reference, evidence, _ in loaded:
            if not reference.get("useForCarving", True) or evidence["viewType"] != "orthographic":
                continue
            evidence_components = component_index(evidence)
            evidence_component = evidence_components.get(component_id)
            if evidence_component is None:
                use_assembly_primary = (
                    evidence["viewId"] == plan["primaryViewId"]
                    and component.get("primaryMaskRole") == "assembly-silhouette"
                )
                if reference.get("fallbackToProductMask", False) or use_assembly_primary:
                    mask = rle_to_mask(evidence["productMask"])
                else:
                    continue
            else:
                mask = rle_to_mask(evidence_component.get("carvingMask", evidence_component["visibleMask"]))
            occupancy &= mask_prism(mask, evidence["registration"], axes)
            constrained_views.append(evidence["viewId"])
            if evidence["viewId"] == plan["primaryViewId"]:
                primary_constrained = True
        if not primary_constrained:
            raise SystemExit(f"component {component_id} has no primary-view region")
        apply_axis_bounds(occupancy, component, axes)
        count = int(occupancy.sum())
        if count == 0:
            raise SystemExit(f"component {component_id} visual hull is empty")
        state_components.append(
            {
                "componentId": component_id,
                "label": component["label"],
                "voxelRuns": voxel_runs(occupancy),
                "voxelCount": count,
                "mesh": mesh_from_voxels(occupancy, axes),
                "material": component["material"],
                "inferenceFlags": component["inferenceFlags"],
                "constrainedViews": constrained_views,
            }
        )

    evidence_refs = [
        {
            "viewId": evidence["viewId"],
            "path": reference["path"],
            "canonicalSha256": evidence["canonicalSha256"],
        }
        for reference, evidence, _ in loaded
    ]
    any_inferred = any(component["inferenceFlags"] for component in plan["components"])
    state = {
        "schema": "interior.product-visual-hull-state.v1",
        "planId": plan["planId"],
        "planSha256": canonical_sha256(plan),
        "primaryViewId": plan["primaryViewId"],
        "axes": axes,
        "axisOrder": list(AXES),
        "axisMeaning": {"x": "width", "y": "depth", "z": "height"},
        "evidence": evidence_refs,
        "components": state_components,
        "status": "provisional" if any_inferred else "candidate",
        "geometryMethod": "primary-mask-extrusion-intersected-with-all-orthographic-mask-prisms-v1",
        "forbiddenAlternateGeometry": False,
        "stateSha256": "",
    }
    state["stateSha256"] = canonical_sha256(state, {"stateSha256"})
    state_schema = json.loads((skill_root / "schemas/visual-hull-state.schema.json").read_text())
    jsonschema.Draft202012Validator(state_schema).validate(state)
    dump_json(arguments.output, state)


if __name__ == "__main__":
    main()
