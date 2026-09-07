#!/usr/bin/env python3
"""Low-cost positive/negative regression for the direct source-model pixel gate."""

from __future__ import annotations

from PIL import Image, ImageDraw

from compile_floorplan_handoff import source_pixel_audit


def fixture() -> tuple[dict, Image.Image]:
    image = Image.new("RGB", (240, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.line([(20, 25), (220, 25)], fill="black", width=1)
    draw.line([(20, 35), (220, 35)], fill="black", width=1)
    draw.line([(92, 25), (112, 25)], fill="black", width=1)
    draw.rectangle((70, 80, 145, 140), outline="black", width=1)
    draw.line([(70, 110), (145, 110)], fill="black", width=1)
    draw.line([(108, 80), (108, 140)], fill="black", width=1)
    model = {
        "walls": [{
            "id": "wall-01",
            "centerline": [[20, 30], [220, 30]],
            "thicknessPx": 10,
        }],
        "openings": [{
            "id": "window-01",
            "kind": "window",
            "segment": [[92, 25], [112, 25]],
        }],
        "objects": [{
            "id": "table-01",
            "outline": [[70, 80], [145, 80], [145, 140], [70, 140]],
            "details": [[[70, 110], [145, 110]], [[108, 80], [108, 140]]],
        }],
    }
    return model, image


def main() -> int:
    model, image = fixture()
    report, errors = source_pixel_audit(model, image)
    assert report["passed"], errors
    model["objects"][0]["outline"] = [[5, 70], [55, 70], [55, 150], [5, 150]]
    report, errors = source_pixel_audit(model, image)
    assert not report["passed"]
    assert any("table-01/object-outline" in error for error in errors)
    print("source pixel audit regression: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
