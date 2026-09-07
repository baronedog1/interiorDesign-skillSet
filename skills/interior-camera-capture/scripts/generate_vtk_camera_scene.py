#!/usr/bin/env python3
"""Generate the sole solver scene from the current loaded HTML model.

There is deliberately only one input path: the current loaded HTML.  If native
HTML export and semantic identity do not agree, the run fails before camera
solving.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any


CAMERA_FIELDS = {
    "position", "target", "fov", "windowCenter", "referenceWallId",
    "algorithmEvidence", "frontalContract", "cameraMode", "placementTier",
}


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def room_kind(room: dict[str, Any]) -> str:
    value = str(room.get("spaceType", "unknown")).strip().lower()
    return value if value and value not in {"room", "space", "other"} else "unknown"


def semantic_item(item: dict[str, Any], native: dict[str, Any]) -> dict[str, Any]:
    width = float(item.get("width", item.get("originalDimensions", {}).get("width", 0.6)))
    depth = float(item.get("depth", item.get("originalDimensions", {}).get("depth", 0.6)))
    height = float(item.get("height", item.get("originalDimensions", {}).get("height", 0.8)))
    bottom = float(item.get("y", 0.0))
    return {
        "id": str(item["id"]),
        "name": str(item.get("name", item["id"])),
        "kind": "furniture",
        "roomId": str(item.get("roomId", "unknown")),
        "roomIds": [str(item.get("roomId", "unknown"))],
        "functionalClass": str(item.get("functionalClass", item.get("type", "unknown"))),
        "semantic": item.get("semantic"),
        "componentId": item.get("componentId"),
        "placementWorld": {
            "center": {
                "x": float(item.get("x", 0.0)),
                "y": bottom + height / 2.0,
                "z": float(item.get("z", 0.0)),
            },
            "dimensionsMeters": {"width": width, "height": height, "depth": depth},
            "rotationY": float(item.get("rotationY", 0.0)),
            "frame": "source-local-oriented-footprint",
        },
        "world": native["world"],
    }


def load_camera_intents(path: str | None, structure: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    value = load(path)
    if value.get("schema") != "interior.user-camera-intent.v1":
        raise SystemExit("camera intent must use interior.user-camera-intent.v1")
    if str(value.get("floorplanId", "")) != str(structure.get("floorplanId", "")):
        raise SystemExit("camera intent and structure belong to different floorplans")
    room_ids = {str(room.get("id")) for room in structure.get("rooms", [])}
    result: dict[str, dict[str, Any]] = {}
    for request in value.get("requests", []):
        room_id = str(request.get("roomId", ""))
        axis = request.get("desiredOpticalAxisXZ")
        if room_id not in room_ids or room_id in result:
            raise SystemExit(f"camera intent has invalid or duplicate roomId: {room_id}")
        if not isinstance(axis, list) or len(axis) != 2:
            raise SystemExit(f"camera intent for {room_id} requires desiredOpticalAxisXZ")
        x, z = float(axis[0]), float(axis[1])
        length = math.hypot(x, z)
        if not math.isfinite(length) or length < 1e-6:
            raise SystemExit(f"camera intent for {room_id} has an invalid optical axis")
        evidence = request.get("sourceEvidence")
        if not isinstance(evidence, dict) or not evidence.get("artifactPath") or not evidence.get("statement"):
            raise SystemExit(f"camera intent for {room_id} requires traceable sourceEvidence")
        eye_height = float(request.get("eyeHeightMeters", 1.5))
        preferred_fov = float(request.get("preferredFovDegrees", 50.0))
        if not 0.8 <= eye_height <= 2.2 or not 35.0 <= preferred_fov <= 120.0:
            raise SystemExit(f"camera intent for {room_id} has an invalid eye height or preferred FOV")
        result[room_id] = {
            "shotId": str(request.get("shotId", f"CAM-{room_id}")),
            "desiredOpticalAxisXZ": [x / length, z / length],
            "eyeHeightMeters": eye_height,
            "preferredFovDegrees": preferred_fov,
            "sourceEvidence": evidence,
        }
    return result


def build_semantic(
    model: dict[str, Any],
    structure: dict[str, Any],
    native: dict[str, Any],
    camera_intents: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    native_by_id = {str(row["id"]): row for row in native["entities"]}
    furniture = [semantic_item(item, native_by_id[str(item["id"])]) for item in model.get("furniture", [])]
    shots = []
    for sequence, room in enumerate(structure.get("rooms", []), 1):
        room_id = str(room["id"])
        inventory = [item for item in furniture if item["roomId"] == room_id]
        shot = {
            "semanticInventory": inventory,
            "roomName": str(room.get("name", room_id)),
            "sequenceOrder": sequence,
            "roomId": room_id,
            "roomKind": room_kind(room),
            "expectedRoomElementIds": [item["id"] for item in inventory],
            "composition": "subject-complete-space-envelope-frontal",
            "anchorElementIds": [],
            "shotId": f"{sequence:02d}-{room_id}",
            "compositionIntent": "完整展示该空间的主要功能主体及可理解的空间上下文",
        }
        if camera_intents and room_id in camera_intents:
            intent = camera_intents[room_id]
            shot["shotId"] = intent["shotId"]
            shot["userCameraIntent"] = intent
        shots.append(shot)
    result = {
        "schema": "interior.semantic-room-facts.v1",
        "schemaVersion": "1.0",
        "floorplanId": structure.get("floorplanId") or model.get("meta", {}).get("sourceFloorplanId"),
        "roomGeometry": [{
            "roomId": str(room["id"]),
            "roomName": room.get("name"),
            "roomKind": room_kind(room),
            "polygon": room.get("polygon", []),
        } for room in structure.get("rooms", [])],
        "shots": shots,
        "cameraFactsPresent": False,
        "forbiddenPoseFields": sorted(CAMERA_FIELDS),
    }
    return result


def scan_camera_fields(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in CAMERA_FIELDS:
                hits.append(f"{path}.{key}")
            hits.extend(scan_camera_fields(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(scan_camera_fields(child, f"{path}[{index}]"))
    return hits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--camera-intent")
    parser.add_argument("--node-bin", default=os.environ.get("NODE_BIN", "/home/agentops/agent-runtime/bin/node"))
    parser.add_argument("--chrome-bin", default=os.environ.get("CHROME_BIN", "/home/agentops/agent-runtime/bin/render-chrome"))
    args = parser.parse_args()
    html = Path(args.html).resolve()
    structure_path = Path(args.structure).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not html.is_file() or not structure_path.is_file():
        raise SystemExit("current HTML or structure-data.json is missing")
    exporter = Path(__file__).resolve().parent / "export_html_camera_scene.mjs"
    environment = os.environ.copy()
    environment["CHROME_BIN"] = args.chrome_bin
    subprocess.run([
        args.node_bin, str(exporter), "--html", str(html), "--out-dir", str(out)
    ], check=True, timeout=240, env=environment)

    model_path = out / "current-model-export.json"
    scene_path = out / "camera-semantic-scene.gltf"
    native_path = out / "native-scene-geometry.json"
    receipt_path = out / "html-camera-scene-export-receipt.json"
    for required in (model_path, scene_path, native_path, receipt_path):
        if not required.is_file():
            raise SystemExit(f"HTML native export missing: {required}")
    model, structure, native = load(model_path), load(structure_path), load(native_path)
    floorplan_html = str(model.get("meta", {}).get("sourceFloorplanId", ""))
    floorplan_structure = str(structure.get("floorplanId", ""))
    if not floorplan_html or floorplan_html != floorplan_structure:
        raise SystemExit(f"HTML/structure floorplan mismatch: {floorplan_html} != {floorplan_structure}")
    model_ids = [str(item["id"]) for item in model.get("furniture", [])]
    native_ids = [str(item["id"]) for item in native.get("entities", [])]
    if len(model_ids) != len(set(model_ids)) or len(native_ids) != len(set(native_ids)):
        raise SystemExit("duplicate furniture ID in current HTML or native scene")
    if set(model_ids) != set(native_ids):
        raise SystemExit(f"HTML/native entity mismatch: missing={sorted(set(model_ids)-set(native_ids))}, extra={sorted(set(native_ids)-set(model_ids))}")
    invalid_mesh = [row["id"] for row in native["entities"] if int(row.get("meshCount", 0)) < 1]
    if invalid_mesh:
        raise SystemExit(f"native HTML entities without mesh: {invalid_mesh}")
    camera_intents = load_camera_intents(args.camera_intent, structure)
    semantic = build_semantic(model, structure, native, camera_intents)
    forbidden = scan_camera_fields(semantic)
    if forbidden:
        raise SystemExit(f"semantic input contains camera facts: {forbidden}")
    semantic_path = out / "semantic-room-facts.json"
    write(semantic_path, semantic)
    receipt = {
        "schema": "interior.camera-scene-generation-receipt.v1",
        "status": "complete",
        "downstreamReady": True,
        "generator": "generate_vtk_camera_scene.py",
        "sourceHtml": {"path": str(html), "sha256": sha256(html)},
        "currentModel": {"path": str(model_path), "sha256": sha256(model_path)},
        "structure": {"path": str(structure_path), "sha256": sha256(structure_path)},
        "scene": {"path": str(scene_path), "sha256": sha256(scene_path)},
        "nativeGeometry": {"path": str(native_path), "sha256": sha256(native_path)},
        "semanticFacts": {"path": str(semantic_path), "sha256": sha256(semantic_path)},
        "cameraIntent": (
            {"path": str(Path(args.camera_intent).resolve()), "sha256": sha256(args.camera_intent)}
            if args.camera_intent else None
        ),
        "counts": {"rooms": len(structure.get("rooms", [])), "furniture": len(model_ids)},
    }
    final_receipt = out / "camera-scene-generation-receipt.json"
    write(final_receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
