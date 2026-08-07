#!/usr/bin/env python3
"""Revalidate a frozen source inventory against source files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from common import (
    ContractError,
    classify_input,
    load_json,
    object_hash,
    project_root_from_document,
    resolve_in,
    sha256_file,
    validate_schema,
)


def validate_inventory(path: Path) -> dict:
    inventory = load_json(path)
    validate_schema(inventory, "source-inventory.schema.json")
    if object_hash(inventory, "inventoryHash") != inventory["inventoryHash"]:
        raise ContractError("inventoryHash does not match canonical inventory content")
    project_root = project_root_from_document(path, inventory["projectRoot"])
    source_ids = set()
    for source in inventory["sources"]:
        if source["sourceId"] in source_ids:
            raise ContractError(f"Duplicate sourceId: {source['sourceId']}")
        source_ids.add(source["sourceId"])
        source_path = resolve_in(project_root, source["path"])
        if not source_path.is_file():
            raise ContractError(f"Source file missing: {source_path}")
        if source_path.stat().st_size != source["bytes"]:
            raise ContractError(f"Source byte size changed: {source['sourceId']}")
        if sha256_file(source_path) != source["sha256"]:
            raise ContractError(f"Source SHA-256 changed: {source['sourceId']}")
        if source["imageSize"] is not None:
            try:
                with Image.open(source_path) as image:
                    size = {"width": image.width, "height": image.height}
            except Exception as exc:
                raise ContractError(f"Cannot reopen raster {source_path}: {exc}") from exc
            if size != source["imageSize"]:
                raise ContractError(f"Source pixel size changed: {source['sourceId']}")
    for fact in inventory["dimensionFacts"]:
        if fact["sourceId"] not in source_ids:
            raise ContractError(f"Dimension references missing sourceId: {fact['dimensionId']}")
    grade, strict = classify_input(inventory["sources"], inventory["dimensionFacts"])
    if grade != inventory["inputGrade"] or strict != inventory["strictEligible"]:
        raise ContractError("Stored input grade does not match evidence")
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    args = parser.parse_args()
    try:
        inventory = validate_inventory(args.inventory.resolve())
        print(f"source inventory valid: grade={inventory['inputGrade']}")
        return 0
    except ContractError as exc:
        print(f"source inventory invalid: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
