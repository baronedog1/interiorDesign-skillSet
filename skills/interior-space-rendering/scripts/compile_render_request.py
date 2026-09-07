#!/usr/bin/env python3
"""Compile current Camera v3 image facts directly into render requests and a batch plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FACTS_SCHEMA = "interior.camera-image-facts.v3"
PLAN_SCHEMA = "interior.model-image-render-plan.v13"
CONTEXT_SCHEMA = "interior.render-context.v9"
REQUEST_SCHEMA = "interior.imagegen-request.v5"
BATCH_SCHEMA = "imagegen.batch-plan.v1"
# Camera-generated stable IDs are case-sensitive and existing valid camera
# contracts include values such as ``01-R01``.  Accept ASCII letters in both
# cases without normalizing or rewriting the source shot identity.
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*$")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def parse_pair(value: str, label: str) -> tuple[str, str]:
    key, separator, text = value.partition("=")
    if not separator or not ID_RE.fullmatch(key) or not text.strip():
        raise ValueError(f"{label} must look like stable-id=value: {value}")
    return key, text.strip()


def dimensions(row: dict[str, Any]) -> dict[str, float]:
    world = row.get("world") or row.get("placementWorld") or {}
    value = world.get("dimensionsMeters") or {}
    return {
        "width": round(float(value.get("width", 0)), 4),
        "depth": round(float(value.get("depth", 0)), 4),
        "height": round(float(value.get("height", 0)), 4),
    }


def object_summary(row: dict[str, Any]) -> dict[str, Any]:
    world = row.get("world") or row.get("placementWorld") or {}
    return {
        "id": row.get("id"),
        "name": row.get("name") or row.get("id"),
        "functionalClass": row.get("functionalClass") or row.get("kind"),
        "roomId": row.get("roomId"),
        "componentId": row.get("componentId"),
        "center": world.get("center"),
        "dimensionsMeters": dimensions(row),
        "rotationY": world.get("rotationY", 0),
    }


def compact_prompt(context: dict[str, Any]) -> str:
    camera = context["camera"]
    inventory = context["functionalObjects"]
    object_lines = "; ".join(
        f"{row['name']}[{row['functionalClass']}] id={row['id']} "
        f"size={row['dimensionsMeters']} center={row['center']} rotationY={row['rotationY']}"
        for row in inventory
    )
    return (
        f"Create one polished photorealistic interior image in {context['style']['name']}. "
        "Use the attached current-model camera image as the exact camera, room geometry, opening, "
        "furniture count, layout, scale and orientation guide. Preserve the current viewpoint and "
        "every functional object; do not add, remove, move, mirror or resize walls, doors, windows, "
        "wardrobes, beds, cabinets, appliances or sanitary fixtures. Improve only materials, lighting, "
        "non-structural decor and photographic realism. Keep the result visually clean and customer-ready. "
        f"Camera position={camera.get('position')}, target={camera.get('target')}, fov={camera.get('fov')}, "
        f"windowCenter={camera.get('windowCenter')}. Exact functional inventory: {object_lines}."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-facts", action="append", required=True)
    parser.add_argument("--style", action="append", required=True, metavar="ID=NAME")
    parser.add_argument("--reference", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-concurrency", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.max_concurrency <= 5:
        raise ValueError("--max-concurrency must be between 1 and 5")

    root = Path(args.out_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    styles = [parse_pair(value, "--style") for value in args.style]
    if len({row[0] for row in styles}) != len(styles):
        raise ValueError("style IDs must be unique")
    references: list[dict[str, Any]] = []
    for value in args.reference:
        reference_id, raw_path = parse_pair(value, "--reference")
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise ValueError(f"reference image is missing: {path}")
        references.append({
            "referenceId": reference_id,
            "path": str(path),
            "sha256": digest_file(path),
            "role": "user-product-or-style-reference",
            "sendToImageModel": True,
        })

    source_rows: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    seen_shots: set[str] = set()
    floorplan_ids: set[str] = set()
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for raw_path in args.camera_facts:
        facts_path = Path(raw_path).resolve()
        facts = load(facts_path)
        if facts.get("schema") != FACTS_SCHEMA:
            raise ValueError(f"camera facts must use {FACTS_SCHEMA}: {facts_path}")
        if facts.get("generation", {}).get("imageRecognitionUsed") is not False:
            raise ValueError("camera facts must come from native scene code, not image recognition")
        shot = facts.get("shot") or {}
        visible = facts.get("visibleScene") or {}
        shot_id = str(shot.get("shotId") or "")
        if not ID_RE.fullmatch(shot_id) or shot_id in seen_shots:
            raise ValueError(f"invalid or duplicate shotId: {shot_id}")
        floorplan_id = str(visible.get("sourceFloorplanId") or "")
        room_id = str(shot.get("roomId") or visible.get("roomId") or "")
        if not floorplan_id or not room_id:
            raise ValueError(f"{shot_id}: floorplan or room identity is missing")
        floorplan_ids.add(floorplan_id)
        seen_shots.add(shot_id)

        image_descriptor = facts.get("image") or {}
        image_path = (facts_path.parent / str(image_descriptor.get("filename") or "")).resolve()
        if not image_path.is_file() or digest_file(image_path) != image_descriptor.get("sha256"):
            raise ValueError(f"{shot_id}: paired camera image is missing or changed")

        inventory = [object_summary(row) for row in facts.get("semanticInventory", [])]
        inventory_ids = {row["id"] for row in inventory if row.get("id")}
        expected_ids = set(facts.get("expectedRoomElementIds", []))
        advisories = list(facts.get("subjectFocus", {}).get("advisoryIssues", []))
        missing_expected = sorted(expected_ids - inventory_ids)
        if missing_expected:
            advisories.append("semantic-inventory-missing-expected-ids:" + ",".join(missing_expected))
        pixel_advisories = (
            shot.get("algorithmEvidence", {})
            .get("nativePixelValidation", {})
            .get("qualityAdvisories", [])
        )
        advisories.extend(str(value) for value in pixel_advisories)

        source_rows.append({
            "shotId": shot_id,
            "roomId": room_id,
            "roomName": shot.get("roomName"),
            "cameraFacts": {"path": str(facts_path), "sha256": digest_file(facts_path)},
            "cameraImage": {"path": str(image_path), "sha256": digest_file(image_path)},
        })
        for style_id, style_name in styles:
            render_id = f"{shot_id}-{style_id}"
            context_path = root / "contexts" / f"{render_id}.render-context.v9.json"
            request_path = root / "requests" / f"{render_id}.imagegen-request.v5.json"
            context = {
                "schema": CONTEXT_SCHEMA,
                "schemaVersion": "9.0",
                "floorplanId": floorplan_id,
                "shotId": shot_id,
                "roomId": room_id,
                "roomName": shot.get("roomName"),
                "style": {"styleId": style_id, "name": style_name},
                "camera": visible.get("camera") or {
                    key: shot.get(key) for key in ("position", "target", "fov", "windowCenter")
                },
                "visibleRoomIds": visible.get("visibleRoomIds") or [room_id],
                "structure": {
                    "walls": (visible.get("contents") or {}).get("walls", []),
                    "openings": (visible.get("contents") or {}).get("openings", []),
                },
                "functionalObjects": inventory,
                "currentModelGuide": {
                    "path": str(image_path),
                    "sha256": digest_file(image_path),
                    "authority": "exact-camera-structure-layout-and-functional-object-guide",
                },
                "qualityAdvisories": sorted(set(advisories)),
                "qualityPolicy": {
                    "advisoryOnly": True,
                    "deliveryBlockedByQuality": False,
                    "customerRunAction": "generate-once-and-deliver-result",
                    "releaseRegressionAction": "improve-shared-algorithm-not-this-customer-image",
                },
                "generatedAtUtc": generated_at,
            }
            write(context_path, context)
            attachments = [{
                "path": str(image_path),
                "sha256": digest_file(image_path),
                "role": "current-model-camera-layout-guide",
                "sendToImageModel": True,
            }, *references]
            request = {
                "schema": REQUEST_SCHEMA,
                "schemaVersion": "5.0",
                "sourceSkill": "interior-space-rendering",
                "renderId": render_id,
                "shotId": shot_id,
                "style": {"styleId": style_id, "name": style_name},
                "prompt": compact_prompt(context),
                "attachments": attachments,
                "context": {"path": str(context_path), "sha256": digest_file(context_path)},
                "executionPolicy": {
                    "formalGenerationCount": 1,
                    "qualityRetryForbidden": True,
                    "deliveryBlockedByQuality": False,
                    "technicalFailureStopsCurrentCall": True,
                },
            }
            write(request_path, request)
            outputs.append({
                "renderId": render_id,
                "shotId": shot_id,
                "styleId": style_id,
                "request": {"path": str(request_path), "sha256": digest_file(request_path)},
                "outputImage": f"{render_id}.png",
                "status": "ready",
            })
            jobs.append({
                "jobId": render_id,
                "requestPath": relative(request_path, root),
                "requestSha256": digest_file(request_path),
                "dependencies": [],
                "outputFile": f"{render_id}.png",
                "maxAttempts": 1,
            })
    if len(floorplan_ids) != 1:
        raise ValueError("all camera facts in one render plan must belong to one floorplan")

    plan_path = root / "render-plan.v13.json"
    plan = {
        "schema": PLAN_SCHEMA,
        "schemaVersion": "13.0",
        "floorplanId": next(iter(floorplan_ids)),
        "inputPolicy": "camera-image-facts-v3-direct-no-scene-map-intermediate",
        "qualityPolicy": "advisory-only-always-deliver-generated-image",
        "sources": source_rows,
        "styles": [{"styleId": key, "name": name} for key, name in styles],
        "outputs": outputs,
        "generatedAtUtc": generated_at,
    }
    write(plan_path, plan)
    batch_path = root / "imagegen.batch-plan.v1.json"
    batch = {
        "schema": BATCH_SCHEMA,
        "planId": "interior-render-" + hashlib.sha256(str(plan_path).encode()).hexdigest()[:12],
        "sourceSkill": "interior-space-rendering",
        "sourcePlan": {"path": relative(plan_path, root), "sha256": digest_file(plan_path)},
        "maxConcurrency": args.max_concurrency,
        "batches": [{"batchId": "independent-renders", "jobIds": [row["jobId"] for row in jobs]}],
        "jobs": jobs,
    }
    write(batch_path, batch)
    print(json.dumps({
        "ok": True,
        "renderPlan": str(plan_path),
        "batchPlan": str(batch_path),
        "requests": len(jobs),
        "qualityGateCount": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
