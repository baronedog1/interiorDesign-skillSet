#!/usr/bin/env python3
"""Index the Blender-only managed asset store without copying binary assets into the Skill."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import CATALOG_SCHEMA, read_json, sha256, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = Path(args.store).resolve()
    policy_path = Path(args.policy).resolve()
    policy = read_json(policy_path)
    if policy.get("schema") != "interior.blender-catalog-policy.v1":
        raise SystemExit("invalid Blender catalog policy schema")
    assets = []
    for path in sorted(store.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".blend", ".glb", ".gltf"}:
            continue
        relative = path.relative_to(store).as_posix()
        slug = path.parent.name if path.parent != store else path.stem
        override = policy.get("assetOverrides", {}).get(slug, {})
        source = override.get("source", policy.get("defaultSource"))
        license_id = override.get("license", policy.get("sourceLicenses", {}).get(source))
        assets.append({
            "assetId": override.get("assetId", slug),
            "name": override.get("name", slug.replace("_", " ")),
            "relativePath": relative,
            "format": path.suffix.lower().lstrip("."),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "source": source,
            "license": license_id,
            "category": override.get("category", "unclassified"),
            "tags": override.get("tags", []),
            "supportedFunctionalClasses": override.get("supportedFunctionalClasses", []),
            "directionalAxes": override.get("directionalAxes", {}),
            "axes": override.get("axes", {"up": "+Z", "front": "-Y"}),
            "reviewStatus": override.get("reviewStatus", "needs-semantic-review"),
        })
    payload = {
        "schema": CATALOG_SCHEMA,
        "storeRoot": str(store),
        "policySha256": sha256(policy_path),
        "assetCount": len(assets),
        "assets": assets,
    }
    write_json(Path(args.out).resolve(), payload)
    print(f"indexed {len(assets)} Blender assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
