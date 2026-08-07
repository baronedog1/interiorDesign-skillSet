#!/usr/bin/env python3
"""Compile bound CAD inspection, projection, snapshot, and viewer evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from common import (
    ContractError,
    artifact_record,
    ensure_within,
    load_json,
    object_hash,
    project_root_from_document,
    resolve_in,
    sha256_file,
    validate_schema,
    write_json,
)
from validate_source_inventory import validate_inventory


def checks_passed(checks: list[dict[str, Any]]) -> bool:
    return all(check.get("passed") is True for check in checks)


def build_validation(job_path: Path, output_path: Path) -> dict[str, Any]:
    job = load_json(job_path)
    if job.get("schema") != "interior.cad-object-validation-job.v1":
        raise ContractError("Validation job schema must be interior.cad-object-validation-job.v1")
    project_root = project_root_from_document(job_path, str(job.get("projectRoot", ".")))
    output_path = ensure_within(project_root, output_path)
    object_id = job.get("objectId")
    if not isinstance(object_id, str) or not object_id:
        raise ContractError("Validation job requires objectId")

    inventory_path = resolve_in(project_root, job.get("sourceInventory", ""))
    inventory = validate_inventory(inventory_path)
    inventory_artifact = artifact_record(project_root, inventory_path)
    source_gate = inventory["objectId"] == object_id

    evidence_gate = True
    evidence_paths = job.get("viewEvidence")
    if not isinstance(evidence_paths, list) or not evidence_paths:
        raise ContractError("Validation job requires viewEvidence")
    for raw in evidence_paths:
        evidence = load_json(resolve_in(project_root, raw))
        validate_schema(evidence, "view-evidence.schema.json")
        evidence_gate = evidence_gate and evidence["objectId"] == object_id and evidence["overallPassed"]
        evidence_gate = evidence_gate and evidence["sourceInventory"]["sha256"] == inventory_artifact["sha256"]

    plan_path = resolve_in(project_root, job.get("plan", ""))
    plan = load_json(plan_path)
    validate_schema(plan, "cad-object-plan.schema.json")
    if plan["objectId"] != object_id or object_hash(plan, "planHash") != plan["planHash"]:
        raise ContractError("Validation plan identity or canonical hash mismatch")
    plan_artifact = artifact_record(project_root, plan_path)

    coordinate_path = resolve_in(project_root, job.get("coordinateReport", ""))
    coordinate = load_json(coordinate_path)
    coordinate_gate = (
        coordinate.get("schema") == "interior.cad-object-coordinate-report.v1"
        and coordinate.get("objectId") == object_id
        and coordinate.get("planHash") == plan["planHash"]
        and coordinate.get("overallPassed") is True
    )
    coordinate_artifact = artifact_record(project_root, coordinate_path)

    generator_path = resolve_in(project_root, job.get("generator", ""))
    generator_artifact = artifact_record(project_root, generator_path)
    step_path = resolve_in(project_root, job.get("step", ""))
    if step_path.suffix.lower() not in {".step", ".stp"}:
        raise ContractError("Validation primary geometry must be STEP/STP")
    step_artifact = artifact_record(project_root, step_path)

    inspection = job.get("inspection")
    if not isinstance(inspection, dict):
        raise ContractError("Validation job requires inspection")
    commands = inspection.get("commands")
    if not isinstance(commands, list) or not commands or any(not isinstance(command, str) or not command for command in commands):
        raise ContractError("Inspection commands must be a non-empty array")
    facts_paths = inspection.get("factsArtifacts")
    if not isinstance(facts_paths, list) or not facts_paths:
        raise ContractError("Inspection requires raw facts artifacts")
    facts_artifacts = [artifact_record(project_root, resolve_in(project_root, path)) for path in facts_paths]
    solid_count = int(inspection.get("solidCount", 0))
    valid_solid_count = int(inspection.get("validSolidCount", 0))
    dimension_checks = inspection.get("dimensionChecks")
    label_checks = inspection.get("componentLabelChecks")
    relationship_checks = inspection.get("relationshipChecks", [])
    if not isinstance(dimension_checks, list) or not dimension_checks:
        raise ContractError("Inspection requires dimensionChecks")
    if not isinstance(label_checks, list) or not label_checks:
        raise ContractError("Inspection requires componentLabelChecks")
    if not isinstance(relationship_checks, list):
        raise ContractError("relationshipChecks must be an array")
    expected_components = {component["componentId"] for component in plan["components"]}
    checked_components = {check.get("componentId") for check in label_checks if check.get("passed") is True}
    label_gate = checks_passed(label_checks) and checked_components == expected_components
    expected_relationships = {item["relationshipId"] for item in plan["relationships"]}
    checked_relationships = {check.get("relationshipId") for check in relationship_checks if check.get("passed") is True}
    relationship_gate = checks_passed(relationship_checks) and checked_relationships == expected_relationships

    projection_paths = job.get("projectionReports")
    if not isinstance(projection_paths, list) or not projection_paths:
        raise ContractError("Validation requires projection reports")
    projection_artifacts: list[dict[str, Any]] = []
    projection_gate = True
    projected_views: set[str] = set()
    for raw in projection_paths:
        path = resolve_in(project_root, raw)
        report = load_json(path)
        if report.get("schema") != "interior.cad-object-projection-report.v1":
            raise ContractError(f"Unexpected projection report schema: {path}")
        projection_gate = projection_gate and report.get("overallPassed") is True
        projection_gate = projection_gate and report.get("step", {}).get("sha256") == step_artifact["sha256"]
        for target in report.get("targets", []):
            for field in ("evidenceMask", "actualMask", "overlay"):
                record = target.get(field, {})
                artifact_path = resolve_in(project_root, record.get("path", ""))
                if (
                    sha256_file(artifact_path) != record.get("sha256")
                    or artifact_path.stat().st_size != record.get("bytes")
                ):
                    raise ContractError(f"Projection {field} binding changed: {artifact_path}")
        projected_views.update(
            target.get("viewId")
            for target in report.get("targets", [])
            if target.get("required") and target.get("passed")
        )
        projection_artifacts.append(artifact_record(project_root, path))
    required_views = {target["viewId"] for target in plan["projectionTargets"] if target["required"]}
    projection_gate = projection_gate and required_views.issubset(projected_views)

    raw_snapshots = job.get("snapshots")
    if not isinstance(raw_snapshots, list) or not raw_snapshots:
        raise ContractError("Validation requires at least one reviewed snapshot")
    snapshots: list[dict[str, Any]] = []
    visual_gate = True
    for raw in raw_snapshots:
        path = resolve_in(project_root, raw.get("path", ""))
        record = artifact_record(project_root, path)
        reviewed = raw.get("reviewed") is True
        note = str(raw.get("reviewNote", ""))
        visual_gate = visual_gate and reviewed and bool(note)
        snapshots.append({**record, "reviewed": reviewed, "reviewNote": note})

    viewer = job.get("viewerHandoff")
    if not isinstance(viewer, dict) or viewer.get("status") not in {"passed", "unavailable"}:
        raise ContractError("viewerHandoff must record passed or unavailable")
    if viewer["status"] == "passed" and not viewer.get("url"):
        raise ContractError("Passed viewer handoff requires url")
    if viewer["status"] == "unavailable" and not viewer.get("reason"):
        raise ContractError("Unavailable viewer handoff requires reason")
    normalized_viewer = {
        "status": viewer["status"],
        "url": viewer.get("url"),
        "reason": str(viewer.get("reason", "")),
    }

    gates = {
        "sourceInventory": source_gate,
        "viewEvidence": evidence_gate,
        "coordinateContract": coordinate_gate,
        "stepGenerated": step_artifact["bytes"] > 0,
        "positiveSolids": solid_count > 0 and valid_solid_count == solid_count,
        "overallDimensions": checks_passed(dimension_checks),
        "componentLabels": label_gate,
        "assemblyRelationships": relationship_gate,
        "projection": projection_gate,
        "visualReview": visual_gate,
    }
    overall = all(gates.values())
    report: dict[str, Any] = {
        "schema": "interior.cad-object-validation.v1",
        "objectId": object_id,
        "sourceInventorySha256": inventory_artifact["sha256"],
        "planSha256": plan_artifact["sha256"],
        "generatorSha256": generator_artifact["sha256"],
        "stepSha256": step_artifact["sha256"],
        "coordinateReport": coordinate_artifact,
        "gates": gates,
        "inspection": {
            "commands": commands,
            "factsArtifacts": facts_artifacts,
            "factsSummary": str(inspection.get("factsSummary", "")),
            "solidCount": solid_count,
            "validSolidCount": valid_solid_count,
            "dimensionChecks": dimension_checks,
            "componentLabelChecks": label_checks,
            "relationshipChecks": relationship_checks,
        },
        "projectionReports": projection_artifacts,
        "snapshots": snapshots,
        "viewerHandoff": normalized_viewer,
        "limitations": [str(item) for item in job.get("limitations", [])],
        "overallStatus": "passed" if overall else "failed",
    }
    validate_schema(report, "cad-object-validation.schema.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = build_validation(args.job.resolve(), args.output.resolve())
        write_json(args.output.resolve(), report)
        if report["overallStatus"] != "passed":
            print("CAD object validation gates failed", file=sys.stderr)
            return 1
        print("CAD object validation passed")
        return 0
    except ContractError as exc:
        print(f"CAD object validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
