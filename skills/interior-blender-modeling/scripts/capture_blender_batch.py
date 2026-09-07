#!/usr/bin/env python3
"""Render one frozen Blender camera plan with one bounded process per shot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True)
    parser.add_argument("--camera-plan", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--viewport", default="960x600")
    parser.add_argument("--blender-bin", default="/home/agentops/agent-runtime/bin/blender")
    args = parser.parse_args()

    blend = Path(args.blend).resolve()
    plan_path = Path(args.camera_plan).resolve()
    adapter = Path(args.adapter).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = read(plan_path)
    if plan.get("schema") != "interior.algorithmic-camera-plan.v3":
        raise SystemExit("Blender batch capture requires interior.algorithmic-camera-plan.v3")

    records = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=".blender-shot-", dir=out) as temporary_root:
        root = Path(temporary_root)
        for shot in sorted(plan.get("shots", []), key=lambda value: int(value.get("sequenceOrder", 0))):
            sequence = int(shot["sequenceOrder"])
            shot_dir = root / str(sequence)
            command = [
                args.blender_bin, "--background", str(blend), "--python-exit-code", "1",
                "--python", str(adapter), "--", "--camera-plan", str(plan_path),
                "--out-dir", str(shot_dir), "--viewport", args.viewport,
                "--sequence", str(sequence),
            ]
            subprocess.run(command, check=True)
            index = read(shot_dir / "camera-delivery-index.json")
            if len(index.get("records", [])) != 1:
                raise SystemExit(f"sequence {sequence} did not return exactly one record")
            record = index["records"][0]
            image_source = Path(record["image"])
            facts_source = Path(record["facts"])
            image_target = out / image_source.name
            facts_target = out / facts_source.name
            shutil.copy2(image_source, image_target)
            shutil.copy2(facts_source, facts_target)
            record["image"] = str(image_target)
            record["facts"] = str(facts_target)
            records.append(record)

    receipt = {
        "schema": "interior.camera-delivery-index.v1",
        "modelBackend": "blender",
        "cameraPlan": str(plan_path),
        "executionMode": "isolated-process-per-shot",
        "records": records,
        "summary": {
            "requested": len(plan.get("shots", [])), "delivered": len(records),
            "failed": 0, "deliveryBlocked": False,
            "seconds": round(time.perf_counter() - started, 3),
        },
    }
    write(out / "camera-delivery-index.json", receipt)
    print(json.dumps(receipt["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
