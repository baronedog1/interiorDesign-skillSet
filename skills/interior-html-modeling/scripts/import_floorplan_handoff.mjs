#!/usr/bin/env node
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { compileModelScope } from "./model_scope_contract.mjs";

const REQUIRED_ARTIFACTS = new Set([
  "sourceImage",
  "sourceEvidence",
  "sourceEvidenceOverlay",
  "evidenceOverlay_wallsOpenings",
  "evidenceOverlay_wallsOpeningsReview",
  "evidenceOverlay_roomLabelsDividers",
  "evidenceOverlay_roomLabelsDividersReview",
  "evidenceOverlay_objects",
  "evidenceOverlay_objectsReview",
  "semanticDecisions",
  "wallGeometry",
  "agentVisualReview",
  "visualOverlay",
  "roomContactSheet",
  "traceSpec",
  "quadrantsImage",
  "structureImage",
  "classifiedOverlay",
  "traceCombinationImage",
  "structureData",
  "traceComponents",
]);
const REQUIRED_REPORTS = new Set(["sourceModelValidation"]);

function fail(message) {
  console.error(message);
  process.exit(1);
}

function option(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function oneEditOrEqual(left, right) {
  if (left === right) return true;
  if (Math.abs(left.length - right.length) > 1) return false;
  if (left.length === right.length) {
    return [...left].filter((character, index) => character !== right[index]).length <= 1;
  }
  const [shorter, longer] = left.length < right.length ? [left, right] : [right, left];
  let shortIndex = 0;
  let longIndex = 0;
  let edits = 0;
  while (shortIndex < shorter.length && longIndex < longer.length) {
    if (shorter[shortIndex] === longer[longIndex]) {
      shortIndex += 1;
      longIndex += 1;
    } else {
      edits += 1;
      longIndex += 1;
      if (edits > 1) return false;
    }
  }
  return true;
}

function compatibleFloorplanProducer(producer) {
  return producer?.skill === "interior-floorplan-planning"
    && /^6\.[0-9]+\.[0-9]+$/.test(String(producer?.version || ""));
}

function discoverRoleEntries(entries, requiredRoles, label) {
  const discovered = {};
  const warnings = [];
  for (const role of requiredRoles) {
    const candidates = Object.entries(entries || {}).filter(([key, value]) => (
      oneEditOrEqual(key, role) && value && typeof value === "object"
    ));
    if (!candidates.length) {
      fail(`${label}/${role}: 未发现语义对应产物；请先询问用户是否已有该文件，并请求上传或提供实际路径`);
    }
    const digests = new Set(candidates.map(([, value]) => canonical(value)));
    if (digests.size > 1) {
      fail(`${label}/${role}: 存在内容冲突的近似字段 ${candidates.map(([key]) => key).join(", ")}；必须询问用户选择`);
    }
    const selected = candidates.find(([key]) => key === role) || candidates.sort(([a], [b]) => a.localeCompare(b))[0];
    discovered[role] = selected[1];
    if (selected[0] !== role) warnings.push(`${label}.${selected[0]} normalized to ${label}.${role}`);
  }
  return { discovered, warnings };
}

function filesBelow(root, limit = 5000) {
  const files = [];
  const pending = [root];
  while (pending.length) {
    const directory = pending.pop();
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const candidate = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) pending.push(candidate);
      else if (entry.isFile()) files.push(candidate);
      if (files.length > limit) fail(`handoff discovery exceeds ${limit} files; narrow the task workspace or provide the path`);
    }
  }
  return files;
}

function resolveEntry(root, entry, label, discoveryLog) {
  if (!entry || typeof entry.path !== "string") fail(`${label}: path is required`);
  let direct = null;
  if (!path.isAbsolute(entry.path) && !entry.path.split(/[\\/]/).includes("..")) {
    const candidate = path.resolve(root, entry.path);
    if (candidate === root || candidate.startsWith(`${root}${path.sep}`)) direct = candidate;
  }
  if (
    direct
    && fs.statSync(direct, { throwIfNoEntry: false })?.isFile()
    && sha256(direct) === entry.sha256
    && fs.statSync(direct).size === entry.bytes
  ) return direct;
  const matches = filesBelow(root).filter((candidate) => (
    fs.statSync(candidate).size === entry.bytes && sha256(candidate) === entry.sha256
  ));
  if (!matches.length) {
    fail(`${label}: manifest 推荐路径不可用，且工作区内未发现同哈希产物；请先询问用户是否有该文件`);
  }
  matches.sort((first, second) => first.length - second.length || first.localeCompare(second));
  discoveryLog.push({ label, recommendedPath: entry.path, resolvedPath: path.relative(root, matches[0]), equivalentCopies: matches.length });
  return matches[0];
}

const manifestArg = option("--handoff");
const outArg = option("--out");
if (!manifestArg || !outArg) {
  fail("usage: import_floorplan_handoff.mjs --handoff <floorplan-handoff.json> [--model-scope <model-scope-request.json>] --out <empty-project-dir>");
}
const manifestPath = path.resolve(manifestArg);
const handoffRoot = path.dirname(manifestPath);
const out = path.resolve(outArg);
const skillRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
if (!fs.statSync(manifestPath, { throwIfNoEntry: false })?.isFile()) fail(`handoff manifest is missing: ${manifestPath}`);
if (fs.existsSync(out) && fs.readdirSync(out).length) fail(`target is not empty: ${out}`);

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
if (manifest.schema !== "interior.floorplan-handoff.v3") fail("only interior.floorplan-handoff.v3 is accepted");
if (!compatibleFloorplanProducer(manifest.producer)) {
  fail("handoff producer must be a schema-compatible interior-floorplan-planning 6.x release");
}
const layoutAuthority = manifest.layoutAuthority;
if (layoutAuthority?.schema !== "interior.floorplan-layout-authority.v1") {
  fail("handoff requires interior.floorplan-layout-authority.v1");
}
if (!["source-furnished", "native-layout-furnished"].includes(layoutAuthority.mode)) {
  fail(`unsupported layoutAuthority.mode ${layoutAuthority.mode}`);
}
const requiredArtifacts = new Set(REQUIRED_ARTIFACTS);
if (layoutAuthority.mode === "native-layout-furnished") {
  requiredArtifacts.add("nativeLayout");
} else if (manifest.artifacts?.nativeLayout) {
  fail("source-furnished handoff must not carry a redundant nativeLayout artifact");
}
const digestPayload = structuredClone(manifest);
delete digestPayload.handoffDigestSha256;
const manifestDigest = crypto.createHash("sha256").update(canonical(digestPayload)).digest("hex");
if (manifestDigest !== manifest.handoffDigestSha256) fail("handoff manifest digest mismatch");
const artifactRoles = discoverRoleEntries(manifest.artifacts, requiredArtifacts, "artifact");
const reportRoles = discoverRoleEntries(manifest.reports, REQUIRED_REPORTS, "report");
if (!Object.values(manifest.validation || {}).length || Object.values(manifest.validation).some((value) => value !== true)) {
  fail("handoff source-model and Agent visual review must both pass");
}

const artifactPathDiscoveries = [];
const artifacts = Object.fromEntries(
  Object.entries(artifactRoles.discovered).map(([key, entry]) => [key, resolveEntry(handoffRoot, entry, `artifact/${key}`, artifactPathDiscoveries)]),
);
const reports = Object.fromEntries(
  Object.entries(reportRoles.discovered).map(([key, entry]) => [key, resolveEntry(handoffRoot, entry, `report/${key}`, artifactPathDiscoveries)]),
);
const structure = JSON.parse(fs.readFileSync(artifacts.structureData, "utf8"));
const traceSpec = JSON.parse(fs.readFileSync(artifacts.traceSpec, "utf8"));
const traceComponents = JSON.parse(fs.readFileSync(artifacts.traceComponents, "utf8"));
for (const [label, data] of Object.entries({ structure, traceSpec, traceComponents })) {
  if (data.floorplanId !== manifest.floorplanId) fail(`${label} floorplanId does not match handoff`);
}
if (structure.schema !== "interior.floorplan-structure.v3") fail("structure-data schema is invalid");
if (traceSpec.schema !== "interior.floorplan-trace.v3") fail("trace-spec schema is invalid");
if (traceComponents.schema !== "interior.trace-components.v2") fail("trace-components schema is invalid");
const modelScopeRequestArg = option("--model-scope");
const modelScopeRequest = modelScopeRequestArg
  ? JSON.parse(fs.readFileSync(path.resolve(modelScopeRequestArg), "utf8"))
  : null;
let modelScope;
try {
  modelScope = compileModelScope(modelScopeRequest, structure, {
    floorplanId: manifest.floorplanId,
    handoffDigestSha256: manifest.handoffDigestSha256,
    structureDataSha256: artifactRoles.discovered.structureData.sha256,
  });
} catch (error) {
  fail(`model scope rejected: ${error.message}`);
}

const sourceModelReport = JSON.parse(fs.readFileSync(reports.sourceModelValidation, "utf8"));
if (
  sourceModelReport.schema !== "interior.floorplan-source-model-validation.v1"
  || sourceModelReport.passed !== true
  || (sourceModelReport.errors || []).length
  || sourceModelReport.traceSpecSha256 !== artifactRoles.discovered.traceSpec.sha256
) {
  fail("sourceModelValidation is not a clean report for this trace spec");
}
for (const field of ["missedPixels", "outsidePixels", "overlapCorePixels"]) {
  if (sourceModelReport.independentFloorMetrics?.[field] !== 0) fail(`independent floor metric ${field} must be zero`);
}
if (
  sourceModelReport.objectMetrics?.acceptedObjects !== (traceComponents.objects || []).length
  || sourceModelReport.objectMetrics?.traceComponents !== (traceComponents.objects || []).length
) {
  fail("source object evidence and trace-components counts differ");
}

const structureRegistry = new Set(manifest.sourceTraceRegistry?.structureTraceIds || []);
for (const item of [...(structure.walls || []), ...(structure.windows || [])]) {
  if (!item.sourceTraceIds?.length) fail(`${item.id}: sourceTraceIds are required`);
  for (const traceId of item.sourceTraceIds) {
    if (!structureRegistry.has(traceId)) fail(`${item.id}: unresolved sourceTraceId ${traceId}`);
  }
}
for (const item of structure.connections || []) {
  const physicalIds = item.sourceTraceIds || [];
  const dividerIds = item.sourceDividerIds || [];
  if (Boolean(physicalIds.length) === Boolean(dividerIds.length)) {
    fail(`${item.id}: connection needs exactly one physical-opening or semantic-divider source`);
  }
  for (const traceId of [...physicalIds, ...dividerIds]) {
    if (!structureRegistry.has(traceId)) fail(`${item.id}: unresolved structure source ID ${traceId}`);
  }
}
const componentRegistry = new Set(manifest.sourceTraceRegistry?.componentTraceIds || []);
const componentTraceIds = new Set((traceComponents.objects || []).map((item) => item.traceId));
if (componentRegistry.size !== componentTraceIds.size || ![...componentRegistry].every((item) => componentTraceIds.has(item))) {
  fail("component trace registry differs from trace-components");
}
const objectRegistry = new Set(manifest.sourceTraceRegistry?.sourceObjectCandidateIds || []);
const objectCandidateIds = new Set();
for (const item of traceComponents.objects || []) {
  if (!componentRegistry.has(item.traceId)) fail(`trace-components: unresolved traceId ${item.traceId}`);
  if (!item.sourceObjectCandidateId) fail(`${item.traceId}: sourceObjectCandidateId is required`);
  if (objectCandidateIds.has(item.sourceObjectCandidateId)) {
    fail(`${item.traceId}: sourceObjectCandidateId is duplicated`);
  }
  objectCandidateIds.add(item.sourceObjectCandidateId);
}
if (objectRegistry.size !== objectCandidateIds.size || ![...objectRegistry].every((item) => objectCandidateIds.has(item))) {
  fail("source object candidate registry differs from trace-components");
}

const structureValidation = spawnSync(
  "python3",
  [
    path.join(skillRoot, "scripts", "validate_structure_data.py"),
    "--handoff",
    manifestPath,
    artifacts.structureData,
  ],
  { encoding: "utf8" },
);
if (structureValidation.status !== 0) {
  fail(
    "compiled room topology was rejected before template import:\n"
    + (structureValidation.stderr || structureValidation.stdout || "unknown structure validation error"),
  );
}

fs.mkdirSync(out, { recursive: true });
fs.cpSync(path.join(skillRoot, "assets", "base-floorplan-template"), out, { recursive: true });
fs.cpSync(path.join(skillRoot, "assets", "component-library"), path.join(out, "component-library"), { recursive: true });
fs.rmSync(path.join(out, "component-layout.json"), { force: true });
fs.rmSync(path.join(out, "component-assets.lock.json"), { force: true });
fs.cpSync(handoffRoot, path.join(out, "floorplan-handoff"), { recursive: true });
fs.copyFileSync(artifacts.structureData, path.join(out, "structure-data.json"));
fs.copyFileSync(artifacts.traceComponents, path.join(out, "trace-components.json"));
fs.copyFileSync(artifacts.structureImage, path.join(out, "structure-source.png"));
fs.writeFileSync(path.join(out, "model-scope.json"), `${JSON.stringify(modelScope, null, 2)}\n`);

const receipt = {
  schema: "interior.floorplan-import-receipt.v1",
  floorplanId: manifest.floorplanId,
  handoffDigestSha256: manifest.handoffDigestSha256,
  handoffManifestSha256: sha256(manifestPath),
  structureDataSha256: artifactRoles.discovered.structureData.sha256,
  traceComponentsSha256: artifactRoles.discovered.traceComponents.sha256,
  layoutAuthority,
  importer: {
    skill: "interior-html-modeling",
    version: "17.0.0",
  },
  modelScope: {
    mode: modelScope.mode,
    requestedRoomIds: modelScope.requestedRoomIds,
    allowedContextRoomIds: modelScope.allowedContextRoomIds,
    excludedRoomIds: modelScope.excludedRoomIds,
    scopeDigestSha256: modelScope.scopeDigestSha256,
  },
  artifactDiscovery: {
    policy: "semantic-content-first-v1",
    roleNormalizations: [...artifactRoles.warnings, ...reportRoles.warnings],
    recoveredPaths: artifactPathDiscoveries,
    recommendedPathsAreHintsOnly: true,
  },
};
fs.writeFileSync(path.join(out, "floorplan-import-receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`);
console.log(JSON.stringify({
  ok: true,
  out,
  floorplanId: manifest.floorplanId,
  handoffDigestSha256: manifest.handoffDigestSha256,
  next: "run match_trace_components.mjs, then validate structure and component layout",
}, null, 2));
