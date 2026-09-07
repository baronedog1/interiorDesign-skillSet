#!/usr/bin/env python3
"""Translate the frozen v3 camera plan for existing native backend adapters.

The adapter copies the selected pose exactly.  It never generates candidates,
scores views, changes FOV/window center, or chooses another camera.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def focal_length_from_vertical_fov(vertical_fov: float, sensor_height: float = 22.5) -> float:
    return sensor_height / (2.0 * math.tan(math.radians(vertical_fov) / 2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--model-manifest", required=True)
    parser.add_argument("--schema", choices=("v8", "v9"), default="v8")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source_path = Path(args.plan).resolve()
    manifest_path = Path(args.model_manifest).resolve()
    source = load(source_path)
    manifest = load(manifest_path)
    if source.get("schema") != "interior.algorithmic-camera-plan.v3":
        raise SystemExit("source plan must be interior.algorithmic-camera-plan.v3")
    if manifest.get("schema") != "interior.native-model-manifest.v1":
        raise SystemExit("model manifest must be interior.native-model-manifest.v1")
    backend = str(manifest.get("modelBackend", ""))
    if backend not in {"html-threejs", "blender", "cad-step"}:
        raise SystemExit(f"unsupported backend: {backend}")
    native = manifest.get("nativeModel", {})
    model_sha = str(native.get("sha256", ""))
    if len(model_sha) != 64:
        raise SystemExit("native model manifest lacks a SHA-256")
    shots = []
    for source_shot in source.get("shots", []):
        hidden = list(
            dict.fromkeys(
                [
                    *(source_shot.get("hiddenWallIds") or []),
                    *(source_shot.get("hiddenOpeningIds") or []),
                    *(source_shot.get("hiddenElementIds") or []),
                ]
            )
        )
        primary = list(source_shot.get("primarySubjectElementIds") or [])
        framing = list(source_shot.get("framingElementIds") or [])
        shot = {
            "shotId": source_shot["shotId"],
            "sequenceOrder": source_shot.get("sequenceOrder", len(shots) + 1),
            "roomId": source_shot["roomId"],
            "role": source_shot.get("viewRole", "primary"),
            "composition": "one-point-frontal",
            "modelBackend": backend,
            "sourceModelSha256": model_sha,
            "position": source_shot["position"],
            "target": source_shot["target"],
            "cameraHeight": float(source_shot["position"][1]),
            "focalLengthMm": round(focal_length_from_vertical_fov(float(source_shot["fov"])), 6),
            "fov": float(source_shot["fov"]),
            "windowCenter": source_shot.get("windowCenter", [0.0, 0.0]),
            "levelCamera": True,
            "visibility": {
                "mode": "frozen-unified-solver-plan",
                "hiddenElementIds": hidden,
                "preserveElementIds": list(dict.fromkeys([*primary, *framing])),
            },
            "mustShowElements": list(dict.fromkeys([*primary, *framing])),
            "algorithmEvidence": source_shot.get("algorithmEvidence", {}),
        }
        shots.append(shot)
    schema = f"interior.camera-plan.{args.schema}"
    output = {
        "schema": schema,
        "schemaVersion": args.schema.removeprefix("v") + ".0",
        "methodVersion": source.get("methodVersion"),
        "coordinateSystem": "interior-world-y-up.v1",
        "modelBackend": backend,
        "sourceModelSha256": model_sha,
        "floorplanId": source.get("floorplanId") or source.get("sourceFloorplanId"),
        "planPhase": "final-selection",
        "nativeModelManifestPath": str(manifest_path),
        "sourceUnifiedPlan": {"path": str(source_path), "sha256": sha256(source_path)},
        "shots": shots,
    }
    output_path = Path(args.output).resolve()
    write(output_path, output)
    print(json.dumps({"schema": schema, "backend": backend, "shots": len(shots), "output": str(output_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
