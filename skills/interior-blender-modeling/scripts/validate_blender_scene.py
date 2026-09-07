#!/usr/bin/env python3
"""Validate the currently opened native Blender floorplan scene."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy


REQUIRED_COLLECTIONS = {
    "STRUCTURE",
    "OPENINGS",
    "FLOORS",
    "CEILINGS",
    "FURNITURE",
    "LIGHTS",
    "CAMERAS",
    "ANNOTATIONS",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-report", required=True)
    parser.add_argument("--out", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    return parser.parse_args(argv)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    args = parse_args()
    report_path = Path(args.build_report).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if report.get("schema") != "interior.blender-build-report.v5" or report.get("accepted") is not True:
        errors.append("build report is not accepted")
    blend_path = Path(bpy.data.filepath).resolve()
    if not blend_path.is_file() or digest(blend_path) != report.get("nativeModelSha256"):
        errors.append("opened .blend does not match the build report hash")
    collection_names = set(bpy.data.collections.keys())
    missing = sorted(REQUIRED_COLLECTIONS - collection_names)
    if missing:
        errors.append(f"missing required collections: {missing}")
    furniture = bpy.data.collections.get("FURNITURE")
    if furniture:
        polluted = sorted(obj.name for obj in furniture.all_objects if obj.type in {"CAMERA", "LIGHT", "SPEAKER"})
        if polluted:
            errors.append(f"asset-local cameras/lights leaked into FURNITURE: {polluted}")
    components = [obj for obj in bpy.data.objects if obj.get("interiorEntityType") == "component"]
    entity_ids = [obj.get("interiorEntityId") for obj in components]
    if len(components) != report.get("counts", {}).get("furniture"):
        errors.append("component root count differs from the build report")
    if None in entity_ids or len(entity_ids) != len(set(entity_ids)):
        errors.append("component entity IDs are not one-to-one")
    if any(not obj.get("componentId") or not obj.get("assetSha256") for obj in components):
        errors.append("component root lacks managed asset identity")
    entity_meshes = [
        obj for obj in bpy.data.objects
        if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"} and obj.get("interiorEntityId")
    ]
    if not entity_meshes:
        errors.append("scene has no renderable entity-tagged geometry")
    if report.get("primitiveFurnitureFallbackCount") != 0:
        errors.append("primitive furniture fallback is present")
    if report.get("unmatchedFurnitureCount") != 0:
        errors.append("unmatched furniture is present")
    if any(not obj.get("frontAxisLocal") or not obj.get("orientationMode") for obj in components):
        errors.append("component root lacks orientation contract")
    if any(not obj.get("assetSelection") or not obj.get("assetStyleTags") for obj in components):
        errors.append("component root lacks material asset selection contract")
    if not bpy.context.scene.get("interiorStylePreset"):
        errors.append("scene lacks embedded Blender style preset")
    required_material_ids = {"wall-white-plaster", "ceiling-soft-plaster", "floor-warm-oak", "floor-interior-ceramic"}
    material_ids = {str(material.get("interiorMaterialId", "")) for material in bpy.data.materials}
    if not required_material_ids.issubset(material_ids):
        errors.append("scene lacks required PBR building material templates")
    result = {
        "schema": "interior.blender-scene-validation.v1",
        "accepted": not errors,
        "nativeModelSha256": report.get("nativeModelSha256"),
        "blenderVersion": bpy.app.version_string,
        "collections": sorted(collection_names & REQUIRED_COLLECTIONS),
        "componentRoots": len(components),
        "renderableTaggedEntities": len(entity_meshes),
        "errors": errors,
    }
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("\n".join(errors))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
