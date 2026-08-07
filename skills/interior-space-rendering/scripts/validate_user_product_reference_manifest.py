#!/usr/bin/env python3
"""Validate user-supplied product images and their exact placement-slot bindings."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from render_contract import exact_unique_strings, load_json, resolve, sha256_file


SCHEMA = "interior.user-product-reference-manifest.v1"


def _slug(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
        raise ValueError(f"{label} must be a lowercase slug")
    return value


def validate_manifest(
    path: Path,
    expected_floorplan_id: str | None = None,
    allowed_slot_ids: set[str] | None = None,
    require_exact_slots: bool = False,
) -> dict:
    path = path.resolve()
    data = load_json(path)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"product reference manifest must use {SCHEMA}")
    floorplan_id = _slug(data.get("floorplanId"), "floorplanId")
    if expected_floorplan_id is not None and floorplan_id != expected_floorplan_id:
        raise ValueError("product reference manifest belongs to a different floorplan")
    if data.get("authority") != "product-appearance-only" or data.get("neverAuthorityFor") != [
        "camera",
        "crop",
        "architecture",
        "room-topology",
        "slot-position-footprint-orientation",
    ]:
        raise ValueError("product reference authority is broader than appearance")

    references = data.get("references")
    if not isinstance(references, list) or not references:
        raise ValueError("at least one user product reference image is required")
    reference_ids = exact_unique_strings(
        [row.get("referenceId") for row in references], "references.referenceId"
    )
    reference_by_id: dict[str, dict] = {}
    product_by_id: dict[str, dict] = {}
    for row, reference_id in zip(references, reference_ids):
        _slug(reference_id, "referenceId")
        target = resolve(path.parent, row.get("path", ""))
        if not target.is_file() or sha256_file(target) != row.get("sha256"):
            raise ValueError(f"user product reference is missing or stale: {reference_id}")
        products = row.get("products")
        if not isinstance(products, list) or not products:
            raise ValueError(f"{reference_id}: products are missing")
        for product in products:
            product_id = _slug(product.get("productId"), "productId")
            if product_id in product_by_id:
                raise ValueError(f"duplicate productId: {product_id}")
            _slug(product.get("functionalClass"), "functionalClass")
            region = product.get("sourceRegionNormalized")
            if (
                not isinstance(region, list)
                or len(region) != 4
                or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in region)
                or any(float(value) < 0 or float(value) > 1 for value in region)
                or float(region[2]) <= 0
                or float(region[3]) <= 0
                or float(region[0]) + float(region[2]) > 1.000001
                or float(region[1]) + float(region[3]) > 1.000001
            ):
                raise ValueError(f"{product_id}: source region must be normalized [x,y,w,h]")
            product_by_id[product_id] = {**product, "referenceId": reference_id}
        reference_by_id[reference_id] = {**row, "resolvedPath": target}

    bindings = data.get("slotBindings")
    if not isinstance(bindings, list):
        raise ValueError("slotBindings must be a list")
    slot_ids = exact_unique_strings(
        [row.get("slotId") for row in bindings], "slotBindings.slotId"
    )
    for binding, slot_id in zip(bindings, slot_ids):
        _slug(slot_id, "slotId")
        product_id = binding.get("productId")
        reference_id = binding.get("referenceId")
        if product_id not in product_by_id or reference_id not in reference_by_id:
            raise ValueError(f"{slot_id}: binding references an unknown product or image")
        if product_by_id[product_id]["referenceId"] != reference_id:
            raise ValueError(f"{slot_id}: product belongs to another reference image")
        if binding.get("appearanceAuthority") != "user-supplied-product-reference":
            raise ValueError(f"{slot_id}: binding lacks user appearance authority")
        if binding.get("exactProductIdentityRequired") is not True:
            raise ValueError(f"{slot_id}: exact product identity must be required")
    slot_set = set(slot_ids)
    if allowed_slot_ids is not None:
        if not slot_set <= allowed_slot_ids:
            raise ValueError("product manifest binds a slot outside the selected render shots")
        if require_exact_slots and slot_set != allowed_slot_ids:
            raise ValueError("required product manifest must bind every selected visible slot exactly once")
    return data


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_user_product_reference_manifest.py manifest.json")
    data = validate_manifest(Path(sys.argv[1]))
    print(
        f"user product reference manifest accepted: "
        f"{len(data['references'])} image(s), {len(data['slotBindings'])} slot(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
