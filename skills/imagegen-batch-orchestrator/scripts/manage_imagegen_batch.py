#!/usr/bin/env python3
"""Persist and recover dependency-aware ImageGen jobs."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator


PLAN_SCHEMA = "imagegen.batch-plan.v1"
RECEIPT_SCHEMA = "imagegen.batch-receipt.v1"
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*$")
MAX_IMAGEGEN_CONCURRENCY = 5


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@contextlib.contextmanager
def locked(run_dir: Path) -> Iterator[None]:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / ".lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def event(run_dir: Path, event_type: str, job_id: str | None = None, **details: Any) -> None:
    row = {"at": now(), "event": event_type, **details}
    if job_id is not None:
        row["jobId"] = job_id
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(canonical(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def validate_plan(plan_path: Path, plan: dict[str, Any]) -> dict[str, int]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"plan must use {PLAN_SCHEMA}")
    if not ID_RE.fullmatch(str(plan.get("planId", ""))):
        raise ValueError("planId must be a lowercase stable ID")
    if not isinstance(plan.get("sourceSkill"), str) or not plan["sourceSkill"].strip():
        raise ValueError("sourceSkill is required")
    concurrency = plan.get("maxConcurrency")
    if (
        not isinstance(concurrency, int)
        or isinstance(concurrency, bool)
        or not 1 <= concurrency <= MAX_IMAGEGEN_CONCURRENCY
    ):
        raise ValueError(
            f"maxConcurrency must be between 1 and {MAX_IMAGEGEN_CONCURRENCY}"
        )
    source = plan.get("sourcePlan")
    if not isinstance(source, dict):
        raise ValueError("sourcePlan is required")
    source_path = resolve(plan_path.parent, source.get("path", ""))
    if not source_path.is_file() or digest_file(source_path) != source.get("sha256"):
        raise ValueError("sourcePlan file is missing or changed")
    jobs = plan.get("jobs")
    batches = plan.get("batches")
    if not isinstance(jobs, list) or not jobs or not isinstance(batches, list) or not batches:
        raise ValueError("jobs and batches must be non-empty lists")
    job_by_id: dict[str, dict[str, Any]] = {}
    for row in jobs:
        job_id = row.get("jobId")
        if not isinstance(job_id, str) or not ID_RE.fullmatch(job_id) or job_id in job_by_id:
            raise ValueError(f"invalid or duplicate jobId: {job_id}")
        dependencies = row.get("dependencies")
        if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)):
            raise ValueError(f"{job_id}: dependencies must be a unique list")
        request_value = row.get("requestPath")
        request_digest = row.get("requestSha256")
        if request_value is None or request_digest is None:
            if request_value is not None or request_digest is not None or not dependencies:
                raise ValueError(f"{job_id}: only dependent jobs may defer both request fields")
        else:
            request_path = resolve(plan_path.parent, request_value)
            if not request_path.is_file() or digest_file(request_path) != request_digest:
                raise ValueError(f"{job_id}: request file is missing or changed")
        output = Path(str(row.get("outputFile", "")))
        if output.is_absolute() or not output.name or ".." in output.parts:
            raise ValueError(f"{job_id}: outputFile must stay inside outputs")
        attempts = row.get("maxAttempts")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
            raise ValueError(f"{job_id}: maxAttempts must be positive")
        job_by_id[job_id] = row
    flat: list[str] = []
    batch_index: dict[str, int] = {}
    for index, batch in enumerate(batches):
        batch_id = batch.get("batchId")
        ids = batch.get("jobIds")
        if not isinstance(batch_id, str) or not ID_RE.fullmatch(batch_id):
            raise ValueError("batchId must be a lowercase stable ID")
        if not isinstance(ids, list) or not ids:
            raise ValueError(f"{batch_id}: jobIds must be non-empty")
        for job_id in ids:
            if job_id in batch_index:
                raise ValueError(f"job appears in multiple batches: {job_id}")
            batch_index[job_id] = index
            flat.append(job_id)
    if set(flat) != set(job_by_id) or len(flat) != len(job_by_id):
        raise ValueError("batches must schedule every job exactly once")
    for job_id, row in job_by_id.items():
        for dependency in row["dependencies"]:
            if dependency not in job_by_id or batch_index[dependency] >= batch_index[job_id]:
                raise ValueError(f"{job_id}: dependency must be in an earlier batch")
    return batch_index


def require_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    plan_path = run_dir / "plan.json"
    run_path = run_dir / "run.json"
    if not plan_path.is_file() or not run_path.is_file():
        raise ValueError(f"not an initialized run: {run_dir}")
    return load(plan_path), load(run_path)


def job_path(run_dir: Path, job_id: str) -> Path:
    if not ID_RE.fullmatch(job_id):
        raise ValueError("invalid job ID")
    path = run_dir / "jobs" / f"{job_id}.json"
    if not path.is_file():
        raise ValueError(f"unknown job: {job_id}")
    return path


def job_states(run_dir: Path, plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["jobId"]: load(job_path(run_dir, row["jobId"])) for row in plan["jobs"]}


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    plan_path = Path(args.plan).resolve()
    run_dir = Path(args.run_dir).resolve()
    plan = load(plan_path)
    batch_index = validate_plan(plan_path, plan)
    with locked(run_dir):
        frozen_path = run_dir / "plan.json"
        if frozen_path.is_file():
            if digest_value(load(frozen_path)) != digest_value(plan):
                raise ValueError("run directory already contains a different plan")
            return {"ok": True, "idempotent": True, "runDir": str(run_dir)}
        atomic_json(frozen_path, plan)
        created = now()
        atomic_json(run_dir / "run.json", {
            "schema": "imagegen.batch-run.v1",
            "planId": plan["planId"],
            "planDigestSha256": digest_value(plan),
            "sourcePlanPath": str(plan_path),
            "createdAt": created,
            "updatedAt": created,
        })
        for row in plan["jobs"]:
            atomic_json(run_dir / "jobs" / f"{row['jobId']}.json", {
                "schema": "imagegen.job-state.v1",
                "jobId": row["jobId"],
                "batchIndex": batch_index[row["jobId"]],
                "status": "queued",
                "attempts": 0,
                "maxAttempts": row["maxAttempts"],
                "dependencies": row["dependencies"],
                "requestPath": (
                    str(resolve(plan_path.parent, row["requestPath"]))
                    if row.get("requestPath") is not None
                    else None
                ),
                "requestSha256": row.get("requestSha256"),
                "outputFile": row["outputFile"],
                "startedAt": None,
                "finishedAt": None,
                "lastError": None,
                "retryable": True,
                "invocationId": None,
                "providerRequestId": None,
                "output": None,
            })
        event(run_dir, "run-initialized", jobs=len(plan["jobs"]))
    return {"ok": True, "idempotent": False, "runDir": str(run_dir), "jobs": len(plan["jobs"])}


def cmd_ready(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    with locked(run_dir):
        plan, _ = require_run(run_dir)
        states = job_states(run_dir, plan)
        running = sum(state["status"] == "running" for state in states.values())
        available = max(0, plan["maxConcurrency"] - running)
        ready_rows: list[dict[str, Any]] = []
        selected_batch = None
        for index, batch in enumerate(plan["batches"]):
            candidates = []
            for job_id in batch["jobIds"]:
                state = states[job_id]
                can_retry = state["status"] == "failed" and state["retryable"] and state["attempts"] < state["maxAttempts"]
                if state["status"] != "queued" and not can_retry:
                    continue
                if not state.get("requestPath") or not state.get("requestSha256"):
                    continue
                if all(states[dependency]["status"] == "succeeded" for dependency in state["dependencies"]):
                    candidates.append(state)
            if candidates:
                selected_batch = index
                ready_rows = candidates[:available]
                break
            unresolved = [states[job_id] for job_id in batch["jobIds"] if states[job_id]["status"] != "succeeded"]
            if unresolved:
                break
        return {
            "schema": "imagegen.ready-jobs.v1",
            "runDir": str(run_dir),
            "maxConcurrency": plan["maxConcurrency"],
            "running": running,
            "batchIndex": selected_batch,
            "jobs": [{
                "jobId": state["jobId"],
                "requestPath": state["requestPath"],
                "requestSha256": state["requestSha256"],
                "dependencies": state["dependencies"],
                "attempt": state["attempts"] + 1,
                "outputFile": state["outputFile"],
            } for state in ready_rows],
        }


def cmd_start(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    with locked(run_dir):
        plan, _ = require_run(run_dir)
        states = job_states(run_dir, plan)
        state = states[args.job_id]
        can_retry = state["status"] == "failed" and state["retryable"] and state["attempts"] < state["maxAttempts"]
        if state["status"] != "queued" and not can_retry:
            raise ValueError(f"{args.job_id}: job is not startable from {state['status']}")
        if not state.get("requestPath") or not state.get("requestSha256"):
            raise ValueError(f"{args.job_id}: request is not bound")
        request_path = Path(state["requestPath"])
        if not request_path.is_file() or digest_file(request_path) != state["requestSha256"]:
            raise ValueError(f"{args.job_id}: bound request is missing or changed")
        if not all(states[dependency]["status"] == "succeeded" for dependency in state["dependencies"]):
            raise ValueError(f"{args.job_id}: dependencies are not complete")
        if sum(row["status"] == "running" for row in states.values()) >= plan["maxConcurrency"]:
            raise ValueError("maximum concurrency reached")
        state.update({
            "status": "running",
            "attempts": state["attempts"] + 1,
            "startedAt": now(),
            "finishedAt": None,
            "lastError": None,
            "retryable": True,
        })
        atomic_json(job_path(run_dir, args.job_id), state)
        event(run_dir, "job-started", args.job_id, attempt=state["attempts"])
        return state


def cmd_bind_request(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    request_path = Path(args.request).resolve()
    if not request_path.is_file():
        raise ValueError(f"request does not exist: {request_path}")
    with locked(run_dir):
        plan, _ = require_run(run_dir)
        states = job_states(run_dir, plan)
        state = states[args.job_id]
        if state["status"] != "queued" or state["attempts"] != 0:
            raise ValueError(f"{args.job_id}: request can only be bound before its first start")
        if not all(states[dependency]["status"] == "succeeded" for dependency in state["dependencies"]):
            raise ValueError(f"{args.job_id}: dependencies must succeed before request binding")
        request_digest = digest_file(request_path)
        state["requestPath"] = str(request_path)
        state["requestSha256"] = request_digest
        atomic_json(job_path(run_dir, args.job_id), state)
        event(run_dir, "job-request-bound", args.job_id, requestSha256=request_digest)
        return state


def cmd_succeed(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    source = Path(args.image).resolve()
    if not source.is_file():
        raise ValueError(f"generated image does not exist: {source}")
    with locked(run_dir):
        _, _ = require_run(run_dir)
        state = load(job_path(run_dir, args.job_id))
        if state["status"] == "succeeded":
            if state.get("output", {}).get("sha256") == digest_file(source):
                return state
            raise ValueError(f"{args.job_id}: succeeded output cannot be replaced")
        if state["status"] != "running":
            raise ValueError(f"{args.job_id}: job is not running")
        target = (run_dir / "outputs" / state["outputFile"]).resolve()
        outputs_root = (run_dir / "outputs").resolve()
        if outputs_root not in target.parents:
            raise ValueError("output path escaped outputs directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        shutil.copy2(source, temp)
        os.replace(temp, target)
        state.update({
            "status": "succeeded",
            "finishedAt": now(),
            "lastError": None,
            "retryable": False,
            "invocationId": args.invocation_id,
            "providerRequestId": args.provider_request_id,
            "output": {"path": str(target), "sha256": digest_file(target), "bytes": target.stat().st_size},
        })
        atomic_json(job_path(run_dir, args.job_id), state)
        event(run_dir, "job-succeeded", args.job_id, outputSha256=state["output"]["sha256"])
        return state


def cmd_fail(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    with locked(run_dir):
        _, _ = require_run(run_dir)
        state = load(job_path(run_dir, args.job_id))
        if state["status"] != "running":
            raise ValueError(f"{args.job_id}: only a running job can fail")
        retryable = bool(args.retryable and state["attempts"] < state["maxAttempts"])
        state.update({
            "status": "failed",
            "finishedAt": now(),
            "lastError": args.reason,
            "retryable": retryable,
        })
        atomic_json(job_path(run_dir, args.job_id), state)
        event(run_dir, "job-failed", args.job_id, retryable=retryable, reason=args.reason)
        return state


def cmd_recover(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    recovered = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=args.stale_seconds)
    with locked(run_dir):
        plan, _ = require_run(run_dir)
        for state in job_states(run_dir, plan).values():
            if state["status"] != "running" or parse_time(state["startedAt"]) > cutoff:
                continue
            state.update({
                "status": "failed",
                "finishedAt": now(),
                "lastError": "stale-running-job-recovered",
                "retryable": state["attempts"] < state["maxAttempts"],
            })
            atomic_json(job_path(run_dir, state["jobId"]), state)
            event(run_dir, "job-recovered", state["jobId"], retryable=state["retryable"])
            recovered.append(state["jobId"])
    return {"ok": True, "recoveredJobIds": recovered}


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    with locked(run_dir):
        plan, _ = require_run(run_dir)
        states = job_states(run_dir, plan)
        counts = {name: sum(row["status"] == name for row in states.values()) for name in ("queued", "running", "succeeded", "failed")}
        return {"schema": "imagegen.batch-status.v1", "planId": plan["planId"], "counts": counts, "jobs": list(states.values())}


def cmd_finalize(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    with locked(run_dir):
        plan, run = require_run(run_dir)
        states = job_states(run_dir, plan)
        incomplete = [job_id for job_id, state in states.items() if state["status"] != "succeeded"]
        if incomplete:
            raise ValueError(f"cannot finalize incomplete jobs: {incomplete}")
        for job_id, state in states.items():
            output = state.get("output") or {}
            output_path = Path(str(output.get("path", "")))
            if (
                not output_path.is_file()
                or digest_file(output_path) != output.get("sha256")
                or output_path.stat().st_size != output.get("bytes")
            ):
                raise ValueError(f"{job_id}: succeeded output is missing or changed")
        path = run_dir / "imagegen.batch-receipt.v1.json"
        if path.is_file():
            existing = load(path)
            existing_payload = dict(existing)
            existing_digest = existing_payload.pop("receiptDigestSha256", None)
            if (
                existing.get("schema") != RECEIPT_SCHEMA
                or existing.get("planId") != plan["planId"]
                or existing.get("planDigestSha256") != run["planDigestSha256"]
                or digest_value(existing_payload) != existing_digest
            ):
                raise ValueError("existing final receipt does not match this run")
            return {"ok": True, "idempotent": True, "receipt": str(path), **existing}
        intervals = [(parse_time(state["startedAt"]), parse_time(state["finishedAt"]), state["jobId"]) for state in states.values()]
        parallel_pairs = []
        for index, left in enumerate(intervals):
            for right in intervals[index + 1:]:
                if max(left[0], right[0]) < min(left[1], right[1]):
                    parallel_pairs.append([left[2], right[2]])
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "planId": plan["planId"],
            "planDigestSha256": run["planDigestSha256"],
            "createdAt": run["createdAt"],
            "finalizedAt": now(),
            "maxConcurrency": plan["maxConcurrency"],
            "parallelExecutionObserved": bool(parallel_pairs),
            "overlappingJobPairs": parallel_pairs,
            "jobs": [{
                "jobId": job_id,
                "batchIndex": state["batchIndex"],
                "dependencies": state["dependencies"],
                "attempts": state["attempts"],
                "requestSha256": state["requestSha256"],
                "invocationId": state.get("invocationId"),
                "providerRequestId": state.get("providerRequestId"),
                "startedAt": state["startedAt"],
                "finishedAt": state["finishedAt"],
                "output": state["output"],
            } for job_id, state in sorted(states.items())],
        }
        receipt["receiptDigestSha256"] = digest_value(receipt)
        atomic_json(path, receipt)
        event(run_dir, "run-finalized", receiptSha256=digest_file(path))
        return {"ok": True, "receipt": str(path), **receipt}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("plan")
    init.add_argument("run_dir")
    ready = commands.add_parser("ready")
    ready.add_argument("run_dir")
    bind_request = commands.add_parser("bind-request")
    bind_request.add_argument("run_dir")
    bind_request.add_argument("job_id")
    bind_request.add_argument("request")
    start = commands.add_parser("start")
    start.add_argument("run_dir")
    start.add_argument("job_id")
    succeed = commands.add_parser("succeed")
    succeed.add_argument("run_dir")
    succeed.add_argument("job_id")
    succeed.add_argument("image")
    succeed.add_argument("--invocation-id")
    succeed.add_argument("--provider-request-id")
    fail = commands.add_parser("fail")
    fail.add_argument("run_dir")
    fail.add_argument("job_id")
    fail.add_argument("--reason", required=True)
    fail.add_argument("--retryable", action="store_true")
    recover = commands.add_parser("recover")
    recover.add_argument("run_dir")
    recover.add_argument("--stale-seconds", type=int, default=900)
    status = commands.add_parser("status")
    status.add_argument("run_dir")
    finalize = commands.add_parser("finalize")
    finalize.add_argument("run_dir")
    return root


def main() -> int:
    args = parser().parse_args()
    handler = globals()[f"cmd_{args.command.replace('-', '_')}"]
    print(json.dumps(handler(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
