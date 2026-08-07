#!/usr/bin/env python3
"""Compile non-overlapping stage events into exact additive timing."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from common import ContractError, load_json, object_hash, validate_schema, write_json


def parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"Invalid ISO-8601 timestamp for {label}: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{label} must include a timezone offset")
    return parsed


def iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds")


def build_timing(job_path: Path) -> dict[str, Any]:
    job = load_json(job_path)
    if job.get("schema") != "interior.cad-object-timing-events.v1":
        raise ContractError("Timing job schema must be interior.cad-object-timing-events.v1")
    task_id = job.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        raise ContractError("Timing job requires taskId")
    raw_stages = job.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ContractError("Timing job stages must be a non-empty array")
    seen: set[str] = set()
    stages: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    for raw in raw_stages:
        stage_id = raw.get("stageId")
        if not isinstance(stage_id, str) or not stage_id or stage_id in seen:
            raise ContractError(f"Invalid or duplicate stageId: {stage_id!r}")
        seen.add(stage_id)
        start = parse_time(raw.get("startedAt"), f"{stage_id}.startedAt")
        end = parse_time(raw.get("endedAt"), f"{stage_id}.endedAt")
        if end < start:
            raise ContractError(f"Stage ends before it starts: {stage_id}")
        if previous_end is not None and start < previous_end:
            raise ContractError(f"Stages overlap or are out of order at {stage_id}")
        previous_end = end
        activities = raw.get("activities")
        if not isinstance(activities, list) or not activities or any(not isinstance(item, str) or not item for item in activities):
            raise ContractError(f"Stage {stage_id} requires non-empty activities")
        duration_ms = round((end - start).total_seconds() * 1000)
        stages.append(
            {
                "stageId": stage_id,
                "name": str(raw.get("name", stage_id)),
                "startedAt": iso(start),
                "endedAt": iso(end),
                "durationMs": duration_ms,
                "activities": activities,
            }
        )
    total = sum(stage["durationMs"] for stage in stages)
    first = parse_time(stages[0]["startedAt"], "first.startedAt")
    last = parse_time(stages[-1]["endedAt"], "last.endedAt")
    wall = round((last - first).total_seconds() * 1000)
    gap = wall - total
    if gap < 0:
        raise ContractError("Stage total exceeds wall-clock duration")
    report: dict[str, Any] = {
        "schema": "interior.cad-object-stage-timing.v1",
        "taskId": task_id,
        "startedAt": stages[0]["startedAt"],
        "endedAt": stages[-1]["endedAt"],
        "stages": stages,
        "totalDurationMs": total,
        "wallClockDurationMs": wall,
        "unaccountedGapMs": gap,
        "timingHash": "",
    }
    report["timingHash"] = object_hash(report, "timingHash")
    validate_schema(report, "stage-timing.schema.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = build_timing(args.job.resolve())
        write_json(args.output.resolve(), report)
        print(f"stage timing passed: stages={len(report['stages'])} totalMs={report['totalDurationMs']}")
        return 0
    except ContractError as exc:
        print(f"stage timing failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
