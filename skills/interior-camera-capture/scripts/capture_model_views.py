#!/usr/bin/env python3
"""Dispatch an accepted camera plan to its native backend capture adapter."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Iterator


BACKENDS = {"html-threejs", "blender", "cad-step"}
CAPTURE_CONCURRENCY = 2
CAPTURE_SLOT_ROOT = Path(
    os.environ.get("INTERIOR_CAPTURE_SLOT_ROOT", "/tmp/interior-capture-slots-v1")
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_from(base: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.strip().split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    return values


def pressure_avg10(resource: str, mode: str) -> float:
    path = Path("/proc/pressure") / resource
    if not path.is_file():
        return 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts and parts[0] == mode:
            for part in parts[1:]:
                if part.startswith("avg10="):
                    return float(part.split("=", 1)[1])
    return 0.0


def filesystem_evidence(path: Path) -> dict[str, float]:
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bavail * stat.f_frsize
    return {
        "totalGiB": round(total / 1024**3, 3),
        "freeGiB": round(free / 1024**3, 3),
        "usedRatio": round((total - free) / total, 4) if total else 0.0,
    }


def resource_snapshot(phase: str) -> dict:
    memory = meminfo()
    available = memory.get("MemAvailable", 0)
    swap_total = memory.get("SwapTotal", 0)
    swap_free = memory.get("SwapFree", 0)
    swap_used_ratio = (swap_total - swap_free) / swap_total if swap_total else 0.0
    root = filesystem_evidence(Path("/"))
    temporary = filesystem_evidence(Path("/tmp"))
    load_1m = os.getloadavg()[0]
    evidence = {
        "phase": phase,
        "capturedAtUnix": time.time(),
        "memoryAvailableGiB": round(available / 1024**3, 3),
        "swapUsedRatio": round(swap_used_ratio, 4),
        "load1m": round(load_1m, 3),
        "cpuCount": os.cpu_count() or 1,
        "memoryPressureSomeAvg10": pressure_avg10("memory", "some"),
        "memoryPressureFullAvg10": pressure_avg10("memory", "full"),
        "rootFilesystem": root,
        "temporaryFilesystem": temporary,
        "captureConcurrencyLimit": CAPTURE_CONCURRENCY,
    }
    return evidence


def resource_gate(phase: str) -> dict:
    evidence = resource_snapshot(phase)
    root = evidence["rootFilesystem"]
    temporary = evidence["temporaryFilesystem"]
    available = evidence["memoryAvailableGiB"] * 1024**3
    swap_used_ratio = evidence["swapUsedRatio"]
    load_1m = evidence["load1m"]
    failures = []
    if root["freeGiB"] < 8:
        failures.append("root disk has less than 8 GiB free")
    if temporary["freeGiB"] < 1.5 or temporary["usedRatio"] >= 0.85:
        failures.append("/tmp has insufficient headroom for a managed Chrome profile")
    if available < 3 * 1024**3:
        failures.append("available memory is below 3 GiB")
    if swap_used_ratio >= 0.95 and available < 4 * 1024**3:
        failures.append("swap is at least 95% used while available memory is below 4 GiB")
    if load_1m >= max(8.0, (os.cpu_count() or 1) * 0.75):
        failures.append("one-minute load exceeds the capture threshold")
    if evidence["memoryPressureFullAvg10"] >= 1.0:
        failures.append("full memory pressure avg10 is at least 1.0")
    if failures:
        raise RuntimeError(f"capture resource gate rejected {phase}: {'; '.join(failures)}; evidence={json.dumps(evidence, ensure_ascii=False)}")
    return evidence


@contextlib.contextmanager
def capture_slot(timeout_seconds: int = 120) -> Iterator[dict]:
    CAPTURE_SLOT_ROOT.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        for slot_number in range(1, CAPTURE_CONCURRENCY + 1):
            handle = (CAPTURE_SLOT_ROOT / f"slot-{slot_number}.lock").open("a+", encoding="utf-8")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            owner = {
                "slot": slot_number,
                "pid": os.getpid(),
                "acquiredAtUnix": time.time(),
                "limit": CAPTURE_CONCURRENCY,
            }
            handle.seek(0)
            handle.truncate()
            json.dump(owner, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                yield owner
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"timed out waiting for one of {CAPTURE_CONCURRENCY} formal screenshot slots"
            )
        time.sleep(0.25)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-manifest", required=True)
    parser.add_argument("--camera-plan", required=True)
    parser.add_argument("--structure", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--blender-bin", default=os.environ.get("BLENDER_BIN", "blender"))
    parser.add_argument("--cad-renderer-command", default=os.environ.get("INTERIOR_CAD_SNAPSHOT_COMMAND"))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    manifest_path = Path(args.model_manifest).resolve()
    plan_path = Path(args.camera_plan).resolve()
    structure_path = Path(args.structure).resolve()
    out = Path(args.out).resolve()
    manifest = read_json(manifest_path)
    plan = read_json(plan_path)
    if manifest.get("schema") != "interior.native-model-manifest.v1" or manifest.get("validation", {}).get("accepted") is not True:
        raise SystemExit("model manifest must be accepted interior.native-model-manifest.v1")
    backend = manifest.get("modelBackend")
    if backend not in BACKENDS:
        raise SystemExit(f"unsupported model backend: {backend}")
    native = manifest.get("nativeModel", {})
    native_path = resolve_from(manifest_path.parent, native.get("path", ""))
    if not native_path.is_file() or sha256(native_path) != native.get("sha256"):
        raise SystemExit("native model file/hash mismatch")
    if plan.get("schema") != "interior.camera-plan.v8" or plan.get("coordinateSystem") != "interior-world-y-up.v1":
        raise SystemExit("camera plan must be v8 in interior-world-y-up.v1")
    if plan.get("modelBackend") != backend or plan.get("sourceModelSha256") != native["sha256"]:
        raise SystemExit("camera plan was not solved against this native model")
    if not structure_path.is_file():
        raise SystemExit("validated structure-data.json is missing")
    validator = Path(__file__).resolve().parent / "validate_camera_manifest.py"
    subprocess.run(
        [sys.executable, str(validator), str(plan_path), str(manifest_path), str(structure_path)],
        check=True,
        timeout=120,
    )
    adapter = resolve_from(manifest_path.parent, manifest.get("captureAdapter", {}).get("script", ""))
    if not adapter.is_file():
        raise SystemExit("native capture adapter is missing")
    out.mkdir(parents=True, exist_ok=True)

    if backend == "html-threejs":
        node_bin = (
            os.environ.get("NODE_BIN")
            or shutil.which("node")
            or "/home/agentops/agent-runtime/bin/node"
        )
        if not Path(node_bin).is_file():
            raise SystemExit("Node.js runtime is required for the formal HTML capture adapter")
        command = [node_bin, str(adapter), "--model-manifest", str(manifest_path), "--shots-manifest", str(plan_path), "--out-dir", str(out)]
        if args.prepare_only:
            command.append("--dry-run")
    elif backend == "blender":
        if args.prepare_only:
            result = {
                "schema": "interior.native-capture-dispatch.v1",
                "accepted": False,
                "preparedOnly": True,
                "modelBackend": backend,
                "command": [args.blender_bin, "-b", str(native_path), "--python", str(adapter), "--", "--camera-plan", str(plan_path), "--out", str(out)],
            }
            (out / "dispatch-plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(out / "dispatch-plan.json")
            return 0
        command = [args.blender_bin, "-b", str(native_path), "--python", str(adapter), "--", "--camera-plan", str(plan_path), "--out", str(out)]
    else:
        command = [sys.executable, str(adapter), "--manifest", str(manifest_path), "--camera-plan", str(plan_path), "--out", str(out)]
        if args.prepare_only:
            command.append("--prepare-only")
        elif args.cad_renderer_command:
            command.extend(["--renderer-command", args.cad_renderer_command])
        else:
            raise SystemExit("INTERIOR_CAD_SNAPSHOT_COMMAND is required for native CAD capture")

    if not 1 <= args.timeout_seconds <= 900:
        raise SystemExit("--timeout-seconds must be between 1 and 900")
    dispatch_resource_evidence = {"preparedOnly": True}
    dispatch_slot = None
    environment = os.environ.copy()
    environment["INTERIOR_FORMAL_CAPTURE_DISPATCH"] = "1"
    if args.prepare_only:
        try:
            subprocess.run(command, check=True, timeout=args.timeout_seconds, env=environment)
        except subprocess.TimeoutExpired as exc:
            raise SystemExit(
                f"native capture exceeded the bounded {args.timeout_seconds}s runtime; stop instead of retrying indefinitely"
            ) from exc
    else:
        with capture_slot() as slot:
            dispatch_slot = slot
            environment["INTERIOR_CAPTURE_SLOT_HELD"] = str(slot["slot"])
            dispatch_resource_evidence = {
                "beforeAdapter": resource_gate("before-native-adapter"),
            }
            try:
                subprocess.run(command, check=True, timeout=args.timeout_seconds, env=environment)
            except subprocess.TimeoutExpired as exc:
                raise SystemExit(
                    f"native capture exceeded the bounded {args.timeout_seconds}s runtime; stop instead of retrying indefinitely"
                ) from exc
            dispatch_resource_evidence["afterAdapter"] = resource_snapshot("after-native-adapter")
    result_path = out / "capture-result.json"
    if not result_path.is_file():
        raise SystemExit("native adapter did not create capture-result.json")
    result = read_json(result_path)
    if not args.prepare_only:
        if result.get("schema") != "interior.native-capture-result.v1" or result.get("modelBackend") != backend:
            raise SystemExit("native adapter returned an invalid result")
        if result.get("sourceModelSha256") != native["sha256"]:
            raise SystemExit("native capture result hash differs from the model")
        if result.get("accepted") is not True:
            raise SystemExit("native capture result was not accepted")
        if backend == "cad-step" and result.get("projectionEvidenceAccepted") is not True:
            raise SystemExit("CAD capture lacks accepted same-B-rep semantic projection evidence")
    result["formalCaptureDispatcher"] = {
        "script": "interior-camera-capture/scripts/capture_model_views.py",
        "cameraPlanValidated": True,
        "resourceGateApplied": not args.prepare_only,
        "globalScreenshotConcurrencyLimit": CAPTURE_CONCURRENCY,
        "slot": dispatch_slot,
    }
    result["dispatcherResourceEvidence"] = dispatch_resource_evidence
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
