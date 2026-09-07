#!/usr/bin/env python3
"""Compile one accepted deterministic circulation audit into the downstream result."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import canonical_sha256, read_json, require_schema, sha256_file, write_json


AUDIT_SCHEMA = "interior.circulation-audit.v3"
RESULT_SCHEMA = "interior.circulation-result.v3"


def verify_canonical_digest(document: dict[str, Any], key: str, label: str) -> str:
    expected = document.get(key)
    payload = dict(document)
    payload.pop(key, None)
    actual = canonical_sha256(payload)
    if expected != actual:
        raise ValueError(f"{label} canonical digest is invalid")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    audit_path = Path(args.audit).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    audit = read_json(audit_path)
    require_schema(audit, AUDIT_SCHEMA, "circulation audit")
    verify_canonical_digest(audit, "auditDigestSha256", "circulation audit")

    checkpoint = audit.get("checkpoint")
    if checkpoint not in {"post-floorplan", "post-model"}:
        raise ValueError("circulation audit has an invalid checkpoint")
    scene_path = Path(audit.get("bindings", {}).get("circulationScenePath", "")).expanduser().resolve()
    if not scene_path.is_file() or sha256_file(scene_path) != audit.get("bindings", {}).get("circulationSceneSha256"):
        raise ValueError("circulation audit does not bind one readable circulation scene")

    audit_status = audit.get("verdict", {}).get("status")
    accepted_statuses = {
        "accepted",
        "accepted-with-source-constraints",
        "accepted-with-layout-risks",
    }
    if audit_status not in accepted_statuses:
        raise ValueError(f"cannot finalize circulation result while audit status is {audit_status!r}")
    if audit.get("counts", {}).get("integrityErrors") != 0:
        raise ValueError("cannot finalize while input integrity errors remain")
    if audit.get("counts", {}).get("connectionEndpointFailures") != 0:
        raise ValueError("cannot finalize while independently derived connection endpoints fail")

    topology_digest = canonical_sha256(audit.get("topologyAudit", {}))
    relationship_digest = canonical_sha256(audit.get("layoutRelationshipAudit", {}))
    result = {
        "schema": RESULT_SCHEMA,
        "producer": {"skill": "interior-circulation-planning", "version": "5.2.0"},
        "floorplanId": audit["floorplanId"],
        "checkpoint": checkpoint,
        "modelBackend": audit["modelBackend"],
        "bindings": {
            **audit["bindings"],
            "circulationAuditPath": str(audit_path),
            "circulationAuditSha256": sha256_file(audit_path),
            "auditDigestSha256": audit["auditDigestSha256"],
            "topologyAuditDigestSha256": topology_digest,
            "layoutRelationshipAuditDigestSha256": relationship_digest,
        },
        "classification": {
            "sourceConstraintCount": audit.get("counts", {}).get("sourceWarnings", 0),
            "layoutRegressionCount": audit.get("counts", {}).get("layoutRegressionRoutes", 0),
            "layoutRiskCount": audit.get("riskSummary", {}).get("issueCount", 0),
            "inputIntegrityErrorCount": 0,
            "roomAreaGateCount": 0,
            "connectionEndpointFailureCount": 0,
            "layoutRelationshipFailureCount": audit.get("counts", {}).get("layoutRelationshipFailures", 0),
        },
        "riskSummary": audit.get("riskSummary", {
            "status": "no-layout-risk",
            "blocking": False,
            "issueCount": 0,
            "notices": [],
            "userMessage": "未发现由当前家具布局新增的动线风险。",
        }),
        "sourceConstraintSummary": audit.get("sourceConstraintSummary", {
            "status": "no-source-constraint",
            "blocking": False,
            "issueCount": 0,
            "notices": [],
            "userMessage": "未发现需要提示的原户型固有通行限制。",
        }),
        "verdict": {
            "status": audit_status,
            "accepted": True,
            "cameraWorkflowAllowed": checkpoint == "post-model",
            "modelingWorkflowAllowed": checkpoint == "post-floorplan",
            "sourceConstraintsDisclosed": audit.get("counts", {}).get("sourceWarnings", 0) > 0,
            "layoutRisksDisclosed": audit_status == "accepted-with-layout-risks",
            "layoutRisksAreAdvisory": True,
            "structuralMutationPerformed": False,
            "method": "deterministic-bound-audit-v3",
        },
        "next": (
            {
                "skill": "interior-html-modeling",
                "requireSameHandoffDigestSha256": audit["bindings"].get("handoffDigestSha256"),
            }
            if checkpoint == "post-floorplan"
            else {
                "skill": "interior-camera-capture",
                "requireSameNativeModelSha256": audit["bindings"]["nativeModelSha256"],
            }
        ),
    }
    result["resultDigestSha256"] = canonical_sha256(result)
    write_json(out_path, result)
    print(f"circulation result finalized: {audit_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
