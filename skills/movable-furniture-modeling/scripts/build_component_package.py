#!/usr/bin/env python3
"""Bind the only carving plan, visual-hull state, projection report and HTML."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_utils import canonical_sha256, dump_json, load_json, sha256_file  # noqa: E402


def artifact(path: Path, output: Path) -> dict[str, str]:
    try:
        relative = str(path.resolve().relative_to(output.resolve().parent))
    except ValueError:
        raise SystemExit(f"package artifact must be inside {output.resolve().parent}: {path}")
    return {"path": relative, "sha256": sha256_file(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("state")
    parser.add_argument("projection_report")
    parser.add_argument("standalone")
    parser.add_argument("browser_qa")
    parser.add_argument("output")
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--placement-class", required=True, choices=("movable-green", "fixed-purple"))
    arguments = parser.parse_args()
    paths = [Path(value).resolve() for value in (
        arguments.plan,
        arguments.state,
        arguments.projection_report,
        arguments.standalone,
        arguments.browser_qa,
    )]
    output = Path(arguments.output).resolve()
    plan, state, report = (load_json(path) for path in paths[:3])
    browser_qa = load_json(paths[4])
    if state.get("planSha256") != canonical_sha256(plan):
        raise SystemExit("state does not bind plan")
    if state.get("stateSha256") != canonical_sha256(state, {"stateSha256"}):
        raise SystemExit("state hash mismatch")
    if report.get("stateSha256") != state["stateSha256"] or not report.get("pass"):
        raise SystemExit("projection report is not an accepted zero-XOR result for state")
    if report.get("planSha256") != state["planSha256"]:
        raise SystemExit("projection report does not bind the carving plan")
    if browser_qa.get("schema") != "interior.product-browser-qa.v1":
        raise SystemExit("unsupported browser QA")
    if browser_qa.get("stateSha256") != state["stateSha256"]:
        raise SystemExit("browser QA does not bind the visual-hull state")
    if browser_qa.get("standaloneSha256") != sha256_file(paths[3]):
        raise SystemExit("browser QA does not bind the standalone HTML")
    if browser_qa.get("canonicalSha256") != canonical_sha256(browser_qa, {"canonicalSha256"}):
        raise SystemExit("browser QA canonical hash mismatch")
    if not browser_qa.get("pass") or browser_qa.get("errors"):
        raise SystemExit("browser QA did not pass")
    for viewport in (browser_qa.get("desktop", {}), browser_qa.get("mobile", {})):
        if not viewport.get("pass") or not viewport.get("canvasNonBlank"):
            raise SystemExit("browser QA viewport did not pass")
        if any(viewport.get(key) != 0 for key in ("consoleErrorCount", "webglErrorCount", "overflowPx")):
            raise SystemExit("browser QA viewport contains errors or overflow")
    evidence_artifacts = []
    seen_view_ids: set[str] = set()
    for reference in plan.get("evidence", []):
        view_id = reference.get("viewId")
        if not view_id or view_id in seen_view_ids:
            raise SystemExit("carving plan evidence viewId must be unique")
        seen_view_ids.add(view_id)
        evidence_path = (paths[0].parent / reference["path"]).resolve()
        evidence = load_json(evidence_path)
        if evidence.get("schema") != "interior.product-view-region-evidence.v1":
            raise SystemExit(f"unsupported region evidence for {view_id}")
        if evidence.get("viewId") != view_id:
            raise SystemExit(f"region evidence viewId mismatch for {view_id}")
        source_path = (evidence_path.parent / evidence["source"]["path"]).resolve()
        if sha256_file(source_path) != evidence["source"]["sha256"]:
            raise SystemExit(f"source image hash mismatch for {view_id}")
        if evidence.get("canonicalSha256") != canonical_sha256(evidence, {"canonicalSha256"}):
            raise SystemExit(f"region evidence canonical hash mismatch for {view_id}")
        evidence_artifacts.append({
            "viewId": view_id,
            "regionEvidence": artifact(evidence_path, output),
            "sourceImage": artifact(source_path, output),
        })
    if not evidence_artifacts:
        raise SystemExit("component package requires at least one source-backed view")
    if state.get("status") not in {"candidate", "provisional"}:
        raise SystemExit("package builder only accepts the immutable carving candidate/provisional state")
    has_inference = state.get("status") == "provisional" or any(
        component.get("inferenceFlags") for component in state.get("components", [])
    )
    status = "provisional" if has_inference else "accepted"
    package = {
        "schema": "interior.custom-component-package.v3",
        "packageId": arguments.package_id,
        "placementClass": arguments.placement_class,
        "appearance": {
            "defaultMode": "white-model",
            "supportedModes": ["white-model", "source-color"],
            "geometryStateSha256": state["stateSha256"],
            "sourceColorAuthority": "visualHullState.components[].material",
        },
        "bindings": {
            "planCanonicalSha256": state["planSha256"],
            "stateCanonicalSha256": state["stateSha256"],
            "projectionReportCanonicalSha256": report["reportSha256"],
            "browserQaCanonicalSha256": browser_qa["canonicalSha256"],
        },
        "carvingPlan": artifact(paths[0], output),
        "evidence": evidence_artifacts,
        "visualHullState": artifact(paths[1], output),
        "projectionReport": artifact(paths[2], output),
        "standalone": artifact(paths[3], output),
        "browserQa": artifact(paths[4], output),
        "status": status,
        "packageSha256": "",
    }
    package["packageSha256"] = canonical_sha256(package, {"packageSha256"})
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "schemas/component-package-v3.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(package)
    dump_json(output, package)


if __name__ == "__main__":
    main()
