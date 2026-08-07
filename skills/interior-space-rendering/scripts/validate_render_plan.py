#!/usr/bin/env python3
"""Validate the closed-world multi-shot render plan v11."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path

from render_contract import (
    validate_closed_world_view,
    validate_execution_policy,
    validate_projection_lock,
    validate_scene_camera_authority,
    validate_space_reference_plan,
)
from validate_generation_receipt import validate_receipt
from validate_four_quadrant_delivery import validate_delivery
from validate_imagegen_request import validate_request
from validate_prompt_manifest import validate_manifest
from validate_render_review import validate_review
from validate_user_product_reference_manifest import validate_manifest as validate_product_manifest


PLAN_SCHEMA = "interior.model-image-render-plan.v11"
MAP_SCHEMA = "interior.shot-scene-map.v9"
CONTEXT_SCHEMA = "interior.render-media-context.v7"
MODES = {"slot-guided"}
BACKENDS = {"html-threejs", "blender", "cad-step"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_treatment(value: dict, mode: str, scene: dict) -> None:
    if not isinstance(value, dict) or value.get("playbookVersion") != "architectural-rendering.v1":
        raise ValueError("architectural treatment is missing")
    if value.get("structureRevisionPolicy") != "preserve-current-accepted-model":
        raise ValueError("rendering may not revise the accepted structure")
    if value.get("ceiling", {}).get("geometryPolicy") != "preserve-current-model":
        raise ValueError("ceiling geometry must be preserved")
    if value.get("walls", {}).get("geometryPolicy") != "preserve-current-model":
        raise ValueError("wall geometry must be preserved")
    if value.get("windows", {}).get("openingPolicy") != "preserve-current-model":
        raise ValueError("window openings must be preserved")
    if value.get("doors", {}).get("openingPolicy") != "preserve-current-model":
        raise ValueError("door openings must be preserved")
    if value.get("balcony", {}).get("enclosurePolicy") != "preserve-current-model":
        raise ValueError("balcony enclosure must be preserved")
    if value.get("decor", {}).get("placementPolicy") != "nonstructural-no-opening-or-clearance-obstruction":
        raise ValueError("decor placement policy is invalid")
    expected_cabinet_policy = (
        "location-footprint-orientation-category-clearance-locked-shape-material-flexible"
    )
    if value.get("cabinetry", {}).get("shapePolicy") != expected_cabinet_policy:
        raise ValueError("cabinet policy differs from the guidance mode")
    if value.get("forbiddenGeometryRequests") != [
        "move-or-resize-wall",
        "move-or-resize-opening",
        "invent-or-remove-door",
        "change-ceiling-volume",
        "change-balcony-enclosure",
    ]:
        raise ValueError("forbidden geometry requests are incomplete")
    validate_projection_lock(value.get("projectionLock"), scene)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render_plan")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="reject planned, candidate, rejected, or missing four-quadrant delivery states",
    )
    args = parser.parse_args()
    path = Path(args.render_plan).resolve()
    root = path.parent
    data = load_json(path)
    if data.get("schema") != PLAN_SCHEMA or data.get("schemaVersion") != "11.0":
        raise ValueError("render plan must use v11")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data.get("floorplanId", "")):
        raise ValueError("invalid floorplanId")
    if data.get("modeSelectionOwner") != "render-plan.v11" or data.get("modeSwitchingPolicy") != "forbidden":
        raise ValueError("render mode ownership differs from v11")
    validate_execution_policy(data.get("renderExecutionPolicy"))
    styles = data.get("requestedStyles")
    if not isinstance(styles, list) or not styles or len(styles) != len(set(styles)):
        raise ValueError("requested styles must be a non-empty unique list")

    shots = data.get("selectedShots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("selectedShots is empty")
    scene_maps: dict[str, dict] = {}
    scene_paths: dict[str, Path] = {}
    shot_modes: dict[str, str] = {}
    shot_backends: dict[str, str] = {}
    for row in shots:
        shot_id = row.get("shotId", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", shot_id) or shot_id in scene_maps:
            raise ValueError("shot IDs must be unique slugs")
        backend = row.get("modelBackend")
        if backend not in BACKENDS or not re.fullmatch(r"[0-9a-f]{64}", row.get("sourceModelSha256", "")):
            raise ValueError(f"{shot_id}: invalid backend or model hash")
        scene_path = (root / row["sourceSceneMap"]).resolve()
        if not scene_path.is_file() or sha256(scene_path) != row.get("sourceSceneMapSha256"):
            raise ValueError(f"{shot_id}: scene map is missing or stale")
        scene = load_json(scene_path)
        if scene.get("schema") != MAP_SCHEMA or scene.get("shotId") != shot_id:
            raise ValueError(f"{shot_id}: scene map identity mismatch")
        if scene.get("floorplanId") != data["floorplanId"] or scene.get("modelBackend") != backend:
            raise ValueError(f"{shot_id}: scene map source mismatch")
        if scene.get("sourceModelSha256") != row["sourceModelSha256"] or scene.get("review", {}).get("status") != "accepted":
            raise ValueError(f"{shot_id}: scene map is not accepted for this model")
        if scene.get("guidance", {}).get("selectionOwner") != "interior-space-rendering/render-plan.v11":
            raise ValueError(f"{shot_id}: stale scene-map guidance owner")
        expected_quadrants = {
            "schema": "interior.render-four-quadrant.v1",
            "quadrants": [
                "q1-slot-guided-concrete-camera",
                "q2-furnished-same-camera-reference",
                "q3-plan-camera-frustum",
                "q4-accepted-render",
            ],
            "sameShotCameraAndModelRequired": True,
        }
        if scene.get("guidance", {}).get("fourQuadrantContract") != expected_quadrants:
            raise ValueError(f"{shot_id}: four-quadrant source contract is missing")
        validate_closed_world_view(scene)
        validate_scene_camera_authority(scene, scene_path)
        mode = row.get("guidance", {}).get("mode")
        if mode not in MODES:
            raise ValueError(f"{shot_id}: invalid guidance mode")
        if row["guidance"].get("selectionSource") != "system-default" or row["guidance"].get("userConfirmation") is not None:
            raise ValueError(f"{shot_id}: slot-guided must be the unconfirmed generation mode")
        scene_maps[shot_id] = scene
        scene_paths[shot_id] = scene_path
        shot_modes[shot_id] = mode
        shot_backends[shot_id] = backend

    product_descriptor = data.get("userProductReferenceManifest")
    if product_descriptor is not None:
        if not isinstance(product_descriptor, dict):
            raise ValueError("userProductReferenceManifest must be a descriptor")
        product_path = (root / product_descriptor.get("path", "")).resolve()
        if not product_path.is_file() or sha256(product_path) != product_descriptor.get("sha256"):
            raise ValueError("user product reference manifest is missing or stale")
        all_visible_slot_ids = {
            slot["slotId"]
            for scene in scene_maps.values()
            for slot in scene.get("placementSlots", [])
        }
        validate_product_manifest(
            product_path,
            expected_floorplan_id=data["floorplanId"],
            allowed_slot_ids=all_visible_slot_ids,
            require_exact_slots=product_descriptor.get("required") is True,
        )

    reference = validate_space_reference_plan(data, scene_maps)
    reference_by_shot = {row["shotId"]: row for row in reference["shots"]}
    expected_outputs = set(itertools.product(scene_maps, styles))
    outputs = data.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("outputs must be a list")
    actual_outputs = set()
    output_by_pair = {}
    for output in outputs:
        pair = output.get("shotId"), output.get("styleId")
        if pair not in expected_outputs or pair in actual_outputs:
            raise ValueError("outputs must enumerate every shot/style pair exactly once")
        actual_outputs.add(pair)
        output_by_pair[pair] = output
        shot_id, style_id = pair
        mode = shot_modes[shot_id]
        scene = scene_maps[shot_id]
        if output.get("guidanceMode") != mode or output.get("modelBackend") != shot_backends[shot_id]:
            raise ValueError(f"{shot_id}: output source differs from selected shot")
        validate_treatment(output.get("architecturalTreatment"), mode, scene)
        context_path = (root / output["renderMediaContext"]).resolve()
        prompt_path = (root / output["promptManifest"]).resolve()
        if not context_path.is_file() or sha256(context_path) != output.get("renderMediaContextSha256"):
            raise ValueError(f"{shot_id}: context is missing or stale")
        if not prompt_path.is_file() or sha256(prompt_path) != output.get("promptManifestSha256"):
            raise ValueError(f"{shot_id}: prompt manifest is missing or stale")
        context = load_json(context_path)
        if context.get("schema") != CONTEXT_SCHEMA or context.get("renderId") != output.get("renderId"):
            raise ValueError(f"{shot_id}: context identity mismatch")
        if context.get("closedWorldView") != scene.get("closedWorldView"):
            raise ValueError(f"{shot_id}: context scene inventory differs")
        expected_dependencies = reference_by_shot[shot_id]["dependsOnAcceptedShotIds"]
        if [row["referenceShotId"] for row in context.get("spaceIdentityReferences", [])] != expected_dependencies:
            raise ValueError(f"{shot_id}: context identity dependencies differ from the plan")
        validate_manifest(prompt_path)
        status = output.get("status")
        if status not in {"planned", "candidate", "accepted", "rejected"}:
            raise ValueError(f"{shot_id}: invalid output status")
        if status == "accepted":
            request_path = (root / output["imagegenRequest"]).resolve()
            receipt_path = (root / output["generationReceipt"]).resolve()
            review_path = (root / output["renderReview"]).resolve()
            image_path = (root / output["outputImage"]).resolve()
            for target, digest in (
                (request_path, output.get("imagegenRequestSha256")),
                (receipt_path, output.get("generationReceiptSha256")),
                (review_path, output.get("renderReviewSha256")),
                (image_path, output.get("outputImageSha256")),
            ):
                if not target.is_file() or sha256(target) != digest:
                    raise ValueError(f"{shot_id}: accepted output evidence is missing or stale")
            request = validate_request(request_path)
            receipt = validate_receipt(request_path, receipt_path)
            review = validate_review(scene_paths[shot_id], request_path, receipt_path, review_path)
            if request.get("renderId") != output.get("renderId") or review.get("decision") != "accept":
                raise ValueError(f"{shot_id}: accepted output has an invalid request or review")
            receipt_image = (receipt_path.parent / receipt["outputImage"]["path"]).resolve()
            if receipt_image != image_path or receipt["outputImage"]["sha256"] != output["outputImageSha256"]:
                raise ValueError(f"{shot_id}: accepted image differs from the provider receipt")
            if output.get("renderProducer") != "imagegen-closed-world":
                raise ValueError(f"{shot_id}: renderProducer differs from its receipt")
    if actual_outputs != expected_outputs:
        raise ValueError("render outputs are incomplete")

    if args.require_complete:
        for (shot_id, style_id), output in output_by_pair.items():
            if output.get("status") != "accepted":
                raise ValueError(f"{shot_id}/{style_id}: final delivery requires accepted output")
            descriptor = output.get("fourQuadrantEvidence")
            if not isinstance(descriptor, dict):
                raise ValueError(f"{shot_id}/{style_id}: four-quadrant evidence is missing")
            evidence_path = (root / descriptor.get("path", "")).resolve()
            if not evidence_path.is_file() or sha256(evidence_path) != descriptor.get("sha256"):
                raise ValueError(f"{shot_id}/{style_id}: four-quadrant evidence is missing or stale")
            evidence = validate_delivery(evidence_path)
            if (
                evidence.get("shotId") != shot_id
                or evidence.get("renderId") != output.get("renderId")
                or evidence.get("sourceModelSha256") != output.get("architecturalTreatment", {})
                .get("projectionLock", {})
                .get("sourceModelSha256")
            ):
                raise ValueError(f"{shot_id}/{style_id}: four-quadrant evidence identity mismatch")

    for style_id in styles:
        for batch in reference["executionBatches"]:
            for shot_id in batch:
                output = output_by_pair[(shot_id, style_id)]
                if output.get("status") in {"candidate", "accepted"}:
                    for dependency in reference_by_shot[shot_id]["dependsOnAcceptedShotIds"]:
                        if output_by_pair[(dependency, style_id)].get("status") != "accepted":
                            raise ValueError(f"{shot_id}: generation started before dependency {dependency} was accepted")
    print(json.dumps({
        "ok": True,
        "schema": data["schema"],
        "shots": len(scene_maps),
        "styles": len(styles),
        "outputs": len(outputs),
        "executionBatches": len(reference["executionBatches"]),
        "complete": args.require_complete,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
