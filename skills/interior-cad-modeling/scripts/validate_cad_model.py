#!/usr/bin/env python3
"""Validate an accepted STEP and its sidecar entity index."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import read_json, sha256, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source = read_json(Path(args.report).resolve())
    errors = []
    if source.get("schema") != "interior.cad-build-report.v1" or source.get("accepted") is not True:
        errors.append("CAD build report is not accepted")
    step = Path(source.get("nativeModelPath", "")).resolve()
    if not step.is_file() or sha256(step) != source.get("nativeModelSha256"):
        errors.append("STEP file/hash mismatch")
    entity_path = Path(source.get("entityIndexPath", "")).resolve()
    if not entity_path.is_file() or sha256(entity_path) != source.get("entityIndexSha256"):
        errors.append("entity index file/hash mismatch")
    else:
        entities = read_json(entity_path).get("entities", [])
        components = [row for row in entities if row.get("type") == "component"]
        if len(components) != source.get("counts", {}).get("components"):
            errors.append("component count differs from entity index")
        source_ids = [row.get("sourceObjectCandidateId") for row in components]
        if len(source_ids) != len(set(source_ids)):
            errors.append("component sourceObjectCandidateId is not one-to-one")
        selector_rows = [row for row in entities if row.get("type") != "connection"]
        selectors = [row.get("selector") for row in selector_rows]
        if any(not isinstance(value, str) or not value.startswith("#o1.") for value in selectors):
            errors.append("renderable CAD entities require native STEP occurrence selectors")
        if len(selectors) != len(set(selectors)):
            errors.append("CAD occurrence selectors are not unique")
        for row in selector_rows:
            world = row.get("worldBoundsMeters", {})
            if not (
                isinstance(world.get("min"), list) and len(world["min"]) == 3
                and isinstance(world.get("max"), list) and len(world["max"]) == 3
                and all(float(a) <= float(b) for a, b in zip(world["min"], world["max"]))
            ):
                errors.append(f"{row.get('id')}: canonical world bounds are missing or invalid")
    if source.get("primitiveFurnitureFallbackCount") != 0:
        errors.append("primitive furniture fallback is present")
    derived_formats = set()
    for row in source.get("derivedModels", []):
        derived_path = Path(row.get("path", "")).resolve()
        derived_format = row.get("format")
        derived_formats.add(derived_format)
        if not derived_path.is_file() or sha256(derived_path) != row.get("sha256"):
            errors.append(f"derived {derived_format} file/hash mismatch")
            continue
        with derived_path.open("rb") as stream:
            header = stream.read(4)
        if derived_format == "glb" and header != b"glTF":
            errors.append("derived GLB has an invalid binary glTF header")
        if derived_format == "3mf" and header[:2] != b"PK":
            errors.append("derived 3MF has an invalid ZIP container header")
    if "glb" not in derived_formats:
        errors.append("accepted CAD delivery is missing the same-B-rep derived GLB")
    if not errors:
        try:
            from build123d import import_step

            shape = import_step(step)
            validity = shape.is_valid() if callable(shape.is_valid) else bool(shape.is_valid)
            if not validity:
                errors.append("OpenCascade reports invalid B-rep")
            if not shape.solids():
                errors.append("reopened STEP contains no solids")
        except Exception as exc:
            errors.append(f"STEP reopen failed: {exc}")
    result = {"schema": "interior.cad-model-validation.v1", "accepted": not errors, "nativeModelSha256": source.get("nativeModelSha256"), "errors": errors}
    write_json(Path(args.out).resolve(), result)
    if errors:
        raise SystemExit("\n".join(errors))
    print("CAD model accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
