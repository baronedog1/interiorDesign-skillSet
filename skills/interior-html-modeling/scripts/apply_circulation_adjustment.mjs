#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || !value) throw new Error(`invalid argument near ${key || "<end>"}`);
    result[key.slice(2)] = value;
  }
  for (const key of ["layout", "plan", "out"]) {
    if (!result[key]) throw new Error(`--${key} is required`);
  }
  return result;
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value) {
  return createHash("sha256").update(canonical(value), "utf8").digest("hex");
}

function operationDigest(operation) {
  const target = operation.target || {};
  const material = {
    backend: String(operation.backend || ""),
    operation: String(operation.operation || ""),
    targetId: String(operation.targetPlacementId || operation.targetEntityId || ""),
    position: (target.position || []).map((value) => Number(value).toFixed(6)),
    rotationYRadians: Number(target.rotationYRadians || 0).toFixed(9),
  };
  return digest(material);
}

function planExecutionDigest(plan) {
  return digest({
    schema: String(plan.schema || ""),
    floorplanId: String(plan.floorplanId || ""),
    modelBackend: String(plan.modelBackend || ""),
    auditDigestSha256: String(plan.bindings?.auditDigestSha256 || ""),
    circulationSceneSha256: String(plan.bindings?.circulationSceneSha256 || ""),
    inputStateDigestSha256: String(plan.inputStateDigestSha256 || ""),
    workflowStatus: String(plan.workflowStatus || ""),
    selectedCandidateId: String(plan.automaticDecision?.selectedCandidateId || ""),
    operationDigestSha256: String(plan.automaticDecision?.operationDigestSha256 || ""),
  });
}

function close(left, right, tolerance = 1e-6) {
  return Number.isFinite(Number(left))
    && Number.isFinite(Number(right))
    && Math.abs(Number(left) - Number(right)) <= tolerance;
}

function samePosition(left, right) {
  return Array.isArray(left)
    && Array.isArray(right)
    && left.length === 2
    && right.length === 2
    && left.every((value, index) => close(value, right[index]));
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const layoutPath = path.resolve(args.layout);
  const planPath = path.resolve(args.plan);
  const outPath = path.resolve(args.out);
  const layout = await readJson(layoutPath);
  const plan = await readJson(planPath);
  if (layout.schema !== "interior.component-layout.v4") {
    throw new Error("layout must use interior.component-layout.v4");
  }
  if (plan.schema !== "interior.circulation-adjustment-plan.v2") {
    throw new Error("plan must use interior.circulation-adjustment-plan.v2");
  }
  const declaredPlanDigest = plan.planDigestSha256;
  if (plan.planDigestScope !== "bound-input-state-and-selected-operation-v1"
      || declaredPlanDigest !== planExecutionDigest(plan)) {
    throw new Error("planDigestSha256 is invalid");
  }
  const decision = plan.automaticDecision;
  if (decision?.action !== "apply-without-user-confirmation" || !decision.selectedCandidateId) {
    throw new Error("plan does not authorize one deterministic correction");
  }
  const candidate = plan.candidates?.find((row) => row.candidateId === decision.selectedCandidateId);
  if (!candidate) throw new Error("selected candidate is absent from plan.candidates");
  if (candidate.operationDigestSha256 !== decision.operationDigestSha256
      || operationDigest(candidate.backendOperation) !== candidate.operationDigestSha256) {
    throw new Error("selected operation digest is invalid");
  }
  const operation = candidate.backendOperation;
  if (operation.backend !== "html-threejs" || operation.operation !== "set-component-plan-transform") {
    throw new Error("selected operation is not an HTML backend transform");
  }
  const placement = layout.placements?.find((row) => row.id === operation.targetPlacementId);
  if (!placement) throw new Error(`unknown target placement: ${operation.targetPlacementId}`);
  if (placement.reviewedAdjustment?.authority === "user-explicit-layout-correction") {
    throw new Error("deterministic correction may not override an explicit user transform");
  }
  if (!samePosition(placement.position, candidate.previousPlanCenter)
      || !close(placement.rotationY || 0, candidate.previousRotationYRadians || 0)) {
    throw new Error("layout active transform differs from the audited candidate input");
  }
  const targetPosition = operation.target?.position;
  const targetRotation = operation.target?.rotationYRadians;
  if (!samePosition(targetPosition, candidate.targetPlanCenter)
      || !close(targetRotation, candidate.targetRotationYRadians)) {
    throw new Error("backend operation and candidate target differ");
  }
  const sourcePosition = placement.sourcePosition;
  const sourceRotation = Number(placement.sourceRotationY || 0);
  const changedFields = [];
  if (!samePosition(targetPosition, sourcePosition)) changedFields.push("position");
  if (!close(targetRotation, sourceRotation)) changedFields.push("rotationY");
  if (!changedFields.length) throw new Error("selected correction would reproduce the immutable source transform");

  placement.position = targetPosition.map(Number);
  placement.rotationY = Number(targetRotation);
  placement.traceLock = {
    ...(placement.traceLock || {}),
    position: !changedFields.includes("position"),
    rotation: !changedFields.includes("rotationY"),
  };
  placement.reviewedAdjustment = {
    schema: "interior.reviewed-layout-adjustment.v1",
    authority: "circulation-deterministic-correction",
    sourceAuditDigestSha256: plan.bindings.auditDigestSha256,
    adjustmentPlanDigestSha256: declaredPlanDigest,
    candidateId: candidate.candidateId,
    operationDigestSha256: candidate.operationDigestSha256,
    reasonCode: candidate.correctionKind,
    reason: "Deterministic circulation algorithm selected the minimum reversible valid transform.",
    changedFields,
    previous: {
      position: sourcePosition.map(Number),
      rotationY: sourceRotation,
    },
    active: {
      position: placement.position,
      rotationY: placement.rotationY,
    },
  };
  await writeFile(outPath, `${JSON.stringify(layout, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify({
    schema: "interior.html-circulation-adjustment-receipt.v1",
    accepted: true,
    layoutPath,
    outputPath: outPath,
    planPath,
    planDigestSha256: declaredPlanDigest,
    candidateId: candidate.candidateId,
    operationDigestSha256: candidate.operationDigestSha256,
    confirmationRequested: false,
  }, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`circulation adjustment rejected: ${error.message}\n`);
  process.exitCode = 1;
});
