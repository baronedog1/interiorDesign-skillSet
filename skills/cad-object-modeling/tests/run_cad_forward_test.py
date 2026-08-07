#!/usr/bin/env python3
"""Run one asymmetric sofa through STEP, projection, mirror rejection, and packaging."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = TEST_ROOT.parent
SCRIPTS = SKILL_ROOT / "scripts"
ASSETS = SKILL_ROOT / "assets"
sys.path.insert(0, str(TEST_ROOT))

from test_contract_pipeline import ContractPipelineTest, sha256, write_json  # noqa: E402


CAD_PYTHON = Path(
    os.environ.get(
        "CAD_PYTHON",
        "/home/agentops/.local/share/codex-cad-runtime/bin/python",
    )
)
CAD_SKILL_ROOT = Path(
    os.environ.get("CAD_SKILL_ROOT", "/home/agentops/.codex/skills/cad-zh")
)


def run(command: list[str], cwd: Path, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != expected:
        raise RuntimeError(
            f"command returned {result.returncode}, expected {expected}: {' '.join(command)}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def main() -> int:
    if not CAD_PYTHON.is_file() or not (CAD_SKILL_ROOT / "scripts" / "step").exists():
        print("CAD runtime or cad-zh is unavailable", file=sys.stderr)
        return 1
    fixture = ContractPipelineTest(methodName="test_grade_a_boundaries_coordinates_and_timing_pass")
    fixture.setUp()
    project = fixture.project
    try:
        shutil.copy2(ASSETS / "cad-object-generator.py", project / "cad-object-generator.py")
        run(
            [
                str(CAD_PYTHON),
                str(CAD_SKILL_ROOT / "scripts" / "step"),
                "cad-object-generator.py",
                "-o",
                "asymmetric-sofa.step",
                "--glb",
                "asymmetric-sofa.glb",
            ],
            project,
        )
        step_path = project / "asymmetric-sofa.step"
        if not step_path.is_file() or step_path.stat().st_size <= 0:
            raise RuntimeError("STEP was not generated")

        inspect_result = run(
            [
                str(CAD_PYTHON),
                str(CAD_SKILL_ROOT / "scripts" / "inspect"),
                "refs",
                "asymmetric-sofa.step",
                "--facts",
                "--planes",
                "--positioning",
            ],
            project,
        )
        (project / "inspect-facts.txt").write_text(
            inspect_result.stdout + inspect_result.stderr,
            encoding="utf-8",
        )

        projection_targets = [
            {
                "targetId": "top",
                "viewId": "top",
                "required": True,
                "sourceSize": {"width": 220, "height": 180},
                "evidenceMask": "source-materials/top.png",
                "cadToSource": [[0.1, 0, 0, 110], [0, -0.1, 0, 90]],
                "maxXorPixels": 0,
                "maxXorRatio": 0,
                "maxBBoxDeltaPx": 0,
                "maxCentroidDeltaPx": 0.5,
            },
            {
                "targetId": "front",
                "viewId": "front",
                "required": True,
                "sourceSize": {"width": 220, "height": 180},
                "evidenceMask": "source-materials/front.png",
                "cadToSource": [[0.1, 0, 0, 110], [0, 0, -0.1, 160]],
                "maxXorPixels": 0,
                "maxXorRatio": 0,
                "maxBBoxDeltaPx": 0,
                "maxCentroidDeltaPx": 0.5,
            },
            {
                "targetId": "side",
                "viewId": "side",
                "required": True,
                "sourceSize": {"width": 220, "height": 180},
                "evidenceMask": "source-materials/side.png",
                "cadToSource": [[0, 0.1, 0, 90], [0, 0, -0.1, 160]],
                "maxXorPixels": 0,
                "maxXorRatio": 0,
                "maxBBoxDeltaPx": 0,
                "maxCentroidDeltaPx": 0.5,
            },
        ]
        projection_job = {
            "schema": "interior.cad-object-projection-job.v1",
            "objectId": "asymmetric-sofa-test",
            "projectRoot": ".",
            "step": "asymmetric-sofa.step",
            "stepSha256": sha256(step_path),
            "meshToleranceMm": 0.2,
            "meshAngularTolerance": 0.08,
            "supersample": 1,
            "targets": projection_targets,
        }
        write_json(project / "projection-job.json", projection_job)
        run(
            [str(CAD_PYTHON), str(SCRIPTS / "compare_step_projection.py"), "projection-job.json", "projection-report.json"],
            project,
        )
        projection_report = json.loads((project / "projection-report.json").read_text())
        if not projection_report["overallPassed"]:
            raise RuntimeError("Correct asymmetric STEP failed projection")

        mirrored = json.loads(json.dumps(projection_job))
        mirrored["targets"][0]["cadToSource"] = [[-0.1, 0, 0, 110], [0, -0.1, 0, 90]]
        write_json(project / "mirrored-projection-job.json", mirrored)
        run(
            [str(CAD_PYTHON), str(SCRIPTS / "compare_step_projection.py"), "mirrored-projection-job.json", "mirrored-projection-report.json"],
            project,
            expected=1,
        )
        mirror_report = json.loads((project / "mirrored-projection-report.json").read_text())
        if mirror_report["overallPassed"] or mirror_report["targets"][0]["metrics"]["xorPixels"] <= 0:
            raise RuntimeError("Mirror gate did not reject a flipped asymmetric projection")

        run(
            [
                str(CAD_PYTHON),
                str(CAD_SKILL_ROOT / "scripts" / "snapshot"),
                "--input",
                "asymmetric-sofa.step",
                "--output",
                str(project / "asymmetric-sofa-iso.png"),
                "--camera",
                "iso",
                "--view-labels",
            ],
            project,
        )
        snapshots = sorted(project.glob("asymmetric-sofa-iso_*.png"))
        if not snapshots:
            raise RuntimeError("CAD snapshot was not generated")
        snapshot = snapshots[-1]

        run(
            [sys.executable, str(SCRIPTS / "validate_coordinate_contract.py"), "cad-object-plan.json", "coordinate-report.json"],
            project,
        )
        validation_job = {
            "schema": "interior.cad-object-validation-job.v1",
            "objectId": "asymmetric-sofa-test",
            "projectRoot": ".",
            "sourceInventory": "source-inventory.json",
            "viewEvidence": ["view-evidence.json"],
            "plan": "cad-object-plan.json",
            "coordinateReport": "coordinate-report.json",
            "generator": "cad-object-generator.py",
            "step": "asymmetric-sofa.step",
            "inspection": {
                "commands": ["cad-zh scripts/inspect refs asymmetric-sofa.step --facts --planes --positioning"],
                "factsArtifacts": ["inspect-facts.txt"],
                "factsSummary": "Two valid labeled solids; overall bounds 1800 x 1200 x 300 mm.",
                "solidCount": 2,
                "validSolidCount": 2,
                "dimensionChecks": [
                    {"checkId": "overall-x", "expectedMm": 1800, "actualMm": 1800, "passed": True},
                    {"checkId": "overall-y", "expectedMm": 1200, "actualMm": 1200, "passed": True},
                    {"checkId": "overall-z", "expectedMm": 300, "actualMm": 300, "passed": True},
                ],
                "componentLabelChecks": [
                    {"checkId": "label-base", "componentId": "base", "passed": True},
                    {"checkId": "label-chaise", "componentId": "chaise", "passed": True},
                ],
                "relationshipChecks": [
                    {"checkId": "contact", "relationshipId": "base-chaise-contact", "passed": True}
                ],
            },
            "projectionReports": ["projection-report.json"],
            "snapshots": [
                {"path": snapshot.name, "reviewed": True, "reviewNote": "Asymmetric right chaise and two-component contact are visually correct."}
            ],
            "viewerHandoff": {"status": "unavailable", "url": None, "reason": "Integration test does not start a persistent review server."},
            "limitations": [],
        }
        write_json(project / "validation-job.json", validation_job)
        run(
            [sys.executable, str(SCRIPTS / "build_validation.py"), "validation-job.json", "validation.json"],
            project,
        )

        timing_job = {
            "schema": "interior.cad-object-timing-events.v1",
            "taskId": "forward-test",
            "stages": [
                {"stageId": "evidence", "name": "Evidence", "startedAt": "2026-08-01T10:00:00+08:00", "endedAt": "2026-08-01T10:00:01+08:00", "activities": ["freeze and segment"]},
                {"stageId": "cad", "name": "CAD", "startedAt": "2026-08-01T10:00:01+08:00", "endedAt": "2026-08-01T10:00:03+08:00", "activities": ["generate and inspect STEP"]},
                {"stageId": "qa", "name": "QA", "startedAt": "2026-08-01T10:00:03+08:00", "endedAt": "2026-08-01T10:00:05+08:00", "activities": ["projection, snapshot, package"]},
            ],
        }
        write_json(project / "timing-events.json", timing_job)
        run([sys.executable, str(SCRIPTS / "build_stage_timing.py"), "timing-events.json", "stage-timing.json"], project)
        package_job = {
            "schema": "interior.cad-object-package-job.v1",
            "objectId": "asymmetric-sofa-test",
            "projectRoot": ".",
            "sourceInventory": "source-inventory.json",
            "viewEvidence": ["view-evidence.json"],
            "plan": "cad-object-plan.json",
            "generator": "cad-object-generator.py",
            "step": "asymmetric-sofa.step",
            "secondaryArtifacts": ["asymmetric-sofa.glb", snapshot.name, "projection-report.json"],
            "validation": "validation.json",
            "timing": "stage-timing.json",
            "allowProvisional": False,
        }
        write_json(project / "package-job.json", package_job)
        run(
            [sys.executable, str(SCRIPTS / "build_cad_object_package.py"), "package-job.json", "cad-object-package.json"],
            project,
        )
        package = json.loads((project / "cad-object-package.json").read_text())
        if package["status"] != "accepted":
            raise RuntimeError(f"Expected accepted package, got {package['status']}")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "stepBytes": step_path.stat().st_size,
                    "projectionXorPixels": {target["targetId"]: target["metrics"]["xorPixels"] for target in projection_report["targets"]},
                    "mirroredTopXorPixels": mirror_report["targets"][0]["metrics"]["xorPixels"],
                    "packageStatus": package["status"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(f"CAD forward test failed: {exc}", file=sys.stderr)
        return 1
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    raise SystemExit(main())
