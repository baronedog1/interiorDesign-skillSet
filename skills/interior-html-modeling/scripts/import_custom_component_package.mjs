#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const [projectArg, packageArg] = process.argv.slice(2);
if (!projectArg || !packageArg) {
  throw new Error("usage: import_custom_component_package.mjs <project-dir> <custom-component-package.json>");
}

const projectDir = path.resolve(projectArg);
const sourceManifest = path.resolve(packageArg);
const sourceRoot = path.dirname(sourceManifest);
const manifestBytes = fs.readFileSync(sourceManifest);
const manifest = JSON.parse(manifestBytes.toString("utf8"));
const HEX_64 = /^[a-f0-9]{64}$/;
const REQUIRED_KEYS = [
  "appearance",
  "bindings",
  "browserQa",
  "carvingPlan",
  "evidence",
  "packageId",
  "packageSha256",
  "placementClass",
  "projectionReport",
  "schema",
  "standalone",
  "status",
  "visualHullState",
];

function sha256Bytes(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function sha256File(filePath) {
  return sha256Bytes(fs.readFileSync(filePath));
}

function canonicalValue(value, omittedKeys = new Set()) {
  if (Array.isArray(value)) return value.map((item) => canonicalValue(item, omittedKeys));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .filter((key) => !omittedKeys.has(key))
        .sort()
        .map((key) => [key, canonicalValue(value[key], omittedKeys)]),
    );
  }
  return value;
}

function canonicalSha256(value, omittedKeys = new Set()) {
  return sha256Bytes(Buffer.from(JSON.stringify(canonicalValue(value, omittedKeys)), "utf8"));
}

function safePackagePath(relative, label) {
  if (typeof relative !== "string" || !relative || path.isAbsolute(relative)) {
    throw new Error(`${label} must be a relative package path`);
  }
  const resolved = path.resolve(sourceRoot, relative);
  if (!resolved.startsWith(`${sourceRoot}${path.sep}`)) {
    throw new Error(`${label} escapes the package root`);
  }
  const stat = fs.lstatSync(resolved);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`${label} must be a regular package file`);
  }
  return resolved;
}

const manifestKeys = Object.keys(manifest).sort();
if (JSON.stringify(manifestKeys) !== JSON.stringify(REQUIRED_KEYS)) {
  throw new Error(`component package has an unexpected field graph: ${manifestKeys.join(",")}`);
}
if (manifest.schema !== "interior.custom-component-package.v3") {
  throw new Error("only interior.custom-component-package.v3 is supported");
}
if (!/^[a-z0-9][a-z0-9-]*$/.test(manifest.packageId || "")) throw new Error("invalid packageId");
if (!["movable-green", "fixed-purple"].includes(manifest.placementClass)) throw new Error("invalid placementClass");
if (manifest.status !== "accepted") throw new Error("only accepted component packages can be imported");
if (manifest.appearance?.defaultMode !== "white-model") throw new Error("package must default to white-model");
if (JSON.stringify(manifest.appearance?.supportedModes) !== JSON.stringify(["white-model", "source-color"])) {
  throw new Error("package must support exactly white-model then source-color");
}
if (manifest.appearance?.sourceColorAuthority !== "visualHullState.components[].material") {
  throw new Error("package source-color authority must be the visual-hull state");
}
if (!HEX_64.test(manifest.appearance?.geometryStateSha256 || "")) throw new Error("invalid geometry state binding");
if (!HEX_64.test(manifest.packageSha256 || "")
    || manifest.packageSha256 !== canonicalSha256(manifest, new Set(["packageSha256"]))) {
  throw new Error("component package canonical SHA-256 mismatch");
}

const filesToCopy = new Map();
function validateArtifact(descriptor, label) {
  if (!descriptor || JSON.stringify(Object.keys(descriptor).sort()) !== JSON.stringify(["path", "sha256"])) {
    throw new Error(`${label} must contain only path and sha256`);
  }
  if (!HEX_64.test(descriptor.sha256 || "")) throw new Error(`${label} has an invalid SHA-256`);
  const resolved = safePackagePath(descriptor.path, label);
  if (sha256File(resolved) !== descriptor.sha256) throw new Error(`${label} file hash mismatch`);
  filesToCopy.set(descriptor.path, resolved);
  return resolved;
}

const planPath = validateArtifact(manifest.carvingPlan, "carvingPlan");
const statePath = validateArtifact(manifest.visualHullState, "visualHullState");
const reportPath = validateArtifact(manifest.projectionReport, "projectionReport");
const standalonePath = validateArtifact(manifest.standalone, "standalone");
const browserQaPath = validateArtifact(manifest.browserQa, "browserQa");
if (!Array.isArray(manifest.evidence) || manifest.evidence.length === 0) {
  throw new Error("component package has no source-backed evidence");
}

const plan = JSON.parse(fs.readFileSync(planPath, "utf8"));
const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
const browserQa = JSON.parse(fs.readFileSync(browserQaPath, "utf8"));
if (plan.schema !== "interior.product-multi-view-carving-plan.v1") throw new Error("unsupported carving plan");
if (state.schema !== "interior.product-visual-hull-state.v1" || state.status !== "candidate") {
  throw new Error("an accepted package must bind the immutable non-inferred carving candidate");
}
if (state.components?.some((component) => component.inferenceFlags?.length)) {
  throw new Error("an accepted package cannot contain inferred component geometry");
}
if (report.schema !== "interior.product-zero-xor-projection-report.v1" || report.pass !== true) {
  throw new Error("component package projection report did not pass");
}

const bindings = manifest.bindings || {};
for (const key of ["planCanonicalSha256", "stateCanonicalSha256", "projectionReportCanonicalSha256", "browserQaCanonicalSha256"]) {
  if (!HEX_64.test(bindings[key] || "")) throw new Error(`invalid package binding: ${key}`);
}
if (bindings.planCanonicalSha256 !== state.planSha256 || bindings.planCanonicalSha256 !== report.planSha256) {
  throw new Error("carving plan binding differs between state and projection report");
}
if (bindings.stateCanonicalSha256 !== state.stateSha256
    || bindings.stateCanonicalSha256 !== report.stateSha256
    || bindings.stateCanonicalSha256 !== manifest.appearance.geometryStateSha256) {
  throw new Error("visual-hull state binding differs across package artifacts");
}
if (bindings.projectionReportCanonicalSha256 !== report.reportSha256) {
  throw new Error("projection report canonical binding mismatch");
}
if (bindings.browserQaCanonicalSha256 !== browserQa.canonicalSha256
    || browserQa.schema !== "interior.product-browser-qa.v1"
    || browserQa.pass !== true
    || browserQa.errors?.length
    || browserQa.stateSha256 !== state.stateSha256
    || browserQa.standaloneSha256 !== manifest.standalone.sha256) {
  throw new Error("browser QA is missing, failed or not bound to the package artifacts");
}
for (const viewport of [browserQa.desktop, browserQa.mobile]) {
  if (viewport?.pass !== true || viewport.canvasNonBlank !== true
      || viewport.consoleErrorCount !== 0 || viewport.webglErrorCount !== 0 || viewport.overflowPx !== 0) {
    throw new Error("browser QA contains a failed viewport");
  }
}
if (report.gate?.xorPixels !== 0
    || report.views?.some((view) => view.pass !== true
      || view.assembly?.xorPixels !== 0
      || view.components?.some((component) => component.xorPixels !== 0))) {
  throw new Error("projection report contains a non-zero source-view difference");
}

const references = new Map((plan.evidence || []).map((item) => [item.viewId, item]));
if (references.size !== plan.evidence?.length || references.size !== manifest.evidence.length) {
  throw new Error("package evidence views do not match the carving plan");
}
const evidenceViewIds = new Set();
for (const item of manifest.evidence) {
  if (!item || JSON.stringify(Object.keys(item).sort()) !== JSON.stringify(["regionEvidence", "sourceImage", "viewId"])) {
    throw new Error("evidence entry has an unexpected field graph");
  }
  if (!item.viewId || evidenceViewIds.has(item.viewId) || !references.has(item.viewId)) {
    throw new Error(`invalid or duplicate evidence viewId: ${item.viewId}`);
  }
  evidenceViewIds.add(item.viewId);
  const evidencePath = validateArtifact(item.regionEvidence, `evidence.${item.viewId}`);
  const sourceImagePath = validateArtifact(item.sourceImage, `sourceImage.${item.viewId}`);
  const expectedEvidencePath = path.resolve(path.dirname(planPath), references.get(item.viewId).path);
  if (evidencePath !== expectedEvidencePath) throw new Error(`plan path differs for evidence ${item.viewId}`);
  const evidence = JSON.parse(fs.readFileSync(evidencePath, "utf8"));
  if (evidence.schema !== "interior.product-view-region-evidence.v1" || evidence.viewId !== item.viewId) {
    throw new Error(`invalid source-backed region evidence for ${item.viewId}`);
  }
  if (path.resolve(path.dirname(evidencePath), evidence.source?.path || "") !== sourceImagePath
      || evidence.source?.sha256 !== item.sourceImage.sha256) {
    throw new Error(`source image binding differs for ${item.viewId}`);
  }
}

const standaloneSource = fs.readFileSync(standalonePath, "utf8");
if (!standalonePath.toLowerCase().endsWith(".html")
    || !standaloneSource.includes("__PRODUCT_STANDALONE_READY__")
    || !standaloneSource.includes("__PRODUCT_APPEARANCE__")
    || !standaloneSource.includes(state.stateSha256)) {
  throw new Error("package standalone HTML is not bound to the accepted visual-hull state");
}
const externalDependencyPatterns = [
  /<(?:script|img|iframe|source|video|audio)\b[^>]*\bsrc\s*=\s*["']https?:\/\//i,
  /<link\b[^>]*\bhref\s*=\s*["']https?:\/\//i,
  /\b(?:import\s*(?:\(|[^;]*?from\s*)|fetch\s*\(|new\s+Worker\s*\()\s*["']https?:\/\//i,
  /url\(\s*["']?https?:\/\//i,
];
if (externalDependencyPatterns.some((pattern) => pattern.test(standaloneSource))
    || standaloneSource.includes("/home/")) {
  throw new Error("package standalone HTML contains an external or local absolute dependency");
}

const customRoot = path.join(projectDir, "custom-components");
const targetRoot = path.join(customRoot, manifest.packageId);
if (fs.existsSync(targetRoot)) throw new Error(`package already exists: ${manifest.packageId}`);
const registryPath = path.join(customRoot, "registry.json");
const registry = fs.existsSync(registryPath)
  ? JSON.parse(fs.readFileSync(registryPath, "utf8"))
  : { schema: "interior.custom-component-registry.v3", packages: [] };
if (registry.schema !== "interior.custom-component-registry.v3" || !Array.isArray(registry.packages)) {
  throw new Error("only interior.custom-component-registry.v3 is supported");
}
if (registry.packages.some((item) => item.packageId === manifest.packageId)) throw new Error("duplicate packageId");

const temporaryRoot = `${targetRoot}.tmp-${process.pid}`;
fs.mkdirSync(customRoot, { recursive: true });
fs.mkdirSync(temporaryRoot, { recursive: false });
try {
  for (const [relative, source] of filesToCopy) {
    const target = path.join(temporaryRoot, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(source, target, fs.constants.COPYFILE_EXCL);
  }
  fs.copyFileSync(sourceManifest, path.join(temporaryRoot, "custom-component-package.json"), fs.constants.COPYFILE_EXCL);
  fs.renameSync(temporaryRoot, targetRoot);
} catch (error) {
  fs.rmSync(temporaryRoot, { recursive: true, force: true });
  throw error;
}

registry.packages.push({
  packageId: manifest.packageId,
  placementClass: manifest.placementClass,
  manifestPath: path.posix.join("custom-components", manifest.packageId, "custom-component-package.json"),
  standaloneHtmlPath: path.posix.join("custom-components", manifest.packageId, manifest.standalone.path),
  manifestSha256: sha256Bytes(manifestBytes),
  packageSha256: manifest.packageSha256,
  geometryStateSha256: state.stateSha256,
  evidenceViewIds: [...evidenceViewIds].sort(),
  scope: "current-project",
  enabled: true,
  defaultAppearanceMode: "white-model",
  supportedAppearanceModes: ["white-model", "source-color"],
});
registry.packages.sort((a, b) => a.packageId.localeCompare(b.packageId));
const registryTemporary = `${registryPath}.tmp-${process.pid}`;
fs.writeFileSync(registryTemporary, `${JSON.stringify(registry, null, 2)}\n`);
fs.renameSync(registryTemporary, registryPath);

const registryEntry = registry.packages.find((item) => item.packageId === manifest.packageId);
console.log(JSON.stringify({
  ok: true,
  packageId: manifest.packageId,
  registryPath,
  packageSha256: manifest.packageSha256,
  geometryStateSha256: state.stateSha256,
  evidenceViewIds: registryEntry.evidenceViewIds,
  standaloneHtmlPath: registryEntry.standaloneHtmlPath,
}));
