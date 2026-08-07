#!/usr/bin/env python3
"""Shared deterministic helpers for the render request and review gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCENE_MAP_SCHEMA = "interior.shot-scene-map.v9"
CONTEXT_SCHEMA = "interior.render-media-context.v7"
EXECUTION_POLICY_SCHEMA = "interior.render-execution-policy.v2"
PROJECTION_LOCK_METHOD = "complete-scene-map-region-correspondence-v1"

PROJECTION_LIMITS = {
    "maximumCameraKeypointError": 0.02,
    "maximumWallLineAngleErrorDeg": 1.0,
    "maximumObjectCenterError": 0.02,
    "maximumObjectRegionEdgeError": 0.025,
    "maximumObjectOrientationErrorDeg": 3.0,
    "maximumStructureRegionEdgeError": 0.02,
    "maximumConnectionRegionEdgeError": 0.02,
}

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_scene_camera_authority(
    scene_map: dict[str, Any], scene_map_path: Path
) -> dict[str, Any]:
    """Bind rendering to the exact formal concrete capture and camera plan."""
    if scene_map.get("schema") != SCENE_MAP_SCHEMA:
        raise ValueError(f"camera authority requires {SCENE_MAP_SCHEMA}")
    scene_root = scene_map_path.resolve().parent
    assets = scene_map.get("assets", {})
    required = {
        "slotGuidedConcreteImage": "q1-generation-input-pure-concrete-structure",
        "planCameraImage": "q3-plan-camera-frustum-evidence-only",
        "planCameraJson": "same-native-model-camera-facts-only",
        "cameraPlan": "native-anchor-and-camera-contract",
    }
    paths: dict[str, Path] = {}
    for key, role in required.items():
        descriptor = assets.get(key)
        if not isinstance(descriptor, dict) or descriptor.get("role") != role:
            raise ValueError(f"scene map lacks formal {key} authority")
        target = (scene_root / descriptor.get("file", "")).resolve()
        if not target.is_file() or sha256_file(target) != descriptor.get("sha256"):
            raise ValueError(f"scene map {key} authority is missing or stale")
        paths[key] = target
    plan = load_json(paths["cameraPlan"])
    evidence = load_json(paths["planCameraJson"])
    if (
        plan.get("schema") != "interior.camera-plan.v8"
        or plan.get("schemaVersion") != "8.0"
        or plan.get("methodVersion") != "deterministic-wall-normal-camera-v7"
        or plan.get("modelBackend") != scene_map.get("modelBackend")
        or plan.get("sourceModelSha256") != scene_map.get("sourceModelSha256")
    ):
        raise ValueError("scene map camera plan is not the formal deterministic plan")
    shot = next(
        (
            row
            for row in plan.get("shots", [])
            if row.get("shotId") == scene_map.get("shotId")
            and row.get("selectionStatus") == "selected"
        ),
        None,
    )
    if shot is None:
        raise ValueError("scene map shot is not selected in its formal camera plan")
    camera = scene_map.get("camera", {})
    for field in ("position", "target", "fov", "focalLengthMm"):
        if camera.get(field) != shot.get(field) or evidence.get(field) != shot.get(field):
            raise ValueError(f"render camera authority drifted at {field}")
    if (
        evidence.get("schema") != "interior.camera-plan-evidence.v2"
        or evidence.get("source") != "same-native-model-camera-state"
        or evidence.get("shotId") != scene_map.get("shotId")
    ):
        raise ValueError("camera evidence did not come from the formal capture adapter")
    if (
        scene_map.get("modelBackend") == "html-threejs"
        and evidence.get("runtimeCameraPlanSource") != "external-formal-camera-plan-v8"
    ):
        raise ValueError("HTML camera evidence bypassed the external formal camera plan")
    contract = scene_map.get("shotContract", {})
    if shot.get("role") == "primary":
        if (
            shot.get("composition") != "one-point-frontal"
            or contract.get("wallNormalFrontal") is not True
            or contract.get("referenceWallId")
            != shot.get("frontalAlignment", {}).get("referenceWallId")
        ):
            raise ValueError("every primary render needs the accepted wall-normal frontal camera")
    return {
        "shotId": shot["shotId"],
        "role": shot.get("role"),
        "composition": shot.get("composition"),
        "cameraPlanSha256": sha256_file(paths["cameraPlan"]),
        "concreteReferenceSha256": sha256_file(paths["slotGuidedConcreteImage"]),
    }


def verify_document_digest(document: dict[str, Any], key: str) -> None:
    expected = document.get(key)
    unsigned = dict(document)
    unsigned[key] = None
    if expected != canonical_sha256(unsigned):
        raise ValueError(f"invalid {key}")


def exact_unique_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(row, str) or not row for row in value):
        raise ValueError(f"{label} must be a string list")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def _region_rows(scene_map: dict[str, Any], collection: str, id_key: str) -> list[dict[str, Any]]:
    rows = []
    for row in scene_map.get(collection, []):
        region = row.get("region")
        bbox = region.get("bbox") if isinstance(region, dict) else None
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in bbox)
        ):
            raise ValueError(f"{collection}.{row.get(id_key)} requires a normalized bbox")
        rows.append({id_key: row[id_key], "bbox": [float(value) for value in bbox]})
    return sorted(rows, key=lambda value: value[id_key])


def derive_projection_lock(scene_map: dict[str, Any]) -> dict[str, Any]:
    """Compile the immutable image-space contract directly from one scene map."""
    if scene_map.get("schema") != SCENE_MAP_SCHEMA:
        raise ValueError(f"projection lock requires {SCENE_MAP_SCHEMA}")
    return {
        "method": PROJECTION_LOCK_METHOD,
        "shotId": scene_map.get("shotId"),
        "sourceModelSha256": scene_map.get("sourceModelSha256"),
        "imageSize": scene_map.get("imageSize"),
        "roomRegionBBoxes": _region_rows(scene_map, "rooms", "roomId"),
        "structureRegionBBoxes": _region_rows(scene_map, "structures", "structureId"),
        "connectionRegionBBoxes": _region_rows(scene_map, "connections", "connectionId"),
        "placementSlotRegionBBoxes": _region_rows(scene_map, "placementSlots", "slotId"),
        "imageTransformPolicy": {
            "recompose": "forbidden",
            "recrop": "forbidden",
            "rescaleSceneWithinFrame": "forbidden",
            "translateSceneWithinFrame": "forbidden",
            "duplicateOrRemoveRequiredRegion": "forbidden",
        },
        "reviewLimits": PROJECTION_LIMITS,
    }


def validate_projection_lock(value: Any, scene_map: dict[str, Any]) -> dict[str, Any]:
    expected = derive_projection_lock(scene_map)
    if value != expected:
        raise ValueError("architecturalTreatment.projectionLock differs from the scene-map-derived contract")
    return expected


def validate_execution_policy(value: Any) -> dict[str, Any]:
    expected = {
        "schema": EXECUTION_POLICY_SCHEMA,
        "primaryProducer": "imagegen-closed-world",
        "maximumImagegenCandidatesPerFrontalMaster": 3,
        "onImagegenExhaustion": "stop-without-q4-delivery",
        "q4ProducerRequirement": "imagegen-receipt-only",
        "thresholdRelaxation": "forbidden",
        "nativeSceneFallback": "forbidden",
    }
    if value != expected:
        raise ValueError("renderExecutionPolicy must stop without Q4 after finite imagegen rejection")
    return expected


def validate_closed_world_view(scene_map: dict[str, Any]) -> dict[str, Any]:
    closed_world = scene_map.get("closedWorldView")
    if not isinstance(closed_world, dict) or closed_world.get("schema") != "interior.closed-world-view.v1":
        raise ValueError("scene map requires interior.closed-world-view.v1")
    if closed_world.get("policyVersion") != "1.0":
        raise ValueError("unsupported closed-world policy version")
    digest = closed_world.get("policyDigestSha256", "")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("closed-world policy digest is missing")
    required = closed_world.get("required")
    if not isinstance(required, dict):
        raise ValueError("closed-world required sets are missing")
    expected_sets = {
        "roomIds": sorted(row["roomId"] for row in scene_map.get("rooms", [])),
        "connectionIds": sorted(row["connectionId"] for row in scene_map.get("connections", [])),
        "structureIds": sorted(row["structureId"] for row in scene_map.get("structures", [])),
        "placementSlotIds": sorted(row["slotId"] for row in scene_map.get("placementSlots", [])),
    }
    for key, expected in expected_sets.items():
        actual = exact_unique_strings(required.get(key), f"closedWorldView.required.{key}")
        if actual != expected:
            raise ValueError(f"closed-world {key} does not exactly match the scene map")
    visible_room_ids = exact_unique_strings(
        scene_map.get("visibleRoomIds"), "sceneMap.visibleRoomIds"
    )
    if visible_room_ids != expected_sets["roomIds"]:
        raise ValueError("visibleRoomIds must exactly equal the prompt-facing room inventory")
    visible_room_set = set(visible_room_ids)
    visible_frame = scene_map.get("visibleFrame")
    if not isinstance(visible_frame, dict):
        raise ValueError("scene map requires a prompt-facing visibleFrame")
    if visible_frame.get("includedRoomIds") != expected_sets["roomIds"]:
        raise ValueError("visibleFrame room IDs differ from the closed-world inventory")
    if visible_frame.get("includedConnectionIds") != expected_sets["connectionIds"]:
        raise ValueError("visibleFrame connection IDs differ from the closed-world inventory")
    decisions = visible_frame.get("decisions")
    if not isinstance(decisions, dict):
        raise ValueError("visibleFrame decisions are missing")
    room_decisions = decisions.get("rooms")
    connection_decisions = decisions.get("connections")
    if not isinstance(room_decisions, list) or not isinstance(connection_decisions, list):
        raise ValueError("visibleFrame decisions must enumerate rooms and connections")
    if any(row.get("included") is not True for row in room_decisions + connection_decisions):
        raise ValueError("prompt-facing scene maps must not contain excluded diagnostic facts")
    decision_room_ids = exact_unique_strings(
        [row.get("roomId") for row in room_decisions], "visibleFrame room decisions"
    )
    decision_connection_ids = exact_unique_strings(
        [row.get("connectionId") for row in connection_decisions],
        "visibleFrame connection decisions",
    )
    if sorted(decision_room_ids) != expected_sets["roomIds"]:
        raise ValueError("visibleFrame room decisions differ from the current-shot inventory")
    if sorted(decision_connection_ids) != expected_sets["connectionIds"]:
        raise ValueError("visibleFrame connection decisions differ from the current-shot inventory")
    for structure in scene_map.get("structures", []):
        structure_room_ids = exact_unique_strings(
            structure.get("roomIds"), f"structure {structure.get('structureId')} roomIds"
        )
        if structure_room_ids != sorted(structure_room_ids) or not structure_room_ids:
            raise ValueError("every visible structure requires sorted current-frame room ownership")
        if not set(structure_room_ids) <= visible_room_set:
            raise ValueError("visible structure room ownership leaks an out-of-frame room")
    for slot in scene_map.get("placementSlots", []):
        if slot.get("roomId") not in visible_room_set:
            raise ValueError("placement slot belongs to an out-of-frame room")
    for connection in scene_map.get("connections", []):
        connection_room_ids = exact_unique_strings(
            connection.get("roomIds"), f"connection {connection.get('connectionId')} roomIds"
        )
        if not {
            room_id for room_id in connection_room_ids if room_id != "exterior"
        } <= visible_room_set:
            raise ValueError("connection references an out-of-frame room")
    visibility_audit = scene_map.get("assets", {}).get("visibilityAudit")
    if not isinstance(visibility_audit, dict) or visibility_audit.get("role") != (
        "qa-only-never-submit-to-image-model"
    ):
        raise ValueError("scene map requires a physically separate QA-only visibility audit")
    inventory = required.get("placementSlotInventory")
    expected_inventory = sorted(
        (
            {
                "slotId": row["slotId"],
                "functionalClass": row["functionalClass"],
                "quantity": row["quantity"],
                "roomId": row["roomId"],
            }
            for row in scene_map.get("placementSlots", [])
        ),
        key=lambda row: row["slotId"],
    )
    if inventory != expected_inventory:
        raise ValueError("closed-world slot inventory differs from placementSlots")
    placement_relations = scene_map.get("placementRelations")
    if not isinstance(placement_relations, dict) or placement_relations.get("schema") != (
        "interior.layout-relation-hints.v2"
    ):
        raise ValueError("scene map requires filtered placement relations")
    if required.get("placementRelations") != placement_relations:
        raise ValueError("closed-world placement relations differ from the scene map")
    forbidden = closed_world.get("forbidden", {})
    inference_classes = exact_unique_strings(
        forbidden.get("inferenceClasses"), "closedWorldView.forbidden.inferenceClasses"
    )
    required_forbidden = {
        "unlisted-room",
        "unlisted-interior-space",
        "unlisted-structure",
        "unlisted-door",
        "unlisted-window",
        "unlisted-open-passage",
        "unlisted-placement-slot",
        "unlisted-movable-furniture",
        "unlisted-fixed-cabinet",
        "unlisted-appliance-or-fixture",
        "interior-room-beyond-exterior-boundary",
    }
    if not required_forbidden.issubset(set(inference_classes)):
        raise ValueError("closed-world forbidden inference classes are incomplete")
    if not isinstance(forbidden.get("rule"), str) or not forbidden["rule"].strip():
        raise ValueError("closed-world absence rule is missing")
    connection_by_id = {
        row["connectionId"]: row for row in scene_map.get("connections", [])
    }
    expected_boundary_ids = {
        row["connectionId"]
        for row in scene_map.get("connections", [])
        if "exterior" in row.get("roomIds", [])
    }
    boundaries = closed_world.get("boundaryTerminations")
    if not isinstance(boundaries, list):
        raise ValueError("closed-world boundary terminations must be a list")
    boundary_ids = [row.get("connectionId") for row in boundaries]
    if len(boundary_ids) != len(set(boundary_ids)) or set(boundary_ids) != expected_boundary_ids:
        raise ValueError("closed-world exterior boundary set differs from scene connections")
    for boundary in boundaries:
        connection = connection_by_id[boundary["connectionId"]]
        if boundary.get("kind") != connection.get("kind") or boundary.get("farSide") != "exterior":
            raise ValueError("closed-world boundary identity differs from its connection")
        expected_rooms = sorted(room_id for room_id in connection.get("roomIds", []) if room_id != "exterior")
        if boundary.get("interiorRoomIds") != expected_rooms:
            raise ValueError("closed-world exterior boundary interior side differs")
        allowed = exact_unique_strings(boundary.get("allowedDepictions"), "boundary.allowedDepictions")
        forbidden_depictions = exact_unique_strings(
            boundary.get("forbiddenDepictions"), "boundary.forbiddenDepictions"
        )
        if not allowed or "interior-room-continuation" not in forbidden_depictions:
            raise ValueError("exterior boundary must have finite depictions and forbid interior continuation")
    additions = closed_world.get("additionPolicy", {})
    allowed_additions = exact_unique_strings(additions.get("allowedClasses"), "additionPolicy.allowedClasses")
    forbidden_additions = {
        "room", "door", "window", "open-passage", "movable-furniture",
        "fixed-cabinet", "appliance", "fixture",
    }
    if not allowed_additions or forbidden_additions & set(allowed_additions):
        raise ValueError("closed-world addition allowlist contains architectural or functional objects")
    for flag in (
        "mustRemainNonstructural",
        "mustNotCreateRoomOpeningOrPlacementSlot",
        "mustNotObstructExistingOpeningOrClearance",
    ):
        if additions.get(flag) is not True:
            raise ValueError(f"closed-world addition policy requires {flag}")
    return closed_world


def validate_space_reference_plan(
    plan: dict[str, Any], scene_maps: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    reference = plan.get("spaceReferencePlan")
    if not isinstance(reference, dict) or reference.get("schema") != "interior.space-reference-plan.v1":
        raise ValueError("render plan requires interior.space-reference-plan.v1")
    rows = reference.get("shots")
    if not isinstance(rows, list) or {row.get("shotId") for row in rows} != set(scene_maps):
        raise ValueError("space reference plan must enumerate every selected shot exactly once")
    if len(rows) != len({row.get("shotId") for row in rows}):
        raise ValueError("space reference plan contains duplicate shot IDs")
    row_by_id = {row["shotId"]: row for row in rows}
    batches = reference.get("executionBatches")
    if not isinstance(batches, list) or not batches or any(not isinstance(batch, list) or not batch for batch in batches):
        raise ValueError("space reference execution batches are missing")
    flat = [shot_id for batch in batches for shot_id in batch]
    if len(flat) != len(set(flat)) or set(flat) != set(scene_maps):
        raise ValueError("execution batches must schedule every shot exactly once")
    batch_index = {shot_id: index for index, batch in enumerate(batches) for shot_id in batch}
    for shot_id, scene in scene_maps.items():
        row = row_by_id[shot_id]
        if row.get("role") not in {"frontal-master", "relation"}:
            raise ValueError(f"{shot_id}: invalid reference role")
        expected_rooms = sorted(scene.get("visibleRoomIds", []))
        expected_slots = sorted(slot["slotId"] for slot in scene.get("placementSlots", []))
        if row.get("primaryRoomId") != scene.get("primaryRoomId"):
            raise ValueError(f"{shot_id}: primary room differs from the current scene map")
        if row.get("visibleRoomIds") != expected_rooms or row.get("visibleSlotIds") != expected_slots:
            raise ValueError(f"{shot_id}: reference inventory differs from the current scene map")
        dependencies = row.get("dependsOnAcceptedShotIds")
        if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)):
            raise ValueError(f"{shot_id}: dependencies must be a unique list")
        for dependency in dependencies:
            if dependency not in scene_maps or batch_index[dependency] >= batch_index[shot_id]:
                raise ValueError(f"{shot_id}: dependencies must come from earlier batches")
        if row["role"] == "relation" and not dependencies:
            raise ValueError(f"{shot_id}: relation shot has no accepted identity reference")
        if row["role"] == "frontal-master" and scene.get("shotContract", {}).get("wallNormalFrontal") is not True:
            raise ValueError(f"{shot_id}: frontal master is not a verified wall-normal shot")

    def overlaps(left: str, right: str) -> bool:
        a, b = row_by_id[left], row_by_id[right]
        return bool(
            set(a["visibleRoomIds"]) & set(b["visibleRoomIds"])
            or set(a["visibleSlotIds"]) & set(b["visibleSlotIds"])
        )

    for batch in batches:
        for index, left in enumerate(batch):
            for right in batch[index + 1 :]:
                if overlaps(left, right):
                    raise ValueError(
                        f"parallel shots {left} and {right} share visible spaces or slots"
                    )
    for later in flat:
        required = {
            earlier
            for earlier in flat
            if batch_index[earlier] < batch_index[later] and overlaps(earlier, later)
        }
        if set(row_by_id[later]["dependsOnAcceptedShotIds"]) != required:
            raise ValueError(
                f"{later}: dependencies must include every earlier overlapping accepted shot"
            )
    for room_id in {row["primaryRoomId"] for row in rows}:
        room_shots = [shot_id for shot_id in flat if row_by_id[shot_id]["primaryRoomId"] == room_id]
        if row_by_id[room_shots[0]]["role"] != "frontal-master":
            raise ValueError(f"{room_id}: first generated shot must be the frontal master")
    return reference


def scene_facts(scene_map: dict[str, Any]) -> dict[str, Any]:
    if scene_map.get("schema") != SCENE_MAP_SCHEMA:
        raise ValueError(f"scene map must use {SCENE_MAP_SCHEMA}")
    closed_world = validate_closed_world_view(scene_map)
    return {
        "schema": "interior.render-scene-facts.v4",
        "floorplanId": scene_map["floorplanId"],
        "shotId": scene_map["shotId"],
        "modelBackend": scene_map["modelBackend"],
        "sourceModelSha256": scene_map["sourceModelSha256"],
        "camera": scene_map["camera"],
        "primaryRoomId": scene_map["primaryRoomId"],
        "visibleRoomIds": scene_map["visibleRoomIds"],
        "circulationBinding": scene_map["circulationBinding"],
        "rooms": [
            {
                "roomId": row["roomId"],
                "roomType": row["roomType"],
                "role": row["role"],
                "region": row["region"],
            }
            for row in scene_map.get("rooms", [])
        ],
        "connections": [
            {
                "connectionId": row["connectionId"],
                "kind": row["kind"],
                "openingStyle": row.get("openingStyle"),
                "roomIds": row["roomIds"],
                "region": row["region"],
            }
            for row in scene_map.get("connections", [])
        ],
        "structures": [
            {
                "structureId": row["structureId"],
                "kind": row["kind"],
                "roomIds": row["roomIds"],
                "region": row["region"],
            }
            for row in scene_map.get("structures", [])
        ],
        "placementSlots": [
            {
                "slotId": row["slotId"],
                "sourceObjectCandidateId": row.get("sourceObjectCandidateId"),
                "assetId": row["assetId"],
                "category": row["category"],
                "functionalClass": row["functionalClass"],
                "quantity": row["quantity"],
                "roomId": row["roomId"],
                "dimensionsMeters": row["dimensionsMeters"],
                "worldTransform": row["worldTransform"],
                "imageRegion": row["region"],
                "localAxes": row.get("localAxes", {}),
                "slotLock": row["slotLock"],
            }
            for row in scene_map.get("placementSlots", [])
        ],
        "placementRelations": scene_map["placementRelations"],
        "closedWorldView": closed_world,
        "neverInfer": scene_map.get("renderPolicy", {}).get("neverInfer", []),
    }


def render_context_facts(context: dict[str, Any]) -> dict[str, Any]:
    if context.get("schema") != CONTEXT_SCHEMA:
        raise ValueError(f"render context must use {CONTEXT_SCHEMA}")
    required_objects = (
        "sourceSceneMap",
        "guidanceSelection",
        "architecturalTreatment",
        "renderExecutionPolicy",
        "imageModelInstruction",
    )
    for key in required_objects:
        if not isinstance(context.get(key), dict):
            raise ValueError(f"render context requires {key}")
    closed_world = context.get("closedWorldView")
    instruction = context["imageModelInstruction"]
    if not isinstance(closed_world, dict) or closed_world.get("schema") != "interior.closed-world-view.v1":
        raise ValueError("render context requires the scene closed-world view")
    if instruction.get("requiredInventory") != closed_world.get("required"):
        raise ValueError("render instruction required inventory differs from closed-world view")
    if instruction.get("boundaryTerminations") != closed_world.get("boundaryTerminations"):
        raise ValueError("render instruction boundary terminations differ from closed-world view")
    if instruction.get("allowedAdditions") != closed_world.get("additionPolicy"):
        raise ValueError("render instruction addition policy differs from closed-world view")
    execution_policy = validate_execution_policy(context.get("renderExecutionPolicy"))
    if instruction.get("renderExecutionPolicy") != execution_policy:
        raise ValueError("render instruction execution policy differs from the context")
    if instruction.get("projectionLock") != context["architecturalTreatment"].get("projectionLock"):
        raise ValueError("render instruction projection lock differs from architectural treatment")
    source = context["sourceSceneMap"]
    return {
        "schema": "interior.render-context-facts.v4",
        "sourceSceneMap": {
            "floorplanId": source.get("floorplanId"),
            "modelRevision": source.get("modelRevision"),
            "shotId": source.get("shotId"),
            "modelBackend": source.get("modelBackend"),
            "sourceModelSha256": source.get("sourceModelSha256"),
            "circulationBinding": source.get("circulationBinding"),
        },
        "guidanceSelection": context["guidanceSelection"],
        "architecturalTreatment": context["architecturalTreatment"],
        "renderExecutionPolicy": execution_policy,
        "targetStyle": context.get("targetMediaInfo", {}).get("style"),
        "spaceIdentityReferences": context.get("spaceIdentityReferences", []),
        "userProductReferences": context.get("userProductReferences", []),
    }


def compile_closed_world_prompt(
    scene_fact_document: dict[str, Any], context_fact_document: dict[str, Any]
) -> str:
    closed_world = scene_fact_document["closedWorldView"]
    required = closed_world["required"]
    additions = closed_world["additionPolicy"]
    guidance_mode = context_fact_document["guidanceSelection"]["mode"]
    if guidance_mode != "slot-guided":
        raise ValueError("slot-guided is the only image-generation mode")
    instructions = [
        "Render one photorealistic interior image from the supplied current-shot evidence and exact JSON facts.",
        "CAMERA AND STRUCTURE LOCK: strictly follow the supplied current-shot Q1 concrete image for camera pose, lens, crop, walls, ceiling volume, floor boundary, openings and all architectural geometry. Q1 contains no furniture, cabinet, slot silhouette or semantic overlay and is the only image authority for camera and architecture.",
        "VISIBLE SPACE ALLOWLIST: render only the rooms and connections enumerated in the JSON at their exact image regions. Any unlisted, rear-camera, out-of-frame, occluded or unreadable space is absent and must not appear.",
        "FUNCTIONAL OBJECT ALLOWLIST: render every placementSlots item exactly once with its JSON category, functional class, quantity, room, metric position, footprint, orientation, facing, wall attachment, relations and image region. No unlisted furniture, cabinet, appliance or fixture may appear.",
        "OPTIONAL ADDITIONS: add only a restrained amount of JSON-allowed nonstructural decor, wall art, luminaires, nonstructural ceiling detail and soft furnishing accessories. These additions may not create or move architecture, openings, functional objects or circulation boundaries.",
        "User product reference images control appearance and exact product identity only for their explicitly bound slot IDs; never copy their camera, crop, architecture or placement.",
        "Accepted prior-shot identity references preserve the same furniture and finish identity only; never copy their camera, crop, walls or openings into this shot.",
        "The model-derived closed-world view below is the complete current-shot inventory, not a suggestion.",
        "Render every listed room, connection, structure and placement slot exactly once where its region is visible.",
        "A zero-length required list means none of that object type may appear.",
        "Do not generate any unlisted room, interior continuation, wall opening, door, window, passage, furniture, cabinet, appliance or fixture.",
        "For each exterior boundary, use exactly one allowed depiction and never turn the far side into another interior room.",
        "Optional additions are limited to these nonstructural classes: " + ", ".join(additions["allowedClasses"]) + ".",
        "Optional additions must not create a room, opening or placement slot and must not block an existing opening or clearance.",
        "Preserve camera, image coordinates, object regions, quantities, categories, positions, footprints and orientations. Never redesign the floorplan.",
        "Obey the scene-map-derived projection lock exactly; do not recompose, recrop, rescale or translate the scene inside the frame.",
        "Apply only the structured target style and architectural treatment from the render context. Do not add a separate subject inventory.",
        "Required counts: rooms=" + str(len(required["roomIds"]))
        + ", connections=" + str(len(required["connectionIds"]))
        + ", structures=" + str(len(required["structureIds"]))
        + ", placementSlots=" + str(len(required["placementSlotIds"])) + ".",
    ]
    prompt = (
        "\n".join(instructions)
        + "\n\n[MODEL_DERIVED_SCENE_FACTS_JSON]\n"
        + canonical_json(scene_fact_document)
        + "\n[/MODEL_DERIVED_SCENE_FACTS_JSON]"
        + "\n\n[MODEL_DERIVED_RENDER_CONTEXT_FACTS_JSON]\n"
        + canonical_json(context_fact_document)
        + "\n[/MODEL_DERIVED_RENDER_CONTEXT_FACTS_JSON]"
    )
    if len(prompt.encode("utf-8")) > 32000:
        raise ValueError("compiled prompt exceeds the 32000-byte deterministic preflight limit")
    return prompt


def resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()
