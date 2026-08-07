#!/usr/bin/env python3
"""Validate source hashes and exact visible-region partition invariants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_utils import (  # noqa: E402
    canonical_sha256,
    registration_axes,
    resolve,
    rle_to_mask,
    sha256_file,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence")
    arguments = parser.parse_args()
    evidence_path = Path(arguments.evidence).resolve()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    skill_root = Path(__file__).resolve().parents[1]
    schema = json.loads((skill_root / "schemas/view-region-evidence.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(evidence)

    expected_canonical = canonical_sha256(evidence, {"canonicalSha256"})
    if evidence["canonicalSha256"] != expected_canonical:
        raise SystemExit("canonical evidence SHA-256 mismatch")
    source_path = resolve(evidence_path, evidence["source"]["path"])
    if sha256_file(source_path) != evidence["source"]["sha256"]:
        raise SystemExit("source file SHA-256 mismatch")

    product = rle_to_mask(evidence["productMask"])
    expected_shape = (evidence["source"]["height"], evidence["source"]["width"])
    if product.shape != expected_shape:
        raise SystemExit("product mask dimensions differ from source")
    exclusion = rle_to_mask(evidence["backgroundExclusionMask"])
    if np.any(product & exclusion):
        raise SystemExit("product mask enters background exclusion")

    labels = np.zeros(expected_shape, dtype=np.uint16)
    for index, component in enumerate(evidence["components"], start=1):
        visible = rle_to_mask(component["visibleMask"])
        if visible.shape != expected_shape:
            raise SystemExit(f"component {component['componentId']} dimensions differ")
        if not np.any(visible):
            raise SystemExit(f"component {component['componentId']} is empty")
        if np.any(labels[visible]):
            raise SystemExit(f"component {component['componentId']} overlaps another visible region")
        labels[visible] = index
        if "carvingMask" in component:
            carving = rle_to_mask(component["carvingMask"])
            if carving.shape != expected_shape:
                raise SystemExit(f"component {component['componentId']} carving mask dimensions differ")
    if not np.array_equal(labels > 0, product):
        missing = int(np.logical_and(product, labels == 0).sum())
        extra = int(np.logical_and(~product, labels > 0).sum())
        raise SystemExit(f"component partition mismatch missing={missing} extra={extra}")

    registration_axes(evidence["registration"])
    for axis_name in ("u", "v"):
        pixel_range = evidence["registration"][f"{axis_name}PixelRange"]
        limit = evidence["source"]["width" if axis_name == "u" else "height"]
        if not (0 <= min(pixel_range) < max(pixel_range) <= limit):
            raise SystemExit(f"{axis_name}PixelRange outside source")

    report = {
        "schema": "interior.product-view-region-validation.v1",
        "evidence": str(evidence_path),
        "canonicalSha256": evidence["canonicalSha256"],
        "productPixels": int(product.sum()),
        "componentCount": len(evidence["components"]),
        "componentCoverage": 1.0,
        "overlapPixels": 0,
        "backgroundExclusionViolations": 0,
        "registrationAxes": list(registration_axes(evidence["registration"])),
        "pass": True,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
