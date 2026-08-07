#!/usr/bin/env python3
"""Create the empty, collection-owned Blender floorplan template."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


COLLECTIONS = ("STRUCTURE", "OPENINGS", "FLOORS", "CEILINGS", "FURNITURE", "LIGHTS", "CAMERAS", "ANNOTATIONS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", required=True)
    parser.add_argument("--out", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    options = json.loads(Path(args.options).read_text(encoding="utf-8"))
    if options.get("schema") != "interior.blender-backend-options.v1":
        raise ValueError("invalid Blender backend options")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = bpy.context.scene.collection
    for name in COLLECTIONS:
        root.children.link(bpy.data.collections.new(name))
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.length_unit = "METERS"
    bpy.context.scene["interiorTemplateSchema"] = "interior.blender-floorplan-template.v1"
    bpy.context.scene["interiorBackendOptions"] = json.dumps(options, ensure_ascii=False)
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
