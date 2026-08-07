#!/usr/bin/env python3
"""Validate the v10 skill graph and reject coexistence of retired workflows."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


RETIRED_FILES = {
    "compare_boundary_projection.py",
    "derive_views.py",
    "extract_visible_boundaries.py",
    "merge_boundary_traces.py",
    "reconstruct.py",
    "validate_boundary_trace.py",
    "component-boundary-map.schema.json",
    "observation.schema.json",
    "reconstruction-seed.schema.json",
    "reconstruction-state.schema.json",
    "topology-hypothesis.schema.json",
    "visible-boundary-trace.schema.json",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    arguments = parser.parse_args()
    root = Path(arguments.root).resolve()
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("version") != "10.2.0" or manifest.get("workflowCount") != 1:
        raise SystemExit("manifest must declare v10.2.0 and exactly one workflow")
    listed = set(manifest["files"])
    actual = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if listed != actual:
        raise SystemExit(
            f"manifest file graph mismatch missing={sorted(actual-listed)} stale={sorted(listed-actual)}"
        )
    retired_present = sorted(path.name for path in root.rglob("*") if path.name in RETIRED_FILES)
    if retired_present:
        raise SystemExit(f"retired workflow files coexist with v10: {retired_present}")
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    required = (
        "extrusion(primary mask)",
        "xorPixels = 0",
        "single-view-inferred",
        "没有第二套",
        "white-model",
        "source-color",
    )
    missing_phrases = [phrase for phrase in required if phrase not in skill_text]
    if missing_phrases:
        raise SystemExit(f"SKILL.md missing invariants: {missing_phrases}")
    for path in (root / "schemas").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in (root / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(json.dumps({
        "skill": manifest["skill"],
        "version": manifest["version"],
        "workflowCount": 1,
        "fileCount": len(actual),
        "retiredFiles": [],
        "pass": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
