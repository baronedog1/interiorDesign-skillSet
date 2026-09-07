#!/usr/bin/env python3
"""Bind a generated image to its request and always deliver quality findings as advisories."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output-image", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--invocation-id")
    parser.add_argument("--advisory", action="append", default=[])
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    output_path = Path(args.output_image).resolve()
    request = load(request_path)
    if request.get("schema") != "interior.imagegen-request.v5":
        raise ValueError("request must use interior.imagegen-request.v5")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise ValueError("ImageGen did not return a readable image")
    receipt = {
        "schema": "interior.render-delivery.v1",
        "schemaVersion": "1.0",
        "status": "delivered",
        "deliveryBlocked": False,
        "renderId": request["renderId"],
        "shotId": request["shotId"],
        "request": {"path": str(request_path), "sha256": digest(request_path)},
        "output": {
            "path": str(output_path),
            "sha256": digest(output_path),
            "bytes": output_path.stat().st_size,
        },
        "invocationId": args.invocation_id,
        "qualityAdvisories": sorted(set(args.advisory)),
        "qualityPolicy": {
            "advisoryOnly": True,
            "qualityCanRejectDelivery": False,
            "generatedImageAlwaysReturned": True,
        },
        "technicalChecks": {
            "requestReadable": True,
            "outputReadable": True,
            "hashesRecorded": True,
        },
        "finishedAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
