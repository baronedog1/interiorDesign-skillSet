#!/usr/bin/env python3
"""Validate shot-scene-map.v9 against its backend-native semantic frame."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageColor

from view_visibility import (
    audit_connection_opening_pixels,
    compile_visible_frame,
    load_policy,
)


SCHEMA = "interior.shot-scene-map.v9"
SOURCE_SCHEMA = "interior.scene-semantic-frame.v4"
BACKENDS = {"html-threejs", "blender", "cad-step"}
PROJECTION_METHODS = {
    "same-camera-gpu-entity-id-plus-depth-to-room-polygon",
    "blender-native-object-index-plus-depth-to-room-polygon",
    "cad-same-brep-topology-zbuffer-to-room-polygon",
}
COMPONENT_TYPES = {"movable-furniture", "fixed-cabinet"}
GUIDANCE_MODES = ["slot-guided"]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def scalar_strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        result: set[str] = set()
        for key, item in value.items():
            result.add(str(key))
            result.update(scalar_strings(item))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(scalar_strings(item))
        return result
    return set()


def load_closed_world_policy() -> dict:
    policy_path = Path(__file__).resolve().parent.parent / "assets/closed-world-view-policy.v1.json"
    policy = load_json(policy_path)
    assert policy.get("schema") == "interior.closed-world-view-policy.v1"
    return policy


def png_dimensions(path: Path) -> list[int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}"
    return list(struct.unpack(">II", header[16:24]))


def valid_bbox(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and 0 <= value[0] < value[2] <= 1
        and 0 <= value[1] < value[3] <= 1
    )


def same_vector(left: object, right: object, tolerance: float = 1e-6) -> bool:
    return (
        isinstance(left, list)
        and isinstance(right, list)
        and len(left) == len(right)
        and all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))
    )


def valid_pixel_bbox(value: object, image_size: list[int]) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
        and 0 <= value[0] < value[2] <= image_size[0]
        and 0 <= value[1] < value[3] <= image_size[1]
    )


def expected_pixel_bbox(bbox: list[float], image_size: list[int]) -> list[int]:
    return [
        round(bbox[0] * image_size[0]),
        round(bbox[1] * image_size[1]),
        round(bbox[2] * image_size[0]),
        round(bbox[3] * image_size[1]),
    ]


def valid_polygon(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 3
        and all(
            isinstance(point, list)
            and len(point) == 2
            and all(
                isinstance(item, (int, float)) and 0 <= item <= 1
                for item in point
            )
            for point in value
        )
    )


def assert_region_matches_source(
    region: dict, screen: dict, image_size: list[int], mask_ref: str
) -> None:
    assert valid_bbox(region.get("bbox"))
    assert region["bbox"] == screen["bbox"]
    assert region["pixelBBox"] == expected_pixel_bbox(screen["bbox"], image_size)
    assert valid_pixel_bbox(region["pixelBBox"], image_size)
    assert region["semanticId"] == screen["semanticId"]
    assert region["semanticColor"] == screen["semanticColor"]
    assert region["visiblePixelCount"] == screen["visiblePixelCount"]
    assert region["coverage"] == screen["coverage"]
    assert region["maskRef"] == mask_ref


def expected_native_projection_audit(
    shot: dict, visible_entities: dict, source_connections: list[dict]
) -> dict:
    minimum_margin = 0.06
    anchor_ids = shot["framing"]["envelopes"]["anchor"]["elementIds"]
    regions = []
    missing = []
    for anchor_id in anchor_ids:
        entity = visible_entities.get(anchor_id)
        if entity is None:
            missing.append(anchor_id)
            continue
        bbox = entity["screen"]["bbox"]
        margins = {
            "left": bbox[0],
            "top": bbox[1],
            "right": 1.0 - bbox[2],
            "bottom": 1.0 - bbox[3],
        }
        regions.append(
            {
                "sourceModelId": anchor_id,
                "bbox": bbox,
                "frameMargins": margins,
                "marginAccepted": all(
                    value + 1e-9 >= minimum_margin for value in margins.values()
                ),
            }
        )
    visible_source_ids = set(visible_entities)
    visible_source_ids.update(
        connection["sourceModelId"]
        for connection in source_connections
        if connection.get("screen", {}).get("bbox")
    )
    must_show_ids = shot.get("mustShowElements", [])
    missing_must_show = sorted(set(must_show_ids) - visible_source_ids)
    return {
        "source": "backend-native-semantic-frame",
        "anchorElementIds": anchor_ids,
        "minimumMarginRatio": minimum_margin,
        "anchorRegions": regions,
        "missingAnchorElementIds": missing,
        "allAnchorElementsVisible": not missing and len(regions) == len(anchor_ids),
        "allAnchorMarginsAccepted": (
            not missing
            and len(regions) == len(anchor_ids)
            and all(region["marginAccepted"] for region in regions)
        ),
        "mustShowElementIds": must_show_ids,
        "missingMustShowElementIds": missing_must_show,
        "allMustShowElementsVisible": bool(must_show_ids) and not missing_must_show,
    }


def expected_closed_world_view(
    rooms: list[dict],
    connections: list[dict],
    structures: list[dict],
    slots: list[dict],
    placement_relations: dict,
) -> dict:
    policy = load_closed_world_policy()
    boundary_terminations = []
    exterior_rules = policy["exteriorBoundaryRules"]
    for connection in connections:
        if "exterior" not in connection.get("roomIds", []):
            continue
        rule = exterior_rules.get(connection.get("kind"), exterior_rules["default"])
        boundary_terminations.append(
            {
                "connectionId": connection["connectionId"],
                "kind": connection["kind"],
                "interiorRoomIds": sorted(
                    room_id
                    for room_id in connection.get("roomIds", [])
                    if room_id != "exterior"
                ),
                "farSide": "exterior",
                "allowedDepictions": rule["allowedDepictions"],
                "forbiddenDepictions": rule["forbiddenDepictions"],
            }
        )
    inventory = sorted(
        (
            {
                "slotId": slot["slotId"],
                "functionalClass": slot["functionalClass"],
                "quantity": slot["quantity"],
                "roomId": slot["roomId"],
            }
            for slot in slots
        ),
        key=lambda row: row["slotId"],
    )
    return {
        "schema": "interior.closed-world-view.v1",
        "policyVersion": policy["policyVersion"],
        "policyDigestSha256": canonical_sha256(policy),
        "semantics": policy["semantics"],
        "required": {
            "roomIds": sorted(room["roomId"] for room in rooms),
            "connectionIds": sorted(connection["connectionId"] for connection in connections),
            "structureIds": sorted(structure["structureId"] for structure in structures),
            "placementSlotIds": sorted(slot["slotId"] for slot in slots),
            "placementSlotInventory": inventory,
            "placementRelations": placement_relations,
        },
        "forbidden": {
            "inferenceClasses": policy["forbiddenInferenceClasses"],
            "rule": "Any room, opening, structure, furniture, cabinet, appliance or fixture not enumerated in required is absent and must not be generated.",
        },
        "boundaryTerminations": boundary_terminations,
        "additionPolicy": {
            "allowedClasses": policy["allowedAdditionClasses"],
            "mustRemainNonstructural": True,
            "mustNotCreateRoomOpeningOrPlacementSlot": True,
            "mustNotObstructExistingOpeningOrClearance": True,
        },
    }


def main() -> None:
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: validate_shot_scene_map.py <map.json> [--final]")
    path = Path(sys.argv[1]).resolve()
    final = len(sys.argv) == 3 and sys.argv[2] == "--final"
    data = load_json(path)
    assert data.get("schema") == SCHEMA
    assert data.get("modelBackend") in BACKENDS
    assert isinstance(data.get("sourceModelSha256"), str) and len(data["sourceModelSha256"]) == 64
    assert data.get("coordinateSystem") == "image-top-left-normalized"
    assert "sendToImageModel" not in json.dumps(data, ensure_ascii=False)

    image_size = data.get("imageSize")
    assert (
        isinstance(image_size, list)
        and len(image_size) == 2
        and all(isinstance(item, int) and item > 0 for item in image_size)
    )
    semantic_raster = data.get("semanticRaster", {})
    assert semantic_raster.get("policy") == "fixed-800px-maximum-width"
    assert semantic_raster.get("normalizedToImageSize") is True
    assert semantic_raster.get("maximumSourcePixelError", 99) <= 2
    guidance = data.get("guidance", {})
    assert guidance.get("mediaKind") == "space-screenshot"
    assert guidance.get("defaultMode") == "slot-guided"
    assert guidance.get("availableModes") == GUIDANCE_MODES
    assert guidance.get("selectionOwner") == (
        "interior-space-rendering/render-plan.v11"
    )
    assert guidance.get("style") == {
        "state": "none",
        "styleId": "none",
        "name": "无风格",
    }
    assert guidance.get("semanticSource") in PROJECTION_METHODS
    assert guidance.get("modePresentation") == {
        "slot-guided": {
            "components": "hidden-facts-retained-in-json-only",
            "structureAppearance": "concrete-shell-including-concrete-floor",
        },
    }
    assert guidance.get("fourQuadrantContract") == {
        "schema": "interior.render-four-quadrant.v1",
        "quadrants": [
            "q1-slot-guided-concrete-camera",
            "q2-furnished-same-camera-reference",
            "q3-plan-camera-frustum",
            "q4-accepted-render",
        ],
        "sameShotCameraAndModelRequired": True,
    }
    assert data.get("sourceEvidence", {}).get("projectionMethod") in PROJECTION_METHODS

    base = path.parent
    assets = data.get("assets", {})
    expected_asset_roles = {
        "slotGuidedConcreteImage": (
            "q1-generation-input-pure-concrete-structure"
        ),
        "furnishedReferenceImage": (
            "q2-qa-only-same-camera-furniture-and-cabinet-reference"
        ),
        "entitySemanticMask": "qa-only-entity-coordinate-evidence-never-submit-to-image-model",
        "roomSemanticMask": "qa-only-room-coordinate-evidence-never-submit-to-image-model",
        "sourceRoomSemanticMask": "qa-only-unfiltered-native-room-mask",
        "planCameraImage": "q3-plan-camera-frustum-evidence-only",
        "planCameraJson": "same-native-model-camera-facts-only",
        "cameraPlan": "native-anchor-and-camera-contract",
        "visibilityAudit": "qa-only-never-submit-to-image-model",
    }
    asset_paths = {}
    for name, asset in assets.items():
        asset_path = (base / asset["file"]).resolve()
        assert asset_path.is_file(), asset_path
        assert sha256(asset_path) == asset["sha256"], asset_path
        asset_paths[name] = asset_path
        if name in expected_asset_roles:
            assert asset.get("role") == expected_asset_roles[name]
    assert png_dimensions(asset_paths["slotGuidedConcreteImage"]) == image_size
    assert png_dimensions(asset_paths["furnishedReferenceImage"]) == image_size
    assert "planCameraImage" in asset_paths, "missing 2D camera-plan evidence"
    assert png_dimensions(asset_paths["planCameraImage"]) == image_size
    camera_plan_evidence = load_json(asset_paths["planCameraJson"])
    assert camera_plan_evidence.get("schema") == \
        "interior.camera-plan-evidence.v2"
    assert camera_plan_evidence.get("source") == "same-native-model-camera-state"
    assert camera_plan_evidence.get("modelBackend") == data.get("modelBackend")
    assert camera_plan_evidence.get("sourceModelSha256") == data.get("sourceModelSha256")
    assert camera_plan_evidence.get("shotId") == data.get("shotId")
    assert camera_plan_evidence.get("position") == data.get("camera", {}).get("position")
    assert camera_plan_evidence.get("target") == data.get("camera", {}).get("target")
    assert camera_plan_evidence.get("fov") == data.get("camera", {}).get("fov")
    camera_plan = load_json(asset_paths["cameraPlan"])
    assert camera_plan.get("schema") == "interior.camera-plan.v8"
    assert camera_plan.get("methodVersion") == "deterministic-wall-normal-camera-v7"
    assert camera_plan.get("modelBackend") == data.get("modelBackend")
    assert camera_plan.get("sourceModelSha256") == data.get("sourceModelSha256")
    shot = next(
        (
            item
            for item in camera_plan.get("shots", [])
            if item.get("shotId") == data.get("shotId")
        ),
        None,
    )
    assert shot is not None, "scene map shot is missing from bundled camera plan"
    seed_descriptor = camera_plan.get("frontalSeedSet", {})
    seed_path = (asset_paths["cameraPlan"].parent / seed_descriptor.get("path", "")).resolve()
    assert seed_path.is_file(), "bundled frontal seed set is missing"
    assert sha256(seed_path) == seed_descriptor.get("sha256")
    seed_set = load_json(seed_path)
    assert seed_set.get("schema") == "interior.camera-frontal-seed-set.v1"
    assert seed_set.get("seedSetDigestSha256") == seed_descriptor.get("seedSetDigestSha256")
    if shot.get("role") == "primary":
        seed = next(
            (item for item in seed_set.get("seeds", []) if item.get("seedId") == shot.get("frontalSeedId")),
            None,
        )
        assert seed is not None, "primary shot is missing its deterministic frontal seed"
        assert seed.get("roomId") == shot.get("roomId")
        assert seed.get("referenceWallId") == shot.get("frontalAlignment", {}).get("referenceWallId")
    assert data.get("shotContract") == {
        "role": shot.get("role"),
        "composition": shot.get("composition"),
        "wallNormalFrontal": (
            shot.get("role") == "primary"
            and shot.get("composition") == "one-point-frontal"
            and shot.get("frontalAlignment", {}).get("mode")
            == "reference-wall-normal"
            and shot.get("frontalAlignment", {}).get("rayHitsReferenceWall")
            is True
        ),
        "referenceWallId": shot.get("frontalAlignment", {}).get(
            "referenceWallId"
        ),
    }
    circulation = data.get("circulationBinding", {})
    descriptor = camera_plan.get("circulationResult", {})
    assert circulation.get("resultSha256") == descriptor.get("sha256")
    assert circulation.get("resultDigestSha256") == descriptor.get("resultDigestSha256")
    assert circulation.get("topologyAuditDigestSha256") == descriptor.get("topologyAuditDigestSha256")
    assert circulation.get("layoutRelationshipAuditDigestSha256") == descriptor.get("layoutRelationshipAuditDigestSha256")

    source_path = asset_paths["semanticFrame"]
    source = load_json(source_path)
    assert source.get("schema") == SOURCE_SCHEMA
    assert source.get("modelBackend") == data.get("modelBackend")
    assert source.get("sourceModelSha256") == data.get("sourceModelSha256")
    assert source.get("floorplanId") == data.get("floorplanId")
    assert source.get("modelRevision") == data.get("modelRevision")
    assert source.get("shotId") == data.get("shotId")
    assert source.get("imageSize") == image_size
    source_camera = source.get("camera", {})
    map_camera = data.get("camera", {})
    assert same_vector(source_camera.get("position"), map_camera.get("position"))
    assert same_vector(source_camera.get("target"), map_camera.get("target"))
    assert abs(float(source_camera.get("fov", 0)) - float(map_camera.get("fov", 0))) <= 1e-6
    for field, value in source_camera.items():
        if field not in {"position", "target", "fov"}:
            assert map_camera.get(field) == value
    assert isinstance(map_camera.get("focalLengthMm"), (int, float))
    assert source.get("coordinateSystem") == data.get("coordinateSystem")
    assert source.get("semanticRaster") == semantic_raster
    assert source.get("guidanceImages", {}).get("furnishedQa") == (
        assets["furnishedReferenceImage"]["file"]
    )
    original_slot_guided = (source_path.parent / source["guidanceImages"]["slotGuided"]).resolve()
    assert original_slot_guided.is_file()
    source_presentation = source.get("presentation", {})
    assert source_presentation == {
        "sourceState": "same-model-dual-capture-evidence-on-concrete-shell",
        "defaultGenerationMode": "slot-guided",
        "evidenceStates": {
            "slot-guided": {
                "componentPresentation": "hidden",
                "slotFactsRetained": True,
                "structureAppearance": "concrete-shell",
                "generationAuthority": True,
            },
            "furnished-qa": {
                "componentPresentation": "visible",
                "structureAppearance": "concrete-shell",
                "generationAuthority": False,
            },
        },
        "styleState": "none",
        "componentAppearanceAuthority": "json-slots-only-for-generation",
    }
    assert assets["entitySemanticMask"]["file"] == (
        source["entitySemanticMask"]["image"]
    )
    assert assets["sourceRoomSemanticMask"]["file"] == (
        source["roomSemanticMask"]["image"]
    )

    visibility_policy = load_policy(Path(__file__).resolve().parent.parent)
    connection_pixel_audits = audit_connection_opening_pixels(
        source, asset_paths["entitySemanticMask"], visibility_policy
    )
    visible_frame = compile_visible_frame(
        source,
        data.get("primaryRoomId"),
        visibility_policy,
        connection_pixel_audits,
    )
    source_rooms = {room["roomId"]: room for room in visible_frame["includedRooms"]}
    prompt_decisions = {
        "rooms": [
            decision
            for decision in visible_frame["decisions"]["rooms"]
            if decision.get("included") is True
        ],
        "connections": [
            decision
            for decision in visible_frame["decisions"]["connections"]
            if decision.get("included") is True
        ],
    }
    expected_visibility_audit = {
        "schema": "interior.shot-visibility-audit.v1",
        "shotId": data.get("shotId"),
        "modelBackend": data.get("modelBackend"),
        "sourceModelSha256": data.get("sourceModelSha256"),
        "sourceSemanticFrame": {
            "file": source_path.name,
            "sha256": sha256(source_path),
        },
        "policyVersion": visible_frame["policyVersion"],
        "policyDigestSha256": visible_frame["policyDigestSha256"],
        "includedRoomIds": sorted(source_rooms),
        "includedConnectionIds": sorted(
            item["sourceModelId"] for item in visible_frame["includedConnections"]
        ),
        "decisions": visible_frame["decisions"],
        "connectionPixelAudits": connection_pixel_audits,
        "submissionPolicy": "qa-only-never-submit-to-image-model",
    }
    assert load_json(asset_paths["visibilityAudit"]) == expected_visibility_audit
    rooms = data.get("rooms", [])
    assert {room["roomId"] for room in rooms} == set(source_rooms)
    assert data.get("visibleRoomIds") == sorted(source_rooms)
    assert data.get("visibleFrame") == {
        "schema": visible_frame["schema"],
        "policyVersion": visible_frame["policyVersion"],
        "policyDigestSha256": visible_frame["policyDigestSha256"],
        "includedRoomIds": sorted(source_rooms),
        "includedConnectionIds": sorted(
            item["sourceModelId"] for item in visible_frame["includedConnections"]
        ),
        "decisions": prompt_decisions,
        "promptRule": (
            "Prompt-facing scene maps contain included current-camera facts only. "
            "Full inclusion and exclusion diagnostics live only in the QA visibility audit "
            "and must never be submitted to the image model."
        ),
    }
    excluded_ids = {
        decision["roomId"]
        for decision in visible_frame["decisions"]["rooms"]
        if decision.get("included") is not True
    } | {
        decision["connectionId"]
        for decision in visible_frame["decisions"]["connections"]
        if decision.get("included") is not True
    }
    leaked_ids = excluded_ids & scalar_strings(data)
    assert not leaked_ids, f"prompt-facing scene map leaks excluded IDs: {sorted(leaked_ids)}"
    with Image.open(asset_paths["roomSemanticMask"]) as opened:
        prompt_image = opened.convert("RGB")
        prompt_pixels = (
            prompt_image.get_flattened_data()
            if hasattr(prompt_image, "get_flattened_data")
            else prompt_image.getdata()
        )
        prompt_room_colors = set(prompt_pixels)
    allowed_room_colors = {
        ImageColor.getrgb(room["screen"]["semanticColor"])
        for room in visible_frame["includedRooms"]
    }
    assert prompt_room_colors <= allowed_room_colors | {(0, 0, 0)}
    assert allowed_room_colors <= prompt_room_colors
    primary_room_id = data.get("primaryRoomId")
    assert any(
        room.get("roomId") == primary_room_id and room.get("role") == "primary"
        for room in rooms
    )
    for room in rooms:
        source_room = source_rooms[room["roomId"]]
        assert room["name"] == source_room["displayName"]
        assert room["roomType"] == source_room["roomType"]
        assert_region_matches_source(
            room["region"], source_room["screen"], image_size, "roomSemanticMask"
        )
        expected_room_source = (
            "same-step-topology-visible-surface-membership"
            if data["modelBackend"] == "cad-step"
            else "same-frame-depth-reprojection-to-room-polygon"
        )
        assert room["region"]["source"] == expected_room_source

    source_connections = {
        item["sourceModelId"]: item
        for item in visible_frame["includedConnections"]
    }
    connections = data.get("connections", [])
    assert {item["connectionId"] for item in connections} == set(
        source_connections
    )
    for connection in connections:
        source_connection = source_connections[connection["connectionId"]]
        region = connection["region"]
        source_screen = source_connection["screen"]
        assert connection["kind"] == source_connection["kind"]
        assert connection.get("openingStyle") == source_connection.get("openingStyle")
        assert connection["roomIds"] == source_connection["roomIds"]
        assert {
            room_id for room_id in connection["roomIds"] if room_id != "exterior"
        } <= set(source_rooms)
        assert connection["forbiddenInferences"] == source_connection.get(
            "forbiddenInferences", []
        )
        assert valid_polygon(region.get("polygon"))
        assert region["polygon"] == source_screen["polygon"]
        assert valid_bbox(region.get("bbox"))
        assert region["bbox"] == source_screen["bbox"]
        assert region["pixelBBox"] == expected_pixel_bbox(
            source_screen["bbox"], image_size
        )
        assert region["source"] == "front-clipped-projected-model-opening-corners"
        visibility = source_screen.get("visibilityEvidence", {})
        assert visibility.get("method") == "all-opening-corners-in-front-of-camera"
        assert visibility.get("allCornersInFrontOfCamera") is True
        assert visibility.get("minimumForwardDepthMeters", 0) > 0
        assert region.get("visibilityEvidence") == {
            "frontProjection": visibility,
            "semanticOpening": connection_pixel_audits[connection["connectionId"]],
        }
        assert region["visibilityEvidence"]["semanticOpening"]["passed"] is True

    visible_entities = {
        entity["sourceModelId"]: entity
        for entity in source.get("entities", [])
        if entity.get("screen", {}).get("visiblePixelCount", 0) > 0
        and entity.get("screen", {}).get("bbox")
    }
    native_projection_audit = expected_native_projection_audit(
        shot, visible_entities, visible_frame["includedConnections"]
    )
    assert data.get("nativeProjectionAudit") == native_projection_audit
    assert native_projection_audit["allAnchorElementsVisible"] is True
    assert native_projection_audit["allAnchorMarginsAccepted"] is True
    assert native_projection_audit["allMustShowElementsVisible"] is True
    source_structures = {
        entity_id: entity
        for entity_id, entity in visible_entities.items()
        if entity["semanticType"] == "structure"
    }
    structures = data.get("structures", [])
    assert {item["structureId"] for item in structures} == set(source_structures)
    for structure in structures:
        source_entity = source_structures[structure["structureId"]]
        assert structure["kind"] == source_entity["category"]
        expected_room_ids = sorted(set(source_entity["roomIds"]) & set(source_rooms))
        assert expected_room_ids
        assert structure["roomIds"] == expected_room_ids
        assert_region_matches_source(
            structure["region"],
            source_entity["screen"],
            image_size,
            "entitySemanticMask",
        )

    source_components = {
        entity_id: entity
        for entity_id, entity in visible_entities.items()
        if entity["semanticType"] in COMPONENT_TYPES
    }
    slots = data.get("placementSlots", [])
    with Image.open(asset_paths["slotGuidedConcreteImage"]) as delivered, Image.open(original_slot_guided) as source_guidance:
        assert ImageChops.difference(delivered.convert("RGB"), source_guidance.convert("RGB")).getbbox() is None
    assert {slot["slotId"] for slot in slots} == set(source_components)
    for slot in slots:
        source_entity = source_components[slot["slotId"]]
        assert slot["objectClass"] == source_entity["semanticType"]
        assert slot["category"] == source_entity["category"]
        assert slot["functionalClass"] == source_entity["functionalClass"]
        assert slot["quantity"] == source_entity["quantity"] == 1
        assert slot["assetId"] == source_entity["assetId"]
        assert slot["sourceObjectCandidateId"] == source_entity.get("sourceObjectCandidateId")
        assert slot["localAxes"] == source_entity.get("localAxes", {})
        expected_component_rooms = [
            room_id for room_id in source_entity["roomIds"] if room_id in source_rooms
        ]
        assert len(expected_component_rooms) == 1
        assert slot["roomId"] == expected_component_rooms[0]
        assert slot["dimensionsMeters"] == source_entity["dimensionsMeters"]
        assert slot["worldBounds"] == source_entity["worldBounds"]
        assert slot["worldTransform"] == source_entity["worldTransform"]
        assert slot["mustPreserve"] == bool(source_entity.get("mustPreserve"))
        assert slot["guidanceAvailability"] == {
            "slot-guided": {
                "componentVisible": False,
                "slotFactsRetained": True,
            },
        }
        assert slot["appearanceAuthority"] == (
            "user-asset-if-provided-otherwise-style-constrained-free"
        )
        assert slot["slotLock"] == {
            "position": True,
            "footprint": True,
            "orientation": True,
            "category": True,
            "clearance": True,
        }
        expected_geometry_policy = (
            "cabinet-location-footprint-orientation-category-clearance-locked-shape-flexible"
            if source_entity["semanticType"] == "fixed-cabinet"
            else "furniture-location-footprint-orientation-category-clearance-locked"
        )
        assert slot["geometryPolicy"] == expected_geometry_policy
        assert_region_matches_source(
            slot["region"],
            source_entity["screen"],
            image_size,
            "entitySemanticMask",
        )

    entity_regions = [
        item["region"] for item in structures
    ] + [item["region"] for item in slots]
    assert entity_regions
    semantic_ids = [region["semanticId"] for region in entity_regions]
    semantic_colors = [region["semanticColor"] for region in entity_regions]
    assert len(semantic_ids) == len(set(semantic_ids))
    assert len(semantic_colors) == len(set(semantic_colors))

    audit = data.get("slotProjectionAudit", {})
    assert audit == {
        "sourceVisibleComponentCount": len(source_components),
        "mappedSlotCount": len(slots),
        "missingSourceModelIds": [],
        "extraSlotIds": [],
        "exactMatch": True,
    }
    assert "camera" in data.get("renderPolicy", {}).get("locked", [])
    assert "placement-slot-footprint" in data["renderPolicy"]["locked"]
    assert "placement-slot-clearance" in data["renderPolicy"]["locked"]
    visible_slot_ids = {slot["slotId"] for slot in slots}
    visible_structure_ids = {structure["structureId"] for structure in structures}
    visible_asset_ids = {slot["assetId"] for slot in slots}
    source_relations = source.get("relationHints") or {}
    placement_relations = {
        "schema": "interior.layout-relation-hints.v2",
        "directionalAxes": [
            row for row in source_relations.get("directionalAxes", [])
            if row.get("assetId") in visible_asset_ids
        ],
        "facing": [
            row for row in source_relations.get("facing", [])
            if row.get("sourceId") in visible_slot_ids
            and row.get("targetId") in visible_slot_ids
        ],
        "wallAttachment": [
            row for row in source_relations.get("wallAttachment", [])
            if row.get("sourceId") in visible_slot_ids
            and (row.get("wallId") or row.get("targetId")) in visible_structure_ids
        ],
        "allowedContacts": [
            row for row in source_relations.get("allowedContacts", [])
            if row.get("firstId") in visible_slot_ids
            and row.get("secondId") in visible_slot_ids
        ],
        "spaceDividerMarkers": [
            row for row in source_relations.get("spaceDividerMarkers", [])
            if set(row.get("roomIds", [])).issubset(set(source_rooms))
        ],
    }
    assert data.get("placementRelations") == placement_relations
    closed_world_view = expected_closed_world_view(
        rooms, connections, structures, slots, placement_relations
    )
    assert data.get("closedWorldView") == closed_world_view
    assert "closed-world-required-sets" in data["renderPolicy"]["locked"]
    assert "closed-world-forbidden-sets" in data["renderPolicy"]["locked"]
    assert "exterior-boundary-termination" in data["renderPolicy"]["locked"]
    assert set(data["renderPolicy"].get("neverInfer", [])) == (
        set(closed_world_view["forbidden"]["inferenceClasses"])
        | {
            item
            for connection in connections
            for item in connection.get("forbiddenInferences", [])
        }
    )
    assert data["renderPolicy"].get("freeWhenNoUserAsset") == [
        "listed-placement-slot-product-appearance",
        "listed-fixed-cabinet-detail-within-locked-slot",
        "materials-and-colors-within-target-style",
        "allowed-nonstructural-additions-only",
    ]

    if final:
        review = data.get("review", {})
        assert review.get("schema") == "interior.scene-map-agent-review.v2"
        assert review.get("status") == "accepted"
        assert review.get("reviewerInvocationId")
        assert review.get("sourceInvocationId")
        assert review["reviewerInvocationId"] != review["sourceInvocationId"]
        assert set(review.get("observedRoomIds", [])) == {room["roomId"] for room in rooms}
        assert set(review.get("observedConnectionIds", [])) == {item["connectionId"] for item in connections}
        assert set(review.get("observedStructureIds", [])) == {item["structureId"] for item in structures}
        assert set(review.get("observedPlacementSlotIds", [])) == {slot["slotId"] for slot in slots}
        assert review.get("unexpectedRoomIds") == []
        assert review.get("unexpectedConnectionIds") == []
        assert review.get("unexpectedStructureIds") == []
        assert review.get("unexpectedPlacementSlotIds") == []
        assert review.get("closedWorldContractAccepted") is True
        assert review.get("decision") == "accept"
        evidence_roles = set()
        for item in review.get("evidence", []):
            evidence_path = (base / item.get("path", "")).resolve()
            assert item.get("role") not in evidence_roles
            evidence_roles.add(item.get("role"))
            assert evidence_path.is_file() and sha256(evidence_path) == item.get("sha256")
        assert evidence_roles == {
            "slot-guided-concrete-image",
            "furnished-reference-image",
            "plan-camera-image",
            "semantic-overlay",
        }
    print(
        json.dumps(
            {
                "ok": True,
                "schema": SCHEMA,
                "rooms": len(rooms),
                "connections": len(connections),
                "structures": len(structures),
                "placementSlots": len(slots),
                "sourceExactMatch": True,
                "final": final,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
