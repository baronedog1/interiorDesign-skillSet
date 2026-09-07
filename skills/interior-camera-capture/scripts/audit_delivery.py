#!/usr/bin/env python3
"""Audit the one production camera path and its real pipeline runs."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

METHOD = "source-intent-fixture-facing-frontal-camera-v6"
VERSION = "47.0.1"
DECISION_FUNCTIONS = {
    "select_subject_group", "preferred_optical_axes", "generate_candidates",
    "evaluate_candidate", "evaluate_candidate_with_external_repairs",
    "select_views", "apply_native_html_repairs",
}
BANNED_FILES = {
    "prepare_camera_inputs.py", "render_frozen_camera_plan.py",
    "solve_frontal_camera_seeds.py", "solve_coauthoring_cameras.py",
    "solve_wall_near_native_cameras.py", "camera_positioning.py",
    "camera_hiding.py", "camera_subjects.py", "legacy_camera_solver.py",
    "alternative_camera_solver.py", "compile_camera_candidates.py",
    "calculate_camera_geometry.py", "finalize_camera_selection.py",
    "build_camera_preview_plan.py",
    "build_shot_scene_map.py", "validate_shot_scene_map.py", "view_visibility.py",
}
BANNED_BRANCH_TOKENS = ("fallback", "best-effort", "bounded-oblique", "include_oblique")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def audit_skill(root: Path) -> dict[str, Any]:
    pycache = [str(path.relative_to(root)) for path in root.rglob("*.pyc")]
    banned_files = [str(path.relative_to(root)) for path in root.rglob("*") if path.name in BANNED_FILES]
    decision_owners: list[str] = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if names & DECISION_FUNCTIONS:
            decision_owners.append(str(path.relative_to(root)))
    solver_source = (root / "scripts/unified_camera_solver.py").read_text(encoding="utf-8").lower()
    branch_hits = [token for token in BANNED_BRANCH_TOKENS if token in solver_source]
    generator_source = (root / "scripts/generate_vtk_camera_scene.py").read_text(encoding="utf-8").lower()
    generator_hits = [token for token in ("proxy", "fallback") if token in generator_source]
    return {
        "pycache": pycache,
        "bannedFiles": banned_files,
        "decisionOwners": sorted(decision_owners),
        "solverBranchHits": branch_hits,
        "generatorBranchHits": generator_hits,
        "ok": not pycache and not banned_files
        and sorted(decision_owners) == ["scripts/unified_camera_solver.py"]
        and not branch_hits and not generator_hits,
    }


def audit_run(root: Path) -> dict[str, Any]:
    receipt = read_json(root / "camera-pipeline-receipt.json")
    plan = read_json(root / "plan/camera-plan.json")
    index = read_json(root / "delivery/camera-delivery-index.json")
    shots = plan.get("shots", [])
    records = index.get("records", [])
    record_by_id = {str(item.get("shotId")): item for item in records}
    failures: list[str] = []
    if receipt.get("schema") != "interior.camera-pipeline-receipt.v2" or receipt.get("status") != "complete":
        failures.append("pipeline receipt is not complete")
    if receipt.get("algorithm") != METHOD or receipt.get("productionSolver") != "unified_camera_solver.py":
        failures.append("pipeline algorithm identity mismatch")
    if plan.get("schema") != "interior.algorithmic-camera-plan.v3":
        failures.append("camera plan schema mismatch")
    if plan.get("methodVersion") != METHOD or plan.get("producer", {}).get("version") != VERSION:
        failures.append("camera plan algorithm identity mismatch")
    if index.get("producer", {}).get("version") != VERSION:
        failures.append("delivery version mismatch")
    summary = receipt.get("summary", {})
    if summary.get("requested") != summary.get("delivered") or summary.get("failed") != 0:
        failures.append("pipeline delivery summary is incomplete")
    if any((root / name).exists() for name in ("provisional-plan", "provisional-capture")):
        failures.append("provisional output was not removed")
    checked = 0
    for shot in shots:
        shot_id = str(shot.get("shotId"))
        evidence = shot.get("algorithmEvidence", {})
        if evidence.get("method") != METHOD:
            failures.append(f"{shot_id}: algorithm evidence mismatch")
        if not shot.get("frontalContract", {}).get("strict"):
            failures.append(f"{shot_id}: not strict wall frontal")
        record = record_by_id.get(shot_id)
        if not record or not record.get("ok") or record.get("deliveredScreenshotCount") != 1:
            failures.append(f"{shot_id}: delivery record missing or invalid")
            continue
        image = root / "delivery" / Path(str(record["image"])).name
        facts = root / "delivery" / Path(str(record["json"])).name
        if not image.exists() or not facts.exists():
            failures.append(f"{shot_id}: image/facts missing")
            continue
        if digest(image) != record.get("imageSha256"):
            failures.append(f"{shot_id}: image digest mismatch")
        with Image.open(image) as png:
            png.verify()
        fact_data = read_json(facts)
        if fact_data.get("schema") != "interior.camera-image-facts.v3":
            failures.append(f"{shot_id}: facts schema mismatch")
        checked += 1
    return {
        "path": str(root), "requested": len(shots), "checked": checked,
        "failures": failures,
        "ok": not failures and checked == len(shots) and len(shots) > 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", required=True)
    parser.add_argument("--run", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    skill = audit_skill(Path(args.skill_root))
    runs = [audit_run(Path(value)) for value in args.run]
    result = {
        "schema": "interior.camera-release-audit.v1",
        "method": METHOD, "version": VERSION,
        "skill": skill, "runs": runs,
        "summary": {
            "runCount": len(runs),
            "shotCount": sum(item["checked"] for item in runs),
            "passed": bool(skill["ok"] and all(item["ok"] for item in runs)),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not result["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
