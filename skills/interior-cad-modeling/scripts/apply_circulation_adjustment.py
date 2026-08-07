#!/usr/bin/env python3
"""Append one digest-bound circulation correction to a native backend override ledger."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from common import canonical_sha256, read_json, write_json


BACKEND = "cad-step"
PLAN_SCHEMA = "interior.circulation-adjustment-plan.v2"
LEDGER_SCHEMA = "interior.native-layout-overrides.v1"


def close(left: Any, right: Any, tolerance: float = 1e-6) -> bool:
    return (
        isinstance(left, (int, float))
        and isinstance(right, (int, float))
        and math.isfinite(float(left))
        and math.isfinite(float(right))
        and abs(float(left) - float(right)) <= tolerance
    )


def same_position(left: Any, right: Any) -> bool:
    return (
        isinstance(left, list)
        and isinstance(right, list)
        and len(left) == len(right) == 2
        and all(close(value, right[index]) for index, value in enumerate(left))
    )


def operation_digest(operation: dict[str, Any]) -> str:
    target = operation.get("target", {})
    return canonical_sha256({
        "backend": str(operation.get("backend", "")),
        "operation": str(operation.get("operation", "")),
        "targetId": str(operation.get("targetEntityId") or operation.get("targetPlacementId") or ""),
        "position": [f"{float(value):.6f}" for value in target.get("position", [])],
        "rotationYRadians": f"{float(target.get('rotationYRadians', 0)):.9f}",
    })


def plan_execution_digest(plan: dict[str, Any]) -> str:
    return canonical_sha256({
        "schema": str(plan.get("schema", "")),
        "floorplanId": str(plan.get("floorplanId", "")),
        "modelBackend": str(plan.get("modelBackend", "")),
        "auditDigestSha256": str(plan.get("bindings", {}).get("auditDigestSha256", "")),
        "circulationSceneSha256": str(plan.get("bindings", {}).get("circulationSceneSha256", "")),
        "inputStateDigestSha256": str(plan.get("inputStateDigestSha256", "")),
        "workflowStatus": str(plan.get("workflowStatus", "")),
        "selectedCandidateId": str(plan.get("automaticDecision", {}).get("selectedCandidateId") or ""),
        "operationDigestSha256": str(plan.get("automaticDecision", {}).get("operationDigestSha256") or ""),
    })


def load_existing(path: Path | None, floorplan_id: str) -> dict[str, Any]:
    if path is None:
        return {
            "schema": LEDGER_SCHEMA,
            "floorplanId": floorplan_id,
            "modelBackend": BACKEND,
            "operations": [],
            "history": [],
        }
    data = read_json(path.resolve())
    declared = data.get("ledgerDigestSha256")
    payload = dict(data)
    payload.pop("ledgerDigestSha256", None)
    if (
        data.get("schema") != LEDGER_SCHEMA
        or data.get("floorplanId") != floorplan_id
        or data.get("modelBackend") != BACKEND
        or declared != canonical_sha256(payload)
    ):
        raise ValueError("existing native override ledger identity or digest mismatch")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--existing")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    plan_path = Path(args.plan).resolve()
    plan = read_json(plan_path)
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("modelBackend") != BACKEND
        or plan.get("workflowStatus") != "correction-ready"
        or plan.get("planDigestScope") != "bound-input-state-and-selected-operation-v1"
        or plan.get("planDigestSha256") != plan_execution_digest(plan)
    ):
        raise ValueError("circulation adjustment plan identity or digest mismatch")
    decision = plan.get("automaticDecision", {})
    if decision.get("action") != "apply-without-user-confirmation":
        raise ValueError("plan does not authorize an automatic reversible correction")
    candidate = next(
        (row for row in plan.get("candidates", []) if row.get("candidateId") == decision.get("selectedCandidateId")),
        None,
    )
    if candidate is None:
        raise ValueError("selected candidate is absent")
    operation = candidate.get("backendOperation", {})
    if (
        operation.get("backend") != BACKEND
        or operation.get("operation") != "set-native-entity-plan-transform"
        or candidate.get("operationDigestSha256") != decision.get("operationDigestSha256")
        or operation_digest(operation) != decision.get("operationDigestSha256")
    ):
        raise ValueError("selected native operation is invalid")
    target = operation.get("target", {})
    if (
        not same_position(target.get("position"), candidate.get("targetPlanCenter"))
        or not close(target.get("rotationYRadians"), candidate.get("targetRotationYRadians"), 1e-8)
    ):
        raise ValueError("candidate and backend target differ")

    ledger = load_existing(Path(args.existing) if args.existing else None, plan["floorplanId"])
    by_id = {row["entityId"]: row for row in ledger.get("operations", [])}
    entity_id = operation.get("targetEntityId")
    previous = by_id.get(entity_id)
    if previous is not None:
        if (
            not same_position(previous.get("target", {}).get("position"), candidate.get("previousPlanCenter"))
            or not close(
                previous.get("target", {}).get("rotationYRadians"),
                candidate.get("previousRotationYRadians"),
                1e-8,
            )
        ):
            raise ValueError("existing native override differs from the audited transform")
    changed_fields = []
    if not same_position(candidate.get("previousPlanCenter"), target["position"]):
        changed_fields.append("position")
    if not close(candidate.get("previousRotationYRadians"), target["rotationYRadians"], 1e-8):
        changed_fields.append("rotationY")
    if not changed_fields:
        raise ValueError("selected correction does not change the native entity")

    by_id[entity_id] = {
        "entityId": entity_id,
        "target": {
            "position": [float(value) for value in target["position"]],
            "rotationYRadians": float(target["rotationYRadians"]),
        },
        "reviewedAdjustment": {
            "schema": "interior.reviewed-layout-adjustment.v1",
            "authority": "circulation-deterministic-correction",
            "sourceAuditDigestSha256": plan["bindings"]["auditDigestSha256"],
            "adjustmentPlanDigestSha256": plan["planDigestSha256"],
            "candidateId": candidate["candidateId"],
            "operationDigestSha256": candidate["operationDigestSha256"],
            "reasonCode": candidate["correctionKind"],
            "changedFields": changed_fields,
            "previous": {
                "position": [float(value) for value in candidate["previousPlanCenter"]],
                "rotationY": float(candidate["previousRotationYRadians"]),
            },
            "active": {
                "position": [float(value) for value in target["position"]],
                "rotationY": float(target["rotationYRadians"]),
            },
        },
    }
    ledger["operations"] = [by_id[key] for key in sorted(by_id)]
    ledger.setdefault("history", []).append({
        "planPath": str(plan_path),
        "planDigestSha256": plan["planDigestSha256"],
        "candidateId": candidate["candidateId"],
        "operationDigestSha256": candidate["operationDigestSha256"],
        "confirmationRequested": False,
    })
    payload = dict(ledger)
    payload.pop("ledgerDigestSha256", None)
    ledger["ledgerDigestSha256"] = canonical_sha256(payload)
    out = Path(args.out).resolve()
    write_json(out, ledger)
    print(json.dumps({
        "accepted": True,
        "modelBackend": BACKEND,
        "output": str(out),
        "ledgerDigestSha256": ledger["ledgerDigestSha256"],
        "entityId": entity_id,
        "confirmationRequested": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

