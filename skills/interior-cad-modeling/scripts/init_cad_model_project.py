#!/usr/bin/env python3
"""Initialize an isolated CAD floorplan project."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from common import coordinate_transform, load_handoff, sha256, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--options", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    handoff_path = Path(args.handoff).resolve()
    options = Path(args.options).resolve()
    handoff, structure, traces = load_handoff(handoff_path)
    project = Path(args.out).resolve()
    if project.exists() and any(project.iterdir()):
        raise SystemExit(f"project directory must be empty: {project}")
    for name in ("input", "config", "model", "reports", "previews", "snapshot-jobs"):
        (project / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(handoff_path, project / "input" / "floorplan-handoff.json")
    shutil.copy2(options, project / "config" / "backend-options.json")
    write_json(project / "project.json", {
        "schema": "interior.cad-model-project.v1",
        "backend": "cad-step",
        "floorplanId": handoff["floorplanId"],
        "handoffPath": str(handoff_path),
        "handoffDigestSha256": handoff["handoffDigestSha256"],
        "backendOptionsSha256": sha256(options),
        "coordinateTransform": coordinate_transform(structure),
        "acceptedSourceObjectCount": len(traces.get("objects", [])),
        "status": "awaiting-asset-selection",
    })
    print(project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
