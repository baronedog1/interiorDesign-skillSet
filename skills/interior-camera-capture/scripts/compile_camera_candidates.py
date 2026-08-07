#!/usr/bin/env python3
"""Compile every frontal seed into deterministic camera candidates in one pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SEED_SCHEMA = "interior.camera-frontal-seed-set.v1"
MEASUREMENT_SCHEMA = "interior.native-camera-envelope-measurements.v1"
OUTPUT_SCHEMA = "interior.camera-candidate-batch.v1"
METHOD_VERSION = "deterministic-wall-normal-camera-v7"
PRODUCER_VERSION = "20.0.0"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_document_digest(document: dict[str, Any], field: str, label: str) -> str:
    unsigned = dict(document)
    declared = unsigned.pop(field, None)
    actual = canonical_sha256(unsigned)
    if declared != actual:
        raise ValueError(f"{label} {field} is invalid")
    return actual


def positive_number(value: Any, label: str, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{label} must be {'non-negative' if allow_zero else 'positive'}")
    return number


def validate_envelope(
    row: dict[str, Any],
    name: str,
    expected_ids: list[str],
    *,
    allow_empty: bool = False,
) -> dict[str, Any]:
    envelope = row.get(name)
    if not isinstance(envelope, dict):
        raise ValueError(f"{row.get('seedId')}: missing {name}")
    element_ids = envelope.get("elementIds")
    if not isinstance(element_ids, list) or sorted(element_ids) != sorted(expected_ids):
        raise ValueError(f"{row.get('seedId')}: {name} element IDs differ from the seed")
    if not allow_empty and not element_ids:
        raise ValueError(f"{row.get('seedId')}: {name} cannot be empty")
    width = positive_number(envelope.get("widthMeters"), f"{name}.widthMeters", allow_zero=allow_empty)
    height = positive_number(envelope.get("heightMeters"), f"{name}.heightMeters", allow_zero=allow_empty)
    depth = positive_number(envelope.get("depthMeters", 0), f"{name}.depthMeters", allow_zero=True)
    if element_ids and (width == 0 or height == 0):
        raise ValueError(f"{row.get('seedId')}: non-empty {name} needs positive width and height")
    return {
        "widthMeters": width,
        "heightMeters": height,
        "depthMeters": depth,
        "elementIds": element_ids,
    }


def prefixed_candidate_id(room_id: str, candidate_id: str) -> str:
    suffix = candidate_id.removeprefix("one-point-frontal-")
    return f"{room_id}-{suffix}"


def compile_batch(seed_path: Path, measurement_path: Path) -> dict[str, Any]:
    seeds = load(seed_path)
    measurements = load(measurement_path)
    if seeds.get("schema") != SEED_SCHEMA:
        raise ValueError(f"seed set must use {SEED_SCHEMA}")
    if measurements.get("schema") != MEASUREMENT_SCHEMA:
        raise ValueError(f"measurements must use {MEASUREMENT_SCHEMA}")
    seed_digest = verify_document_digest(seeds, "seedSetDigestSha256", "seed set")
    measurement_digest = verify_document_digest(
        measurements, "measurementDigestSha256", "measurements"
    )
    if seeds.get("methodVersion") != METHOD_VERSION:
        raise ValueError("seed set uses the wrong camera algorithm")
    if seeds.get("algorithm", {}).get("status") != "ready":
        raise ValueError("seed set is not ready")
    if measurements.get("seedSetDigestSha256") != seed_digest:
        raise ValueError("measurements belong to a different seed set")
    if measurements.get("sourceModelSha256") != seeds.get("sourceModelSha256"):
        raise ValueError("measurements belong to a different native model")

    seed_rows = seeds.get("seeds")
    measurement_rows = measurements.get("measurements")
    if not isinstance(seed_rows, list) or not isinstance(measurement_rows, list):
        raise ValueError("seed and measurement rows must be arrays")
    measurement_by_seed = {row.get("seedId"): row for row in measurement_rows}
    if len(measurement_by_seed) != len(measurement_rows) or None in measurement_by_seed:
        raise ValueError("measurement seed IDs must be unique and non-empty")
    seed_ids = [row.get("seedId") for row in seed_rows]
    if set(seed_ids) != set(measurement_by_seed):
        raise ValueError("measurements must cover every and only current frontal seed")

    calculator = Path(__file__).resolve().with_name("calculate_camera_geometry.py")
    compiled_rooms = []
    for seed in seed_rows:
        seed_id = seed["seedId"]
        room_id = seed["roomId"]
        row = measurement_by_seed[seed_id]
        anchor = validate_envelope(row, "anchorEnvelope", seed.get("anchorElementIds", []))
        reference = validate_envelope(
            row,
            "referenceFacadeEnvelope",
            seed.get("referenceFacadeElementIds", []),
        )
        context = validate_envelope(
            row,
            "contextEnvelope",
            seed.get("contextElementIds", []),
            allow_empty=True,
        )
        available_depth = positive_number(
            row.get("availableDepthMeters"), "availableDepthMeters"
        )
        structure_path = Path(seed["calculatorArguments"]["structureData"])
        if not structure_path.is_absolute():
            structure_path = (seed_path.parent / structure_path).resolve()
        expected_structure_sha = seeds.get("bindings", {}).get("structureDataSha256")
        if not structure_path.is_file() or file_sha256(structure_path) != expected_structure_sha:
            raise ValueError(f"{seed_id}: structure binding changed before candidate compilation")

        command = [
            sys.executable,
            str(calculator),
            "--anchor-width", str(anchor["widthMeters"]),
            "--anchor-height", str(anchor["heightMeters"]),
            "--anchor-depth", str(anchor["depthMeters"]),
            "--anchor-ids", ",".join(anchor["elementIds"]),
            "--reference-width", str(reference["widthMeters"]),
            "--reference-height", str(reference["heightMeters"]),
            "--reference-ids", ",".join(reference["elementIds"]),
            "--context-width", str(context["widthMeters"]),
            "--context-height", str(context["heightMeters"]),
            "--context-ids", ",".join(context["elementIds"]),
            "--available-depth", str(available_depth),
            "--room-type", seed["roomType"],
            "--composition", "one-point-frontal",
            "--structure-data", str(structure_path),
            "--reference-wall-id", seed["referenceWallId"],
            "--target-xz", seed["calculatorArguments"]["targetXZ"],
            "--camera-side-xz", seed["calculatorArguments"]["cameraSideXZ"],
        ]
        optional_numbers = {
            "referenceFaceOffsetMeters": "--reference-face-offset",
            "nearDepthOffsetMeters": "--near-depth-offset",
            "farDepthOffsetMeters": "--far-depth-offset",
        }
        for field, flag in optional_numbers.items():
            if field in row:
                command.extend([flag, str(positive_number(row[field], field, allow_zero=True))])
        if "wallWidthMeters" in row:
            command.extend([
                "--wall-width",
                str(positive_number(row["wallWidthMeters"], "wallWidthMeters")),
            ])
        if row.get("tinyRoomAudited") is True:
            command.append("--tiny-room-audited")
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode not in {0, 1}:
            raise ValueError(f"{seed_id}: candidate calculator failed: {completed.stderr.strip()}")
        candidate_set = json.loads(completed.stdout)
        if completed.returncode == 1 or not candidate_set.get("deterministicPrimaryCandidateId"):
            raise ValueError(
                f"{seed_id}: no wall-normal candidate fits the measured retreat depth"
            )
        id_map = {
            candidate["candidateId"]: prefixed_candidate_id(room_id, candidate["candidateId"])
            for candidate in candidate_set.get("candidates", [])
        }
        for candidate in candidate_set.get("candidates", []):
            candidate["candidateId"] = id_map[candidate["candidateId"]]
        for field in (
            "fittingCandidateIds",
            "nativePreviewCandidateIds",
        ):
            candidate_set[field] = [id_map[value] for value in candidate_set.get(field, [])]
        primary_id = candidate_set.get("deterministicPrimaryCandidateId")
        candidate_set["deterministicPrimaryCandidateId"] = id_map.get(primary_id)
        compiled_rooms.append({
            "seedId": seed_id,
            "seedDigestSha256": seed["seedDigestSha256"],
            "roomId": room_id,
            "candidateGroupId": f"{room_id}-frontal",
            "measurement": row,
            "candidateSet": candidate_set,
        })

    output = {
        "schema": OUTPUT_SCHEMA,
        "producer": {"skill": "interior-camera-capture", "version": PRODUCER_VERSION},
        "methodVersion": METHOD_VERSION,
        "floorplanId": seeds["floorplanId"],
        "modelBackend": seeds["modelBackend"],
        "sourceModelSha256": seeds["sourceModelSha256"],
        "bindings": {
            "seedSetPath": str(seed_path),
            "seedSetSha256": file_sha256(seed_path),
            "seedSetDigestSha256": seed_digest,
            "measurementsPath": str(measurement_path),
            "measurementsSha256": file_sha256(measurement_path),
            "measurementDigestSha256": measurement_digest,
        },
        "policy": {
            "selectionMethod": "deterministic-first-fitting-with-one-bounded-fallback",
            "humanCandidateSearchRequired": False,
            "primaryPreviewCount": 1,
            "maximumFallbackPreviewCount": 1,
        },
        "rooms": compiled_rooms,
    }
    output["batchDigestSha256"] = canonical_sha256(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--measurements", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    seed_path = Path(args.seeds).expanduser().resolve()
    measurement_path = Path(args.measurements).expanduser().resolve()
    output = compile_batch(seed_path, measurement_path)
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"compiled {len(output['rooms'])} deterministic frontal camera groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
