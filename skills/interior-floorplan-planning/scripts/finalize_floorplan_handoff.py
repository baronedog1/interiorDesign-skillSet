#!/usr/bin/env python3
"""Compile the unique floorplan facts, validate them once and package the handoff."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import cv2

from topology_compiler import compile_space_topology
from compile_floorplan_handoff import validate_compiled_structure


SCHEMAS = {
    "traceSpec": "interior.floorplan-trace.v3",
    "structureData": "interior.floorplan-structure.v4",
    "traceComponents": "interior.trace-components.v2",
}
PRODUCER_VERSION = "9.0.0"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def artifact_entry(path: Path, target_name: str) -> dict:
    return {
        "path": f"artifacts/{target_name}",
        "sha256": digest(path),
        "bytes": path.stat().st_size,
    }


def canonical_digest(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def metric_transform(trace_spec: dict):
    x0, y0, x1, y1 = map(float, trace_spec["planBounds"])
    width_m = float(trace_spec["knownSizeMm"]["width"]) / 1000
    depth_m = float(trace_spec["knownSizeMm"]["depth"]) / 1000

    def transform(point: list[float]) -> list[float]:
        return [
            round((float(point[0]) - x0) / (x1 - x0) * width_m, 5),
            round((float(point[1]) - y0) / (y1 - y0) * depth_m, 5),
        ]

    return transform, width_m, depth_m


def compile_structure_data(trace_spec: dict) -> dict:
    """Generate structure-data directly; no hand-authored second structure is accepted."""
    transform, width_m, depth_m = metric_transform(trace_spec)
    topology = trace_spec["compiledTopology"]
    wall_adjacency = topology["wallAdjacency"]
    walls = []
    for source in trace_spec["cleanStructure"]["walls"]:
        points = source["points"]
        start = transform([
            (points[0][0] + points[3][0]) / 2,
            (points[0][1] + points[3][1]) / 2,
        ])
        end = transform([
            (points[1][0] + points[2][0]) / 2,
            (points[1][1] + points[2][1]) / 2,
        ])
        face_a_mid = transform([
            (points[0][0] + points[1][0]) / 2,
            (points[0][1] + points[1][1]) / 2,
        ])
        face_b_mid = transform([
            (points[2][0] + points[3][0]) / 2,
            (points[2][1] + points[3][1]) / 2,
        ])
        adjacent = wall_adjacency[source["id"]]
        walls.append({
            "id": source["id"],
            "name": source.get(
                "name",
                f"{'外墙' if 'exterior' in adjacent else '分隔墙'} {source['id']}",
            ),
            "start": start,
            "end": end,
            "thickness": round(math.dist(face_a_mid, face_b_mid), 5),
            "height": float(source.get("height", 3.0)),
            "type": "external" if "exterior" in adjacent else "partition",
            "adjacentRoomIds": adjacent,
            "sourceTraceIds": [source["id"]],
        })
    wall_by_id = {wall["id"]: wall for wall in walls}

    windows = []
    for source in trace_spec["cleanStructure"].get("windows", []):
        source_id = source["id"]
        host_id = source.get("hostWallTraceId")
        if host_id not in wall_by_id:
            raise ValueError(f"{source_id}: hostWallTraceId must name one clean wall")
        points = source.get("points", [])
        if len(points) < 2:
            raise ValueError(f"{source_id}: window needs at least two source points")
        source_start = transform(points[0])
        source_end = transform(points[-1])
        host = wall_by_id[host_id]
        dx = host["end"][0] - host["start"][0]
        dz = host["end"][1] - host["start"][1]
        length = math.hypot(dx, dz)
        unit = [dx / length, dz / length]
        window_dx = source_end[0] - source_start[0]
        window_dz = source_end[1] - source_start[1]
        window_width = math.hypot(window_dx, window_dz)
        if window_width <= 0.01:
            raise ValueError(f"{source_id}: source window must have non-zero width")
        parallel = abs(
            window_dx / window_width * unit[0]
            + window_dz / window_width * unit[1]
        )
        if parallel < 0.95:
            raise ValueError(
                f"{source_id}: source window is not parallel to host wall {host_id}"
            )
        endpoint_offsets = [
            (point[0] - host["start"][0]) * unit[0]
            + (point[1] - host["start"][1]) * unit[1]
            for point in (source_start, source_end)
        ]
        if min(endpoint_offsets) < -1e-6 or max(endpoint_offsets) > length + 1e-6:
            raise ValueError(
                f"{source_id}: source window exceeds host wall {host_id}; "
                "correct hostWallTraceId in the authored source binding"
            )
        offset = sum(endpoint_offsets) / 2
        windows.append({
            "id": source_id,
            "name": source.get("name", source_id),
            "existence": "present",
            "wallId": host_id,
            "offset": round(offset, 5),
            "width": round(window_width, 5),
            "sill": float(source.get("sill", 0.75)),
            "openingHeight": float(source.get("openingHeight", 1.55)),
            "kind": source.get("kind", "standard"),
            "openingStyle": source.get("openingStyle"),
            "frameDepth": float(source.get("frameDepth", 0.08)),
            "sourceTraceIds": list(source.get("sourceTraceIds") or [source_id]),
        })

    connections = []
    for source in trace_spec["cleanStructure"].get("connections", []):
        connections.append({
            "id": source["id"],
            "fromRoomId": source["fromRoomId"],
            "toRoomId": source["toRoomId"],
            "kind": source["kind"],
            "openingStyle": source.get("openingStyle"),
            "start": transform(source["segment"][0]),
            "end": transform(source["segment"][1]),
            "bottom": float(source.get("bottom", 0)),
            "height": float(source.get("height", 2.1)),
            "sourceTraceIds": list(source.get("sourceTraceIds") or []),
            **(
                {"sourceDividerIds": list(source["sourceDividerIds"])}
                if source.get("sourceDividerIds")
                else {}
            ),
        })

    boundary_features = []
    for source in trace_spec["cleanStructure"].get("boundaryFeatures", []):
        segment = source.get("segment", [])
        if len(segment) != 2:
            raise ValueError(f"{source.get('id')}: boundary feature needs one segment")
        boundary_features.append({
            "id": source["id"],
            "kind": source["kind"],
            "roomId": source["roomId"],
            "start": transform(segment[0]),
            "end": transform(segment[1]),
            "bottom": float(source.get("bottom", 0.0)),
            "height": float(source.get("height", 1.1)),
            "sourceTraceIds": list(source.get("sourceTraceIds") or [source["id"]]),
            "reason": source.get("reason"),
        })

    semantic_dividers = [{
        "id": source["id"],
        "sourceDividerId": source["sourceDividerId"],
        "roomIds": list(source["roomIds"]),
        "traversal": source["traversal"],
        "start": transform(source["segment"][0]),
        "end": transform(source["segment"][1]),
        "reason": source["reason"],
        **(
            {"connectionId": source["connectionId"]}
            if source.get("connectionId")
            else {}
        ),
    } for source in trace_spec.get("semanticDividers", [])]

    rooms = [{
        "id": room["id"],
        "name": room["name"],
        "spaceType": room["spaceType"],
        "topologyClass": room["topologyClass"],
        "polygon": [transform(point) for point in room["polygon"]],
        "labelPosition": transform(room["labelPosition"]),
        "areaM2": room["areaM2"],
    } for room in trace_spec["spaces"]]
    return {
        "schema": SCHEMAS["structureData"],
        "floorplanId": trace_spec["floorplanId"],
        "name": trace_spec.get("name", trace_spec["floorplanId"]),
        "source": {
            "kind": "compiled-floorplan-handoff",
            "image": "structure-source.png",
            "traceSpec": "trace-spec.json",
        },
        "coordinateSystem": {
            "units": "m",
            "origin": "north-west",
            "realWidthMeters": width_m,
            "realDepthMeters": depth_m,
            "defaultWallHeightMeters": 3.0,
        },
        "dimensionAnnotations": {
            "widthMeters": width_m,
            "depthMeters": depth_m,
            "widthLabel": "总宽",
            "depthLabel": "总深",
        },
        "floorBoundary": [transform(point) for point in trace_spec["floorBoundary"]],
        "rooms": rooms,
        "walls": walls,
        "windows": windows,
        "connections": connections,
        "boundaryFeatures": boundary_features,
        "semanticDividers": semantic_dividers,
        "topology": topology,
        "layers": {
            "walls": True,
            "windows": True,
            "boundaryFeatures": True,
            "fixedFixtures": True,
            "movableFurniture": True,
            "grid": True,
            "annotations": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--geometry", required=True)
    parser.add_argument("--visual-review", required=True)
    parser.add_argument("--visual-overlay", required=True)
    parser.add_argument("--room-contact-sheet", required=True)
    parser.add_argument("--trace-spec", required=True)
    parser.add_argument("--quadrants", required=True)
    parser.add_argument("--structure-image", required=True)
    parser.add_argument("--classified-overlay", required=True)
    parser.add_argument("--trace-combination", required=True)
    parser.add_argument("--native-layout")
    parser.add_argument("--trace-components", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scripts = Path(__file__).resolve().parent
    evidence_path = Path(args.evidence).resolve()
    evidence = load(evidence_path)
    overlay_relative = evidence.get("candidateOverlayPath")
    if (
        not isinstance(overlay_relative, str)
        or not overlay_relative
        or Path(overlay_relative).is_absolute()
        or ".." in Path(overlay_relative).parts
    ):
        raise SystemExit("source evidence candidateOverlayPath must be a safe relative path")
    source_evidence_overlay = (evidence_path.parent / overlay_relative).resolve()
    layered_overlay_paths = evidence.get("candidateOverlayPaths")
    if not isinstance(layered_overlay_paths, dict):
        raise SystemExit("source evidence candidateOverlayPaths must be an object")
    paths = {
        key: Path(value).resolve()
        for key, value in {
            "sourceImage": args.source,
            "sourceEvidence": args.evidence,
            "sourceEvidenceOverlay": source_evidence_overlay,
            "semanticDecisions": args.decisions,
            "wallGeometry": args.geometry,
            "agentVisualReview": args.visual_review,
            "visualOverlay": args.visual_overlay,
            "roomContactSheet": args.room_contact_sheet,
            "quadrantsImage": args.quadrants,
            "structureImage": args.structure_image,
            "classifiedOverlay": args.classified_overlay,
            "traceCombinationImage": args.trace_combination,
            "traceComponents": args.trace_components,
        }.items()
    }
    if args.native_layout:
        paths["nativeLayout"] = Path(args.native_layout).resolve()
    for key, relative in layered_overlay_paths.items():
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise SystemExit(
                f"source evidence candidateOverlayPaths.{key} must be a safe relative path"
            )
        paths[f"evidenceOverlay_{key}"] = (evidence_path.parent / relative).resolve()
    authored_trace_path = Path(args.trace_spec).resolve()
    paths["authoredTraceSpec"] = authored_trace_path
    missing = [f"{key}: {path}" for key, path in paths.items() if not path.is_file()]
    if missing:
        raise SystemExit("missing required artifacts:\n" + "\n".join(missing))

    authored_trace = load(authored_trace_path)
    source_evidence = load(paths["sourceEvidence"])
    semantic_decisions = load(paths["semanticDecisions"])
    wall_geometry = load(paths["wallGeometry"])
    components = load(paths["traceComponents"])
    layout_authority = source_evidence.get("layoutAuthority")
    if not isinstance(layout_authority, dict):
        raise SystemExit("source evidence requires layoutAuthority")
    layout_mode = layout_authority.get("mode")
    if layout_mode == "native-layout-furnished":
        if "nativeLayout" not in paths:
            raise SystemExit("native-layout-furnished mode requires --native-layout")
        if layout_authority.get("nativeLayoutSha256") != digest(paths["nativeLayout"]):
            raise SystemExit("layoutAuthority does not bind the supplied native layout")
    elif layout_mode == "source-furnished":
        if "nativeLayout" in paths or layout_authority.get("nativeLayoutSha256") is not None:
            raise SystemExit("source-furnished mode must not require a redundant native layout")
    else:
        raise SystemExit("unsupported layoutAuthority.mode")
    if authored_trace.get("schema") != SCHEMAS["traceSpec"]:
        raise SystemExit(f"traceSpec schema must be {SCHEMAS['traceSpec']}")
    if components.get("schema") != SCHEMAS["traceComponents"]:
        raise SystemExit(f"traceComponents schema must be {SCHEMAS['traceComponents']}")
    if wall_geometry.get("schema") != "interior.floorplan-wall-geometry.v1":
        raise SystemExit("wallGeometry schema must be interior.floorplan-wall-geometry.v1")
    if "walls" in authored_trace.get("cleanStructure", {}):
        raise SystemExit(
            "authored trace-spec must not contain cleanStructure.walls; "
            "the finalizer injects the frozen wall geometry"
        )
    generated_layers = sorted(
        set(authored_trace.get("layers", {})) & {"walls", "windows", "doors"}
    )
    if generated_layers:
        raise SystemExit(
            "authored trace-spec contains generated source layers: "
            + ", ".join(generated_layers)
        )
    for binding in authored_trace.get("cleanStructure", {}).get("connections", []):
        forbidden = sorted(
            set(binding)
            & {"kind", "segment", "sourceTraceIds", "sourceDividerIds"}
        )
        if forbidden:
            raise SystemExit(
                f"{binding.get('id')}: authored connection contains generated fields: "
                + ", ".join(forbidden)
            )
        source_opening_id = binding.get("sourceOpeningId")
        source_divider_id = binding.get("sourceDividerId")
        if bool(source_opening_id) == bool(source_divider_id):
            raise SystemExit(
                f"{binding.get('id')}: authored connection needs exactly one of "
                "sourceOpeningId or sourceDividerId"
            )
    for binding in authored_trace.get("cleanStructure", {}).get("windows", []):
        forbidden = sorted(set(binding) & {"type", "points", "width", "sourceTraceIds"})
        if forbidden:
            raise SystemExit(
                f"{binding.get('id')}: authored window contains generated fields: "
                + ", ".join(forbidden)
            )
        if not binding.get("sourceOpeningId"):
            raise SystemExit(
                f"{binding.get('id')}: authored window needs sourceOpeningId"
            )
    for divider in authored_trace.get("semanticDividers", []):
        generated = sorted(set(divider) & {"segment", "traversal", "roomIds"})
        if generated:
            raise SystemExit(
                f"{divider.get('id')}: authored semantic divider contains "
                "generated fields: "
                + ", ".join(generated)
            )
        source_divider_id = divider.get("sourceDividerId")
        if not source_divider_id or divider.get("sourceOpeningId"):
            raise SystemExit(
                f"{divider.get('id')}: authored semantic divider needs exactly "
                "one sourceDividerId"
            )
    generated_fields = [
        field
        for field in ("floorBoundary", "spaces", "compiledTopology")
        if field in authored_trace
    ]
    if generated_fields:
        raise SystemExit(
            "authored trace-spec contains generated topology fields: "
            + ", ".join(generated_fields)
        )
    floorplan_id = authored_trace.get("floorplanId")
    if not floorplan_id or components.get("floorplanId") != floorplan_id:
        raise SystemExit("trace-spec and trace-components must share a non-empty floorplanId")
    object_decisions = {
        row.get("candidateId"): row
        for row in semantic_decisions.get("objects", [])
        if row.get("classification")
        in {"movable-furniture", "fixed-cabinet-equipment"}
    }
    accepted_object_ids = set(object_decisions)
    source_label_to_room = {
        seed.get("sourceLabelId"): seed.get("id")
        for seed in authored_trace.get("spaceSeeds", [])
    }
    layer_by_source_id: dict[str, tuple[str, dict]] = {}
    for layer_name in ("movableFurniture", "fixedFixtures"):
        for row in authored_trace.get("layers", {}).get(layer_name, []):
            source_object_id = row.get("sourceObjectCandidateId")
            if not source_object_id or source_object_id in layer_by_source_id:
                raise SystemExit(
                    "every green/purple trace needs one unique "
                    "sourceObjectCandidateId"
                )
            layer_by_source_id[source_object_id] = (layer_name, row)
    if set(layer_by_source_id) != accepted_object_ids:
        raise SystemExit(
            "green/purple traces must consume every and only accepted "
            "source object candidate"
        )
    component_by_source_id: dict[str, dict] = {}
    for component in components.get("objects", []):
        source_object_id = component.get("sourceObjectCandidateId")
        if not source_object_id or source_object_id in component_by_source_id:
            raise SystemExit(
                "trace-components need one unique sourceObjectCandidateId per object"
            )
        component_by_source_id[source_object_id] = component
    if set(component_by_source_id) != accepted_object_ids:
        raise SystemExit(
            "trace-components must consume every accepted source object "
            "candidate exactly once"
        )
    for source_object_id, decision in object_decisions.items():
        layer_name, layer = layer_by_source_id[source_object_id]
        component = component_by_source_id[source_object_id]
        expected_layer = (
            "movableFurniture"
            if decision.get("classification") == "movable-furniture"
            else "fixedFixtures"
        )
        expected_semantic = (
            "movable-green"
            if expected_layer == "movableFurniture"
            else "fixed-purple"
        )
        expected_room = source_label_to_room.get(decision.get("sourceLabelId"))
        if layer_name != expected_layer:
            raise SystemExit(
                f"{source_object_id}: object classification does not match "
                "the green/purple trace layer"
            )
        if layer.get("sourceLabelId") != decision.get("sourceLabelId"):
            raise SystemExit(
                f"{source_object_id}: trace sourceLabelId differs from the "
                "semantic decision"
            )
        source_candidate = next(
            (
                row
                for row in source_evidence.get("objectCandidates", [])
                if row.get("id") == source_object_id
            ),
            {},
        )
        if source_candidate.get("assemblyId") != decision.get("assemblyId"):
            raise SystemExit(
                f"{source_object_id}: source candidate assemblyId differs from the semantic decision"
            )
        if layer.get("points") != source_candidate.get("outline"):
            raise SystemExit(
                f"{source_object_id}: trace points differ from the frozen source "
                "object outline"
            )
        if layer.get("details") != source_candidate.get("details"):
            raise SystemExit(
                f"{source_object_id}: trace details differ from the frozen source "
                "object details"
            )
        if layer.get("name") != decision.get("name"):
            raise SystemExit(
                f"{source_object_id}: trace name differs from the semantic decision"
            )
        if component.get("traceId") != layer.get("traceId"):
            raise SystemExit(
                f"{source_object_id}: trace-component and trace layer IDs differ"
            )
        if component.get("semantic") != expected_semantic:
            raise SystemExit(
                f"{source_object_id}: component semantic differs from the "
                "source object decision"
            )
        if layer.get("assemblyId") != decision.get("assemblyId") \
                or component.get("assemblyId") != decision.get("assemblyId"):
            raise SystemExit(
                f"{source_object_id}: assemblyId differs across evidence, trace and component"
            )
        if layer.get("assemblyRole") != decision.get("assemblyRole") \
                or component.get("assemblyRole") != decision.get("assemblyRole"):
            raise SystemExit(
                f"{source_object_id}: assemblyRole differs across trace and component"
            )
        if not expected_room or component.get("roomId") != expected_room:
            raise SystemExit(
                f"{source_object_id}: component room differs from the "
                "source object decision"
            )
        if not isinstance(component.get("rotationY"), (int, float)):
            raise SystemExit(f"{source_object_id}: trace-component requires an explicit rotationY")
        orientation = component.get("orientation")
        if not isinstance(orientation, dict) or orientation.get("evidence") not in {
            "source-symbol", "source-outline-axis", "user-explicit-layout"
        }:
            raise SystemExit(
                f"{source_object_id}: trace-component requires source-bound orientation evidence"
            )
        local_axes = orientation.get("localAxes")
        if not isinstance(local_axes, dict) or not local_axes:
            raise SystemExit(f"{source_object_id}: orientation.localAxes must not be empty")
        for role, axis in local_axes.items():
            if role not in {"front", "back", "headboard"} or axis not in {"+X", "-X", "+Z", "-Z"}:
                raise SystemExit(f"{source_object_id}: invalid orientation axis {role}={axis}")

    expected_assemblies: dict[str, list[str]] = {}
    for source_object_id, decision in object_decisions.items():
        assembly_id = decision.get("assemblyId")
        if assembly_id:
            expected_assemblies.setdefault(assembly_id, []).append(
                component_by_source_id[source_object_id]["traceId"]
            )
    declared_assemblies = components.get("assemblies", [])
    declared_by_id = {
        row.get("id"): row for row in declared_assemblies if isinstance(row, dict)
    }
    if len(declared_by_id) != len(declared_assemblies) \
            or set(declared_by_id) != set(expected_assemblies):
        raise SystemExit("trace-components assembly registry differs from source decisions")
    for assembly_id, child_trace_ids in expected_assemblies.items():
        assembly = declared_by_id[assembly_id]
        if len(child_trace_ids) < 2:
            raise SystemExit(f"{assembly_id}: assembly needs at least two atomic members")
        if assembly.get("compositionPolicy") != "source-evidenced-atomic-members" \
                or assembly.get("childTraceIds") != child_trace_ids:
            raise SystemExit(f"{assembly_id}: assembly membership is invalid")

    source_image = cv2.imread(str(paths["sourceImage"]), cv2.IMREAD_COLOR)
    if source_image is None:
        raise SystemExit(f"cannot read source image: {paths['sourceImage']}")
    topology = compile_space_topology(
        authored_trace,
        source_image.shape[:2],
        wall_geometry,
        source_evidence,
        semantic_decisions,
    )
    if topology["errors"]:
        raise SystemExit("room topology compilation failed:\n" + "\n".join(topology["errors"]))
    compiled_trace = topology["traceSpec"]
    structure = compile_structure_data(compiled_trace)
    structure_errors = validate_compiled_structure(structure)
    if structure_errors:
        raise SystemExit(
            "compiled structure rejected before handoff:\n" + "\n".join(structure_errors)
        )
    room_ids = {room["id"] for room in compiled_trace["spaces"]}
    unresolved_component_rooms = sorted({
        row.get("roomId")
        for row in components.get("objects", [])
        if row.get("roomId") not in room_ids
    })
    if unresolved_component_rooms:
        raise SystemExit(
            "trace-components reference unknown rooms: "
            + ", ".join(map(str, unresolved_component_rooms))
        )

    visual_review = load(paths["agentVisualReview"])
    for key, field in (
        ("sourceEvidenceOverlay", "sourceEvidenceOverlay"),
        ("visualOverlay", "overlayImage"),
        ("roomContactSheet", "roomContactSheet"),
    ):
        relative = visual_review.get(field)
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise SystemExit(f"agent visual review {field} must be a safe relative path")
        bound_path = (paths["agentVisualReview"].parent / relative).resolve()
        if not bound_path.is_file() or digest(bound_path) != digest(paths[key]):
            raise SystemExit(f"{key} does not match the artifact referenced by agent visual review")

    output = Path(args.out).resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"handoff target must be empty: {output}")
    build_dir = output / ".build"
    artifacts_dir = output / "artifacts"
    reports_dir = output / "reports"
    build_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    compiled_trace_path = build_dir / "trace-spec.json"
    structure_path = build_dir / "structure-data.json"
    compiled_trace_path.write_text(
        json.dumps(compiled_trace, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    structure_path.write_text(
        json.dumps(structure, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["traceSpec"] = compiled_trace_path
    paths["structureData"] = structure_path
    paths.pop("authoredTraceSpec")

    source_model_report = reports_dir / "source-model-validation.json"
    validation_command = [
        sys.executable,
        str(scripts / "validate_source_model.py"),
        "--source", str(paths["sourceImage"]),
        "--evidence", str(paths["sourceEvidence"]),
        "--decisions", str(paths["semanticDecisions"]),
        "--geometry", str(paths["wallGeometry"]),
        "--visual-review", str(paths["agentVisualReview"]),
        "--trace-spec", str(paths["traceSpec"]),
        "--trace-components", str(paths["traceComponents"]),
        "--report", str(source_model_report),
    ]
    if "nativeLayout" in paths:
        validation_command.extend(["--native-layout", str(paths["nativeLayout"])])
    run(validation_command)

    clean_ids = {
        trace_id
        for layer in ("walls", "windows", "connections", "boundaryFeatures")
        for item in compiled_trace.get("cleanStructure", {}).get(layer, [])
        for trace_id in [
            item["id"],
            *item.get("sourceTraceIds", []),
            *item.get("sourceDividerIds", []),
        ]
    }
    clean_ids.update(
        trace_id
        for item in compiled_trace.get("semanticDividers", [])
        for trace_id in [item["id"], item["sourceDividerId"]]
    )
    component_ids = {
        item["id"]
        for layer in ("movableFurniture", "fixedFixtures")
        for item in compiled_trace.get("layers", {}).get(layer, [])
    }
    unresolved_components = sorted({
        item.get("traceId")
        for item in components.get("objects", [])
        if item.get("traceId") not in component_ids
    })
    if unresolved_components:
        raise SystemExit(f"trace-components contains unresolved source IDs: {unresolved_components}")

    target_names = {
        "sourceImage": f"source-floorplan{paths['sourceImage'].suffix.lower()}",
        "sourceEvidence": "source-evidence.json",
        "sourceEvidenceOverlay": "source-evidence-overlay.png",
        "semanticDecisions": "semantic-decisions.json",
        "wallGeometry": "wall-geometry.json",
        "agentVisualReview": "agent-visual-review.json",
        "visualOverlay": visual_review["overlayImage"],
        "roomContactSheet": visual_review["roomContactSheet"],
        "traceSpec": "trace-spec.json",
        "quadrantsImage": f"floorplan-four-quadrants{paths['quadrantsImage'].suffix.lower()}",
        "structureImage": f"floorplan-structure{paths['structureImage'].suffix.lower()}",
        "classifiedOverlay": f"floorplan-classified-overlay{paths['classifiedOverlay'].suffix.lower()}",
        "traceCombinationImage": f"floorplan-trace-combination{paths['traceCombinationImage'].suffix.lower()}",
        "structureData": "structure-data.json",
        "traceComponents": "trace-components.json",
    }
    if "nativeLayout" in paths:
        target_names["nativeLayout"] = f"native-layout{paths['nativeLayout'].suffix.lower()}"
    target_names.update({
        f"evidenceOverlay_{key}": relative
        for key, relative in layered_overlay_paths.items()
    })
    artifact_manifest = {}
    for key, source in paths.items():
        target_name = target_names[key]
        target = artifacts_dir / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        artifact_manifest[key] = artifact_entry(target, target_name)
    shutil.rmtree(build_dir)

    report_manifest = {
        "sourceModelValidation": {
            "path": f"reports/{source_model_report.name}",
            "sha256": digest(source_model_report),
            "bytes": source_model_report.stat().st_size,
        }
    }
    manifest = {
        "schema": "interior.floorplan-handoff.v3",
        "floorplanId": floorplan_id,
        "producer": {
            "skill": "interior-floorplan-planning",
            "version": PRODUCER_VERSION,
        },
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifact_manifest,
        "reports": report_manifest,
        "sourceTraceRegistry": {
            "structureTraceIds": sorted(clean_ids),
            "componentTraceIds": sorted(component_ids),
            "sourceObjectCandidateIds": sorted(accepted_object_ids),
        },
        "layoutAuthority": layout_authority,
        "validation": {
            "sourceModel": True,
            "agentVisualReview": True,
        },
    }
    manifest["handoffDigestSha256"] = canonical_digest(manifest)
    manifest_path = output / "floorplan-handoff.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "handoff": str(manifest_path),
        "floorplanId": floorplan_id,
        "handoffDigestSha256": manifest["handoffDigestSha256"],
        "rooms": len(compiled_trace["spaces"]),
        "connections": len(compiled_trace["cleanStructure"].get("connections", [])),
        "artifacts": len(artifact_manifest),
        "reports": len(report_manifest),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
