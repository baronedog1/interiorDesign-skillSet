#!/usr/bin/env python3
"""Add exact, reviewable functional-class tags to the frozen CAD catalog."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def classify(asset: dict) -> tuple[list[str], str]:
    text = " ".join(
        str(asset.get(key, "")) for key in ("id", "name", "category", "sourceRepositoryPath")
    ).lower()
    text = re.sub(r"[_/]+", "-", text)
    exact_rules = (
        (("bathroom-cabinet-sink",), ["vanity"]),
        (("wall-hung-toilet", "wallhungtoilet", "wall-hung-toilets"), ["toilet"]),
        (("wallhungbidet",), ["bidet"]),
        (("washbasin",), ["washbasin"]),
        (("shower-box",), ["shower-enclosure"]),
        (("showerpad",), ["shower-tray"]),
        (("floor-drain",), ["floor-drain"]),
        (("faucet", "faucete"), ["faucet"]),
        (("bed-double", "double-bed"), ["double-bed"]),
        (("singlebed", "single-bed"), ["single-bed"]),
        (("nightstand",), ["nightstand"]),
        (("bedroom-closet",), ["wardrobe"]),
        (("kitchen-cabinet-base",), ["base-cabinet"]),
        (("kitchen-cabinet-sink",), ["sink-base-cabinet"]),
        (("kitchen-cabinet-superior",), ["wall-cabinet"]),
        (("kitchen-cabinet-vertical",), ["tall-cabinet"]),
        (("light-pendant",), ["pendant-light"]),
        (("chair-upholstered", "sofa-armchair", "adirondack", "modernchair"), ["accent-chair"]),
        (("wooden-folding-chair",), ["utility-chair"]),
        (("simplechair", "ikealikechair", "living-room-chair", "fcbl-chair"), ["dining-chair"]),
        (("rectangular-center-table",), ["coffee-table"]),
        (("coffee-table", "ikea-lack"), ["coffee-table"]),
        (("sideboard",), ["sideboard"]),
        (("living-room-cabinet",), ["tv-console"]),
        (("computerdesk",), ["desk"]),
        (("generictable", "wooden-folding-table", "table-parametric"), ["dining-table"]),
        (("ikea-kallax", "open-cabinet"), ["shelving"]),
        (("genericdrawers",), ["dresser"]),
        (("generic-kitchenette-cabinet",), ["base-cabinet"]),
        (("generic-parametric-cabinet", "generic-cabinet"), ["closed-cupboard"]),
        (("electricstovetop", "parametric-stove"), ["cooktop"]),
        (("dishwasher",), ["dishwasher"]),
        (("fridge", "refrigerator"), ["refrigerator"]),
        (("kitchenhood",), ["range-hood"]),
        (("laundrymachine", "washing-machine"), ["washing-machine"]),
        (("microwave",), ["microwave"]),
        (("oven",), ["oven"]),
        (("tv-50",), ["television"]),
        (("air-condition",), ["air-conditioner"]),
        (("curtain",), ["curtain"]),
        (("tree-entourage",), ["plant"]),
    )
    for needles, classes in exact_rules:
        if any(needle in text for needle in needles):
            return classes, "accepted"
    if asset.get("category") == "doors":
        return ["door"], "accepted"
    if asset.get("category") == "windows":
        return ["window"], "accepted"
    return [], "needs-functional-review"


def directional_axes(classes: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    if any(value in {"sofa", "accent-chair", "dining-chair", "utility-chair"} for value in classes):
        roles.update({"front": "-Z", "back": "+Z"})
    if any(value in {"single-bed", "double-bed"} for value in classes):
        roles["headboard"] = "+Z"
    if any(value in {"tv-console", "wardrobe", "sideboard", "dresser", "closed-cupboard", "base-cabinet", "sink-base-cabinet", "wall-cabinet", "tall-cabinet", "vanity"} for value in classes):
        roles.update({"front": "-Z", "back": "+Z"})
    return roles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source = Path(args.source).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema") not in {"interior.cad-residential-assets.v2", "interior.cad-residential-assets.v3"}:
        raise SystemExit("source catalog must use interior.cad-residential-assets.v2 or v3")
    accepted = 0
    for asset in payload.get("assets", []):
        classes, status = classify(asset)
        asset["supportedFunctionalClasses"] = classes
        asset["directionalAxes"] = directional_axes(classes)
        asset["functionalReviewStatus"] = status
        accepted += status == "accepted"
    payload["schema"] = "interior.cad-residential-assets.v3"
    payload["functionalTagging"] = {
        "method": "exact-name-and-category-rules-v1",
        "acceptedAssetCount": accepted,
        "needsReviewAssetCount": len(payload.get("assets", [])) - accepted,
        "noCrossFunctionalClassFallback": True,
    }
    target = Path(args.out).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"tagged {len(payload.get('assets', []))} CAD assets; accepted={accepted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
