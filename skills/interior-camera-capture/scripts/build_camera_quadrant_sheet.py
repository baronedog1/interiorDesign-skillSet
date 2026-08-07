#!/usr/bin/env python3
"""Build the canonical Q1-Q3 camera evidence sheet with a Q4 placeholder."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


SCHEMA = "interior.shot-scene-map.v9"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int, bold: bool = False):
    name = "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc"
    path = Path("/usr/share/fonts/opentype/noto") / name
    return ImageFont.truetype(path, size=size) if path.is_file() else ImageFont.load_default()


def fitted(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    return ImageOps.fit(image, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-map", required=True)
    parser.add_argument("--camera-plan", required=True)
    parser.add_argument("--room-name", required=True)
    parser.add_argument("--shot-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    scene_path = Path(args.scene_map).resolve()
    plan_path = Path(args.camera_plan).resolve()
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if scene.get("schema") != SCHEMA or scene.get("shotId") != args.shot_id:
        raise ValueError("camera quadrant source must be one shot-scene-map.v9")
    if plan.get("schema") != "interior.camera-plan.v8":
        raise ValueError("camera plan must use v8")
    shot = next(row for row in plan["shots"] if row["shotId"] == args.shot_id)
    if scene["camera"]["position"] != shot["position"] or scene["camera"]["target"] != shot["target"]:
        raise ValueError("scene-map and camera-plan camera differ")
    if scene["sourceModelSha256"] != plan["sourceModelSha256"]:
        raise ValueError("scene-map and camera-plan model differ")

    root = scene_path.parent
    roles = [
        ("slotGuidedConcreteImage", "① 槽位引导｜水泥墙地面 + 当前机位"),
        ("furnishedReferenceImage", "② 家具柜体｜同一模型 + 同一机位"),
        ("planCameraImage", "③ 平面机位｜位置 + 方向 + 视锥"),
    ]
    panels: list[tuple[Path | None, str]] = []
    for key, label in roles:
        asset = scene["assets"][key]
        path = (root / asset["file"]).resolve()
        if not path.is_file() or sha256(path) != asset["sha256"]:
            raise ValueError(f"stale quadrant source: {key}")
        panels.append((path, label))
    panels.append((None, "④ 渲染图｜等待 accepted render 回填"))

    width, height, gutter, header = 1920, 1200, 18, 62
    cell_w = (width - gutter * 3) // 2
    cell_h = (height - gutter * 3) // 2
    canvas = Image.new("RGB", (width, height), "#171613")
    draw = ImageDraw.Draw(canvas)
    for index, (path, label) in enumerate(panels):
        col, row = index % 2, index // 2
        x = gutter + col * (cell_w + gutter)
        y = gutter + row * (cell_h + gutter)
        draw.rectangle((x, y, x + cell_w, y + cell_h), fill="#24221e")
        draw.text((x + 20, y + 16), label, fill="#f4e7cf", font=font(24, True))
        target = (cell_w - 2, cell_h - header - 1)
        if path:
            canvas.paste(fitted(path, target), (x + 1, y + header))
        else:
            draw.rectangle((x + 1, y + header, x + cell_w - 1, y + cell_h - 1), fill="#ece7de")
            message = "等待同一 shot 的第四象限"
            draw.text(
                (x + cell_w / 2, y + header + target[1] / 2),
                message,
                fill="#756c60",
                font=font(34, True),
                anchor="mm",
            )
    draw.text(
        (width - 28, height - 24),
        f"{args.room_name} | {args.shot_id} | {scene['sourceModelSha256'][:12]}",
        fill="#f4e7cf",
        font=font(17),
        anchor="rs",
    )
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG", optimize=True)


if __name__ == "__main__":
    main()
