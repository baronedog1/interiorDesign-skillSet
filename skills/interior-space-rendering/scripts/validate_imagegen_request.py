#!/usr/bin/env python3
"""Verify that the submitted request embeds exact scene facts and selected images."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from render_contract import (
    canonical_sha256,
    compile_closed_world_prompt,
    load_json,
    render_context_facts,
    resolve,
    scene_facts,
    sha256_file,
    verify_document_digest,
)


def validate_request(path: Path) -> dict:
    path = path.resolve()
    data = load_json(path)
    if data.get("schema") != "interior.imagegen-request.v4":
        raise ValueError("request schema mismatch")
    if data.get("promptCompiler") != "closed-world-scene-v2":
        raise ValueError("request did not use the closed-world prompt compiler")
    if data.get("guidanceMode") != "slot-guided":
        raise ValueError("slot-guided is the only image-generation mode")
    verify_document_digest(data, "requestDigestSha256")
    scene_descriptor = data.get("embeddedDocuments", {}).get("sceneMap", {})
    scene_path = resolve(path.parent, scene_descriptor.get("path", ""))
    if not scene_path.is_file() or sha256_file(scene_path) != scene_descriptor.get("sha256"):
        raise ValueError("embedded scene map descriptor is stale")
    facts = scene_facts(load_json(scene_path))
    if data.get("sceneFactsDigestSha256") != canonical_sha256(facts):
        raise ValueError("scene fact digest differs from the supplied scene map")
    context_descriptor = data.get("embeddedDocuments", {}).get("renderContext", {})
    context_path = resolve(path.parent, context_descriptor.get("path", ""))
    if not context_path.is_file() or sha256_file(context_path) != context_descriptor.get("sha256"):
        raise ValueError("embedded render context descriptor is stale")
    context_facts = render_context_facts(load_json(context_path))
    if data.get("renderContextFactsDigestSha256") != canonical_sha256(context_facts):
        raise ValueError("render context fact digest differs from the supplied context")
    expected_prompt = compile_closed_world_prompt(facts, context_facts)
    if data.get("prompt") != expected_prompt:
        raise ValueError("submitted prompt is not the exact deterministic closed-world compilation")
    if data.get("promptDigestSha256") != hashlib.sha256(expected_prompt.encode("utf-8")).hexdigest():
        raise ValueError("compiled prompt digest differs")
    json_documents = data.get("submittedJsonDocuments", [])
    expected_documents = {
        ("shot-scene-map", scene_descriptor.get("sha256"), canonical_sha256(facts)),
        ("render-media-context", context_descriptor.get("sha256"), canonical_sha256(context_facts)),
    }
    actual_documents = {
        (row.get("role"), row.get("sha256"), row.get("factsDigestSha256"))
        for row in json_documents
        if row.get("encoding") == "canonical-json-prompt-block"
    }
    if len(json_documents) != 2 or actual_documents != expected_documents:
        raise ValueError("submitted JSON documents do not match the two canonical prompt blocks")
    attachments = data.get("submittedImageAttachments", [])
    keys = [(row["role"], row.get("referenceId", "")) for row in attachments]
    if len(keys) != len(set(keys)):
        raise ValueError("submitted image attachment role/referenceId pairs must be unique")
    roles = [row["role"] for row in attachments]
    role_set = set(roles)
    current_roles = {"current-shot-concrete-structure-camera-authority"}
    if not current_roles.issubset(role_set):
        raise ValueError("actual request is missing a selected current-shot authority")
    forbidden_roles = {
        "current-shot-furnished-layout-qa-only",
        "entity-semantic-mask-qa-only",
        "room-semantic-mask-qa-only",
    }
    if forbidden_roles & role_set:
        raise ValueError("QA-only furniture or semantic-mask images entered the request")
    allowed_image_roles = current_roles | {
        "accepted-space-identity-reference",
        "user-product-reference",
    }
    if role_set - allowed_image_roles:
        raise ValueError("request contains an unplanned or unaccepted image reference")
    context = load_json(context_path)
    expected_references = {
        row["referenceShotId"] for row in context.get("spaceIdentityReferences", [])
    }
    actual_references = {
        row.get("referenceId")
        for row in attachments
        if row.get("role") == "accepted-space-identity-reference"
    }
    if actual_references != expected_references or None in actual_references:
        raise ValueError("submitted prior-shot references differ from the dependency plan")
    expected_product_references = {
        row["referenceId"] for row in context.get("userProductReferences", [])
    }
    actual_product_references = {
        row.get("referenceId")
        for row in attachments
        if row.get("role") == "user-product-reference"
    }
    if actual_product_references != expected_product_references or None in actual_product_references:
        raise ValueError("submitted user products differ from the context slot bindings")
    expected_slots_by_reference = {
        reference_id: sorted(
            row["slotId"]
            for row in context.get("userProductReferences", [])
            if row["referenceId"] == reference_id
        )
        for reference_id in expected_product_references
    }
    for row in attachments:
        if row.get("role") == "user-product-reference" and row.get("coveredSlotIds") != (
            expected_slots_by_reference[row["referenceId"]]
        ):
            raise ValueError("submitted user product slot coverage differs from context")
    for row in attachments:
        target = resolve(path.parent, row["path"])
        if not target.is_file() or sha256_file(target) != row["sha256"]:
            raise ValueError(f"submitted image changed: {row['role']}")
    return data


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_imagegen_request.py imagegen-request.json")
    data = validate_request(Path(sys.argv[1]))
    print(f"imagegen request accepted: {data['renderId']} {data['requestDigestSha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
