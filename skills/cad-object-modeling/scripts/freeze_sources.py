#!/usr/bin/env python3
"""Freeze source artifacts, dimensions, calibration, and evidence grade."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from PIL import Image

from common import (
    ContractError,
    classify_input,
    object_hash,
    project_root_from_document,
    project_root_string,
    relative_path,
    resolve_in,
    sha256_file,
    validate_schema,
    write_json,
    load_json,
)


def normalized_calibration(raw: dict[str, Any]) -> dict[str, Any]:
    status = raw.get("status", "uncalibrated")
    basis = str(raw.get("basis", ""))
    ppm = raw.get("pixelsPerMillimeter")
    if ppm is None and raw.get("pixelLength") is not None and raw.get("millimeters") is not None:
        millimeters = float(raw["millimeters"])
        if millimeters <= 0:
            raise ContractError("Calibration millimeters must be positive")
        ppm = float(raw["pixelLength"]) / millimeters
    if status == "calibrated":
        if ppm is None or float(ppm) <= 0:
            raise ContractError("Calibrated source requires positive pixelsPerMillimeter")
        ppm = float(ppm)
        if not basis:
            raise ContractError("Calibrated source requires a non-empty basis")
    else:
        ppm = None
        status = "not-applicable" if status == "not-applicable" else "uncalibrated"
    return {"status": status, "pixelsPerMillimeter": ppm, "basis": basis}


def image_size(path: Path, kind: str) -> dict[str, int] | None:
    if kind not in {"image", "drawing"}:
        return None
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception as exc:
        raise ContractError(f"Cannot read raster dimensions from {path}: {exc}") from exc
    if width <= 0 or height <= 0:
        raise ContractError(f"Invalid raster dimensions: {path}")
    return {"width": width, "height": height}


def build_inventory(job_path: Path, output_path: Path) -> dict[str, Any]:
    job = load_json(job_path)
    if job.get("schema") != "interior.cad-object-source-job.v1":
        raise ContractError("Source job schema must be interior.cad-object-source-job.v1")
    object_id = job.get("objectId")
    if not isinstance(object_id, str) or not object_id:
        raise ContractError("objectId is required")
    if job.get("units", "mm") != "mm":
        raise ContractError("CAD object workflow uses millimeters")
    project_root = project_root_from_document(job_path, str(job.get("projectRoot", ".")))
    output_path = ensure_output(project_root, output_path)

    raw_sources = job.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ContractError("sources must be a non-empty array")
    source_ids: set[str] = set()
    view_ids: set[str] = set()
    sources: list[dict[str, Any]] = []
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ContractError("Each source must be an object")
        source_id = raw.get("sourceId")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            raise ContractError(f"Invalid or duplicate sourceId: {source_id!r}")
        source_ids.add(source_id)
        kind = raw.get("kind", "image")
        if kind not in {"image", "drawing", "cad", "document"}:
            raise ContractError(f"Unsupported source kind: {kind}")
        path = resolve_in(project_root, raw.get("path", ""))
        if not path.is_file() or path.stat().st_size <= 0:
            raise ContractError(f"Source file is missing or empty: {path}")
        view = raw.get("view")
        if not isinstance(view, dict):
            raise ContractError(f"Source {source_id} requires view metadata")
        view_id = view.get("viewId")
        if not isinstance(view_id, str) or not view_id:
            raise ContractError(f"Source {source_id} requires viewId")
        if view_id != "not-applicable" and view_id in view_ids:
            raise ContractError(f"Duplicate viewId: {view_id}")
        view_ids.add(view_id)
        normalized_view = {
            "viewId": view_id,
            "projection": view.get("projection", "unknown"),
            "normalAxis": view.get("normalAxis", "unknown"),
            "screenRight": str(view.get("screenRight", "unknown")),
            "screenUp": str(view.get("screenUp", "unknown")),
        }
        sources.append(
            {
                "sourceId": source_id,
                "path": relative_path(project_root, path),
                "kind": kind,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "imageSize": image_size(path, kind),
                "role": raw.get("role", "supporting"),
                "view": normalized_view,
                "calibration": normalized_calibration(raw.get("calibration", {})),
            }
        )

    raw_dimensions = job.get("dimensionFacts", [])
    if not isinstance(raw_dimensions, list):
        raise ContractError("dimensionFacts must be an array")
    dimension_ids: set[str] = set()
    dimensions: list[dict[str, Any]] = []
    for raw in raw_dimensions:
        dimension_id = raw.get("dimensionId")
        if not isinstance(dimension_id, str) or not dimension_id or dimension_id in dimension_ids:
            raise ContractError(f"Invalid or duplicate dimensionId: {dimension_id!r}")
        dimension_ids.add(dimension_id)
        if raw.get("sourceId") not in source_ids:
            raise ContractError(f"Dimension {dimension_id} references unknown sourceId")
        value = float(raw.get("value", 0))
        if value <= 0:
            raise ContractError(f"Dimension {dimension_id} must be positive")
        dimensions.append(
            {
                "dimensionId": dimension_id,
                "axis": raw.get("axis", "other"),
                "value": value,
                "unit": "mm",
                "sourceId": raw["sourceId"],
                "confidence": raw.get("confidence", "estimated"),
                "note": str(raw.get("note", "")),
            }
        )

    grade, strict = classify_input(sources, dimensions)
    inventory: dict[str, Any] = {
        "schema": "interior.cad-object-source-inventory.v1",
        "objectId": object_id,
        "projectRoot": project_root_string(output_path, project_root),
        "units": "mm",
        "sources": sources,
        "dimensionFacts": dimensions,
        "inputGrade": grade,
        "strictEligible": strict,
        "inventoryHash": "",
    }
    inventory["inventoryHash"] = object_hash(inventory, "inventoryHash")
    validate_schema(inventory, "source-inventory.schema.json")
    return inventory


def ensure_output(project_root: Path, output_path: Path) -> Path:
    candidate = output_path if output_path.is_absolute() else Path.cwd() / output_path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ContractError(f"Output must stay inside project root: {candidate}") from exc
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        inventory = build_inventory(args.job.resolve(), output)
        write_json(output, inventory)
        print(f"source inventory passed: grade={inventory['inputGrade']} output={output}")
        return 0
    except ContractError as exc:
        print(f"source inventory failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
