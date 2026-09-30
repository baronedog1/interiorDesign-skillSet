#!/usr/bin/env python3
"""Resolve one Blender component move with swept AABB first-contact stopping."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


BACKEND = "blender"
UNIT = "m"
DEFAULT_STEP = 0.02


def vector(value, field):
    if not isinstance(value, list) or len(value) != 3 or not all(isinstance(item, (int, float)) and math.isfinite(item) for item in value):
        raise ValueError(f"{field} must contain three finite numbers")
    return [float(item) for item in value]


def overlaps(a_min, a_max, b_min, b_max, epsilon=1e-6):
    return all(a_max[index] > b_min[index] + epsilon and a_min[index] < b_max[index] - epsilon for index in range(3))


def moved(bounds, delta, factor):
    return (
        [bounds["min"][index] + delta[index] * factor for index in range(3)],
        [bounds["max"][index] + delta[index] * factor for index in range(3)],
    )


def colliders(bounds, delta, factor, obstacles):
    minimum, maximum = moved(bounds, delta, factor)
    return [
        obstacle["id"]
        for obstacle in obstacles
        if overlaps(minimum, maximum, obstacle["bounds"]["min"], obstacle["bounds"]["max"])
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    if request.get("schema") != "interior.native-component-motion.v1" or request.get("modelBackend") != BACKEND:
        raise ValueError("motion request backend/schema mismatch")
    bounds = request["startWorldBounds"]
    bounds["min"], bounds["max"] = vector(bounds.get("min"), "startWorldBounds.min"), vector(bounds.get("max"), "startWorldBounds.max")
    delta = vector(request.get("requestedDelta"), "requestedDelta")
    obstacles = request.get("obstacles")
    if not isinstance(obstacles, list):
        raise ValueError("obstacles must be a native-model-derived list")
    for obstacle in obstacles:
        obstacle["bounds"]["min"] = vector(obstacle["bounds"].get("min"), "obstacle.bounds.min")
        obstacle["bounds"]["max"] = vector(obstacle["bounds"].get("max"), "obstacle.bounds.max")
    if colliders(bounds, delta, 0, obstacles):
        raise ValueError("component starts in collision; repair source placement before moving")
    distance = math.sqrt(sum(value * value for value in delta))
    step = float(request.get("maxSweepStep", DEFAULT_STEP))
    samples = max(1, math.ceil(distance / step))
    safe, hit, hit_ids = 0.0, 1.0, []
    for index in range(1, samples + 1):
        factor = index / samples
        current = colliders(bounds, delta, factor, obstacles)
        if current:
            hit, hit_ids = factor, current
            break
        safe = factor
    else:
        safe = 1.0
    if safe < 1.0:
        for _ in range(24):
            middle = (safe + hit) / 2
            current = colliders(bounds, delta, middle, obstacles)
            if current:
                hit, hit_ids = middle, current
            else:
                safe = middle
    accepted_delta = [value * safe for value in delta]
    result = {
        "schema": "interior.native-component-motion-result.v1",
        "modelBackend": BACKEND,
        "sourceModelSha256": request["sourceModelSha256"],
        "componentId": request["componentId"],
        "unit": UNIT,
        "requestedDelta": delta,
        "acceptedDelta": accepted_delta,
        "acceptedFraction": safe,
        "stoppedAtFirstContact": safe < 1.0,
        "colliderIds": sorted(set(hit_ids)),
        "sweepStep": step,
    }
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
