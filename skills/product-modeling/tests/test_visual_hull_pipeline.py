#!/usr/bin/env python3
"""Deterministic forward tests for multi-view and single-view carving."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from mask_utils import canonical_sha256, dump_json, mask_to_rle, sha256_file  # noqa: E402


def evidence(
    path: Path,
    source: Path,
    view_id: str,
    registration: dict,
    masks: dict[str, np.ndarray],
) -> None:
    product = np.zeros_like(next(iter(masks.values())))
    components = []
    for depth, (component_id, mask) in enumerate(masks.items()):
        product |= mask
        components.append({
            "componentId": component_id,
            "label": component_id.upper(),
            "visibleMask": mask_to_rle(mask),
            "carvingMask": mask_to_rle(mask),
            "depthOrder": depth,
            "projectionRequired": True,
            "occlusion": "none",
        })
    document = {
        "schema": "interior.product-view-region-evidence.v1",
        "viewId": view_id,
        "viewType": "orthographic",
        "source": {
            "path": source.name,
            "sha256": sha256_file(source),
            "width": int(product.shape[1]),
            "height": int(product.shape[0]),
        },
        "registration": registration,
        "productMask": mask_to_rle(product),
        "backgroundExclusionMask": mask_to_rle(np.zeros_like(product)),
        "components": components,
        "quality": {"componentCoverage": 1.0, "overlapPixels": 0},
        "canonicalSha256": "",
    }
    document["canonicalSha256"] = canonical_sha256(document, {"canonicalSha256"})
    dump_json(path, document)


def run(*arguments: str) -> None:
    subprocess.run([sys.executable, *arguments], check=True, capture_output=True, text=True)


def browser_qa(path: Path, state_path: Path, standalone_path: Path) -> None:
    state = json.loads(state_path.read_text())
    document = {
        "schema": "interior.product-browser-qa.v1",
        "stateSha256": state["stateSha256"],
        "standaloneSha256": sha256_file(standalone_path),
        "desktop": {"width": 1280, "height": 800, "canvasNonBlank": True, "consoleErrorCount": 0, "webglErrorCount": 0, "overflowPx": 0, "pass": True},
        "mobile": {"width": 390, "height": 844, "canvasNonBlank": True, "consoleErrorCount": 0, "webglErrorCount": 0, "overflowPx": 0, "pass": True},
        "errors": [],
        "pass": True,
        "canonicalSha256": "",
    }
    document["canonicalSha256"] = canonical_sha256(document, {"canonicalSha256"})
    dump_json(path, document)


def multi_view_case(directory: Path) -> None:
    top_source = directory / "top.png"
    front_source = directory / "front.png"
    cv2.imwrite(str(top_source), np.full((5, 6, 3), 255, np.uint8))
    cv2.imwrite(str(front_source), np.full((4, 6, 3), 255, np.uint8))
    top_a = np.zeros((5, 6), bool); top_a[1:4, 1:3] = True
    top_b = np.zeros((5, 6), bool); top_b[2:4, 3:5] = True
    front_a = np.zeros((4, 6), bool); front_a[1:3, 1:3] = True
    front_b = np.zeros((4, 6), bool); front_b[0:3, 3:5] = True
    evidence(directory / "top.json", top_source, "top", {
        "uAxis": "x", "vAxis": "y", "rayAxis": "z",
        "uPixelRange": [0, 6], "vPixelRange": [0, 5],
        "uWorldRange": [0, 6], "vWorldRange": [0, 5], "rayDirection": -1,
    }, {"a": top_a, "b": top_b})
    evidence(directory / "front.json", front_source, "front", {
        "uAxis": "x", "vAxis": "z", "rayAxis": "y",
        "uPixelRange": [0, 6], "vPixelRange": [0, 4],
        "uWorldRange": [0, 6], "vWorldRange": [4, 0], "rayDirection": -1,
    }, {"a": front_a, "b": front_b})
    plan = {
        "schema": "interior.product-multi-view-carving-plan.v1",
        "planId": "synthetic-multi",
        "primaryViewId": "top",
        "evidence": [
            {"viewId": "top", "path": "top.json", "useForCarving": True, "useForProjectionGate": True},
            {"viewId": "front", "path": "front.json", "useForCarving": True, "useForProjectionGate": True},
        ],
        "axisFallbacks": {},
        "components": [
            {"componentId": "a", "label": "A", "material": {"color": "#aaa"}, "inferenceFlags": []},
            {"componentId": "b", "label": "B", "material": {"color": "#bbb"}, "inferenceFlags": []},
        ],
    }
    dump_json(directory / "multi-plan.json", plan)
    run(str(ROOT / "scripts/carve_visual_hull.py"), str(directory / "multi-plan.json"), str(directory / "multi-state.json"))
    run(str(ROOT / "scripts/compare_view_projection.py"), str(directory / "multi-plan.json"), str(directory / "multi-state.json"), str(directory / "multi-report.json"))
    report = json.loads((directory / "multi-report.json").read_text())
    assert report["pass"]
    assert all(view["assembly"]["xorPixels"] == 0 for view in report["views"])
    run(
        str(ROOT / "scripts/build_product_standalone.py"),
        str(directory / "multi-state.json"),
        str(directory / "multi-standalone.html"),
    )
    browser_qa(directory / "multi-browser-qa.json", directory / "multi-state.json", directory / "multi-standalone.html")
    run(
        str(ROOT / "scripts/build_component_package.py"),
        str(directory / "multi-plan.json"),
        str(directory / "multi-state.json"),
        str(directory / "multi-report.json"),
        str(directory / "multi-standalone.html"),
        str(directory / "multi-browser-qa.json"),
        str(directory / "multi-package.json"),
        "--package-id", "synthetic-multi",
        "--placement-class", "movable-green",
    )
    package = json.loads((directory / "multi-package.json").read_text())
    assert package["status"] == "accepted"
    assert package["appearance"]["defaultMode"] == "white-model"
    assert len(package["evidence"]) == 2


def single_view_case(directory: Path) -> None:
    source = directory / "single-top.png"
    cv2.imwrite(str(source), np.full((5, 6, 3), 255, np.uint8))
    mask = np.zeros((5, 6), bool); mask[1:4, 1:5] = True
    evidence(directory / "single-top.json", source, "top", {
        "uAxis": "x", "vAxis": "y", "rayAxis": "z",
        "uPixelRange": [0, 6], "vPixelRange": [0, 5],
        "uWorldRange": [0, 6], "vWorldRange": [0, 5], "rayDirection": -1,
    }, {"seat": mask})
    plan = {
        "schema": "interior.product-multi-view-carving-plan.v1",
        "planId": "synthetic-single",
        "primaryViewId": "top",
        "evidence": [{"viewId": "top", "path": "single-top.json", "useForCarving": True, "useForProjectionGate": True}],
        "axisFallbacks": {"z": {"min": 0, "max": 2, "cells": 4, "source": "single-view-inferred"}},
        "components": [{"componentId": "seat", "label": "Seat", "material": {"color": "#aaa"}, "inferenceFlags": ["single-view-inferred:z"]}],
    }
    dump_json(directory / "single-plan.json", plan)
    run(str(ROOT / "scripts/carve_visual_hull.py"), str(directory / "single-plan.json"), str(directory / "single-state.json"))
    run(str(ROOT / "scripts/compare_view_projection.py"), str(directory / "single-plan.json"), str(directory / "single-state.json"), str(directory / "single-report.json"))
    state = json.loads((directory / "single-state.json").read_text())
    report = json.loads((directory / "single-report.json").read_text())
    assert state["status"] == "provisional"
    assert report["pass"] and report["views"][0]["assembly"]["xorPixels"] == 0
    run(
        str(ROOT / "scripts/build_product_standalone.py"),
        str(directory / "single-state.json"),
        str(directory / "single-standalone.html"),
    )
    browser_qa(directory / "single-browser-qa.json", directory / "single-state.json", directory / "single-standalone.html")
    run(
        str(ROOT / "scripts/build_component_package.py"),
        str(directory / "single-plan.json"),
        str(directory / "single-state.json"),
        str(directory / "single-report.json"),
        str(directory / "single-standalone.html"),
        str(directory / "single-browser-qa.json"),
        str(directory / "single-package.json"),
        "--package-id", "synthetic-single",
        "--placement-class", "movable-green",
    )
    package = json.loads((directory / "single-package.json").read_text())
    assert package["status"] == "provisional"
    assert len(package["evidence"]) == 1


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="visual-hull-test-") as raw:
        directory = Path(raw)
        multi_view_case(directory)
        single_view_case(directory)
    print(json.dumps({"multiView": "pass", "singleView": "pass", "zeroXor": True}))


if __name__ == "__main__":
    main()
