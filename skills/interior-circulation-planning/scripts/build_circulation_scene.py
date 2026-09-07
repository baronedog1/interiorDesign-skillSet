#!/usr/bin/env python3
"""Normalize HTML, Blender, or CAD layout state into one circulation scene."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

from common import (
    as_point,
    canonical_sha256,
    normalize_polygon,
    read_json,
    require_schema,
    sha256_file,
    transform_outline,
    write_json,
)


HANDOFF_SCHEMA = "interior.floorplan-handoff.v3"
STRUCTURE_SCHEMAS = {"interior.floorplan-structure.v3", "interior.floorplan-structure.v4"}
TRACE_SCHEMA = "interior.trace-components.v2"
MANIFEST_SCHEMA = "interior.native-model-manifest.v1"
SCENE_SCHEMA = "interior.circulation-scene.v3"


NON_BLOCKING_TERMS = {
    "rug",
    "carpet",
    "地毯",
    "wall-art",
    "painting",
    "挂画",
    "mirror",
    "镜子",
    "ceiling",
    "light",
    "lamp",
    "chandelier",
    "吊灯",
    "窗帘",
    "curtain",
}


def artifact_descriptor(handoff: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    artifacts = handoff.get("artifacts", {})
    for key in keys:
        descriptor = artifacts.get(key)
        if isinstance(descriptor, dict):
            return descriptor
    return None


def verify_handoff_artifact(handoff: dict[str, Any], path: Path, *keys: str) -> str:
    actual = sha256_file(path)
    descriptor = artifact_descriptor(handoff, *keys)
    if descriptor is None:
        raise ValueError(f"handoff is missing required artifact descriptor: {'/'.join(keys)}")
    if descriptor.get("sha256") != actual:
        raise ValueError(f"handoff artifact SHA-256 mismatch: {path}")
    if descriptor.get("bytes") not in (None, path.stat().st_size):
        raise ValueError(f"handoff artifact byte count mismatch: {path}")
    return actual


def verify_manifest_source(manifest: dict[str, Any], structure_sha: str, traces_sha: str) -> None:
    structure_candidates = [
        manifest.get("sourceHashes", {}).get("structure"),
        manifest.get("sourceArtifacts", {}).get("structureData", {}).get("sha256"),
    ]
    if structure_sha not in structure_candidates:
        raise ValueError("native model manifest is not bound to the supplied structure-data.json")
    trace_candidates = [
        manifest.get("sourceHashes", {}).get("components"),
        manifest.get("sourceArtifacts", {}).get("traceComponents", {}).get("sha256"),
    ]
    if any(value is not None for value in trace_candidates) and traces_sha not in trace_candidates:
        raise ValueError("native model manifest is not bound to the supplied trace-components.json")


def native_model_sha(manifest: dict[str, Any]) -> str:
    native = manifest.get("nativeModel") or {}
    path_value = native.get("path") or manifest.get("nativeModelPath")
    expected = native.get("sha256") or manifest.get("nativeModelSha256")
    if not path_value or not expected:
        raise ValueError("native model manifest is missing native model path or SHA-256")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"native model file does not exist: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError("native model SHA-256 mismatch")
    return actual


def trace_index(traces: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in traces.get("objects", []):
        source_id = item.get("sourceObjectCandidateId")
        if not source_id or source_id in result:
            raise ValueError("trace-components requires unique sourceObjectCandidateId values")
        result[source_id] = item
    return result


def text_blob(value: dict[str, Any]) -> str:
    parts = [
        value.get("id"),
        value.get("name"),
        value.get("category"),
        value.get("semanticType"),
        value.get("componentId"),
        value.get("assetId"),
        value.get("variant"),
    ]
    return " ".join(str(item).lower() for item in parts if item)


def relation_hint_facts(layout: dict[str, Any]) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    relations = layout.get("relationHints")
    if not isinstance(relations, dict) or relations.get("schema") != "interior.layout-relation-hints.v3":
        raise ValueError("layout state requires interior.layout-relation-hints.v3 orientation evidence")
    allowed_keys = {
        "schema", "directionalAxes", "worldOrientations", "facing", "wallAttachment",
        "allowedContacts", "spaceDividerMarkers",
    }
    unexpected = sorted(set(relations) - allowed_keys)
    if unexpected:
        raise ValueError(f"relation hints contain legacy or calculated fields: {unexpected}")
    axes: dict[str, dict[str, str]] = {}
    allowed_evidence = {
        "browser-reviewed-authored-model",
        "blender-native-preview-reviewed-authored-model",
        "cad-native-preview-reviewed-authored-model",
        "historical-browser-reviewed-consensus",
    }
    for row in relations.get("directionalAxes", []):
        component_id = row.get("assetId")
        role = row.get("role")
        local_axis = row.get("localAxis")
        if (
            set(row) != {"assetId", "role", "localAxis", "evidence"}
            or not component_id
            or role not in {"front", "back", "headboard"}
            or local_axis not in {"+X", "-X", "+Z", "-Z"}
            or row.get("evidence") not in allowed_evidence
            or role in axes.setdefault(component_id, {})
        ):
            raise ValueError(f"invalid or duplicate directional axis evidence: {component_id}::{role}")
        axes[component_id][role] = local_axis
    for row in relations.get("facing", []):
        if (
            set(row) != {"sourceId", "targetId", "axisRole"}
            or not row.get("sourceId")
            or not row.get("targetId")
            or row.get("axisRole") not in {"front", "back", "headboard"}
        ):
            raise ValueError("facing hints only allow sourceId, targetId and axisRole")
    for row in relations.get("wallAttachment", []):
        if (
            set(row) != {"sourceId", "wallId", "axisRole"}
            or not row.get("sourceId")
            or not row.get("wallId")
            or row.get("axisRole") not in {"front", "back", "headboard"}
        ):
            raise ValueError("wall attachment hints only allow sourceId, wallId and axisRole")
    for row in relations.get("allowedContacts", []):
        if (
            set(row) != {"firstId", "secondId", "kind"}
            or not row.get("firstId")
            or not row.get("secondId")
            or row.get("firstId") == row.get("secondId")
            or row.get("kind") != "chair-tucked-under-table"
        ):
            raise ValueError("allowed contact hints only identify one chair/table object pair")
    hints = {
        "facing": [
            {
                "sourceId": row.get("sourceId"),
                "targetId": row.get("targetId"),
                "axisRole": row.get("axisRole"),
            }
            for row in relations.get("facing", [])
        ],
        "wallAttachment": [
            {
                "sourceId": row.get("sourceId"),
                "wallId": row.get("wallId"),
                "axisRole": row.get("axisRole"),
            }
            for row in relations.get("wallAttachment", [])
        ],
        "allowedContacts": [
            {
                "firstId": row.get("firstId"),
                "secondId": row.get("secondId"),
                "kind": row.get("kind"),
            }
            for row in relations.get("allowedContacts", [])
        ],
    }
    return axes, hints


def floorplan_components(traces: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Compile the accepted plan objects without introducing model-side facts."""
    components: list[dict[str, Any]] = []
    for trace in traces.get("objects", []):
        center = as_point(trace.get("center", []), f"{trace.get('traceId')} center")
        rotation = float(trace.get("rotationY"))
        footprint = trace_footprint(trace, center, rotation)
        orientation = trace.get("orientation") or {}
        local_axes = orientation.get("localAxes") or trace.get("localAxes") or {}
        if not isinstance(local_axes, dict):
            raise ValueError(f"{trace.get('traceId')} orientation.localAxes must be an object")
        component = {
            "id": trace.get("traceId"),
            "sourceObjectCandidateId": trace.get("sourceObjectCandidateId"),
            "designAdditionId": None,
            "sourceTraceId": trace.get("traceId"),
            "roomId": trace.get("roomId"),
            "semantic": trace.get("semantic"),
            "assetId": None,
            "category": trace.get("category") or trace.get("functionalClass"),
            "functionalClass": trace.get("functionalClass"),
            "quantity": trace.get("quantity"),
            "localAxes": local_axes,
            "origin": "accepted-floorplan-layout",
            "blockingClass": blocking_class(trace),
            "footprint": [[round(point[0], 6), round(point[1], 6)] for point in footprint],
            "activeTransform": {"position": list(center), "rotationRadians": rotation},
            "sourceTransform": {"position": list(center), "rotationRadians": rotation},
            "reviewedAdjustment": None,
        }
        if (
            not component["id"]
            or not component["sourceObjectCandidateId"]
            or not component["roomId"]
            or not component["functionalClass"]
            or component["quantity"] != 1
        ):
            raise ValueError(
                "floorplan objects require traceId, sourceObjectCandidateId, roomId, "
                "functionalClass and quantity=1"
            )
        components.append(component)
    relations = traces.get("relationHints") or {
        "schema": "interior.layout-relation-hints.v3",
        "directionalAxes": [],
        "worldOrientations": [],
        "facing": [],
        "wallAttachment": [],
        "allowedContacts": [],
        "spaceDividerMarkers": [],
    }
    relation_container = {"relationHints": relations}
    axes_by_asset, relation_hints = relation_hint_facts(relation_container)
    if axes_by_asset:
        raise ValueError("floorplan checkpoint must place directional axes on trace objects, not asset IDs")
    return components, [], relation_hints


def validate_relation_hint_references(
    components: list[dict[str, Any]],
    structure: dict[str, Any],
    relation_hints: dict[str, Any],
) -> None:
    component_by_id = {row["id"]: row for row in components}
    wall_ids = {row["id"] for row in structure.get("walls", [])}
    seen: set[tuple[str, ...]] = set()
    for row in relation_hints.get("facing", []):
        source = component_by_id.get(row["sourceId"])
        target = component_by_id.get(row["targetId"])
        key = ("facing", row["sourceId"], row["targetId"], row["axisRole"])
        if (
            key in seen
            or source is None
            or target is None
            or row["axisRole"] not in source.get("localAxes", {})
        ):
            raise ValueError(f"unresolved or duplicate facing hint: {key}")
        seen.add(key)
    for row in relation_hints.get("wallAttachment", []):
        source = component_by_id.get(row["sourceId"])
        key = ("wall", row["sourceId"], row["wallId"], row["axisRole"])
        if (
            key in seen
            or source is None
            or row["wallId"] not in wall_ids
            or row["axisRole"] not in source.get("localAxes", {})
        ):
            raise ValueError(f"unresolved or duplicate wall attachment hint: {key}")
        seen.add(key)
    for row in relation_hints.get("allowedContacts", []):
        first = component_by_id.get(row["firstId"])
        second = component_by_id.get(row["secondId"])
        classes = {first.get("functionalClass") if first else None, second.get("functionalClass") if second else None}
        key = ("contact", *sorted((row["firstId"], row["secondId"])), row["kind"])
        if (
            key in seen
            or first is None
            or second is None
            or classes != {"dining-chair", "dining-table"}
        ):
            raise ValueError(f"allowed contact is not one atomic dining-chair/table pair: {key}")
        seen.add(key)


def blocking_class(value: dict[str, Any], minimum_y: float | None = None) -> str:
    declared = value.get("blockingClass")
    if declared in {"floor-obstacle", "overhead", "surface-covering", "non-blocking"}:
        return declared
    mount_type = str(value.get("mountType", "")).lower()
    elevation = value.get("elevation")
    if mount_type in {"wall", "ceiling"}:
        return "overhead"
    if isinstance(elevation, (int, float)) and float(elevation) >= 0.45:
        return "overhead"
    if minimum_y is not None and minimum_y >= 0.45:
        return "overhead"
    blob = text_blob(value)
    if any(term in blob for term in NON_BLOCKING_TERMS):
        return "surface-covering" if any(term in blob for term in {"rug", "carpet", "地毯"}) else "non-blocking"
    return "floor-obstacle"


def trace_footprint(
    trace: dict[str, Any], center: tuple[float, float], rotation: float, dimensions: dict[str, Any] | None = None
) -> list[tuple[float, float]]:
    evidence = trace.get("shapeEvidence") or {}
    outline = evidence.get("outline")
    bbox = dimensions or trace.get("bbox") or {}
    width = float(bbox.get("width", 0))
    depth = float(bbox.get("depth", 0))
    if not isinstance(outline, list) or len(outline) < 3:
        raise ValueError(f"trace {trace.get('traceId')} is missing an exact normalized outline")
    return transform_outline(outline, width, depth, center, rotation)


def html_components(layout: dict[str, Any], traces: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    require_schema(layout, "interior.component-layout.v5", "HTML component layout")
    axes_by_asset, relation_hints = relation_hint_facts(layout)
    components: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for placement in layout.get("placements", []):
        source_id = placement.get("sourceObjectCandidateId")
        design_id = placement.get("designAdditionId")
        if bool(source_id) == bool(design_id):
            raise ValueError("each HTML placement requires exactly one sourceObjectCandidateId or designAdditionId")
        center = as_point(placement.get("position", []), "HTML placement position")
        rotation = float(placement.get("planFootprintRotationY", placement.get("sourceRotationY")))
        if source_id:
            if source_id in seen_sources or source_id not in traces:
                raise ValueError(f"HTML placement source binding is missing or duplicated: {source_id}")
            seen_sources.add(source_id)
            trace = traces[source_id]
            if (
                placement.get("functionalClass") != trace.get("functionalClass")
                or placement.get("quantity") != trace.get("quantity")
            ):
                raise ValueError(
                    f"HTML placement {placement.get('id')} changes the frozen functional class or quantity"
                )
            evidence = placement.get("sourceShapeEvidence") or trace.get("shapeEvidence")
            dimensions = placement.get("targetDimensions") or placement.get("sourceDimensions") or trace.get("bbox")
            footprint = transform_outline(
                evidence.get("outline", []),
                float(dimensions.get("width", 0)),
                float(dimensions.get("depth", 0)),
                center,
                rotation,
            )
            origin = "source-traced" if placement.get("reviewedAdjustment") is None else "reviewed-adjustment"
        else:
            footprint_value = placement.get("planFootprint")
            if not isinstance(footprint_value, list):
                raise ValueError(f"design addition {design_id} requires exact planFootprint")
            footprint = normalize_polygon(footprint_value, f"design addition {design_id} footprint")
            origin = "user-explicit-addition"
        component = {
            "id": placement.get("id"),
            "sourceObjectCandidateId": source_id,
            "designAdditionId": design_id,
            "sourceTraceId": placement.get("sourceTraceId"),
            "roomId": placement.get("roomId"),
            "semantic": placement.get("semantic"),
            "assetId": placement.get("componentId"),
            "category": placement.get("category") or placement.get("componentCategory"),
            "functionalClass": placement.get("functionalClass"),
            "quantity": placement.get("quantity"),
            "localAxes": axes_by_asset.get(placement.get("componentId"), {}),
            "worldOrientation": placement.get("worldOrientation"),
            "origin": origin,
            "blockingClass": blocking_class(placement),
            "footprint": [[round(point[0], 6), round(point[1], 6)] for point in footprint],
            "activeTransform": {"position": list(center), "rotationRadians": rotation},
            "sourceTransform": {
                "position": placement.get("sourcePosition"),
                "rotationRadians": placement.get("sourceRotationY"),
            },
            "reviewedAdjustment": placement.get("reviewedAdjustment"),
        }
        if (
            not component["id"]
            or not component["roomId"]
            or not component["category"]
            or not component["functionalClass"]
            or component["quantity"] != 1
        ):
            raise ValueError("HTML placement requires id, roomId, category, functionalClass and quantity=1")
        components.append(component)
    removed = list(layout.get("source", {}).get("removedSourceTraceIds", []))
    return components, removed, relation_hints


def entity_components(
    layout: dict[str, Any],
    traces: dict[str, dict[str, Any]],
    structure: dict[str, Any],
    backend: str,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    expected = "interior.blender-entity-index.v2" if backend == "blender" else "interior.cad-entity-index.v1"
    require_schema(layout, expected, f"{backend} entity index")
    axes_by_asset, relation_hints = relation_hint_facts(layout)
    width = float(structure["coordinateSystem"]["realWidthMeters"])
    depth = float(structure["coordinateSystem"]["realDepthMeters"])
    components: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for entity in layout.get("entities", []):
        entity_type = entity.get("entityType") or entity.get("type")
        if entity_type != "component":
            continue
        source_id = entity.get("sourceObjectCandidateId")
        design_id = entity.get("designAdditionId")
        if bool(source_id) == bool(design_id):
            raise ValueError(f"{backend} component requires one source or design ID: {entity.get('entityId') or entity.get('id')}")
        transform = entity.get("worldTransform") or {}
        world_position = transform.get("position")
        if not isinstance(world_position, list) or len(world_position) < 3:
            raise ValueError(f"{backend} component is missing worldTransform.position")
        center = (float(world_position[0]) + width / 2.0, float(world_position[2]) + depth / 2.0)
        rotation = float(transform.get("yawRadians", entity.get("yawRadians", 0)))
        world_scale = transform.get("scale", [1.0, 1.0, 1.0])
        if not isinstance(world_scale, list) or len(world_scale) < 3:
            raise ValueError(f"{backend} component worldTransform.scale must contain x, y, and z")
        scale_x = abs(float(world_scale[0]))
        scale_z = abs(float(world_scale[2]))
        if not math.isfinite(scale_x) or not math.isfinite(scale_z) or scale_x <= 0 or scale_z <= 0:
            raise ValueError(f"{backend} component has an invalid planar scale")
        if source_id:
            if source_id in seen_sources or source_id not in traces:
                raise ValueError(f"{backend} source binding is missing or duplicated: {source_id}")
            seen_sources.add(source_id)
            if (
                entity.get("functionalClass") != traces[source_id].get("functionalClass")
                or entity.get("quantity") != traces[source_id].get("quantity")
            ):
                raise ValueError(
                    f"{backend} component {entity.get('entityId') or entity.get('id')} changes the frozen functional class or quantity"
                )
            source_bbox = traces[source_id].get("bbox") or {}
            footprint = trace_footprint(
                traces[source_id],
                center,
                rotation,
                {
                    "width": float(source_bbox.get("width", 0)) * scale_x,
                    "depth": float(source_bbox.get("depth", 0)) * scale_z,
                },
            )
            origin = "source-traced"
        else:
            footprint_value = entity.get("planFootprint")
            if not isinstance(footprint_value, list):
                raise ValueError(f"{backend} design addition {design_id} requires exact planFootprint")
            footprint = normalize_polygon(footprint_value, f"{backend} design addition footprint")
            origin = "user-explicit-addition"
        bounds = entity.get("worldBounds") or entity.get("worldBoundsMeters") or {}
        minimum = bounds.get("min") if isinstance(bounds, dict) else None
        minimum_y = float(minimum[1]) if isinstance(minimum, list) and len(minimum) >= 2 else None
        components.append(
            {
                "id": entity.get("entityId") or entity.get("id"),
                "sourceObjectCandidateId": source_id,
                "designAdditionId": design_id,
                "sourceTraceId": entity.get("traceId"),
                "roomId": entity.get("roomId") or (entity.get("roomIds") or [None])[0],
                "semantic": entity.get("semanticType"),
                "assetId": entity.get("assetId"),
                "category": entity.get("category"),
                "functionalClass": entity.get("functionalClass"),
                "quantity": entity.get("quantity"),
                "localAxes": axes_by_asset.get(entity.get("assetId"), {}),
                "origin": origin,
                "blockingClass": blocking_class(entity, minimum_y),
                "footprint": [[round(point[0], 6), round(point[1], 6)] for point in footprint],
                "activeTransform": {
                    "position": list(center),
                    "rotationRadians": rotation,
                    "planarScale": [scale_x, scale_z],
                },
                "sourceTransform": {
                    "position": list(as_point(traces[source_id].get("center", center))) if source_id else None,
                    "rotationRadians": float(traces[source_id].get("rotationY", 0)) if source_id else None,
                },
                "reviewedAdjustment": entity.get("reviewedAdjustment"),
            }
        )
        component = components[-1]
        if (
            not component["id"]
            or not component["roomId"]
            or not component["category"]
            or not component["functionalClass"]
            or component["quantity"] != 1
        ):
            raise ValueError(
                f"{backend} component requires id, roomId, category, functionalClass and quantity=1"
            )
    return components, [], relation_hints


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--traces", required=True)
    parser.add_argument("--checkpoint", choices=("post-floorplan", "post-model"), required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--layout-state")
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.checkpoint == "post-model" and (not args.manifest or not args.layout_state):
        parser.error("post-model requires --manifest and --layout-state")
    paths = {
        name: Path(value).expanduser().resolve()
        for name, value in {
            "handoff": args.handoff,
            "structure": args.structure,
            "traces": args.traces,
            "manifest": args.manifest,
            "layout_state": args.layout_state,
            "source_image": args.source_image,
            "out": args.out,
        }.items()
        if value
    }
    handoff = read_json(paths["handoff"])
    structure = read_json(paths["structure"])
    traces = read_json(paths["traces"])
    manifest = read_json(paths["manifest"]) if "manifest" in paths else None
    layout = read_json(paths["layout_state"]) if "layout_state" in paths else None
    require_schema(handoff, HANDOFF_SCHEMA, "floorplan handoff")
    if structure.get("schema") not in STRUCTURE_SCHEMAS:
        raise ValueError(f"structure data schema must be one of {sorted(STRUCTURE_SCHEMAS)}")
    require_schema(traces, TRACE_SCHEMA, "trace components")
    if manifest is not None:
        require_schema(manifest, MANIFEST_SCHEMA, "native model manifest")

    floorplan_id = handoff.get("floorplanId")
    bound_ids = {structure.get("floorplanId"), traces.get("floorplanId")}
    if manifest is not None:
        bound_ids.add(manifest.get("floorplanId"))
    if not floorplan_id or bound_ids != {floorplan_id}:
        raise ValueError("floorplanId differs across the supplied checkpoint artifacts")
    if manifest is not None and manifest.get("handoffDigestSha256") != handoff.get("handoffDigestSha256"):
        raise ValueError("native model is not derived from this floorplan handoff")
    if handoff.get("validation", {}).get("sourceModel") is not True or handoff.get("validation", {}).get("agentVisualReview") is not True:
        raise ValueError("floorplan handoff has not passed source and Agent visual validation")

    structure_sha = verify_handoff_artifact(handoff, paths["structure"], "structureData")
    traces_sha = verify_handoff_artifact(handoff, paths["traces"], "traceComponents")
    source_sha = sha256_file(paths["source_image"])
    source_descriptor = artifact_descriptor(handoff, "sourceImage", "floorplanSource", "sourceFloorplan")
    if source_descriptor is not None and source_descriptor.get("sha256") != source_sha:
        raise ValueError("source image SHA-256 differs from the handoff")
    traces_by_source = trace_index(traces)
    model_sha = None
    if args.checkpoint == "post-floorplan":
        backend = "floorplan-layout"
        components, removed, relation_hints = floorplan_components(traces)
        adapter = "floorplan-trace-components-v2"
    else:
        assert manifest is not None and layout is not None
        verify_manifest_source(manifest, structure_sha, traces_sha)
        model_sha = native_model_sha(manifest)
        backend = manifest.get("modelBackend")
    if args.checkpoint == "post-model" and backend == "html-threejs":
        components, removed, relation_hints = html_components(layout, traces_by_source)
        adapter = "html-component-layout-v5"
    elif args.checkpoint == "post-model" and backend == "blender":
        components, removed, relation_hints = entity_components(layout, traces_by_source, structure, "blender")
        adapter = "blender-entity-index-v2-to-plan"
    elif args.checkpoint == "post-model" and backend == "cad-step":
        components, removed, relation_hints = entity_components(layout, traces_by_source, structure, "cad")
        adapter = "cad-entity-index-v1-to-plan"
    elif args.checkpoint == "post-model":
        raise ValueError(f"unsupported modelBackend: {backend}")

    validate_relation_hint_references(components, structure, relation_hints)

    scene = {
        "schema": SCENE_SCHEMA,
        "floorplanId": floorplan_id,
        "checkpoint": args.checkpoint,
        "modelBackend": backend,
        "authority": "current-native-model-layout-state",
        "bindings": {
            "sourceImagePath": str(paths["source_image"]),
            "sourceImageSha256": source_sha,
            "floorplanHandoffPath": str(paths["handoff"]),
            "floorplanHandoffSha256": sha256_file(paths["handoff"]),
            "handoffDigestSha256": handoff["handoffDigestSha256"],
            "structureDataPath": str(paths["structure"]),
            "structureDataSha256": structure_sha,
            "traceComponentsPath": str(paths["traces"]),
            "traceComponentsSha256": traces_sha,
            **({
                "nativeModelManifestPath": str(paths["manifest"]),
                "nativeModelManifestSha256": sha256_file(paths["manifest"]),
                "nativeModelSha256": model_sha,
                "layoutStatePath": str(paths["layout_state"]),
                "layoutStateSha256": sha256_file(paths["layout_state"]),
            } if args.checkpoint == "post-model" else {}),
        },
        "backendAdapter": adapter,
        "components": components,
        "relationHints": relation_hints,
        "removedSourceTraceIds": removed,
        "counts": {
            "components": len(components),
            "floorObstacles": sum(item["blockingClass"] == "floor-obstacle" for item in components),
            "nonBlocking": sum(item["blockingClass"] != "floor-obstacle" for item in components),
        },
    }
    scene["sceneDigestSha256"] = canonical_sha256(scene)
    write_json(paths["out"], scene)
    print(f"circulation scene accepted: {backend}, {len(components)} components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
