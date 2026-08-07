#!/usr/bin/env python3
"""Validate circulation acceptance against the exact native model before camera work."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_circulation_gate.py circulation-result.json native-model-manifest.json")
    result_path = Path(sys.argv[1]).expanduser().resolve()
    manifest_path = Path(sys.argv[2]).expanduser().resolve()
    result = read_json(result_path)
    manifest = read_json(manifest_path)
    if result.get("schema") != "interior.circulation-result.v2":
        raise ValueError("circulation result schema must be interior.circulation-result.v2")
    if manifest.get("schema") != "interior.native-model-manifest.v1":
        raise ValueError("model manifest schema must be interior.native-model-manifest.v1")
    expected_digest = result.get("resultDigestSha256")
    unsigned = dict(result)
    unsigned.pop("resultDigestSha256", None)
    if expected_digest != canonical_sha256(unsigned):
        raise ValueError("circulation result canonical digest is invalid")
    verdict = result.get("verdict", {})
    classification = result.get("classification", {})
    if verdict.get("accepted") is not True or verdict.get("cameraWorkflowAllowed") is not True:
        raise ValueError("circulation result does not allow camera workflow")
    if verdict.get("structuralMutationPerformed") is not False:
        raise ValueError("circulation result does not preserve the frozen structure")
    if classification.get("layoutRegressionCount") != 0 or classification.get("inputIntegrityErrorCount") != 0:
        raise ValueError("circulation result still contains blocking errors")
    if classification.get("connectionEndpointFailureCount") != 0:
        raise ValueError("circulation result still contains connection endpoint failures")
    if classification.get("layoutRelationshipFailureCount") != 0:
        raise ValueError("circulation result still contains placement relationship failures")
    for key in ("topologyAuditDigestSha256", "layoutRelationshipAuditDigestSha256"):
        if not isinstance(result.get("bindings", {}).get(key), str) or len(result["bindings"][key]) != 64:
            raise ValueError(f"circulation result is missing {key}")
    if result.get("floorplanId") != manifest.get("floorplanId"):
        raise ValueError("circulation result and model manifest floorplanId differ")
    if result.get("modelBackend") != manifest.get("modelBackend"):
        raise ValueError("circulation result and model manifest backend differ")
    bindings = result.get("bindings", {})
    if bindings.get("handoffDigestSha256") != manifest.get("handoffDigestSha256"):
        raise ValueError("circulation result and model manifest handoff digest differ")
    native = manifest.get("nativeModel") or {}
    native_path_value = native.get("path") or manifest.get("nativeModelPath")
    expected_model_sha = native.get("sha256") or manifest.get("nativeModelSha256")
    if not native_path_value or not expected_model_sha:
        raise ValueError("model manifest is missing native model path or SHA-256")
    native_path = Path(native_path_value).expanduser().resolve()
    if not native_path.is_file() or file_sha256(native_path) != expected_model_sha:
        raise ValueError("native model file is missing or changed")
    if bindings.get("nativeModelSha256") != expected_model_sha:
        raise ValueError("circulation result is stale for the current native model")
    print(f"circulation gate accepted: {manifest['modelBackend']} {expected_model_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
