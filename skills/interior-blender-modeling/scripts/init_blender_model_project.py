#!/usr/bin/env python3
"""Initialize the only Blender project from the current HTML model revision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--blender-catalog", required=True)
    parser.add_argument("--material-catalog", required=True)
    parser.add_argument("--style-preset", required=True)
    parser.add_argument("--template-options", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    model_path, structure_path, catalog_path, material_catalog_path, style_path = map(
        lambda value: Path(value).resolve(),
        (args.model, args.structure, args.blender_catalog, args.material_catalog, args.style_preset),
    )
    model, structure, catalog, style = map(read, (model_path, structure_path, catalog_path, style_path))
    floorplan_id = model.get("meta", {}).get("sourceFloorplanId")
    if not floorplan_id or floorplan_id != structure.get("floorplanId"):
        raise SystemExit("current HTML model and structure identities differ")
    furniture = model.get("furniture", [])
    covered = {value for asset in catalog.get("assets", []) for value in asset.get("functionalClasses", [])}
    missing = {str(item.get("functionalClass")) for item in furniture} - covered
    if missing:
        raise SystemExit(f"Blender precision catalog lacks: {sorted(missing)}")
    project = Path(args.out).resolve()
    if project.exists() and any(project.iterdir()):
        raise SystemExit(f"project directory must be empty: {project}")
    for name in ("input", "config", "model", "reports", "camera-scene", "camera"):
        (project / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_path, project / "input" / "current-model.json")
    shutil.copy2(structure_path, project / "input" / "structure-data.json")
    shutil.copy2(catalog_path, project / "config" / "blender-component-catalog.json")
    shutil.copy2(material_catalog_path, project / "config" / "blender-material-catalog.json")
    shutil.copy2(style_path, project / "config" / "style-preset.json")
    options = Path(args.template_options).resolve()
    shutil.copy2(options, project / "config" / "backend-options.json")
    write(project / "project.json", {
        "schema": "interior.blender-model-project.v5", "backend": "blender",
        "floorplanId": floorplan_id,
        "sourceHtmlModelSha256": sha256(model_path),
        "structureSha256": sha256(structure_path), "blenderCatalogSha256": sha256(catalog_path),
        "materialCatalogSha256": sha256(material_catalog_path),
        "stylePresetSha256": sha256(style_path), "styleId": style.get("styleId"),
        "backendOptionsSha256": sha256(options), "furnitureCount": len(furniture),
        "unmatchedFurnitureCount": 0, "status": "ready-to-build",
    })
    print(project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
