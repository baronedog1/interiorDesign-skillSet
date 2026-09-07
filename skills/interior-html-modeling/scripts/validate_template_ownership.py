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
        default="__INTERIOR_COAUTHORING_EDITOR__",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    owner = args.skill_root.resolve()
    skills_root = args.skills_root.resolve()
    template_root = owner / "assets" / "interior-coauthoring-template"
    owner_app = template_root / "index.html"
    issues: list[str] = []
    conflicts: list[str] = []

    if not (template_root / "index.html").is_file():
        issues.append("owner 缺少 assets/interior-coauthoring-template/index.html")
    if not owner_app.is_file():
        issues.append("owner 缺少唯一模板 index.html")
    elif args.expected_marker not in owner_app.read_text(encoding="utf-8"):
        issues.append(f"owner index.html 缺少模板标记 {args.expected_marker}")

    for peer in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        if peer.resolve() == owner:
            continue
        legacy_template_name = "base-" + "floorplan-template"
        for template_name in ("interior-coauthoring-template", legacy_template_name):
            duplicate_root = peer / "assets" / template_name
            if duplicate_root.exists():
                conflicts.append(str(duplicate_root))
        for candidate in [*peer.rglob("*.js"), *peer.rglob("*.html")]:
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
