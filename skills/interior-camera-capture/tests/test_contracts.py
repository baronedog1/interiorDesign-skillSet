from __future__ import annotations

import importlib.util
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("solver", SCRIPTS / "unified_camera_solver.py")
solver = importlib.util.module_from_spec(spec)
sys.modules["solver"] = solver
assert spec.loader is not None
spec.loader.exec_module(solver)


class Contracts(unittest.TestCase):
    def test_method_and_version(self) -> None:
        self.assertEqual(solver.METHOD, "source-intent-fixture-facing-frontal-camera-v6")
        self.assertEqual(solver.VERSION, "47.0.1")

    def test_user_camera_axis_is_signed_and_overrides_default_family(self) -> None:
        shot = {"userCameraIntent": {"desiredOpticalAxisXZ": [0, -1]}}
        requested = solver.requested_camera_axis(shot)
        self.assertEqual(requested, (0.0, -1.0))
        self.assertTrue(solver.matches_requested_camera_axis((0.0, -1.0), requested))
        self.assertFalse(solver.matches_requested_camera_axis((0.0, 1.0), requested))
        self.assertFalse(solver.matches_requested_camera_axis((1.0, 0.0), requested))

    def test_obsolete_scene_map_intermediate_is_absent(self) -> None:
        for name in ("build_shot_scene_map.py", "validate_shot_scene_map.py", "view_visibility.py"):
            self.assertFalse((ROOT / "scripts" / name).exists())
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("camera-image-facts.v3 + 同名 PNG", skill)
        self.assertNotIn("继续生成 accepted `shot-scene-map.v10`", skill)

    def test_wall_backed_fixture_has_signed_front_camera_direction(self) -> None:
        polygon = [(0.0, 0.0), (2.0, 0.0), (2.0, 3.0), (0.0, 3.0)]
        washer = solver.Box("washer", "washing-machine", "balcony", 0.25, 0.45, 1.5, 0.6, 0.9, 0.6, 0)
        directions = solver.preferred_fixture_forwards("balcony", [washer], polygon)
        self.assertEqual(len(directions), 1)
        self.assertAlmostEqual(directions[0][0], -1.0)
        self.assertAlmostEqual(directions[0][1], 0.0)

    def test_front_facing_nonoverlap_fixture_view_wins(self) -> None:
        wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "w", 1)

        def candidate(facade: float, overlap: float, score: float) -> solver.Candidate:
            return solver.Candidate(
                room_id="bath", room_name="卫生间", room_kind="bathroom", mode="strict-wall-frontal",
                target_wall=wall, position=(1, 1.42, 1), forward=wall.optical_axis, fov=90,
                window_center=(0, 0), placement_tier="floor-standing", primary_ids=["toilet", "vanity"],
                companion_ids=[], framing_ids=["toilet", "vanity"], primary_center=(1, 0.5, 0),
                front_score=1, semantic_axis_alignment=0, semantic_axis_required=False,
                wall_alignment_error_degrees=0, analytic_score=score,
                analytic={"perspectiveDepthRatio": 2, "primaryCompleteFit": True,
                          "fixtureFacadeAxisCount": 2, "fixtureFacadeAlignment": facade,
                          "lateralOffsetMeters": 0, "primaryNearDepthMeters": 1.4},
                camera_inside_target_room=True, quality_preferred=True, final_score=score,
                pixel={"primary": {"bboxArea": 0.2}, "frontalUsable": True, "centerFirstHitPass": True,
                       "fixtureFacadeAlignment": facade, "primaryFixtureMaxOverlap": overlap,
                       "foregroundFurnitureRatio": 0, "foregroundWallRatio": 0,
                       "foregroundOpeningRatio": 0, "targetCropForeignRatio": 0,
                       "pixelBlankBorder": 0.2, "qualityAdvisories": []},
            )

        good = candidate(1.0, 0.0, 1)
        back = candidate(-1.0, 0.0, 10000)
        overlapping = candidate(1.0, 0.7, 10000)
        selected, _ = solver.select_views([back, overlapping, good], 1)
        self.assertEqual(selected, [good])

    def test_old_camera_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            solver.reject_camera_facts({"shots": [{"roomId": "x", "position": [0, 1, 0]}]})
        with self.assertRaises(ValueError):
            solver.reject_camera_facts({"shots": [{"roomId": "x", "projectionCrop": {"left": 0.1}}]})

    def test_unknown_does_not_default_to_study(self) -> None:
        self.assertEqual(
            solver.classify_room(
                {"roomId": "mystery", "roomName": "未命名空间"}, [], {"spaceType": "unknown"}
            ),
            "unknown",
        )

    def test_strict_wall_axis_is_exact_normal(self) -> None:
        wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "w", 0)
        self.assertEqual(wall.optical_axis, (0, -1))

    def test_kitchen_uses_one_coherent_work_run(self) -> None:
        def box(identifier: str, functional_class: str, x: float, z: float) -> solver.Box:
            return solver.Box(identifier, functional_class, "k", x, 0.5, z, 0.6, 0.9, 0.6, 0)

        boxes = [
            box("cabinet-a", "base-cabinet", 0.0, 0.0),
            box("cabinet-b", "base-cabinet", 1.0, 0.0),
            box("sink", "sink-base-cabinet", 0.2, 0.1),
            box("cooktop", "cooktop", 0.8, 0.1),
            box("fridge", "refrigerator", 2.0, 0.0),
        ]
        primary, companions = solver.select_subject_group("kitchen", boxes)
        self.assertIn("sink", primary)
        self.assertIn("cooktop", primary)
        self.assertTrue(any(value.startswith("cabinet-") for value in primary))
        self.assertIn("fridge", companions)

    def test_envelope_profile_biases_top_and_adapts_to_slenderness(self) -> None:
        normal = solver.space_envelope_profile("bedroom", 1.0)
        slender = solver.space_envelope_profile("bedroom", 2.8)
        self.assertGreater(normal["ceilingTarget"], normal["floorTarget"])
        self.assertGreater(slender["ceilingTarget"], normal["ceilingTarget"])
        self.assertGreaterEqual(slender["ceilingMin"], normal["ceilingMin"])

    def test_bedroom_frames_bedside_objects_before_wardrobe(self) -> None:
        def box(identifier: str, functional_class: str, x: float) -> solver.Box:
            return solver.Box(identifier, functional_class, "bedroom", x, 0.3, 0, 0.5, 0.6, 0.5, 0)

        bed = box("bed", "double-bed", 0)
        companions = [
            box("wardrobe", "wardrobe", 0.1),
            box("left", "side-table", 0.6),
            box("right", "nightstand", -0.6),
        ]
        selected = solver.select_framing_companions("bedroom", [bed], companions)
        self.assertEqual(set(selected), {"left", "right"})

    def test_projected_span_is_orientation_aware(self) -> None:
        polygon = [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (0.0, 1.0)]
        self.assertAlmostEqual(solver.projected_span(polygon, (1.0, 0.0)), 4.0)
        self.assertAlmostEqual(solver.projected_span(polygon, (0.0, 1.0)), 1.0)

    def test_only_strict_frontal_candidate_family_exists(self) -> None:
        source = (SCRIPTS / "unified_camera_solver.py").read_text(encoding="utf-8")
        lowered = source.lower()
        for token in ("fallback", "best-effort", "bounded-oblique", "include_oblique"):
            self.assertNotIn(token, lowered)

    def test_only_unified_solver_owns_camera_decisions(self) -> None:
        decision_names = {
            "select_subject_group",
            "preferred_optical_axes",
            "generate_candidates",
            "evaluate_candidate",
            "select_views",
            "apply_native_html_repairs",
        }
        owners = []
        for path in SCRIPTS.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
            if names & decision_names:
                owners.append(path.name)
        self.assertEqual(owners, ["unified_camera_solver.py"])

    def test_scene_generator_has_one_live_html_input(self) -> None:
        source = (SCRIPTS / "generate_vtk_camera_scene.py").read_text(encoding="utf-8")
        self.assertIn("export_html_camera_scene.mjs", source)
        self.assertIn('"placementWorld"', source)
        self.assertNotIn("proxy", source.lower())
        self.assertNotIn("fallback", source.lower())

    def test_natural_external_view_and_target_space_crop_are_one_solver_policy(self) -> None:
        source = (SCRIPTS / "unified_camera_solver.py").read_text(encoding="utf-8")
        self.assertIn("naturalness_tier", source)
        self.assertIn("native-target-room-wall-envelope-v2", source)
        self.assertIn("crop_bottom", source)
        self.assertIn("abs(item.fov - 90.0)", source)
        capture = (SCRIPTS / "capture_frozen_html_plan.mjs").read_text(encoding="utf-8")
        self.assertIn("normalizedProjectionCrop", capture)
        self.assertIn("remapFrameFacts", capture)
        self.assertIn("Page.captureScreenshot", capture)

    def test_quality_advisory_does_not_block_strict_camera_delivery(self) -> None:
        wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "w", 1)
        candidate = solver.Candidate(
            room_id="room",
            room_name="房间",
            room_kind="bedroom",
            mode="strict-wall-frontal",
            target_wall=wall,
            position=(1, 1.5, 1),
            forward=(0, -1),
            fov=90,
            window_center=(0, 0),
            placement_tier="floor-standing",
            primary_ids=["bed"],
            companion_ids=[],
            framing_ids=["bed"],
            primary_center=(1, 0.5, 0),
            front_score=1,
            semantic_axis_alignment=1,
            semantic_axis_required=True,
            wall_alignment_error_degrees=0,
            analytic_score=1,
            analytic={"perspectiveDepthRatio": 2},
            quality_preferred=False,
            final_score=1,
            pixel={
                "primary": {"bboxArea": 0.1},
                "qualityAdvisories": ["subject-small"],
            },
        )
        selected, contract = solver.select_views([candidate], 1)
        self.assertEqual(selected, [candidate])
        self.assertFalse(contract["deliveryBlockedByQuality"])

    def test_subject_facing_axis_outranks_neat_side_view(self) -> None:
        correct_wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "headboard", 0.9)
        side_wall = solver.WallFrame(1, (0, 0), (0, 2), (0, 1), (1, 0), 2, "side", -0.8)

        def candidate(wall: solver.WallFrame, alignment: float, score: float) -> solver.Candidate:
            return solver.Candidate(
                room_id="room", room_name="卧室", room_kind="bedroom", mode="strict-wall-frontal",
                target_wall=wall, position=(1, 1.5, 1), forward=wall.optical_axis, fov=90,
                window_center=(0, 0), placement_tier="floor-standing", primary_ids=["bed"],
                companion_ids=[], framing_ids=["bed"], primary_center=(1, 0.5, 0), front_score=alignment,
                semantic_axis_alignment=alignment, semantic_axis_required=True, wall_alignment_error_degrees=0,
                analytic_score=score, analytic={"perspectiveDepthRatio": 2, "primaryCompleteFit": True},
                quality_preferred=True, final_score=score,
                pixel={"primary": {"bboxArea": 0.2}, "frontalUsable": True, "centerFirstHitPass": True,
                       "foregroundFurnitureRatio": 0, "foregroundWallRatio": 0, "foregroundOpeningRatio": 0,
                       "targetCropForeignRatio": 0, "pixelBlankBorder": 0.2, "qualityAdvisories": []},
            )

        correct = candidate(correct_wall, 1.0, 10)
        side = candidate(side_wall, 0.0, 1000)
        selected, _ = solver.select_views([side, correct], 1)
        self.assertEqual(selected, [correct])

    def test_complete_inside_subject_view_precedes_external_view(self) -> None:
        wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "headboard", 0.9)

        def candidate(inside: bool, score: float) -> solver.Candidate:
            return solver.Candidate(
                room_id="room", room_name="卧室", room_kind="bedroom", mode="strict-wall-frontal",
                target_wall=wall, position=(1, 1.5, 1 if inside else 3), forward=wall.optical_axis,
                fov=110 if inside else 90, window_center=(0, 0),
                placement_tier="floor-standing" if inside else "external-frontal",
                primary_ids=["bed"], companion_ids=[], framing_ids=["bed"], primary_center=(1, 0.5, 0),
                front_score=1, semantic_axis_alignment=1, semantic_axis_required=True,
                wall_alignment_error_degrees=0, analytic_score=score,
                analytic={"perspectiveDepthRatio": 2, "primaryCompleteFit": True},
                camera_inside_target_room=inside, quality_preferred=True, final_score=score,
                pixel={"primary": {"bboxArea": 0.2}, "frontalUsable": True, "centerFirstHitPass": True,
                       "foregroundFurnitureRatio": 0, "foregroundWallRatio": 0, "foregroundOpeningRatio": 0,
                       "targetCropForeignRatio": 0, "pixelBlankBorder": 0.2, "qualityAdvisories": []},
            )

        inside = candidate(True, 10)
        external = candidate(False, 1000)
        selected, _ = solver.select_views([external, inside], 1)
        self.assertEqual(selected, [inside])

    def test_external_view_precedes_camera_pressed_against_bed(self) -> None:
        wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "headboard", 0.9)

        def candidate(inside: bool, near_depth: float) -> solver.Candidate:
            return solver.Candidate(
                room_id="room", room_name="卧室", room_kind="bedroom", mode="strict-wall-frontal",
                target_wall=wall, position=(1, 1.5, 1 if inside else 3), forward=wall.optical_axis,
                fov=110 if inside else 90, window_center=(0, 0),
                placement_tier="floor-standing" if inside else "external-frontal",
                primary_ids=["bed"], companion_ids=[], framing_ids=["bed"], primary_center=(1, 0.5, 0),
                front_score=1, semantic_axis_alignment=1, semantic_axis_required=True,
                wall_alignment_error_degrees=0, analytic_score=1,
                analytic={"perspectiveDepthRatio": 2, "primaryCompleteFit": True,
                          "primaryNearDepthMeters": near_depth, "lateralOffsetMeters": 0},
                camera_inside_target_room=inside, quality_preferred=True, final_score=1,
                pixel={"primary": {"bboxArea": 0.2}, "frontalUsable": True, "centerFirstHitPass": True,
                       "foregroundFurnitureRatio": 0, "foregroundWallRatio": 0, "foregroundOpeningRatio": 0,
                       "targetCropForeignRatio": 0, "pixelBlankBorder": 0.2, "qualityAdvisories": []},
            )

        selected, _ = solver.select_views([candidate(True, 0.25), candidate(False, 1.25)], 1)
        self.assertFalse(selected[0].camera_inside_target_room)

    def test_directional_subject_prefers_centered_station(self) -> None:
        wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "headboard", 0.9)

        def candidate(lateral: float, score: float) -> solver.Candidate:
            return solver.Candidate(
                room_id="room", room_name="卧室", room_kind="bedroom", mode="strict-wall-frontal",
                target_wall=wall, position=(1 + lateral, 1.5, 1), forward=wall.optical_axis, fov=96,
                window_center=(0, 0), placement_tier="floor-standing", primary_ids=["bed"],
                companion_ids=[], framing_ids=["bed"], primary_center=(1, 0.5, 0), front_score=1,
                semantic_axis_alignment=1, semantic_axis_required=True, wall_alignment_error_degrees=0,
                analytic_score=score,
                analytic={"perspectiveDepthRatio": 2, "primaryCompleteFit": True, "lateralOffsetMeters": lateral},
                camera_inside_target_room=True, quality_preferred=True, final_score=score,
                pixel={"primary": {"bboxArea": 0.2}, "frontalUsable": True, "centerFirstHitPass": True,
                       "foregroundFurnitureRatio": 0, "foregroundWallRatio": 0, "foregroundOpeningRatio": 0,
                       "targetCropForeignRatio": 0, "pixelBlankBorder": 0.2, "qualityAdvisories": []},
            )

        centered = candidate(0.0, 10)
        offset = candidate(0.9, 1000)
        selected, _ = solver.select_views([offset, centered], 1)
        self.assertEqual(selected, [centered])

    def test_backend_templates_share_one_solver_contract(self) -> None:
        root = ROOT / "assets" / "backend-templates"
        templates = [json.loads((root / name).read_text(encoding="utf-8")) for name in ("html.json", "blender.json", "cad.json")]
        self.assertEqual({item["backend"] for item in templates}, {"html-threejs", "blender", "cad-step"})
        self.assertTrue(all(item["schema"] == "interior.camera-backend-template.v1" for item in templates))
        by_backend = {item["backend"]: item for item in templates}
        self.assertEqual(by_backend["html-threejs"]["planPolicy"], "solve-once-from-current-html")
        self.assertEqual(by_backend["blender"]["planPolicy"], "consume-frozen-v3")
        self.assertEqual(by_backend["cad-step"]["planPolicy"], "consume-frozen-v3")
        self.assertNotIn("scene", by_backend["blender"])
        self.assertNotIn("scene", by_backend["cad-step"])
        runner = (SCRIPTS / "run_camera_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"productionSolver": "unified_camera_solver.py"', runner)
        self.assertNotIn("select_blender_camera", runner)
        self.assertNotIn("select_cad_camera", runner)

    def test_visible_quality_preferred_candidate_outranks_invisible_candidate(self) -> None:
        wall = solver.WallFrame(0, (0, 0), (2, 0), (1, 0), (0, 1), 2, "headboard", 0.9)

        def candidate(preferred: bool, score: float) -> solver.Candidate:
            return solver.Candidate(
                room_id="room", room_name="卧室", room_kind="bedroom", mode="strict-wall-frontal",
                target_wall=wall, position=(1, 1.5, 1), forward=wall.optical_axis, fov=90,
                window_center=(0, 0), placement_tier="floor-standing", primary_ids=["bed"],
                companion_ids=[], framing_ids=["bed"], primary_center=(1, 0.5, 0), front_score=1,
                semantic_axis_alignment=1, semantic_axis_required=True, wall_alignment_error_degrees=0,
                analytic_score=score,
                analytic={"perspectiveDepthRatio": 2, "primaryCompleteFit": True,
                          "lateralOffsetMeters": 0, "primaryNearDepthMeters": 1.4},
                camera_inside_target_room=True, quality_preferred=preferred, final_score=score,
                pixel={"primary": {"bboxArea": 0.2 if preferred else 0.0},
                       "frontalUsable": preferred, "centerFirstHitPass": preferred,
                       "foregroundFurnitureRatio": 0, "foregroundWallRatio": 0,
                       "foregroundOpeningRatio": 0, "targetCropForeignRatio": 0,
                       "pixelBlankBorder": 0.2, "qualityAdvisories": [] if preferred else ["primary-group-not-visible"]},
            )

        visible = candidate(True, 1)
        invisible = candidate(False, 10000)
        selected, contract = solver.select_views([invisible, visible], 1)
        self.assertEqual(selected, [visible])
        self.assertEqual(contract["selectionPool"], "quality-preferred")


if __name__ == "__main__":
    unittest.main()
