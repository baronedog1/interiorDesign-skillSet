#!/usr/bin/env python3
"""Sole production camera solver for Interior Camera Capture 47.0.1.

Method: source-intent-fixture-facing-frontal-camera-v6

The selection hierarchy is contractual:

* every delivered view is selected from the strict wall-frontal candidate family;
* multiple views use different complete wall-frontal families or positions;
* no alternative pose class or degraded result can be selected.

No legacy camera pose or lens field is accepted in the semantic input.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from copy import deepcopy
import hashlib
import json
import math
import numpy as np
from pathlib import Path
import sys
import time
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from semantic_vtk_scene import CameraPose, SemanticVTKScene, point_segment_distance, projection_param

METHOD = "source-intent-fixture-facing-frontal-camera-v6"
VERSION = "47.0.1"

FORBIDDEN_INPUT_FIELDS = {
    "position",
    "target",
    "fov",
    "windowCenter",
    "referenceWallId",
    "horizontalLensShiftNormalized",
    "verticalLensShiftNormalized",
    "algorithmEvidence",
    "frontalContract",
    "cameraMode",
    "placementTier",
    "projectionCrop",
}

DIRECTIONAL_KINDS = {
    "living",
    "bedroom",
    "children-bedroom",
    "kitchen",
    "bathroom",
    "study",
    "closet",
    "laundry",
    "entry",
}

TARGET_PRIMARY_RATIO = {
    "kitchen": 0.14,
    "bathroom": 0.10,
    "bedroom": 0.13,
    "children-bedroom": 0.13,
    "living": 0.14,
    "dining": 0.13,
    "study": 0.12,
    "entry": 0.10,
    "corridor": 0.09,
    "balcony": 0.10,
    "laundry": 0.11,
    "closet": 0.12,
    "storage": 0.10,
    "gym": 0.13,
    "media": 0.14,
    "tea-room": 0.13,
    "unknown": 0.12,
}

MIN_PRIMARY_PIXEL_RATIO = 0.03
MIN_PRIMARY_BBOX_AREA = 0.05

CAMERA_HEIGHT = {
    "bathroom": 1.42,
    "balcony": 1.45,
    "laundry": 1.45,
    "bedroom": 1.50,
    "children-bedroom": 1.48,
    "living": 1.52,
    "dining": 1.52,
    "kitchen": 1.52,
    "study": 1.52,
    "entry": 1.52,
    "corridor": 1.52,
}


@dataclass(frozen=True)
class Box:
    id: str
    functional_class: str
    room_id: str
    x: float
    y: float
    z: float
    width: float
    height: float
    depth: float
    rotation_y: float

    @property
    def footprint_area(self) -> float:
        return self.width * self.depth

    @property
    def top(self) -> float:
        return self.y + self.height / 2

    @property
    def center3(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class WallFrame:
    index: int
    a: tuple[float, float]
    b: tuple[float, float]
    tangent: tuple[float, float]
    inward: tuple[float, float]
    length: float
    model_wall_id: str
    support_score: float
    has_opening: bool = False
    is_exterior: bool = False

    @property
    def optical_axis(self) -> tuple[float, float]:
        return (-self.inward[0], -self.inward[1])

    @property
    def angle_degrees(self) -> float:
        return math.degrees(math.atan2(self.optical_axis[1], self.optical_axis[0]))


@dataclass
class Candidate:
    room_id: str
    room_name: str
    room_kind: str
    mode: str
    target_wall: WallFrame
    position: tuple[float, float, float]
    forward: tuple[float, float]
    fov: float
    window_center: tuple[float, float]
    placement_tier: str
    primary_ids: list[str]
    companion_ids: list[str]
    framing_ids: list[str]
    primary_center: tuple[float, float, float]
    front_score: float
    semantic_axis_alignment: float
    semantic_axis_required: bool
    wall_alignment_error_degrees: float
    analytic_score: float
    analytic: dict[str, Any]
    hidden_wall_ids: tuple[str, ...] = ()
    hidden_opening_ids: tuple[str, ...] = ()
    hidden_element_ids: tuple[str, ...] = ()
    camera_inside_target_room: bool = True
    quality_preferred: bool = False
    final_score: float = -1e9
    pixel: dict[str, Any] = field(default_factory=dict)

    @property
    def pose(self) -> CameraPose:
        target = (
            self.position[0] + self.forward[0] * 2.0,
            self.position[1],
            self.position[2] + self.forward[1] * 2.0,
        )
        return CameraPose(
            position=self.position,
            target=target,
            fov=self.fov,
            window_center=self.window_center,
        )


# ----------------------------- generic geometry -----------------------------

def reject_camera_facts(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        bad = FORBIDDEN_INPUT_FIELDS.intersection(value)
        if bad:
            raise ValueError(f"Semantic input contains forbidden camera fields at {path}: {sorted(bad)}")
        for key, child in value.items():
            reject_camera_facts(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_camera_facts(child, f"{path}[{index}]")


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def get_shots(data: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    for key in ("shots", "cameraShots", "cameraPlan", "captures"):
        value = data.get(key)
        if isinstance(value, list):
            return key, value
    raise ValueError("No semantic room shot list found")


def normalize(x: float, z: float) -> tuple[float, float]:
    length = math.hypot(x, z)
    return (x / length, z / length) if length > 1e-9 else (0.0, 1.0)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def space_envelope_profile(room_kind: str, slenderness: float = 1.0) -> dict[str, float]:
    """Return formal-shot top/bottom space targets for a room.

    The profile is used by the sole solver during candidate generation and
    native-pixel validation.  Elongated rooms receive a slightly larger top
    target and more retreat tolerance inside the same strict-frontal solver.
    """
    base = {
        "bedroom": (0.080, 0.050, 0.150, 0.090),
        "children-bedroom": (0.080, 0.050, 0.150, 0.090),
        "bathroom": (0.070, 0.040, 0.130, 0.070),
        "study": (0.075, 0.045, 0.145, 0.080),
        "living": (0.090, 0.050, 0.170, 0.090),
        "dining": (0.080, 0.045, 0.150, 0.080),
        "kitchen": (0.075, 0.040, 0.145, 0.075),
        "entry": (0.065, 0.035, 0.125, 0.065),
        "corridor": (0.070, 0.040, 0.135, 0.070),
        "balcony": (0.050, 0.055, 0.105, 0.095),
        "laundry": (0.065, 0.040, 0.125, 0.070),
        "closet": (0.065, 0.035, 0.125, 0.065),
        "storage": (0.060, 0.035, 0.115, 0.060),
        "gym": (0.080, 0.045, 0.150, 0.080),
        "media": (0.080, 0.045, 0.150, 0.080),
        "tea-room": (0.075, 0.045, 0.145, 0.075),
        "unknown": (0.070, 0.040, 0.135, 0.070),
    }.get(room_kind, (0.070, 0.040, 0.135, 0.070))
    ceiling_min, floor_min, ceiling_target, floor_target = base
    elongation = clamp((slenderness - 1.35) / 1.65, 0.0, 1.0)
    return {
        "ceilingMin": ceiling_min + 0.010 * elongation,
        "floorMin": floor_min + 0.004 * elongation,
        "ceilingTarget": ceiling_target + 0.030 * elongation,
        "floorTarget": floor_target + 0.010 * elongation,
    }


def projected_span(poly: list[tuple[float, float]], axis: tuple[float, float]) -> float:
    values = [point[0] * axis[0] + point[1] * axis[1] for point in poly]
    return max(values) - min(values) if values else 0.0


def angle_difference_degrees(a: tuple[float, float], b: tuple[float, float]) -> float:
    dot = clamp(a[0] * b[0] + a[1] * b[1], -1.0, 1.0)
    return math.degrees(math.acos(dot))


def polygon_area(poly: list[tuple[float, float]]) -> float:
    return 0.5 * sum(
        poly[i][0] * poly[(i + 1) % len(poly)][1]
        - poly[(i + 1) % len(poly)][0] * poly[i][1]
        for i in range(len(poly))
    )


def point_in_polygon(point: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, z = point
    inside = False
    for i in range(len(poly)):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z):
            xi = (x2 - x1) * (z - z1) / (z2 - z1 + 1e-12) + x1
            if x < xi:
                inside = not inside
    return inside


def inward_normal(poly: list[tuple[float, float]], a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dz) or 1.0
    left = (-dz / length, dx / length)
    right = (dz / length, -dx / length)
    midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    probe = (midpoint[0] + left[0] * 0.04, midpoint[1] + left[1] * 0.04)
    return left if point_in_polygon(probe, poly) else right


def box_from_item(item: dict[str, Any], default_room_id: str) -> Box:
    world = item.get("placementWorld") or item.get("world") or item.get("bounds") or item.get("geometry") or {}
    center = world.get("center", {}) if isinstance(world, dict) else {}
    dims = world.get("dimensionsMeters", {}) if isinstance(world, dict) else {}
    return Box(
        id=str(item.get("id")),
        functional_class=str(item.get("functionalClass", "unknown")).lower(),
        room_id=str(item.get("roomId", default_room_id)),
        x=float(center.get("x", world.get("x", 0.0))),
        y=float(center.get("y", world.get("y", 0.0))),
        z=float(center.get("z", world.get("z", 0.0))),
        width=max(0.03, float(dims.get("width", world.get("width", 0.6)))),
        height=max(0.03, float(dims.get("height", world.get("height", 0.8)))),
        depth=max(0.03, float(dims.get("depth", world.get("depth", 0.6)))),
        rotation_y=float(world.get("rotationY", item.get("rotationY", 0.0))),
    )


def point_inside_box_xz(point: tuple[float, float], box: Box, margin: float, camera_height: float) -> bool:
    if camera_height > box.top + 0.22:
        return False
    dx, dz = point[0] - box.x, point[1] - box.z
    cosine, sine = math.cos(-box.rotation_y), math.sin(-box.rotation_y)
    local_x = cosine * dx - sine * dz
    local_z = sine * dx + cosine * dz
    return abs(local_x) <= box.width / 2 + margin and abs(local_z) <= box.depth / 2 + margin


def box_points(box: Box) -> list[tuple[float, float, float]]:
    ux = (math.cos(box.rotation_y), math.sin(box.rotation_y))
    uz = (-math.sin(box.rotation_y), math.cos(box.rotation_y))
    result: list[tuple[float, float, float]] = []
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                result.append(
                    (
                        box.x + sx * box.width / 2 * ux[0] + sz * box.depth / 2 * uz[0],
                        box.y + sy * box.height / 2,
                        box.z + sx * box.width / 2 * ux[1] + sz * box.depth / 2 * uz[1],
                    )
                )
    return result


def weighted_center(boxes: list[Box]) -> tuple[float, float, float]:
    if not boxes:
        return (0.0, 1.0, 0.0)
    weights = [max(0.05, box.footprint_area) for box in boxes]
    total = sum(weights)
    return (
        sum(box.x * weight for box, weight in zip(boxes, weights)) / total,
        sum(box.y * weight for box, weight in zip(boxes, weights)) / total,
        sum(box.z * weight for box, weight in zip(boxes, weights)) / total,
    )


def weighted_visual_center(boxes: list[Box]) -> tuple[float, float, float]:
    """Return a center that lies on the visible body, not near the floor.

    Beds, sofas, desks, and low cabinets have geometric centers too close to the
    floor for a reliable center-ray test.  The visual center lifts each object's
    sample toward its upper third while preserving the same footprint weights.
    """
    if not boxes:
        return (0.0, 1.0, 0.0)
    weights = [max(0.05, box.footprint_area) for box in boxes]
    total = sum(weights)
    return (
        sum(box.x * weight for box, weight in zip(boxes, weights)) / total,
        sum((box.y + min(0.34, box.height * 0.28)) * weight for box, weight in zip(boxes, weights)) / total,
        sum(box.z * weight for box, weight in zip(boxes, weights)) / total,
    )


def project_points(
    camera: tuple[float, float, float],
    forward: tuple[float, float],
    fov: float,
    points: Iterable[tuple[float, float, float]],
    aspect: float = 1.6,
) -> list[tuple[float, float, float]] | None:
    fx, fz = normalize(*forward)
    rx, rz = -fz, fx
    tangent = math.tan(math.radians(fov) / 2)
    projected: list[tuple[float, float, float]] = []
    for x, y, z in points:
        dx, dy, dz = x - camera[0], y - camera[1], z - camera[2]
        depth = dx * fx + dz * fz
        if depth <= 0.08:
            return None
        projected.append(
            (
                (dx * rx + dz * rz) / (depth * tangent * aspect),
                dy / (depth * tangent),
                depth,
            )
        )
    return projected


def nearest_room_wall_id(model: dict[str, Any], a: tuple[float, float], b: tuple[float, float]) -> str:
    midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    candidates: list[tuple[float, str]] = []
    for wall in model.get("walls", []):
        wa = (float(wall["a"]["x"]), float(wall["a"]["z"]))
        wb = (float(wall["b"]["x"]), float(wall["b"]["z"]))
        distance = point_segment_distance(midpoint, wa, wb)
        wall_tangent = normalize(wb[0] - wa[0], wb[1] - wa[1])
        edge_tangent = normalize(b[0] - a[0], b[1] - a[1])
        alignment = abs(wall_tangent[0] * edge_tangent[0] + wall_tangent[1] * edge_tangent[1])
        candidates.append((distance + (1.0 - alignment) * 2.0, str(wall.get("id"))))
    return min(candidates, default=(0.0, "unknown-wall"), key=lambda x: x[0])[1]


# ----------------------------- semantic inference -----------------------------

ROOM_KEYWORDS = {
    "living": ("living", "客厅", "起居", "会客"),
    "dining": ("dining", "餐厅", "餐区"),
    "kitchen": ("kitchen", "厨房", "厨"),
    "children-bedroom": ("children", "child", "儿童房", "婴儿房"),
    "bedroom": ("bedroom", "卧室", "主卧", "次卧", "客房"),
    "bathroom": ("bathroom", "washroom", "卫生间", "主卫", "客卫", "浴室"),
    "study": ("study", "office", "书房", "办公室", "电竞"),
    "entry": ("entry", "foyer", "entrance", "玄关", "入户"),
    "corridor": ("corridor", "hallway", "走廊", "过道"),
    "balcony": ("balcony", "阳台", "露台"),
    "laundry": ("laundry", "洗衣房", "家政间", "洗衣"),
    "closet": ("closet", "wardrobe room", "衣帽间"),
    "storage": ("storage", "储藏", "储物"),
    "gym": ("gym", "健身"),
    "media": ("media", "cinema", "影音", "影院"),
    "tea-room": ("tea room", "茶室"),
}


def classify_room(shot: dict[str, Any], boxes: list[Box], structure_room: dict[str, Any] | None) -> str:
    explicit = str((structure_room or {}).get("spaceType", "")).lower()
    if explicit and explicit not in {"room", "space", "other", "unknown"}:
        for kind, words in ROOM_KEYWORDS.items():
            if explicit == kind or any(word.lower() in explicit for word in words):
                return kind
    raw = " ".join(str(shot.get(key, "")) for key in ("roomId", "roomName", "roomKind", "name")).lower()
    for kind, words in ROOM_KEYWORDS.items():
        if any(word.lower() in raw for word in words):
            return kind
    classes = [box.functional_class for box in boxes]

    def has(*needles: str) -> bool:
        return any(any(needle in value for needle in needles) for value in classes)

    if has("cooktop", "sink", "base-cabinet", "counter"):
        return "kitchen"
    if has("bed", "crib"):
        return "bedroom"
    if has("sofa") and has("coffee", "tv"):
        return "living"
    if has("dining-table"):
        return "dining"
    if has("toilet", "vanity", "shower", "washbasin"):
        return "bathroom"
    if has("washer", "dryer", "washing-machine"):
        return "laundry"
    if sum("wardrobe" in value or "closet" in value for value in classes) >= 2:
        return "closet"
    return "unknown"


def matching_ids(boxes: list[Box], words: tuple[str, ...]) -> list[str]:
    return [box.id for box in boxes if any(word in box.functional_class for word in words)]


def select_subject_group(kind: str, boxes: list[Box]) -> tuple[list[str], list[str]]:
    primary: list[str] = []
    companions: list[str] = []
    if kind == "kitchen":
        # A one-image kitchen hero shot should explain one coherent work run,
        # not require every small module from every perpendicular run.  Build
        # orientation families, attach the cooktop/sink to their nearest run,
        # and make the dominant functional run mandatory.  Other cabinet runs
        # and the refrigerator stay as high-priority context.
        work_anchors = [
            box for box in boxes
            if any(word in box.functional_class for word in ("cooktop", "sink-base", "sink"))
        ]
        refrigerators = [
            box for box in boxes
            if any(word in box.functional_class for word in ("refrigerator", "fridge"))
        ]
        cabinet_boxes = [
            box for box in boxes
            if any(word in box.functional_class for word in ("base-cabinet", "wall-cabinet", "counter"))
        ]
        by_orientation: dict[int, list[Box]] = {}
        for box in cabinet_boxes:
            orientation = int(round((box.rotation_y % math.pi) / (math.pi / 2))) % 2
            by_orientation.setdefault(orientation, []).append(box)

        anchor_family: dict[str, int] = {}
        for anchor in work_anchors:
            if by_orientation:
                family = min(
                    by_orientation,
                    key=lambda key: min(
                        math.hypot(anchor.x - cabinet.x, anchor.z - cabinet.z)
                        for cabinet in by_orientation[key]
                    ),
                )
                anchor_family[anchor.id] = family

        def family_score(key: int) -> float:
            family_boxes = by_orientation[key]
            area = sum(box.footprint_area for box in family_boxes)
            anchors = [anchor for anchor in work_anchors if anchor_family.get(anchor.id) == key]
            return area + 1.6 * sum(max(0.15, anchor.footprint_area) for anchor in anchors) + 0.9 * len(anchors)

        dominant_family = max(by_orientation, key=family_score) if by_orientation else None
        cabinet_required: list[str] = []
        dominant_anchors: list[str] = []
        if dominant_family is not None:
            family_boxes = by_orientation[dominant_family]
            axis = (1.0, 0.0) if dominant_family == 0 else (0.0, 1.0)
            ordered = sorted(family_boxes, key=lambda box: box.x * axis[0] + box.z * axis[1])
            cabinet_required.append(ordered[0].id)
            if len(ordered) > 1:
                cabinet_required.append(ordered[-1].id)
            dominant_anchors = [
                anchor.id for anchor in work_anchors if anchor_family.get(anchor.id) == dominant_family
            ]
        if not dominant_anchors and work_anchors:
            dominant_anchors = [max(work_anchors, key=lambda box: box.footprint_area).id]
        primary = list(dict.fromkeys(dominant_anchors + cabinet_required))
        companions = [
            box.id for box in boxes
            if box.id not in primary
        ]
        # Refrigerators are intentionally context unless they are the only
        # functional anchor in a tiny kitchenette.
        if not primary and refrigerators:
            primary = [refrigerators[0].id]
            companions = [box.id for box in boxes if box.id not in primary]
    elif kind in {"bedroom", "children-bedroom"}:
        primary = matching_ids(boxes, ("bed", "crib"))
        companions = matching_ids(
            boxes,
            ("nightstand", "bedside", "side-table", "table-light", "dresser", "wardrobe", "desk"),
        )
    elif kind == "living":
        primary = matching_ids(boxes, ("sofa", "sectional"))
        companions = matching_ids(boxes, ("coffee-table", "side-table", "accent-chair", "tv-console", "television"))
    elif kind == "dining":
        table_ids = matching_ids(boxes, ("dining-table",)) or matching_ids(boxes, ("table",))
        seat_ids = matching_ids(boxes, ("dining-chair", "bench"))
        primary = list(dict.fromkeys(table_ids + seat_ids))
        companions = matching_ids(boxes, ("sideboard", "console", "accent-chair"))
    elif kind == "bathroom":
        # A bathroom hero view must explain the fixture relationship, not only
        # show a tiny vanity.  Treat the vanity/basin and the principal toilet
        # or shower as one mandatory semantic subject group.
        primary = matching_ids(boxes, ("vanity", "washbasin", "sink", "toilet", "shower", "bathtub"))
        companions = [box.id for box in boxes if box.id not in primary]
    elif kind == "study":
        # The desk is the functional anchor.  A sofa-bed is context, otherwise
        # it can pull the supposedly frontal study view toward the wrong wall.
        primary = matching_ids(boxes, ("desk",)) or matching_ids(boxes, ("worktable", "table"))
        companions = [box.id for box in boxes if box.id not in primary]
    elif kind in {"media", "gym", "tea-room"}:
        primary = matching_ids(boxes, ("sofa", "table", "bench", "equipment"))
        companions = [box.id for box in boxes if box.id not in primary]
    elif kind in {"entry", "corridor"}:
        primary = matching_ids(boxes, ("shoe", "console", "bench", "wardrobe"))
        companions = [box.id for box in boxes if box.id not in primary]
    elif kind in {"balcony", "laundry"}:
        primary = matching_ids(boxes, ("washing-machine", "washer", "dryer", "washbasin", "cabinet"))
        companions = [box.id for box in boxes if box.id not in primary]
    elif kind in {"closet", "storage"}:
        primary = matching_ids(boxes, ("wardrobe", "closet", "cabinet", "shelf"))
        companions = [box.id for box in boxes if box.id not in primary]
    if not primary and boxes:
        ranked = sorted(boxes, key=lambda box: box.footprint_area, reverse=True)
        primary = [box.id for box in ranked[: max(1, min(3, len(ranked)))]]
        companions = [box.id for box in ranked if box.id not in primary][:3]
    return list(dict.fromkeys(primary)), list(dict.fromkeys(companions))


def select_framing_companions(kind: str, primary_boxes: list[Box], companion_boxes: list[Box]) -> list[str]:
    if not companion_boxes:
        return []
    center = weighted_center(primary_boxes)
    def companion_key(box: Box) -> tuple[float, float, str]:
        role_priority = 0.0
        if kind in {"bedroom", "children-bedroom"}:
            functional_class = box.functional_class
            role_priority = (
                0.0 if any(word in functional_class for word in ("nightstand", "bedside", "side-table"))
                else 1.0 if any(word in functional_class for word in ("table-light", "desk-lamp"))
                else 2.0 if "dresser" in functional_class
                else 3.0
            )
        return (
            role_priority,
            math.hypot(box.x - center[0], box.z - center[2]),
            box.id,
        )

    ranked = sorted(companion_boxes, key=companion_key)
    limits = {
        "kitchen": 4,
        "living": 3,
        "dining": 5,
        "bedroom": 2,
        "children-bedroom": 2,
        "bathroom": 2,
        "study": 4,
        "entry": 2,
        "balcony": 2,
        "laundry": 2,
    }
    return [box.id for box in ranked[: limits.get(kind, 3)]]



def local_depth_axis(box: Box) -> tuple[float, float]:
    """Return the furniture-local depth direction in world XZ."""
    return normalize(-math.sin(box.rotation_y), math.cos(box.rotation_y))


FIXTURE_FACADE_WORDS = (
    "toilet", "vanity", "washbasin", "sink", "washing-machine", "washer", "dryer", "cabinet",
)


def preferred_fixture_forwards(
    room_kind: str,
    primary_boxes: list[Box],
    polygon: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Infer signed camera-forward axes from each fixture's nearest room edge.

    Wall-backed fixtures face from their supporting wall into the room.  A
    camera that sees the fixture front therefore looks toward that wall, i.e.
    opposite the wall's inward normal.  Keeping the directions per fixture
    also lets native-pixel overlap decide between perpendicular fixture runs.
    """
    if room_kind not in {"bathroom", "balcony", "laundry"}:
        return []
    result: list[tuple[float, float]] = []
    for box in primary_boxes:
        if not any(word in box.functional_class for word in FIXTURE_FACADE_WORDS):
            continue
        edges = [
            (polygon[index], polygon[(index + 1) % len(polygon)])
            for index in range(len(polygon))
        ]
        edge = min(edges, key=lambda value: point_segment_distance((box.x, box.z), value[0], value[1]))
        inward = inward_normal(polygon, edge[0], edge[1])
        result.append((-inward[0], -inward[1]))
    return result


def preferred_optical_axes(
    room_kind: str,
    primary_boxes: list[Box],
    companion_boxes: list[Box],
) -> tuple[list[tuple[float, float]], bool, str]:
    """Infer which wall-normal directions can produce the semantic hero view.

    The returned axes are *unoriented* for wall-family selection: either sign
    remains a mathematically frontal view, and native pixels choose the better
    side.  The important distinction is between looking along the subject's
    front/depth axis and photographing its side.
    """
    if not primary_boxes:
        return [], False, "none"
    anchor = max(primary_boxes, key=lambda box: box.footprint_area)
    if room_kind in {"bedroom", "children-bedroom"}:
        return [local_depth_axis(anchor)], True, "bed-depth-axis"
    if room_kind in {"entry", "closet", "storage"}:
        return [local_depth_axis(anchor)], True, "cabinet-facade-axis"
    if room_kind == "study":
        desks = [box for box in primary_boxes if "desk" in box.functional_class]
        chairs = [box for box in companion_boxes if "chair" in box.functional_class]
        if desks:
            desk = max(desks, key=lambda box: box.footprint_area)
            facade_axis = local_depth_axis(desk)
            if chairs:
                chair = min(chairs, key=lambda box: math.hypot(box.x - desk.x, box.z - desk.z))
                relation_axis = normalize(desk.x - chair.x, desk.z - chair.z)
                if angle_difference_degrees(facade_axis, relation_axis) <= 35.0 or angle_difference_degrees((-facade_axis[0], -facade_axis[1]), relation_axis) <= 35.0:
                    return [relation_axis], True, "chair-confirmed-desk-facade-axis"
            return [facade_axis], True, "desk-facade-axis"
        return [local_depth_axis(anchor)], True, "study-anchor-facade-axis"
    if room_kind == "living":
        televisions = [
            box for box in companion_boxes
            if "tv" in box.functional_class or "television" in box.functional_class
        ]
        if televisions:
            tv = min(televisions, key=lambda box: math.hypot(box.x - anchor.x, box.z - anchor.z))
            return [normalize(anchor.x - tv.x, anchor.z - tv.z)], True, "tv-to-sofa-axis"
        return [local_depth_axis(anchor)], True, "sofa-depth-axis"
    # Kitchens, dining areas, bathrooms and balconies are semantic groups whose
    # best overview can legitimately use more than one wall family.
    return [], False, "room-group-no-single-axis"


def axis_alignment(forward: tuple[float, float], axes: list[tuple[float, float]]) -> float:
    if not axes:
        return 0.0
    return max(abs(forward[0] * axis[0] + forward[1] * axis[1]) for axis in axes)


def requested_camera_axis(shot: dict[str, Any]) -> tuple[float, float] | None:
    intent = shot.get("userCameraIntent")
    if not isinstance(intent, dict):
        return None
    axis = intent.get("desiredOpticalAxisXZ")
    if not isinstance(axis, list) or len(axis) != 2:
        return None
    return normalize(float(axis[0]), float(axis[1]))


def matches_requested_camera_axis(
    forward: tuple[float, float], requested_axis: tuple[float, float] | None
) -> bool:
    return requested_axis is None or forward[0] * requested_axis[0] + forward[1] * requested_axis[1] >= 0.92


# ----------------------------- candidate generation -----------------------------


def wall_support_score(wall_a: tuple[float, float], wall_b: tuple[float, float], primary_boxes: list[Box]) -> float:
    if not primary_boxes:
        return 0.0
    weighted = 0.0
    weight_total = 0.0
    for box in primary_boxes:
        weight = max(0.05, box.footprint_area)
        distance = point_segment_distance((box.x, box.z), wall_a, wall_b)
        parameter = projection_param((box.x, box.z), wall_a, wall_b)
        outside = max(0.0, -parameter, parameter - 1.0)
        weighted += weight * (math.exp(-distance / 0.70) - outside * 0.8)
        weight_total += weight
    return weighted / max(weight_total, 1e-9)


def build_wall_frames(
    polygon: list[tuple[float, float]], model: dict[str, Any], primary_boxes: list[Box]
) -> list[WallFrame]:
    result: list[WallFrame] = []
    for index in range(len(polygon)):
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        tangent = normalize(b[0] - a[0], b[1] - a[1])
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 0.45:
            continue
        inward = inward_normal(polygon, a, b)
        model_wall_id = nearest_room_wall_id(model, a, b)
        model_wall = next((wall for wall in model.get("walls", []) if str(wall.get("id")) == model_wall_id), {})
        opening_wall_ids = {str(opening.get("wallId")) for opening in model.get("openings", [])}
        result.append(
            WallFrame(
                index=index,
                a=a,
                b=b,
                tangent=tangent,
                inward=inward,
                length=length,
                model_wall_id=model_wall_id,
                support_score=wall_support_score(a, b, primary_boxes),
                has_opening=model_wall_id in opening_wall_ids,
                is_exterior="exterior" in {str(value) for value in model_wall.get("adjacentRoomIds", [])},
            )
        )
    return result


def choose_camera_height(
    point: tuple[float, float], base_height: float, all_boxes: list[Box]
) -> tuple[float, str] | None:
    collisions = [box for box in all_boxes if point_inside_box_xz(point, box, 0.17, base_height)]
    if not collisions:
        return base_height, "floor-standing"
    required_height = max(box.top for box in collisions) + 0.24
    if required_height <= 2.12 and all(not point_inside_box_xz(point, box, 0.12, required_height) for box in all_boxes):
        return max(base_height, required_height), "support-above"
    return None


def near_plane_clear(
    point: tuple[float, float],
    camera_height: float,
    forward: tuple[float, float],
    fov: float,
    boxes: list[Box],
    aspect: float = 1.6,
) -> bool:
    near = 0.10
    half_width = near * math.tan(math.radians(fov) / 2) * aspect
    right = (forward[1], -forward[0])
    for lateral in (-half_width, 0.0, half_width):
        sample = (
            point[0] + forward[0] * near + right[0] * lateral,
            point[1] + forward[1] * near + right[1] * lateral,
        )
        if any(point_inside_box_xz(sample, box, 0.06, camera_height) for box in boxes):
            return False
    return True


def shifted_bounds(
    values: list[tuple[float, float, float]], shift_x: float, shift_y: float
) -> dict[str, float]:
    xmin, xmax = min(v[0] for v in values), max(v[0] for v in values)
    ymin, ymax = min(v[1] for v in values), max(v[1] for v in values)
    return {
        "left": (xmin - shift_x + 1) / 2,
        "right": (xmax - shift_x + 1) / 2,
        "top": (1 - (ymax - shift_y)) / 2,
        "bottom": (1 - (ymin - shift_y)) / 2,
    }


def area_of_bounds(bounds: dict[str, float]) -> float:
    return max(0.0, bounds["right"] - bounds["left"]) * max(0.0, bounds["bottom"] - bounds["top"])


def edge_overflow(bounds: dict[str, float], margin: float = 0.025) -> float:
    return (
        max(0.0, margin - bounds["left"])
        + max(0.0, bounds["right"] - (1 - margin))
        + max(0.0, margin - bounds["top"])
        + max(0.0, bounds["bottom"] - (1 - margin))
    )



def ray_exit_distance(
    origin: tuple[float, float], direction: tuple[float, float], polygon: list[tuple[float, float]]
) -> float | None:
    if not point_in_polygon(origin, polygon):
        return None
    step = 0.04
    distance = step
    maximum = 30.0
    while distance <= maximum and point_in_polygon(
        (origin[0] + direction[0] * distance, origin[1] + direction[1] * distance), polygon
    ):
        distance += step
    if distance > maximum:
        return None
    low, high = max(0.0, distance - step), distance
    for _ in range(24):
        middle = (low + high) / 2
        point = (origin[0] + direction[0] * middle, origin[1] + direction[1] * middle)
        if point_in_polygon(point, polygon):
            low = middle
        else:
            high = middle
    return high


def nearest_boundary_wall(point: tuple[float, float], walls: list[WallFrame]) -> WallFrame:
    return min(walls, key=lambda wall: point_segment_distance(point, wall.a, wall.b))


def generate_candidates(
    room_id: str,
    room_name: str,
    room_kind: str,
    polygon: list[tuple[float, float]],
    walls: list[WallFrame],
    primary_boxes: list[Box],
    companion_boxes: list[Box],
    framing_ids: list[str],
    all_boxes: list[Box],
    preferred_axes_override: list[tuple[float, float]] | None = None,
    semantic_axis_source_override: str | None = None,
) -> list[Candidate]:
    footprint_center = weighted_center(primary_boxes)
    primary_center = weighted_visual_center(primary_boxes)
    framing_boxes = [box for box in all_boxes if box.id in framing_ids]
    if not framing_boxes:
        framing_boxes = primary_boxes
    primary_points = [point for box in primary_boxes for point in box_points(box)]
    framing_points = [point for box in framing_boxes for point in box_points(box)]
    if not primary_points or not framing_points:
        return []

    backdrop = max(walls, key=lambda wall: wall.support_score)
    inferred_front = backdrop.inward
    preferred_axes, semantic_axis_required, semantic_axis_source = preferred_optical_axes(
        room_kind, primary_boxes, companion_boxes
    )
    if preferred_axes_override:
        preferred_axes = [normalize(axis[0], axis[1]) for axis in preferred_axes_override]
        semantic_axis_required = True
        semantic_axis_source = semantic_axis_source_override or "user-camera-intent"
    fixture_forwards = preferred_fixture_forwards(room_kind, primary_boxes, polygon)
    base_height = CAMERA_HEIGHT.get(room_kind, 1.52)
    strict_candidates: list[Candidate] = []

    span_x = max(x for x, _ in polygon) - min(x for x, _ in polygon)
    span_z = max(z for _, z in polygon) - min(z for _, z in polygon)
    room_span = max(span_x, span_z)
    room_short_span = max(0.60, min(span_x, span_z))
    room_long_span = max(span_x, span_z)
    room_slenderness = room_long_span / max(room_short_span, 1e-6)
    slender_bonus = max(0.0, room_slenderness - 1.6)
    max_distance = max(1.60, room_span + 2.20 + 0.65 * slender_bonus)
    steps = int(round((max_distance - 0.68) / 0.10))
    distances = [0.68 + i * 0.10 for i in range(max(10, steps + 1))]
    fov_values = [42.0, 46.0, 50.0, 54.0, 58.0, 62.0, 66.0, 70.0, 74.0, 78.0, 82.0, 86.0, 90.0, 96.0, 102.0, 108.0, 115.0, 122.0, 128.0, 134.0, 142.0, 150.0, 160.0, 170.0]

    def candidate_from_projection(
        target_wall: WallFrame,
        mode: str,
        point: tuple[float, float],
        camera_height: float,
        placement_tier: str,
        forward: tuple[float, float],
        wall_error: float,
        lateral: float,
        lateral_scale: float,
        view_depth: float,
        view_width: float,
        view_slenderness: float,
        fov: float,
        framing_projection: list[tuple[float, float, float]],
        primary_projection: list[tuple[float, float, float]],
        hidden_wall_ids: tuple[str, ...] = (),
        hidden_opening_ids: tuple[str, ...] = (),
        hidden_element_ids: tuple[str, ...] = (),
        camera_inside_target_room: bool = True,
    ) -> Candidate:
        primary_xmin = min(v[0] for v in primary_projection)
        primary_xmax = max(v[0] for v in primary_projection)
        primary_ymin = min(v[1] for v in primary_projection)
        primary_ymax = max(v[1] for v in primary_projection)
        primary_cx = (primary_xmin + primary_xmax) / 2
        frame_xmin = min(v[0] for v in framing_projection)
        frame_xmax = max(v[0] for v in framing_projection)
        frame_ymin = min(v[1] for v in framing_projection)
        frame_ymax = max(v[1] for v in framing_projection)
        frame_cx = (frame_xmin + frame_xmax) / 2

        # First solve the horizontal and vertical lens-shift intervals that keep
        # every mandatory-subject corner inside the safe frame.
        margin_x = 0.02
        margin_top = 0.015
        margin_bottom = 0.002
        feasible_x_low = primary_xmax - 1.0 + 2.0 * margin_x
        feasible_x_high = primary_xmin + 1.0 - 2.0 * margin_x
        feasible_y_low = primary_ymax - 1.0 + 2.0 * margin_top
        feasible_y_high = primary_ymin + 1.0 - 2.0 * margin_bottom
        hardware_x_low, hardware_x_high = (-0.90, 0.90)
        hardware_y_low, hardware_y_high = (-0.90, 0.90)
        fit_x_low = max(feasible_x_low, hardware_x_low)
        fit_x_high = min(feasible_x_high, hardware_x_high)
        fit_y_low = max(feasible_y_low, hardware_y_low)
        fit_y_high = min(feasible_y_high, hardware_y_high)
        fit_interval_available = fit_x_low <= fit_x_high and fit_y_low <= fit_y_high

        preferred_shift_x = primary_cx * 0.82 + frame_cx * 0.18
        shift_x = (
            clamp(preferred_shift_x, fit_x_low, fit_x_high)
            if fit_x_low <= fit_x_high
            else clamp(preferred_shift_x, hardware_x_low, hardware_x_high)
        )

        combined_slenderness = max(room_slenderness, view_slenderness)
        envelope = space_envelope_profile(room_kind, combined_slenderness)
        ceiling_min = envelope["ceilingMin"]
        floor_min = envelope["floorMin"]
        ceiling_target = envelope["ceilingTarget"]
        floor_target = envelope["floorTarget"]

        # For a horizontal optical axis, the top/bottom free-space bands are
        # affine functions of vertical lens shift.  Solve the interval that
        # simultaneously preserves the subject and the formal-shot envelope.
        envelope_y_low = 2.0 * ceiling_min - 1.0 + frame_ymax
        envelope_y_high = 1.0 + frame_ymin - 2.0 * floor_min
        formal_y_low = max(fit_y_low, envelope_y_low)
        formal_y_high = min(fit_y_high, envelope_y_high)
        formal_y_interval_available = fit_interval_available and formal_y_low <= formal_y_high

        ideal_top_shift = 2.0 * ceiling_target - 1.0 + frame_ymax
        ideal_bottom_shift = 1.0 + frame_ymin - 2.0 * floor_target
        ideal_shift_y = (1.35 * ideal_top_shift + ideal_bottom_shift) / 2.35

        if formal_y_interval_available:
            shift_y = clamp(ideal_shift_y, formal_y_low, formal_y_high)
        elif fit_interval_available:
            shift_candidates = {
                fit_y_low,
                fit_y_high,
                clamp(ideal_shift_y, fit_y_low, fit_y_high),
                clamp((fit_y_low + fit_y_high) / 2.0, fit_y_low, fit_y_high),
                clamp(ideal_top_shift, fit_y_low, fit_y_high),
                clamp(ideal_bottom_shift, fit_y_low, fit_y_high),
            }

            def vertical_loss(value: float) -> float:
                top_open = max(0.0, (1.0 - frame_ymax + value) / 2.0)
                bottom_open = max(0.0, (1.0 + frame_ymin - value) / 2.0)
                deficit = (
                    12.0 * max(0.0, ceiling_min - top_open) / max(ceiling_min, 1e-6)
                    + 10.0 * max(0.0, floor_min - bottom_open) / max(floor_min, 1e-6)
                )
                target_error = (
                    1.35 * abs(top_open - ceiling_target) / max(ceiling_target, 1e-6)
                    + abs(bottom_open - floor_target) / max(floor_target, 1e-6)
                )
                ceiling_bias = 2.0 * max(0.0, bottom_open * 0.72 - top_open)
                return deficit + target_error + ceiling_bias + 0.05 * abs(value)

            shift_y = min(shift_candidates, key=vertical_loss)
        else:
            shift_y = clamp(ideal_shift_y, hardware_y_low, hardware_y_high)

        frame_bounds = shifted_bounds(framing_projection, shift_x, shift_y)
        primary_bounds = shifted_bounds(primary_projection, shift_x, shift_y)
        frame_edge = edge_overflow(frame_bounds, 0.02)
        primary_edge = edge_overflow(primary_bounds, 0.01)
        full_primary_fit = fit_interval_available and (
            primary_bounds["left"] >= 0.02
            and primary_bounds["right"] <= 0.98
            and primary_bounds["top"] >= 0.015
            and primary_bounds["bottom"] <= 0.995
        )
        top_open_ratio = max(0.0, float(frame_bounds["top"]))
        bottom_open_ratio = max(0.0, 1.0 - float(frame_bounds["bottom"]))
        analytic_envelope_complete = (
            top_open_ratio >= ceiling_min and bottom_open_ratio >= floor_min
        )
        formal_frame_complete = full_primary_fit and analytic_envelope_complete
        primary_area = area_of_bounds(primary_bounds)
        framing_area = area_of_bounds(frame_bounds)
        blank_ratio = max(0.0, 1.0 - primary_area / max(framing_area, primary_area, 1e-9))
        depths = [value[2] for value in framing_projection]
        primary_depths = [value[2] for value in primary_projection]
        perspective = max(depths) / max(0.08, min(depths))
        base_target_ratio = TARGET_PRIMARY_RATIO.get(room_kind, 0.12)
        slender_ratio_scale = 1.0 / (1.0 + 0.13 * max(combined_slenderness - 1.0, 0.0))
        target_ratio = max(0.07, base_target_ratio * slender_ratio_scale)
        distance_to_subject = math.hypot(
            point[0] - footprint_center[0], point[1] - footprint_center[2]
        )
        wall_fit = min(
            1.0,
            target_wall.length
            / max(1.0, math.sqrt(sum(box.footprint_area for box in primary_boxes))),
        )
        semantic_alignment = axis_alignment(forward, preferred_axes)
        fixture_facade_alignment = (
            sum(forward[0] * axis[0] + forward[1] * axis[1] for axis in fixture_forwards)
            / len(fixture_forwards)
            if fixture_forwards else 0.0
        )
        subject_to_camera = normalize(
            point[0] - footprint_center[0], point[1] - footprint_center[2]
        )
        front_score = (
            1
            + subject_to_camera[0] * inferred_front[0]
            + subject_to_camera[1] * inferred_front[1]
        ) / 2
        ceiling_deficit = max(0.0, ceiling_min - top_open_ratio) / max(ceiling_min, 1e-6)
        floor_deficit = max(0.0, floor_min - bottom_open_ratio) / max(floor_min, 1e-6)
        envelope_target_error = (
            1.35 * abs(top_open_ratio - ceiling_target) / max(ceiling_target, 1e-6)
            + abs(bottom_open_ratio - floor_target) / max(floor_target, 1e-6)
        )
        fov_penalty_weight = max(0.62, 1.45 - 0.22 * min(combined_slenderness - 1.0, 2.0))
        analytic_score = (
            52.0 * front_score
            + 28.0 * target_wall.support_score
            + 18.0 * wall_fit
            + 165.0 * semantic_alignment
            + 140.0 * fixture_facade_alignment
            + 36.0 * min(primary_area, target_ratio * 1.8)
            - 145.0 * abs(primary_area - target_ratio)
            - 150.0 * blank_ratio
            - 420.0 * primary_edge
            - 140.0 * frame_edge
            - 36.0 * max(0.0, perspective - 1.35)
            - fov_penalty_weight * max(0.0, fov - 54.0)
            - 38.0 * abs(shift_x)
            - 8.0 * max(0.0, abs(shift_y) - 0.08)
            - 0.35 * wall_error
            + 6.0 * min(distance_to_subject, 4.6)
            - 8.5 * abs(lateral) / max(lateral_scale, 0.1)
            - 185.0 * ceiling_deficit
            - 150.0 * floor_deficit
            - 24.0 * envelope_target_error
            - (8.0 if placement_tier == "support-above" else 0.0)
            - (20.0 if placement_tier == "external-frontal" else 0.0)
            - 26.0
            * (len(hidden_wall_ids) + len(hidden_opening_ids) + len(hidden_element_ids))
            + (18.0 if mode == "strict-wall-frontal" else 0.0)
            + (28.0 if full_primary_fit else 0.0)
            + (70.0 if formal_frame_complete else 0.0)
        )
        return Candidate(
            room_id=room_id,
            room_name=room_name,
            room_kind=room_kind,
            mode=mode,
            target_wall=target_wall,
            position=(point[0], camera_height, point[1]),
            forward=forward,
            fov=fov,
            window_center=(round(shift_x, 6), round(shift_y, 6)),
            placement_tier=placement_tier,
            primary_ids=[box.id for box in primary_boxes],
            companion_ids=[box.id for box in companion_boxes],
            framing_ids=framing_ids,
            primary_center=primary_center,
            front_score=front_score,
            semantic_axis_alignment=semantic_alignment,
            semantic_axis_required=semantic_axis_required,
            wall_alignment_error_degrees=wall_error,
            analytic_score=analytic_score,
            hidden_wall_ids=hidden_wall_ids,
            hidden_opening_ids=hidden_opening_ids,
            hidden_element_ids=hidden_element_ids,
            camera_inside_target_room=camera_inside_target_room,
            analytic={
                "primaryArea": primary_area,
                "framingArea": framing_area,
                "primaryBounds": primary_bounds,
                "framingBounds": frame_bounds,
                "primaryEdgeOverflow": primary_edge,
                "framingEdgeOverflow": frame_edge,
                "primaryCompleteFit": full_primary_fit,
                "analyticEnvelopeComplete": analytic_envelope_complete,
                "formalFrameComplete": formal_frame_complete,
                "fitShiftIntervalAvailable": fit_interval_available,
                "formalShiftIntervalAvailable": formal_y_interval_available,
                "feasibleShiftX": [fit_x_low, fit_x_high],
                "feasibleShiftY": [fit_y_low, fit_y_high],
                "formalShiftY": [formal_y_low, formal_y_high],
                "topOpenRatio": top_open_ratio,
                "bottomOpenRatio": bottom_open_ratio,
                "ceilingMinimumRatio": ceiling_min,
                "floorMinimumRatio": floor_min,
                "ceilingTargetRatio": ceiling_target,
                "floorTargetRatio": floor_target,
                "blankRatio": blank_ratio,
                "perspectiveDepthRatio": perspective,
                "primaryNearDepthMeters": min(primary_depths),
                "primaryFarDepthMeters": max(primary_depths),
                "distanceToSubjectMeters": distance_to_subject,
                "wallSupportScore": target_wall.support_score,
                "semanticAxisAlignment": semantic_alignment,
                "semanticAxisRequired": semantic_axis_required,
                "semanticAxisSource": semantic_axis_source,
                "fixtureFacadeAlignment": fixture_facade_alignment,
                "fixtureFacadeAxisCount": len(fixture_forwards),
                "lateralOffsetMeters": lateral,
                "requiredFovCandidate": fov,
                "roomLongSpanMeters": room_long_span,
                "roomShortSpanMeters": room_short_span,
                "roomSlenderness": room_slenderness,
                "viewDepthMeters": view_depth,
                "viewWidthMeters": view_width,
                "viewSlenderness": view_slenderness,
                "combinedSlenderness": combined_slenderness,
            },
        )

    for target_wall in walls:
        strict_forward = target_wall.optical_axis
        view_width = max(0.60, projected_span(polygon, target_wall.tangent))
        view_depth = max(0.60, projected_span(polygon, target_wall.inward))
        view_slenderness = view_depth / max(view_width, 1e-6)
        lateral_scale = min(
            1.95,
            max(0.38, view_width * 0.42 + 0.08 * max(0.0, view_depth - view_width)),
        )
        lateral_offsets = [
            -lateral_scale,
            -lateral_scale * 0.80,
            -lateral_scale * 0.58,
            -lateral_scale * 0.35,
            -lateral_scale * 0.15,
            0.0,
            lateral_scale * 0.15,
            lateral_scale * 0.35,
            lateral_scale * 0.58,
            lateral_scale * 0.80,
            lateral_scale,
        ]
        wall_candidates: list[Candidate] = []
        for distance in distances:
            for lateral in lateral_offsets:
                point = (
                    footprint_center[0] + target_wall.inward[0] * distance + target_wall.tangent[0] * lateral,
                    footprint_center[2] + target_wall.inward[1] * distance + target_wall.tangent[1] * lateral,
                )
                if not point_in_polygon(point, polygon):
                    continue
                height_result = choose_camera_height(point, base_height, all_boxes)
                if not height_result:
                    continue
                camera_height, placement_tier = height_result
                directions: list[tuple[str, tuple[float, float], float]] = [("strict-wall-frontal", strict_forward, 0.0)]

                for mode, forward, wall_error in directions:
                    best_fit: Candidate | None = None
                    best_relaxed: Candidate | None = None
                    for fov in fov_values:
                        if not near_plane_clear(point, camera_height, forward, fov, all_boxes):
                            continue
                        framing_projection = project_points((point[0], camera_height, point[1]), forward, fov, framing_points)
                        primary_projection = project_points((point[0], camera_height, point[1]), forward, fov, primary_points)
                        if not framing_projection or not primary_projection:
                            continue
                        candidate = candidate_from_projection(
                            target_wall,
                            mode,
                            point,
                            camera_height,
                            placement_tier,
                            forward,
                            wall_error,
                            lateral,
                            lateral_scale,
                            view_depth,
                            view_width,
                            view_slenderness,
                            fov,
                            framing_projection,
                            primary_projection,
                        )
                        if candidate.analytic["formalFrameComplete"]:
                            best_fit = candidate
                            break
                        if best_relaxed is None or candidate.analytic_score > best_relaxed.analytic_score:
                            best_relaxed = candidate
                    if best_fit is not None:
                        wall_candidates.append(best_fit)
                    elif best_relaxed is not None:
                        wall_candidates.append(best_relaxed)

        # If the room does not provide enough retreat distance, continue the
        # same strict frontal ray beyond the camera-side boundary.  The crossed
        # boundary wall is hidden explicitly and recorded.  Non-primary
        # furniture touching the external station may also be hidden, but this
        # tier is considered only after complete internal frontal candidates.
        exit_distance = ray_exit_distance(
            (footprint_center[0], footprint_center[2]), target_wall.inward, polygon
        )
        semantic_wall_alignment = axis_alignment(strict_forward, preferred_axes)
        external_axis_allowed = (not semantic_axis_required) or semantic_wall_alignment >= 0.92
        if exit_distance is not None and external_axis_allowed:
            external_extension = 0.35 * max(0.0, max(room_slenderness, view_slenderness) - 1.4)
            for extra_distance in (
                0.45,
                0.80,
                1.20,
                1.75,
                2.30 + external_extension,
                3.00 + external_extension,
            ):
                for lateral in lateral_offsets:
                    point = (
                        footprint_center[0] + target_wall.inward[0] * (exit_distance + extra_distance) + target_wall.tangent[0] * lateral,
                        footprint_center[2] + target_wall.inward[1] * (exit_distance + extra_distance) + target_wall.tangent[1] * lateral,
                    )
                    exit_point = (
                        footprint_center[0] + target_wall.inward[0] * (exit_distance + 0.01),
                        footprint_center[2] + target_wall.inward[1] * (exit_distance + 0.01),
                    )
                    crossed_wall = nearest_boundary_wall(exit_point, walls)
                    colliding = [
                        box for box in all_boxes
                        if point_inside_box_xz(point, box, 0.17, base_height)
                    ]
                    primary_id_set = {item.id for item in primary_boxes}
                    protected_framing_ids = set(framing_ids)
                    if any(box.id in primary_id_set for box in colliding):
                        continue
                    camera_height = base_height
                    primary_depth_from_external = (
                        (footprint_center[0] - point[0]) * strict_forward[0]
                        + (footprint_center[2] - point[1]) * strict_forward[1]
                    )
                    screen_right = (-strict_forward[1], strict_forward[0])
                    subject_half_span = max(
                        0.55,
                        max((max(box.width, box.depth) for box in primary_boxes), default=0.6) * 0.62,
                    )
                    corridor_blockers: list[Box] = []
                    for box in all_boxes:
                        if box.id in protected_framing_ids:
                            continue
                        if room_kind == "living" and box.id in {item.id for item in companion_boxes}:
                            continue
                        if room_kind == "kitchen" and any(
                            word in box.functional_class
                            for word in ("cabinet", "counter", "cooktop", "sink", "refrigerator", "fridge")
                        ):
                            continue
                        dx, dz = box.x - point[0], box.z - point[1]
                        depth = dx * strict_forward[0] + dz * strict_forward[1]
                        lateral_distance = abs(dx * screen_right[0] + dz * screen_right[1])
                        blocker_half_span = max(box.width, box.depth) / 2
                        if (
                            0.0 < depth < primary_depth_from_external * 0.94
                            and lateral_distance < subject_half_span + blocker_half_span + 0.18
                        ):
                            corridor_blockers.append(box)
                    corridor_blockers.sort(
                        key=lambda box: (
                            abs((box.x - point[0]) * screen_right[0] + (box.z - point[1]) * screen_right[1]),
                            (box.x - point[0]) * strict_forward[0] + (box.z - point[1]) * strict_forward[1],
                        )
                    )
                    initial_hideable = [box for box in colliding if box.id not in protected_framing_ids]
                    initial_hideable.extend(corridor_blockers[:2])
                    hidden_elements = tuple(sorted({box.id for box in initial_hideable}))
                    external_complete: list[Candidate] = []
                    for fov in fov_values:
                        if not near_plane_clear(
                            point, camera_height, strict_forward, fov,
                            [box for box in all_boxes if box.id not in hidden_elements],
                        ):
                            continue
                        framing_projection = project_points(
                            (point[0], camera_height, point[1]), strict_forward, fov, framing_points
                        )
                        primary_projection = project_points(
                            (point[0], camera_height, point[1]), strict_forward, fov, primary_points
                        )
                        if not framing_projection or not primary_projection:
                            continue
                        candidate = candidate_from_projection(
                            target_wall,
                            "strict-wall-frontal",
                            point,
                            camera_height,
                            "external-frontal",
                            strict_forward,
                            0.0,
                            lateral,
                            lateral_scale,
                            view_depth,
                            view_width,
                            view_slenderness,
                            fov,
                            framing_projection,
                            primary_projection,
                            hidden_wall_ids=(crossed_wall.model_wall_id,),
                            hidden_element_ids=hidden_elements,
                            camera_inside_target_room=False,
                        )
                        if candidate.analytic["formalFrameComplete"]:
                            external_complete.append(candidate)
                    if external_complete:
                        # A sectioned external station exists to avoid an
                        # extreme internal ultra-wide view.  Keep the one
                        # complete strict-frontal lens closest to the natural
                        # architectural target instead of stopping at the
                        # smallest FOV that happens to fit.
                        candidate = min(
                            external_complete,
                            key=lambda item: (abs(item.fov - 90.0), -item.analytic_score),
                        )
                        if crossed_wall.has_opening:
                            candidate.analytic_score += 34.0
                            candidate.analytic["externalAccess"] = "through-opening-wall"
                        elif crossed_wall.is_exterior:
                            candidate.analytic_score -= 24.0
                            candidate.analytic["externalAccess"] = "through-exterior-wall"
                        else:
                            candidate.analytic_score -= 10.0
                            candidate.analytic["externalAccess"] = "through-solid-interior-wall"
                        candidate.analytic["crossedWallHasOpening"] = crossed_wall.has_opening
                        candidate.analytic["crossedWallIsExterior"] = crossed_wall.is_exterior
                        wall_candidates.append(candidate)

        internal_wall_candidates = sorted(
            [candidate for candidate in wall_candidates if candidate.camera_inside_target_room],
            key=lambda candidate: candidate.analytic_score,
            reverse=True,
        )
        external_wall_candidates = sorted(
            [candidate for candidate in wall_candidates if not candidate.camera_inside_target_room],
            key=lambda candidate: candidate.analytic_score,
            reverse=True,
        )

        def diverse_shortlist(pool: list[Candidate], limit: int) -> list[Candidate]:
            selected: list[Candidate] = []
            for candidate in pool:
                if all(
                    abs(candidate.position[0] - chosen.position[0])
                    + abs(candidate.position[2] - chosen.position[2]) > 0.22
                    or abs(candidate.fov - chosen.fov) >= 8
                    for chosen in selected
                ):
                    selected.append(candidate)
                if len(selected) >= limit:
                    break
            return selected

        strict_candidates.extend(diverse_shortlist(internal_wall_candidates, 20))
        strict_candidates.extend(diverse_shortlist(external_wall_candidates, 16))


    strict_candidates.sort(key=lambda candidate: candidate.analytic_score, reverse=True)
    return strict_candidates


# ----------------------------- native pixel validation -----------------------------


def group_depth(candidate: Candidate, info: dict[str, Any]) -> float | None:
    center = info.get("world", {}).get("center", {})
    if not center:
        return None
    dx = float(center.get("x", 0.0)) - candidate.position[0]
    dz = float(center.get("z", 0.0)) - candidate.position[2]
    return dx * candidate.forward[0] + dz * candidate.forward[1]


def evaluate_candidate(
    candidate: Candidate,
    scene: SemanticVTKScene,
    room_id: str,
    room_kind: str,
) -> Candidate:
    hidden_groups = candidate.hidden_wall_ids + candidate.hidden_opening_ids + candidate.hidden_element_ids
    codes, _depth = scene.render_id_depth(candidate.pose, hidden_groups)
    primary_metric = scene.union_metric(codes, candidate.primary_ids)
    framing_metric = scene.union_metric(codes, candidate.framing_ids)
    primary_metrics = {group_id: scene.metric(codes, group_id) for group_id in candidate.primary_ids}
    companion_metrics = {group_id: scene.metric(codes, group_id) for group_id in candidate.companion_ids}

    primary_pair_overlaps: list[float] = []
    primary_pair_center_distances: list[float] = []
    primary_items = list(primary_metrics.items())
    for left_index, (_left_id, left_metric) in enumerate(primary_items):
        left_bounds = left_metric.get("bounds") or {}
        if not left_metric.get("visible") or not left_bounds:
            continue
        left_width = max(0.0, float(left_bounds["right"]) - float(left_bounds["left"]))
        left_height = max(0.0, float(left_bounds["bottom"]) - float(left_bounds["top"]))
        left_area = left_width * left_height
        left_center = (
            (float(left_bounds["left"]) + float(left_bounds["right"])) / 2.0,
            (float(left_bounds["top"]) + float(left_bounds["bottom"])) / 2.0,
        )
        for _right_id, right_metric in primary_items[left_index + 1 :]:
            right_bounds = right_metric.get("bounds") or {}
            if not right_metric.get("visible") or not right_bounds:
                continue
            right_width = max(0.0, float(right_bounds["right"]) - float(right_bounds["left"]))
            right_height = max(0.0, float(right_bounds["bottom"]) - float(right_bounds["top"]))
            right_area = right_width * right_height
            intersection_width = max(
                0.0,
                min(float(left_bounds["right"]), float(right_bounds["right"]))
                - max(float(left_bounds["left"]), float(right_bounds["left"])),
            )
            intersection_height = max(
                0.0,
                min(float(left_bounds["bottom"]), float(right_bounds["bottom"]))
                - max(float(left_bounds["top"]), float(right_bounds["top"])),
            )
            intersection = intersection_width * intersection_height
            primary_pair_overlaps.append(intersection / max(1e-9, min(left_area, right_area)))
            right_center = (
                (float(right_bounds["left"]) + float(right_bounds["right"])) / 2.0,
                (float(right_bounds["top"]) + float(right_bounds["bottom"])) / 2.0,
            )
            primary_pair_center_distances.append(math.hypot(left_center[0] - right_center[0], left_center[1] - right_center[1]))
    primary_max_overlap = max(primary_pair_overlaps, default=0.0)
    primary_min_center_separation = min(primary_pair_center_distances, default=1.0)
    visible_primary_count = sum(1 for metric in primary_metrics.values() if metric["visible"])
    visible_companion_count = sum(1 for metric in companion_metrics.values() if metric["visible"])
    primary_visible_fraction = visible_primary_count / max(1, len(candidate.primary_ids))
    companion_visible_fraction = visible_companion_count / max(1, len(candidate.companion_ids)) if candidate.companion_ids else 1.0
    center_hit = scene.center_hit(codes, candidate.primary_center)
    center_hit_pass = center_hit in set(candidate.framing_ids)

    visible_ratios = scene.visible_ratios(codes, minimum=0.0002)
    wall_ratios = [
        ratio for group_id, ratio in visible_ratios.items() if scene.group_info.get(group_id, {}).get("kind") == "wall"
    ]
    wall_total = sum(wall_ratios)
    wall_max = max(wall_ratios, default=0.0)
    target_wall_ratio = visible_ratios.get(candidate.target_wall.model_wall_id, 0.0)
    ceiling_ratio = scene.ratio_by_kind(codes, "ceiling")
    floor_ratio = scene.ratio_by_kind(codes, "floor")
    opening_ratio = scene.ratio_by_kind(codes, "opening")

    combined_slenderness = float(
        candidate.analytic.get(
            "combinedSlenderness",
            candidate.analytic.get("roomSlenderness", 1.0),
        )
    )
    envelope = space_envelope_profile(room_kind, combined_slenderness)
    ceiling_min_ratio = envelope["ceilingMin"]
    floor_min_ratio = envelope["floorMin"]
    ceiling_target_ratio = envelope["ceilingTarget"]
    floor_target_ratio = envelope["floorTarget"]


    primary_depth = (
        (candidate.primary_center[0] - candidate.position[0]) * candidate.forward[0]
        + (candidate.primary_center[2] - candidate.position[2]) * candidate.forward[1]
    )
    height, width = codes.shape
    central_band = (slice(int(height * 0.34), int(height * 0.98)), slice(int(width * 0.14), int(width * 0.86)))
    central_codes = codes[central_band]
    foreground_furniture_ratio = 0.0
    foreground_wall_ratio = 0.0
    foreground_opening_ratio = 0.0
    foreign_furniture_ratio = 0.0
    foreground_groups: list[dict[str, Any]] = []
    framing_set = set(candidate.framing_ids)
    for group_id, ratio in visible_ratios.items():
        info = scene.group_info.get(group_id, {})
        kind = info.get("kind")
        code = scene.group_code.get(group_id)
        if not code:
            continue
        central_ratio = float((central_codes == code).sum() / codes.size)
        depth = group_depth(candidate, info)
        if kind == "furniture":
            room_ids = {str(x) for x in info.get("roomIds", [])}
            if room_ids and room_id not in room_ids:
                foreign_furniture_ratio += ratio
            if group_id not in framing_set and depth is not None and depth < primary_depth * 0.82:
                weighted = max(ratio * 0.65, central_ratio * 1.9)
                foreground_furniture_ratio += weighted
                if weighted > 0.005:
                    foreground_groups.append(
                        {
                            "id": group_id,
                            "kind": kind,
                            "ratio": ratio,
                            "centralRatio": central_ratio,
                            "depth": depth,
                        }
                    )
        elif kind == "wall" and group_id != candidate.target_wall.model_wall_id:
            if depth is not None and depth < primary_depth * 0.74:
                weighted = max(ratio * 0.55, central_ratio * 1.7)
                foreground_wall_ratio += weighted
                if weighted > 0.005:
                    foreground_groups.append(
                        {
                            "id": group_id,
                            "kind": kind,
                            "ratio": ratio,
                            "centralRatio": central_ratio,
                            "depth": depth,
                        }
                    )
        elif kind == "opening":
            if depth is not None and depth < primary_depth * 0.86:
                weighted = max(ratio * 0.65, central_ratio * 1.65)
                foreground_opening_ratio += weighted
                if weighted > 0.005:
                    foreground_groups.append(
                        {
                            "id": group_id,
                            "kind": kind,
                            "ratio": ratio,
                            "centralRatio": central_ratio,
                            "depth": depth,
                        }
                    )

    bounds = primary_metric.get("bounds") or {}
    # Floor-standing subjects are allowed to meet the bottom border.  Cropping
    # the left, right, or top edge remains more serious.  Large semantic groups
    # such as an L-shaped kitchen or a long desk may touch one side when most
    # members remain visible.
    left_crop = max(0.0, 0.006 - float(bounds.get("left", 0.0))) if bounds else 1.0
    right_crop = max(0.0, float(bounds.get("right", 1.0)) - 0.994) if bounds else 1.0
    top_crop = max(0.0, 0.004 - float(bounds.get("top", 0.0))) if bounds else 1.0
    horizontal_both_sides = bool(bounds) and bounds.get("left", 0.0) <= 0.002 and bounds.get("right", 1.0) >= 0.998
    safe_bounds = bool(bounds) and (
        float(bounds.get("left", 0.0)) >= 0.002
        and float(bounds.get("right", 1.0)) <= 0.998
        and float(bounds.get("top", 0.0)) >= 0.002
    )
    minimum_visible_fraction_by_kind = {
        "bedroom": 1.0,
        "children-bedroom": 1.0,
        "bathroom": 1.0,
        "study": 1.0,
        "living": 1.0,
        "dining": 1.0,
        "kitchen": 0.80,
        "entry": 0.80,
        "balcony": 0.75,
        "laundry": 0.75,
        "closet": 0.85,
        "storage": 0.75,
        "corridor": 0.70,
        "unknown": 0.75,
    }
    minimum_visible_fraction = minimum_visible_fraction_by_kind.get(
        room_kind,
        1.0 if len(candidate.primary_ids) <= 1 else 0.80,
    )
    room_slenderness = combined_slenderness
    slender_relief = max(0.0, room_slenderness - 1.25)
    minimum_visible_fraction = max(0.72, minimum_visible_fraction - 0.05 * min(slender_relief, 2.0))
    minimum_primary_pixel_ratio = max(0.03, MIN_PRIMARY_PIXEL_RATIO * (1.0 - 0.10 * min(slender_relief, 2.0)))
    minimum_primary_bbox_area = max(0.05, MIN_PRIMARY_BBOX_AREA * (1.0 - 0.12 * min(slender_relief, 2.0)))
    foreign_limit = 0.16 if room_kind in {"living", "dining", "corridor"} else (0.10 if room_kind == "entry" else 0.08 if room_kind == "balcony" else 0.14)
    quality_advisories: list[str] = []
    if not primary_metric["visible"]:
        quality_advisories.append("primary-group-not-visible")
    if primary_metric["pixelRatio"] < minimum_primary_pixel_ratio:
        quality_advisories.append("primary-group-too-small")
    if primary_metric.get("bboxArea", 0.0) < minimum_primary_bbox_area:
        quality_advisories.append("primary-group-framing-too-small")
    if primary_visible_fraction < minimum_visible_fraction:
        quality_advisories.append("insufficient-primary-members-visible")
    minimum_member_ratio = {
        "bathroom": 0.003,
        "balcony": 0.006,
        "laundry": 0.006,
        "closet": 0.004,
    }.get(room_kind, 0.0)
    undersized_required_members = [
        group_id
        for group_id, metric in primary_metrics.items()
        if metric.get("visible") and float(metric.get("pixelRatio", 0.0)) < minimum_member_ratio
    ]
    if minimum_member_ratio > 0.0 and undersized_required_members:
        quality_advisories.append("required-primary-members-too-small")
    for group_id, metric in primary_metrics.items():
        member_bounds = metric.get("bounds") or {}
        if metric.get("visible") and (
            float(member_bounds.get("left", 0.0)) <= 0.002
            or float(member_bounds.get("right", 1.0)) >= 0.998
            or float(member_bounds.get("top", 0.0)) <= 0.002
        ):
            quality_advisories.append(f"primary-member-cropped:{group_id}")
    if not safe_bounds:
        quality_advisories.append("primary-group-severely-cropped")
    if not center_hit_pass and primary_metric["pixelRatio"] < minimum_primary_pixel_ratio * 1.45:
        quality_advisories.append("primary-center-first-hit-failed")
    if not candidate.analytic.get("primaryCompleteFit", False):
        quality_advisories.append("analytic-primary-not-complete")
    foreground_furniture_limit = (
        0.14 if room_kind == "study" and combined_slenderness >= 1.45
        else 0.085 if room_kind == "study"
        else 0.24
    )
    if foreground_furniture_ratio > foreground_furniture_limit:
        quality_advisories.append("foreground-furniture-dominates")
    if foreground_wall_ratio > 0.34:
        quality_advisories.append("foreground-wall-dominates")
    if foreground_opening_ratio > 0.18:
        quality_advisories.append("foreground-opening-dominates")
    if foreign_furniture_ratio > foreign_limit:
        quality_advisories.append("foreign-room-furniture-dominates")
    if opening_ratio > (0.46 if room_kind == "bathroom" else 0.52):
        quality_advisories.append("opening-dominates")
    if candidate.mode == "strict-wall-frontal" and candidate.wall_alignment_error_degrees > 0.25:
        quality_advisories.append("strict-wall-alignment-broken")
    if candidate.semantic_axis_required and candidate.semantic_axis_alignment < 0.90:
        quality_advisories.append("primary-facing-axis-misaligned")
    fixture_facade_alignment = float(candidate.analytic.get("fixtureFacadeAlignment", 0.0))
    if candidate.analytic.get("fixtureFacadeAxisCount", 0) and fixture_facade_alignment < 0.45:
        quality_advisories.append("fixture-front-facing-direction-missed")
    if room_kind in {"bathroom", "balcony", "laundry"} and primary_max_overlap > 0.34:
        quality_advisories.append("primary-fixtures-overlap")

    target_ratio = TARGET_PRIMARY_RATIO.get(room_kind, 0.12)
    # Formal top/bottom space belongs to the mandatory primary subject.  Tall
    # context furniture still affects ranking and occlusion, but it cannot turn
    # a complete primary composition into a false failure by touching an edge.
    framing_bounds = primary_metric.get("bounds") or {}
    if framing_bounds:
        pixel_blank_border = (
            float(framing_bounds.get("left", 0.0))
            + max(0.0, 1.0 - float(framing_bounds.get("right", 1.0)))
            + float(framing_bounds.get("top", 0.0))
            + 0.35 * max(0.0, 1.0 - float(framing_bounds.get("bottom", 1.0)))
        )
        top_open_ratio = float(framing_bounds.get("top", 0.0))
        bottom_open_ratio = max(0.0, 1.0 - float(framing_bounds.get("bottom", 1.0)))
    else:
        pixel_blank_border = 4.0
        top_open_ratio = 0.0
        bottom_open_ratio = 0.0
    effective_ceiling_ratio = max(ceiling_ratio, top_open_ratio)
    effective_floor_ratio = max(floor_ratio, bottom_open_ratio)
    envelope_complete = effective_ceiling_ratio >= ceiling_min_ratio and effective_floor_ratio >= floor_min_ratio
    if effective_ceiling_ratio < ceiling_min_ratio:
        quality_advisories.append("ceiling-not-visible-enough")
    if effective_floor_ratio < floor_min_ratio:
        quality_advisories.append("floor-not-visible-enough")
    largest_companion_ratio = max((metric.get("pixelRatio", 0.0) for metric in companion_metrics.values()), default=0.0)
    companion_dominance = largest_companion_ratio / max(primary_metric.get("pixelRatio", 0.0), 0.01)
    ceiling_reward = 34.0 * max(0.0, 1.0 - abs(effective_ceiling_ratio - ceiling_target_ratio) / max(ceiling_target_ratio, 1e-6))
    floor_reward = 22.0 * max(0.0, 1.0 - abs(effective_floor_ratio - floor_target_ratio) / max(floor_target_ratio, 1e-6))
    envelope_penalty = 0.0
    if effective_ceiling_ratio < ceiling_min_ratio:
        envelope_penalty += 260.0 * (ceiling_min_ratio - effective_ceiling_ratio) / max(ceiling_min_ratio, 1e-6)
    if effective_floor_ratio < floor_min_ratio:
        envelope_penalty += 220.0 * (floor_min_ratio - effective_floor_ratio) / max(floor_min_ratio, 1e-6)
    if effective_ceiling_ratio + 1e-6 < effective_floor_ratio * 0.72:
        envelope_penalty += 24.0
    pixel_score = (
        220.0
        - 175.0 * abs(primary_metric["pixelRatio"] - target_ratio)
        + 48.0 * primary_visible_fraction
        + 20.0 * companion_visible_fraction
        + (30.0 if center_hit_pass else -45.0)
        - 225.0 * foreground_furniture_ratio
        - 250.0 * foreground_wall_ratio
        - 210.0 * foreground_opening_ratio
        - 240.0 * foreign_furniture_ratio
        - 80.0 * max(0.0, wall_total - 0.78)
        - 75.0 * max(0.0, wall_max - 0.58)
        - 150.0 * max(0.0, opening_ratio - 0.30)
        - 70.0 * max(0.0, effective_floor_ratio - 0.42)
        + ceiling_reward
        + floor_reward
        - envelope_penalty
        + (36.0 if envelope_complete else -80.0)
        + 18.0 * min(target_wall_ratio, 0.35)
        - 52.0 * abs(candidate.window_center[0])
        - 90.0 * candidate.analytic.get("blankRatio", 0.0)
        - 52.0 * pixel_blank_border
        + (42.0 if candidate.analytic.get("primaryCompleteFit", False) else -60.0)
        - (45.0 * max(0.0, companion_dominance - 1.45) if room_kind in {"bedroom", "children-bedroom"} else 0.0)
        - max(0.06, 0.20 - 0.045 * min(max(combined_slenderness - 1.0, 0.0), 2.5))
        * max(0.0, candidate.fov - 58.0)
        + (14.0 + 5.0 * min(max(combined_slenderness - 1.0, 0.0), 2.5))
        * min(max(candidate.fov - 58.0, 0.0) / 42.0, 1.0)
        + 8.0 * min(max(candidate.analytic.get("distanceToSubjectMeters", 0.0) - 2.2, 0.0) / 2.0, 1.0)
    )

    projection_crop = None
    target_crop_foreign_groups: list[dict[str, Any]] = []
    target_crop_foreign_ratio = 0.0
    # Every single-space shot is cropped by the target room's real wall/opening
    # Entity-ID envelope.  The top remains untouched for the ceiling; left,
    # right, and especially the bottom may be removed.  Primary furniture is
    # unioned only to guarantee that the subject is not cut.  This works for
    # room-internal and external stations alike and never inspects RGB pixels.
    if primary_metric.get("bounds"):
        primary_bounds = primary_metric["bounds"]
        target_wall_codes = [
            scene.group_code[group_id]
            for group_id, info in scene.group_info.items()
            if room_id in {str(value) for value in info.get("roomIds", [])}
            and info.get("kind") in {"wall", "opening"}
            and group_id in scene.group_code
        ]
        primary_codes = [scene.group_code[group_id] for group_id in candidate.primary_ids if group_id in scene.group_code]
        target_mask = np.isin(codes, target_wall_codes) if target_wall_codes else np.zeros_like(codes, dtype=bool)
        if primary_codes:
            target_mask |= np.isin(codes, primary_codes)
        target_y, target_x = np.where(target_mask)
        if target_x.size:
            target_left = float(target_x.min()) / float(codes.shape[1])
            target_right = float(target_x.max() + 1) / float(codes.shape[1])
            target_bottom = float(target_y.max() + 1) / float(codes.shape[0])
        else:
            target_left = float(primary_bounds.get("left", 0.0))
            target_right = float(primary_bounds.get("right", 1.0))
            target_bottom = float(primary_bounds.get("bottom", 1.0))
        crop_left = max(
            0.0,
            min(target_left + 0.012, float(primary_bounds.get("left", 0.0)) - 0.02),
        )
        crop_right = min(
            1.0,
            max(target_right - 0.012, float(primary_bounds.get("right", 1.0)) + 0.02),
        )
        crop_width = crop_right - crop_left
        if crop_width < 0.40:
            center = (crop_left + crop_right) / 2.0
            crop_left = clamp(center - 0.20, 0.0, 0.60)
            crop_right = crop_left + 0.40
        framing_bottom = float((framing_metric.get("bounds") or primary_bounds).get("bottom", 1.0))
        crop_bottom = min(
            1.0,
            max(
                float(primary_bounds.get("bottom", 1.0)) + 0.02,
                min(target_bottom + 0.012, framing_bottom + 0.035),
            ),
        )
        if crop_bottom < 0.45:
            crop_bottom = 0.45
        if crop_left > 0.005 or crop_right < 0.995 or crop_bottom < 0.995:
            projection_crop = {
                "left": round(crop_left, 6),
                "top": 0.0,
                "right": round(crop_right, 6),
                "bottom": round(crop_bottom, 6),
                "source": "native-target-room-wall-envelope-v2",
                "imageRecognitionUsed": False,
            }
            crop_x0 = max(0, min(codes.shape[1] - 1, int(math.floor(crop_left * codes.shape[1]))))
            crop_x1 = max(crop_x0 + 1, min(codes.shape[1], int(math.ceil(crop_right * codes.shape[1]))))
            crop_y1 = max(1, min(codes.shape[0], int(math.ceil(crop_bottom * codes.shape[0]))))
            crop_codes = codes[:crop_y1, crop_x0:crop_x1]
            crop_area = max(1, crop_codes.size)
            for group_id, info in scene.group_info.items():
                kind = str(info.get("kind", ""))
                if kind not in {"wall", "opening", "furniture"}:
                    continue
                room_ids = {str(value) for value in info.get("roomIds", [])}
                if room_id in room_ids:
                    continue
                code = scene.group_code.get(group_id)
                if not code:
                    continue
                ratio = float((crop_codes == code).sum() / crop_area)
                if ratio < 0.0015:
                    continue
                depth = group_depth(candidate, info)
                # A foreign object behind the target subject may visually act
                # as the room boundary.  Only camera-side foreign geometry is
                # an unwanted pillar/blocker; hiding background layers would
                # open a tunnel through the whole house.
                if depth is None or depth >= primary_depth * 0.94:
                    continue
                target_crop_foreign_groups.append({
                    "id": group_id,
                    "kind": kind,
                    "ratio": ratio,
                    "depth": depth,
                    "roomIds": sorted(room_ids),
                })
                target_crop_foreign_ratio += ratio

    candidate.quality_preferred = not quality_advisories
    frontal_usable = bool(
        primary_metric["visible"]
        and primary_metric["pixelRatio"] >= minimum_primary_pixel_ratio * 0.72
        and primary_visible_fraction >= max(0.30, minimum_visible_fraction - 0.10)
        and candidate.analytic.get("primaryCompleteFit", False)
        and envelope_complete
        and foreground_furniture_ratio <= 0.34
        and foreground_wall_ratio <= 0.42
        and foreign_furniture_ratio <= foreign_limit + 0.08
    )
    bounded_analytic = clamp(candidate.analytic_score, -260.0, 260.0)
    candidate.final_score = (
        pixel_score
        + bounded_analytic
        + 210.0 * candidate.semantic_axis_alignment
        + 180.0 * fixture_facade_alignment
        - 240.0 * primary_max_overlap
        + 80.0 * min(primary_min_center_separation, 0.30)
        - 1.25 * max(0.0, candidate.fov - 54.0)
        - 42.0 * (len(candidate.hidden_wall_ids) + len(candidate.hidden_opening_ids) + len(candidate.hidden_element_ids))
        - (12.0 if candidate.placement_tier == "external-frontal" else 0.0)
        - (0.0 if candidate.quality_preferred else 180.0 if frontal_usable else 520.0)
    )
    candidate.pixel = {
        "qualityPreferred": candidate.quality_preferred,
        "frontalUsable": frontal_usable,
        "qualityAdvisories": quality_advisories,
        "cropEvidence": {
            "leftCrop": left_crop,
            "rightCrop": right_crop,
            "topCrop": top_crop,
            "horizontalBothSides": horizontal_both_sides,
            "safeBounds": safe_bounds,
        },
        "primary": primary_metric,
        "framing": framing_metric,
        "primaryMembers": primary_metrics,
        "primaryFixtureMaxOverlap": primary_max_overlap,
        "primaryFixtureMinCenterSeparation": primary_min_center_separation,
        "fixtureFacadeAlignment": fixture_facade_alignment,
        "companionMembers": companion_metrics,
        "visiblePrimaryCount": visible_primary_count,
        "primaryVisibleFraction": primary_visible_fraction,
        "minimumRequiredMemberPixelRatio": minimum_member_ratio,
        "undersizedRequiredPrimaryMembers": undersized_required_members,
        "visibleCompanionCount": visible_companion_count,
        "companionVisibleFraction": companion_visible_fraction,
        "largestCompanionPixelRatio": largest_companion_ratio,
        "companionDominanceRatio": companion_dominance,
        "semanticAxisAlignment": candidate.semantic_axis_alignment,
        "semanticAxisRequired": candidate.semantic_axis_required,
        "heroAxisAligned": (not candidate.semantic_axis_required) or candidate.semantic_axis_alignment >= 0.90,
        "centerFirstHit": center_hit,
        "centerFirstHitPass": center_hit_pass,
        "wallTotalRatio": wall_total,
        "wallMaximumRatio": wall_max,
        "targetWallRatio": target_wall_ratio,
        "openingRatio": opening_ratio,
        "ceilingRatio": ceiling_ratio,
        "floorRatio": floor_ratio,
        "topOpenRatio": top_open_ratio,
        "bottomOpenRatio": bottom_open_ratio,
        "effectiveCeilingRatio": effective_ceiling_ratio,
        "effectiveFloorRatio": effective_floor_ratio,
        "ceilingMinimumRatio": ceiling_min_ratio,
        "floorMinimumRatio": floor_min_ratio,
        "ceilingTargetRatio": ceiling_target_ratio,
        "floorTargetRatio": floor_target_ratio,
        "spaceEnvelopeComplete": envelope_complete,
        "roomShortSpanMeters": float(candidate.analytic.get("roomShortSpanMeters", 0.0)),
        "roomLongSpanMeters": float(candidate.analytic.get("roomLongSpanMeters", 0.0)),
        "roomSlenderness": float(candidate.analytic.get("roomSlenderness", room_slenderness)),
        "viewSlenderness": float(candidate.analytic.get("viewSlenderness", 1.0)),
        "combinedSlenderness": combined_slenderness,
        "minimumPrimaryPixelRatio": minimum_primary_pixel_ratio,
        "minimumPrimaryBboxArea": minimum_primary_bbox_area,
        "minimumVisibleFraction": minimum_visible_fraction,
        "foregroundFurnitureRatio": foreground_furniture_ratio,
        "foregroundWallRatio": foreground_wall_ratio,
        "foregroundOpeningRatio": foreground_opening_ratio,
        "foreignFurnitureRatio": foreign_furniture_ratio,
        "foregroundGroups": sorted(foreground_groups, key=lambda item: item["ratio"], reverse=True),
        "visibleRatios": visible_ratios,
        "pixelBlankBorder": pixel_blank_border,
        "suggestedProjectionCrop": projection_crop,
        "targetCropForeignGroups": sorted(
            target_crop_foreign_groups, key=lambda item: item["ratio"], reverse=True
        ),
        "targetCropForeignRatio": target_crop_foreign_ratio,
        "pixelScore": pixel_score,
    }
    return candidate


def evaluate_candidate_with_external_repairs(
    candidate: Candidate,
    scene: SemanticVTKScene,
    room_id: str,
    room_kind: str,
) -> list[Candidate]:
    current = evaluate_candidate(candidate, scene, room_id, room_kind)
    results = [current]
    if current.camera_inside_target_room:
        return results
    cumulative_hidden: set[str] = set()
    for repair_pass in range(3):
        protected = set(current.framing_ids)
        hideable: list[tuple[float, str, str]] = []
        for item in current.pixel.get("foregroundGroups", []):
            group_id = str(item.get("id"))
            if group_id in protected:
                continue
            kind = str(item.get("kind", ""))
            ratio = float(item.get("ratio", 0.0))
            if ratio >= 0.006 and kind in {"wall", "furniture", "opening"}:
                hideable.append((ratio + (0.24 if kind == "opening" else 0.15), group_id, kind))
        for item in current.pixel.get("targetCropForeignGroups", []):
            group_id = str(item.get("id"))
            if group_id in protected:
                continue
            kind = str(item.get("kind", ""))
            ratio = float(item.get("ratio", 0.0))
            if ratio >= 0.0015 and kind in {"wall", "furniture", "opening"}:
                hideable.append((ratio + 0.60, group_id, kind))

        selected: list[tuple[float, str, str]] = []
        seen: set[str] = set()
        already_hidden = set(current.hidden_wall_ids + current.hidden_opening_ids + current.hidden_element_ids)
        for item in sorted(hideable, reverse=True):
            if item[1] in seen or item[1] in already_hidden:
                continue
            selected.append(item)
            seen.add(item[1])
            if len(selected) >= 8:
                break
        if not selected:
            break

        repaired = deepcopy(current)
        hidden_walls = set(repaired.hidden_wall_ids)
        hidden_openings = set(repaired.hidden_opening_ids)
        hidden_elements = set(repaired.hidden_element_ids)
        for _, group_id, kind in selected:
            if kind == "wall":
                hidden_walls.add(group_id)
            elif kind == "opening":
                hidden_openings.add(group_id)
            elif kind == "furniture":
                hidden_elements.add(group_id)
        repaired.hidden_wall_ids = tuple(sorted(hidden_walls))
        repaired.hidden_opening_ids = tuple(sorted(hidden_openings))
        repaired.hidden_element_ids = tuple(sorted(hidden_elements))
        cumulative_hidden.update(seen)
        current = evaluate_candidate(repaired, scene, room_id, room_kind)
        current.pixel["externalRepairApplied"] = True
        current.pixel["externalRepairPassCount"] = repair_pass + 1
        current.pixel["externalRepairHiddenIds"] = sorted(cumulative_hidden)
        results.append(current)
    return results


def select_views(candidates: list[Candidate], count: int) -> tuple[list[Candidate], dict[str, Any]]:
    """Select the best visible strict-frontal view without turning quality into a delivery gate."""
    def hero_key(candidate: Candidate) -> tuple[float, ...]:
        primary = candidate.pixel.get("primary", {})
        foreground_cost = (
            float(candidate.pixel.get("foregroundFurnitureRatio", 0.0))
            + float(candidate.pixel.get("foregroundWallRatio", 0.0))
            + float(candidate.pixel.get("foregroundOpeningRatio", 0.0))
            + 2.5 * float(candidate.pixel.get("targetCropForeignRatio", 0.0))
        )
        access = candidate.analytic.get("externalAccess")
        access_cost = 0.0 if candidate.camera_inside_target_room else (
            0.5 if access == "through-opening-wall" else
            1.0 if access == "through-solid-interior-wall" else 1.5
        )
        hidden_count = float(
            len(candidate.hidden_wall_ids)
            + len(candidate.hidden_opening_ids)
            + len(candidate.hidden_element_ids)
        )
        perspective_ratio = float(candidate.analytic.get("perspectiveDepthRatio", 1.0))
        # Room-internal remains preferred whenever it offers a natural lens.
        # An internal 160-degree tunnel must not outrank an external strict-
        # frontal 80–100 degree view with one correctly sectioned wall.
        naturalness_tier = (
            0.0 if candidate.fov <= 100.0 and perspective_ratio <= 6.0
            else 1.0 if candidate.fov <= 120.0 and perspective_ratio <= 9.0
            else 2.0
        )
        hero_axis_cost = 0.0 if (
            not candidate.semantic_axis_required or candidate.semantic_axis_alignment >= 0.90
        ) else 1.0
        subject_visibility_cost = 0.0 if candidate.pixel.get("frontalUsable", False) else 1.0
        fixture_facade_cost = (
            0.0
            if not candidate.analytic.get("fixtureFacadeAxisCount", 0)
            or float(candidate.pixel.get("fixtureFacadeAlignment", 0.0)) >= 0.45
            else 1.0
        )
        fixture_overlap_cost = float(candidate.pixel.get("primaryFixtureMaxOverlap", 0.0))
        subject_complete_cost = 0.0 if candidate.analytic.get("primaryCompleteFit", False) else 1.0
        center_hit_cost = 0.0 if candidate.pixel.get("centerFirstHitPass", False) else 1.0
        correct_axis = hero_axis_cost == 0.0
        complete_geometry = subject_complete_cost == 0.0
        primary_near_depth = float(candidate.analytic.get("primaryNearDepthMeters", 1.5))
        minimum_clearance = 1.10 if candidate.semantic_axis_required else 0.75
        ideal_clearance = 1.60 if candidate.semantic_axis_required else 1.35
        comfortable_clearance = primary_near_depth >= minimum_clearance
        lateral_offset = abs(float(candidate.analytic.get("lateralOffsetMeters", 0.0)))
        centered_enough = (not candidate.semantic_axis_required) or lateral_offset <= 0.45
        placement_preference = (
            0.0 if correct_axis and complete_geometry and comfortable_clearance and centered_enough and candidate.camera_inside_target_room
            else 1.0 if correct_axis and complete_geometry and comfortable_clearance and centered_enough
            else 2.0 if correct_axis and complete_geometry and candidate.camera_inside_target_room
            else 3.0 if correct_axis and complete_geometry
            else 4.0 if correct_axis and candidate.camera_inside_target_room
            else 5.0 if correct_axis
            else 6.0 if candidate.camera_inside_target_room
            else 7.0
        )
        directional_lateral_cost = lateral_offset if candidate.semantic_axis_required else lateral_offset * 0.20
        subject_clearance_cost = abs(primary_near_depth - ideal_clearance)
        # The subject's facing axis and its actual support wall define the shot.
        # Lens naturalness is optimized only after the camera is looking at the
        # correct side of the subject.  This prevents a tidy 90-degree side view
        # from outranking the actual front of a bed or desk.
        return (
            subject_visibility_cost,
            fixture_facade_cost,
            fixture_overlap_cost,
            center_hit_cost,
            placement_preference,
            hero_axis_cost,
            directional_lateral_cost,
            subject_clearance_cost,
            subject_complete_cost,
            -float(candidate.semantic_axis_alignment),
            -float(candidate.target_wall.support_score),
            -float(candidate.front_score),
            foreground_cost,
            naturalness_tier,
            access_cost,
            abs(float(candidate.fov) - 90.0),
            perspective_ratio,
            hidden_count,
            -float(primary.get("bboxArea", 0.0)),
            -float(candidate.final_score),
            abs(float(candidate.window_center[0])) + 0.45 * abs(float(candidate.window_center[1])),
            float(candidate.pixel.get("pixelBlankBorder", 4.0)),
        )

    strict = [candidate for candidate in candidates if candidate.mode == "strict-wall-frontal"]
    if not strict:
        raise RuntimeError("no strict-wall-frontal geometric candidate exists")
    aligned = [
        candidate for candidate in strict
        if not candidate.semantic_axis_required or candidate.semantic_axis_alignment >= 0.90
    ]
    if not aligned:
        raise RuntimeError("no subject-facing strict-wall-frontal candidate exists")
    preferred = [candidate for candidate in aligned if candidate.quality_preferred]
    eligible = sorted(preferred or aligned, key=hero_key)
    selected = [eligible[0]]
    while len(selected) < count:
        remaining = [candidate for candidate in eligible if candidate not in selected]
        if not remaining:
            break
        def diversity_score(candidate: Candidate) -> tuple[float, ...]:
            orientation = min(
                angle_difference_degrees(candidate.forward, chosen.forward)
                for chosen in selected
            )
            position = min(
                math.hypot(
                    candidate.position[0] - chosen.position[0],
                    candidate.position[2] - chosen.position[2],
                )
                for chosen in selected
            )
            new_wall = all(candidate.target_wall.index != chosen.target_wall.index for chosen in selected)
            return (
                1.0 if new_wall else 0.0,
                min(orientation, 180.0),
                min(position, 10.0),
                candidate.final_score,
            )
        selected.append(max(remaining, key=diversity_score))

    contract = {
        "requestedViewCount": count,
        "eligibleStrictCandidateCount": len(strict),
        "subjectFacingCandidateCount": len(aligned),
        "qualityPreferredCandidateCount": len(preferred),
        "selectionPool": "quality-preferred" if preferred else "best-available-subject-facing",
        "selectionPolicy": "visible-subject-facing-wall-first-quality-advisory",
        "subjectCompletenessPreferred": True,
        "deliveryBlockedByQuality": False,
        "firstViewIsStrictFrontal": True,
        "selectedViewCount": len(selected),
        "selectedModes": ["strict-wall-frontal" for _ in selected],
        "selectedWallIndices": [candidate.target_wall.index for candidate in selected],
        "selectedForwardAnglesDegrees": [
            round(candidate.target_wall.angle_degrees, 6) for candidate in selected
        ],
    }
    return selected, contract


# ----------------------------- output -----------------------------


def strip_camera_fields(shot: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(shot)
    for key in (
        "position",
        "target",
        "fov",
        "referenceWallId",
        "windowCenter",
        "horizontalLensShiftNormalized",
        "verticalLensShiftNormalized",
        "algorithmEvidence",
        "frontalContract",
        "frontalPriorityContract",
        "placementTier",
        "cameraMode",
        "targetSpacePolicy",
    ):
        output.pop(key, None)
    return output


def candidate_to_shot(
    base_shot: dict[str, Any],
    candidate: Candidate,
    view_index: int,
    requested_count: int,
    sequence_order: int,
    contract: dict[str, Any],
) -> dict[str, Any]:
    output = strip_camera_fields(base_shot)
    original_shot_id = str(base_shot.get("shotId", f"{sequence_order:02d}-{candidate.room_id}"))
    output["shotId"] = original_shot_id if requested_count == 1 else f"{original_shot_id}-v{view_index}"
    output["sequenceOrder"] = sequence_order
    output["roomKind"] = candidate.room_kind
    output["viewIndex"] = view_index
    output["requestedViewCount"] = requested_count
    output["viewRole"] = "primary-frontal" if view_index == 1 else "secondary-frontal"
    output["composition"] = "one-point-wall-frontal"
    output["primarySubjectElementIds"] = candidate.primary_ids
    output["companionElementIds"] = candidate.companion_ids
    output["framingElementIds"] = candidate.framing_ids
    output["hiddenWallIds"] = list(candidate.hidden_wall_ids)
    output["hiddenOpeningIds"] = list(candidate.hidden_opening_ids)
    output["hiddenElementIds"] = list(candidate.hidden_element_ids)
    pose = candidate.pose
    output["position"] = [round(value, 6) for value in pose.position]
    output["target"] = [round(value, 6) for value in pose.target]
    output["fov"] = float(pose.fov)
    output["windowCenter"] = [round(value, 6) for value in pose.window_center]
    output["horizontalLensShiftNormalized"] = round(pose.window_center[0] / 2, 6)
    output["verticalLensShiftNormalized"] = round(pose.window_center[1] / 2, 6)
    output["referenceWallId"] = f"{candidate.room_id}:boundary:{candidate.target_wall.index}"
    output["modelReferenceWallId"] = candidate.target_wall.model_wall_id
    output["cameraMode"] = candidate.mode
    output["targetSpacePolicy"] = {
        "mode": "single-space-main",
        "includedRoomIds": [candidate.room_id],
        "foreignRoomsAreSceneContent": True,
        "cameraPlacementTier": candidate.placement_tier,
        "cameraInsideTargetRoom": candidate.camera_inside_target_room,
        "sectionWallIds": [],
        "insideRoomVisibilityPolicy": "subject-complete-frontal-first-zero-hide-v2",
        "projectionCrop": candidate.pixel.get("suggestedProjectionCrop"),
        "ceilingPreferred": True,
        "ceilingRequired": True,
        "floorRequired": True,
        "ceilingPolicy": "formal-shot-requires-visible-ceiling-and-floor-with-ceiling-biased-composition",
    }
    output["algorithmEvidence"] = {
        "method": METHOD,
        "singleProductionSolver": "scripts/unified_camera_solver.py",
        "legacyPoseReuseForbidden": True,
        "oldCameraCoordinatesUsed": False,
        "pixelOrImageRecognitionUsed": False,
        "nativeEntityIdValidationUsed": True,
        "subjectGrouping": "required-vs-companion-room-semantic-group-v3",
        "roomClassification": candidate.room_kind,
        "selectedMode": candidate.mode,
        "placementTier": candidate.placement_tier,
        "selectedScore": round(candidate.final_score, 6),
        "analyticScore": round(candidate.analytic_score, 6),
        "frontScore": round(candidate.front_score, 6),
        "semanticAxisAlignment": round(candidate.semantic_axis_alignment, 6),
        "semanticAxisRequired": candidate.semantic_axis_required,
        "wallAlignmentErrorDegrees": round(candidate.wall_alignment_error_degrees, 6),
        "targetWallSupportScore": round(candidate.target_wall.support_score, 6),
        "analytic": candidate.analytic,
        "nativePixelValidation": candidate.pixel,
        "cameraBodyRadiusMeters": 0.17,
        "nearPlaneMeters": 0.10,
        "zeroHide": not (candidate.hidden_wall_ids or candidate.hidden_opening_ids or candidate.hidden_element_ids),
        "hiddenWallIds": list(candidate.hidden_wall_ids),
        "hiddenOpeningIds": list(candidate.hidden_opening_ids),
        "hiddenElementIds": list(candidate.hidden_element_ids),
    }
    output["frontalContract"] = {
        "strict": True,
        "referenceWallId": f"{candidate.room_id}:boundary:{candidate.target_wall.index}",
        "modelReferenceWallId": candidate.target_wall.model_wall_id,
        "wallInteriorNormalXZ": [round(value, 6) for value in candidate.target_wall.inward],
        "opticalAxisXYZ": [round(candidate.forward[0], 6), 0.0, round(candidate.forward[1], 6)],
        "opticalAxisDotTowardWall": round(
            candidate.forward[0] * candidate.target_wall.optical_axis[0]
            + candidate.forward[1] * candidate.target_wall.optical_axis[1],
            6,
        ),
        "yawErrorDegrees": round(candidate.wall_alignment_error_degrees, 6),
        "pitchDegrees": 0.0,
        "rollDegrees": 0.0,
        "verticalFovDegrees": float(candidate.fov),
        "maximumVerticalFovDegrees": 175.0,
        "fovPolicy": "minimum-required-fov-per-station-not-room-template",
    }
    output["frontalPriorityContract"] = contract
    return output


def apply_native_html_repairs(
    output_shots: list[dict[str, Any]],
    facts_dir: str | Path,
) -> dict[str, Any]:
    """Reconcile solver-scene occlusion with native HTML ray facts.

    This remains part of the sole solver.  It never changes the selected pose,
    FOV, or window center.  Inside-room cameras stay zero-hide.  For external
    cameras it can only add a bounded first-hit blocker that the real HTML
    reports in front of a protected primary subject.
    """
    root = Path(facts_dir).resolve()
    facts_by_shot: dict[str, dict[str, Any]] = {}
    for path in root.glob("*.json"):
        try:
            value = load_json(path)
        except Exception:
            continue
        shot = value.get("shot")
        if isinstance(shot, dict) and shot.get("shotId"):
            facts_by_shot[str(shot["shotId"])] = value
    repaired = []
    missing = []
    for shot in output_shots:
        shot_id = str(shot.get("shotId"))
        room_id = str(shot.get("roomId"))
        facts = facts_by_shot.get(shot_id)
        if facts is None:
            missing.append(shot_id)
            continue
        policy = shot.get("targetSpacePolicy", {})
        if bool(policy.get("cameraInsideTargetRoom")):
            shot.setdefault("algorithmEvidence", {})["nativeHtmlRepair"] = {
                "applied": False,
                "reason": "inside-room-zero-hide",
                "addedIds": [],
            }
            continue
        protected = set(str(value) for value in shot.get("primarySubjectElementIds", []))
        protected.update(str(value) for value in shot.get("framingElementIds", []))
        hidden_walls = set(str(value) for value in shot.get("hiddenWallIds", []))
        hidden_openings = set(str(value) for value in shot.get("hiddenOpeningIds", []))
        hidden_elements = set(str(value) for value in shot.get("hiddenElementIds", []))
        hidden_all = hidden_walls | hidden_openings | hidden_elements
        remaining = 8
        additions: list[dict[str, str]] = []
        subjects = (facts.get("subjectFocus") or {}).get("subjects") or []
        primary_union = (facts.get("subjectFocus") or {}).get("primaryUnionBounds") or {}
        primary_hits = {
            str((subject.get("centerRayFirstHit") or {}).get("id", ""))
            for subject in subjects
            if subject.get("role") == "primary" and subject.get("centerOccluded")
        }

        def overlaps_primary(bounds: dict[str, Any]) -> bool:
            if not bounds or not primary_union:
                return False
            return (
                float(bounds.get("right", 0.0)) > float(primary_union.get("left", 1.0))
                and float(bounds.get("left", 1.0)) < float(primary_union.get("right", 0.0))
                and float(bounds.get("bottom", 0.0)) > float(primary_union.get("top", 1.0))
                and float(bounds.get("top", 1.0)) < float(primary_union.get("bottom", 0.0))
            )

        native_candidates: list[tuple[float, str, str]] = []
        contents = (facts.get("visibleScene") or {}).get("contents") or {}
        for kind_key, kind in (("furniture", "furniture"), ("walls", "wall"), ("openings", "opening")):
            for item in contents.get(kind_key, []) or []:
                group_id = str(item.get("id", ""))
                if not group_id or group_id in protected or group_id in hidden_all:
                    continue
                room_ids = {str(value) for value in item.get("roomIds", [])}
                if room_id in room_ids:
                    continue
                bounds = (item.get("projection") or {}).get("normalizedBounds") or {}
                area = max(0.0, float(bounds.get("right", 0.0)) - float(bounds.get("left", 0.0))) * max(
                    0.0, float(bounds.get("bottom", 0.0)) - float(bounds.get("top", 0.0))
                )
                should_remove = kind == "furniture" or group_id in primary_hits or overlaps_primary(bounds)
                if should_remove and area >= 0.001:
                    native_candidates.append((area + (0.5 if kind == "furniture" else 0.0), group_id, kind))

        for _, group_id, kind in sorted(native_candidates, reverse=True):
            if remaining <= 0 or group_id in hidden_all:
                continue
            if kind == "wall":
                hidden_walls.add(group_id)
            elif kind == "opening":
                hidden_openings.add(group_id)
            elif kind == "furniture":
                hidden_elements.add(group_id)
            hidden_all.add(group_id)
            additions.append({"id": group_id, "kind": kind, "source": "native-cropped-frame"})
            remaining -= 1

        for subject in subjects:
            if remaining <= 0 or subject.get("role") != "primary" or not subject.get("centerOccluded"):
                continue
            hit = subject.get("centerRayFirstHit") or {}
            group_id = str(hit.get("id", ""))
            kind = str(hit.get("kind", ""))
            if not group_id or group_id in protected or group_id in hidden_all:
                continue
            if kind == "wall":
                hidden_walls.add(group_id)
            elif kind == "opening":
                hidden_openings.add(group_id)
            elif kind == "furniture":
                hidden_elements.add(group_id)
            else:
                continue
            hidden_all.add(group_id)
            additions.append({"id": group_id, "kind": kind})
            remaining -= 1
        shot["hiddenWallIds"] = sorted(hidden_walls)
        shot["hiddenOpeningIds"] = sorted(hidden_openings)
        shot["hiddenElementIds"] = sorted(hidden_elements)
        shot.setdefault("algorithmEvidence", {})["nativeHtmlRepair"] = {
            "applied": bool(additions),
            "reason": "native-html-cropped-target-space-and-primary-first-hit",
            "addedIds": additions,
            "poseChanged": False,
            "fovChanged": False,
            "windowCenterChanged": False,
            "projectionCropChanged": False,
        }
        if additions:
            repaired.append({"shotId": shot_id, "addedIds": additions})
    return {"factsDir": str(root), "repaired": repaired, "missingShotIds": missing}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--semantic-facts", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--native-geometry", required=True)
    parser.add_argument("--output-plan", required=True)
    parser.add_argument("--output-diagnostics", required=True)
    parser.add_argument("--views-per-room", type=int, default=1)
    parser.add_argument("--room-ids", default="")
    parser.add_argument("--search-width", type=int, default=360)
    parser.add_argument("--search-height", type=int, default=225)
    parser.add_argument("--native-facts-dir")
    args = parser.parse_args()

    if args.views_per_room < 1 or args.views_per_room > 6:
        raise ValueError("--views-per-room must be between 1 and 6")

    semantic = load_json(args.semantic_facts)
    reject_camera_facts(semantic)
    model = load_json(args.model)
    structure = load_json(args.structure)
    native_geometry = load_json(args.native_geometry)
    shot_key, semantic_shots = get_shots(semantic)
    structure_rooms = {str(room.get("id")): room for room in structure.get("rooms", [])}
    requested_room_ids = {value.strip() for value in args.room_ids.split(",") if value.strip()}

    id_scene = SemanticVTKScene(
        args.scene,
        model,
        structure,
        native_geometry,
        size=(args.search_width, args.search_height),
        mode="id",
    )

    output_shots: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    sequence_order = 1
    for semantic_shot in semantic_shots:
        room_id = str(semantic_shot.get("roomId"))
        if requested_room_ids and room_id not in requested_room_ids:
            continue
        room_name = str(semantic_shot.get("roomName", room_id))
        structure_room = structure_rooms.get(room_id)
        if not structure_room:
            raise ValueError(f"Missing room geometry for {room_id}")
        polygon = [(float(point[0]), float(point[1])) for point in structure_room.get("polygon", [])]
        if len(polygon) < 3:
            raise ValueError(f"Invalid room polygon for {room_id}")
        if polygon_area(polygon) < 0:
            polygon.reverse()

        inventory = [item for item in semantic_shot.get("semanticInventory", []) if isinstance(item, dict)]
        boxes = [box_from_item(item, room_id) for item in inventory]
        room_kind = classify_room(semantic_shot, boxes, structure_room)
        primary_ids, companion_ids = select_subject_group(room_kind, boxes)
        primary_boxes = [box for box in boxes if box.id in primary_ids]
        companion_boxes = [box for box in boxes if box.id in companion_ids]
        framing_companion_ids = select_framing_companions(room_kind, primary_boxes, companion_boxes)
        framing_ids = list(dict.fromkeys(primary_ids + framing_companion_ids))
        walls = build_wall_frames(polygon, model, primary_boxes)
        if not walls:
            raise RuntimeError(f"No usable walls for {room_id}")

        requested_count = int(semantic_shot.get("requestedViewCount", args.views_per_room))
        requested_count = max(1, min(6, requested_count))
        requested_axis = requested_camera_axis(semantic_shot)
        candidates = generate_candidates(
            room_id,
            room_name,
            room_kind,
            polygon,
            walls,
            primary_boxes,
            companion_boxes,
            framing_ids,
            boxes,
            preferred_axes_override=[requested_axis] if requested_axis else None,
            semantic_axis_source_override="user-confirmed-camera-intent" if requested_axis else None,
        )
        evaluated = [
            evaluated_candidate
            for candidate in candidates
            if candidate.mode == "strict-wall-frontal"
            and matches_requested_camera_axis(candidate.forward, requested_axis)
            for evaluated_candidate in evaluate_candidate_with_external_repairs(
                candidate, id_scene, room_id, room_kind
            )
        ]
        if not evaluated:
            raise RuntimeError(f"No strict-wall-frontal candidates for {room_id}")
        selected, contract = select_views(evaluated, requested_count)

        room_diagnostic = {
            "roomId": room_id,
            "roomName": room_name,
            "roomKind": room_kind,
            "requestedViewCount": requested_count,
            "userCameraIntent": semantic_shot.get("userCameraIntent"),
            "primaryIds": primary_ids,
            "companionIds": companion_ids,
            "framingIds": framing_ids,
            "wallFrames": [
                {
                    "index": wall.index,
                    "modelWallId": wall.model_wall_id,
                    "a": wall.a,
                    "b": wall.b,
                    "inward": wall.inward,
                    "opticalAxis": wall.optical_axis,
                    "supportScore": wall.support_score,
                }
                for wall in walls
            ],
            "frontalPriorityContract": contract,
            "candidateCount": len(evaluated),
            "strictQualityPreferredCount": sum(
                candidate.quality_preferred and candidate.mode == "strict-wall-frontal" for candidate in evaluated
            ),
            "selected": [
                {
                    "mode": candidate.mode,
                    "targetWallId": candidate.target_wall.model_wall_id,
                    "targetWallIndex": candidate.target_wall.index,
                    "position": candidate.position,
                    "target": candidate.pose.target,
                    "fov": candidate.fov,
                    "windowCenter": candidate.window_center,
                    "wallAlignmentErrorDegrees": candidate.wall_alignment_error_degrees,
                    "frontScore": candidate.front_score,
                    "semanticAxisAlignment": candidate.semantic_axis_alignment,
                    "semanticAxisRequired": candidate.semantic_axis_required,
                    "qualityPreferred": candidate.quality_preferred,
                    "hiddenWallIds": list(candidate.hidden_wall_ids),
                    "hiddenOpeningIds": list(candidate.hidden_opening_ids),
                    "hiddenElementIds": list(candidate.hidden_element_ids),
                    "cameraInsideTargetRoom": candidate.camera_inside_target_room,
                    "finalScore": candidate.final_score,
                    "analytic": candidate.analytic,
                    "pixel": candidate.pixel,
                }
                for candidate in selected
            ],
            "topStrictCandidates": [
                {
                    "targetWallId": candidate.target_wall.model_wall_id,
                    "position": candidate.position,
                    "fov": candidate.fov,
                    "windowCenter": candidate.window_center,
                    "qualityPreferred": candidate.quality_preferred,
                    "score": candidate.final_score,
                    "qualityAdvisories": candidate.pixel.get("qualityAdvisories", []),
                }
                for candidate in sorted(evaluated, key=lambda item: item.final_score, reverse=True)[:8]
            ],
        }
        diagnostics.append(room_diagnostic)
        for view_index, candidate in enumerate(selected, 1):
            output_shots.append(
                candidate_to_shot(
                    semantic_shot,
                    candidate,
                    view_index,
                    requested_count,
                    sequence_order,
                    contract,
                )
            )
            sequence_order += 1

    native_html_repair = None
    if args.native_facts_dir:
        native_html_repair = apply_native_html_repairs(output_shots, args.native_facts_dir)

    result = deepcopy(semantic)
    result[shot_key] = output_shots
    result["schema"] = "interior.algorithmic-camera-plan.v3"
    result["schemaVersion"] = "3.0"
    result["coordinateSystem"] = "interior-world-y-up.v1"
    result["floorplanId"] = structure.get("floorplanId") or model.get("meta", {}).get("sourceFloorplanId")
    result["producer"] = {"skill": "interior-camera-capture", "version": VERSION}
    result["methodVersion"] = METHOD
    result["inputEvidence"] = {
        "model": {"path": str(Path(args.model).resolve()), "sha256": sha256(args.model)},
        "structure": {"path": str(Path(args.structure).resolve()), "sha256": sha256(args.structure)},
        "semanticFacts": {"path": str(Path(args.semantic_facts).resolve()), "sha256": sha256(args.semantic_facts)},
        "scene": {"path": str(Path(args.scene).resolve()), "sha256": sha256(args.scene)},
        "nativeGeometry": {"path": str(Path(args.native_geometry).resolve()), "sha256": sha256(args.native_geometry)},
    }
    result["algorithmPolicy"] = {
        "productionSolverCount": 1,
        "productionSolver": "scripts/unified_camera_solver.py",
        "rendererMaySelectOrModifyCamera": False,
        "singleViewSubjectCompleteFirst": True,
        "singleViewFrontalFirstAmongCompleteCandidates": True,
        "multiViewFirstShotFrontal": True,
        "legacyPoseReuseForbidden": True,
        "zeroHideDefault": True,
        "nativeHtmlRepairOwnedBySoleSolver": True,
    }
    if native_html_repair is not None:
        result["nativeHtmlRepair"] = native_html_repair
    result["generatedAtUtc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    output_plan = Path(args.output_plan)
    output_diagnostics = Path(args.output_diagnostics)
    output_plan.parent.mkdir(parents=True, exist_ok=True)
    output_diagnostics.parent.mkdir(parents=True, exist_ok=True)
    output_plan.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    output_diagnostics.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    id_scene.close()

    print(
        json.dumps(
            {
                "method": METHOD,
                "version": VERSION,
                "roomCount": len(diagnostics),
                "shotCount": len(output_shots),
                "strictFirstViewCount": sum(
                    1 for room in diagnostics if room["frontalPriorityContract"]["firstViewIsStrictFrontal"]
                ),
                "outputPlan": str(output_plan),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
