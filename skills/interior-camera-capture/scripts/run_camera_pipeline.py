#!/usr/bin/env python3
"""Run one common camera solver through a declarative backend template."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any


ALIASES = {"html": "html-threejs", "blender": "blender", "cad": "cad-step"}
def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expand(value: str, context: dict[str, str]) -> str:
    result = value
    for key, replacement in context.items():
        result = result.replace("{" + key + "}", replacement)
    if "{" in result or "}" in result:
        raise ValueError(f"unresolved backend template token: {result}")
    return result


def runtime_program(runtime: str, args: argparse.Namespace) -> str:
    return {
        "python": args.python_bin,
        "node": args.node_bin,
        "blender": args.blender_bin,
    }[runtime]


def run(command: list[str], environment: dict[str, str], timeout: int | None = None) -> float:
    started = time.perf_counter()
    subprocess.run(command, check=True, timeout=timeout, env=environment)
    return time.perf_counter() - started


def run_spec(spec: dict[str, Any], context: dict[str, str], args: argparse.Namespace, environment: dict[str, str]) -> float:
    runtime = str(spec["runtime"])
    program = runtime_program(runtime, args)
    spec_context = dict(context)
    if spec.get("script"):
        spec_context["script"] = expand(str(spec["script"]), spec_context)
    arguments = [expand(str(value), spec_context) for value in spec.get("arguments", [])]
    command = [program]
    if runtime in {"python", "node"} and spec.get("script"):
        command.append(spec_context["script"])
    command.extend(arguments)
    timeout = int(spec["timeoutSeconds"]) if "timeoutSeconds" in spec else None
    return run(command, environment, timeout=timeout)


def localize_spec(spec: dict[str, Any], skill_root: Path) -> dict[str, Any]:
    value = dict(spec)
    script = str(value.get("script", ""))
    if script and "{" not in script and not Path(script).is_absolute():
        value["script"] = str(skill_root / script)
    return value


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--backend", default="html-threejs")
    value.add_argument("--html")
    value.add_argument("--native-model")
    value.add_argument("--model-manifest")
    value.add_argument("--camera-plan")
    value.add_argument("--camera-intent")
    value.add_argument("--structure", required=True)
    value.add_argument("--out-dir", required=True)
    value.add_argument("--views-per-room", type=int, default=1)
    value.add_argument("--viewport", default="1600x1000")
    value.add_argument("--python-bin", default=os.environ.get("CAMERA_PYTHON", "/home/agentops/agent-runtime/runtimes/interior-camera-capture-39/bin/python"))
    value.add_argument("--node-bin", default=os.environ.get("NODE_BIN", "/home/agentops/agent-runtime/bin/node"))
    value.add_argument("--chrome-bin", default=os.environ.get("CHROME_BIN", "/home/agentops/agent-runtime/bin/render-chrome"))
    value.add_argument("--blender-bin", default=os.environ.get("BLENDER_BIN", "/home/agentops/agent-runtime/bin/blender"))
    value.add_argument("--blender-skill", default=os.environ.get("INTERIOR_BLENDER_MODELING_SKILL", "/home/agentops/.codex/skills/interior-blender-modeling"))
    value.add_argument("--cad-skill", default=os.environ.get("INTERIOR_CAD_MODELING_SKILL", "/home/agentops/.codex/skills/interior-cad-modeling"))
    return value


def main() -> None:
    args = parser().parse_args()
    backend = ALIASES.get(args.backend, args.backend)
    if not 1 <= args.views_per_room <= 6:
        raise SystemExit("--views-per-room must be between 1 and 6")
    skill_root = Path(__file__).resolve().parents[1]
    template_path = skill_root / "assets" / "backend-templates" / (
        "html.json" if backend == "html-threejs" else "blender.json" if backend == "blender" else "cad.json"
    )
    template = load(template_path)
    if template.get("schema") != "interior.camera-backend-template.v1" or template.get("backend") != backend:
        raise SystemExit("camera backend template is invalid or belongs to another backend")
    supplied = {
        "html": args.html,
        "nativeModel": args.native_model,
        "modelManifest": args.model_manifest,
        "cameraPlan": args.camera_plan,
        "structure": args.structure,
    }
    missing = [name for name in template.get("requiredInputs", []) if not supplied.get(name)]
    if missing:
        raise SystemExit(f"{backend} camera pipeline requires: {', '.join(missing)}")
    capture_spec = localize_spec(template["capture"], skill_root)
    plan_adapter_spec = localize_spec(template["planAdapter"], skill_root) if template.get("planAdapter") else None

    root = Path(args.out_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    scene_dir, final_plan, delivery = root / "scene", root / "plan", root / "delivery"
    for directory in (scene_dir, final_plan, delivery):
        directory.mkdir(parents=True, exist_ok=True)
    scripts = Path(__file__).resolve().parent
    environment = os.environ.copy()
    environment.update({"CHROME_BIN": args.chrome_bin, "NODE_BIN": args.node_bin})
    context = {
        "html": str(Path(args.html).resolve()) if args.html else "",
        "nativeModel": str(Path(args.native_model).resolve()) if args.native_model else "",
        "modelManifest": str(Path(args.model_manifest).resolve()) if args.model_manifest else "",
        "structure": str(Path(args.structure).resolve()), "sceneDir": str(scene_dir),
        "outDir": str(delivery), "viewport": args.viewport,
        "nodeBin": args.node_bin, "chromeBin": args.chrome_bin,
        "blenderSkill": str(Path(args.blender_skill).resolve()), "cadSkill": str(Path(args.cad_skill).resolve()),
        "plan": str(final_plan / "camera-plan.json"), "adaptedPlan": str(final_plan / "backend-camera-plan.json"),
    }
    pipeline_started = time.perf_counter()
    timings: dict[str, float] = {}
    plan_policy = str(template.get("planPolicy", ""))
    solver_invoked = False
    plan_source: dict[str, str]
    if plan_policy == "solve-once-from-current-html":
        scene_spec = template["scene"]
        if scene_spec.get("mode") != "generate":
            raise SystemExit("the canonical HTML template must generate the sole solver scene")
        scene_context = dict(context)
        scene_context["script"] = str(skill_root / str(scene_spec["script"]))
        spec = dict(scene_spec)
        spec["script"] = scene_context["script"]
        if args.camera_intent:
            camera_intent = str(Path(args.camera_intent).resolve())
            if not Path(camera_intent).is_file():
                raise SystemExit(f"camera intent is missing: {camera_intent}")
            spec["arguments"] = [*spec.get("arguments", []), "--camera-intent", camera_intent]
        timings["sceneGenerationSeconds"] = run_spec(spec, scene_context, args, environment)
        common_solver = [
            args.python_bin, str(scripts / "unified_camera_solver.py"),
            "--model", str(scene_dir / "current-model-export.json"),
            "--structure", str(Path(args.structure).resolve()),
            "--semantic-facts", str(scene_dir / "semantic-room-facts.json"),
            "--scene", str(scene_dir / "camera-semantic-scene.gltf"),
            "--native-geometry", str(scene_dir / "native-scene-geometry.json"),
            "--views-per-room", str(args.views_per_room),
        ]
        provisional_plan, provisional_facts = root / ".provisional-plan", root / ".provisional-native-facts"
        provisional_plan.mkdir(exist_ok=True)
        provisional_facts.mkdir(exist_ok=True)
        solver_invoked = True
        timings["provisionalSolveSeconds"] = run([
            *common_solver, "--output-plan", str(provisional_plan / "camera-plan.json"),
            "--output-diagnostics", str(provisional_plan / "camera-solver-diagnostics.json"),
        ], environment)
        provisional_context = dict(context)
        provisional_context.update({"plan": str(provisional_plan / "camera-plan.json"), "outDir": str(provisional_facts)})
        timings["nativeProbeCaptureSeconds"] = run_spec(capture_spec, provisional_context, args, environment)
        timings["finalSolveSeconds"] = run([
            *common_solver, "--output-plan", str(final_plan / "camera-plan.json"),
            "--output-diagnostics", str(final_plan / "camera-solver-diagnostics.json"),
            "--native-facts-dir", str(provisional_facts),
        ], environment)
        shutil.rmtree(provisional_plan)
        shutil.rmtree(provisional_facts)
        plan_source = {"mode": "solved-once-from-current-html", "path": str(final_plan / "camera-plan.json")}
    elif plan_policy == "consume-frozen-v3":
        source_plan = Path(args.camera_plan).resolve()
        if not source_plan.is_file():
            raise SystemExit("the backend requires an existing frozen camera plan")
        frozen = load(source_plan)
        structure = load(Path(args.structure).resolve())
        if frozen.get("schema") != "interior.algorithmic-camera-plan.v3":
            raise SystemExit("backend camera plan must be interior.algorithmic-camera-plan.v3")
        if str(frozen.get("floorplanId")) != str(structure.get("floorplanId")):
            raise SystemExit("frozen camera plan and backend structure belong to different floorplans")
        if len(frozen.get("shots", [])) < 1:
            raise SystemExit("frozen camera plan has no shots")
        shutil.copy2(source_plan, final_plan / "camera-plan.json")
        timings["planReuseSeconds"] = 0.0
        plan_source = {"mode": "reused-frozen-plan", "path": str(source_plan), "sha256": sha256(source_plan)}
    else:
        raise SystemExit(f"unsupported plan policy: {plan_policy}")

    context["plan"] = str(final_plan / "camera-plan.json")
    if plan_adapter_spec:
        timings["planAdaptationSeconds"] = run_spec(plan_adapter_spec, context, args, environment)
    timings["formalCaptureSeconds"] = run_spec(capture_spec, context, args, environment)
    index_path = delivery / "camera-delivery-index.json"
    if not index_path.is_file():
        raise SystemExit("backend capture did not create camera-delivery-index.json")
    index = load(index_path)
    summary = index.get("summary", {})
    if summary.get("failed") or summary.get("delivered") != summary.get("requested"):
        raise SystemExit("backend camera delivery is incomplete")
    timings["totalSeconds"] = time.perf_counter() - pipeline_started
    timings = {key: round(value, 3) for key, value in timings.items()}
    receipt = {
        "schema": "interior.camera-pipeline-receipt.v2", "status": "complete",
        "downstreamReady": True, "modelBackend": backend,
        "backendTemplate": {"path": str(template_path), "sha256": sha256(template_path)},
        "algorithm": "source-intent-fixture-facing-frontal-camera-v6",
        "productionSolver": "unified_camera_solver.py",
        "productionSolverInvoked": solver_invoked,
        "planSource": plan_source,
        "cameraPlan": {"path": str(final_plan / "camera-plan.json"), "sha256": sha256(final_plan / "camera-plan.json")},
        "cameraIntent": (
            {"path": str(Path(args.camera_intent).resolve()), "sha256": sha256(args.camera_intent)}
            if args.camera_intent else None
        ),
        "deliveryIndex": {"path": str(index_path), "sha256": sha256(index_path)},
        "summary": summary, "timings": timings,
        "timingPolicy": {"advisoryOnly": True, "deliveryBlockedByTiming": False},
    }
    write(root / "camera-pipeline-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
