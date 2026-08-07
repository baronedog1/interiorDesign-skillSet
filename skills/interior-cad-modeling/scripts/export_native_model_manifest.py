#!/usr/bin/env python3
"""Export a backend-neutral native model manifest for an accepted CAD build."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import read_json, sha256, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--semantic-topology", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = read_json(Path(args.report).resolve())
    if report.get("schema") != "interior.cad-build-report.v1" or report.get("accepted") is not True:
        raise SystemExit("CAD build report is not accepted")
    model = Path(report["nativeModelPath"]).resolve()
    entity_index = Path(report["entityIndexPath"]).resolve()
    semantic_topology = Path(args.semantic_topology).resolve()
    if not model.is_file() or sha256(model) != report.get("nativeModelSha256"):
        raise SystemExit("STEP file/hash mismatch")
    if not entity_index.is_file() or sha256(entity_index) != report.get("entityIndexSha256"):
        raise SystemExit("CAD entity index hash mismatch")
    if not semantic_topology.is_file() or semantic_topology.suffix.lower() != ".glb":
        raise SystemExit("STEP-derived semantic topology GLB is missing")
    payload = {
        "schema": "interior.native-model-manifest.v1",
        "modelBackend": "cad-step",
        "floorplanId": report["floorplanId"],
        "handoffDigestSha256": report["handoffDigestSha256"],
        "nativeModel": {"path": str(model), "sha256": report["nativeModelSha256"], "format": "step", "runtimeVersion": report["runtime"]},
        "derivedModels": report.get("derivedModels", []),
        "coordinateTransform": report["coordinateTransform"],
        "collections": report["groups"],
        "counts": report["counts"],
        "entityIndex": {"path": str(entity_index), "sha256": report["entityIndexSha256"], "schema": "interior.cad-entity-index.v1"},
        "semanticTopology": {"path": str(semantic_topology), "sha256": sha256(semantic_topology), "format": "step-derived-occurrence-glb"},
        "capabilities": {
            "raycast": False,
            "depth": False,
            "entityId": False,
            "visibilityStates": True,
            "nativeCameraRender": True,
            "projectionProfile": "cad-same-brep-topology-zbuffer-v1",
            "semanticProjection": True,
        },
        "captureAdapter": {"runtime": "cad-snapshot-renderer", "script": str(Path(args.adapter).resolve()), "interface": "interior.native-capture-adapter.v1"},
        "license": {"usageContext": report.get("usageContext"), "redistributionAllowed": report.get("redistributionAllowed")},
        "validation": {"accepted": True, "primitiveFurnitureFallbackCount": report.get("primitiveFurnitureFallbackCount")},
        "sourceHashes": {"selection": report["selectionSha256"], "catalog": report["catalogSha256"], "backendOptions": report["backendOptionsSha256"]},
        "sourceArtifacts": report.get("sourceArtifacts", {}),
    }
    write_json(Path(args.out).resolve(), payload)
    print("native CAD model manifest accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
