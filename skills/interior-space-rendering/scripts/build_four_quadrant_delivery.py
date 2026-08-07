#!/usr/bin/env python3
"""Compose the canonical per-shot Q1/Q2/Q3/Q4 delivery after render acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from render_contract import load_json, resolve, sha256_file
from validate_render_review import validate_review


def relative(path: Path, root: Path) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def font(size: int, bold: bool = False):
    name = "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc"
    path = Path("/usr/share/fonts/opentype/noto") / name
    return ImageFont.truetype(path, size=size) if path.is_file() else ImageFont.load_default()


def fitted(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as opened:
        return ImageOps.fit(opened.convert("RGB"), size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-map", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--room-name", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    scene_path = Path(args.scene_map).resolve()
    request_path = Path(args.request).resolve()
    receipt_path = Path(args.receipt).resolve()
    review_path = Path(args.review).resolve()
    out_path = Path(args.out).resolve()
    scene = load_json(scene_path)
    request = load_json(request_path)
    receipt = load_json(receipt_path)
    validate_review(scene_path, request_path, receipt_path, review_path)
    if scene.get("schema") != "interior.shot-scene-map.v9":
        raise ValueError("scene map must use v9")
    if receipt.get("schema") != "interior.imagegen-receipt.v4":
        raise ValueError("Q4 must be a true image-generated render")
    if request.get("guidanceMode") != "slot-guided":
        raise ValueError("Q4 must use the single slot-guided generation contract")

    scene_root = scene_path.parent
    asset_keys = ["slotGuidedConcreteImage", "furnishedReferenceImage", "planCameraImage"]
    source_paths = []
    for key in asset_keys:
        asset = scene["assets"][key]
        target = (scene_root / asset["file"]).resolve()
        if not target.is_file() or sha256_file(target) != asset["sha256"]:
            raise ValueError(f"stale quadrant asset: {key}")
        source_paths.append(target)
    submitted = {(row["role"], row["sha256"]) for row in request["submittedImageAttachments"]}
    if (
        "current-shot-concrete-structure-camera-authority",
        scene["assets"][asset_keys[0]]["sha256"],
    ) not in submitted:
        raise ValueError("Q1 was not submitted to image generation")
    if any(
        role in {
            "current-shot-furnished-layout-qa-only",
            "current-shot-confirmed-white-model-shape-authority",
            "entity-semantic-mask-qa-only",
            "room-semantic-mask-qa-only",
        }
        for role, _ in submitted
    ):
        raise ValueError("generation submitted QA-only furniture or mask images")
    render_path = resolve(receipt_path.parent, receipt["outputImage"]["path"])
    if not render_path.is_file() or sha256_file(render_path) != receipt["outputImage"]["sha256"]:
        raise ValueError("accepted Q4 render is missing or stale")
    source_paths.append(render_path)

    labels = [
        "① 槽位引导｜纯水泥结构 + 当前机位",
        "② 家具柜体｜同一模型 + 同一机位",
        "③ 平面机位｜位置 + 方向 + 视锥",
        "④ 渲染图｜同一结构与空间身份",
    ]
    width, height, gutter, header = 1920, 1200, 18, 62
    cell_w = (width - gutter * 3) // 2
    cell_h = (height - gutter * 3) // 2
    canvas = Image.new("RGB", (width, height), "#171613")
    draw = ImageDraw.Draw(canvas)
    for index, (source, label) in enumerate(zip(source_paths, labels)):
        col, row = index % 2, index // 2
        x = gutter + col * (cell_w + gutter)
        y = gutter + row * (cell_h + gutter)
        draw.rectangle((x, y, x + cell_w, y + cell_h), fill="#24221e")
        draw.text((x + 20, y + 16), label, fill="#f4e7cf", font=font(24, True))
        canvas.paste(fitted(source, (cell_w - 2, cell_h - header - 1)), (x + 1, y + header))
    draw.text(
        (width - 28, height - 24),
        f"{args.room_name} | {scene['shotId']} | {scene['sourceModelSha256'][:12]}",
        fill="#f4e7cf",
        font=font(17),
        anchor="rs",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG", optimize=True)
    evidence_path = out_path.with_suffix(".evidence.json")
    evidence = {
        "schema": "interior.render-four-quadrant-evidence.v1",
        "shotId": scene["shotId"],
        "renderId": request["renderId"],
        "renderProducer": "imagegen-closed-world",
        "floorplanId": scene["floorplanId"],
        "sourceModelSha256": scene["sourceModelSha256"],
        "sceneMap": {"path": relative(scene_path, evidence_path.parent), "sha256": sha256_file(scene_path)},
        "request": {"path": relative(request_path, evidence_path.parent), "sha256": sha256_file(request_path)},
        "receipt": {"path": relative(receipt_path, evidence_path.parent), "sha256": sha256_file(receipt_path)},
        "review": {"path": relative(review_path, evidence_path.parent), "sha256": sha256_file(review_path)},
        "quadrants": [
            {
                "index": index + 1,
                "role": role,
                "path": relative(source, evidence_path.parent),
                "sha256": sha256_file(source),
            }
            for index, (role, source) in enumerate(zip(
                [
                    "q1-slot-guided-concrete-camera",
                    "q2-furnished-same-camera-reference",
                    "q3-plan-camera-frustum",
                    "q4-accepted-render",
                ],
                source_paths,
            ))
        ],
        "output": {
            "path": relative(out_path, evidence_path.parent),
            "sha256": sha256_file(out_path),
            "imageSize": [width, height],
        },
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from validate_four_quadrant_delivery import validate_delivery

    validate_delivery(evidence_path)
    print(json.dumps({"image": str(out_path), "evidence": str(evidence_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
