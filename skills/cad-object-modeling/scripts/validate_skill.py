#!/usr/bin/env python3
"""Validate the exact cad-object-modeling Skill package and unique workflow."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


IGNORED_NAMES = {"__pycache__", ".DS_Store"}
REQUIRED_SKILL_TOKENS = {
    "interior.cad-object-source-inventory.v1",
    "interior.cad-object-view-evidence.v1",
    "interior.cad-object-plan.v1",
    "interior.cad-object-validation.v1",
    "interior.cad-object-package.v1",
    "$cad-zh",
    "$cad-viewer",
    "STEP/B-Rep",
}
PROHIBITED_TOKENS = {
    "interior.custom-component-package.v3",
    "interior.visual-hull-state",
    "movable-furniture-modeling",
}


class SkillValidationError(ValueError):
    pass


def packaged_files(root: Path) -> list[str]:
    values = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_NAMES for part in path.parts):
            continue
        if path.suffix == ".pyc":
            continue
        values.append(path.relative_to(root).as_posix())
    return sorted(values)


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise SkillValidationError("SKILL.md must start with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise SkillValidationError("SKILL.md frontmatter is not closed") from exc
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise SkillValidationError(f"Invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values, "\n".join(lines[end + 1 :])


def validate(root: Path) -> list[str]:
    manifest_path = root / "MANIFEST.json"
    if not manifest_path.is_file():
        raise SkillValidationError("MANIFEST.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != "cad-object-modeling":
        raise SkillValidationError("MANIFEST name mismatch")
    if manifest.get("version") != "1.0.0" or manifest.get("workflowCount") != 1:
        raise SkillValidationError("MANIFEST must declare version 1.0.0 and one workflow")
    if manifest.get("primaryGeometryFact") != "STEP/B-Rep":
        raise SkillValidationError("STEP/B-Rep must be the primary geometry fact")
    expected_files = manifest.get("files")
    actual_files = packaged_files(root)
    if not isinstance(expected_files, list) or expected_files != sorted(set(expected_files)):
        raise SkillValidationError("MANIFEST files must be a sorted unique array")
    if expected_files != actual_files:
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        raise SkillValidationError(f"MANIFEST file graph mismatch: missing={missing} extra={extra}")

    frontmatter, skill_body = parse_frontmatter(root / "SKILL.md")
    if set(frontmatter) != {"name", "description"}:
        raise SkillValidationError("SKILL.md frontmatter may contain only name and description")
    if frontmatter["name"] != "cad-object-modeling" or len(frontmatter["description"]) < 40:
        raise SkillValidationError("SKILL.md name or trigger description is incomplete")
    if len(skill_body.splitlines()) > 500:
        raise SkillValidationError("SKILL.md exceeds 500 body lines")
    for token in REQUIRED_SKILL_TOKENS:
        if token not in (root / "SKILL.md").read_text(encoding="utf-8"):
            raise SkillValidationError(f"SKILL.md is missing required workflow token: {token}")

    all_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in root.rglob("*")
        if path.is_file()
        and path.name != "validate_skill.py"
        and path.suffix in {".md", ".py", ".yaml", ".json"}
    )
    if re.search(r"\b(TODO|TBD|FIXME)\b|\[TODO", all_text, flags=re.IGNORECASE):
        raise SkillValidationError("Skill contains unfinished placeholder text")
    for token in PROHIBITED_TOKENS:
        if token in all_text:
            raise SkillValidationError(f"Skill contains a retired or parallel workflow token: {token}")

    openai_yaml = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "display_name: \"CAD 物品建模\"" not in openai_yaml:
        raise SkillValidationError("agents/openai.yaml display_name mismatch")
    if "$cad-object-modeling" not in openai_yaml:
        raise SkillValidationError("Default prompt must explicitly invoke $cad-object-modeling")

    schema_count = 0
    for path in sorted((root / "schemas").glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_count += 1
    if schema_count != 6:
        raise SkillValidationError(f"Expected exactly six public schemas, found {schema_count}")

    python_count = 0
    for folder in (root / "scripts", root / "assets", root / "tests"):
        for path in sorted(folder.glob("*.py")):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            python_count += 1
    if python_count < 10:
        raise SkillValidationError("Deterministic implementation/test surface is incomplete")
    return [
        f"files={len(actual_files)}",
        f"schemas={schema_count}",
        f"pythonFiles={python_count}",
        "workflowCount=1",
        "primaryGeometryFact=STEP/B-Rep",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_root", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        facts = validate(args.skill_root.resolve())
        print("cad-object-modeling skill valid: " + " ".join(facts))
        return 0
    except (SkillValidationError, json.JSONDecodeError, SyntaxError) as exc:
        print(f"cad-object-modeling skill invalid: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
