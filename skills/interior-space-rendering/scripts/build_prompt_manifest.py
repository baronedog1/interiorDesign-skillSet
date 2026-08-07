#!/usr/bin/env python3
"""Build the only allowed image prompt manifest from one v7 render context."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from render_contract import load_json, resolve, sha256_file


def relative(path: Path, root: Path) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context")
    parser.add_argument("scene_map")
    parser.add_argument("out")
    parser.add_argument("--model", required=True)
    parser.add_argument("--parameters-json", default="{}")
    args = parser.parse_args()
    context_path = Path(args.context).resolve()
    scene_path = Path(args.scene_map).resolve()
    out_path = Path(args.out).resolve()
    context = load_json(context_path)
    scene = load_json(scene_path)
    if context.get("schema") != "interior.render-media-context.v7":
        raise ValueError("render context must use v7")
    if scene.get("schema") != "interior.shot-scene-map.v9":
        raise ValueError("scene map must use v9")
    if context.get("sourceSceneMap", {}).get("sha256") != sha256_file(scene_path):
        raise ValueError("render context is not bound to the supplied scene map")
    parameters = json.loads(args.parameters_json)
    if not isinstance(parameters, dict):
        raise ValueError("parameters JSON must be an object")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    inputs = []
    for row in context.get("attachmentManifest", []):
        target = resolve(context_path.parent, row["path"])
        if not target.is_file() or sha256_file(target) != row["sha256"]:
            raise ValueError(f"stale context attachment: {row.get('role')}")
        item = {
            "role": row["role"],
            "path": relative(target, out_path.parent),
            "sha256": row["sha256"],
            "sendToImageModel": row["sendToImageModel"],
        }
        for optional in ("referenceId", "coveredRoomIds", "coveredSlotIds"):
            if optional in row:
                item[optional] = row[optional]
        inputs.append(item)
    inputs.extend(
        [
            {
                "role": "render-media-context",
                "path": relative(context_path, out_path.parent),
                "sha256": sha256_file(context_path),
                "sendToImageModel": True,
            }
        ]
    )
    mode = context["guidanceSelection"]["mode"]
    if mode != "slot-guided":
        raise ValueError("slot-guided is the only image-generation mode")
    priority_order = [
        "shot-scene-map",
        "render-media-context",
        "current-shot-concrete-structure-camera-authority",
    ]
    priority_order.extend([
        "user-product-reference",
        "accepted-space-identity-reference",
        "current-shot-furnished-layout-qa-only",
        "room-semantic-mask-qa-only",
        "entity-semantic-mask-qa-only",
        "model-projection-evidence-qa-only",
    ])
    manifest = {
        "schema": "interior.imagegen-prompt-manifest.v7",
        "renderId": context["renderId"],
        "guidanceMode": context["guidanceSelection"]["mode"],
        "promptCompiler": "closed-world-scene-v2",
        "modeSwitchingPolicy": "forbidden",
        "model": args.model,
        "parameters": parameters,
        "priorityOrder": priority_order,
        "inputs": inputs,
    }
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from validate_prompt_manifest import validate_manifest

    validate_manifest(out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
