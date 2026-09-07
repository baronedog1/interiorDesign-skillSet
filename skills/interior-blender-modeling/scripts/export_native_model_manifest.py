#!/usr/bin/env python3
"""Export a backend-neutral model manifest from an accepted Blender build report."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import read_json, sha256, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = read_json(Path(args.report).resolve())
    if report.get("schema") != "interior.blender-build-report.v5" or report.get("accepted") is not True:
        raise SystemExit("Blender build report is not accepted")
    native = Path(report["nativeModelPath"]).resolve()
    if not native.is_file() or sha256(native) != report.get("nativeModelSha256"):
        raise SystemExit("native .blend hash mismatch")
    payload = {
        "schema": "interior.native-model-manifest.v1",
        "modelBackend": "blender",
        "floorplanId": report["floorplanId"],
        "sourceHtmlModelSha256": report["sourceHtmlModel"]["sha256"],
        "nativeModel": {"path": str(native), "sha256": report["nativeModelSha256"], "format": "blend", "runtimeVersion": report["blenderVersion"]},
        "derivedModels": [{"path": report["derivedGlbPath"], "sha256": report["derivedGlbSha256"], "format": "glb"}],
        "coordinateTransform": report["coordinateTransform"],
        "collections": report["collections"],
        "counts": report["counts"],
        "capabilities": {
            "raycast": True,
            "depth": True,
            "entityId": True,
            "visibilityStates": True,
            "nativeCameraRender": True,
            "semanticProjection": True,
            "projectionProfile": "blender-native-object-index-depth-room-v1",
        },
        "captureAdapter": {"runtime": "blender-background", "script": str(Path(args.adapter).resolve()), "interface": "interior.native-capture-adapter.v2"},
        "validation": {
            "accepted": True,
            "primitiveFurnitureFallbackCount": report.get("primitiveFurnitureFallbackCount"),
            "unmatchedFurnitureCount": report.get("unmatchedFurnitureCount"),
        },
        "sourceHashes": {
            "currentHtmlModel": report["sourceHtmlModel"]["sha256"],
            "structure": report["structure"]["sha256"],
            "blenderCatalog": report["blenderCatalog"]["sha256"],
            "materialCatalog": report["materialCatalog"]["sha256"],
            "stylePreset": report["stylePreset"]["sha256"],
        },
    }
    write_json(Path(args.out).resolve(), payload)
    print("native Blender model manifest accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
