#!/usr/bin/env python3
"""Shared contract helpers for the Blender floorplan backend."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


HANDOFF_SCHEMA = "interior.floorplan-handoff.v3"
STRUCTURE_SCHEMA = "interior.floorplan-structure.v3"
TRACE_SCHEMA = "interior.trace-components.v2"
SELECTION_SCHEMA = "interior.blender-asset-selection.v1"
CATALOG_SCHEMA = "interior.blender-component-catalog.v1"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(payload: dict[str, Any]) -> str:
    clean = {key: value for key, value in payload.items() if key != "handoffDigestSha256"}
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_layout_overrides(
    path: Path | None,
    *,
    backend: str,
    floorplan_id: str,
    entity_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    data = read_json(path.resolve())
    if (
        data.get("schema") != "interior.native-layout-overrides.v1"
        or data.get("modelBackend") != backend
        or data.get("floorplanId") != floorplan_id
    ):
        raise ValueError("native layout overrides identity mismatch")
    declared = data.get("ledgerDigestSha256")
    payload = dict(data)
    payload.pop("ledgerDigestSha256", None)
    if declared != canonical_sha256(payload):
        raise ValueError("native layout overrides digest mismatch")
    result: dict[str, dict[str, Any]] = {}
    for row in data.get("operations", []):
        entity_id = row.get("entityId")
        target = row.get("target", {})
        position = target.get("position")
        rotation = target.get("rotationYRadians")
        if (
            entity_id not in entity_ids
            or entity_id in result
            or not isinstance(position, list)
            or len(position) != 2
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in position)
            or not isinstance(rotation, (int, float))
            or not math.isfinite(rotation)
        ):
            raise ValueError("native layout override contains an invalid entity transform")
        result[entity_id] = row
    return result


def one_edit_or_equal(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    index = 0
    edits = 0
    for character in longer:
        if index < len(shorter) and shorter[index] == character:
            index += 1
        else:
            edits += 1
            if edits > 1:
                return False
    return True


def semantic_artifact_record(handoff: dict[str, Any], key: str) -> dict[str, Any]:
    candidates = [
        (candidate_key, value)
        for candidate_key, value in handoff.get("artifacts", {}).items()
        if one_edit_or_equal(str(candidate_key), key) and isinstance(value, dict)
    ]
    if not candidates:
        raise ValueError(
            f"未发现语义产物 {key}；请先询问用户是否已有该文件，并请求上传或提供实际路径"
        )
    digests = {json.dumps(value, sort_keys=True, separators=(",", ":")) for _, value in candidates}
    if len(digests) != 1:
        raise ValueError(f"{key} has conflicting semantic candidates; ask the user which artifact is authoritative")
    return next((value for candidate_key, value in candidates if candidate_key == key), candidates[0][1])


def resolve_artifact(handoff_path: Path, handoff: dict[str, Any], key: str) -> Path:
    record = semantic_artifact_record(handoff, key)
    relative = Path(str(record.get("path", "")))
    root = handoff_path.parent.resolve()
    if not relative.is_absolute() and ".." not in relative.parts:
        direct = (root / relative).resolve()
        if (
            (direct == root or root in direct.parents)
            and direct.is_file()
            and sha256(direct) == record.get("sha256")
            and direct.stat().st_size == record.get("bytes")
        ):
            return direct
    files = [candidate for candidate in root.rglob("*") if candidate.is_file()]
    if len(files) > 5000:
        raise ValueError("handoff search is too broad; provide the artifact path or a narrower workspace")
    matches = [
        candidate
        for candidate in files
        if candidate.stat().st_size == record.get("bytes") and sha256(candidate) == record.get("sha256")
    ]
    if not matches:
        raise ValueError(f"{key} 推荐路径不可用且未发现同哈希文件；请先询问用户是否有该文件")
    return sorted(matches, key=lambda candidate: (len(str(candidate)), str(candidate)))[0]


def load_handoff(handoff_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    handoff_path = handoff_path.resolve()
    handoff = read_json(handoff_path)
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise ValueError(f"handoff schema must be {HANDOFF_SCHEMA}")
    if handoff.get("producer", {}).get("skill") != "interior-floorplan-planning":
        raise ValueError("handoff producer must be interior-floorplan-planning")
    if not str(handoff.get("producer", {}).get("version", "")).startswith("6."):
        raise ValueError("handoff producer must be a schema-compatible floorplan 6.x release")
    if not all(handoff.get("validation", {}).get(key) is True for key in ("sourceModel", "agentVisualReview")):
        raise ValueError("handoff validation is not accepted")
    if handoff.get("handoffDigestSha256") != canonical_digest(handoff):
        raise ValueError("handoffDigestSha256 mismatch")
    structure = read_json(resolve_artifact(handoff_path, handoff, "structureData"))
    traces = read_json(resolve_artifact(handoff_path, handoff, "traceComponents"))
    if structure.get("schema") != STRUCTURE_SCHEMA:
        raise ValueError(f"structure schema must be {STRUCTURE_SCHEMA}")
    if traces.get("schema") != TRACE_SCHEMA:
        raise ValueError(f"trace component schema must be {TRACE_SCHEMA}")
    if not handoff.get("floorplanId") or handoff["floorplanId"] != structure.get("floorplanId"):
        raise ValueError("handoff and structure floorplanId differ")
    if handoff["floorplanId"] != traces.get("floorplanId"):
        raise ValueError("handoff and trace component floorplanId differ")
    return handoff, structure, traces


def source_object_index(traces: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in traces.get("objects", []):
        source_id = row.get("sourceObjectCandidateId")
        if not source_id or source_id in result:
            raise ValueError("trace components require unique sourceObjectCandidateId values")
        result[source_id] = row
    if not result:
        raise ValueError("trace components contain no accepted objects")
    return result


def blender_transform(structure: dict[str, Any]) -> dict[str, Any]:
    coordinate = structure.get("coordinateSystem", {})
    width = float(coordinate["realWidthMeters"])
    depth = float(coordinate["realDepthMeters"])
    return {
        "source": {"origin": "north-west", "axes": {"x": "east", "y": "south", "z": "up"}},
        "target": {"origin": "floorplan-center", "axes": {"x": "east", "y": "north", "z": "up"}},
        "matrix4x4": [
            [1, 0, 0, -width / 2],
            [0, -1, 0, depth / 2],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ],
        "inverseMatrix4x4": [
            [1, 0, 0, width / 2],
            [0, -1, 0, depth / 2],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ],
        "controlPoints": [
            {"source": [0, 0, 0], "target": [-width / 2, depth / 2, 0]},
            {"source": [width, 0, 0], "target": [width / 2, depth / 2, 0]},
            {"source": [width, depth, 0], "target": [width / 2, -depth / 2, 0]},
            {"source": [0, depth, 0], "target": [-width / 2, -depth / 2, 0]},
            {"source": [width / 2, depth / 2, 0], "target": [0, 0, 0]},
        ],
    }


def to_blender_xy(structure: dict[str, Any], point: list[float]) -> tuple[float, float]:
    coordinate = structure["coordinateSystem"]
    return (
        float(point[0]) - float(coordinate["realWidthMeters"]) / 2,
        float(coordinate["realDepthMeters"]) / 2 - float(point[1]),
    )
