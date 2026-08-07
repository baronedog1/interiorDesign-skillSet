#!/usr/bin/env python3
"""Initialize a Blender backend project from one accepted floorplan handoff."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from common import blender_transform, load_handoff, sha256, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--template-options", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    handoff_path = Path(args.handoff).resolve()
    handoff, structure, traces = load_handoff(handoff_path)
    project = Path(args.out).resolve()
    if project.exists() and any(project.iterdir()):
        raise SystemExit(f"project directory must be empty: {project}")
    for name in ("input", "config", "model", "reports", "previews"):
        (project / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(handoff_path, project / "input" / "floorplan-handoff.json")
    options = Path(args.template_options).resolve()
    shutil.copy2(options, project / "config" / "backend-options.json")
    write_json(project / "project.json", {
        "schema": "interior.blender-model-project.v1",
        "backend": "blender",
        "floorplanId": handoff["floorplanId"],
        "handoffPath": str(handoff_path),
        "handoffDigestSha256": handoff["handoffDigestSha256"],
        "backendOptionsSha256": sha256(options),
        "coordinateTransform": blender_transform(structure),
        "acceptedSourceObjectCount": len(traces.get("objects", [])),
        "status": "awaiting-asset-selection",
    })
    print(project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
