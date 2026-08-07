#!/usr/bin/env python3
"""Finalize and bind the sole CAD object plan from an auditable draft."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from common import (
    ContractError,
    load_json,
    object_hash,
    resolve_in,
    sha256_file,
    validate_schema,
    write_json,
)


def unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ContractError(f"Duplicate {label}")


def finalize(draft_path: Path, project_root: Path) -> dict[str, Any]:
    plan = load_json(draft_path)
    plan["planHash"] = ""
    if plan.get("schema") != "interior.cad-object-plan.v1":
        raise ContractError("Plan schema must be interior.cad-object-plan.v1")
    inventory_path = resolve_in(project_root, plan["sourceInventory"]["path"])
    if sha256_file(inventory_path) != plan["sourceInventory"]["sha256"]:
        raise ContractError("Plan source inventory binding mismatch")
    inventory = load_json(inventory_path)
    validate_schema(inventory, "source-inventory.schema.json")
    evidence_hashes: set[str] = set()
    evidence_view_ids: set[str] = set()
    evidence_component_ids: set[str] = set()
    for binding in plan["viewEvidence"]:
        evidence_path = resolve_in(project_root, binding["path"])
        actual = sha256_file(evidence_path)
        if actual != binding["sha256"]:
            raise ContractError(f"Plan evidence binding mismatch: {binding['path']}")
        if actual in evidence_hashes:
            raise ContractError("Plan repeats the same view evidence file")
        evidence_hashes.add(actual)
        evidence = load_json(evidence_path)
        validate_schema(evidence, "view-evidence.schema.json")
        if not evidence["overallPassed"] or evidence["objectId"] != plan["objectId"]:
            raise ContractError(f"Plan consumes failed or foreign view evidence: {binding['path']}")
        evidence_view_ids.update(view["viewId"] for view in evidence["views"])
        evidence_component_ids.update(
            component["componentId"]
            for view in evidence["views"]
            for component in view["components"]
        )
    component_ids = [component["componentId"] for component in plan["components"]]
    unique(component_ids, "componentId")
    missing_component_evidence = set(component_ids) - evidence_component_ids
    if missing_component_evidence:
        raise ContractError(f"Plan components lack visible-region evidence: {sorted(missing_component_evidence)}")
    unique([item["parameterId"] for item in plan["parameterFacts"]], "parameterId")
    unique([item["relationshipId"] for item in plan["relationships"]], "relationshipId")
    transform_ids = [item["viewId"] for item in plan["viewTransforms"]]
    unique(transform_ids, "view transform")
    transform_set = set(transform_ids)
    supplied_view_ids = {
        source["view"]["viewId"]
        for source in inventory["sources"]
        if source["imageSize"] is not None
        and source["view"]["projection"] in {"orthographic", "perspective"}
    }
    if not supplied_view_ids.issubset(evidence_view_ids):
        raise ContractError(f"Missing view evidence for supplied views: {sorted(supplied_view_ids - evidence_view_ids)}")
    if not supplied_view_ids.issubset(transform_set):
        raise ContractError(f"Missing coordinate transforms for supplied views: {sorted(supplied_view_ids - transform_set)}")
    for orientation in plan["orientationChecks"]:
        if orientation["viewId"] not in transform_set:
            raise ContractError(f"Orientation check references missing transform: {orientation['viewId']}")
    for target in plan["projectionTargets"]:
        if target["viewId"] not in transform_set:
            raise ContractError(f"Projection target references missing transform: {target['viewId']}")
    required_projection_views = {target["viewId"] for target in plan["projectionTargets"] if target["required"]}
    if not supplied_view_ids.issubset(required_projection_views):
        raise ContractError(f"Missing required projection targets for supplied views: {sorted(supplied_view_ids - required_projection_views)}")
    component_set = set(component_ids)
    for relationship in plan["relationships"]:
        unknown = set(relationship["components"]) - component_set
        if unknown:
            raise ContractError(f"Relationship {relationship['relationshipId']} references unknown components: {sorted(unknown)}")
    plan["planHash"] = object_hash(plan, "planHash")
    validate_schema(plan, "cad-object-plan.schema.json")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        root = args.project_root.resolve()
        if not root.is_dir():
            raise ContractError(f"Project root does not exist: {root}")
        plan = finalize(args.draft.resolve(), root)
        write_json(args.output.resolve(), plan)
        print(f"CAD object plan finalized: components={len(plan['components'])}")
        return 0
    except (ContractError, KeyError, TypeError) as exc:
        print(f"CAD object plan failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
