#!/usr/bin/env python3
"""Forward and failure tests for the non-CAD contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_matrix(matrix: list[list[float]], point: list[float]) -> list[float]:
    vector = [point[0], point[1], 1.0]
    return [sum(matrix[row][column] * vector[column] for column in range(3)) for row in range(2)]


class ContractPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cad-object-contract-")
        self.project = Path(self.temp.name)
        (self.project / "source-materials").mkdir()
        self._make_source_images()
        self._write_source_job()
        self.run_script("freeze_sources.py", "source-job.json", "source-inventory.json")
        self.run_script("validate_source_inventory.py", "source-inventory.json")
        self._write_boundary_job()
        self.run_script("build_view_evidence.py", "boundary-job.json", "view-evidence.json")
        self._write_plan_draft()
        self.run_script(
            "finalize_cad_object_plan.py",
            "cad-object-plan.draft.json",
            "cad-object-plan.json",
            "--project-root",
            ".",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, script: str, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *arguments],
            cwd=self.project,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected,
            msg=f"{script} returned {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        return result

    def _draw(self, path: Path, rectangles: list[tuple[int, int, int, int]]) -> None:
        image = Image.new("L", (220, 180), 0)
        draw = ImageDraw.Draw(image)
        for rectangle in rectangles:
            draw.rectangle(rectangle, fill=255)
        image.save(path)

    def _make_source_images(self) -> None:
        self._draw(self.project / "source-materials" / "top.png", [(20, 50, 139, 130), (140, 40, 200, 160)])
        self._draw(self.project / "source-materials" / "front.png", [(20, 130, 139, 160), (140, 130, 200, 160)])
        self._draw(self.project / "source-materials" / "side.png", [(20, 130, 140, 160)])

    def _write_source_job(self) -> None:
        sources = []
        definitions = [
            ("source-top", "top", "z", "+x", "+y"),
            ("source-front", "front", "y", "+x", "+z"),
            ("source-side", "side", "x", "+y", "+z"),
        ]
        for source_id, view_id, normal, right, up in definitions:
            sources.append(
                {
                    "sourceId": source_id,
                    "path": f"source-materials/{view_id}.png",
                    "kind": "image",
                    "role": "primary" if view_id == "top" else "supporting",
                    "view": {
                        "viewId": view_id,
                        "projection": "orthographic",
                        "normalAxis": normal,
                        "screenRight": right,
                        "screenUp": up,
                    },
                    "calibration": {
                        "status": "calibrated",
                        "pixelsPerMillimeter": 0.1,
                        "basis": "explicit overall dimensions",
                    },
                }
            )
        dimensions = [
            {"dimensionId": "overall-x", "axis": "x", "value": 1800, "sourceId": "source-front", "confidence": "explicit"},
            {"dimensionId": "overall-y", "axis": "y", "value": 1200, "sourceId": "source-top", "confidence": "explicit"},
            {"dimensionId": "overall-z", "axis": "z", "value": 300, "sourceId": "source-side", "confidence": "explicit"},
        ]
        write_json(
            self.project / "source-job.json",
            {
                "schema": "interior.cad-object-source-job.v1",
                "objectId": "asymmetric-sofa-test",
                "projectRoot": ".",
                "units": "mm",
                "sources": sources,
                "dimensionFacts": dimensions,
            },
        )

    def _write_boundary_job(self) -> None:
        rectangle = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        views = [
            {
                "viewId": "top",
                "sourceId": "source-top",
                "foregroundMask": "source-materials/top.png",
                "components": [
                    {"componentId": "base", "boundaryRings": [rectangle(20, 50, 139, 130)], "holeRings": []},
                    {"componentId": "chaise", "boundaryRings": [rectangle(140, 40, 200, 160)], "holeRings": []},
                ],
            },
            {
                "viewId": "front",
                "sourceId": "source-front",
                "foregroundMask": "source-materials/front.png",
                "components": [
                    {"componentId": "base", "boundaryRings": [rectangle(20, 130, 139, 160)], "holeRings": []},
                    {"componentId": "chaise", "boundaryRings": [rectangle(140, 130, 200, 160)], "holeRings": []},
                ],
            },
            {
                "viewId": "side",
                "sourceId": "source-side",
                "foregroundMask": "source-materials/side.png",
                "components": [
                    {"componentId": "chaise", "boundaryRings": [rectangle(20, 130, 140, 160)], "holeRings": []}
                ],
            },
        ]
        write_json(
            self.project / "boundary-job.json",
            {
                "schema": "interior.cad-object-boundary-job.v1",
                "objectId": "asymmetric-sofa-test",
                "projectRoot": ".",
                "sourceInventory": "source-inventory.json",
                "sourceInventorySha256": sha256(self.project / "source-inventory.json"),
                "views": views,
            },
        )

    def _transform(self, view_id: str, forward: list[list[float]], inverse: list[list[float]], axes: list[str]) -> dict:
        source_points = [[0, 0], [219, 0], [0, 179], [219, 179], [110, 90]]
        return {
            "viewId": view_id,
            "sourceSize": {"width": 220, "height": 180},
            "planeAxes": axes,
            "sourceToPlane": forward,
            "planeToSource": inverse,
            "controlPoints": [
                {"source": point, "plane": apply_matrix(forward, point)} for point in source_points
            ],
            "maxSourceRoundTripErrorPx": 0.000001,
            "maxPlaneErrorMm": 0.000001,
        }

    def _write_plan_draft(self) -> None:
        transforms = [
            self._transform("top", [[10, 0, -1100], [0, -10, 900], [0, 0, 1]], [[0.1, 0, 110], [0, -0.1, 90], [0, 0, 1]], ["+x", "+y"]),
            self._transform("front", [[10, 0, -1100], [0, -10, 1600], [0, 0, 1]], [[0.1, 0, 110], [0, -0.1, 160], [0, 0, 1]], ["+x", "+z"]),
            self._transform("side", [[10, 0, -900], [0, -10, 1600], [0, 0, 1]], [[0.1, 0, 90], [0, -0.1, 160], [0, 0, 1]], ["+y", "+z"]),
        ]
        plan = {
            "schema": "interior.cad-object-plan.v1",
            "objectId": "asymmetric-sofa-test",
            "units": "mm",
            "sourceInventory": {"path": "source-inventory.json", "sha256": sha256(self.project / "source-inventory.json")},
            "viewEvidence": [{"path": "view-evidence.json", "sha256": sha256(self.project / "view-evidence.json")}],
            "coordinateFrame": {"handedness": "right", "x": "+right", "y": "+back", "z": "+up", "origin": "footprint center at floor"},
            "overallDimensions": {"x": 1800, "y": 1200, "z": 300},
            "parameterFacts": [
                {"parameterId": "overall-x", "value": 1800, "unit": "mm", "provenance": "source-backed", "evidenceIds": ["overall-x"]},
                {"parameterId": "overall-y", "value": 1200, "unit": "mm", "provenance": "source-backed", "evidenceIds": ["overall-y"]},
                {"parameterId": "overall-z", "value": 300, "unit": "mm", "provenance": "source-backed", "evidenceIds": ["overall-z"]},
            ],
            "viewTransforms": transforms,
            "orientationChecks": [{"landmarkId": "right-chaise", "viewId": "top", "expectedCadSide": "+x", "evaluatedCadSide": "+x", "evidenceId": "top:chaise"}],
            "components": [
                {"componentId": "base", "label": "Base", "role": "seat", "geometry": {"primitive": "box", "size": [1200, 800, 300]}, "transform": {"translation": [-300, 0, 0], "rotationDegXYZ": [0, 0, 0]}, "sourceEvidenceIds": ["top:base", "front:base"]},
                {"componentId": "chaise", "label": "Chaise", "role": "seat", "geometry": {"primitive": "box", "size": [600, 1200, 300]}, "transform": {"translation": [600, -100, 0], "rotationDegXYZ": [0, 0, 0]}, "sourceEvidenceIds": ["top:chaise", "front:chaise", "side:chaise"]},
            ],
            "relationships": [{"relationshipId": "base-chaise-contact", "type": "contact", "components": ["base", "chaise"], "parameters": {"axis": "x", "gapMm": 0}}],
            "projectionTargets": [
                {"viewId": view, "evidenceId": f"{view}:union", "required": True, "maxXorPixels": 0, "maxXorRatio": 0, "maxBBoxDeltaPx": 0, "maxCentroidDeltaPx": 0.5}
                for view in ("top", "front", "side")
            ],
            "assumptions": [],
            "planHash": "",
        }
        write_json(self.project / "cad-object-plan.draft.json", plan)

    def test_grade_a_boundaries_coordinates_and_timing_pass(self) -> None:
        inventory = json.loads((self.project / "source-inventory.json").read_text())
        self.assertEqual(inventory["inputGrade"], "A")
        evidence = json.loads((self.project / "view-evidence.json").read_text())
        self.assertTrue(evidence["overallPassed"])
        self.run_script("validate_coordinate_contract.py", "cad-object-plan.json", "coordinate-report.json")
        timing_job = {
            "schema": "interior.cad-object-timing-events.v1",
            "taskId": "test-task",
            "stages": [
                {"stageId": "evidence", "name": "Evidence", "startedAt": "2026-08-01T10:00:00+08:00", "endedAt": "2026-08-01T10:00:02+08:00", "activities": ["freeze and segment"]},
                {"stageId": "cad", "name": "CAD", "startedAt": "2026-08-01T10:00:03+08:00", "endedAt": "2026-08-01T10:00:08+08:00", "activities": ["generate STEP"]},
                {"stageId": "qa", "name": "QA", "startedAt": "2026-08-01T10:00:09+08:00", "endedAt": "2026-08-01T10:00:12+08:00", "activities": ["projection and snapshot"]},
            ],
        }
        write_json(self.project / "timing-events.json", timing_job)
        self.run_script("build_stage_timing.py", "timing-events.json", "stage-timing.json")
        timing = json.loads((self.project / "stage-timing.json").read_text())
        self.assertEqual(timing["totalDurationMs"], 10_000)
        self.assertEqual(sum(stage["durationMs"] for stage in timing["stages"]), timing["totalDurationMs"])

    def test_changed_source_is_rejected(self) -> None:
        path = self.project / "source-materials" / "top.png"
        image = Image.open(path).convert("L")
        image.putpixel((0, 0), 255)
        image.save(path)
        self.run_script("validate_source_inventory.py", "source-inventory.json", expected=1)

    def test_overlapping_component_regions_are_rejected(self) -> None:
        job = json.loads((self.project / "boundary-job.json").read_text())
        top = job["views"][0]
        top["components"][0]["boundaryRings"][0][1][0] = 140
        top["components"][0]["boundaryRings"][0][2][0] = 140
        write_json(self.project / "overlap-boundary-job.json", job)
        self.run_script("build_view_evidence.py", "overlap-boundary-job.json", "overlap-evidence.json", expected=1)
        report = json.loads((self.project / "overlap-evidence.json").read_text())
        self.assertGreater(report["views"][0]["gates"]["overlapPixels"], 0)

    def test_mirrored_landmark_is_rejected(self) -> None:
        draft = json.loads((self.project / "cad-object-plan.draft.json").read_text())
        draft["orientationChecks"][0]["evaluatedCadSide"] = "-x"
        write_json(self.project / "mirrored-plan.draft.json", draft)
        self.run_script(
            "finalize_cad_object_plan.py",
            "mirrored-plan.draft.json",
            "mirrored-plan.json",
            "--project-root",
            ".",
        )
        self.run_script("validate_coordinate_contract.py", "mirrored-plan.json", "mirrored-coordinate-report.json", expected=1)
        report = json.loads((self.project / "mirrored-coordinate-report.json").read_text())
        self.assertFalse(report["overallPassed"])


if __name__ == "__main__":
    unittest.main()
