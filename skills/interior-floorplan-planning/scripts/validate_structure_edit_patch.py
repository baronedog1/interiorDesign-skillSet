#!/usr/bin/env python3
"""Validate backend-authored collinear wall edits before a new handoff revision."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


TOLERANCE = 1e-6


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def vector(value, field):
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(item, (int, float)) and math.isfinite(item) for item in value):
        raise ValueError(f"{field} must be a two-number point")
    return tuple(float(item) for item in value)


def close_point(left, right):
    return math.dist(left, right) <= TOLERANCE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structure", required=True)
    parser.add_argument("--patch-set", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    structure = read(Path(args.structure).resolve())
    patch_set = read(Path(args.patch_set).resolve())
    if structure.get("schema") not in {
        "interior.floorplan-structure.v3",
        "interior.floorplan-structure.v4",
    }:
        raise ValueError("structure must be interior.floorplan-structure.v3 or v4")
    if patch_set.get("schema") != "interior.structure-edit-patch-set.v1":
        raise ValueError("patch set schema mismatch")
    if patch_set.get("floorplanId") != structure.get("floorplanId"):
        raise ValueError("patch set and structure belong to different floorplans")
    if patch_set.get("backend") not in {"html-threejs", "blender", "cad-step"}:
        raise ValueError("unsupported patch authoring backend")
    walls = {wall["id"]: wall for wall in structure.get("walls", [])}
    windows_by_wall = {}
    for window in structure.get("windows", []):
        windows_by_wall.setdefault(window["wallId"], []).append(window)
    seen = set()
    audits = []
    for patch in patch_set.get("patches", []):
        wall_id = patch.get("entityId")
        if wall_id in seen or wall_id not in walls:
            raise ValueError(f"unknown or duplicate patched wall: {wall_id}")
        seen.add(wall_id)
        if patch.get("schema") != "interior.structure-edit-patch.v1" or patch.get("entityType") != "wall" or patch.get("operation") != "extend-collinear-endpoints":
            raise ValueError(f"{wall_id}: unsupported patch operation")
        wall = walls[wall_id]
        source_start, source_end = vector(wall["start"], "wall.start"), vector(wall["end"], "wall.end")
        if not close_point(vector(patch["source"]["start"], "patch.source.start"), source_start) or not close_point(vector(patch["source"]["end"], "patch.source.end"), source_end):
            raise ValueError(f"{wall_id}: patch source differs from accepted structure")
        dx, dy = source_end[0] - source_start[0], source_end[1] - source_start[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        start_extension = float(patch["extensionMeters"]["start"])
        end_extension = float(patch["extensionMeters"]["end"])
        expected_start = (source_start[0] - ux * start_extension, source_start[1] - uy * start_extension)
        expected_end = (source_end[0] + ux * end_extension, source_end[1] + uy * end_extension)
        current_start = vector(patch["current"]["start"], "patch.current.start")
        current_end = vector(patch["current"]["end"], "patch.current.end")
        if not close_point(current_start, expected_start) or not close_point(current_end, expected_end):
            raise ValueError(f"{wall_id}: current endpoints are not the declared collinear extension")
        new_length = length + start_extension + end_extension
        if new_length < 0.1:
            raise ValueError(f"{wall_id}: edited wall would be shorter than 0.1m")
        hosted = windows_by_wall.get(wall_id, [])
        for window in hosted:
            shifted_offset = float(window["offset"]) + start_extension
            if shifted_offset < -TOLERANCE or shifted_offset + float(window["width"]) > new_length + TOLERANCE:
                raise ValueError(f"{wall_id}: edited endpoint would pass hosted window {window['id']}")
        audits.append({
            "wallId": wall_id,
            "sourceLengthMeters": length,
            "candidateLengthMeters": new_length,
            "hostedOpeningIds": [window["id"] for window in hosted],
            "collinear": True,
            "hostedOpeningsRemainOnWall": True,
        })
    if not audits:
        raise ValueError("patch set contains no wall patches")
    result = {
        "schema": "interior.structure-edit-patch-validation.v1",
        "acceptedAsRevisionCandidate": True,
        "acceptedAsCurrentHandoffMutation": False,
        "requiresNewFloorplanRevision": True,
        "floorplanId": structure["floorplanId"],
        "authoringBackend": patch_set["backend"],
        "patches": audits,
        "nextStep": "recompile room topology, openings, structure data and handoff before native-model acceptance",
    }
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
