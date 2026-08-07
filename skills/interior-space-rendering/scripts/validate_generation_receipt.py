#!/usr/bin/env python3
"""Bind a successful image-generation receipt to the exact compiled request."""

from __future__ import annotations

import sys
from pathlib import Path

from render_contract import load_json, resolve, sha256_file, verify_document_digest
from validate_imagegen_request import validate_request


def validate_receipt(request_path: Path, receipt_path: Path) -> dict:
    request_path = request_path.resolve()
    receipt_path = receipt_path.resolve()
    request = validate_request(request_path)
    receipt = load_json(receipt_path)
    if request.get("schema") != "interior.imagegen-request.v4":
        raise ValueError("request schema mismatch")
    if receipt.get("schema") != "interior.imagegen-receipt.v4":
        raise ValueError("Q4 requires an imagegen receipt; native-scene fallback is forbidden")
    verify_document_digest(request, "requestDigestSha256")
    verify_document_digest(receipt, "receiptDigestSha256")
    if receipt.get("requestDigestSha256") != request.get("requestDigestSha256"):
        raise ValueError("receipt is not bound to the compiled request")
    if receipt.get("generationInvocationId") != request.get("generationInvocationId"):
        raise ValueError("receipt generation invocation differs")
    if receipt.get("status") != "succeeded":
        raise ValueError("image generation did not return one successful output")
    if not receipt.get("providerRequestId"):
        raise ValueError("imagegen receipt requires a provider request ID")
    expected = {
        (row["role"], row.get("referenceId", ""), row["sha256"])
        for row in request.get("submittedImageAttachments", [])
    }
    actual = {
        (row["role"], row.get("referenceId", ""), row["sha256"])
        for row in receipt.get("submittedImageAttachments", [])
    }
    if actual != expected:
        raise ValueError("provider receipt image attachments differ from the compiled request")
    output = receipt.get("outputImage", {})
    output_path = resolve(receipt_path.parent, output.get("path", ""))
    if not output_path.is_file() or sha256_file(output_path) != output.get("sha256"):
        raise ValueError("generated output image is missing or changed")
    return receipt


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_generation_receipt.py imagegen-request.json receipt.json")
    receipt = validate_receipt(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"generation receipt accepted: {receipt['providerRequestId']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
