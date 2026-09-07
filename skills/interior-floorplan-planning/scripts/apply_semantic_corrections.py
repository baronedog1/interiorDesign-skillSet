#!/usr/bin/env python3
"""Apply explicit user corrections to existing semantic candidates as a new revision."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


OPENING_CLASSES = {
    "door", "sliding-door", "open-passage", "glazing", "window", "not-opening"
}
BOUNDARY_CLASSES = {
    "railing", "parapet", "open-edge", "full-height-glazing", "not-boundary"
}
CORRECTION_AUTHORITIES = {
    "source-evidence-correction",
    "user-explicit-correction",
}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-evidence", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--corrections", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    evidence = read_json(Path(args.source_evidence).resolve())
    decisions = read_json(Path(args.decisions).resolve())
    corrections = read_json(Path(args.corrections).resolve())
    if corrections.get("schema") != "interior.semantic-correction-set.v1":
        raise ValueError("corrections must use interior.semantic-correction-set.v1")
    authority = corrections.get("authority")
    if authority not in CORRECTION_AUTHORITIES:
        raise ValueError(
            "authority must be source-evidence-correction or user-explicit-correction"
        )
    result = copy.deepcopy(decisions)
    receipts = []

    groups = (
        ("openings", "openingCandidates", OPENING_CLASSES),
        ("boundaries", "boundaryCandidates", BOUNDARY_CLASSES),
    )
    correction_count = 0
    for decision_key, evidence_key, allowed_classes in groups:
        rows = corrections.get(decision_key, [])
        if not isinstance(rows, list):
            raise ValueError(f"corrections.{decision_key} must be a list")
        candidates = {row.get("id"): row for row in evidence.get(evidence_key, [])}
        decision_by_id = {
            row.get("candidateId"): row for row in result.get(decision_key, [])
        }
        seen: set[str] = set()
        for correction in rows:
            candidate_id = correction.get("candidateId")
            classification = correction.get("classification")
            reason = str(correction.get("reason") or "").strip()
            evidence_types = correction.get("evidenceTypes") or [authority]
            if candidate_id in seen or candidate_id not in candidates:
                raise ValueError(
                    f"unknown or duplicate {decision_key} candidate: {candidate_id}"
                )
            if candidate_id not in decision_by_id:
                raise ValueError(
                    f"{decision_key} candidate has no semantic decision: {candidate_id}"
                )
            if classification not in allowed_classes or not reason:
                raise ValueError(
                    f"{candidate_id}: invalid classification or missing reason"
                )
            if not isinstance(evidence_types, list) or not evidence_types:
                raise ValueError(f"{candidate_id}: evidenceTypes must be non-empty")
            seen.add(candidate_id)
            target = decision_by_id[candidate_id]
            previous = target.get("classification")
            target["classification"] = classification
            target["reason"] = reason
            target["evidenceTypes"] = evidence_types
            target["correctionAuthority"] = {
                "schema": "interior.semantic-correction-authority.v2",
                "authority": authority,
                "instructionRef": corrections.get("instructionRef"),
                "previousClassification": previous,
                "correctionSetDigestSha256": canonical_digest(corrections),
            }
            for field in ("sourceLabelId", "height", "bottom"):
                if field in correction:
                    target[field] = correction[field]
            receipts.append({
                "candidateId": candidate_id,
                "previousClassification": previous,
                "classification": classification,
                "authority": authority,
            })
            correction_count += 1
    if correction_count == 0:
        raise ValueError("correction set must contain at least one correction")

    result["revisionCause"] = authority
    result["parentDecisionDigestSha256"] = canonical_digest(decisions)
    result["semanticCorrectionSetDigestSha256"] = canonical_digest(corrections)
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": "interior.semantic-correction-receipt.v1",
        "accepted": True,
        "corrections": receipts,
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
