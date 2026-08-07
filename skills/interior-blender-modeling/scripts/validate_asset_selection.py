#!/usr/bin/env python3
"""Validate the one-to-one Blender asset selection against the frozen handoff."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    CATALOG_SCHEMA,
    SELECTION_SCHEMA,
    load_handoff,
    read_json,
    sha256,
    source_object_index,
    write_json,
)


FORBIDDEN_PLACEMENT_FIELDS = {"position", "rotation", "rotationY", "roomId", "width", "depth", "height", "center", "bbox"}
ALLOWED_LICENSES = {"CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "public-domain"}


REQUIRED_AXIS_ROLE = {
    "sofa": "back",
    "single-bed": "headboard",
    "double-bed": "headboard",
    "dining-chair": "front",
    "accent-chair": "front",
    "office-chair": "front",
    "utility-chair": "front",
    "tv-console": "front",
    "wardrobe": "front",
    "sideboard": "front",
    "dresser": "front",
    "console-table": "front",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--asset-store", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    handoff, _, traces = load_handoff(Path(args.handoff))
    selection_path = Path(args.selection).resolve()
    catalog_path = Path(args.catalog).resolve()
    selection = read_json(selection_path)
    catalog = read_json(catalog_path)
    errors: list[str] = []
    if selection.get("schema") != SELECTION_SCHEMA:
        errors.append(f"selection schema must be {SELECTION_SCHEMA}")
    if catalog.get("schema") != CATALOG_SCHEMA:
        errors.append(f"catalog schema must be {CATALOG_SCHEMA}")
    if selection.get("floorplanId") != handoff.get("floorplanId"):
        errors.append("selection floorplanId differs from handoff")
    if selection.get("handoffDigestSha256") != handoff.get("handoffDigestSha256"):
        errors.append("selection handoff digest differs from handoff")
    if selection.get("catalogSha256") != sha256(catalog_path):
        errors.append("selection catalogSha256 mismatch")
    sources = source_object_index(traces)
    assets = {row.get("assetId"): row for row in catalog.get("assets", [])}
    selected: dict[str, dict] = {}
    semantic_checks: list[dict] = []
    store = Path(args.asset_store).resolve()
    for item in selection.get("items", []):
        source_id = item.get("sourceObjectCandidateId")
        if source_id in selected or source_id not in sources:
            errors.append(f"invalid or duplicate source object: {source_id}")
            continue
        forbidden = sorted(FORBIDDEN_PLACEMENT_FIELDS & set(item))
        if forbidden:
            errors.append(f"{source_id}: selection repeats placement fields: {', '.join(forbidden)}")
        selected[source_id] = item
        source = sources[source_id]
        if item.get("traceId") != source.get("traceId"):
            errors.append(f"{source_id}: traceId mismatch")
        asset = assets.get(item.get("assetId"))
        if not asset:
            errors.append(f"{source_id}: unknown assetId {item.get('assetId')}")
            continue
        if asset.get("reviewStatus") != "accepted":
            errors.append(f"{source_id}: asset semantic review is not accepted")
        functional_class = source.get("functionalClass")
        supported = asset.get("supportedFunctionalClasses") or []
        exact_match = functional_class in supported
        semantic_checks.append({
            "sourceObjectCandidateId": source_id,
            "sourceFunctionalClass": functional_class,
            "assetSupportedFunctionalClasses": supported,
            "compatible": exact_match,
        })
        if source.get("quantity") != 1 or source.get("atomicObject") is not True or not functional_class:
            errors.append(f"{source_id}: source must be one atomic object with an exact functionalClass")
        elif not exact_match:
            errors.append(f"{source_id}: asset does not support exact functional class {functional_class}")
        axis_role = REQUIRED_AXIS_ROLE.get(functional_class)
        if axis_role and asset.get("directionalAxes", {}).get(axis_role) not in {"+X", "-X", "+Z", "-Z"}:
            errors.append(f"{source_id}: asset lacks reviewed {axis_role} axis for {functional_class}")
        if asset.get("license") not in ALLOWED_LICENSES:
            errors.append(f"{source_id}: asset license is not automatically allowed")
        path = store / str(asset.get("relativePath", ""))
        if not path.is_file() or sha256(path) != asset.get("sha256"):
            errors.append(f"{source_id}: asset file/hash mismatch")
        if item.get("assetSha256") != asset.get("sha256"):
            errors.append(f"{source_id}: selected assetSha256 mismatch")
        if item.get("axisAdapter") != asset.get("axes"):
            errors.append(f"{source_id}: axisAdapter differs from catalog")
        if item.get("scaleMode") != "uniform-fit":
            errors.append(f"{source_id}: scaleMode must be uniform-fit")
    missing = sorted(set(sources) - set(selected))
    extra = sorted(set(selected) - set(sources))
    if missing:
        errors.append("missing source objects: " + ", ".join(missing))
    if extra:
        errors.append("extra source objects: " + ", ".join(extra))
    report = {
        "schema": "interior.blender-asset-selection-validation.v1",
        "accepted": not errors,
        "floorplanId": handoff.get("floorplanId"),
        "sourceObjectCount": len(sources),
        "selectedCount": len(selected),
        "semanticChecks": semantic_checks,
        "errors": errors,
    }
    write_json(Path(args.report).resolve(), report)
    if errors:
        raise SystemExit("\n".join(errors))
    print("Blender asset selection accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
