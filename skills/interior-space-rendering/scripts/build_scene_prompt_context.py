#!/usr/bin/env python3
"""Build render-media-context.v7 from render-plan.v11 and scene-map.v9."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from render_contract import (
    validate_closed_world_view,
    validate_execution_policy,
    validate_projection_lock,
    validate_scene_camera_authority,
    validate_space_reference_plan,
)
from validate_user_product_reference_manifest import validate_manifest as validate_product_manifest


PLAN_SCHEMA = "interior.model-image-render-plan.v11"
MAP_SCHEMA = "interior.shot-scene-map.v9"
CONTEXT_SCHEMA = "interior.render-media-context.v7"
MODES = {"slot-guided"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(path: Path, root: Path) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


if len(sys.argv) != 6:
    raise SystemExit(
        "usage: build_scene_prompt_context.py "
        "<render-plan.v11.json> <shot-id> <style-id> <style-name> <out.json>"
    )

plan_path = Path(sys.argv[1]).resolve()
shot_id = sys.argv[2]
style_id = sys.argv[3]
style_name = sys.argv[4].strip()
output_path = Path(sys.argv[5]).resolve()
plan = load_json(plan_path)
assert plan.get("schema") == PLAN_SCHEMA
assert plan.get("schemaVersion") == "11.0"
assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", shot_id)
assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", style_id)
assert style_name
assert style_id in plan.get("requestedStyles", [])
planned_output = next(
    (
        output
        for output in plan.get("outputs", [])
        if output.get("shotId") == shot_id and output.get("styleId") == style_id
    ),
    None,
)
assert planned_output is not None, "render plan has no output for this shot/style"
architectural_treatment = planned_output.get("architecturalTreatment")
assert isinstance(architectural_treatment, dict)
render_execution_policy = validate_execution_policy(plan.get("renderExecutionPolicy"))

selected = next(
    (item for item in plan.get("selectedShots", []) if item.get("shotId") == shot_id),
    None,
)
assert selected is not None, f"shot is not selected: {shot_id}"
guidance = selected.get("guidance", {})
mode = guidance.get("mode")
assert mode in MODES
assert guidance.get("selectionSource") == "system-default"
assert guidance.get("userConfirmation") is None
guidance_name = "槽位引导模式"
source_component_presentation = "hidden"
source_structure_appearance = "concrete-shell-including-concrete-floor"
target_shape_policy = "style-product-inside-locked-slot"
structure_asset_key = "slotGuidedConcreteImage"
structure_role = "current-shot-concrete-structure-camera-authority"
furnished_asset_key = "furnishedReferenceImage"
furnished_role = "current-shot-furnished-layout-qa-only"

scene_map_path = (plan_path.parent / selected["sourceSceneMap"]).resolve()
assert scene_map_path.is_file()
assert sha256(scene_map_path) == selected["sourceSceneMapSha256"]
scene_map = load_json(scene_map_path)
assert scene_map.get("schema") == MAP_SCHEMA
assert scene_map.get("floorplanId") == plan.get("floorplanId")
assert scene_map.get("shotId") == shot_id
assert scene_map.get("modelBackend") == selected.get("modelBackend")
assert scene_map.get("sourceModelSha256") == selected.get("sourceModelSha256")
assert scene_map.get("review", {}).get("status") == "accepted"
assert scene_map.get("guidance", {}).get("defaultMode") == "slot-guided"
assert scene_map.get("guidance", {}).get("availableModes") == ["slot-guided"]
assert scene_map.get("guidance", {}).get("selectionOwner") == (
    "interior-space-rendering/render-plan.v11"
)
assert scene_map.get("guidance", {}).get("modePresentation") == {
    "slot-guided": {
        "components": "hidden-facts-retained-in-json-only",
        "structureAppearance": "concrete-shell-including-concrete-floor",
    },
}
assert scene_map.get("closedWorldView", {}).get("schema") == (
    "interior.closed-world-view.v1"
)
assert scene_map["closedWorldView"].get("policyVersion") == "1.0"
validate_closed_world_view(scene_map)
camera_authority = validate_scene_camera_authority(scene_map, scene_map_path)
validate_projection_lock(architectural_treatment.get("projectionLock"), scene_map)
all_scene_maps = {}
for plan_shot in plan.get("selectedShots", []):
    candidate_path = (plan_path.parent / plan_shot["sourceSceneMap"]).resolve()
    assert candidate_path.is_file()
    assert sha256(candidate_path) == plan_shot["sourceSceneMapSha256"]
    candidate = load_json(candidate_path)
    assert candidate.get("schema") == MAP_SCHEMA
    all_scene_maps[plan_shot["shotId"]] = candidate
validate_space_reference_plan(plan, all_scene_maps)

product_manifest_descriptor = plan.get("userProductReferenceManifest")
product_manifest = None
product_manifest_path = None
product_binding_by_slot: dict[str, dict] = {}
product_by_id: dict[str, dict] = {}
product_reference_by_id: dict[str, dict] = {}
if product_manifest_descriptor is not None:
    assert isinstance(product_manifest_descriptor, dict)
    product_manifest_path = (plan_path.parent / product_manifest_descriptor["path"]).resolve()
    assert product_manifest_path.is_file()
    assert sha256(product_manifest_path) == product_manifest_descriptor["sha256"]
    all_visible_slot_ids = {
        slot["slotId"]
        for candidate in all_scene_maps.values()
        for slot in candidate.get("placementSlots", [])
    }
    product_manifest = validate_product_manifest(
        product_manifest_path,
        expected_floorplan_id=plan["floorplanId"],
        allowed_slot_ids=all_visible_slot_ids,
        require_exact_slots=product_manifest_descriptor.get("required") is True,
    )
    product_reference_by_id = {
        row["referenceId"]: row for row in product_manifest["references"]
    }
    for reference in product_manifest["references"]:
        for product in reference["products"]:
            product_by_id[product["productId"]] = {
                **product,
                "referenceId": reference["referenceId"],
                "imageSha256": reference["sha256"],
            }
    product_binding_by_slot = {
        row["slotId"]: row for row in product_manifest["slotBindings"]
    }

output_path.parent.mkdir(parents=True, exist_ok=True)
scene_root = scene_map_path.parent
assets = scene_map["assets"]
assert assets[structure_asset_key].get("role") == (
    "q1-generation-input-pure-concrete-structure"
)
assert assets[furnished_asset_key].get("role") == (
    "q2-qa-only-same-camera-furniture-and-cabinet-reference"
)
assert assets["visibilityAudit"].get("role") == (
    "qa-only-never-submit-to-image-model"
)
for key in (
    structure_asset_key,
    furnished_asset_key,
    "entitySemanticMask",
    "roomSemanticMask",
    "semanticFrame",
    "visibilityAudit",
):
    asset_path = (scene_root / assets[key]["file"]).resolve()
    assert asset_path.is_file(), asset_path
    assert sha256(asset_path) == assets[key]["sha256"], asset_path


def room_value(room: dict) -> dict:
    return {
        "roomId": room["roomId"],
        "name": room["name"],
        "roomType": room["roomType"],
        "role": room["role"],
        "region": room["region"],
    }


def slot_value(slot: dict, target: bool) -> dict:
    lock = slot.get("slotLock", {})
    value = {
        "slotId": slot["slotId"],
        "roomId": slot["roomId"],
        "category": slot["category"],
        "functionalClass": slot["functionalClass"],
        "quantity": slot["quantity"],
        "assetId": slot["assetId"],
        "sourceObjectCandidateId": slot.get("sourceObjectCandidateId"),
        "localAxes": slot.get("localAxes", {}),
        "objectClass": slot["objectClass"],
        "dimensionsMeters": slot["dimensionsMeters"],
        "worldBounds": slot["worldBounds"],
        "worldTransform": slot["worldTransform"],
        "imageRegion": slot["region"],
        "positionLocked": lock.get("position") is True,
        "footprintLocked": lock.get("footprint") is True,
        "orientationLocked": lock.get("orientation") is True,
        "categoryLocked": lock.get("category") is True,
        "clearanceLocked": lock.get("clearance") is True,
    }
    if target:
        binding = product_binding_by_slot.get(slot["slotId"])
        value["appearance"] = {
            "authority": slot["appearanceAuthority"],
            "styleId": style_id,
            "shapePolicy": target_shape_policy,
            "assetSelection": (
                "exact-user-product-reference"
                if binding is not None
                else "style-constrained-free"
            ),
        }
        if binding is not None:
            product = product_by_id[binding["productId"]]
            assert product["functionalClass"] == slot["functionalClass"], (
                f"{slot['slotId']}: user product class differs from the slot class"
            )
            value["appearance"]["userProductReference"] = {
                "referenceId": binding["referenceId"],
                "productId": binding["productId"],
                "sourceRegionNormalized": product["sourceRegionNormalized"],
                "exactProductIdentityRequired": True,
            }
    else:
        value["appearance"] = {
            "state": "slot-fact-with-component-hidden",
            "componentVisible": False,
        }
    return value


shared_media = {
    "width": scene_map["imageSize"][0],
    "height": scene_map["imageSize"][1],
    "aspectRatio": f"{scene_map['imageSize'][0]}:{scene_map['imageSize'][1]}",
    "orientation": (
        "landscape"
        if scene_map["imageSize"][0] >= scene_map["imageSize"][1]
        else "portrait"
    ),
    "view": {
        "shotId": shot_id,
        "camera": scene_map["camera"],
        "coordinateSystem": scene_map["coordinateSystem"],
        "semanticRaster": scene_map["semanticRaster"],
    },
}
space_layout = {
    "primaryRoomId": scene_map["primaryRoomId"],
    "rooms": [room_value(room) for room in scene_map["rooms"]],
    "connections": scene_map["connections"],
    "cameraAndRegionsLocked": True,
    "circulationBinding": scene_map["circulationBinding"],
    "closedWorldView": scene_map["closedWorldView"],
    "placementRelations": scene_map["placementRelations"],
}
hard_decoration = {
    "structures": scene_map["structures"],
    "locked": True,
    "sourceAppearance": source_structure_appearance,
    "sourceAppearanceIsGuidanceOnly": True,
}
source_soft_decoration = {
    "componentPresentation": source_component_presentation,
    "placementSlots": [
        slot_value(slot, target=False) for slot in scene_map["placementSlots"]
    ],
}
target_soft_decoration = {
    "componentPresentation": "render-from-slots",
    "placementSlots": [
        slot_value(slot, target=True) for slot in scene_map["placementSlots"]
    ],
}

structure_image_path = (scene_root / assets[structure_asset_key]["file"]).resolve()
furnished_image_path = (scene_root / assets[furnished_asset_key]["file"]).resolve()
source_media_id = f"{shot_id}-{mode}"
target_media_id = f"{shot_id}-{style_id}"
original_media_info = {
    "schemaVersion": "media_info.v1",
    "basicInfo": {
        "mediaInfoId": f"mediainfo-{source_media_id}",
        "mediaId": source_media_id,
        "mediaKind": "image",
        "mediaSubType": "spatial_photo",
        "mimeType": "image/png",
        "infoState": "observed",
        "confidence": "high",
        "source": {
            "domain": "project_asset",
            "storagePath": relative_path(structure_image_path, output_path.parent),
        },
    },
    "media": {
        **shared_media,
        "sourcePresentation": "slot-guided-concrete-camera-authority",
        "guidanceModeName": guidance_name,
        "componentPresentation": source_component_presentation,
        "structureAppearance": source_structure_appearance,
    },
    "spaceLayout": space_layout,
    "hardDecoration": hard_decoration,
    "softDecoration": source_soft_decoration,
    "style": {"state": "none", "styleId": "none", "name": "无风格"},
    "lighting": {
        "state": "model-check-light",
        "purpose": "structure-readability-only",
    },
}
target_media_info = {
    "schemaVersion": "media_info.v1",
    "basicInfo": {
        "mediaInfoId": f"mediainfo-{target_media_id}",
        "mediaId": target_media_id,
        "mediaKind": "image",
        "mediaSubType": "spatial_render_image",
        "mimeType": "image/png",
        "infoState": "intended",
        "confidence": "target",
        "source": {"domain": "generation_target"},
    },
    "media": {
        **shared_media,
        "sourcePresentation": "photorealistic-interior-render",
        "guidanceMode": mode,
        "componentPresentation": target_soft_decoration[
            "componentPresentation"
        ],
    },
    "spaceLayout": space_layout,
    "hardDecoration": {
        **hard_decoration,
        "treatment": architectural_treatment,
    },
    "softDecoration": target_soft_decoration,
    "style": {
        "state": "intended",
        "styleId": style_id,
        "name": style_name,
    },
    "lighting": {
        "state": "intended",
        "policy": (
            "preserve opening directions; use natural architectural light and "
            "restrained fill; avoid clipped white surfaces and muddy shadows"
        ),
    },
}


def attachment(
    file_path: Path,
    role: str,
    send: bool,
    source_asset: dict | None = None,
    reference_id: str | None = None,
    covered_room_ids: list[str] | None = None,
    covered_slot_ids: list[str] | None = None,
) -> dict:
    value = {
        "path": relative_path(file_path, output_path.parent),
        "attachmentLabel": file_path.name,
        "role": role,
        "sha256": (
            source_asset["sha256"] if source_asset is not None else sha256(file_path)
        ),
        "sendToImageModel": send,
    }
    if reference_id is not None:
        value["referenceId"] = reference_id
    if covered_room_ids is not None:
        value["coveredRoomIds"] = covered_room_ids
    if covered_slot_ids is not None:
        value["coveredSlotIds"] = covered_slot_ids
    return value


reference_row = next(
    row
    for row in plan["spaceReferencePlan"]["shots"]
    if row["shotId"] == shot_id
)
identity_references = []
identity_attachments = []
for dependency_shot_id in reference_row["dependsOnAcceptedShotIds"]:
    dependency_output = next(
        row
        for row in plan["outputs"]
        if row["shotId"] == dependency_shot_id and row["styleId"] == style_id
    )
    assert dependency_output.get("status") == "accepted", (
        f"{shot_id}: identity dependency {dependency_shot_id} is not accepted"
    )
    dependency_image = (plan_path.parent / dependency_output["outputImage"]).resolve()
    assert dependency_image.is_file()
    assert sha256(dependency_image) == dependency_output["outputImageSha256"]
    dependency_reference_row = next(
        row
        for row in plan["spaceReferencePlan"]["shots"]
        if row["shotId"] == dependency_shot_id
    )
    shared_rooms = sorted(
        set(reference_row["visibleRoomIds"])
        & set(dependency_reference_row["visibleRoomIds"])
    )
    shared_slots = sorted(
        set(reference_row["visibleSlotIds"])
        & set(dependency_reference_row["visibleSlotIds"])
    )
    identity_references.append(
        {
            "referenceShotId": dependency_shot_id,
            "imageSha256": dependency_output["outputImageSha256"],
            "coveredRoomIds": shared_rooms,
            "coveredSlotIds": shared_slots,
            "authority": "appearance-and-object-identity-only",
            "neverAuthorityFor": ["current-camera", "current-crop", "walls", "openings"],
        }
    )
    identity_attachments.append(
        attachment(
            dependency_image,
            "accepted-space-identity-reference",
            True,
            reference_id=dependency_shot_id,
            covered_room_ids=shared_rooms,
            covered_slot_ids=shared_slots,
        )
    )


current_slot_ids = {slot["slotId"] for slot in scene_map["placementSlots"]}
user_product_references = []
product_attachments = []
if product_manifest is not None and product_manifest_path is not None:
    bindings = [
        row for row in product_manifest["slotBindings"] if row["slotId"] in current_slot_ids
    ]
    bindings_by_reference: dict[str, list[dict]] = {}
    for binding in bindings:
        product = product_by_id[binding["productId"]]
        user_product_references.append(
            {
                "slotId": binding["slotId"],
                "referenceId": binding["referenceId"],
                "productId": binding["productId"],
                "functionalClass": product["functionalClass"],
                "sourceRegionNormalized": product["sourceRegionNormalized"],
                "imageSha256": product["imageSha256"],
                "authority": "exact-product-identity-and-appearance-only",
                "neverAuthorityFor": [
                    "camera",
                    "crop",
                    "architecture",
                    "room-topology",
                    "slot-position-footprint-orientation",
                ],
            }
        )
        bindings_by_reference.setdefault(binding["referenceId"], []).append(binding)
    for reference_id, reference_bindings in sorted(bindings_by_reference.items()):
        reference = product_reference_by_id[reference_id]
        reference_path = (product_manifest_path.parent / reference["path"]).resolve()
        product_attachments.append(
            attachment(
                reference_path,
                "user-product-reference",
                True,
                reference,
                reference_id=reference_id,
                covered_slot_ids=sorted(row["slotId"] for row in reference_bindings),
            )
        )
    user_product_references.sort(key=lambda row: row["slotId"])


attachment_manifest = [
    attachment(
        structure_image_path,
        structure_role,
        True,
        assets[structure_asset_key],
    ),
    attachment(
        furnished_image_path,
        furnished_role,
        False,
        assets[furnished_asset_key],
    ),
] + product_attachments + [
    attachment(scene_map_path, "shot-scene-map", True),
    attachment(
        scene_root / assets["entitySemanticMask"]["file"],
        "entity-semantic-mask-qa-only",
        False,
        assets["entitySemanticMask"],
    ),
    attachment(
        scene_root / assets["roomSemanticMask"]["file"],
        "room-semantic-mask-qa-only",
        False,
        assets["roomSemanticMask"],
    ),
    attachment(
        scene_root / assets["semanticFrame"]["file"],
        "model-projection-evidence-qa-only",
        False,
        assets["semanticFrame"],
    ),
] + identity_attachments

context = {
    "schema": CONTEXT_SCHEMA,
    "sourceRenderPlan": {
        "file": plan_path.name,
        "schema": PLAN_SCHEMA,
        "shotId": shot_id,
    },
    "renderId": planned_output["renderId"],
    "sourceSceneMap": {
        "file": relative_path(scene_map_path, output_path.parent),
        "sha256": sha256(scene_map_path),
        "floorplanId": scene_map["floorplanId"],
        "modelRevision": scene_map["modelRevision"],
        "shotId": shot_id,
        "modelBackend": scene_map["modelBackend"],
        "sourceModelSha256": scene_map["sourceModelSha256"],
        "circulationBinding": scene_map["circulationBinding"],
        "cameraAuthority": camera_authority,
    },
    "closedWorldView": scene_map["closedWorldView"],
    "guidanceSelection": {
        "mode": mode,
        "name": guidance_name,
        "selectionSource": guidance["selectionSource"],
        "userConfirmation": guidance["userConfirmation"],
        "sourceImageRoles": [structure_role],
        "structureAppearance": source_structure_appearance,
    },
    "spaceIdentityReferences": identity_references,
    "userProductReferences": user_product_references,
    "renderExecutionPolicy": render_execution_policy,
    "moduleSelection": {
        "readFromOriginal": [
            "spaceLayout",
            "hardDecoration",
            "softDecoration",
            "style",
            "lighting",
        ],
        "writeToTarget": ["media", "hardDecoration.finish", "softDecoration", "style", "lighting"],
        "reason": (
            "Keep camera, room regions, openings, structure and placement slots "
            "unchanged; apply only the selected guidance mode."
        ),
    },
    "originalMediaInfo": original_media_info,
    "targetMediaInfo": target_media_info,
    "architecturalTreatment": architectural_treatment,
    "transition": {
        "changedModules": ["media", "hardDecoration.finish", "softDecoration", "style", "lighting"],
        "changedObjectIds": [
            slot["slotId"] for slot in scene_map["placementSlots"]
        ],
        "preservedModules": ["spaceLayout", "hardDecoration.geometry"],
    },
    "attachmentManifest": attachment_manifest,
    "imageModelInstruction": {
        "sourceOfTruth": (
            "The closedWorldView is the complete current-shot inventory. Use its "
            "required sets, forbidden inference classes and boundary terminations; "
            "do not identify rooms, openings or slots by guessing from the screenshot."
        ),
        "projectionLock": architectural_treatment["projectionLock"],
        "renderExecutionPolicy": render_execution_policy,
        "currentShotAuthority": {
            "cameraAndArchitecture": structure_role,
            "functionalObjectLayout": "shot-scene-map-placement-slots-and-relations-json",
            "componentShape": "style-constrained-inside-json-slot",
            "userProductReferences": "exact-product-identity-and-appearance-for-bound-slots-only",
            "priorAcceptedImages": "appearance-and-object-identity-only",
        },
        "guidanceMode": mode,
        "guidanceRule": (
            "Use the concrete-shell structural image only as camera and architectural "
            "geometry authority. Rebuild every functional object from the exact JSON "
            "slot facts; never use the furnished QA image as model input."
        ),
        "assetFreedom": (
            "Use the exact user-supplied product identity and appearance for every bound slot. "
            "Only unbound listed slots may use style-compatible products. A missing slot means "
            "the functional object is absent; never invent a replacement for a bound product."
        ),
        "architecturalStyling": (
            "Apply the explicit architecturalTreatment. Preserve every current-model "
            "opening, wall, ceiling and balcony enclosure. Window frames, glazing, curtains, "
            "surface finishes, existing door-leaf state, luminaires and non-structural decor "
            "may change only within that treatment. Any geometry change requires a new accepted "
            "upstream model revision before rendering."
        ),
        "neverChange": scene_map["renderPolicy"]["locked"],
        "neverInfer": scene_map["renderPolicy"]["neverInfer"],
        "requiredInventory": scene_map["closedWorldView"]["required"],
        "boundaryTerminations": scene_map["closedWorldView"]["boundaryTerminations"],
        "allowedAdditions": scene_map["closedWorldView"]["additionPolicy"],
        "visibleText": "none",
        "modeSwitching": "forbidden",
    },
}

output_path.write_text(
    json.dumps(context, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(
    json.dumps(
        {
            "ok": True,
            "schema": CONTEXT_SCHEMA,
            "shotId": shot_id,
            "styleId": style_id,
            "guidanceMode": mode,
            "bytes": output_path.stat().st_size,
            "rooms": len(scene_map["rooms"]),
            "slots": len(scene_map["placementSlots"]),
        },
        ensure_ascii=False,
    )
)
