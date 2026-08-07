#!/usr/bin/env python3
"""Bind validated CAD object artifacts into the sole delivery package."""

from __future__ import annotations

import argparse
import ast
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
    project_root_string,
    resolve_in,
    sha256_file,
    validate_schema,
    write_json,
)
from validate_source_inventory import validate_inventory


def require_artifact_hash(root: Path, record: dict[str, Any], label: str) -> None:
    path = resolve_in(root, record["path"])
    if sha256_file(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
        raise ContractError(f"{label} artifact binding changed: {record['path']}")


def build_package(job_path: Path, output_path: Path) -> dict[str, Any]:
    job = load_json(job_path)
    if job.get("schema") != "interior.cad-object-package-job.v1":
        raise ContractError("Package job schema must be interior.cad-object-package-job.v1")
    project_root = project_root_from_document(job_path, str(job.get("projectRoot", ".")))
    output_path = ensure_within(project_root, output_path)
    object_id = job.get("objectId")
    if not isinstance(object_id, str) or not object_id:
        raise ContractError("Package job requires objectId")

    inventory_path = resolve_in(project_root, job.get("sourceInventory", ""))
    inventory = validate_inventory(inventory_path)
    if inventory["objectId"] != object_id:
        raise ContractError("Source inventory objectId mismatch")
    inventory_artifact = artifact_record(project_root, inventory_path)

    evidence_paths_raw = job.get("viewEvidence")
    if not isinstance(evidence_paths_raw, list) or not evidence_paths_raw:
        raise ContractError("Package job requires at least one viewEvidence path")
    evidence_artifacts: list[dict[str, Any]] = []
    for raw in evidence_paths_raw:
        path = resolve_in(project_root, raw)
        value = load_json(path)
        validate_schema(value, "view-evidence.schema.json")
        if value["objectId"] != object_id or not value["overallPassed"]:
            raise ContractError(f"View evidence is not passed for this object: {path}")
        if object_hash(value, "evidenceHash") != value["evidenceHash"]:
            raise ContractError(f"View evidence canonical hash mismatch: {path}")
        if value["sourceInventory"]["sha256"] != inventory_artifact["sha256"]:
            raise ContractError(f"View evidence source inventory binding mismatch: {path}")
        evidence_artifacts.append(artifact_record(project_root, path))

    plan_path = resolve_in(project_root, job.get("plan", ""))
    plan = load_json(plan_path)
    validate_schema(plan, "cad-object-plan.schema.json")
    if plan["objectId"] != object_id or object_hash(plan, "planHash") != plan["planHash"]:
        raise ContractError("CAD object plan identity or canonical hash mismatch")
    if plan["sourceInventory"]["sha256"] != inventory_artifact["sha256"]:
        raise ContractError("CAD plan source inventory binding mismatch")
    expected_evidence_hashes = {artifact["sha256"] for artifact in evidence_artifacts}
    plan_evidence_hashes = {binding["sha256"] for binding in plan["viewEvidence"]}
    if expected_evidence_hashes != plan_evidence_hashes:
        raise ContractError("CAD plan view evidence bindings are incomplete or stale")
    plan_artifact = artifact_record(project_root, plan_path)

    generator_path = resolve_in(project_root, job.get("generator", ""))
    if generator_path.suffix != ".py":
        raise ContractError("Generator must be a Python file")
    try:
        ast.parse(generator_path.read_text(encoding="utf-8"), filename=str(generator_path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise ContractError(f"Generator is not valid audited Python: {exc}") from exc
    generator_artifact = artifact_record(project_root, generator_path)

    step_path = resolve_in(project_root, job.get("step", ""))
    if step_path.suffix.lower() not in {".step", ".stp"}:
        raise ContractError("Primary geometry must be STEP/STP")
    step_artifact = artifact_record(project_root, step_path)

    validation_path = resolve_in(project_root, job.get("validation", ""))
    validation = load_json(validation_path)
    validate_schema(validation, "cad-object-validation.schema.json")
    if validation["objectId"] != object_id:
        raise ContractError("Validation objectId mismatch")
    bindings = {
        "sourceInventorySha256": inventory_artifact["sha256"],
        "planSha256": plan_artifact["sha256"],
        "generatorSha256": generator_artifact["sha256"],
        "stepSha256": step_artifact["sha256"],
    }
    for field, expected in bindings.items():
        if validation[field] != expected:
            raise ContractError(f"Validation {field} binding mismatch")
    if validation["overallStatus"] != "passed" or not all(validation["gates"].values()):
        raise ContractError("Validation has failed or incomplete hard gates")
    for index, record in enumerate(validation["projectionReports"]):
        require_artifact_hash(project_root, record, f"projectionReports[{index}]")
    for index, record in enumerate(validation["snapshots"]):
        require_artifact_hash(project_root, record, f"snapshots[{index}]")
        if not record["reviewed"]:
            raise ContractError(f"Snapshot has not been reviewed: {record['path']}")
    validation_artifact = artifact_record(project_root, validation_path)

    timing_path = resolve_in(project_root, job.get("timing", ""))
    timing = load_json(timing_path)
    validate_schema(timing, "stage-timing.schema.json")
    if object_hash(timing, "timingHash") != timing["timingHash"]:
        raise ContractError("Stage timing canonical hash mismatch")
    if timing["totalDurationMs"] != sum(stage["durationMs"] for stage in timing["stages"]):
        raise ContractError("Stage timing is not additive")
    timing_artifact = artifact_record(project_root, timing_path)

    secondary_raw = job.get("secondaryArtifacts", [])
    if not isinstance(secondary_raw, list):
        raise ContractError("secondaryArtifacts must be an array")
    secondary = [artifact_record(project_root, resolve_in(project_root, raw)) for raw in secondary_raw]

    unresolved = [item for item in plan["assumptions"] if item["status"] == "unresolved"]
    unresolved.extend(
        {
            "field": item["parameterId"],
            "value": item["value"],
            "status": "unresolved",
            "reason": "parameter provenance is unresolved",
            "impact": "see CAD plan",
            "resolution": "provide source evidence or user confirmation",
        }
        for item in plan["parameterFacts"]
        if item["provenance"] == "unresolved"
    )
    status = "accepted" if inventory["strictEligible"] and not unresolved else "provisional"
    if status == "provisional" and not bool(job.get("allowProvisional", False)):
        raise ContractError("Package is provisional; set allowProvisional=true only for an explicit limited delivery")
    limitations = list(validation["limitations"])
    if inventory["inputGrade"] != "A":
        limitations.append(f"Input evidence grade is {inventory['inputGrade']}; unobserved geometry is not a strict source fact.")
    package: dict[str, Any] = {
        "schema": "interior.cad-object-package.v1",
        "objectId": object_id,
        "status": status,
        "inputGrade": inventory["inputGrade"],
        "projectRoot": project_root_string(output_path, project_root),
        "sourceInventory": inventory_artifact,
        "viewEvidence": evidence_artifacts,
        "plan": plan_artifact,
        "generator": generator_artifact,
        "step": step_artifact,
        "secondaryArtifacts": secondary,
        "validation": validation_artifact,
        "timing": timing_artifact,
        "unresolvedAssumptions": unresolved,
        "limitations": limitations,
        "packageHash": "",
    }
    package["packageHash"] = object_hash(package, "packageHash")
    validate_schema(package, "cad-object-package.schema.json")
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        package = build_package(args.job.resolve(), args.output.resolve())
        write_json(args.output.resolve(), package)
        print(f"CAD object package passed: status={package['status']}")
        return 0
    except ContractError as exc:
        print(f"CAD object package failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
