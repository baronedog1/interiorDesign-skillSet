#!/usr/bin/env python3
"""Atomically promote a user-saved coauthoring HTML to the workspace current version."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


TEMPLATE_DATA = re.compile(
    r"<script\b[^>]*\bid=[\"']template-data[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--returned-html", required=True)
    parser.add_argument("--canonical-html", required=True)
    parser.add_argument("--model-json", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-floorplan-id")
    args = parser.parse_args()

    source = Path(args.returned_html).expanduser().resolve()
    canonical = Path(args.canonical_html).expanduser().resolve()
    model_path = Path(args.model_json).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    html_bytes = source.read_bytes()
    text = html_bytes.decode("utf-8")
    match = TEMPLATE_DATA.search(text)
    if not match:
        raise ValueError("returned HTML is missing the canonical template-data model")
    model = json.loads(match.group(1))
    meta = model.get("meta") or {}
    if meta.get("documentRole") != "user-returned-current-html":
        raise ValueError("this is not a user-saved current HTML; ask the user to click 保存新版HTML first")
    floorplan_id = meta.get("sourceFloorplanId")
    if args.expected_floorplan_id and floorplan_id != args.expected_floorplan_id:
        raise ValueError(
            f"returned HTML belongs to {floorplan_id!r}, expected {args.expected_floorplan_id!r}"
        )
    for key in ("walls", "openings", "rooms", "furniture"):
        if not isinstance(model.get(key), list):
            raise ValueError(f"returned HTML model is missing list: {key}")

    previous_sha = sha256_bytes(canonical.read_bytes()) if canonical.is_file() else None
    model_bytes = (json.dumps(model, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write(canonical, html_bytes)
    atomic_write(model_path, model_bytes)
    receipt = {
        "schema": "interior.user-returned-html-receipt.v1",
        "acceptedAt": datetime.now(timezone.utc).isoformat(),
        "floorplanId": floorplan_id,
        "sourceAttachment": str(source),
        "canonicalHtml": str(canonical),
        "previousCanonicalHtmlSha256": previous_sha,
        "currentCanonicalHtmlSha256": sha256_bytes(html_bytes),
        "currentModelJson": str(model_path),
        "currentModelSha256": sha256_bytes(model_bytes),
        "counts": {
            "rooms": len(model["rooms"]),
            "walls": len(model["walls"]),
            "openings": len(model["openings"]),
            "furniture": len(model["furniture"]),
        },
        "replacementPolicy": "atomic-overwrite-current-version-no-active-legacy-copy",
    }
    receipt_bytes = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write(receipt_path, receipt_bytes)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
