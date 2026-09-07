#!/usr/bin/env python3
"""Render the four-quadrant floorplan contract from declared source-pixel vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from topology_compiler import compile_space_topology


COLORS = {
    "walls": (229, 41, 54, 255),
    "windows": (17, 111, 224, 255),
    "doors": (220, 145, 24, 255),
    "movableFurniture": (21, 148, 77, 255),
    "fixedFixtures": (126, 64, 184, 255),
    "other": (91, 101, 95, 255),
    "spaces": (255, 214, 10, 82),
    "spaceBoundary": (218, 159, 0, 255),
    "railing": (0, 148, 163, 255),
    "parapet": (0, 121, 107, 255),
    "open-edge": (216, 27, 96, 255),
    "full-height-glazing": (0, 120, 212, 255),
}
TRACE_ORDER = (
    "walls",
    "windows",
    "doors",
    "boundaryFeatures",
    "movableFurniture",
    "fixedFixtures",
    "other",
)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def draw_shape(draw: ImageDraw.ImageDraw, item: dict, color: tuple[int, ...]) -> None:
    kind = item.get("type")
    width = max(1, int(item.get("width", 2)))
    stroke_only = item.get("strokeOnly", True)
    if kind == "polygon":
        points = [tuple(point) for point in item["points"]]
        if stroke_only:
            draw.line(points + [points[0]], fill=color, width=width, joint="curve")
        else:
            draw.polygon(points, fill=color)
    elif kind == "ellipse":
        box = (item["x"], item["y"], item["x"] + item["w"], item["y"] + item["h"])
        draw.ellipse(box, outline=color, width=width)
    elif kind in {"line", "polyline"}:
        points = [tuple(point) for point in item["points"]]
        if item.get("closed"):
            points.append(points[0])
        draw.line(points, fill=color, width=width, joint=item.get("joint", "curve"))
    elif kind == "rect":
        box = (item["x"], item["y"], item["x"] + item["w"], item["y"] + item["h"])
        draw.rectangle(box, outline=color, width=width)
    else:
        raise ValueError(f"unsupported shape type: {kind}")
    for detail in item.get("details", []):
        if isinstance(detail, list):
            draw.line(
                [tuple(point) for point in detail],
                fill=color,
                width=width,
                joint="curve",
            )
        else:
            draw_shape(draw, detail, color)


def draw_layer(image: Image.Image, items: list[dict], color: tuple[int, ...]) -> None:
    draw = ImageDraw.Draw(image)
    for item in items:
        draw_shape(draw, item, color)


def draw_boundary_features(image: Image.Image, items: list[dict]) -> None:
    draw = ImageDraw.Draw(image)
    for item in items:
        points = [tuple(point) for point in item.get("points", item.get("segment", []))]
        if len(points) < 2:
            continue
        kind = item.get("kind", "open-edge")
        color = COLORS.get(kind, COLORS["open-edge"])
        width = max(2, int(item.get("width", 4)))
        if kind == "open-edge":
            start, end = points[0], points[-1]
            length = max(1.0, ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5)
            cursor = 0.0
            while cursor < length:
                stop = min(length, cursor + 8)
                a, b = cursor / length, stop / length
                draw.line(
                    (
                        round(start[0] + (end[0] - start[0]) * a),
                        round(start[1] + (end[1] - start[1]) * a),
                        round(start[0] + (end[0] - start[0]) * b),
                        round(start[1] + (end[1] - start[1]) * b),
                    ),
                    fill=color,
                    width=width,
                )
                cursor += 14
        else:
            draw.line(points, fill=color, width=width, joint="curve")


def render_source_evidence_overlay(
    evidence: dict,
    source: Image.Image,
    *,
    groups: set[str] | None = None,
    show_ids: bool = True,
) -> Image.Image:
    """Draw the exact candidate vectors that will later compile into walls."""
    groups = groups or {
        "walls",
        "openings",
        "boundaries",
        "labels",
        "dividers",
        "objects",
    }
    image = source.convert("RGBA").copy()
    overlay = Image.new("RGBA", source.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(13)
    line_width = max(2, round(max(source.size) / 700))
    colors = {
        "faceA": (229, 41, 54, 245),
        "faceB": (202, 36, 140, 245),
        "opening": (220, 145, 24, 245),
        "divider": (235, 184, 24, 245),
        "label": (33, 86, 154, 245),
        "object": (16, 132, 112, 245),
        "boundary": (0, 148, 163, 245),
    }

    def label_at(points: list[tuple[int, int]], text: str, color: tuple[int, ...]) -> None:
        if len(points) < 2:
            return
        x = round((points[0][0] + points[-1][0]) / 2)
        y = round((points[0][1] + points[-1][1]) / 2)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        label_width = box[2] - box[0]
        label_height = box[3] - box[1]
        x = max(2, min(source.width - label_width - 4, x - label_width // 2))
        y = max(2, min(source.height - label_height - 4, y + 4))
        draw.rectangle(
            (x - 2, y - 1, x + label_width + 2, y + label_height + 2),
            fill=(255, 255, 255, 220),
        )
        draw.text((x, y), text, fill=color, font=font)

    if "walls" in groups:
        for candidate in evidence.get("wallCandidates", []):
            face_a = candidate.get("faceA", [])
            for face_name in ("faceA", "faceB"):
                points = [tuple(point) for point in candidate.get(face_name, [])]
                if len(points) >= 2:
                    draw.line(points, fill=colors[face_name], width=line_width, joint="curve")
            if show_ids:
                label_at([tuple(point) for point in face_a], candidate["id"], colors["faceA"])
    if "openings" in groups:
        for opening in evidence.get("openingCandidates", []):
            points = [tuple(point) for point in opening.get("segment", [])]
            if len(points) >= 2:
                draw.line(points, fill=colors["opening"], width=line_width + 1, joint="curve")
                if show_ids:
                    label_at(points, opening["id"], colors["opening"])
    if "boundaries" in groups:
        for boundary in evidence.get("boundaryCandidates", []):
            points = [tuple(point) for point in boundary.get("segment", [])]
            if len(points) >= 2:
                draw.line(points, fill=colors["boundary"], width=line_width + 1)
                if show_ids:
                    label_at(points, boundary["id"], colors["boundary"])
    if "labels" in groups:
        for room_label in evidence.get("spaceLabelCandidates", []):
            point = room_label.get("point", [])
            if len(point) == 2:
                x, y = map(round, point)
                radius = max(3, line_width * 2)
                draw.ellipse(
                    (x - radius, y - radius, x + radius, y + radius),
                    outline=colors["label"],
                    width=line_width,
                )
                label_at(
                    [(x - 1, y), (x + 1, y)],
                    (
                        f"{room_label['id']}:{room_label.get('text', '')}"
                        if show_ids
                        else room_label.get("text", "")
                    ),
                    colors["label"],
                )
    if "objects" in groups:
        for candidate in evidence.get("objectCandidates", []):
            points = [tuple(point) for point in candidate.get("outline", [])]
            if len(points) >= 3:
                draw.line(
                    points + [points[0]],
                    fill=colors["object"],
                    width=line_width,
                    joint="curve",
                )
                for detail in candidate.get("details", []):
                    if len(detail) >= 2:
                        draw.line(
                            [tuple(point) for point in detail],
                            fill=colors["object"],
                            width=max(1, line_width - 1),
                            joint="curve",
                        )
                if show_ids:
                    label_at(points, candidate["id"], colors["object"])
    if "dividers" in groups:
        for divider in evidence.get("semanticDividerCandidates", []):
            points = [tuple(point) for point in divider.get("segment", [])]
            if len(points) >= 2:
                start, end = points
                length = max(1, round(((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5))
                for offset in range(0, length, max(8, line_width * 4)):
                    t0 = offset / length
                    t1 = min(1.0, (offset + max(4, line_width * 2)) / length)
                    dash = [
                        (
                            round(start[0] + (end[0] - start[0]) * t0),
                            round(start[1] + (end[1] - start[1]) * t0),
                        ),
                        (
                            round(start[0] + (end[0] - start[0]) * t1),
                            round(start[1] + (end[1] - start[1]) * t1),
                        ),
                    ]
                    draw.line(dash, fill=colors["divider"], width=line_width + 1)
                if show_ids:
                    label_at(points, divider["id"], colors["divider"])
    image.alpha_composite(overlay)
    return image


def render_traces(
    spec: dict,
    size: tuple[int, int],
    layers: tuple[str, ...],
    *,
    transparent: bool = False,
) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
    for layer in layers:
        if layer == "boundaryFeatures":
            draw_boundary_features(image, spec.get("layers", {}).get(layer, []))
        else:
            draw_layer(image, spec.get("layers", {}).get(layer, []), COLORS[layer])
    return image


def render_clean_structure(spec: dict, size: tuple[int, int]) -> Image.Image:
    clean = spec.get("cleanStructure")
    if not clean:
        raise ValueError("cleanStructure is required")
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    draw_layer(image, clean.get("walls", []), COLORS["walls"])
    draw_layer(image, clean.get("windows", []), COLORS["windows"])
    draw_boundary_features(image, clean.get("boundaryFeatures", []))
    return image


def draw_dashed_polygon(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: tuple[int, ...],
    width: int = 2,
    dash: int = 8,
    gap: int = 6,
) -> None:
    closed = points + [points[0]]
    for start, end in zip(closed, closed[1:]):
        x0, y0 = start
        x1, y1 = end
        length = max(1.0, ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
        cursor = 0.0
        while cursor < length:
            stop = min(length, cursor + dash)
            a = cursor / length
            b = stop / length
            draw.line(
                (
                    round(x0 + (x1 - x0) * a),
                    round(y0 + (y1 - y0) * a),
                    round(x0 + (x1 - x0) * b),
                    round(y0 + (y1 - y0) * b),
                ),
                fill=color,
                width=width,
            )
            cursor += dash + gap


def render_classified_overlay(spec: dict, source: Image.Image, all_traces: Image.Image) -> Image.Image:
    # Quadrant 2 is evidence, so the source pixels remain unchanged beneath overlays.
    classified = source.convert("RGBA").copy()
    spaces = Image.new("RGBA", source.size, (0, 0, 0, 0))
    space_draw = ImageDraw.Draw(spaces)
    for space in spec.get("spaces", []):
        points = [tuple(point) for point in space["polygon"]]
        space_draw.polygon(points, fill=COLORS["spaces"])
        draw_dashed_polygon(space_draw, points, COLORS["spaceBoundary"])
    classified.alpha_composite(spaces)
    classified.alpha_composite(all_traces)
    return classified


def render(
    spec: dict,
    wall_geometry: dict,
    source_evidence: dict,
    semantic_decisions: dict,
    source: Image.Image,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    topology = compile_space_topology(
        spec,
        (source.height, source.width),
        wall_geometry,
        source_evidence,
        semantic_decisions,
    )
    if topology["errors"]:
        raise ValueError(
            "room topology compilation failed:\n" + "\n".join(topology["errors"])
        )
    spec = topology["traceSpec"]
    size = source.size
    all_traces = render_traces(spec, size, TRACE_ORDER, transparent=True)
    classified = render_classified_overlay(spec, source, all_traces)

    structure = render_clean_structure(spec, size)
    composite = render_traces(
        spec,
        size,
        (
            "walls",
            "windows",
            "doors",
            "boundaryFeatures",
            "movableFurniture",
            "fixedFixtures",
        ),
    )
    return classified, structure, composite


def main() -> int:
    parser = argparse.ArgumentParser()
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--spec")
    source_group.add_argument("--evidence")
    parser.add_argument("--source")
    parser.add_argument("--native-layout")
    parser.add_argument("--geometry")
    parser.add_argument("--source-evidence")
    parser.add_argument("--decisions")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if args.evidence:
        evidence_path = Path(args.evidence).resolve()
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not args.source:
            raise ValueError("--source is required with --evidence")
        source = Image.open(Path(args.source).resolve()).convert("RGBA")
        layout_authority = evidence.get("layoutAuthority", {})
        native_layout = None
        if layout_authority.get("mode") == "native-layout-furnished":
            if not args.native_layout:
                raise ValueError(
                    "--native-layout is required for native-layout-furnished evidence"
                )
            native_layout = Image.open(Path(args.native_layout).resolve()).convert("RGBA")
            if native_layout.size != source.size:
                raise ValueError("native layout must use the source canvas size")
        aggregate_base = native_layout or source
        overlay = render_source_evidence_overlay(evidence, aggregate_base)
        output = out / "source-evidence-overlay.png"
        overlay.save(output)
        layered = {
            "walls-openings-overlay.png": (
                {"walls", "openings", "boundaries"},
                False,
            ),
            "walls-openings-overlay-review.png": (
                {"walls", "openings", "boundaries"},
                True,
            ),
            "room-labels-dividers-overlay.png": (
                {"labels", "dividers"},
                False,
            ),
            "room-labels-dividers-overlay-review.png": (
                {"labels", "dividers"},
                True,
            ),
            "objects-overlay.png": (
                {"objects"},
                False,
            ),
            "objects-overlay-review.png": (
                {"objects"},
                True,
            ),
        }
        for filename, (groups, show_ids) in layered.items():
            layer_base = native_layout if groups == {"objects"} and native_layout else source
            render_source_evidence_overlay(
                evidence,
                layer_base,
                groups=groups,
                show_ids=show_ids,
            ).save(out / filename)
        print(json.dumps({
            "outDir": str(out),
            "output": str(output),
            "layeredOutputs": sorted(layered),
            "wallCandidates": len(evidence.get("wallCandidates", [])),
            "mode": "source-evidence",
        }, ensure_ascii=False))
        return 0

    spec_path = Path(args.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not args.geometry or not args.source_evidence or not args.decisions:
        raise ValueError(
            "--geometry, --source-evidence and --decisions are required with --spec"
        )
    geometry_path = Path(args.geometry).resolve()
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    evidence_path = Path(args.source_evidence).resolve()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    decisions_path = Path(args.decisions).resolve()
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    source_path = Path(spec["sourceImage"])
    if not source_path.is_absolute():
        source_path = spec_path.parent / source_path
    source = Image.open(source_path).convert("RGBA")
    layout_authority = evidence.get("layoutAuthority", {})
    layout_source = source
    if layout_authority.get("mode") == "native-layout-furnished":
        if not args.native_layout:
            raise ValueError(
                "--native-layout is required when the furnishing authority is native-layout"
            )
        layout_source = Image.open(Path(args.native_layout).resolve()).convert("RGBA")
        if layout_source.size != source.size:
            raise ValueError("native layout must use the source canvas size")
    classified, structure, composite = render(
        spec,
        geometry,
        evidence,
        decisions,
        layout_source,
    )

    classified.save(out / "floorplan-classified-overlay.png")
    structure.save(out / "floorplan-structure-red-blue.png")
    composite.save(out / "floorplan-traced-composite.png")

    gap = 20
    title_height = 34
    width, height = source.size
    canvas = Image.new("RGB", (width * 2 + gap, (height + title_height) * 2 + gap), "#e9ecea")
    panels = (
        (source, "1 原始户型图"),
        (classified, "2 已确认平面布局与区域"),
        (structure, "3 红墙蓝窗框架"),
        (composite, "4 墙窗与绿紫对象纯描线"),
    )
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(16)
    for index, (panel, label) in enumerate(panels):
        x = (index % 2) * (width + gap)
        y = (index // 2) * (height + title_height + gap)
        draw.rectangle((x, y, x + width, y + title_height), fill="#17211c")
        draw.text((x + 12, y + 7), label, fill="white", font=title_font)
        canvas.paste(panel.convert("RGB"), (x, y + title_height))
    canvas.save(out / "floorplan-four-quadrants.png")
    print(json.dumps({
        "outDir": str(out),
        "size": source.size,
        "outputs": 4,
        "wallColor": "red",
        "windowColor": "blue",
        "quadrant4Spaces": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
