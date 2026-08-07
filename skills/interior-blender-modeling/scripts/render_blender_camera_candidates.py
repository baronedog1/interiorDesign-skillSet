#!/usr/bin/env python3
"""Render the deterministic primary and optional single projection fallback."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--out", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def canonical_to_blender(point):
    return Vector((float(point[0]), -float(point[2]), float(point[1])))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    job = json.loads(Path(args.job).resolve().read_text(encoding="utf-8"))
    if job.get("schema") != "interior.blender-camera-candidate-job.v1":
        raise ValueError("candidate job schema mismatch")
    model = Path(bpy.data.filepath).resolve()
    if not model.is_file() or sha256(model) != job.get("sourceModelSha256"):
        raise ValueError("opened .blend does not match candidate job")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x = int(job.get("imageSize", [1280, 720])[0])
    scene.render.resolution_y = int(job.get("imageSize", [1280, 720])[1])
    for obj in bpy.data.collections.get("CEILINGS", []).objects if bpy.data.collections.get("CEILINGS") else []:
        obj.hide_render = True
    records = []
    for candidate in job.get("candidates", []):
        data = bpy.data.cameras.new(f"candidate::{candidate['candidateId']}::data")
        camera = bpy.data.objects.new(f"candidate::{candidate['candidateId']}", data)
        bpy.data.collections["CAMERAS"].objects.link(camera)
        camera.location = canonical_to_blender(candidate["position"])
        target = canonical_to_blender(candidate["target"])
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        data.lens = float(candidate["focalLengthMm"])
        data.sensor_width = 36
        data.sensor_fit = "HORIZONTAL"
        scene.camera = camera
        image = out / f"{candidate['candidateId']}.png"
        scene.render.filepath = str(image)
        bpy.ops.render.render(write_still=True)
        records.append({
            "candidateId": candidate["candidateId"],
            "modelBackend": "blender",
            "sourceModelSha256": job["sourceModelSha256"],
            "position": candidate["position"],
            "target": candidate["target"],
            "focalLengthMm": candidate["focalLengthMm"],
            "imagePath": str(image),
            "imageSha256": sha256(image),
        })
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.cameras.remove(data)
    if not 1 <= len(records) <= 2 or len({record["imageSha256"] for record in records}) != len(records):
        raise RuntimeError("candidate previews must contain one deterministic primary and at most one distinct fallback")
    manifest = {
        "schema": "interior.blender-camera-candidate-result.v1",
        "sourceModelSha256": job["sourceModelSha256"],
        "accepted": True,
        "records": records,
    }
    (out / "candidate-result.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
