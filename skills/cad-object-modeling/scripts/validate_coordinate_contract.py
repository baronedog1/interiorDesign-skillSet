#!/usr/bin/env python3
"""Validate source/CAD coordinate transforms and anti-mirror landmarks."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

from common import ContractError, load_json, object_hash, validate_schema, write_json


def matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3)]
        for row in range(3)
    ]


def apply(matrix: list[list[float]], point: list[float]) -> list[float]:
    vector = [float(point[0]), float(point[1]), 1.0]
    result = [sum(matrix[row][column] * vector[column] for column in range(3)) for row in range(3)]
    if abs(result[2]) <= 1e-12:
        raise ContractError("Coordinate transform produced a point at infinity")
    return [result[0] / result[2], result[1] / result[2]]


def distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def determinant(matrix: list[list[float]]) -> float:
    return (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )


def validate_plan_coordinates(plan_path: Path) -> tuple[dict[str, Any], bool]:
    plan = load_json(plan_path)
    validate_schema(plan, "cad-object-plan.schema.json")
    checks: list[dict[str, Any]] = []
    if object_hash(plan, "planHash") != plan["planHash"]:
        checks.append({"check": "planHash", "passed": False, "detail": "canonical hash mismatch"})
    else:
        checks.append({"check": "planHash", "passed": True, "detail": "matched"})
    frame = plan["coordinateFrame"]
    frame_passed = frame == {
        "handedness": "right",
        "x": "+right",
        "y": "+back",
        "z": "+up",
        "origin": frame["origin"],
    }
    checks.append({"check": "rightHandedFrame", "passed": frame_passed, "detail": frame})
    view_ids: set[str] = set()
    for transform in plan["viewTransforms"]:
        view_id = transform["viewId"]
        if view_id in view_ids:
            checks.append({"check": "uniqueViewId", "viewId": view_id, "passed": False, "detail": "duplicate"})
            continue
        view_ids.add(view_id)
        forward = [[float(value) for value in row] for row in transform["sourceToPlane"]]
        inverse = [[float(value) for value in row] for row in transform["planeToSource"]]
        det = determinant(forward)
        product = matmul(forward, inverse)
        identity_error = max(
            abs(product[row][column] - (1.0 if row == column else 0.0))
            for row in range(3)
            for column in range(3)
        )
        source_errors: list[float] = []
        plane_errors: list[float] = []
        for control in transform["controlPoints"]:
            calculated_plane = apply(forward, control["source"])
            calculated_source = apply(inverse, control["plane"])
            plane_errors.append(distance(calculated_plane, control["plane"]))
            source_errors.append(distance(calculated_source, control["source"]))
            source_errors.append(distance(apply(inverse, calculated_plane), control["source"]))
        max_source = max(source_errors, default=math.inf)
        max_plane = max(plane_errors, default=math.inf)
        passed = (
            abs(det) > 1e-12
            and identity_error <= 1e-8
            and max_source <= transform["maxSourceRoundTripErrorPx"]
            and max_plane <= transform["maxPlaneErrorMm"]
        )
        checks.append(
            {
                "check": "viewTransform",
                "viewId": view_id,
                "passed": passed,
                "detail": {
                    "determinant": det,
                    "identityError": identity_error,
                    "maxSourceErrorPx": max_source,
                    "maxPlaneErrorMm": max_plane,
                    "controlPointCount": len(transform["controlPoints"]),
                },
            }
        )
    for orientation in plan["orientationChecks"]:
        passed = (
            orientation["viewId"] in view_ids
            and orientation["expectedCadSide"] == orientation["evaluatedCadSide"]
        )
        checks.append(
            {
                "check": "orientationLandmark",
                "viewId": orientation["viewId"],
                "landmarkId": orientation["landmarkId"],
                "passed": passed,
                "detail": {
                    "expected": orientation["expectedCadSide"],
                    "evaluated": orientation["evaluatedCadSide"],
                    "evidenceId": orientation["evidenceId"],
                },
            }
        )
    passed = all(check["passed"] for check in checks)
    report = {
        "schema": "interior.cad-object-coordinate-report.v1",
        "objectId": plan["objectId"],
        "planHash": plan["planHash"],
        "checks": checks,
        "overallPassed": passed,
    }
    return report, passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report, passed = validate_plan_coordinates(args.plan.resolve())
        write_json(args.output.resolve(), report)
        if not passed:
            print("coordinate contract failed", file=sys.stderr)
            return 1
        print(f"coordinate contract passed: views={len(report['checks'])}")
        return 0
    except ContractError as exc:
        print(f"coordinate contract failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
