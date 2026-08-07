#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


if len(sys.argv) != 4:
    raise SystemExit("usage: validate_booklet_plan.py <brief.json> <asset-register.json> <page-specs.json>")
brief = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
register = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
spec = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
assert brief.get("schema") == "interior.design-booklet.v2"
assert register.get("schema") == "interior.booklet-asset-register.v1"
assert spec.get("schema") == "interior.booklet-pages.v2"
assert brief.get("includeTraceAppendix") is False or brief.get("traceAppendixUserRequested") is True

assets = {item["assetId"]: item for item in register.get("assets", [])}
assert assets and len(assets) == len(register["assets"])
assert all(item.get("qaStatus") == "passed" for item in assets.values())
assert any(item.get("role") == "planning" for item in assets.values())

pages = spec.get("pages", [])
assert pages and [page["pageNumber"] for page in pages] == list(range(1, len(pages) + 1))
order = {"cover": 0, "planning": 1, "user-assets": 2, "space": 3, "detail": 4, "material": 4, "closing": 5}
sections = [order[page["section"]] for page in pages]
assert sections == sorted(sections), "booklet section order is invalid"
assert "planning" in [page["section"] for page in pages]
assert "space" in [page["section"] for page in pages]

inset_default = brief.get("whiteModelInset", {}).get("enabled") is True
disabled = brief.get("whiteModelInset", {}).get("userExplicitlyDisabled") is True
layout_modes = []
for page in pages:
    layout_modes.append(page.get("layoutMode"))
    assert page.get("headline") is not None
    assert page.get("layoutMode") and page.get("layoutReason")
    for key in ("primaryAssetId",):
        if page.get(key):
            assert page[key] in assets
    if page["section"] != "space":
        continue
    primary = assets[page["primaryAssetId"]]
    assert primary["role"] == "final-render"
    inset = page.get("whiteModelInset", {})
    matching = [
        item for item in assets.values()
        if item.get("role") == "white-model-shot" and item.get("shotId") == primary.get("shotId")
    ]
    if inset_default and not disabled and matching:
        assert inset.get("enabled") is True
        assert inset.get("assetId") in {item["assetId"] for item in matching}
        assert 0.16 <= float(inset.get("widthRatio", 0)) <= 0.28
        assert inset.get("position") in {"top-right", "bottom-right", "side-rail"}

if len(pages) > 8:
    assert len(set(layout_modes)) >= 4
for left, middle, right in zip(layout_modes, layout_modes[1:], layout_modes[2:]):
    assert not (left == middle == right), "same layout may not repeat three times"
print(json.dumps({
    "ok": True,
    "pages": len(pages),
    "layoutModes": len(set(layout_modes)),
    "assets": len(assets),
}, ensure_ascii=False))
