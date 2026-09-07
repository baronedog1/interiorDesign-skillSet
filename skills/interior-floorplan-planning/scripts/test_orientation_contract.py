#!/usr/bin/env python3
"""Regression tests for the explicit source orientation-unit contract."""

from __future__ import annotations

import importlib.util
import math
import tempfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("compile_floorplan_handoff.py")
SPEC = importlib.util.spec_from_file_location("floorplan_compiler", MODULE_PATH)
assert SPEC and SPEC.loader
COMPILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPILER)


def close(first: float, second: float, tolerance: float = 1e-6) -> None:
    assert abs(first - second) <= tolerance, (first, second)


def point_close(first: list[float], second: list[float], tolerance: float = 1e-6) -> None:
    close(first[0], second[0], tolerance)
    close(first[1], second[1], tolerance)


def reconstruct_world(geometry: dict, yaw: float) -> list[list[float]]:
    bounds = geometry["bounds"]
    width = geometry["width"]
    depth = geometry["depth"]
    center_local = [
        (bounds["minX"] + bounds["maxX"]) / 2,
        (bounds["minY"] + bounds["maxY"]) / 2,
    ]
    local = [
        [
            center_local[0] + point[0] * width,
            center_local[1] + point[1] * depth,
        ]
        for point in geometry["normalized"]
    ]
    return [COMPILER.rotate_plan_point(point, yaw) for point in local]


def test_cardinal_degrees() -> None:
    expected = {
        0: 0.0,
        90: math.pi / 2,
        -90: -math.pi / 2,
        180: math.pi,
    }
    for degrees, radians in expected.items():
        item = {"id": f"rotation-{degrees}", "rotationY": degrees}
        close(COMPILER.source_rotation_radians(item, "degrees"), radians)
    for ambiguous in (None, "radians"):
        try:
            COMPILER.source_rotation_radians({"id": "ambiguous", "rotationY": 90}, ambiguous)
        except ValueError as error:
            assert "explicitly set to degrees" in str(error)
        else:
            raise AssertionError("ambiguous source angle unit was accepted")


def test_source_compilation_rejects_ambiguous_unit() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.bin"
        source.write_bytes(b"orientation-contract-test")
        base = {
            "schema": COMPILER.SOURCE_SCHEMA,
            "sourceSha256": COMPILER.digest(source),
            "floorplanId": "orientation-contract-test",
            "planBounds": [0, 0, 10, 10],
            "knownSizeMm": {"width": 1000, "depth": 1000},
            "rooms": [],
            "walls": [],
            "openings": [],
            "objects": [],
            "floorBoundary": [],
        }
        image = COMPILER.Image.new("RGB", (10, 10), "white")
        missing_errors = COMPILER.validate_source_model(base, source, image)
        assert any("orientationAngleUnit must be explicitly set to degrees" in error for error in missing_errors)
        explicit_errors = COMPILER.validate_source_model(
            {**base, "orientationAngleUnit": "degrees"}, source, image,
        )
        assert not any("orientationAngleUnit" in error for error in explicit_errors)


def test_rotated_rectangle_round_trip() -> None:
    yaw = COMPILER.source_rotation_radians({"id": "rectangle", "rotationY": 90}, "degrees")
    local = [[-1.4, -0.8], [1.4, -0.8], [1.4, 0.8], [-1.4, 0.8]]
    translated_world = []
    for point in local:
        rotated = COMPILER.rotate_plan_point(point, yaw)
        translated_world.append([rotated[0] + 4.2, rotated[1] - 1.3])
    geometry = COMPILER.oriented_geometry(translated_world, yaw)
    close(geometry["width"], 2.8)
    close(geometry["depth"], 1.6)
    for original, rebuilt in zip(translated_world, reconstruct_world(geometry, yaw)):
        point_close(original, rebuilt)


def test_irregular_outline_round_trip() -> None:
    yaw = COMPILER.source_rotation_radians({"id": "irregular", "rotationY": -37}, "degrees")
    local = [
        [-1.7, -0.9], [1.2, -0.9], [1.2, -0.2], [0.4, -0.2],
        [0.4, 1.1], [-1.7, 1.1],
    ]
    translated_world = []
    for point in local:
        rotated = COMPILER.rotate_plan_point(point, yaw)
        translated_world.append([rotated[0] - 2.4, rotated[1] + 5.6])
    geometry = COMPILER.oriented_geometry(translated_world, yaw)
    close(geometry["width"], 2.9)
    close(geometry["depth"], 2.0)
    for original, rebuilt in zip(translated_world, reconstruct_world(geometry, yaw)):
        point_close(original, rebuilt)


def test_canonical_facing_preserved() -> None:
    item = {
        "id": "canonical-facing",
        "rotationY": 90,
        "orientation": {
            "evidence": "source-symbol",
            "localAxes": {"front": "+X", "back": "-X"},
        },
    }
    yaw, orientation = COMPILER.canonical_object_orientation(item, "degrees")
    assert orientation["localAxes"] == {"front": "+Z", "back": "-Z"}
    source_yaw = COMPILER.source_rotation_radians(item, "degrees")
    for role in ("front", "back"):
        source_world = COMPILER.rotate_plan_point(
            COMPILER.ORIENTATION_AXIS_VECTORS[item["orientation"]["localAxes"][role]],
            source_yaw,
        )
        accepted_world = COMPILER.rotate_plan_point(
            COMPILER.ORIENTATION_AXIS_VECTORS[orientation["localAxes"][role]],
            yaw,
        )
        point_close(source_world, accepted_world)


def test_case02_bed_local_frame_and_world_footprint() -> None:
    plan_bounds = [100, 20, 500, 600]
    scale_x = 4.2 / (plan_bounds[2] - plan_bounds[0])
    scale_z = 5.6 / (plan_bounds[3] - plan_bounds[1])
    source_outline = [[110, 205], [365, 205], [365, 390], [110, 390]]
    world_outline = [
        [
            (point[0] - plan_bounds[0]) * scale_x,
            (point[1] - plan_bounds[1]) * scale_z,
        ]
        for point in source_outline
    ]
    item = {
        "id": "bed-main",
        "rotationY": 90,
        "orientation": {
            "evidence": "source-symbol",
            "localAxes": {"front": "+Z", "headboard": "-Z"},
        },
    }
    yaw, orientation = COMPILER.canonical_object_orientation(item, "degrees")
    close(yaw, math.pi / 2)
    assert orientation["localAxes"]["headboard"] == "-Z"
    geometry = COMPILER.oriented_geometry(world_outline, yaw)
    close(geometry["width"], 1.786206896551724)
    close(geometry["depth"], 2.6775)
    for original, rebuilt in zip(world_outline, reconstruct_world(geometry, yaw)):
        point_close(original, rebuilt)


def main() -> int:
    test_cardinal_degrees()
    test_source_compilation_rejects_ambiguous_unit()
    test_rotated_rectangle_round_trip()
    test_irregular_outline_round_trip()
    test_canonical_facing_preserved()
    test_case02_bed_local_frame_and_world_footprint()
    print("orientation contract regressions passed: 6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
