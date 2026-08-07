#!/usr/bin/env python3
"""Build shot-scene-map.v9 from one backend-native semantic frame."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

from view_visibility import (
    audit_connection_opening_pixels,
    build_pure_concrete_structure,
    build_prompt_room_mask,
    compile_visible_frame,
    load_policy,
)


SOURCE_SCHEMA = "interior.scene-semantic-frame.v4"
OUTPUT_SCHEMA = "interior.shot-scene-map.v9"
BACKENDS = {"html-threejs", "blender", "cad-step"}
PROJECTION_METHODS = {
    "same-camera-gpu-entity-id-plus-depth-to-room-polygon",
    "blender-native-object-index-plus-depth-to-room-polygon",
    "cad-same-brep-topology-zbuffer-to-room-polygon",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(base_dir: Path, name: str, label: str) -> Path:
    path = (base_dir / name).resolve()
    if not path.is_file():
        raise AssertionError(f"{label} does not exist: {path}")
    return path


def pixel_bbox(bbox: list[float], image_size: list[int]) -> list[int]:
    return [
        round(bbox[0] * image_size[0]),
        round(bbox[1] * image_size[1]),
        round(bbox[2] * image_size[0]),
        round(bbox[3] * image_size[1]),
    ]


def pixel_polygon(
    polygon: list[list[float]], image_size: list[int]
) -> list[list[int]]:
    return [
        [round(point[0] * image_size[0]), round(point[1] * image_size[1])]
        for point in polygon
    ]


def screen_region(entity: dict, image_size: list[int]) -> dict:
    screen = entity["screen"]
    return {
        "bbox": screen["bbox"],
        "pixelBBox": pixel_bbox(screen["bbox"], image_size),
        "semanticId": screen["semanticId"],
        "semanticColor": screen["semanticColor"],
        "visiblePixelCount": screen["visiblePixelCount"],
        "coverage": screen["coverage"],
        "maskRef": "entitySemanticMask",
    }


def same_vector(left: list[float], right: list[float], tolerance: float = 1e-6) -> bool:
    return (
        len(left) == len(right)
        and all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))
    )


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_closed_world_policy() -> dict:
    policy_path = Path(__file__).resolve().parent.parent / "assets/closed-world-view-policy.v1.json"
    policy = load_json(policy_path)
    assert policy.get("schema") == "interior.closed-world-view-policy.v1"
    return policy


def native_projection_audit(
    shot: dict, visible: list[dict], projected_connections: list[dict]
) -> dict:
    """Prove that every camera-plan anchor and must-show element exists in-frame."""
    minimum_margin = 0.06
    anchor_ids = shot["framing"]["envelopes"]["anchor"]["elementIds"]
    visible_by_id = {entity["sourceModelId"]: entity for entity in visible}
    visible_source_ids = set(visible_by_id)
    visible_source_ids.update(
        connection["sourceModelId"]
        for connection in projected_connections
        if connection.get("screen", {}).get("bbox")
    )
    regions = []
    missing = []
    for anchor_id in anchor_ids:
        entity = visible_by_id.get(anchor_id)
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
    must_show_ids = shot.get("mustShowElements", [])
    missing_must_show = sorted(set(must_show_ids) - visible_source_ids)
    audit = {
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
    if not audit["allAnchorElementsVisible"]:
        raise AssertionError(f"camera anchors are not all visible: {missing}")
    if not audit["allAnchorMarginsAccepted"]:
        rejected = [
            region["sourceModelId"]
            for region in regions
            if not region["marginAccepted"]
        ]
        raise AssertionError(
            f"camera anchors violate the {minimum_margin:.0%} native-frame margin: {rejected}"
        )
    if not audit["allMustShowElementsVisible"]:
        raise AssertionError(
            f"camera must-show elements are absent from the native frame: {missing_must_show}"
        )
    return audit


def build_closed_world_view(
    rooms: list[dict],
    connections: list[dict],
    structures: list[dict],
    placement_slots: list[dict],
    placement_relations: dict,
) -> dict:
    policy = load_closed_world_policy()
    boundary_terminations = []
    exterior_rules = policy["exteriorBoundaryRules"]
    for connection in connections:
        if "exterior" not in connection.get("roomIds", []):
            continue
        rule = exterior_rules.get(connection.get("kind"), exterior_rules["default"])
        interior_room_ids = sorted(
            room_id for room_id in connection.get("roomIds", []) if room_id != "exterior"
        )
        boundary_terminations.append(
            {
                "connectionId": connection["connectionId"],
                "kind": connection["kind"],
                "interiorRoomIds": interior_room_ids,
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
            for slot in placement_slots
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
            "placementSlotIds": sorted(slot["slotId"] for slot in placement_slots),
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
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: build_shot_scene_map.py "
            "<semantic-frame.json> <camera-plan.json> <shot-id> <out.json> "
            "<camera-plan-evidence.png>"
        )

    source_path = Path(sys.argv[1]).resolve()
    plan_path = Path(sys.argv[2]).resolve()
    shot_id = sys.argv[3]
    out_path = Path(sys.argv[4]).resolve()
    plan_evidence_path = Path(sys.argv[5]).resolve()
    source = load_json(source_path)
    plan = load_json(plan_path)

    assert source.get("schema") == SOURCE_SCHEMA
    assert source.get("shotId") == shot_id
    assert source.get("coordinateSystem") == "image-top-left-normalized"
    assert source.get("presentation", {}).get("defaultGenerationMode") == "slot-guided"
    assert source.get("presentation", {}).get("evidenceStates") == {
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
    }
    assert source.get("modelBackend") in BACKENDS
    assert source.get("projectionEvidence", {}).get("method") in PROJECTION_METHODS
    assert plan.get("schema") == "interior.camera-plan.v8"
    assert plan.get("coordinateSystem") == "interior-world-y-up.v1"
    assert source.get("modelBackend") == plan.get("modelBackend")
    assert source.get("sourceModelSha256") == plan.get("sourceModelSha256")
    circulation_descriptor = plan.get("circulationResult", {})
    circulation_path = (plan_path.parent / circulation_descriptor.get("path", "")).resolve()
    assert circulation_path.is_file()
    assert sha256(circulation_path) == circulation_descriptor.get("sha256")
    circulation = load_json(circulation_path)
    assert circulation.get("schema") == "interior.circulation-result.v2"
    assert circulation.get("resultDigestSha256") == circulation_descriptor.get("resultDigestSha256")
    assert circulation.get("bindings", {}).get("nativeModelSha256") == plan.get("sourceModelSha256")
    seed_descriptor = plan.get("frontalSeedSet", {})
    seed_path = (plan_path.parent / seed_descriptor.get("path", "")).resolve()
    assert seed_path.is_file()
    assert sha256(seed_path) == seed_descriptor.get("sha256")
    seed_set = load_json(seed_path)
    assert seed_set.get("schema") == "interior.camera-frontal-seed-set.v1"
    assert seed_set.get("seedSetDigestSha256") == seed_descriptor.get("seedSetDigestSha256")
    shot = next((item for item in plan.get("shots", []) if item.get("shotId") == shot_id), None)
    assert shot is not None, f"shot not found in camera plan: {shot_id}"
    assert source.get("floorplanId") == plan.get("floorplanId")
    source_camera = source.get("camera", {})
    assert same_vector(source_camera.get("position", []), shot["position"]), (
        "same-frame camera position differs from camera plan"
    )
    assert same_vector(source_camera.get("target", []), shot["target"]), (
        "same-frame camera target differs from camera plan"
    )
    assert abs(float(source_camera.get("fov", 0)) - float(shot["fov"])) <= 1e-6
    camera = dict(source_camera)
    camera["position"] = shot["position"]
    camera["target"] = shot["target"]
    camera["fov"] = shot["fov"]
    camera["focalLengthMm"] = shot["focalLengthMm"]

    source_dir = source_path.parent
    slot_guided_image_path = require_file(
        source_dir, source["guidanceImages"]["slotGuided"], "slot-guided image"
    )
    entity_semantic_mask_path = require_file(
        source_dir, source["entitySemanticMask"]["image"], "entity semantic ID mask"
    )
    room_semantic_mask_path = require_file(
        source_dir, source["roomSemanticMask"]["image"], "room semantic ID mask"
    )
    white_model_image_path = require_file(
        source_dir,
        source["guidanceImages"]["furnishedQa"],
        "furnished QA image",
    )
    assert plan_evidence_path.is_file(), plan_evidence_path
    plan_evidence_json_path = plan_evidence_path.with_suffix(".json")
    assert plan_evidence_json_path.is_file(), plan_evidence_json_path
    plan_evidence = load_json(plan_evidence_json_path)
    assert plan_evidence.get("schema") == "interior.camera-plan-evidence.v2"
    assert plan_evidence.get("source") == "same-native-model-camera-state"
    assert plan_evidence.get("modelBackend") == plan.get("modelBackend")
    assert plan_evidence.get("sourceModelSha256") == plan.get("sourceModelSha256")
    assert plan_evidence.get("shotId") == shot_id
    assert plan_evidence.get("position") == shot["position"]
    assert plan_evidence.get("target") == shot["target"]
    assert plan_evidence.get("fov") == shot["fov"]
    assert plan_evidence.get("focalLengthMm") == shot["focalLengthMm"]

    out_path.parent.mkdir(parents=True, exist_ok=True)

    def bundle(source_file: Path) -> Path:
        target = out_path.parent / source_file.name
        if target.resolve() != source_file.resolve():
            shutil.copy2(source_file, target)
        return target

    slot_guided_image_path = bundle(slot_guided_image_path)
    white_model_image_path = bundle(white_model_image_path)
    entity_semantic_mask_path = bundle(entity_semantic_mask_path)
    room_semantic_mask_path = bundle(room_semantic_mask_path)
    plan_evidence_path = bundle(plan_evidence_path)
    plan_evidence_json_path = bundle(plan_evidence_json_path)
    source_path = bundle(source_path)
    bundled_circulation_path = bundle(circulation_path)
    bundled_seed_path = bundle(seed_path)
    visibility_policy = load_policy(Path(__file__).resolve().parent.parent)
    connection_pixel_audits = audit_connection_opening_pixels(
        source, entity_semantic_mask_path, visibility_policy
    )
    visible_frame = compile_visible_frame(
        source, shot["roomId"], visibility_policy, connection_pixel_audits
    )
    visible = visible_frame["visibleEntities"]
    included_source_rooms = visible_frame["includedRooms"]
    included_source_connections = visible_frame["includedConnections"]
    visible_room_ids = {room["roomId"] for room in included_source_rooms}
    capture_scope = plan.get("captureScope")
    source_model_scope = source.get("modelScope")
    if source.get("modelBackend") == "html-threejs":
        assert source_model_scope is not None, "HTML semantic frame must carry modelScope"
        assert source_model_scope.get("schema") == "interior.model-scope.v1"
        assert source_model_scope.get("sameTemplateAsWholeFloor") is True
        assert source_model_scope.get("customProjectGeometryAllowed") is False
    if capture_scope is not None:
        allowed_scope_room_ids = set(capture_scope.get("requestedRoomIds", [])) | set(
            capture_scope.get("allowedContextRoomIds", [])
        )
        unexpected_visible_rooms = sorted(visible_room_ids - allowed_scope_room_ids)
        if unexpected_visible_rooms:
            raise AssertionError(
                "current camera exposes rooms outside the accepted model/capture scope: "
                + ", ".join(unexpected_visible_rooms)
            )
        if source_model_scope is not None:
            for key in (
                "requestedRoomIds",
                "allowedContextRoomIds",
                "excludedRoomIds",
            ):
                if set(capture_scope.get(key, [])) != set(source_model_scope.get(key, [])):
                    raise AssertionError(
                        f"camera captureScope.{key} differs from the native model scope"
                    )
    projection_audit = native_projection_audit(
        shot, visible, included_source_connections
    )
    bundled_plan_path = out_path.parent / f"{shot_id}.camera-plan.v8.json"
    bundled_plan = dict(plan)
    bundled_plan["circulationResult"] = dict(plan["circulationResult"])
    bundled_plan["circulationResult"]["path"] = bundled_circulation_path.name
    bundled_plan["frontalSeedSet"] = dict(plan["frontalSeedSet"])
    bundled_plan["frontalSeedSet"]["path"] = bundled_seed_path.name
    bundled_plan_path.write_text(
        json.dumps(bundled_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rooms = []
    connections = []
    structures = []
    placement_slots = []
    room_region_source = (
        "same-step-topology-visible-surface-membership"
        if source["modelBackend"] == "cad-step"
        else "same-frame-depth-reprojection-to-room-polygon"
    )

    for entity in visible:
        region = screen_region(entity, source["imageSize"])
        semantic_type = entity["semanticType"]
        if semantic_type == "structure":
            structure_room_ids = sorted(
                set(entity.get("roomIds", [])) & visible_room_ids
            )
            assert structure_room_ids, (
                f"{entity['sourceModelId']}: visible structure has no current-frame room owner"
            )
            structures.append(
                {
                    "structureId": entity["sourceModelId"],
                    "kind": entity["category"],
                    "roomIds": structure_room_ids,
                    "region": region,
                }
            )
        elif semantic_type in {"movable-furniture", "fixed-cabinet"}:
            assert entity.get("assetId"), f"{entity['sourceModelId']}: missing assetId"
            assert entity.get("functionalClass"), f"{entity['sourceModelId']}: missing functionalClass"
            assert entity.get("quantity") == 1, f"{entity['sourceModelId']}: quantity must be 1"
            component_room_ids = [
                room_id
                for room_id in entity.get("roomIds", [])
                if room_id in visible_room_ids
            ]
            assert len(component_room_ids) == 1, (
                f"{entity['sourceModelId']}: component must resolve to exactly one current-frame room"
            )
            placement_slots.append(
                {
                    "slotId": entity["sourceModelId"],
                    "objectClass": semantic_type,
                    "category": entity["category"],
                    "functionalClass": entity["functionalClass"],
                    "quantity": entity["quantity"],
                    "assetId": entity["assetId"],
                    "sourceObjectCandidateId": entity.get("sourceObjectCandidateId"),
                    "localAxes": entity.get("localAxes", {}),
                    "roomId": component_room_ids[0],
                    "dimensionsMeters": entity["dimensionsMeters"],
                    "worldBounds": entity["worldBounds"],
                    "worldTransform": entity["worldTransform"],
                    "region": region,
                    "guidanceAvailability": {
                        "slot-guided": {
                            "componentVisible": False,
                            "slotFactsRetained": True,
                        },
                    },
                    "appearanceAuthority": "user-asset-if-provided-otherwise-style-constrained-free",
                    "slotLock": {
                        "position": True,
                        "footprint": True,
                        "orientation": True,
                        "category": True,
                        "clearance": True,
                    },
                    "geometryPolicy": (
                        "cabinet-location-footprint-orientation-category-clearance-locked-shape-flexible"
                        if semantic_type == "fixed-cabinet"
                        else "furniture-location-footprint-orientation-category-clearance-locked"
                    ),
                    "mustPreserve": bool(entity.get("mustPreserve")),
                }
            )

    for room in included_source_rooms:
        room_id = room["roomId"]
        screen = room["screen"]
        rooms.append(
            {
                "roomId": room_id,
                "name": room["displayName"],
                "roomType": room["roomType"],
                "role": "primary" if room_id == shot["roomId"] else "adjacent-visible",
                "region": {
                    "bbox": screen["bbox"],
                    "pixelBBox": pixel_bbox(screen["bbox"], source["imageSize"]),
                    "semanticId": screen["semanticId"],
                    "semanticColor": screen["semanticColor"],
                    "visiblePixelCount": screen["visiblePixelCount"],
                    "coverage": screen["coverage"],
                    "maskRef": "roomSemanticMask",
                    "source": room_region_source,
                },
            }
        )

    primary_room = next((room for room in rooms if room["role"] == "primary"), None)
    if not primary_room:
        raise AssertionError(
            "The primary room has no visible pixels after exact depth reprojection"
        )

    for connection in included_source_connections:
        screen = connection["screen"]
        connections.append(
            {
                "connectionId": connection["sourceModelId"],
                "kind": connection["kind"],
                "openingStyle": connection.get("openingStyle"),
                "roomIds": connection["roomIds"],
                "region": {
                    "polygon": screen["polygon"],
                    "pixelPolygon": pixel_polygon(
                        screen["polygon"], source["imageSize"]
                    ),
                    "bbox": screen["bbox"],
                    "pixelBBox": pixel_bbox(screen["bbox"], source["imageSize"]),
                    "source": screen["source"],
                    "visibilityEvidence": {
                        "frontProjection": screen["visibilityEvidence"],
                        "semanticOpening": connection_pixel_audits[
                            connection["sourceModelId"]
                        ],
                    },
                },
                "forbiddenInferences": connection.get(
                    "forbiddenInferences", []
                ),
            }
        )

    semantic_ids = [
        entity["screen"]["semanticId"]
        for entity in visible
    ]
    semantic_colors = [
        entity["screen"]["semanticColor"]
        for entity in visible
    ]
    assert len(semantic_ids) == len(set(semantic_ids)), "duplicate semantic IDs"
    assert len(semantic_colors) == len(set(semantic_colors)), "duplicate semantic colors"
    visible_slot_ids = {slot["slotId"] for slot in placement_slots}
    visible_structure_ids = {structure["structureId"] for structure in structures}
    visible_asset_ids = {slot["assetId"] for slot in placement_slots}
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
            if set(row.get("roomIds", [])).issubset(visible_room_ids)
        ],
    }
    closed_world_view = build_closed_world_view(
        rooms, connections, structures, placement_slots, placement_relations
    )
    prompt_room_mask_path = out_path.parent / f"{shot_id}.prompt-room-id.png"
    slot_guided_concrete_path = out_path.parent / f"{shot_id}.slot-guided-concrete.png"
    build_prompt_room_mask(
        room_semantic_mask_path,
        included_source_rooms,
        visibility_policy,
        prompt_room_mask_path,
    )
    build_pure_concrete_structure(slot_guided_image_path, slot_guided_concrete_path)
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
    visibility_audit_path = (
        out_path.parent / f"{shot_id}.visibility-audit.v1.json"
    )
    visibility_audit = {
        "schema": "interior.shot-visibility-audit.v1",
        "shotId": shot_id,
        "modelBackend": plan["modelBackend"],
        "sourceModelSha256": plan["sourceModelSha256"],
        "sourceSemanticFrame": {
            "file": source_path.name,
            "sha256": sha256(source_path),
        },
        "policyVersion": visible_frame["policyVersion"],
        "policyDigestSha256": visible_frame["policyDigestSha256"],
        "includedRoomIds": sorted(room["roomId"] for room in rooms),
        "includedConnectionIds": sorted(
            connection["connectionId"] for connection in connections
        ),
        "decisions": visible_frame["decisions"],
        "connectionPixelAudits": connection_pixel_audits,
        "submissionPolicy": "qa-only-never-submit-to-image-model",
    }
    visibility_audit_path.write_text(
        json.dumps(visibility_audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = {
        "schema": OUTPUT_SCHEMA,
        "modelBackend": plan["modelBackend"],
        "sourceModelSha256": plan["sourceModelSha256"],
        "floorplanId": source["floorplanId"],
        "modelRevision": source["modelRevision"],
        "modelScope": source_model_scope,
        "shotId": shot_id,
        "imageSize": source["imageSize"],
        "semanticRaster": source["semanticRaster"],
        "coordinateSystem": source["coordinateSystem"],
        "guidance": {
            "mediaKind": "space-screenshot",
            "defaultMode": "slot-guided",
            "availableModes": ["slot-guided"],
            "selectionOwner": "interior-space-rendering/render-plan.v11",
            "style": {
                "state": "none",
                "styleId": "none",
                "name": "无风格",
            },
            "semanticSource": source["projectionEvidence"]["method"],
            "modePresentation": {
                "slot-guided": {
                    "components": "hidden-facts-retained-in-json-only",
                    "structureAppearance": "concrete-shell-including-concrete-floor",
                },
            },
            "fourQuadrantContract": {
                "schema": "interior.render-four-quadrant.v1",
                "quadrants": [
                    "q1-slot-guided-concrete-camera",
                    "q2-furnished-same-camera-reference",
                    "q3-plan-camera-frustum",
                    "q4-accepted-render",
                ],
                "sameShotCameraAndModelRequired": True,
            },
        },
        "camera": camera,
        "circulationBinding": {
            "resultSha256": circulation_descriptor["sha256"],
            "resultDigestSha256": circulation["resultDigestSha256"],
            "topologyAuditDigestSha256": circulation["bindings"]["topologyAuditDigestSha256"],
            "layoutRelationshipAuditDigestSha256": circulation["bindings"]["layoutRelationshipAuditDigestSha256"],
        },
        "primaryRoomId": shot["roomId"],
        "shotContract": {
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
        },
        "visibleRoomIds": sorted(room["roomId"] for room in rooms),
        "visibleFrame": {
            "schema": visible_frame["schema"],
            "policyVersion": visible_frame["policyVersion"],
            "policyDigestSha256": visible_frame["policyDigestSha256"],
            "includedRoomIds": sorted(room["roomId"] for room in rooms),
            "includedConnectionIds": sorted(
                connection["connectionId"] for connection in connections
            ),
            "decisions": prompt_decisions,
            "promptRule": (
                "Prompt-facing scene maps contain included current-camera facts only. "
                "Full inclusion and exclusion diagnostics live only in the QA visibility audit "
                "and must never be submitted to the image model."
            ),
        },
        "rooms": rooms,
        "connections": connections,
        "structures": structures,
        "placementSlots": placement_slots,
        "placementRelations": placement_relations,
        "closedWorldView": closed_world_view,
        "renderPolicy": {
            "locked": [
                "camera",
                "image-coordinate-system",
                "room-regions",
                "connections",
                "walls",
                "windows",
                "placement-slot-position",
                "placement-slot-footprint",
                "placement-slot-orientation",
                "placement-slot-category",
                "placement-slot-clearance",
                "closed-world-required-sets",
                "closed-world-forbidden-sets",
                "exterior-boundary-termination",
            ],
            "freeWhenNoUserAsset": [
                "listed-placement-slot-product-appearance",
                "listed-fixed-cabinet-detail-within-locked-slot",
                "materials-and-colors-within-target-style",
                "allowed-nonstructural-additions-only",
            ],
            "neverInfer": sorted(
                set(closed_world_view["forbidden"]["inferenceClasses"])
                | {
                    item
                    for connection in connections
                    for item in connection.get("forbiddenInferences", [])
                }
            ),
        },
        "assets": {
            "slotGuidedConcreteImage": {
                "file": slot_guided_concrete_path.name,
                "sha256": sha256(slot_guided_concrete_path),
                "role": "q1-generation-input-pure-concrete-structure",
            },
            "furnishedReferenceImage": {
                "file": white_model_image_path.name,
                "sha256": sha256(white_model_image_path),
                "role": "q2-qa-only-same-camera-furniture-and-cabinet-reference",
            },
            "planCameraImage": {
                "file": plan_evidence_path.name,
                "sha256": sha256(plan_evidence_path),
                "role": "q3-plan-camera-frustum-evidence-only",
            },
            "planCameraJson": {
                "file": plan_evidence_json_path.name,
                "sha256": sha256(plan_evidence_json_path),
                "role": "same-native-model-camera-facts-only",
            },
            "entitySemanticMask": {
                "file": entity_semantic_mask_path.name,
                "sha256": sha256(entity_semantic_mask_path),
                "encoding": source["entitySemanticMask"]["encoding"],
                "role": "qa-only-entity-coordinate-evidence-never-submit-to-image-model",
            },
            "roomSemanticMask": {
                "file": prompt_room_mask_path.name,
                "sha256": sha256(prompt_room_mask_path),
                "encoding": source["roomSemanticMask"]["encoding"],
                "role": "qa-only-room-coordinate-evidence-never-submit-to-image-model",
            },
            "sourceRoomSemanticMask": {
                "file": room_semantic_mask_path.name,
                "sha256": sha256(room_semantic_mask_path),
                "encoding": source["roomSemanticMask"]["encoding"],
                "role": "qa-only-unfiltered-native-room-mask",
            },
            "semanticFrame": {
                "file": source_path.name,
                "sha256": sha256(source_path),
            },
            "cameraPlan": {
                "file": bundled_plan_path.name,
                "sha256": sha256(bundled_plan_path),
                "role": "native-anchor-and-camera-contract",
            },
            "visibilityAudit": {
                "file": visibility_audit_path.name,
                "sha256": sha256(visibility_audit_path),
                "role": "qa-only-never-submit-to-image-model",
            },
        },
        "sourceEvidence": {
            "projectionMethod": source["projectionEvidence"]["method"],
            "projectionElapsedMs": source["projectionEvidence"].get("elapsedMs"),
            "cpuReadbackBytes": source["projectionEvidence"].get("cpuReadbackBytes"),
            "generatedMaskBytes": source["projectionEvidence"].get("generatedMaskBytes"),
            "renderTargetBytes": source["projectionEvidence"].get("renderTargetBytes"),
            "entityIdPassMs": source["projectionEvidence"].get("entityIdPassMs"),
            "roomDepthPassMs": source["projectionEvidence"].get("roomDepthPassMs"),
            "roomReprojectionMs": source["projectionEvidence"].get("roomReprojectionMs"),
            "roomOverlapRule": source["projectionEvidence"].get("overlapRule"),
            "roomSearchDirection": source["projectionEvidence"].get("roomSearchDirection"),
            "maximumRoomSearchDistanceMeters": source["projectionEvidence"].get("maximumRoomSearchDistanceMeters"),
            "roomSearchStepMeters": source["projectionEvidence"].get("roomSearchStepMeters"),
            "entityCountInModelFrame": len(source.get("entities", [])),
            "visibleEntityCount": len(visible),
        },
        "slotProjectionAudit": {
            "sourceVisibleComponentCount": len(
                [
                    entity
                    for entity in visible
                    if entity["semanticType"]
                    in {"movable-furniture", "fixed-cabinet"}
                ]
            ),
            "mappedSlotCount": len(placement_slots),
            "missingSourceModelIds": [],
            "extraSlotIds": [],
            "exactMatch": True,
        },
        "nativeProjectionAudit": projection_audit,
        "interpretationConstraints": source.get("interpretationConstraints", []),
        "review": {
            "schema": "interior.scene-map-agent-review.v2",
            "status": "pending",
            "reviewerInvocationId": None,
            "sourceInvocationId": plan.get("producerInvocationId"),
            "evidence": [],
            "observedRoomIds": [],
            "observedConnectionIds": [],
            "observedStructureIds": [],
            "observedPlacementSlotIds": [],
            "unexpectedRoomIds": [],
            "unexpectedConnectionIds": [],
            "unexpectedStructureIds": [],
            "unexpectedPlacementSlotIds": [],
            "closedWorldContractAccepted": None,
            "decision": None,
            "notes": [],
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
