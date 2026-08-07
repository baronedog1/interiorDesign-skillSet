#!/usr/bin/env python3
"""Compile the actual image-generation request with embedded model facts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from render_contract import (
    canonical_sha256,
    compile_closed_world_prompt,
    load_json,
    render_context_facts,
    resolve,
    scene_facts,
    sha256_file,
)


IMAGE_ROLES = {
    "current-shot-concrete-structure-camera-authority",
    "user-product-reference",
    "accepted-space-identity-reference",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt_manifest")
    parser.add_argument("out")
    parser.add_argument("--generation-invocation-id", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.prompt_manifest).resolve()
    out_path = Path(args.out).resolve()
    manifest = load_json(manifest_path)
    if manifest.get("schema") != "interior.imagegen-prompt-manifest.v7":
        raise ValueError("prompt manifest must use v7")
    if manifest.get("promptCompiler") != "closed-world-scene-v2":
        raise ValueError("prompt manifest must select the closed-world compiler")
    if "finalPrompt" in manifest:
        raise ValueError("free-form finalPrompt is forbidden")
    if manifest.get("guidanceMode") != "slot-guided":
        raise ValueError("slot-guided is the only image-generation mode")
    rows = manifest.get("inputs", [])
    context_rows = [row for row in rows if row.get("role") == "render-media-context"]
    scene_rows = [row for row in rows if row.get("role") == "shot-scene-map"]
    context_row = context_rows[0] if len(context_rows) == 1 else None
    scene_row = scene_rows[0] if len(scene_rows) == 1 else None
    if not context_row or not scene_row:
        raise ValueError("prompt manifest requires scene map and render context")
    if context_row.get("sendToImageModel") is not True or scene_row.get("sendToImageModel") is not True:
        raise ValueError("scene map and render context must be compiled into the actual model prompt")
    context_path = resolve(manifest_path.parent, context_row["path"])
    scene_path = resolve(manifest_path.parent, scene_row["path"])
    if sha256_file(context_path) != context_row.get("sha256") or sha256_file(scene_path) != scene_row.get("sha256"):
        raise ValueError("scene map or render context hash mismatch")
    context = load_json(context_path)
    scene_map = load_json(scene_path)
    if context.get("schema") != "interior.render-media-context.v7":
        raise ValueError("render context must use v7")
    if context.get("sourceSceneMap", {}).get("sha256") != sha256_file(scene_path):
        raise ValueError("render context is not bound to the supplied scene map")
    facts = scene_facts(scene_map)
    context_facts = render_context_facts(context)
    if context.get("closedWorldView") != scene_map.get("closedWorldView"):
        raise ValueError("render context closed-world view differs from the scene map")
    prompt = compile_closed_world_prompt(facts, context_facts)
    attachments = []
    attachment_keys = set()
    for row in rows:
        if row.get("sendToImageModel") is not True or row.get("role") not in IMAGE_ROLES:
            continue
        target = resolve(manifest_path.parent, row["path"])
        if not target.is_file() or sha256_file(target) != row.get("sha256"):
            raise ValueError(f"image attachment missing or changed: {row.get('role')}")
        attachment_key = (row["role"], row.get("referenceId", ""))
        if attachment_key in attachment_keys:
            raise ValueError(f"duplicate image attachment identity: {attachment_key}")
        attachment_keys.add(attachment_key)
        item = {
            "role": row["role"],
            "path": os.path.relpath(target, out_path.parent).replace(os.sep, "/"),
            "sha256": row["sha256"],
        }
        for optional in ("referenceId", "coveredRoomIds", "coveredSlotIds"):
            if optional in row:
                item[optional] = row[optional]
        attachments.append(item)
    attachment_roles = {row["role"] for row in attachments}
    required_roles = {"current-shot-concrete-structure-camera-authority"}
    if not required_roles.issubset(attachment_roles):
        raise ValueError("actual request is missing a selected guidance authority")
    request = {
        "schema": "interior.imagegen-request.v4",
        "renderId": manifest["renderId"],
        "generationInvocationId": args.generation_invocation_id,
        "model": manifest["model"],
        "parameters": manifest["parameters"],
        "guidanceMode": manifest["guidanceMode"],
        "promptCompiler": "closed-world-scene-v2",
        "prompt": prompt,
        "promptDigestSha256": __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest(),
        "sceneFactsDigestSha256": canonical_sha256(facts),
        "renderContextFactsDigestSha256": canonical_sha256(context_facts),
        "submittedImageAttachments": attachments,
        "submittedJsonDocuments": [
            {
                "role": "shot-scene-map",
                "path": os.path.relpath(scene_path, out_path.parent).replace(os.sep, "/"),
                "sha256": sha256_file(scene_path),
                "encoding": "canonical-json-prompt-block",
                "factsDigestSha256": canonical_sha256(facts),
            },
            {
                "role": "render-media-context",
                "path": os.path.relpath(context_path, out_path.parent).replace(os.sep, "/"),
                "sha256": sha256_file(context_path),
                "encoding": "canonical-json-prompt-block",
                "factsDigestSha256": canonical_sha256(context_facts),
            },
        ],
        "embeddedDocuments": {
            "sceneMap": {"path": os.path.relpath(scene_path, out_path.parent), "sha256": sha256_file(scene_path)},
            "renderContext": {"path": os.path.relpath(context_path, out_path.parent), "sha256": sha256_file(context_path)},
        },
        "sourcePromptManifest": {
            "path": os.path.relpath(manifest_path, out_path.parent),
            "sha256": sha256_file(manifest_path),
        },
        "requestDigestSha256": None,
    }
    request["requestDigestSha256"] = canonical_sha256(request)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(__import__("json").dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
