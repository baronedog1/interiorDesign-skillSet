#!/usr/bin/env python3
"""Shared deterministic helpers for cad-object-modeling."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = SKILL_ROOT / "schemas"


class ContractError(ValueError):
    """Raised when an input breaks a workflow contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Top-level JSON must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def object_hash(value: dict[str, Any], hash_field: str) -> str:
    body = dict(value)
    body.pop(hash_field, None)
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_within(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractError(f"Path escapes project root: {candidate}") from exc
    return candidate


def resolve_in(root: Path, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ContractError("Artifact path must be a non-empty string")
    path = Path(raw_path)
    candidate = path if path.is_absolute() else root / path
    return ensure_within(root, candidate)


def relative_path(root: Path, path: Path) -> str:
    return ensure_within(root, path).relative_to(root.resolve()).as_posix()


def artifact_record(root: Path, path: Path) -> dict[str, Any]:
    path = ensure_within(root, path)
    if not path.is_file():
        raise ContractError(f"Artifact does not exist: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise ContractError(f"Artifact is empty: {path}")
    return {
        "path": relative_path(root, path),
        "sha256": sha256_file(path),
        "bytes": size,
    }


def validate_schema(value: dict[str, Any], schema_name: str) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise ContractError(
            "jsonschema is required for contract validation; use /usr/bin/python3"
        ) from exc
    schema_path = SCHEMA_ROOT / schema_name
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        lines = []
        for error in errors[:12]:
            location = ".".join(str(part) for part in error.path) or "<root>"
            lines.append(f"{location}: {error.message}")
        raise ContractError(f"Schema validation failed ({schema_name}): " + " | ".join(lines))


def classify_input(sources: list[dict[str, Any]], dimensions: list[dict[str, Any]]) -> tuple[str, bool]:
    calibrated_axes = {
        source["view"]["normalAxis"]
        for source in sources
        if source["view"]["projection"] == "orthographic"
        and source["view"]["normalAxis"] in {"x", "y", "z"}
        and source["calibration"]["status"] == "calibrated"
    }
    explicit_axes = {
        fact["axis"]
        for fact in dimensions
        if fact["axis"] in {"x", "y", "z"}
        and fact["confidence"] in {"explicit", "user-confirmed"}
    }
    if calibrated_axes == {"x", "y", "z"} and explicit_axes == {"x", "y", "z"}:
        return "A", True
    if calibrated_axes and explicit_axes:
        return "B", False
    return "C", False


def project_root_from_document(document_path: Path, raw_root: str) -> Path:
    root = (document_path.parent / raw_root).resolve()
    if not root.is_dir():
        raise ContractError(f"Project root does not exist: {root}")
    return root


def project_root_string(document_path: Path, project_root: Path) -> str:
    return Path(os.path.relpath(project_root, document_path.parent)).as_posix()
