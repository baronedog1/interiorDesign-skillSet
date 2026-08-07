#!/usr/bin/env python3
"""Validate the canonical closed-world image prompt manifest v7."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from render_contract import validate_closed_world_view


SCHEMA = "interior.imagegen-prompt-manifest.v7"
CONTEXT_SCHEMA = "interior.render-media-context.v7"
SCENE_SCHEMA = "interior.shot-scene-map.v9"
PROMPT_COMPILER = "closed-world-scene-v2"
MODES = {"slot-guided"}
STRUCTURE_ROLE = "current-shot-concrete-structure-camera-authority"
FURNISHED_ROLES = {"current-shot-furnished-layout-qa-only"}
MASK_ROLES = {
    "entity-semantic-mask-qa-only",
    "room-semantic-mask-qa-only",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple[str, str]:
    return row.get("role", ""), row.get("referenceId", "")


def validate_manifest(path: Path) -> dict:
    path = path.resolve()
    root = path.parent
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError("prompt manifest must use v7")
    if data.get("promptCompiler") != PROMPT_COMPILER or "finalPrompt" in data:
        raise ValueError("only the deterministic closed-world-scene-v2 compiler is allowed")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data.get("renderId", "")):
        raise ValueError("invalid renderId")
    mode = data.get("guidanceMode")
    if mode not in MODES:
        raise ValueError("invalid guidance mode")
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("prompt manifest has no inputs")
    keys = [key(row) for row in inputs]
    if len(keys) != len(set(keys)):
        raise ValueError("input role/referenceId pairs must be unique")
    for row in inputs:
        target = (root / row.get("path", "")).resolve()
        if not target.is_file() or sha256(target) != row.get("sha256"):
            raise ValueError(f"missing or stale input: {key(row)}")

    rows_by_role: dict[str, list[dict]] = {}
    for row in inputs:
        rows_by_role.setdefault(row["role"], []).append(row)
    singleton_roles = {STRUCTURE_ROLE} | MASK_ROLES | {
        "shot-scene-map",
        "render-media-context",
        "model-projection-evidence-qa-only",
    }
    if any(len(rows_by_role.get(role, [])) != 1 for role in singleton_roles):
        raise ValueError("canonical current-shot inputs are incomplete or duplicated")
    furnished_rows = [row for role in FURNISHED_ROLES for row in rows_by_role.get(role, [])]
    if len(furnished_rows) != 1:
        raise ValueError("manifest requires exactly one mode-specific Q2 evidence row")

    sent = [row for row in inputs if row.get("sendToImageModel") is True]
    sent_roles = {row["role"] for row in sent}
    required_sent = {STRUCTURE_ROLE, "shot-scene-map", "render-media-context"}
    if not required_sent.issubset(sent_roles):
        raise ValueError("selected guidance authorities and scene/context JSON must be submitted")
    forbidden_sent = MASK_ROLES | {"current-shot-furnished-layout-qa-only"}
    if forbidden_sent & sent_roles:
        raise ValueError("slot silhouettes, semantic masks and QA-only Q2 must not be submitted")
    if rows_by_role["model-projection-evidence-qa-only"][0].get("sendToImageModel") is not False:
        raise ValueError("raw projection evidence is QA-only")
    allowed_sent = required_sent | {
        "accepted-space-identity-reference",
        "user-product-reference",
    }
    if sent_roles - allowed_sent:
        raise ValueError("prompt manifest submits an unrecognized source role")

    context_row = rows_by_role["render-media-context"][0]
    scene_row = rows_by_role["shot-scene-map"][0]
    context = json.loads((root / context_row["path"]).read_text(encoding="utf-8"))
    scene = json.loads((root / scene_row["path"]).read_text(encoding="utf-8"))
    if context.get("schema") != CONTEXT_SCHEMA or scene.get("schema") != SCENE_SCHEMA:
        raise ValueError("context or scene schema mismatch")
    validate_closed_world_view(scene)
    visibility_audit = scene.get("assets", {}).get("visibilityAudit", {})
    visibility_audit_path = (
        (root / scene_row["path"]).resolve().parent
        / visibility_audit.get("file", "")
    ).resolve()
    if any((root / row["path"]).resolve() == visibility_audit_path for row in inputs):
        raise ValueError("QA visibility audit must not enter the prompt manifest")
    if context.get("sourceSceneMap", {}).get("sha256") != scene_row["sha256"]:
        raise ValueError("context is not bound to this scene map")
    if context.get("renderId") != data.get("renderId"):
        raise ValueError("renderId differs between context and prompt manifest")
    if context.get("guidanceSelection", {}).get("mode") != mode:
        raise ValueError("guidance mode differs between context and manifest")
    expected_source_roles = [STRUCTURE_ROLE]
    if context["guidanceSelection"].get("sourceImageRoles") != expected_source_roles:
        raise ValueError("context source image roles differ from the selected guidance mode")
    if context.get("closedWorldView") != scene.get("closedWorldView"):
        raise ValueError("context closed-world view differs from scene map")

    expected_references = {
        row["referenceShotId"] for row in context.get("spaceIdentityReferences", [])
    }
    actual_references = {
        row.get("referenceId")
        for row in rows_by_role.get("accepted-space-identity-reference", [])
        if row.get("sendToImageModel") is True
    }
    if actual_references != expected_references or None in actual_references:
        raise ValueError("accepted identity-reference attachments differ from the dependency plan")
    expected_product_references = {
        row["referenceId"] for row in context.get("userProductReferences", [])
    }
    actual_product_references = {
        row.get("referenceId")
        for row in rows_by_role.get("user-product-reference", [])
        if row.get("sendToImageModel") is True
    }
    if actual_product_references != expected_product_references or None in actual_product_references:
        raise ValueError("user product attachments differ from the exact slot bindings")
    expected_slots_by_reference = {
        reference_id: sorted(
            row["slotId"]
            for row in context.get("userProductReferences", [])
            if row["referenceId"] == reference_id
        )
        for reference_id in expected_product_references
    }
    for row in rows_by_role.get("user-product-reference", []):
        if row.get("coveredSlotIds") != expected_slots_by_reference[row["referenceId"]]:
            raise ValueError("user product attachment slot coverage differs from context")
    expected_priority = [
        "shot-scene-map",
        "render-media-context",
        STRUCTURE_ROLE,
    ]
    expected_priority.extend([
        "user-product-reference",
        "accepted-space-identity-reference",
        "current-shot-furnished-layout-qa-only",
        "room-semantic-mask-qa-only",
        "entity-semantic-mask-qa-only",
        "model-projection-evidence-qa-only",
    ])
    if data.get("priorityOrder") != expected_priority:
        raise ValueError("prompt authority order differs from the canonical contract")
    if data.get("modeSwitchingPolicy") != "forbidden":
        raise ValueError("guidance mode switching is forbidden")
    if not data.get("model") or not isinstance(data.get("parameters"), dict):
        raise ValueError("model and structured parameters are required")
    return data


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_prompt_manifest.py prompt-manifest.v7.json")
    data = validate_manifest(Path(sys.argv[1]))
    print(json.dumps({"ok": True, "schema": data["schema"], "renderId": data["renderId"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
