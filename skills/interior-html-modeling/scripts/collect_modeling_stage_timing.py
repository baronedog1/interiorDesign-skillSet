#!/usr/bin/env python3
"""Report actual HTML modeling stage intervals from accepted project artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


STAGES = (
    ("handoff-import", "import_receipt"),
    ("asset-materialization", "asset_lock"),
    ("component-match-commit", "component_layout"),
    ("standalone-build", "standalone"),
    ("native-manifest", "native_manifest"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-start", required=True, help="ISO-8601 task/modeling start time")
    parser.add_argument("--import-receipt", required=True)
    parser.add_argument("--component-layout", required=True)
    parser.add_argument("--asset-lock", required=True)
    parser.add_argument("--standalone", required=True)
    parser.add_argument("--native-manifest", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def iso_timestamp(value: str) -> float:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def main() -> int:
    args = parse_args()
    task_started = iso_timestamp(args.task_start)
    previous = task_started
    stage_rows = []
    for stage, argument in STAGES:
        path = Path(getattr(args, argument)).resolve()
        if not path.is_file():
            raise SystemExit(f"missing {stage} artifact: {path}")
        completed = path.stat().st_mtime
        if completed < previous:
            raise SystemExit(f"non-monotonic artifact time at {stage}: {path}")
        stage_rows.append({
            "stage": stage,
            "completedAt": datetime.fromtimestamp(completed, timezone.utc).isoformat(),
            "durationMs": round((completed - previous) * 1000),
            "artifact": str(path),
        })
        previous = completed

    payload = {
        "schema": "interior.html-modeling-stage-timing.v1",
        "producer": {"skill": "interior-html-modeling", "version": "30.0.0"},
        "taskStartedAt": datetime.fromtimestamp(task_started, timezone.utc).isoformat(),
        "totalDurationMs": sum(row["durationMs"] for row in stage_rows),
        "stages": stage_rows,
        "interpretation": "Intervals include orchestration time between consecutive accepted artifacts; unrelated camera/rendering work is outside this report.",
    }
    target = Path(args.out).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(target), "totalDurationMs": payload["totalDurationMs"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
