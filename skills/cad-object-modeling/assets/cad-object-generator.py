#!/usr/bin/env python3
"""Schema-driven build123d generator scaffold for one CAD object plan."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from build123d import (
    Align,
    Box,
    Cylinder,
    Face,
    Location,
    Vector,
    Wire,
    extrude,
    fillet,
)
from cadpy.assembly import AssemblyHelper


PLAN_PATH = Path(
    os.environ.get("CAD_OBJECT_PLAN", Path(__file__).with_name("cad-object-plan.json"))
).resolve()


def canonical_hash(value: dict[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    payload = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def positive(value: Any, label: str) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def vector3(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must contain three numbers")
    return float(value[0]), float(value[1]), float(value[2])


def load_plan() -> dict[str, Any]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if plan.get("schema") != "interior.cad-object-plan.v1":
        raise ValueError("Expected interior.cad-object-plan.v1")
    if plan.get("units") != "mm":
        raise ValueError("Generator supports millimeter CAD plans")
    if canonical_hash(plan, "planHash") != plan.get("planHash"):
        raise ValueError("CAD plan canonical hash mismatch")
    return plan


def make_box(geometry: dict[str, Any], rounded: bool) -> Any:
    size = vector3(geometry.get("size"), "geometry.size")
    length, width, height = (positive(item, "box size") for item in size)
    shape = Box(
        length,
        width,
        height,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    radius = float(geometry.get("radius", 0.0)) if rounded else 0.0
    if radius < 0 or radius >= min(length, width, height) / 2:
        raise ValueError("rounded_box radius must be non-negative and less than half the smallest size")
    if radius > 0:
        shape = fillet(shape.edges(), radius)
    return shape


def make_cylinder(geometry: dict[str, Any]) -> Any:
    radius = positive(geometry.get("radius"), "cylinder radius")
    height = positive(geometry.get("height"), "cylinder height")
    return Cylinder(
        radius,
        height,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )


def make_extruded_polygon(geometry: dict[str, Any]) -> Any:
    raw_points = geometry.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 3:
        raise ValueError("extruded_polygon points must contain at least three XY points")
    points = []
    for index, raw in enumerate(raw_points):
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError(f"extruded_polygon point {index} is invalid")
        points.append(Vector(float(raw[0]), float(raw[1]), 0.0))
    height = positive(geometry.get("height"), "extruded_polygon height")
    wire = Wire.make_polygon(points, close=True)
    face = Face(wire)
    return extrude(face, amount=height)


def make_component(component: dict[str, Any]) -> Any:
    geometry = component["geometry"]
    primitive = geometry["primitive"]
    if primitive == "box":
        shape = make_box(geometry, rounded=False)
    elif primitive == "rounded_box":
        shape = make_box(geometry, rounded=True)
    elif primitive == "cylinder":
        shape = make_cylinder(geometry)
    elif primitive == "extruded_polygon":
        shape = make_extruded_polygon(geometry)
    else:
        raise ValueError(
            f"Unsupported primitive {primitive!r} for {component['componentId']}; "
            "add one audited named build123d constructor that reads this plan"
        )
    translation = vector3(component["transform"]["translation"], "transform.translation")
    rotation = vector3(component["transform"]["rotationDegXYZ"], "transform.rotationDegXYZ")
    return shape.moved(Location(translation, rotation))


def gen_step() -> Any:
    plan = load_plan()
    assembly = AssemblyHelper(plan["objectId"])
    component_ids: set[str] = set()
    for component in plan["components"]:
        component_id = component["componentId"]
        if component_id in component_ids:
            raise ValueError(f"Duplicate componentId: {component_id}")
        component_ids.add(component_id)
        assembly.add(make_component(component), component_id)
    if not component_ids:
        raise ValueError("CAD plan contains no components")
    return assembly.build()
