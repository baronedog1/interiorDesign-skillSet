#!/usr/bin/env python3
"""Create a non-blocking circulation advisory from the current coauthoring model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any


PASSAGE_TYPES = {"door", "sliding", "open-passage", "passage", "opening"}


def canonical_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def wall_length(wall: dict[str, Any]) -> float:
    return math.hypot(wall["b"]["x"] - wall["a"]["x"], wall["b"]["z"] - wall["a"]["z"])


def opening_point(opening: dict[str, Any], wall: dict[str, Any]) -> tuple[float, float]:
    length = wall_length(wall) or 1.0
    ratio = float(opening.get("center", length / 2)) / length
    return (
        float(wall["a"]["x"]) + (float(wall["b"]["x"]) - float(wall["a"]["x"])) * ratio,
        float(wall["a"]["z"]) + (float(wall["b"]["z"]) - float(wall["a"]["z"])) * ratio,
    )


def furniture_radius(item: dict[str, Any]) -> float:
    return math.hypot(float(item.get("width", 0.6)), float(item.get("depth", 0.6))) / 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="model JSON extracted from the current HTML")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    model_path = Path(args.model).expanduser().resolve()
    model = json.loads(model_path.read_text(encoding="utf-8"))
    walls = {item["id"]: item for item in model.get("walls", [])}
    rooms = {item["id"]: item for item in model.get("rooms", [])}
    furniture = model.get("furniture", [])

    graph = {room_id: set() for room_id in rooms}
    entrances: set[str] = set()
    connection_rows = []
    warnings = []
    for opening in model.get("openings", []):
        if opening.get("type") not in PASSAGE_TYPES:
            continue
        wall = walls.get(opening.get("wallId"))
        if not wall:
            warnings.append({
                "code": "missing-opening-host-wall",
                "severity": "warning",
                "location": opening.get("name") or opening.get("id"),
                "message": "这个门或通道找不到对应墙体，请在 HTML 中检查；本次仍继续生成机位。",
            })
            continue
        endpoints = [value for value in wall.get("adjacentRoomIds", []) if value]
        internal = [value for value in endpoints if value in rooms]
        if "exterior" in endpoints:
            entrances.update(internal)
        if len(internal) >= 2:
            for left in internal:
                for right in internal:
                    if left != right:
                        graph[left].add(right)
        point = opening_point(opening, wall)
        connection_rows.append({
            "openingId": opening.get("id"),
            "type": opening.get("type"),
            "roomIds": internal,
            "worldPosition": {"x": round(point[0], 4), "z": round(point[1], 4)},
            "widthMeters": float(opening.get("width", 0)),
        })

        for item in furniture:
            if item.get("roomId") not in internal:
                continue
            distance = math.hypot(float(item.get("x", 0)) - point[0], float(item.get("z", 0)) - point[1])
            clearance = distance - furniture_radius(item)
            if clearance < 0.55:
                warnings.append({
                    "code": "opening-near-furniture",
                    "severity": "advisory",
                    "location": opening.get("name") or opening.get("id"),
                    "objectId": item.get("id"),
                    "objectName": item.get("name") or item.get("id"),
                    "clearanceMetersApprox": round(max(0.0, clearance), 3),
                    "message": f"{opening.get('name') or opening.get('id')} 附近的 {item.get('name') or item.get('id')} 可能压窄通道，请按实际使用习惯确认；不会改动用户布局。",
                })

    start_rooms = entrances or ({"entrance"} if "entrance" in rooms else ({next(iter(rooms))} if rooms else set()))
    reachable = set(start_rooms)
    queue = list(start_rooms)
    while queue:
        current = queue.pop(0)
        for neighbor in graph.get(current, set()):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)
    for room_id, room in rooms.items():
        if room_id not in reachable:
            warnings.append({
                "code": "room-topology-not-connected",
                "severity": "advisory",
                "location": room.get("name") or room_id,
                "roomId": room_id,
                "message": f"从入户拓扑暂时找不到通往 {room.get('name') or room_id} 的门或开放通道；请确认这是不是用户有意保留的布局。机位仍照常生成。",
            })

    deduped = []
    seen = set()
    for item in warnings:
        key = (item.get("code"), item.get("location"), item.get("objectId"), item.get("roomId"))
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    result = {
        "schema": "interior.circulation-result.v3",
        "schemaVersion": "3.1-advisory",
        "producer": {"skill": "interior-circulation-planning", "version": "6.0.0"},
        "floorplanId": model.get("meta", {}).get("sourceFloorplanId"),
        "checkpoint": "post-user-html",
        "modelBackend": "html-threejs",
        "sourceModel": str(model_path),
        "status": "accepted-with-layout-risks" if deduped else "accepted",
        "policy": {
            "mode": "user-layout-advisory-only",
            "blocking": False,
            "automaticMutation": False,
            "userLayoutPreserved": True,
            "cameraContinuesRegardlessOfFindings": True,
        },
        "topology": {
            "entranceRoomIds": sorted(start_rooms),
            "reachableRoomIds": sorted(reachable),
            "unreachableRoomIds": sorted(set(rooms) - reachable),
            "connections": connection_rows,
        },
        "riskNotices": deduped,
        "classification": {
            "layoutRiskCount": len(deduped),
            "inputIntegrityErrorCount": 0,
            "connectionEndpointFailureCount": 0,
        },
        "verdict": {
            "accepted": True,
            "blocking": False,
            "cameraWorkflowAllowed": True,
            "structuralMutationPerformed": False,
            "userLayoutPreserved": True,
        },
        "timingSeconds": round(time.perf_counter() - started, 6),
    }
    result["resultDigestSha256"] = canonical_sha(result)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "riskCount": len(deduped), "blocking": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
