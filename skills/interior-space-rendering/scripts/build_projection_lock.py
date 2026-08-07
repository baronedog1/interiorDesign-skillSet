#!/usr/bin/env python3
"""Compile an immutable projection lock from one accepted shot scene map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from render_contract import derive_projection_lock, load_json, validate_closed_world_view


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene_map")
    parser.add_argument("output")
    args = parser.parse_args()
    scene = load_json(Path(args.scene_map).resolve())
    validate_closed_world_view(scene)
    lock = derive_projection_lock(scene)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "shotId": lock["shotId"], "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
