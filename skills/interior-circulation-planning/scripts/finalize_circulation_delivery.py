#!/usr/bin/env python3
"""Bind deterministic circulation results to an Agent visual comparison review."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import canonical_sha256, read_json, require_schema, sha256_file, write_json


AUDIT_SCHEMA = "interior.circulation-audit.v2"
REVIEW_SCHEMA = "interior.circulation-agent-review.v2"
RESULT_SCHEMA = "interior.circulation-result.v2"


def verify_canonical_digest(document: dict[str, Any], key: str, label: str) -> str:
    expected = document.get(key)
    payload = dict(document)
    payload.pop(key, None)
    actual = canonical_sha256(payload)
    if expected != actual:
        raise ValueError(f"{label} canonical digest is invalid")
    return actual


def verify_evidence(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    required = {"source-floorplan", "floorplan-overlay", "native-model-top-view", "circulation-overlay"}
    evidence_by_role: dict[str, dict[str, Any]] = {}
    for item in review.get("evidence", []):
        role = item.get("role")
        path_value = item.get("path")
        expected = item.get("sha256")
        if not role or not path_value or not expected:
            raise ValueError("each visual review evidence item requires role, path, and sha256")
        path = Path(path_value).expanduser().resolve()
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"visual review evidence is missing or changed: {role}")
        if role in evidence_by_role:
            raise ValueError(f"duplicate visual review evidence role: {role}")
        evidence_by_role[role] = {**item, "path": str(path)}
    missing = required - set(evidence_by_role)
    if missing:
        raise ValueError(f"visual review is missing evidence roles: {sorted(missing)}")
    return evidence_by_role


def exact_id_set(actual: Any, expected: set[str], label: str) -> None:
    if not isinstance(actual, list) or len(actual) != len(set(actual)):
        raise ValueError(f"{label} must be one duplicate-free list")
    if set(actual) != expected:
        raise ValueError(f"{label} must enumerate the computed set exactly")


def relationship_key(row: dict[str, Any]) -> str:
    return "::".join(
        str(row.get(key, "")) for key in ("ruleId", "sourceId", "targetId", "wallId")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--agent-review", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    audit_path = Path(args.audit).expanduser().resolve()
    review_path = Path(args.agent_review).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    audit = read_json(audit_path)
    review = read_json(review_path)
    require_schema(audit, AUDIT_SCHEMA, "circulation audit")
    require_schema(review, REVIEW_SCHEMA, "Agent visual review")
    verify_canonical_digest(audit, "auditDigestSha256", "circulation audit")
    if review.get("floorplanId") != audit.get("floorplanId"):
        raise ValueError("Agent review and audit floorplanId differ")
    if review.get("bindings", {}).get("circulationAuditSha256") != sha256_file(audit_path):
        raise ValueError("Agent review is not bound to the supplied circulation audit")
    if review.get("bindings", {}).get("auditDigestSha256") != audit.get("auditDigestSha256"):
        raise ValueError("Agent review audit digest differs")
    for key in ("sourceImageSha256", "floorplanHandoffSha256", "nativeModelSha256"):
        if review.get("bindings", {}).get(key) != audit.get("bindings", {}).get(key):
            raise ValueError(f"Agent review binding differs from the audit: {key}")
    verify_evidence(review)

    scene_path = Path(audit.get("bindings", {}).get("circulationScenePath", "")).expanduser().resolve()
    if not scene_path.is_file() or sha256_file(scene_path) != audit.get("bindings", {}).get("circulationSceneSha256"):
        raise ValueError("circulation audit does not bind one readable circulation scene")
    scene = read_json(scene_path)
    expected_routes = {route["id"] for route in audit.get("routes", [])}
    expected_rooms = {
        row["roomId"]
        for row in audit.get("topologyAudit", {}).get("roomOpenings", [])
    }
    expected_connections = {
        row["connectionId"]
        for row in audit.get("topologyAudit", {}).get("connectionEndpointAudit", [])
    }
    expected_objects = {row["id"] for row in scene.get("components", [])}
    expected_relationships = {
        relationship_key(row)
        for row in audit.get("layoutRelationshipAudit", {}).get("results", [])
    }
    exact_id_set(review.get("reviewedRoomIds"), expected_rooms, "reviewedRoomIds")
    exact_id_set(review.get("reviewedConnectionIds"), expected_connections, "reviewedConnectionIds")
    exact_id_set(review.get("reviewedAtomicObjectIds"), expected_objects, "reviewedAtomicObjectIds")
    exact_id_set(review.get("reviewedLayoutRelationshipKeys"), expected_relationships, "reviewedLayoutRelationshipKeys")
    exact_id_set(review.get("reviewedRouteIds"), expected_routes, "reviewedRouteIds")
    if not isinstance(review.get("findings"), list):
        raise ValueError("Agent review findings must be an explicit list")
    if review.get("decision") != "accept":
        raise ValueError("Agent review decision is not accept")

    audit_status = audit.get("verdict", {}).get("status")
    if audit_status not in {"accepted", "accepted-with-source-constraints"}:
        raise ValueError(f"cannot finalize circulation result while audit status is {audit_status!r}")
    if audit.get("counts", {}).get("layoutErrors") != 0 or audit.get("counts", {}).get("integrityErrors") != 0:
        raise ValueError("cannot finalize while layout or integrity errors remain")
    if audit.get("counts", {}).get("connectionEndpointFailures") != 0:
        raise ValueError("cannot finalize while independently derived connection endpoints fail")
    if audit.get("counts", {}).get("layoutRelationshipFailures") != 0:
        raise ValueError("cannot finalize while required placement relationships fail")

    topology_digest = canonical_sha256(audit.get("topologyAudit", {}))
    relationship_digest = canonical_sha256(audit.get("layoutRelationshipAudit", {}))

    result = {
        "schema": RESULT_SCHEMA,
        "producer": {"skill": "interior-circulation-planning", "version": "3.1.0"},
        "floorplanId": audit["floorplanId"],
        "modelBackend": audit["modelBackend"],
        "bindings": {
            **audit["bindings"],
            "circulationAuditPath": str(audit_path),
            "circulationAuditSha256": sha256_file(audit_path),
            "auditDigestSha256": audit["auditDigestSha256"],
            "topologyAuditDigestSha256": topology_digest,
            "layoutRelationshipAuditDigestSha256": relationship_digest,
            "agentReviewPath": str(review_path),
            "agentReviewSha256": sha256_file(review_path),
        },
        "classification": {
            "sourceConstraintCount": audit.get("counts", {}).get("sourceWarnings", 0),
            "layoutRegressionCount": 0,
            "inputIntegrityErrorCount": 0,
            "roomAreaGateCount": 0,
            "connectionEndpointFailureCount": 0,
            "layoutRelationshipFailureCount": 0,
        },
        "verdict": {
            "status": audit_status,
            "accepted": True,
            "cameraWorkflowAllowed": True,
            "sourceConstraintsDisclosed": audit_status == "accepted-with-source-constraints",
            "structuralMutationPerformed": False,
        },
        "next": {
            "skill": "interior-camera-capture",
            "requireSameNativeModelSha256": audit["bindings"]["nativeModelSha256"],
        },
    }
    result["resultDigestSha256"] = canonical_sha256(result)
    write_json(out_path, result)
    print(f"circulation result finalized: {audit_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
