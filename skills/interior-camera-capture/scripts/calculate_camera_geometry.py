#!/usr/bin/env python3
"""Generate backend-neutral camera candidates from measured 3D envelopes."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


PROFILE_PATH = Path(__file__).resolve().parents[1] / "assets" / "room-camera-algorithms.json"
PROFILE = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
SENSOR_WIDTH_MM = float(PROFILE["sensor"]["widthMm"])
SENSOR_HEIGHT_MM = float(PROFILE["sensor"]["heightMm"])
SHARED = PROFILE["shared"]
METHOD_VERSION = "deterministic-wall-normal-camera-v7"
FIT_FORMULA = (
    "Fw=max(Wa/oa,Wf/of,Wc/oc,Ha/ov*36/22.5,Hf/ov*36/22.5);"
    "D=Fw*focal/36*1.05"
)
ROOM_CAMERA_HEIGHTS = {
    room: float(config["cameraHeightMeters"])
    for room, config in PROFILE["rooms"].items()
}
COMPOSITION_RULES = {
    "one-point-frontal": {
        "basis": "anchor-reference-context-obb",
        "occupancies": tuple(SHARED["frontalOccupancies"]),
    },
    "relationship": {
        "basis": "anchor-context-obb",
        "occupancies": tuple(SHARED["relationshipOccupancies"]),
    },
    "entry-user": {
        "basis": "anchor-context-obb",
        "occupancies": tuple(SHARED["relationshipOccupancies"]),
    },
    "detail": {
        "basis": "subject-detail-obb",
        "occupancies": (0.70, 0.85),
    },
}
FRONTAL_TOLERANCES = {
    "yawErrorDeg": 1.0,
    "pitchAbsDeg": 0.25,
    "rollAbsDeg": 0.1,
    "alignmentResidualDeg": 0.25,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor-width", type=float, required=True)
    parser.add_argument("--anchor-height", type=float, required=True)
    parser.add_argument("--anchor-depth", type=float, default=0.0)
    parser.add_argument("--anchor-ids", required=True)
    parser.add_argument("--reference-width", type=float, required=True)
    parser.add_argument("--reference-height", type=float)
    parser.add_argument("--reference-ids", required=True)
    parser.add_argument("--context-width", type=float, default=0.0)
    parser.add_argument("--context-height", type=float, default=0.0)
    parser.add_argument("--context-ids", default="")
    parser.add_argument("--reference-occupancy", type=float)
    parser.add_argument("--context-occupancy", type=float, default=0.94)
    parser.add_argument("--wall-width", type=float)
    parser.add_argument("--reference-face-offset", type=float, default=0.0)
    parser.add_argument("--near-depth-offset", type=float, default=0.0)
    parser.add_argument("--far-depth-offset", type=float, default=0.0)
    parser.add_argument("--available-depth", type=float, required=True)
    parser.add_argument("--room-type", choices=sorted(ROOM_CAMERA_HEIGHTS), required=True)
    parser.add_argument("--composition", choices=sorted(COMPOSITION_RULES), default="one-point-frontal")
    parser.add_argument("--vertical-occupancy", type=float, default=float(SHARED["verticalOccupancy"]))
    parser.add_argument("--target-occupancies")
    parser.add_argument("--focal-length", type=float)
    parser.add_argument("--tiny-room-audited", action="store_true")
    parser.add_argument("--structure-data", type=Path)
    parser.add_argument("--reference-wall-id")
    parser.add_argument("--target-xz")
    parser.add_argument("--camera-side-xz")
    return parser.parse_args()


def csv_ids(raw: str, field: str, allow_empty: bool = False) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values and not allow_empty:
        raise SystemExit(f"{field} cannot be empty")
    return values


def parse_xz(raw: str, field: str) -> tuple[float, float]:
    try:
        values = tuple(float(value.strip()) for value in raw.split(","))
    except (AttributeError, ValueError) as exc:
        raise SystemExit(f"{field} must be formatted as X,Z") from exc
    if len(values) != 2:
        raise SystemExit(f"{field} must be formatted as X,Z")
    return values


def normalize2(vector: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*vector)
    if length <= 1e-9:
        raise SystemExit("cannot normalize a zero-length vector")
    return vector[0] / length, vector[1] / length


def cross2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def wall_world_segment(structure: dict, wall_id: str) -> tuple[tuple[float, float], tuple[float, float]]:
    walls = {wall.get("id"): wall for wall in structure.get("walls", [])}
    if wall_id not in walls:
        raise SystemExit(f"unknown --reference-wall-id {wall_id}")
    coordinate_system = structure.get("coordinateSystem", {})
    if coordinate_system.get("units") != "m":
        raise SystemExit("structure coordinate units must be meters")
    origin = coordinate_system.get("origin")
    if origin == "north-west":
        half_width = float(coordinate_system["realWidthMeters"]) / 2
        half_depth = float(coordinate_system["realDepthMeters"]) / 2

        def to_world(point: list[float]) -> tuple[float, float]:
            return float(point[0]) - half_width, float(point[1]) - half_depth
    elif origin == "world-center":

        def to_world(point: list[float]) -> tuple[float, float]:
            return float(point[0]), float(point[1])
    else:
        raise SystemExit(f"unsupported structure coordinate origin {origin!r}")
    wall = walls[wall_id]
    return to_world(wall["start"]), to_world(wall["end"])


def frontal_basis(args: argparse.Namespace) -> dict | None:
    wall_args = (args.structure_data, args.reference_wall_id, args.target_xz, args.camera_side_xz)
    if args.composition != "one-point-frontal":
        if any(wall_args):
            raise SystemExit("wall-normal arguments are only valid for one-point-frontal")
        return None
    if not all(wall_args):
        raise SystemExit(
            "one-point-frontal requires --structure-data, --reference-wall-id, "
            "--target-xz and --camera-side-xz"
        )
    structure = json.loads(args.structure_data.read_text(encoding="utf-8"))
    if structure.get("schema") != "interior.floorplan-structure.v3":
        raise SystemExit("--structure-data must use interior.floorplan-structure.v3")
    target_xz = parse_xz(args.target_xz, "--target-xz")
    camera_side_xz = parse_xz(args.camera_side_xz, "--camera-side-xz")
    wall_start, wall_end = wall_world_segment(structure, args.reference_wall_id)
    wall_delta = (wall_end[0] - wall_start[0], wall_end[1] - wall_start[1])
    wall_tangent = normalize2(wall_delta)
    normal_a = (-wall_tangent[1], wall_tangent[0])
    side_to_target = (target_xz[0] - camera_side_xz[0], target_xz[1] - camera_side_xz[1])
    if math.hypot(*side_to_target) <= 1e-9:
        raise SystemExit("--camera-side-xz must differ from --target-xz")
    wall_normal = normal_a if (
        normal_a[0] * side_to_target[0] + normal_a[1] * side_to_target[1]
    ) >= 0 else (-normal_a[0], -normal_a[1])
    return {
        "wallStart": wall_start,
        "wallEnd": wall_end,
        "wallDelta": wall_delta,
        "wallTangent": wall_tangent,
        "wallNormal": wall_normal,
        "targetXZ": target_xz,
    }


def fov_for_focal(focal_length_mm: float) -> float:
    return math.degrees(2 * math.atan(SENSOR_HEIGHT_MM / (2 * focal_length_mm)))


def lens_band(focal_length_mm: float) -> str:
    if focal_length_mm < 20:
        return "audited-ultra-wide"
    if focal_length_mm < 28:
        return "wide"
    return "standard"


def parse_occupancies(raw: str | None, defaults: tuple[float, ...]) -> tuple[float, ...]:
    if not raw:
        return defaults
    values = tuple(float(value.strip()) for value in raw.split(",") if value.strip())
    if not values or any(value <= 0 or value >= 1 for value in values):
        raise SystemExit("target occupancies must be numbers between 0 and 1")
    return values


def focal_chain(args: argparse.Namespace) -> tuple[float, ...]:
    if args.focal_length is not None:
        if args.focal_length == 16:
            raise SystemExit("16mm is never an accepted automatic or explicit final lens")
        if args.focal_length == 18 and not args.tiny_room_audited:
            raise SystemExit("18mm requires --tiny-room-audited")
        if not 18 <= args.focal_length <= 85:
            raise SystemExit("--focal-length must be between 18 and 85mm")
        return (float(args.focal_length),)
    chain = [float(value) for value in SHARED["focalChainMm"] if float(value) != 16]
    if not args.tiny_room_audited:
        chain = [value for value in chain if value != 18]
    return tuple(chain)


def validate_positive(args: argparse.Namespace) -> None:
    for name in ("anchor_width", "anchor_height", "reference_width", "available_depth"):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    for name in ("anchor_depth", "context_width", "context_height", "near_depth_offset", "far_depth_offset"):
        if getattr(args, name) < 0:
            raise SystemExit(f"--{name.replace('_', '-')} cannot be negative")
    if args.reference_height is not None and args.reference_height <= 0:
        raise SystemExit("--reference-height must be positive")
    if args.reference_face_offset < 0:
        raise SystemExit("--reference-face-offset cannot be negative")
    if not 0.45 <= args.vertical_occupancy <= 0.85:
        raise SystemExit("--vertical-occupancy must be between 0.45 and 0.85")
    if not 0.5 <= args.context_occupancy <= 0.98:
        raise SystemExit("--context-occupancy must be between 0.5 and 0.98")


def main() -> int:
    args = parse_args()
    validate_positive(args)
    frontal = frontal_basis(args)
    rule = COMPOSITION_RULES[args.composition]
    occupancies = parse_occupancies(args.target_occupancies, rule["occupancies"])
    focals = focal_chain(args)
    anchor_ids = csv_ids(args.anchor_ids, "--anchor-ids")
    reference_ids = csv_ids(args.reference_ids, "--reference-ids")
    context_ids = csv_ids(args.context_ids, "--context-ids", allow_empty=True)
    reference_height = args.reference_height or args.anchor_height
    wall_width = args.wall_width or args.reference_width
    if wall_width <= 0:
        raise SystemExit("--wall-width must be positive")

    candidates = []
    for occupancy in occupancies:
        reference_occupancy = args.reference_occupancy or occupancy
        if not 0 < reference_occupancy < 1:
            raise SystemExit("--reference-occupancy must be between 0 and 1")
        envelope_terms = {
            "anchorWidth": args.anchor_width / occupancy,
            "referenceWidth": args.reference_width / reference_occupancy,
            "contextWidth": args.context_width / args.context_occupancy if args.context_width else 0.0,
            "anchorHeight": args.anchor_height / args.vertical_occupancy * SENSOR_WIDTH_MM / SENSOR_HEIGHT_MM,
            "referenceHeight": reference_height / args.vertical_occupancy * SENSOR_WIDTH_MM / SENSOR_HEIGHT_MM,
        }
        frame_width = max(envelope_terms.values())
        frame_height = frame_width * SENSOR_HEIGHT_MM / SENSOR_WIDTH_MM
        for focal in focals:
            base_distance = frame_width * focal / SENSOR_WIDTH_MM
            target_distance = base_distance * float(SHARED["distanceSafetyFactor"])
            fit_pass = target_distance <= args.available_depth + 1e-9
            near_distance = max(0.01, target_distance - args.near_depth_offset)
            far_distance = target_distance + args.far_depth_offset
            depth_scale_ratio = far_distance / near_distance
            camera_height = ROOM_CAMERA_HEIGHTS[args.room_type]
            candidate = {
                "candidateId": f"{args.composition}-o{int(round(occupancy * 100)):02d}-f{int(round(focal)):02d}",
                "coordinateSystem": "interior-world-y-up.v1",
                "cameraHeightMeters": camera_height,
                "focalLengthMm": focal,
                "fov": round(fov_for_focal(focal), 3),
                "lensBand": lens_band(focal),
                "distortion": 0,
                "framing": {
                    "sensorWidthMm": SENSOR_WIDTH_MM,
                    "sensorHeightMm": SENSOR_HEIGHT_MM,
                    "framingBasis": rule["basis"],
                    "targetOccupancy": round(occupancy, 4),
                    "referenceOccupancyPolicy": round(reference_occupancy, 4),
                    "contextOccupancyPolicy": round(args.context_occupancy, 4),
                    "verticalOccupancyPolicy": round(args.vertical_occupancy, 4),
                    "envelopes": {
                        "anchor": {"widthMeters": args.anchor_width, "heightMeters": args.anchor_height, "depthMeters": args.anchor_depth, "elementIds": anchor_ids},
                        "referenceFacade": {"widthMeters": args.reference_width, "heightMeters": reference_height, "elementIds": reference_ids},
                        "context": {"widthMeters": args.context_width, "heightMeters": args.context_height, "elementIds": context_ids},
                    },
                    "envelopeFrameWidthTerms": {key: round(value, 6) for key, value in envelope_terms.items()},
                    "frameWidthMeters": round(frame_width, 6),
                    "frameHeightMeters": round(frame_height, 6),
                    "availableDepthMeters": round(args.available_depth, 6),
                    "targetPlaneDistanceMeters": round(target_distance, 6),
                    "cameraToReferenceFaceMeters": round(target_distance + args.reference_face_offset, 6),
                    "distanceSafetyFactor": float(SHARED["distanceSafetyFactor"]),
                    "horizontalOccupancy": round(args.anchor_width / frame_width, 6),
                    "verticalOccupancy": round(args.anchor_height / frame_height, 6),
                    "depthScaleRatioEstimate": round(depth_scale_ratio, 6),
                    "depthScaleRatioLimit": float(SHARED["depthScaleRatioLimit"]),
                    "fitFormula": FIT_FORMULA,
                    "fitPass": fit_pass and depth_scale_ratio <= float(SHARED["depthScaleRatioLimit"]),
                    "measurementBasis": "native-model-obb-eight-corners",
                },
            }
            if frontal:
                target_xz = frontal["targetXZ"]
                view = frontal["wallNormal"]
                position_xz = (
                    target_xz[0] - view[0] * target_distance,
                    target_xz[1] - view[1] * target_distance,
                )
                wall_start = frontal["wallStart"]
                wall_delta = frontal["wallDelta"]
                ray_to_wall = (wall_start[0] - position_xz[0], wall_start[1] - position_xz[1])
                denominator = cross2(view, wall_delta)
                if abs(denominator) <= 1e-9:
                    raise SystemExit("frontal optical axis cannot intersect the reference wall")
                camera_to_wall = cross2(ray_to_wall, wall_delta) / denominator
                segment_parameter = cross2(ray_to_wall, view) / denominator
                if camera_to_wall <= 0 or not -1e-6 <= segment_parameter <= 1 + 1e-6:
                    raise SystemExit("frontal optical ray misses the reference wall segment")
                intersection = (
                    position_xz[0] + camera_to_wall * view[0],
                    position_xz[1] + camera_to_wall * view[1],
                )
                candidate.update({
                    "position": [round(position_xz[0], 6), camera_height, round(position_xz[1], 6)],
                    "target": [round(target_xz[0], 6), camera_height, round(target_xz[1], 6)],
                    "levelCamera": True,
                    "frontalAlignment": {
                        "mode": "reference-wall-normal",
                        "referenceWallId": args.reference_wall_id,
                        "wallTangentXZ": [round(value, 6) for value in frontal["wallTangent"]],
                        "wallNormalXZ": [round(value, 6) for value in view],
                        "opticalAxisXYZ": [round(view[0], 6), 0, round(view[1], 6)],
                        "cameraUp": [0, 1, 0],
                        "rayIntersectionXZ": [round(value, 6) for value in intersection],
                        "raySegmentParameter": round(segment_parameter, 6),
                        "cameraToWallMeters": round(camera_to_wall, 6),
                        "yawErrorDeg": 0,
                        "pitchDeg": 0,
                        "rollDeg": 0,
                        "alignmentResidualDeg": 0,
                        "sensorPlaneParallelToWall": True,
                        "worldVerticalsRemainVertical": True,
                        "targetHeightEqualsCameraHeight": True,
                        "rayHitsReferenceWall": True,
                        "tolerances": FRONTAL_TOLERANCES,
                    },
                })
            candidates.append(candidate)

    fitting = [candidate for candidate in candidates if candidate["framing"]["fitPass"]]
    preview_candidates = fitting[:2]
    result = {
        "schema": "interior.camera-candidate-set.v1",
        "methodVersion": METHOD_VERSION,
        "coordinateSystem": "interior-world-y-up.v1",
        "algorithmProfile": str(PROFILE_PATH),
        "composition": args.composition,
        "candidatePolicy": {
            "selectionMethod": "deterministic-first-fitting-with-one-bounded-fallback",
            "primaryNativePreviewCount": 1,
            "maximumFallbackPreviewCount": 1,
            "maximumNativePreviewCount": 2,
            "targetOccupancies": list(occupancies),
            "focalChainMm": list(focals),
            "actualProjectionCheckRequired": True,
            "nativeBackendScreenshotRequired": True,
            "sixteenMillimeterAutomatic": False,
        },
        "candidates": candidates,
        "fittingCandidateIds": [candidate["candidateId"] for candidate in fitting],
        "nativePreviewCandidateIds": [candidate["candidateId"] for candidate in preview_candidates],
        "deterministicPrimaryCandidateId": preview_candidates[0]["candidateId"] if preview_candidates else None,
        "decision": (
            "Render the deterministic primary once; render the sole fallback only when native projection rejects the primary."
            if fitting
            else "No candidate fits the measured retreat depth; stop and disclose the source-space constraint."
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if fitting else 1


if __name__ == "__main__":
    raise SystemExit(main())
