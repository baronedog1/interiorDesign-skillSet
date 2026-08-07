#!/usr/bin/env python3
"""Validate one canonical per-shot four-quadrant delivery."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from render_contract import load_json, resolve, sha256_file
from validate_render_review import validate_review


def validate_descriptor(root: Path, row: dict) -> Path:
    target = resolve(root, row.get("path", ""))
    if not target.is_file() or sha256_file(target) != row.get("sha256"):
        raise ValueError("four-quadrant source is missing or stale")
    return target


def validate_delivery(path: Path) -> dict:
    path = path.resolve()
    data = load_json(path)
    if data.get("schema") != "interior.render-four-quadrant-evidence.v1":
        raise ValueError("four-quadrant evidence schema mismatch")
    root = path.parent
    scene_path = validate_descriptor(root, data["sceneMap"])
    request_path = validate_descriptor(root, data["request"])
    receipt_path = validate_descriptor(root, data["receipt"])
    review_path = validate_descriptor(root, data["review"])
    scene = load_json(scene_path)
    request = load_json(request_path)
    receipt = load_json(receipt_path)
    validate_review(scene_path, request_path, receipt_path, review_path)
    if receipt.get("schema") != "interior.imagegen-receipt.v4":
        raise ValueError("Q4 must have an imagegen receipt")
    if data.get("renderProducer") != "imagegen-closed-world":
        raise ValueError("four-quadrant producer differs from the accepted receipt")
    if data.get("shotId") != scene.get("shotId") or data.get("renderId") != request.get("renderId"):
        raise ValueError("four-quadrant shot/render identity mismatch")
    if data.get("floorplanId") != scene.get("floorplanId") or data.get("sourceModelSha256") != scene.get("sourceModelSha256"):
        raise ValueError("four-quadrant floorplan/model identity mismatch")
    expected_roles = [
        "q1-slot-guided-concrete-camera",
        "q2-furnished-same-camera-reference",
        "q3-plan-camera-frustum",
        "q4-accepted-render",
    ]
    rows = data.get("quadrants")
    if not isinstance(rows, list) or [row.get("index") for row in rows] != [1, 2, 3, 4]:
        raise ValueError("four-quadrant indices must be 1..4")
    if [row.get("role") for row in rows] != expected_roles:
        raise ValueError("four-quadrant roles are not canonical")
    quadrant_paths = [validate_descriptor(root, row) for row in rows]
    assets = scene["assets"]
    if rows[0]["sha256"] != assets["slotGuidedConcreteImage"]["sha256"]:
        raise ValueError("Q1 differs from the current scene map")
    if rows[1]["sha256"] != assets["furnishedReferenceImage"]["sha256"]:
        raise ValueError("Q2 differs from the current scene map")
    if rows[2]["sha256"] != assets["planCameraImage"]["sha256"]:
        raise ValueError("Q3 differs from the current scene map")
    if rows[3]["sha256"] != receipt["outputImage"]["sha256"]:
        raise ValueError("Q4 differs from the accepted render-producer output")
    output_path = validate_descriptor(root, data["output"])
    with Image.open(output_path) as image:
        if list(image.size) != data["output"].get("imageSize") or list(image.size) != [1920, 1200]:
            raise ValueError("four-quadrant canvas dimensions differ")
    for source in quadrant_paths:
        with Image.open(source) as image:
            image.verify()
    return data


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_four_quadrant_delivery.py evidence.json")
    data = validate_delivery(Path(sys.argv[1]))
    print(f"four-quadrant delivery accepted: {data['shotId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
