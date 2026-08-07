#!/usr/bin/env python3
"""Compile a dependency-aware ImageGen batch plan from render-plan.v11."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from render_contract import load_json, sha256_file, validate_space_reference_plan
from validate_imagegen_request import validate_request


def relative(path: Path, root: Path) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render_plan")
    parser.add_argument("out")
    parser.add_argument(
        "--request",
        action="append",
        default=[],
        metavar="RENDER_ID=PATH",
        help="bind one ready render output to its validated request v4",
    )
    parser.add_argument("--max-concurrency", type=int, default=5)
    args = parser.parse_args()
    plan_path = Path(args.render_plan).resolve()
    out_path = Path(args.out).resolve()
    plan = load_json(plan_path)
    if plan.get("schema") != "interior.model-image-render-plan.v11":
        raise ValueError("render plan must use v11")
    if not 1 <= args.max_concurrency <= 5:
        raise ValueError("ImageGen concurrency must be between 1 and 5")

    scene_maps = {}
    for shot in plan.get("selectedShots", []):
        scene_path = (plan_path.parent / shot["sourceSceneMap"]).resolve()
        if not scene_path.is_file() or sha256_file(scene_path) != shot["sourceSceneMapSha256"]:
            raise ValueError(f"stale scene map: {shot['shotId']}")
        scene_maps[shot["shotId"]] = load_json(scene_path)
    reference = validate_space_reference_plan(plan, scene_maps)
    reference_by_shot = {row["shotId"]: row for row in reference["shots"]}
    output_by_render = {row["renderId"]: row for row in plan.get("outputs", [])}
    expected_render_ids = {
        row["renderId"] for row in plan.get("outputs", []) if row.get("status") != "accepted"
    }
    request_by_render = {}
    for value in args.request:
        if "=" not in value:
            raise ValueError("--request must use RENDER_ID=PATH")
        declared_render_id, path_value = value.split("=", 1)
        request_path = Path(path_value).resolve()
        request = validate_request(request_path)
        render_id = request["renderId"]
        if declared_render_id != render_id:
            raise ValueError(f"request renderId differs from binding: {declared_render_id}")
        if render_id in request_by_render or render_id not in expected_render_ids:
            raise ValueError(f"unexpected or duplicate request: {render_id}")
        request_by_render[render_id] = request_path

    jobs = []
    render_id_by_pair = {
        (row["shotId"], row["styleId"]): row["renderId"]
        for row in plan.get("outputs", [])
    }
    for render_id in sorted(expected_render_ids):
        output = output_by_render[render_id]
        dependencies = [
            render_id_by_pair[(dependency_shot, output["styleId"])]
            for dependency_shot in reference_by_shot[output["shotId"]]["dependsOnAcceptedShotIds"]
        ]
        request_path = request_by_render.get(render_id)
        if request_path is None and not dependencies:
            raise ValueError(f"frontal master request must be built before scheduling: {render_id}")
        jobs.append({
            "jobId": render_id,
            "requestPath": relative(request_path, out_path.parent) if request_path else None,
            "requestSha256": sha256_file(request_path) if request_path else None,
            "dependencies": dependencies,
            "outputFile": output["outputImage"],
            "maxAttempts": plan["renderExecutionPolicy"]["maximumImagegenCandidatesPerFrontalMaster"],
        })

    batches = []
    for index, shot_batch in enumerate(reference["executionBatches"]):
        job_ids = [
            render_id_by_pair[(shot_id, style_id)]
            for shot_id in shot_batch
            for style_id in plan["requestedStyles"]
            if render_id_by_pair[(shot_id, style_id)] in expected_render_ids
        ]
        if job_ids:
            batches.append({"batchId": f"render-batch-{index + 1}", "jobIds": job_ids})
    result = {
        "schema": "imagegen.batch-plan.v1",
        "planId": f"{plan['floorplanId']}-imagegen",
        "sourceSkill": "interior-space-rendering",
        "sourcePlan": {
            "path": relative(plan_path, out_path.parent),
            "sha256": sha256_file(plan_path),
        },
        "maxConcurrency": args.max_concurrency,
        "batches": batches,
        "jobs": jobs,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "jobs": len(jobs), "batches": len(batches), "out": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
