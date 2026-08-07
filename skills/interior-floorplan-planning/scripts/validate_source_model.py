#!/usr/bin/env python3
"""Validate one floorplan model against its frozen source evidence and visual review."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops

from render_floorplan_quadrants import render_source_evidence_overlay
from topology_compiler import (
    ALL_CONNECTION_KINDS,
    DIVIDER_TRAVERSAL_TYPES,
    ENCLOSED_ACCESS_KINDS,
    TRAVERSABLE_CONNECTION_KINDS,
    compile_space_topology,
    divider_endpoints_match_anchors,
    divider_labels_are_opposite,
    valid_segment,
)

SOURCE_NORMALIZATION_METHOD = "grayscale-local-contrast-union-v1"
SOURCE_EVIDENCE_SCHEMA = "interior.floorplan-source-evidence.v4"
LAYOUT_AUTHORITY_SCHEMA = "interior.floorplan-layout-authority.v1"
OPENING_SYMBOL_REQUIREMENTS = {
    "door": ("single-leaf-swing", {"wall-gap", "swing-arc"}),
    "sliding-door": ("sliding-panel", {"wall-gap", "parallel-tracks"}),
    "open-passage": ("open-gap", {"wall-gap", "no-swing-or-track"}),
    "glazing": ("fixed-glazing", {"host-wall", "glass-panels"}),
    "window": ("window-frame", {"host-wall", "parallel-frame-lines"}),
    "not-opening": ("non-opening-line", set()),
}
LAYERED_OVERLAYS = {
    "wallsOpenings": ("walls-openings-overlay.png", {"walls", "openings"}, False),
    "wallsOpeningsReview": (
        "walls-openings-overlay-review.png",
        {"walls", "openings"},
        True,
    ),
    "roomLabelsDividers": (
        "room-labels-dividers-overlay.png",
        {"labels", "dividers"},
        False,
    ),
    "roomLabelsDividersReview": (
        "room-labels-dividers-overlay-review.png",
        {"labels", "dividers"},
        True,
    ),
    "objects": ("objects-overlay.png", {"objects"}, False),
    "objectsReview": ("objects-overlay-review.png", {"objects"}, True),
}

AGGREGATE_FUNCTIONAL_CLASSES = {
    "dining-set",
    "bedroom-set",
    "living-room-set",
    "furniture-group",
    "cabinet-group",
    "fixture-group",
}
FUNCTIONAL_CLASS_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_relative_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def transform_point(matrix: np.ndarray, point: list[float]) -> np.ndarray:
    homogeneous = matrix @ np.asarray([point[0], point[1], 1.0], dtype=float)
    if abs(float(homogeneous[2])) < 1e-9:
        raise ValueError("coordinate transform produced a point at infinity")
    return homogeneous[:2] / homogeneous[2]


def line_values(
    distance: np.ndarray,
    points: list[list[float]],
    occlusion_mask: np.ndarray | None = None,
) -> np.ndarray:
    mask = np.zeros(distance.shape, dtype=np.uint8)
    pts = np.rint(np.asarray(points, dtype=float)).astype(np.int32)
    for start, end in zip(pts, pts[1:]):
        cv2.line(mask, tuple(start), tuple(end), 255, 1)
    if occlusion_mask is not None:
        mask[occlusion_mask > 0] = 0
    return distance[mask > 0]


def polygon_mask(shape: tuple[int, int], points: list[list[float]]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    pts = np.rint(np.asarray(points, dtype=float)).astype(np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def expected_polygon(candidate: dict) -> list[list[float]]:
    face_a = candidate["faceA"]
    face_b = candidate["faceB"]
    if len(face_a) != 2 or len(face_b) != 2:
        raise ValueError(f"{candidate['id']}: only straight paired faces are supported")
    return [face_a[0], face_a[1], face_b[1], face_b[0]]


def build_normalized_ink_mask(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert any readable source color/contrast into one deterministic ink mask.

    The mask is validation evidence for authored output, not an input-admission gate.
    Geometry remains in the original image coordinate frame.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, otsu = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        7,
    )
    channels = image.astype(np.int16)
    chroma = channels.max(axis=2) - channels.min(axis=2)
    colored = ((chroma >= 16) & (gray <= 250)).astype(np.uint8)
    ink = (
        (otsu > 0)
        | ((adaptive > 0) & (gray < 250))
        | (colored > 0)
    ).astype(np.uint8)
    return gray, ink, colored


def validate(
    source_path: Path,
    native_layout_path: Path | None,
    evidence_path: Path,
    decisions_path: Path,
    geometry_path: Path,
    visual_path: Path,
    trace_spec_path: Path | None,
    trace_components_path: Path | None,
) -> dict:
    evidence = load(evidence_path)
    decisions = load(decisions_path)
    geometry = load(geometry_path)
    visual = load(visual_path)
    errors: list[str] = []

    if evidence.get("schema") != SOURCE_EVIDENCE_SCHEMA:
        errors.append("invalid source evidence schema")
    if decisions.get("schema") != "interior.floorplan-semantic-decisions.v1":
        errors.append("invalid semantic decisions schema")
    if geometry.get("schema") != "interior.floorplan-wall-geometry.v1":
        errors.append("invalid wall geometry schema")
    if visual.get("schema") != "interior.floorplan-agent-visual-review.v2":
        errors.append("invalid visual review schema")

    source_sha = digest(source_path)
    evidence_sha = digest(evidence_path)
    decisions_sha = digest(decisions_path)
    if evidence.get("sourceSha256") != source_sha:
        errors.append("source evidence is not bound to the current source image")
    if decisions.get("evidenceSha256") != evidence_sha:
        errors.append("semantic decisions are not bound to the evidence ledger")
    if geometry.get("decisionsSha256") != decisions_sha:
        errors.append("wall geometry is not bound to semantic decisions")
    if visual.get("geometrySha256") != digest(geometry_path):
        errors.append("visual review is not bound to the current wall geometry")

    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot read source image: {source_path}")
    layout_authority = evidence.get("layoutAuthority")
    if not isinstance(layout_authority, dict):
        errors.append("source evidence requires layoutAuthority")
        layout_authority = {}
    layout_mode = layout_authority.get("mode")
    if layout_authority.get("schema") != LAYOUT_AUTHORITY_SCHEMA:
        errors.append(f"layoutAuthority must use {LAYOUT_AUTHORITY_SCHEMA}")
    if layout_mode not in {"source-furnished", "native-layout-furnished"}:
        errors.append("layoutAuthority.mode must identify the furnishing fact source")
        layout_mode = "source-furnished"
    if layout_authority.get("structureAuthority") != "source-floorplan":
        errors.append("walls, openings and room boundaries must remain source-floorplan facts")
    expected_furnishing_authority = (
        "native-layout" if layout_mode == "native-layout-furnished" else "source-floorplan"
    )
    if layout_authority.get("furnishingAuthority") != expected_furnishing_authority:
        errors.append("layoutAuthority furnishingAuthority differs from its mode")
    if layout_authority.get("coordinateBinding") != "same-canvas-identity":
        errors.append("native layout must preserve the source canvas without a second transform")
    if layout_authority.get("structureLock") != {
        "walls": True,
        "openings": True,
        "spaceBoundaries": True,
    }:
        errors.append("layoutAuthority must lock walls, openings and space boundaries")
    native_generation = layout_authority.get("nativeGeneration")
    if layout_mode == "native-layout-furnished":
        if native_layout_path is None:
            raise ValueError(
                "native-layout-furnished mode requires --native-layout"
            )
        native_layout = cv2.imread(str(native_layout_path), cv2.IMREAD_COLOR)
        if native_layout is None:
            raise ValueError(f"cannot read native layout image: {native_layout_path}")
        if native_layout.shape[:2] != image.shape[:2]:
            errors.append(
                "native layout must use the exact source-image canvas and coordinate frame"
            )
        if layout_authority.get("nativeLayoutSha256") != digest(native_layout_path):
            errors.append("layoutAuthority is not bound to the supplied native layout")
        if (
            not isinstance(native_generation, dict)
            or native_generation.get("method") != "native-image-generation"
            or native_generation.get("accepted") is not True
            or not re.fullmatch(r"[0-9a-f]{64}", native_generation.get("promptDigestSha256", ""))
        ):
            errors.append(
                "an empty source plan requires one accepted, hash-bound native layout generation"
            )
    else:
        native_layout = image
        if layout_authority.get("nativeLayoutSha256") is not None:
            errors.append("source-furnished mode must not bind a redundant native layout")
        if native_generation is not None:
            errors.append("source-furnished mode must not claim a generated furnishing authority")
    normalization = evidence.get("sourceNormalization")
    if not isinstance(normalization, dict):
        errors.append("source evidence needs deterministic sourceNormalization")
        normalization = {}
    if normalization.get("method") != SOURCE_NORMALIZATION_METHOD:
        errors.append(
            "sourceNormalization.method must use the current deterministic "
            f"method: {SOURCE_NORMALIZATION_METHOD}"
        )
    if normalization.get("coordinateBinding") != "original-source-image-pixels":
        errors.append(
            "sourceNormalization must keep all authored candidates in original source pixels"
        )
    gray, ink, colored = build_normalized_ink_mask(image)
    _, native_ink, _ = build_normalized_ink_mask(native_layout)
    distance = cv2.distanceTransform(1 - ink, cv2.DIST_L2, 5)
    native_distance = cv2.distanceTransform(1 - native_ink, cv2.DIST_L2, 5)
    furnishing_image = (
        native_layout if layout_mode == "native-layout-furnished" else image
    )
    _, furnishing_ink, _ = build_normalized_ink_mask(furnishing_image)
    object_distance = cv2.distanceTransform(1 - furnishing_ink, cv2.DIST_L2, 5)

    frame = evidence.get("sourceCoordinateFrame")
    if (
        not isinstance(frame, dict)
        or frame.get("origin") != "top-left"
        or frame.get("xAxis") != "right"
        or frame.get("yAxis") != "down"
        or frame.get("width") != image.shape[1]
        or frame.get("height") != image.shape[0]
    ):
        errors.append(
            "sourceCoordinateFrame must describe the current source image in "
            "top-left, x-right, y-down pixels"
        )

    inspection_views = evidence.get("inspectionViews")
    if not isinstance(inspection_views, list):
        errors.append("inspectionViews must be an array")
        inspection_views = []
    inspection_ids: set[str] = set()
    for view in inspection_views:
        if not isinstance(view, dict) or not view.get("id"):
            errors.append("each inspection view needs a unique non-empty ID")
            continue
        if view["id"] in inspection_ids:
            errors.append(f"{view['id']}: duplicate inspection-view ID")
        inspection_ids.add(view["id"])
        if not safe_relative_path(view.get("path")):
            errors.append(f"{view['id']}: inspection view needs a safe relative path")
            continue
        view_path = (evidence_path.parent / view["path"]).resolve()
        if not view_path.is_file():
            errors.append(f"{view['id']}: inspection view image is missing")
            continue
        view_image = cv2.imread(str(view_path), cv2.IMREAD_COLOR)
        if view_image is None:
            errors.append(f"{view['id']}: inspection view image cannot be read")
            continue
        expected_size = view.get("size")
        if expected_size != [view_image.shape[1], view_image.shape[0]]:
            errors.append(f"{view['id']}: inspection view size does not match its image")
        try:
            source_to_view = np.asarray(view.get("sourceToView"), dtype=float)
            view_to_source = np.asarray(view.get("viewToSource"), dtype=float)
            if source_to_view.shape != (3, 3) or view_to_source.shape != (3, 3):
                raise ValueError("transforms must be 3x3 matrices")
            if not np.allclose(
                source_to_view @ view_to_source,
                np.eye(3),
                atol=1e-6,
            ):
                raise ValueError("sourceToView and viewToSource are not inverses")
            controls = view.get("roundTripControlPoints")
            if not isinstance(controls, list) or len(controls) < 5:
                raise ValueError("at least five round-trip control points are required")
            for control in controls:
                source_point = control.get("source")
                view_point = control.get("view")
                if (
                    not isinstance(source_point, list)
                    or len(source_point) != 2
                    or not isinstance(view_point, list)
                    or len(view_point) != 2
                ):
                    raise ValueError("round-trip control points need source and view pairs")
                projected = transform_point(source_to_view, source_point)
                restored = transform_point(view_to_source, view_point)
                if not np.allclose(projected, view_point, atol=0.01):
                    raise ValueError("source-to-view control point mismatch")
                if not np.allclose(restored, source_point, atol=0.01):
                    raise ValueError("view-to-source control point mismatch")
        except (TypeError, ValueError, np.linalg.LinAlgError) as error:
            errors.append(f"{view['id']}: invalid reversible coordinate transform: {error}")

    overlay_relative = evidence.get("candidateOverlayPath")
    if not safe_relative_path(overlay_relative):
        errors.append("source evidence needs a safe candidateOverlayPath")
    else:
        overlay_path = (evidence_path.parent / overlay_relative).resolve()
        if not overlay_path.is_file():
            errors.append("source evidence overlay is missing")
        else:
            expected_overlay = render_source_evidence_overlay(
                evidence,
                Image.open(
                    native_layout_path
                    if layout_mode == "native-layout-furnished"
                    else source_path
                ).convert("RGBA"),
            ).convert("RGB")
            actual_overlay = Image.open(overlay_path).convert("RGB")
            if (
                expected_overlay.size != actual_overlay.size
                or ImageChops.difference(expected_overlay, actual_overlay).getbbox() is not None
            ):
                errors.append("source evidence overlay is not generated from current source vectors")

    layered_paths = evidence.get("candidateOverlayPaths")
    if not isinstance(layered_paths, dict) or set(layered_paths) != set(LAYERED_OVERLAYS):
        errors.append(
            "candidateOverlayPaths must contain the six formal evidence-review layers"
        )
        layered_paths = {}
    for key, (expected_name, groups, show_ids) in LAYERED_OVERLAYS.items():
        relative = layered_paths.get(key)
        if relative != expected_name or not safe_relative_path(relative):
            errors.append(f"{key}: invalid formal evidence-overlay path")
            continue
        layered_path = (evidence_path.parent / relative).resolve()
        if not layered_path.is_file():
            errors.append(f"{key}: formal evidence overlay is missing")
            continue
        layer_base = (
            native_layout_path
            if groups == {"objects"} and layout_mode == "native-layout-furnished"
            else source_path
        )
        expected_layer = render_source_evidence_overlay(
            evidence,
            Image.open(layer_base).convert("RGBA"),
            groups=groups,
            show_ids=show_ids,
        ).convert("RGB")
        actual_layer = Image.open(layered_path).convert("RGB")
        if (
            expected_layer.size != actual_layer.size
            or ImageChops.difference(expected_layer, actual_layer).getbbox() is not None
        ):
            errors.append(f"{key}: evidence overlay is not generated from current vectors")

    candidates = evidence.get("wallCandidates", [])
    candidate_by_id = {item.get("id"): item for item in candidates}
    if len(candidate_by_id) != len(candidates) or None in candidate_by_id:
        errors.append("source evidence contains missing or duplicate candidate IDs")

    decision_rows = decisions.get("candidates", [])
    decision_by_id = {item.get("candidateId"): item for item in decision_rows}
    if len(decision_by_id) != len(decision_rows) or None in decision_by_id:
        errors.append("semantic wall decisions contain missing or duplicate candidate IDs")
    if set(decision_by_id) != set(candidate_by_id):
        errors.append("every source candidate must have exactly one semantic decision")
    allowed_wall_classifications = {
        "wall",
        "occluded-wall",
        "not-wall",
        "unresolved",
    }
    for candidate_id, decision in decision_by_id.items():
        if decision.get("classification") not in allowed_wall_classifications:
            errors.append(f"{candidate_id}: unsupported wall classification")
        if not decision.get("reason") or not decision.get("evidenceTypes"):
            errors.append(
                f"{candidate_id}: wall decision needs a reason and evidence types"
            )
        candidate = candidate_by_id.get(candidate_id, {})
        occlusion_evidence = candidate.get("occlusionEvidence", [])
        if decision.get("classification") == "occluded-wall":
            evidence_types = {
                item.get("type")
                for item in occlusion_evidence
                if isinstance(item, dict) and item.get("type")
            } if isinstance(occlusion_evidence, list) else set()
            if len(evidence_types) < 2:
                errors.append(
                    f"{candidate_id}: occluded wall needs two structured source "
                    "occlusion evidence types"
                )
            if not evidence_types.issubset(set(decision.get("evidenceTypes", []))):
                errors.append(
                    f"{candidate_id}: occlusion evidence types must be referenced "
                    "by the semantic decision"
                )
            for evidence_index, item in enumerate(
                occlusion_evidence if isinstance(occlusion_evidence, list) else []
            ):
                if not isinstance(item, dict) or not item.get("finding"):
                    errors.append(
                        f"{candidate_id}/occlusion-evidence-{evidence_index}: "
                        "structured evidence needs a finding"
                    )
                    continue
                unknown_references = sorted(
                    set(item.get("referenceCandidateIds", [])) - set(candidate_by_id)
                )
                if unknown_references:
                    errors.append(
                        f"{candidate_id}/occlusion-evidence-{evidence_index}: "
                        f"unknown wall candidate references: {unknown_references}"
                    )
        elif occlusion_evidence:
            errors.append(
                f"{candidate_id}: structured occlusion evidence requires "
                "occluded-wall classification"
            )

    opening_candidates = evidence.get("openingCandidates", [])
    opening_candidate_by_id = {item.get("id"): item for item in opening_candidates}
    opening_decisions = decisions.get("openings", [])
    opening_decision_by_id = {
        item.get("candidateId"): item for item in opening_decisions
    }
    if (
        len(opening_candidate_by_id) != len(opening_candidates)
        or None in opening_candidate_by_id
        or len(opening_decision_by_id) != len(opening_decisions)
        or None in opening_decision_by_id
    ):
        errors.append("source openings contain missing or duplicate candidate IDs")
    if set(opening_decision_by_id) != set(opening_candidate_by_id):
        errors.append(
            "every source opening candidate must have exactly one semantic decision"
        )
    allowed_opening_classifications = ALL_CONNECTION_KINDS | {
        "not-opening",
        "unresolved",
    }
    for candidate_id, candidate in opening_candidate_by_id.items():
        if candidate.get("discovery") != "deterministic-source-pixel-trace":
            errors.append(
                f"{candidate_id}: opening coordinates must come from deterministic "
                "source-pixel tracing"
            )
        if not valid_segment(candidate.get("segment")):
            errors.append(f"{candidate_id}: opening candidate needs one non-zero segment")
        decision = opening_decision_by_id.get(candidate_id, {})
        classification = decision.get("classification")
        if classification not in allowed_opening_classifications:
            errors.append(f"{candidate_id}: unsupported opening classification")
        if not decision.get("reason") or not decision.get("evidenceTypes"):
            errors.append(
                f"{candidate_id}: opening decision needs a reason and evidence types"
            )
        if classification == "unresolved":
            errors.append(f"{candidate_id}: unresolved opening classification")
        symbol_evidence = candidate.get("symbolEvidence")
        if classification in OPENING_SYMBOL_REQUIREMENTS:
            required_signature, required_primitives = OPENING_SYMBOL_REQUIREMENTS[
                classification
            ]
            if not isinstance(symbol_evidence, dict):
                errors.append(
                    f"{candidate_id}: {classification} requires structured symbolEvidence"
                )
            else:
                primitives = symbol_evidence.get("primitiveTypes")
                primitive_set = set(primitives) if isinstance(primitives, list) else set()
                if symbol_evidence.get("signature") != required_signature:
                    errors.append(
                        f"{candidate_id}: {classification} requires signature "
                        f"{required_signature}"
                    )
                if not required_primitives.issubset(primitive_set):
                    errors.append(
                        f"{candidate_id}: {classification} lacks symbol primitives "
                        f"{sorted(required_primitives - primitive_set)}"
                    )
                panel_material = symbol_evidence.get("panelMaterial")
                if classification in {"sliding-door", "glazing", "window"}:
                    if panel_material not in {"glass", "opaque", "mixed", "unknown"}:
                        errors.append(
                            f"{candidate_id}: {classification} requires an explicit "
                            "panelMaterial"
                        )
                    if classification in {"glazing", "window"} and panel_material != "glass":
                        errors.append(
                            f"{candidate_id}: {classification} must preserve glass material evidence"
                        )

    label_candidates = evidence.get("spaceLabelCandidates", [])
    label_candidate_by_id = {item.get("id"): item for item in label_candidates}
    if (
        len(label_candidate_by_id) != len(label_candidates)
        or None in label_candidate_by_id
    ):
        errors.append("space label evidence contains missing or duplicate IDs")
    for label_id, label in label_candidate_by_id.items():
        if label.get("discovery") != "source-plan-text-position-agent-confirmed":
            errors.append(
                f"{label_id}: space label must be bound to source text and Agent confirmation"
            )
        point = label.get("point")
        if (
            not isinstance(label.get("text"), str)
            or not label["text"].strip()
            or not isinstance(point, list)
            or len(point) != 2
            or not all(isinstance(axis, (int, float)) for axis in point)
        ):
            errors.append(f"{label_id}: space label needs text and one source-pixel point")
        elif not (0 <= point[0] < image.shape[1] and 0 <= point[1] < image.shape[0]):
            errors.append(f"{label_id}: space label point lies outside the source image")

    divider_candidates = evidence.get("semanticDividerCandidates", [])
    divider_candidate_by_id = {
        item.get("id"): item for item in divider_candidates
    }
    divider_decisions = decisions.get("dividers", [])
    divider_decision_by_id = {
        item.get("candidateId"): item for item in divider_decisions
    }
    if (
        len(divider_candidate_by_id) != len(divider_candidates)
        or None in divider_candidate_by_id
        or len(divider_decision_by_id) != len(divider_decisions)
        or None in divider_decision_by_id
    ):
        errors.append("semantic divider evidence contains missing or duplicate IDs")
    if set(divider_decision_by_id) != set(divider_candidate_by_id):
        errors.append(
            "every semantic divider candidate must have exactly one decision"
        )
    all_evidence_ids = [
        *candidate_by_id,
        *opening_candidate_by_id,
        *label_candidate_by_id,
        *divider_candidate_by_id,
    ]
    if len(all_evidence_ids) != len(set(all_evidence_ids)):
        errors.append("all source evidence IDs must be globally unique")
    allowed_divider_classifications = {
        "semantic-divider",
        "not-divider",
        "unresolved",
    }
    for candidate_id, candidate in divider_candidate_by_id.items():
        if candidate.get("discovery") != "deterministic-space-label-partition":
            errors.append(
                f"{candidate_id}: semantic divider must be derived from room labels "
                "and open-zone geometry, not source-pixel opening tracing"
            )
        if not valid_segment(candidate.get("segment")):
            errors.append(f"{candidate_id}: semantic divider needs one non-zero segment")
        source_label_ids = set(candidate.get("sourceLabelIds", []))
        if len(source_label_ids) != 2:
            errors.append(
                f"{candidate_id}: semantic divider needs exactly two source room labels"
            )
        unknown_labels = sorted(source_label_ids - set(label_candidate_by_id))
        if unknown_labels:
            errors.append(
                f"{candidate_id}: unknown source room labels: {unknown_labels}"
            )
        anchor_ids = set(candidate.get("anchorWallCandidateIds", []))
        if len(anchor_ids) != 2:
            errors.append(
                f"{candidate_id}: semantic divider needs exactly two structural endpoint anchors"
            )
        unknown_anchors = sorted(
            anchor_ids - set(candidate_by_id)
        )
        if unknown_anchors:
            errors.append(
                f"{candidate_id}: unknown divider wall anchors: {unknown_anchors}"
            )
        if not unknown_labels and not divider_labels_are_opposite(
            candidate,
            label_candidate_by_id,
        ):
            errors.append(
                f"{candidate_id}: source room labels must lie on opposite "
                "sides of the semantic divider"
            )
        if not unknown_anchors and not divider_endpoints_match_anchors(
            candidate,
            candidate_by_id,
        ):
            errors.append(
                f"{candidate_id}: divider endpoints must terminate on the "
                "two declared wall anchors within 3px"
            )
        decision = divider_decision_by_id.get(candidate_id, {})
        if decision.get("classification") not in allowed_divider_classifications:
            errors.append(f"{candidate_id}: unsupported divider classification")
        if not decision.get("reason") or len(set(decision.get("evidenceTypes", []))) < 2:
            errors.append(
                f"{candidate_id}: divider decision needs a reason and two evidence types"
            )
        if decision.get("classification") == "unresolved":
            errors.append(f"{candidate_id}: unresolved divider classification")
        traversal = decision.get("traversal")
        if (
            decision.get("classification") == "semantic-divider"
            and traversal not in DIVIDER_TRAVERSAL_TYPES
        ):
            errors.append(
                f"{candidate_id}: accepted divider needs traversal "
                "open-passage or boundary-only"
            )
        if (
            decision.get("classification") != "semantic-divider"
            and traversal is not None
        ):
            errors.append(
                f"{candidate_id}: rejected divider must not declare traversal"
            )

    evidence_metrics = []
    for candidate in candidates:
        candidate_id = candidate["id"]
        if candidate.get("discovery") != "deterministic-source-pixel-trace":
            errors.append(
                f"{candidate_id}: candidate coordinates must come from deterministic source-pixel tracing"
            )
        candidate_occlusion = np.zeros(gray.shape, dtype=np.uint8)
        for mask_index, rect in enumerate(candidate.get("occlusionMasks", [])):
            if len(rect) != 4:
                errors.append(f"{candidate_id}/occlusion-{mask_index}: mask must contain four coordinates")
                continue
            x0, y0, x1, y1 = map(int, rect)
            region = colored[y0 : y1 + 1, x0 : x1 + 1]
            decision = decision_by_id.get(candidate_id, {})
            semantic_occlusion = (
                decision.get("classification") == "occluded-wall"
                and len(decision.get("evidenceTypes", [])) >= 2
                and bool(candidate.get("occlusionEvidence"))
            )
            if region.size == 0 or (float(region.mean()) < 0.20 and not semantic_occlusion):
                errors.append(
                    f"{candidate_id}/occlusion-{mask_index}: mask lacks colored obstruction "
                    "or independently documented semantic occlusion"
                )
            candidate_occlusion[y0 : y1 + 1, x0 : x1 + 1] = 255
        for face_name in ("faceA", "faceB"):
            raw_values = line_values(distance, candidate.get(face_name, []))
            values = line_values(distance, candidate.get(face_name, []), candidate_occlusion)
            if values.size == 0:
                errors.append(f"{candidate_id}/{face_name}: no measurable pixels")
                continue
            if values.size < max(2, raw_values.size * 0.40):
                errors.append(f"{candidate_id}/{face_name}: too much evidence was hidden by occlusion masks")
            p95 = float(np.percentile(values, 95))
            within2 = float((values <= 2).mean())
            evidence_metrics.append(
                {
                    "candidateId": candidate_id,
                    "face": face_name,
                    "p95DistancePx": round(p95, 3),
                    "within2PxRatio": round(within2, 4),
                }
            )
            if p95 > 2 or within2 < 0.95:
                errors.append(
                    f"{candidate_id}/{face_name}: source support failed "
                    f"(p95={p95:.2f}, within2={within2:.4f})"
                )
            if layout_mode == "native-layout-furnished":
                native_values = line_values(
                    native_distance,
                    candidate.get(face_name, []),
                    candidate_occlusion,
                )
                native_p95 = (
                    float(np.percentile(native_values, 95))
                    if native_values.size
                    else float("inf")
                )
                evidence_metrics.append({
                    "candidateId": candidate_id,
                    "face": face_name,
                    "authority": "native-layout-structure-lock",
                    "p95DistancePx": round(native_p95, 3),
                })
                if native_p95 > 4:
                    errors.append(
                        f"{candidate_id}/{face_name}: generated native layout changed "
                        f"the source wall geometry (p95={native_p95:.2f})"
                    )

    allowed_wall_ids = {
        candidate_id
        for candidate_id, row in decision_by_id.items()
        if row.get("classification") in {"wall", "occluded-wall"}
    }
    unresolved = [
        candidate_id
        for candidate_id, row in decision_by_id.items()
        if row.get("classification") == "unresolved"
    ]
    if unresolved:
        errors.append(f"unresolved source candidates: {sorted(unresolved)}")

    geometry_rows = geometry.get("walls", [])
    geometry_candidate_ids = [row.get("candidateId") for row in geometry_rows]
    if len(set(geometry_candidate_ids)) != len(geometry_candidate_ids):
        errors.append("a source candidate may generate only one wall band")
    if set(geometry_candidate_ids) != allowed_wall_ids:
        errors.append("wall geometry must represent every and only wall-classified candidate")

    geometry_metrics = []
    for row in geometry_rows:
        candidate_id = row.get("candidateId")
        candidate = candidate_by_id.get(candidate_id)
        if not candidate:
            continue
        expected = expected_polygon(candidate)
        if row.get("points") != expected:
            errors.append(f"{row.get('id')}: wall polygon was not derived from paired source faces")
        wall_mask = polygon_mask(gray.shape, row.get("points", []))
        boundary_mask = cv2.morphologyEx(wall_mask, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        for rect in candidate.get("occlusionMasks", []):
            x0, y0, x1, y1 = map(int, rect)
            boundary_mask[y0 : y1 + 1, x0 : x1 + 1] = 0
        values = distance[boundary_mask > 0]
        if values.size:
            p95 = float(np.percentile(values, 95))
            geometry_metrics.append({"wallId": row.get("id"), "p95BoundaryDistancePx": round(p95, 3)})
            if p95 > 3:
                errors.append(f"{row.get('id')}: wall boundary departs from source ink (p95={p95:.2f})")

    floor_metrics = None
    connection_metrics = None
    topology_metrics = None
    opening_object_intersections: list[dict] = []
    extra_access_rooms: dict[str, set[str]] = {}
    room_ids_for_review: set[str] = set()
    connection_ids_for_review: set[str] = set()
    opening_ids_for_review = {
        candidate_id
        for candidate_id, decision in opening_decision_by_id.items()
        if decision.get("classification") not in {"not-opening", "unresolved"}
    }
    divider_ids_for_review = {
        candidate_id
        for candidate_id, decision in divider_decision_by_id.items()
        if decision.get("classification") == "semantic-divider"
    }
    object_candidates = evidence.get("objectCandidates", [])
    object_candidate_by_id = {
        item.get("id"): item for item in object_candidates
    }
    object_decisions = decisions.get("objects", [])
    object_decision_by_id = {
        item.get("candidateId"): item for item in object_decisions
    }
    if (
        len(object_candidate_by_id) != len(object_candidates)
        or None in object_candidate_by_id
        or len(object_decision_by_id) != len(object_decisions)
        or None in object_decision_by_id
    ):
        errors.append("source objects contain missing or duplicate candidate IDs")
    if set(object_decision_by_id) != set(object_candidate_by_id):
        errors.append(
            "every source object candidate must have exactly one semantic decision"
        )
    allowed_object_classifications = {
        "movable-furniture",
        "fixed-cabinet-equipment",
        "not-object",
        "unresolved",
    }
    accepted_object_ids: set[str] = set()
    functional_class_by_object: dict[str, str] = {}
    functional_counts_by_label: dict[str, Counter] = {}
    object_evidence_metrics: list[dict] = []
    expected_object_discovery = (
        "deterministic-native-layout-object-contour"
        if layout_mode == "native-layout-furnished"
        else "deterministic-source-object-contour"
    )
    for candidate_id, candidate in object_candidate_by_id.items():
        if candidate.get("discovery") != expected_object_discovery:
            errors.append(
                f"{candidate_id}: object contour must come from the declared "
                "furnishing authority"
            )
        outline = candidate.get("outline")
        if (
            not isinstance(outline, list)
            or len(outline) < 3
            or any(
                not isinstance(point, list)
                or len(point) != 2
                or not all(isinstance(axis, (int, float)) for axis in point)
                for point in outline
            )
        ):
            errors.append(f"{candidate_id}: object candidate needs a polygon outline")
        else:
            for point in outline:
                if not (
                    0 <= float(point[0]) < image.shape[1]
                    and 0 <= float(point[1]) < image.shape[0]
                ):
                    errors.append(
                        f"{candidate_id}: object outline lies outside the source image"
                    )
                    break
            closed_outline = [*outline, outline[0]]
            values = line_values(object_distance, closed_outline)
            if values.size:
                p95 = float(np.percentile(values, 95))
                within4 = float((values <= 4).mean())
                object_evidence_metrics.append({
                    "candidateId": candidate_id,
                    "p95DistancePx": round(p95, 3),
                    "within4PxRatio": round(within4, 4),
                })
                if p95 > 4 or within4 < 0.85:
                    errors.append(
                        f"{candidate_id}: object outline lacks source-pixel support "
                        f"(p95={p95:.2f}, within4={within4:.4f})"
                    )
        details = candidate.get("details")
        if not isinstance(details, list):
            errors.append(f"{candidate_id}: object details must be an explicit list")
            details = []
        for detail_index, detail in enumerate(details):
            detail_id = f"{candidate_id}:detail-{detail_index + 1:03d}"
            if (
                not isinstance(detail, list)
                or len(detail) < 2
                or any(
                    not isinstance(point, list)
                    or len(point) != 2
                    or not all(isinstance(axis, (int, float)) for axis in point)
                    for point in detail
                )
            ):
                errors.append(
                    f"{detail_id}: object detail needs a source-coordinate polyline"
                )
                continue
            if any(
                not (
                    0 <= float(point[0]) < image.shape[1]
                    and 0 <= float(point[1]) < image.shape[0]
                )
                for point in detail
            ):
                errors.append(f"{detail_id}: object detail lies outside the source image")
                continue
            values = line_values(object_distance, detail)
            if not values.size:
                errors.append(f"{detail_id}: object detail has no measurable pixels")
                continue
            p95 = float(np.percentile(values, 95))
            within4 = float((values <= 4).mean())
            object_evidence_metrics.append({
                "candidateId": candidate_id,
                "detailIndex": detail_index,
                "p95DistancePx": round(p95, 3),
                "within4PxRatio": round(within4, 4),
            })
            if p95 > 4 or within4 < 0.85:
                errors.append(
                    f"{detail_id}: object detail lacks source-pixel support "
                    f"(p95={p95:.2f}, within4={within4:.4f})"
                )
        decision = object_decision_by_id.get(candidate_id, {})
        classification = decision.get("classification")
        if classification not in allowed_object_classifications:
            errors.append(f"{candidate_id}: unsupported object classification")
        if not decision.get("reason") or not decision.get("evidenceTypes"):
            errors.append(
                f"{candidate_id}: object decision needs a reason and evidence types"
            )
        if classification == "unresolved":
            errors.append(f"{candidate_id}: unresolved object classification")
        if classification in {
            "movable-furniture",
            "fixed-cabinet-equipment",
        }:
            accepted_object_ids.add(candidate_id)
            if not isinstance(decision.get("name"), str) or not decision["name"].strip():
                errors.append(f"{candidate_id}: accepted object needs a name")
            if decision.get("sourceLabelId") not in label_candidate_by_id:
                errors.append(
                    f"{candidate_id}: accepted object needs one known sourceLabelId"
                )
            functional_class = decision.get("functionalClass")
            if (
                not isinstance(functional_class, str)
                or not FUNCTIONAL_CLASS_PATTERN.fullmatch(functional_class)
                or functional_class in AGGREGATE_FUNCTIONAL_CLASSES
            ):
                errors.append(
                    f"{candidate_id}: accepted object needs one atomic functionalClass; "
                    "room sets and furniture groups are forbidden"
                )
            if decision.get("quantity") != 1 or decision.get("atomicObject") is not True:
                errors.append(
                    f"{candidate_id}: every accepted contour must represent exactly one "
                    "atomic object with quantity=1"
                )
            if isinstance(functional_class, str):
                functional_class_by_object[candidate_id] = functional_class
                label_id = decision.get("sourceLabelId")
                functional_counts_by_label.setdefault(label_id, Counter())[functional_class] += 1
    all_evidence_ids.extend(object_candidate_by_id)
    if len(all_evidence_ids) != len(set(all_evidence_ids)):
        errors.append("all source evidence IDs must be globally unique")

    trace_components = None
    if trace_components_path is not None:
        trace_components = load(trace_components_path)
        if trace_components.get("schema") != "interior.trace-components.v2":
            errors.append("invalid trace-components schema")
    elif trace_spec_path is not None:
        errors.append(
            "trace-components are required when validating a compiled trace-spec"
        )
    object_room_metrics: list[dict] = []
    if trace_spec_path is not None:
        trace_spec = load(trace_spec_path)
        if trace_spec.get("cleanStructure", {}).get("walls") != geometry_rows:
            errors.append(
                "trace-spec cleanStructure.walls differs from the frozen wall geometry"
            )
        if trace_spec.get("layers", {}).get("walls") != geometry_rows:
            errors.append(
                "trace-spec layers.walls differs from the frozen wall geometry"
            )
        try:
            topology = compile_space_topology(
                trace_spec,
                gray.shape,
                geometry,
                evidence,
                decisions,
            )
        except ValueError as error:
            errors.append(str(error))
            topology = {
                "errors": [],
                "traceSpec": trace_spec,
                "interior": np.zeros(gray.shape, dtype=np.uint8),
                "assignment": np.zeros(gray.shape, dtype=np.int32),
                "metrics": {},
            }
        errors.extend(topology["errors"])
        compiled_spec = topology["traceSpec"]
        for field in ("floorBoundary", "spaces", "compiledTopology"):
            if trace_spec.get(field) != compiled_spec.get(field):
                errors.append(
                    f"trace-spec {field} must be generated by the deterministic topology compiler"
                )
        spaces = compiled_spec.get("spaces", [])
        room_ids = [item.get("id") for item in spaces]
        if None in room_ids or len(room_ids) != len(set(room_ids)):
            errors.append("trace-spec spaces need unique non-empty IDs")
        room_id_set = set(room_ids)
        room_ids_for_review = room_id_set
        source_label_to_room = {
            item.get("sourceLabelId"): item.get("id")
            for item in trace_spec.get("spaceSeeds", [])
        }
        room_to_ordinal = {
            item.get("id"): index + 1
            for index, item in enumerate(trace_spec.get("spaceSeeds", []))
            if item.get("id")
        }
        ordinal_to_room = {
            ordinal: room_id for room_id, ordinal in room_to_ordinal.items()
        }
        for candidate_id in sorted(accepted_object_ids):
            candidate = object_candidate_by_id.get(candidate_id, {})
            decision = object_decision_by_id.get(candidate_id, {})
            expected_room_id = source_label_to_room.get(
                decision.get("sourceLabelId")
            )
            expected_ordinal = room_to_ordinal.get(expected_room_id)
            outline = candidate.get("outline", [])
            if expected_ordinal is None or len(outline) < 3:
                continue
            mask = polygon_mask(gray.shape, outline) > 0
            object_pixels = int(mask.sum())
            expected_pixels = int(
                (mask & (topology["assignment"] == expected_ordinal)).sum()
            )
            foreign_ordinals = sorted(
                int(value)
                for value in np.unique(topology["assignment"][mask])
                if int(value) > 0 and int(value) != expected_ordinal
            )
            foreign_pixels = int(
                (
                    mask
                    & (topology["assignment"] > 0)
                    & (topology["assignment"] != expected_ordinal)
                ).sum()
            )
            foreign_room_ids = [
                ordinal_to_room.get(ordinal, str(ordinal))
                for ordinal in foreign_ordinals
            ]
            object_room_metrics.append({
                "candidateId": candidate_id,
                "expectedRoomId": expected_room_id,
                "objectPixels": object_pixels,
                "expectedRoomPixels": expected_pixels,
                "foreignRoomPixels": foreign_pixels,
                "foreignRoomIds": foreign_room_ids,
                "barrierOrExteriorPixels": (
                    object_pixels - expected_pixels - foreign_pixels
                ),
            })
            if expected_pixels == 0:
                errors.append(
                    f"{candidate_id}: accepted object has no pixels in its "
                    f"declared compiled room {expected_room_id}"
                )
            if foreign_pixels:
                errors.append(
                    f"{candidate_id}: accepted object occupies "
                    f"{foreign_pixels} pixels in foreign compiled rooms "
                    f"{foreign_room_ids}; correct the space boundary or object "
                    "room decision from source evidence"
                )
            if decision.get("classification") == "movable-furniture":
                moments = cv2.moments(mask.astype(np.uint8))
                if moments["m00"]:
                    center_x = int(round(moments["m10"] / moments["m00"]))
                    center_y = int(round(moments["m01"] / moments["m00"]))
                    center_ordinal = int(
                        topology["assignment"][center_y, center_x]
                    )
                    if center_ordinal != expected_ordinal:
                        errors.append(
                            f"{candidate_id}: movable object center belongs to "
                            f"{ordinal_to_room.get(center_ordinal, 'wall-or-exterior')}, "
                            f"not declared compiled room {expected_room_id}"
                        )
        layer_object_rows: list[tuple[str, dict]] = []
        for layer_name in ("movableFurniture", "fixedFixtures"):
            for row in trace_spec.get("layers", {}).get(layer_name, []):
                layer_object_rows.append((layer_name, row))
        layer_object_ids = [
            row.get("sourceObjectCandidateId")
            for _, row in layer_object_rows
        ]
        if None in layer_object_ids or len(layer_object_ids) != len(set(layer_object_ids)):
            errors.append(
                "every green/purple trace needs one unique sourceObjectCandidateId"
            )
        if set(layer_object_ids) != accepted_object_ids:
            errors.append(
                "green/purple traces must consume every and only accepted source object candidate"
            )
        trace_ids = [row.get("traceId") for _, row in layer_object_rows]
        if None in trace_ids or len(trace_ids) != len(set(trace_ids)):
            errors.append("green/purple traces need unique non-empty traceId values")
        for layer_name, row in layer_object_rows:
            candidate_id = row.get("sourceObjectCandidateId")
            decision = object_decision_by_id.get(candidate_id, {})
            expected_classification = (
                "movable-furniture"
                if layer_name == "movableFurniture"
                else "fixed-cabinet-equipment"
            )
            if decision.get("classification") != expected_classification:
                errors.append(
                    f"{row.get('traceId')}: source object classification does not "
                    f"match {layer_name}"
                )
            if row.get("sourceLabelId") != decision.get("sourceLabelId"):
                errors.append(
                    f"{row.get('traceId')}: sourceLabelId differs from the object decision"
                )
            candidate = object_candidate_by_id.get(candidate_id, {})
            if row.get("points") != candidate.get("outline"):
                errors.append(
                    f"{row.get('traceId')}: trace points differ from the frozen "
                    "source object outline"
                )
            if row.get("details") != candidate.get("details"):
                errors.append(
                    f"{row.get('traceId')}: trace details differ from the frozen "
                    "source object details"
                )
            if row.get("name") != decision.get("name"):
                errors.append(
                    f"{row.get('traceId')}: trace name differs from the object decision"
                )
            if row.get("functionalClass") != decision.get("functionalClass"):
                errors.append(
                    f"{row.get('traceId')}: trace functionalClass differs from the "
                    "atomic source object decision"
                )
            if row.get("quantity") != 1:
                errors.append(f"{row.get('traceId')}: trace quantity must be exactly 1")
        if trace_components is not None:
            component_rows = trace_components.get("objects", [])
            component_source_ids = [
                row.get("sourceObjectCandidateId") for row in component_rows
            ]
            if (
                None in component_source_ids
                or len(component_source_ids) != len(set(component_source_ids))
                or set(component_source_ids) != accepted_object_ids
            ):
                errors.append(
                    "trace-components must consume every accepted source object candidate exactly once"
                )
            layer_by_source_id = {
                row.get("sourceObjectCandidateId"): (layer_name, row)
                for layer_name, row in layer_object_rows
            }
            for component in component_rows:
                candidate_id = component.get("sourceObjectCandidateId")
                decision = object_decision_by_id.get(candidate_id, {})
                layer_name, layer = layer_by_source_id.get(candidate_id, (None, {}))
                expected_semantic = (
                    "movable-green"
                    if decision.get("classification") == "movable-furniture"
                    else "fixed-purple"
                )
                if component.get("semantic") != expected_semantic:
                    errors.append(
                        f"{component.get('traceId')}: component semantic differs "
                        "from the source object decision"
                    )
                if component.get("functionalClass") != decision.get("functionalClass"):
                    errors.append(
                        f"{component.get('traceId')}: component functionalClass differs "
                        "from the source object decision"
                    )
                if component.get("quantity") != 1:
                    errors.append(
                        f"{component.get('traceId')}: component quantity must be exactly 1"
                    )
                if component.get("traceId") != layer.get("traceId"):
                    errors.append(
                        f"{component.get('traceId')}: component and trace layer "
                        "do not share the same traceId"
                    )
                expected_room = source_label_to_room.get(decision.get("sourceLabelId"))
                if component.get("roomId") != expected_room:
                    errors.append(
                        f"{component.get('traceId')}: component room differs from "
                        "the source object decision"
                    )
        source_opening_ids = {
            candidate_id
            for candidate_id, decision in opening_decision_by_id.items()
            if decision.get("classification") in (
                TRAVERSABLE_CONNECTION_KINDS | {"glazing"}
            )
        }
        source_divider_ids = divider_ids_for_review
        traversable_source_divider_ids = {
            candidate_id
            for candidate_id in source_divider_ids
            if divider_decision_by_id[candidate_id].get("traversal")
            == "open-passage"
        }
        boundary_only_source_divider_ids = (
            source_divider_ids - traversable_source_divider_ids
        )
        clean_connections = compiled_spec.get("cleanStructure", {}).get("connections", [])
        connection_ids = [item.get("id") for item in clean_connections]
        connection_ids_for_review = set(connection_ids)
        if None in connection_ids or len(connection_ids) != len(set(connection_ids)):
            errors.append("cleanStructure.connections need unique non-empty IDs")
        consumed_opening_ids: list[str] = []
        connected_divider_ids: list[str] = []
        graph: dict[str, set[str]] = {room_id: set() for room_id in room_id_set}
        graph["exterior"] = set()
        room_connection_ids: dict[str, set[str]] = {room_id: set() for room_id in room_id_set}
        room_connection_kinds: dict[str, list[str]] = {room_id: [] for room_id in room_id_set}
        for connection in clean_connections:
            connection_id = connection.get("id")
            left = connection.get("fromRoomId")
            right = connection.get("toRoomId")
            if left == right or left not in room_id_set | {"exterior"} or right not in room_id_set | {"exterior"}:
                errors.append(f"{connection_id}: connection endpoints must name two different known spaces")
                continue
            if connection.get("kind") not in ALL_CONNECTION_KINDS:
                errors.append(f"{connection_id}: unsupported connection kind")
            segment = connection.get("segment", [])
            if not valid_segment(segment):
                errors.append(f"{connection_id}: connection needs one non-zero source-pixel segment")
            if float(connection.get("bottom", -1)) < 0 or float(connection.get("height", 0)) <= 0.3:
                errors.append(f"{connection_id}: invalid opening height")
            trace_ids = connection.get("sourceTraceIds", [])
            divider_ids = connection.get("sourceDividerIds", [])
            if bool(trace_ids) == bool(divider_ids):
                errors.append(
                    f"{connection_id}: connection must cite exactly one physical "
                    "opening source or semantic divider source"
                )
            unknown_openings = sorted(set(trace_ids) - source_opening_ids)
            if unknown_openings:
                errors.append(
                    f"{connection_id}: unknown opening source IDs: {unknown_openings}"
                )
            unknown_dividers = sorted(
                set(divider_ids) - traversable_source_divider_ids
            )
            if unknown_dividers:
                errors.append(
                    f"{connection_id}: divider source is not an accepted "
                    f"open-passage boundary: {unknown_dividers}"
                )
            if divider_ids and connection.get("kind") != "open-passage":
                errors.append(
                    f"{connection_id}: semantic divider connection must be open-passage"
                )
            consumed_opening_ids.extend(trace_ids)
            connected_divider_ids.extend(divider_ids)
            if connection.get("kind") in TRAVERSABLE_CONNECTION_KINDS:
                graph.setdefault(left, set()).add(right)
                graph.setdefault(right, set()).add(left)
                if left in room_id_set:
                    room_connection_ids[left].add(connection_id)
                    room_connection_kinds[left].append(connection["kind"])
                if right in room_id_set:
                    room_connection_ids[right].add(connection_id)
                    room_connection_kinds[right].append(connection["kind"])
            if (
                connection.get("kind") in TRAVERSABLE_CONNECTION_KINDS
                and not divider_ids
                and valid_segment(segment)
            ):
                start = np.asarray(segment[0], dtype=float)
                end = np.asarray(segment[1], dtype=float)
                channel_start = start + 0.12 * (end - start)
                channel_end = start + 0.88 * (end - start)
                channel = np.zeros(gray.shape, dtype=np.uint8)
                cv2.line(
                    channel,
                    tuple(np.rint(channel_start).astype(int)),
                    tuple(np.rint(channel_end).astype(int)),
                    255,
                    1,
                )
                for candidate_id in sorted(accepted_object_ids):
                    outline = object_candidate_by_id[candidate_id].get("outline")
                    if not isinstance(outline, list) or len(outline) < 3:
                        continue
                    occupancy = polygon_mask(gray.shape, outline)
                    intersection_pixels = int(
                        np.count_nonzero((channel > 0) & (occupancy > 0))
                    )
                    if not intersection_pixels:
                        continue
                    opening_object_intersections.append({
                        "connectionId": connection_id,
                        "sourceOpeningIds": trace_ids,
                        "sourceObjectCandidateId": candidate_id,
                        "intersectionPixels": intersection_pixels,
                    })
                    errors.append(
                        f"{candidate_id}: source object crosses the physical opening "
                        f"centerline of {connection_id} ({intersection_pixels}px); "
                        "retrace the object or opening from source evidence"
                    )
        if len(consumed_opening_ids) != len(set(consumed_opening_ids)):
            errors.append("one source opening may compile to only one spatial connection")
        missing_doors = sorted(source_opening_ids - set(consumed_opening_ids))
        if missing_doors:
            errors.append(f"door traces lack spatial connection facts: {missing_doors}")
        if len(connected_divider_ids) != len(set(connected_divider_ids)):
            errors.append(
                "one semantic divider may compile to only one spatial connection"
            )
        missing_traversable_dividers = sorted(
            traversable_source_divider_ids - set(connected_divider_ids)
        )
        if missing_traversable_dividers:
            errors.append(
                "open-passage semantic dividers lack spatial connections: "
                f"{missing_traversable_dividers}"
            )
        compiled_dividers = compiled_spec.get("semanticDividers", [])
        compiled_divider_sources = [
            item.get("sourceDividerId") for item in compiled_dividers
        ]
        if (
            None in compiled_divider_sources
            or len(compiled_divider_sources) != len(set(compiled_divider_sources))
        ):
            errors.append(
                "compiled semantic dividers need unique non-empty sourceDividerId"
            )
        if set(compiled_divider_sources) != source_divider_ids:
            errors.append(
                "compiled semantic dividers must consume every accepted source "
                "divider exactly once"
            )
        connection_by_id = {
            item.get("id"): item for item in clean_connections
        }
        for divider in compiled_dividers:
            source_divider_id = divider.get("sourceDividerId")
            decision = divider_decision_by_id.get(source_divider_id, {})
            traversal = decision.get("traversal")
            if divider.get("traversal") != traversal:
                errors.append(
                    f"{divider.get('id')}: compiled traversal differs from "
                    "the source semantic decision"
                )
            candidate = divider_candidate_by_id.get(source_divider_id, {})
            if divider.get("segment") != candidate.get("segment"):
                errors.append(
                    f"{divider.get('id')}: compiled divider segment differs from "
                    "its source candidate"
                )
            connection_id = divider.get("connectionId")
            connection = connection_by_id.get(connection_id)
            if traversal == "open-passage":
                if (
                    connection is None
                    or connection.get("sourceDividerId") != source_divider_id
                ):
                    errors.append(
                        f"{divider.get('id')}: open-passage divider lacks its "
                        "same-source connection"
                    )
            elif connection_id is not None:
                errors.append(
                    f"{divider.get('id')}: boundary-only divider must not carry "
                    "a connectionId"
                )
        reachable = {"exterior"}
        queue = ["exterior"]
        while queue:
            current = queue.pop(0)
            for neighbor in graph.get(current, set()):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append(neighbor)
        unreachable = sorted(room_id_set - reachable)
        if unreachable:
            errors.append(f"spaces are not connected to an evidenced exterior route: {unreachable}")
        topology_class_by_id = {
            item.get("id"): item.get("topologyClass")
            for item in spaces
        }
        for room_id, topology_class in topology_class_by_id.items():
            access_count = len(room_connection_ids.get(room_id, set()))
            if access_count < 1:
                errors.append(f"{room_id}: {topology_class} space has no traversable connection")
            if (
                topology_class == "enclosed"
                and not ENCLOSED_ACCESS_KINDS.intersection(room_connection_kinds.get(room_id, []))
            ):
                errors.append(
                    f"{room_id}: enclosed space needs an evidenced door or sliding-door access"
                )
            if topology_class == "enclosed" and access_count > 1:
                extra_access_rooms[room_id] = room_connection_ids[room_id]
        connection_metrics = {
            "spaces": len(room_id_set),
            "connections": len(clean_connections),
            "sourceOpenings": len(source_opening_ids),
            "semanticDividers": len(source_divider_ids),
            "traversableSemanticDividers": len(
                traversable_source_divider_ids
            ),
            "boundaryOnlySemanticDividers": len(
                boundary_only_source_divider_ids
            ),
            "roomsReachableFromExterior": len(room_id_set & reachable),
            "unreachableRoomIds": unreachable,
            "enclosedRoomsWithExtraAccess": sorted(extra_access_rooms),
        }
        if compiled_spec.get("cleanStructure", {}).get("walls") != geometry_rows:
            errors.append(
                "trace-spec cleanStructure.walls must be the exact wall-geometry rows"
            )
        if compiled_spec.get("layers", {}).get("walls") != geometry_rows:
            errors.append(
                "trace-spec layers.walls must be the exact wall-geometry rows"
            )
        for field in ("doors", "windows"):
            if trace_spec.get("layers", {}).get(field) != compiled_spec.get("layers", {}).get(field):
                errors.append(
                    f"trace-spec layers.{field} must be generated from source opening evidence"
                )
        if trace_spec.get("cleanStructure", {}).get("connections") != compiled_spec.get(
            "cleanStructure", {}
        ).get("connections"):
            errors.append(
                "trace-spec connections must preserve compiled source opening geometry"
            )
        if trace_spec.get("cleanStructure", {}).get("windows") != compiled_spec.get(
            "cleanStructure", {}
        ).get("windows"):
            errors.append(
                "trace-spec windows must preserve compiled source opening geometry"
            )
        interior_pixels = int(topology["interior"].sum())
        assigned_pixels = int(
            ((topology["interior"] > 0) & (topology["assignment"] > 0)).sum()
        )
        missed = interior_pixels - assigned_pixels
        floor_metrics = {
            "derivedInteriorPixels": interior_pixels,
            "assignedInteriorPixels": assigned_pixels,
            "missedPixels": missed,
            "outsidePixels": 0,
            "sharedBoundaryPixels": 0,
            "overlapCorePixels": 0,
            "wallClippedPixels": 0,
            "missedRatio": round(missed / max(1, interior_pixels), 6),
            "outsideRatio": 0.0,
        }
        if interior_pixels == 0:
            errors.append("wall and entry evidence did not produce an enclosed interior")
        if missed:
            errors.append(f"compiled spaces leave {missed} usable interior pixels unassigned")
        topology_metrics = topology["metrics"]

    review_ids = set(visual.get("reviewedWallIds", []))
    geometry_ids = {row.get("id") for row in geometry_rows}
    if review_ids != geometry_ids:
        errors.append("Agent visual review must enumerate every generated wall ID")
    if trace_spec_path is not None:
        if set(visual.get("reviewedSpaceLabelIds", [])) != set(label_candidate_by_id):
            errors.append(
                "Agent visual review must enumerate every source space-label ID"
            )
        if set(visual.get("reviewedRoomIds", [])) != room_ids_for_review:
            errors.append("Agent visual review must enumerate every compiled room ID")
        if set(visual.get("reviewedConnectionIds", [])) != connection_ids_for_review:
            errors.append("Agent visual review must enumerate every spatial connection ID")
        if set(visual.get("reviewedOpeningIds", [])) != opening_ids_for_review:
            errors.append(
                "Agent visual review must enumerate every active source opening ID"
            )
        if set(visual.get("reviewedDividerIds", [])) != divider_ids_for_review:
            errors.append(
                "Agent visual review must enumerate every accepted semantic divider ID"
            )
        if set(visual.get("reviewedObjectIds", [])) != set(object_candidate_by_id):
            errors.append(
                "Agent visual review must enumerate every source object candidate ID"
            )
        coverage_rows = visual.get("objectCoverageReviews", [])
        coverage_by_label = {
            item.get("sourceLabelId"): item
            for item in coverage_rows
            if isinstance(item, dict)
        }
        if (
            len(coverage_by_label) != len(coverage_rows)
            or set(coverage_by_label) != set(label_candidate_by_id)
        ):
            errors.append(
                "Agent object coverage review must enumerate every source space label"
            )
        else:
            for label_id, coverage in coverage_by_label.items():
                expected_ids = {
                    candidate_id
                    for candidate_id in accepted_object_ids
                    if object_decision_by_id[candidate_id].get("sourceLabelId")
                    == label_id
                }
                if set(coverage.get("sourceObjectCandidateIds", [])) != expected_ids:
                    errors.append(
                        f"{label_id}: object coverage review differs from accepted "
                        "source objects"
                    )
                observed_counts = coverage.get("observedFunctionalCounts")
                expected_counts = dict(sorted(functional_counts_by_label.get(label_id, Counter()).items()))
                if observed_counts != expected_counts:
                    errors.append(
                        f"{label_id}: observedFunctionalCounts must exactly match the "
                        f"atomic source ledger; expected={expected_counts}"
                    )
                if not isinstance(coverage.get("finding"), str) or not coverage[
                    "finding"
                ].strip():
                    errors.append(
                        f"{label_id}: object coverage review needs a concrete finding"
                    )
        extra_reviews = {
            item.get("roomId"): set(item.get("connectionIds", []))
            for item in visual.get("extraAccessReviews", [])
            if isinstance(item, dict)
        }
        for room_id, expected_ids in extra_access_rooms.items():
            if extra_reviews.get(room_id) != expected_ids:
                errors.append(
                    f"{room_id}: enclosed space has extra access and needs a visual review "
                    "bound to every connection ID"
                )
    if visual.get("status") != "passed":
        errors.append("Agent visual review is not passed")
    if visual.get("unresolved"):
        errors.append("Agent visual review contains unresolved findings")
    expected_review_overlays = set(evidence.get("candidateOverlayPaths", {}).values())
    reviewed_overlays = visual.get("reviewedEvidenceOverlayPaths")
    if (
        not isinstance(reviewed_overlays, list)
        or set(reviewed_overlays) != expected_review_overlays
    ):
        errors.append(
            "Agent visual review must enumerate all six formal evidence-overlay paths"
        )
    if (
        not visual.get("sourceEvidenceOverlay")
        or not visual.get("overlayImage")
        or not visual.get("roomContactSheet")
    ):
        errors.append(
            "Agent visual review requires source evidence, final overlay and room contact-sheet evidence"
        )
    for field in ("sourceEvidenceOverlay", "overlayImage", "roomContactSheet"):
        value = visual.get(field)
        if value and not (visual_path.parent / value).exists():
            errors.append(f"missing visual review artifact: {value}")

    return {
        "schema": "interior.floorplan-source-model-validation.v1",
        "traceSpecSha256": digest(trace_spec_path) if trace_spec_path is not None else None,
        "sourceSha256": source_sha,
        "nativeLayoutSha256": (
            digest(native_layout_path)
            if native_layout_path is not None and layout_mode == "native-layout-furnished"
            else None
        ),
        "layoutAuthority": layout_authority,
        "evidenceSha256": evidence_sha,
        "decisionsSha256": decisions_sha,
        "geometrySha256": digest(geometry_path),
        "passed": not errors,
        "errors": errors,
        "evidenceMetrics": evidence_metrics,
        "geometryMetrics": geometry_metrics,
        "independentFloorMetrics": floor_metrics,
        "connectionMetrics": connection_metrics,
        "topologyMetrics": topology_metrics,
        "objectMetrics": {
            "sourceCandidates": len(object_candidate_by_id),
            "acceptedObjects": len(accepted_object_ids),
            "traceComponents": (
                len(trace_components.get("objects", []))
                if trace_components is not None
                else None
            ),
            "sourceEvidence": object_evidence_metrics,
            "compiledRoomConsistency": object_room_metrics,
            "physicalOpeningIntersections": opening_object_intersections,
            "functionalCounts": dict(sorted(Counter(functional_class_by_object.values()).items())),
            "atomicQuantity": len(accepted_object_ids),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--native-layout")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--geometry", required=True)
    parser.add_argument("--visual-review", required=True)
    parser.add_argument("--trace-spec")
    parser.add_argument("--trace-components")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = validate(
        Path(args.source).resolve(),
        Path(args.native_layout).resolve() if args.native_layout else None,
        Path(args.evidence).resolve(),
        Path(args.decisions).resolve(),
        Path(args.geometry).resolve(),
        Path(args.visual_review).resolve(),
        Path(args.trace_spec).resolve() if args.trace_spec else None,
        Path(args.trace_components).resolve() if args.trace_components else None,
    )
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": report["passed"],
        "report": str(report_path),
        "wallCandidates": len(report["evidenceMetrics"]) // 2,
        "walls": len(report["geometryMetrics"]),
        "floor": report["independentFloorMetrics"],
        "connections": report["connectionMetrics"],
        "errors": report["errors"],
    }, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
