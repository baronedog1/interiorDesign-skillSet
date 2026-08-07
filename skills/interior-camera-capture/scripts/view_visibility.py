#!/usr/bin/env python3
"""Compile prompt-visible rooms, connections and pure structure evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageDraw


POLICY_SCHEMA = "interior.view-visibility-policy.v1"
COMPONENT_TYPES = {"movable-furniture", "fixed-cabinet"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_policy(skill_root: Path) -> dict[str, Any]:
    policy = load_json(skill_root / "assets/view-visibility-policy.v1.json")
    if policy.get("schema") != POLICY_SCHEMA:
        raise ValueError("view visibility policy schema mismatch")
    return policy


def valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and 0 <= value[0] < value[2] <= 1
        and 0 <= value[1] < value[3] <= 1
    )


def visible_entities(source: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entity
        for entity in source.get("entities", [])
        if entity.get("screen", {}).get("visiblePixelCount", 0) > 0
        and valid_bbox(entity.get("screen", {}).get("bbox"))
    ]


def audit_connection_opening_pixels(
    source: dict[str, Any], entity_mask_path: Path, policy: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Measure whether each projected opening is actually covered by a wall."""
    rules = policy["connectionInclusion"]
    categories = set(rules["occludingStructureCategories"])
    occluding_colors = {
        _rgb(entity["screen"]["semanticColor"])
        for entity in source.get("entities", [])
        if entity.get("semanticType") == "structure"
        and entity.get("category") in categories
        and entity.get("screen", {}).get("semanticColor")
    }
    with Image.open(entity_mask_path) as opened:
        image = opened.convert("RGB")
    image_pixels = image.load()
    audits: dict[str, dict[str, Any]] = {}
    for connection in source.get("connections", []):
        connection_id = connection.get("sourceModelId") or connection.get("connectionId")
        polygon = connection.get("screen", {}).get("polygon")
        if not isinstance(polygon, list) or len(polygon) < 3:
            audits[connection_id] = {
                "method": "normalized-entity-mask-opening-occlusion-v1",
                "semanticMaskSize": [image.width, image.height],
                "samplePixelCount": 0,
                "occludingStructurePixelCount": 0,
                "occludingStructureRatio": 1.0,
                "maximumOccludingStructureRatio": rules["maximumOccludingStructureRatio"],
                "minimumOpeningSamplePixelCount": rules["minimumOpeningSamplePixelCount"],
                "passed": False,
            }
            continue
        raster_polygon = [
            [
                min(image.width - 1, max(0, round(float(point[0]) * (image.width - 1)))),
                min(image.height - 1, max(0, round(float(point[1]) * (image.height - 1)))),
            ]
            for point in polygon
        ]
        polygon_mask = Image.new("1", image.size, 0)
        ImageDraw.Draw(polygon_mask).polygon(
            [tuple(point) for point in raster_polygon], fill=1
        )
        mask_pixels = polygon_mask.load()
        xs = [point[0] for point in raster_polygon]
        ys = [point[1] for point in raster_polygon]
        sample_count = 0
        occluding_count = 0
        for y in range(min(ys), max(ys) + 1):
            for x in range(min(xs), max(xs) + 1):
                if not mask_pixels[x, y]:
                    continue
                sample_count += 1
                if image_pixels[x, y] in occluding_colors:
                    occluding_count += 1
        ratio = occluding_count / sample_count if sample_count else 1.0
        audits[connection_id] = {
            "method": "normalized-entity-mask-opening-occlusion-v1",
            "semanticMaskSize": [image.width, image.height],
            "rasterPolygon": raster_polygon,
            "samplePixelCount": sample_count,
            "occludingStructurePixelCount": occluding_count,
            "occludingStructureRatio": round(ratio, 6),
            "maximumOccludingStructureRatio": rules["maximumOccludingStructureRatio"],
            "minimumOpeningSamplePixelCount": rules["minimumOpeningSamplePixelCount"],
            "passed": (
                sample_count >= rules["minimumOpeningSamplePixelCount"]
                and ratio <= rules["maximumOccludingStructureRatio"]
            ),
        }
    return audits


def compile_visible_frame(
    source: dict[str, Any],
    primary_room_id: str,
    policy: dict[str, Any],
    connection_pixel_audits: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entities = visible_entities(source)
    functional_room_ids = {
        room_id
        for entity in entities
        if entity.get("semanticType") in COMPONENT_TYPES
        for room_id in entity.get("roomIds", [])
    }
    thresholds = policy["roomInclusion"]
    included_rooms: list[dict[str, Any]] = []
    excluded_rooms: list[dict[str, Any]] = []
    for room in source.get("rooms", []):
        screen = room.get("screen", {})
        bbox = screen.get("bbox")
        has_pixels = screen.get("visiblePixelCount", 0) > 0 and valid_bbox(bbox)
        width = bbox[2] - bbox[0] if valid_bbox(bbox) else 0
        height = bbox[3] - bbox[1] if valid_bbox(bbox) else 0
        primary = room.get("roomId") == primary_room_id
        functional = room.get("roomId") in functional_room_ids
        readable = (
            has_pixels
            and screen.get("coverage", 0) >= thresholds["minimumReadableCoverage"]
            and width >= thresholds["minimumReadableWidthRatio"]
            and height >= thresholds["minimumReadableHeightRatio"]
            and screen.get("visiblePixelCount", 0) >= thresholds["minimumVisiblePixelCount"]
        )
        include = has_pixels and (primary or functional or readable)
        decision = {
            "roomId": room.get("roomId"),
            "included": include,
            "reason": (
                "primary-visible-room"
                if primary and has_pixels
                else "contains-visible-functional-object"
                if functional and has_pixels
                else "readable-native-room-region"
                if readable
                else "camera-rear-outside-occluded-or-unreadable-edge-fragment"
            ),
            "visiblePixelCount": screen.get("visiblePixelCount", 0),
            "coverage": screen.get("coverage", 0),
            "bbox": bbox,
        }
        (included_rooms if include else excluded_rooms).append({"room": room, "decision": decision})
    if not any(row["room"].get("roomId") == primary_room_id for row in included_rooms):
        raise ValueError("primary room has no prompt-visible native pixels")

    included_room_ids = {row["room"]["roomId"] for row in included_rooms}
    included_connections: list[dict[str, Any]] = []
    excluded_connections: list[dict[str, Any]] = []
    for connection in source.get("connections", []):
        connection_id = connection.get("sourceModelId") or connection.get("connectionId")
        screen = connection.get("screen", {})
        interior_endpoints = {
            room_id for room_id in connection.get("roomIds", []) if room_id != "exterior"
        }
        visibility = screen.get("visibilityEvidence", {})
        projected = valid_bbox(screen.get("bbox")) and isinstance(screen.get("polygon"), list)
        front_visible = (
            screen.get("source") == "front-clipped-projected-model-opening-corners"
            and visibility.get("method") == "all-opening-corners-in-front-of-camera"
            and visibility.get("allCornersInFrontOfCamera") is True
            and visibility.get("minimumForwardDepthMeters", 0) > 0
        )
        semantic_audit = connection_pixel_audits.get(connection_id, {})
        semantic_visible = (
            semantic_audit.get("method")
            == "normalized-entity-mask-opening-occlusion-v1"
            and semantic_audit.get("passed") is True
        )
        include = (
            bool(interior_endpoints)
            and interior_endpoints.issubset(included_room_ids)
            and projected
            and front_visible
            and semantic_visible
        )
        decision = {
            "connectionId": connection_id,
            "included": include,
            "reason": (
                "all-visible-endpoints-with-front-projected-unoccluded-opening"
                if include
                else "no-complete-front-projected-unoccluded-current-frame-opening-evidence"
            ),
            "interiorEndpointRoomIds": sorted(interior_endpoints),
            "semanticOpeningAudit": semantic_audit,
        }
        (included_connections if include else excluded_connections).append(
            {"connection": connection, "decision": decision}
        )

    return {
        "schema": "interior.prompt-visible-frame.v1",
        "policyVersion": policy["policyVersion"],
        "policyDigestSha256": canonical_sha256(policy),
        "includedRooms": [row["room"] for row in included_rooms],
        "includedConnections": [row["connection"] for row in included_connections],
        "connectionPixelAudits": connection_pixel_audits,
        "visibleEntities": entities,
        "decisions": {
            "rooms": [row["decision"] for row in included_rooms + excluded_rooms],
            "connections": [
                row["decision"] for row in included_connections + excluded_connections
            ],
        },
    }


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(hex_color)


def build_prompt_room_mask(
    source_mask: Path,
    included_rooms: list[dict[str, Any]],
    policy: dict[str, Any],
    out_path: Path,
) -> None:
    with Image.open(source_mask) as opened:
        image = opened.convert("RGB")
    allowed = {_rgb(row["screen"]["semanticColor"]) for row in included_rooms}
    background = _rgb(policy["promptMask"]["excludedRoomColor"])
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x, y] not in allowed:
                pixels[x, y] = background
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", optimize=True)


def build_pure_concrete_structure(source_image: Path, out_path: Path) -> None:
    """Copy the same-camera concrete shell without drawing component hints."""
    with Image.open(source_image) as opened:
        base = opened.convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_path, format="PNG", optimize=True)
