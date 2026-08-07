#!/usr/bin/env python3
"""Compile camera-plan.v8 into native CAD snapshot jobs and execute them."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess

from common import read_json, sha256, write_json
from cad_semantic_projection import compile_semantic_frame


def canonical_to_cad_mm(point):
    """Convert interior-world-y-up metres to CAD Z-up millimetres."""
    if not isinstance(point, list) or len(point) != 3:
        raise SystemExit("camera coordinates must be 3-number arrays")
    return [1000.0 * float(point[0]), -1000.0 * float(point[2]), 1000.0 * float(point[1])]


def focal_length_to_snapshot_zoom(focal_length_mm: float, width: int, height: int) -> float:
    """Map a 36mm horizontal camera to the CAD viewer's 48-degree base camera."""
    aspect = float(width) / float(height)
    return math.tan(math.radians(24.0)) * aspect * float(focal_length_mm) / 18.0


def result_output_paths(result):
    if isinstance(result, dict) and isinstance(result.get("jobs"), list):
        values = []
        for child in result["jobs"]:
            values.extend(result_output_paths(child))
        return values
    return [row.get("path") for row in result.get("outputs", []) if isinstance(row, dict) and row.get("path")]


def run_snapshot(command, job_path: Path, destination: Path) -> None:
    completed = subprocess.run(
        [*command, "--job", str(job_path), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"CAD snapshot renderer returned non-JSON output: {completed.stdout[-1000:]}") from exc
    paths = result_output_paths(result)
    if len(paths) != 1:
        raise SystemExit(f"CAD snapshot renderer returned {len(paths)} outputs; expected one")
    generated = Path(paths[0]).resolve()
    if not generated.is_file() or generated.stat().st_size < 1024:
        raise SystemExit(f"CAD snapshot renderer did not create a nonblank image: {generated}")
    if generated != destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        generated.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--camera-plan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--renderer-command")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    manifest = read_json(Path(args.manifest).resolve())
    plan = read_json(Path(args.camera_plan).resolve())
    if manifest.get("schema") != "interior.native-model-manifest.v1" or manifest.get("modelBackend") != "cad-step":
        raise SystemExit("manifest must be an accepted CAD native model")
    if manifest.get("validation", {}).get("accepted") is not True:
        raise SystemExit("native CAD model is not accepted")
    if plan.get("schema") != "interior.camera-plan.v8" or plan.get("modelBackend") != "cad-step":
        raise SystemExit("camera plan must be CAD camera-plan.v8")
    if plan.get("coordinateSystem") != "interior-world-y-up.v1":
        raise SystemExit("camera plan must use interior-world-y-up.v1")
    if plan.get("sourceModelSha256") != manifest.get("nativeModel", {}).get("sha256"):
        raise SystemExit("camera plan and STEP hash differ")
    model = Path(manifest["nativeModel"]["path"]).resolve()
    if not model.is_file() or sha256(model) != manifest["nativeModel"]["sha256"]:
        raise SystemExit("native STEP file/hash mismatch")
    entity_index = read_json(Path(manifest["entityIndex"]["path"]).resolve())
    selector_by_id = {
        row["id"]: row["selector"]
        for row in entity_index.get("entities", [])
        if row.get("id") and row.get("selector")
    }
    indexed_entities = [
        row for row in entity_index.get("entities", [])
        if row.get("id") and row.get("selector")
    ]
    component_selectors = [
        row["selector"] for row in indexed_entities
        if row.get("type") == "component"
    ]
    if len(component_selectors) != len([row for row in entity_index.get("entities", []) if row.get("type") == "component"]):
        raise SystemExit("CAD entity index lacks native occurrence selectors for components")
    non_top_level = [
        row["selector"] for row in indexed_entities
        if re.fullmatch(r"#o1\.\d+", row["selector"]) is None
    ]
    if non_top_level:
        raise SystemExit(f"CAD capture requires top-level STEP occurrence selectors: {non_top_level}")
    out = Path(args.out).resolve()
    jobs = out / "jobs"
    images = out / "images"
    jobs.mkdir(parents=True, exist_ok=True)
    images.mkdir(parents=True, exist_ok=True)
    records = []
    projection_records = []
    command_text = args.renderer_command or os.environ.get("INTERIOR_CAD_SNAPSHOT_COMMAND", "")
    if not args.prepare_only and not command_text:
        raise SystemExit("INTERIOR_CAD_SNAPSHOT_COMMAND is required for real native capture")
    command = shlex.split(command_text) if command_text else []
    for shot in plan.get("shots", []):
        native_position = canonical_to_cad_mm(shot["position"])
        native_target = canonical_to_cad_mm(shot["target"])
        outputs = []
        job_paths = []
        width = int(shot.get("imageSize", [1600, 1000])[0])
        height = int(shot.get("imageSize", [1600, 1000])[1])
        for mode in ("slot-guided", "furnished-qa"):
            unknown_hidden = [
                value for value in shot.get("visibility", {}).get("hiddenElementIds", [])
                if value not in selector_by_id
            ]
            if unknown_hidden:
                raise SystemExit(f"camera plan references CAD entities without selectors: {unknown_hidden}")
            hidden_ids = set(shot.get("visibility", {}).get("hiddenElementIds", []))
            if mode == "slot-guided":
                hidden_ids.update(
                    row["id"] for row in indexed_entities
                    if row.get("type") == "component"
                )
            hidden_selectors = sorted(selector_by_id[value] for value in hidden_ids)
            destination = images / f"{shot['shotId']}.{mode}.png"
            camera = {
                "position": native_position,
                "target": native_target,
                "up": [0, 0, 1],
                "zoom": focal_length_to_snapshot_zoom(shot["focalLengthMm"], width, height),
            }
            job = {
                "input": str(model),
                "mode": "view",
                "appearance": "workbench",
                "display": {
                    "projection": "perspective",
                    "mode": "rendered",
                    "edges": {
                        "enabled": False,
                        "color": "#59616b",
                    },
                },
                "outputs": [{"path": str(destination), "width": width, "height": height, "camera": camera}],
                "render": {"padding": 0, "lockFraming": True, "sizeProfile": "assembly"},
            }
            if hidden_selectors:
                job["selection"] = {"hide": hidden_selectors}
            job_path = jobs / f"{shot['shotId']}.{mode}.json"
            write_json(job_path, job)
            job_paths.append(str(job_path))
            if not args.prepare_only:
                run_snapshot(command, job_path, destination)
            outputs.append({
                "mode": mode,
                "path": str(destination),
                "camera": {
                    **camera,
                    "focalLengthMm": shot["focalLengthMm"],
                    "sensorWidthMm": 36,
                    "projection": "perspective",
                    "distortion": 0,
                    "units": "mm",
                },
                "visibility": {
                    "hiddenOccurrenceSelectors": hidden_selectors,
                    "hiddenEntityIds": sorted(hidden_ids),
                    "preserveEntityIds": shot.get("visibility", {}).get("preserveElementIds", []),
                },
                "appearance": "concrete-shell",
                "semanticPasses": "compiled-from-same-step-derived-occurrence-topology-zbuffer",
            })
        semantic_projection = None
        if not args.prepare_only:
            base_hidden = {
                selector_by_id[value]
                for value in shot.get("visibility", {}).get("hiddenElementIds", [])
            }
            semantic_projection = compile_semantic_frame(
                command=command,
                manifest=manifest,
                entity_index=entity_index,
                shot=shot,
                camera=camera,
                model=model,
                slot_guided_image=images / f"{shot['shotId']}.slot-guided.png",
                furnished_qa_image=images / f"{shot['shotId']}.furnished-qa.png",
                out=out,
                base_hidden=base_hidden,
            )
            projection_records.append(semantic_projection)
        records.append({
            "shotId": shot["shotId"],
            "jobs": job_paths,
            "canonicalCamera": {"position": shot["position"], "target": shot["target"]},
            "nativeCamera": {"position": native_position, "target": native_target, "units": "mm"},
            "outputs": outputs,
            "semanticProjection": semantic_projection,
        })
    result = {
        "schema": "interior.native-capture-result.v1",
        "modelBackend": "cad-step",
        "sourceModelSha256": manifest["nativeModel"]["sha256"],
        "coordinateSystem": "interior-world-y-up.v1",
        "preparedOnly": args.prepare_only,
        "accepted": not args.prepare_only,
        "nativeImagesAccepted": not args.prepare_only,
        "projectionEvidenceAccepted": not args.prepare_only and len(projection_records) == len(plan.get("shots", [])),
        "projectionEvidenceStatus": "accepted-same-brep-topology-zbuffer" if not args.prepare_only else "prepare-only",
        "records": records,
    }
    write_json(out / "capture-result.json", result)
    print(out / "capture-result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
