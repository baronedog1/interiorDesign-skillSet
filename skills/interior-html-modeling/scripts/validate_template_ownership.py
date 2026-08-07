#!/usr/bin/env python3
"""Verify that the active floor-plan HTML template has one Skill owner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--skills-root", required=True, type=Path)
    parser.add_argument(
        "--expected-marker",
        default="INTERIOR_HTML_MODELING_V170_MODEL_SCOPE_SINGLE_SOURCE",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    owner = args.skill_root.resolve()
    skills_root = args.skills_root.resolve()
    template_root = owner / "assets" / "base-floorplan-template"
    owner_app = template_root / "app.js"
    issues: list[str] = []
    conflicts: list[str] = []

    if not (template_root / "index.html").is_file():
        issues.append("owner 缺少 assets/base-floorplan-template/index.html")
    if not owner_app.is_file():
        issues.append("owner 缺少 assets/base-floorplan-template/app.js")
    elif args.expected_marker not in owner_app.read_text(encoding="utf-8"):
        issues.append(f"owner app.js 缺少版本标记 {args.expected_marker}")

    for peer in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        if peer.resolve() == owner:
            continue
        duplicate_root = peer / "assets" / "base-floorplan-template"
        if duplicate_root.exists():
            conflicts.append(str(duplicate_root))
        for candidate in peer.rglob("*.js"):
            try:
                if args.expected_marker in candidate.read_text(encoding="utf-8"):
                    conflicts.append(str(candidate))
            except (OSError, UnicodeDecodeError):
                continue

    if conflicts:
        issues.append("其它 Skill 存在基础户型模板或相同模板版本标记")

    report = {
        "schema": "interior.template-ownership-audit.v1",
        "owner": str(owner),
        "skillsRoot": str(skills_root),
        "templateRoot": str(template_root),
        "expectedMarker": args.expected_marker,
        "conflicts": sorted(set(conflicts)),
        "issues": issues,
        "ok": not issues,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
