#!/usr/bin/env python3
"""Validate CAD asset selection against the frozen floorplan objects."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import CATALOG_SCHEMA, SELECTION_SCHEMA, load_handoff, read_json, sha256, source_objects, write_json


FORBIDDEN_FIELDS = {"position", "rotation", "rotationY", "roomId", "center", "bbox", "width", "depth", "height"}
SAFE_LICENSES = {"CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "public-domain"}


REQUIRED_AXIS_ROLE = {
    "sofa": "back",
    "single-bed": "headboard",
    "double-bed": "headboard",
    "dining-chair": "front",
    "accent-chair": "front",
    "utility-chair": "front",
    "tv-console": "front",
    "wardrobe": "front",
    "sideboard": "front",
    "dresser": "front",
    "vanity": "front",
}


def embedded_conflict(asset: dict) -> bool:
    value = str(asset.get("metadata", {}).get("license", "")).lower()
    return "all rights reserved" in value or "proprietary" in value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--asset-store", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    handoff, _, traces = load_handoff(Path(args.handoff))
    selection_path, catalog_path = Path(args.selection).resolve(), Path(args.catalog).resolve()
    selection, catalog = read_json(selection_path), read_json(catalog_path)
    errors: list[str] = []
    warnings: list[str] = []
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
    usage = selection.get("usageContext")
    if usage not in {"research-only", "commercial", "community-publication"}:
        errors.append("usageContext must be research-only, commercial or community-publication")
    sources = source_objects(traces)
    assets = {row.get("id"): row for row in catalog.get("assets", [])}
    selected: dict[str, dict] = {}
    semantic_checks: list[dict] = []
    store = Path(args.asset_store).resolve()
    redistribution_allowed = True
    for item in selection.get("items", []):
        source_id = item.get("sourceObjectCandidateId")
        if source_id in selected or source_id not in sources:
            errors.append(f"invalid or duplicate source object: {source_id}")
            continue
        selected[source_id] = item
        forbidden = sorted(FORBIDDEN_FIELDS & set(item))
        if forbidden:
            errors.append(f"{source_id}: selection repeats placement fields: {', '.join(forbidden)}")
        source = sources[source_id]
        if item.get("traceId") != source.get("traceId"):
            errors.append(f"{source_id}: traceId mismatch")
        asset = assets.get(item.get("assetId"))
        if not asset:
            errors.append(f"{source_id}: unknown assetId {item.get('assetId')}")
            continue
        functional_class = source.get("functionalClass")
        supported = asset.get("supportedFunctionalClasses") or []
        exact_match = functional_class in supported and asset.get("functionalReviewStatus") == "accepted"
        semantic_checks.append({
            "sourceObjectCandidateId": source_id,
            "sourceFunctionalClass": functional_class,
            "assetSupportedFunctionalClasses": supported,
            "compatible": exact_match,
        })
        if source.get("quantity") != 1 or source.get("atomicObject") is not True or not functional_class:
            errors.append(f"{source_id}: source must be one atomic object with an exact functionalClass")
        elif not exact_match:
            errors.append(f"{source_id}: CAD asset does not support exact functional class {functional_class}")
        axis_role = REQUIRED_AXIS_ROLE.get(functional_class)
        if axis_role and asset.get("directionalAxes", {}).get(axis_role) not in {"+X", "-X", "+Z", "-Z"}:
            errors.append(f"{source_id}: CAD asset lacks reviewed {axis_role} axis for {functional_class}")
        step = asset.get("formats", {}).get("step")
        if item.get("format") != "step" or not isinstance(step, dict):
            errors.append(f"{source_id}: selected asset has no normalized STEP")
            continue
        path = store / str(step.get("path", ""))
        if not path.is_file() or sha256(path) != step.get("sha256"):
            errors.append(f"{source_id}: STEP file/hash mismatch")
        if item.get("assetSha256") != step.get("sha256"):
            errors.append(f"{source_id}: assetSha256 mismatch")
        if item.get("scaleMode") != "uniform-fit":
            errors.append(f"{source_id}: scaleMode must be uniform-fit")
        axes = item.get("axisAdapter")
        if axes not in tuple({"up": "+Z", "front": front} for front in ("-Y", "+Y", "-X", "+X")):
            errors.append(f"{source_id}: axisAdapter is not reviewed")
        conflict = embedded_conflict(asset)
        if conflict:
            redistribution_allowed = False
            if usage != "research-only" or item.get("licenseDecision") != "research-only":
                errors.append(f"{source_id}: embedded license conflict only allows local research gate")
            else:
                warnings.append(f"{source_id}: license conflict; redistribution disabled")
        elif asset.get("license") not in SAFE_LICENSES and "CC-BY-3.0" not in str(asset.get("license")):
            errors.append(f"{source_id}: unsupported asset license")
    if set(selected) != set(sources):
        errors.append("selection must cover every accepted source object exactly once")
    report = {
        "schema": "interior.cad-asset-selection-validation.v1",
        "accepted": not errors,
        "floorplanId": handoff.get("floorplanId"),
        "usageContext": usage,
        "redistributionAllowed": redistribution_allowed,
        "sourceObjectCount": len(sources),
        "selectedCount": len(selected),
        "semanticChecks": semantic_checks,
        "warnings": warnings,
        "errors": errors,
    }
    write_json(Path(args.report).resolve(), report)
    if errors:
        raise SystemExit("\n".join(errors))
    print("CAD asset selection accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
