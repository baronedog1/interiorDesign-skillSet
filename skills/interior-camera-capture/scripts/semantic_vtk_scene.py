#!/usr/bin/env python3
"""Pure VTK scene adapter for Interior Camera Capture.

This module maps imported glTF actors to stable semantic IDs and renders RGB,
entity-ID, and depth buffers.  It never creates, ranks, selects, repairs, or
changes a camera pose.  Camera decision-making belongs exclusively to
``unified_camera_solver.py``.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment
import vtk
from vtk.util.numpy_support import vtk_to_numpy


@dataclass(frozen=True)
class CameraPose:
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    fov: float
    window_center: tuple[float, float] = (0.0, 0.0)


def point_segment_distance(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    px, pz = point
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    d2 = dx * dx + dz * dz
    t = 0.0 if d2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / d2))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


def projection_param(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    px, pz = point
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    d2 = dx * dx + dz * dz
    return 0.5 if d2 < 1e-12 else ((px - ax) * dx + (pz - az) * dz) / d2


def point_in_polygon(point: tuple[float, float], polygon: list[list[float]] | list[tuple[float, float]]) -> bool:
    x, z = point
    inside = False
    for i in range(len(polygon)):
        x1, z1 = polygon[i]
        x2, z2 = polygon[(i + 1) % len(polygon)]
        if (z1 > z) != (z2 > z):
            xi = (x2 - x1) * (z - z1) / (z2 - z1 + 1e-12) + x1
            if x < xi:
                inside = not inside
    return inside


def _safe_actor_bounds(actor: vtk.vtkActor) -> tuple[float, float, float, float, float, float]:
    bounds = actor.GetBounds()
    if bounds is None or len(bounds) != 6 or not all(math.isfinite(float(x)) for x in bounds):
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return tuple(float(x) for x in bounds)  # type: ignore[return-value]


class SemanticVTKScene:
    """Decision-free semantic renderer and low-resolution candidate evaluator."""

    def __init__(
        self,
        scene_path: str | Path,
        model: dict[str, Any],
        structure: dict[str, Any],
        native_geometry: dict[str, Any],
        size: tuple[int, int] = (400, 250),
        mode: str = "id",
    ) -> None:
        if mode not in {"id", "rgb"}:
            raise ValueError(f"Unsupported mode: {mode}")
        self.scene_path = Path(scene_path)
        self.model = model
        self.structure = structure
        self.native_geometry = native_geometry
        self.size = (int(size[0]), int(size[1]))
        self.mode = mode

        self.window = vtk.vtkRenderWindow()
        self.window.SetOffScreenRendering(1)
        self.window.SetSize(*self.size)
        self.window.SetMultiSamples(0)

        self.importer = vtk.vtkGLTFImporter()
        self.importer.SetFileName(str(self.scene_path))
        self.importer.SetRenderWindow(self.window)
        self.importer.Update()

        renderers = self.window.GetRenderers()
        renderers.InitTraversal()
        self.renderer = renderers.GetNextItem()
        if self.renderer is None:
            self.renderer = vtk.vtkRenderer()
            self.window.AddRenderer(self.renderer)

        actors_collection = self.renderer.GetActors()
        actors_collection.InitTraversal()
        self.actors: list[vtk.vtkActor] = [
            actors_collection.GetNextActor() for _ in range(actors_collection.GetNumberOfItems())
        ]

        self.actor_group: dict[int, str] = {}
        self.group_info: dict[str, dict[str, Any]] = {}
        self.group_code: dict[str, int] = {}
        self.code_group: dict[int, str] = {}
        self._map_groups()
        self._hidden_group_ids: frozenset[str] = frozenset()

        if self.mode == "id":
            self._configure_id_scene()
        else:
            self._configure_rgb_scene()

        self.rgb_filter = vtk.vtkWindowToImageFilter()
        self.rgb_filter.SetInput(self.window)
        self.rgb_filter.SetInputBufferTypeToRGB()
        self.rgb_filter.ReadFrontBufferOff()

        self.depth_filter = vtk.vtkWindowToImageFilter()
        self.depth_filter.SetInput(self.window)
        self.depth_filter.SetInputBufferTypeToZBuffer()
        self.depth_filter.ReadFrontBufferOff()

    @staticmethod
    def _entity_bbox(entity: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
        world = entity.get("world", {})
        center = world.get("center", {})
        dims = world.get("dimensionsMeters", {})
        x, y, z = float(center.get("x", 0)), float(center.get("y", 0)), float(center.get("z", 0))
        w = max(0.01, float(dims.get("width", 0.01)))
        h = max(0.01, float(dims.get("height", 0.01)))
        d = max(0.01, float(dims.get("depth", 0.01)))
        return (x - w / 2, x + w / 2, y - h / 2, y + h / 2, z - d / 2, z + d / 2)

    def _map_furniture(self) -> int:
        entities = [e for e in self.native_geometry.get("entities", []) if int(e.get("meshCount", 0)) > 0]
        slots: list[int] = []
        for entity_index, entity in enumerate(entities):
            slots.extend([entity_index] * int(entity["meshCount"]))
        furniture_actor_count = len(slots)
        if furniture_actor_count == 0:
            return 0
        if furniture_actor_count > len(self.actors):
            raise ValueError(
                f"Native furniture mesh count {furniture_actor_count} exceeds actor count {len(self.actors)}"
            )

        entity_boxes = [self._entity_bbox(e) for e in entities]
        cost = np.empty((furniture_actor_count, furniture_actor_count), dtype=np.float64)
        for actor_index, actor in enumerate(self.actors[:furniture_actor_count]):
            bounds = _safe_actor_bounds(actor)
            actor_center = (
                (bounds[0] + bounds[1]) / 2,
                (bounds[2] + bounds[3]) / 2,
                (bounds[4] + bounds[5]) / 2,
            )
            for slot_index, entity_index in enumerate(slots):
                entity = entities[entity_index]
                eb = entity_boxes[entity_index]
                dims = entity["world"]["dimensionsMeters"]
                scale = max(
                    float(dims.get("width", 0.05)),
                    float(dims.get("height", 0.05)),
                    float(dims.get("depth", 0.05)),
                    0.05,
                )
                outside = (
                    max(0.0, eb[0] - bounds[0])
                    + max(0.0, bounds[1] - eb[1])
                    + max(0.0, eb[2] - bounds[2])
                    + max(0.0, bounds[3] - eb[3])
                    + max(0.0, eb[4] - bounds[4])
                    + max(0.0, bounds[5] - eb[5])
                ) / scale
                center = entity["world"]["center"]
                distance = math.dist(
                    actor_center,
                    (float(center["x"]), float(center["y"]), float(center["z"])),
                ) / scale
                cost[actor_index, slot_index] = outside * 1000.0 + distance * distance

        row_indices, column_indices = linear_sum_assignment(cost)
        model_furniture = {str(x.get("id")): x for x in self.model.get("furniture", [])}
        for actor_index, slot_index in zip(row_indices, column_indices):
            entity = entities[slots[int(slot_index)]]
            group_id = str(entity["id"])
            self.actor_group[int(actor_index)] = group_id
            model_item = model_furniture.get(group_id, {})
            self.group_info[group_id] = {
                "id": group_id,
                "kind": "furniture",
                "name": model_item.get("name", group_id),
                "functionalClass": entity.get("functionalClass"),
                "roomIds": entity.get("roomIds", []),
                "world": entity.get("world", {}),
            }
        return furniture_actor_count

    def _opening_world(self, opening: dict[str, Any]) -> dict[str, Any] | None:
        walls = {str(w.get("id")): w for w in self.model.get("walls", [])}
        wall = walls.get(str(opening.get("wallId")))
        if not wall:
            return None
        ax, az = float(wall["a"]["x"]), float(wall["a"]["z"])
        bx, bz = float(wall["b"]["x"]), float(wall["b"]["z"])
        dx, dz = bx - ax, bz - az
        length = math.hypot(dx, dz) or 1.0
        ux, uz = dx / length, dz / length
        center_distance = float(opening.get("center", length / 2))
        cx, cz = ax + ux * center_distance, az + uz * center_distance
        bottom = float(opening.get("bottom", 0))
        height = float(opening.get("height", 2.1))
        width = float(opening.get("width", 0.8))
        return {
            "center": {"x": cx, "y": bottom + height / 2, "z": cz},
            "dimensionsMeters": {
                "width": width,
                "height": height,
                "depth": max(0.06, float(wall.get("thickness", 0.06))),
            },
            "rotationY": math.atan2(dz, dx),
            "wall": wall,
        }

    @staticmethod
    def _bbox_overlap_area_xz(
        bounds: tuple[float, float, float, float, float, float], polygon: list[list[float]]
    ) -> float:
        xs = [float(p[0]) for p in polygon]
        zs = [float(p[1]) for p in polygon]
        overlap_x = max(0.0, min(bounds[1], max(xs)) - max(bounds[0], min(xs)))
        overlap_z = max(0.0, min(bounds[5], max(zs)) - max(bounds[4], min(zs)))
        return overlap_x * overlap_z

    def _map_structure_actor(self, actor_index: int) -> str:
        actor = self.actors[actor_index]
        bounds = _safe_actor_bounds(actor)
        cx, cy, cz = (
            (bounds[0] + bounds[1]) / 2,
            (bounds[2] + bounds[3]) / 2,
            (bounds[4] + bounds[5]) / 2,
        )
        color = actor.GetProperty().GetColor()

        # Horizontal planes are floor or ceiling.
        if abs(bounds[2] - bounds[3]) < 1e-5:
            if cy > 2.0:
                group_id = "__ceiling__"
                self.group_info.setdefault(
                    group_id,
                    {"id": group_id, "kind": "ceiling", "name": "ceiling", "roomIds": [], "world": {}},
                )
                return group_id
            room_scores = []
            for room in self.structure.get("rooms", []):
                score = self._bbox_overlap_area_xz(bounds, room.get("polygon", []))
                room_scores.append((score, str(room.get("id")), room))
            _, room_id, room = max(room_scores, default=(0.0, "unknown", {}))
            group_id = f"__floor__:{room_id}"
            self.group_info.setdefault(
                group_id,
                {
                    "id": group_id,
                    "kind": "floor",
                    "name": f"{room.get('name', room_id)} floor",
                    "roomIds": [room_id],
                    "world": {},
                },
            )
            return group_id

        # Opening actors tend to differ in material color from the neutral wall.
        wall_gray_distance = math.sqrt(
            sum((float(color[k]) - (0.88, 0.88, 0.86)[k]) ** 2 for k in range(3))
        )
        opening_candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for opening in self.model.get("openings", []):
            opening_world = self._opening_world(opening)
            if not opening_world:
                continue
            center = opening_world["center"]
            dims = opening_world["dimensionsMeters"]
            wall = opening_world["wall"]
            distance_to_wall = point_segment_distance(
                (cx, cz),
                (float(wall["a"]["x"]), float(wall["a"]["z"])),
                (float(wall["b"]["x"]), float(wall["b"]["z"])),
            )
            along = math.hypot(cx - float(center["x"]), cz - float(center["z"])) / max(
                float(dims["width"]), 0.1
            )
            vertical = abs(cy - float(center["y"])) / max(float(dims["height"]), 0.1)
            if distance_to_wall < 0.15 and along < 0.9 and vertical < 0.75:
                opening_candidates.append((distance_to_wall * 5 + along + vertical, opening, opening_world))
        if opening_candidates and wall_gray_distance > 0.08:
            _, opening, opening_world = min(opening_candidates, key=lambda x: x[0])
            group_id = str(opening["id"])
            wall = opening_world["wall"]
            self.group_info.setdefault(
                group_id,
                {
                    "id": group_id,
                    "kind": "opening",
                    "name": opening.get("name", group_id),
                    "functionalClass": opening.get("type", "opening"),
                    "roomIds": wall.get("adjacentRoomIds", []),
                    "world": {k: v for k, v in opening_world.items() if k != "wall"},
                },
            )
            return group_id

        wall_candidates: list[tuple[float, dict[str, Any]]] = []
        for wall in self.model.get("walls", []):
            a = (float(wall["a"]["x"]), float(wall["a"]["z"]))
            b = (float(wall["b"]["x"]), float(wall["b"]["z"]))
            distance = point_segment_distance((cx, cz), a, b)
            parameter = projection_param((cx, cz), a, b)
            outside = max(0.0, -parameter, parameter - 1.0)
            wall_candidates.append((distance + outside * 3.0, wall))
        _, wall = min(wall_candidates, key=lambda x: x[0])
        group_id = str(wall["id"])
        length = math.hypot(
            float(wall["b"]["x"]) - float(wall["a"]["x"]),
            float(wall["b"]["z"]) - float(wall["a"]["z"]),
        )
        self.group_info.setdefault(
            group_id,
            {
                "id": group_id,
                "kind": "wall",
                "name": wall.get("name", group_id),
                "functionalClass": "wall",
                "roomIds": wall.get("adjacentRoomIds", []),
                "world": {
                    "center": {
                        "x": (float(wall["a"]["x"]) + float(wall["b"]["x"])) / 2,
                        "y": float(wall.get("height", 2.8)) / 2,
                        "z": (float(wall["a"]["z"]) + float(wall["b"]["z"])) / 2,
                    },
                    "dimensionsMeters": {
                        "width": length,
                        "height": float(wall.get("height", 2.8)),
                        "depth": float(wall.get("thickness", 0.06)),
                    },
                    "rotationY": math.atan2(
                        float(wall["b"]["z"]) - float(wall["a"]["z"]),
                        float(wall["b"]["x"]) - float(wall["a"]["x"]),
                    ),
                },
            },
        )
        return group_id

    def _map_groups(self) -> None:
        furniture_count = self._map_furniture()
        for actor_index in range(furniture_count, len(self.actors)):
            self.actor_group[actor_index] = self._map_structure_actor(actor_index)
        for code, group_id in enumerate(sorted(set(self.actor_group.values())), 1):
            self.group_code[group_id] = code
            self.code_group[code] = group_id

    @staticmethod
    def _code_color(code: int) -> tuple[float, float, float]:
        return ((code & 255) / 255.0, ((code >> 8) & 255) / 255.0, ((code >> 16) & 255) / 255.0)

    def _configure_id_scene(self) -> None:
        self.renderer.SetBackground(0.0, 0.0, 0.0)
        self.renderer.RemoveAllLights()
        for actor_index, actor in enumerate(self.actors):
            mapper = actor.GetMapper()
            if mapper is not None:
                mapper.ScalarVisibilityOff()
            prop = actor.GetProperty()
            prop.LightingOff()
            prop.SetInterpolationToFlat()
            prop.SetOpacity(1.0)
            prop.SetColor(*self._code_color(self.group_code[self.actor_group[actor_index]]))

    def _configure_rgb_scene(self) -> None:
        self.renderer.SetBackground(0.92, 0.93, 0.94)
        # Preserve imported lights if present; otherwise add a neutral rig.
        if self.renderer.GetLights().GetNumberOfItems() == 0:
            for position, intensity in [((2, 8, 2), 0.95), ((10, 8, 2), 0.65), ((5, 8, 11), 0.75)]:
                light = vtk.vtkLight()
                light.SetLightTypeToSceneLight()
                light.SetPosition(*position)
                light.SetFocalPoint(5, 0, 5)
                light.SetIntensity(intensity)
                self.renderer.AddLight(light)
            headlight = vtk.vtkLight()
            headlight.SetLightTypeToHeadlight()
            headlight.SetIntensity(0.85)
            self.renderer.AddLight(headlight)

    def set_hidden_groups(self, group_ids: Iterable[str] = ()) -> None:
        hidden = frozenset(str(value) for value in group_ids)
        if hidden == self._hidden_group_ids:
            return
        self._hidden_group_ids = hidden
        for actor_index, actor in enumerate(self.actors):
            actor.SetVisibility(self.actor_group.get(actor_index) not in hidden)

    def set_camera(self, pose: CameraPose) -> None:
        camera = vtk.vtkCamera()
        camera.SetPosition(*pose.position)
        camera.SetFocalPoint(*pose.target)
        camera.SetViewUp(0.0, 1.0, 0.0)
        camera.SetViewAngle(float(pose.fov))
        camera.SetWindowCenter(*pose.window_center)
        camera.SetClippingRange(0.035, 100.0)
        self.renderer.SetActiveCamera(camera)

    def render_id_depth(
        self, pose: CameraPose, hidden_group_ids: Iterable[str] = ()
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.mode != "id":
            raise RuntimeError("render_id_depth requires an ID scene")
        self.set_hidden_groups(hidden_group_ids)
        self.set_camera(pose)
        self.window.Render()
        self.rgb_filter.Modified()
        self.rgb_filter.Update()
        rgb = vtk_to_numpy(self.rgb_filter.GetOutput().GetPointData().GetScalars()).reshape(
            self.size[1], self.size[0], 3
        )
        rgb = np.flipud(rgb).astype(np.int32)
        codes = rgb[:, :, 0] + (rgb[:, :, 1] << 8) + (rgb[:, :, 2] << 16)
        self.depth_filter.Modified()
        self.depth_filter.Update()
        depth = vtk_to_numpy(self.depth_filter.GetOutput().GetPointData().GetScalars()).reshape(
            self.size[1], self.size[0]
        )
        return codes.copy(), np.flipud(depth).copy()

    def render_rgb_array(
        self, pose: CameraPose, hidden_group_ids: Iterable[str] = ()
    ) -> np.ndarray:
        if self.mode != "rgb":
            raise RuntimeError("render_rgb_array requires an RGB scene")
        self.set_hidden_groups(hidden_group_ids)
        self.set_camera(pose)
        self.window.Render()
        self.rgb_filter.Modified()
        self.rgb_filter.Update()
        rgb = vtk_to_numpy(self.rgb_filter.GetOutput().GetPointData().GetScalars()).reshape(
            self.size[1], self.size[0], 3
        )
        return np.flipud(rgb).copy()

    def project(self, world: tuple[float, float, float]) -> tuple[float, float, float]:
        self.renderer.SetWorldPoint(float(world[0]), float(world[1]), float(world[2]), 1.0)
        self.renderer.WorldToDisplay()
        x, y, z = self.renderer.GetDisplayPoint()
        return float(x), float(self.size[1] - 1 - y), float(z)

    def metric(self, codes: np.ndarray, group_id: str) -> dict[str, Any]:
        code = self.group_code.get(group_id)
        height, width = codes.shape
        if not code:
            return {"visible": False, "pixels": 0, "pixelRatio": 0.0, "bboxArea": 0.0, "bounds": None, "edge": False}
        ys, xs = np.where(codes == code)
        if len(xs) == 0:
            return {"visible": False, "pixels": 0, "pixelRatio": 0.0, "bboxArea": 0.0, "bounds": None, "edge": False}
        bounds = {
            "left": float(xs.min() / width),
            "top": float(ys.min() / height),
            "right": float((xs.max() + 1) / width),
            "bottom": float((ys.max() + 1) / height),
        }
        return {
            "visible": True,
            "pixels": int(len(xs)),
            "pixelRatio": float(len(xs) / (width * height)),
            "bboxArea": float((bounds["right"] - bounds["left"]) * (bounds["bottom"] - bounds["top"])),
            "bounds": bounds,
            "edge": bool(xs.min() <= 1 or ys.min() <= 1 or xs.max() >= width - 2 or ys.max() >= height - 2),
        }

    def union_metric(self, codes: np.ndarray, group_ids: Iterable[str]) -> dict[str, Any]:
        valid_codes = [self.group_code[g] for g in group_ids if g in self.group_code]
        height, width = codes.shape
        if not valid_codes:
            return {"visible": False, "pixels": 0, "pixelRatio": 0.0, "bboxArea": 0.0, "bounds": None, "edge": False}
        mask = np.isin(codes, valid_codes)
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return {"visible": False, "pixels": 0, "pixelRatio": 0.0, "bboxArea": 0.0, "bounds": None, "edge": False}
        bounds = {
            "left": float(xs.min() / width),
            "top": float(ys.min() / height),
            "right": float((xs.max() + 1) / width),
            "bottom": float((ys.max() + 1) / height),
        }
        return {
            "visible": True,
            "pixels": int(len(xs)),
            "pixelRatio": float(len(xs) / (width * height)),
            "bboxArea": float((bounds["right"] - bounds["left"]) * (bounds["bottom"] - bounds["top"])),
            "bounds": bounds,
            "edge": bool(xs.min() <= 1 or ys.min() <= 1 or xs.max() >= width - 2 or ys.max() >= height - 2),
        }

    def center_hit(self, codes: np.ndarray, world_center: tuple[float, float, float]) -> str | None:
        x, y, _ = self.project(world_center)
        ix, iy = int(round(x)), int(round(y))
        height, width = codes.shape
        values: list[int] = []
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                xx, yy = ix + dx, iy + dy
                if 0 <= xx < width and 0 <= yy < height:
                    code = int(codes[yy, xx])
                    if code:
                        values.append(code)
        if not values:
            return None
        code = Counter(values).most_common(1)[0][0]
        return self.code_group.get(code)

    def ratio_by_kind(self, codes: np.ndarray, kind: str) -> float:
        ids = [gid for gid, info in self.group_info.items() if info.get("kind") == kind]
        valid_codes = [self.group_code[x] for x in ids if x in self.group_code]
        if not valid_codes:
            return 0.0
        return float(np.isin(codes, valid_codes).mean())

    def visible_ratios(self, codes: np.ndarray, minimum: float = 0.0001) -> dict[str, float]:
        result: dict[str, float] = {}
        total = codes.size
        unique, counts = np.unique(codes, return_counts=True)
        for code, count in zip(unique, counts):
            if int(code) == 0:
                continue
            ratio = float(count / total)
            if ratio >= minimum:
                group_id = self.code_group.get(int(code))
                if group_id:
                    result[group_id] = ratio
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

    def save_id_png(self, codes: np.ndarray, path: str | Path) -> None:
        from PIL import Image

        rgb = np.empty((codes.shape[0], codes.shape[1], 3), dtype=np.uint8)
        rgb[:, :, 0] = (codes & 255).astype(np.uint8)
        rgb[:, :, 1] = ((codes >> 8) & 255).astype(np.uint8)
        rgb[:, :, 2] = ((codes >> 16) & 255).astype(np.uint8)
        Image.fromarray(rgb, mode="RGB").save(path)

    def close(self) -> None:
        self.window.Finalize()
