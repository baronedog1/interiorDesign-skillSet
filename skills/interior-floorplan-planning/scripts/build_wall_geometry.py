#!/usr/bin/env python3
"""Build wall bands only from frozen source-evidence face pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evidence_path = Path(args.evidence).resolve()
    decisions_path = Path(args.decisions).resolve()
    output_path = Path(args.output).resolve()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if decisions.get("evidenceSha256") != digest(evidence_path):
        raise ValueError("decisions do not reference the current evidence ledger")
    candidates = {item["id"]: item for item in evidence["wallCandidates"]}
    walls = []
    for row in decisions["candidates"]:
        if row["classification"] not in {"wall", "occluded-wall"}:
            continue
        candidate = candidates[row["candidateId"]]
        face_a = candidate["faceA"]
        face_b = candidate["faceB"]
        if len(face_a) != 2 or len(face_b) != 2:
            raise ValueError(f"{candidate['id']}: paired faces must each contain two points")
        walls.append(
            {
                "id": f"wall-{candidate['id'].removeprefix('candidate-')}",
                "candidateId": candidate["id"],
                "type": "polygon",
                "points": [face_a[0], face_a[1], face_b[1], face_b[0]],
                "wallBand": True,
                "strokeOnly": True,
                "color": "#ef233c",
                **({"shortWall": True} if candidate.get("shortWall") is True else {}),
            }
        )
    payload = {
        "schema": "interior.floorplan-wall-geometry.v1",
        "sourceSha256": evidence["sourceSha256"],
        "evidenceSha256": digest(evidence_path),
        "decisionsSha256": digest(decisions_path),
        "walls": walls,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
