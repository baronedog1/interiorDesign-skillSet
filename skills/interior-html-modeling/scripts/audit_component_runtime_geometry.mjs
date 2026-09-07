#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

function option(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function canonicalSha256(value) {
  return crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

function fitFrame(authored, measured, frame) {
  const width = frame === "quarter-turn" ? measured.depth : measured.width;
  const depth = frame === "quarter-turn" ? measured.width : measured.depth;
  const ratios = [
    authored.width / width,
    authored.height / measured.height,
    authored.depth / depth,
  ];
  const canonicalScale = median(ratios);
  const ratioSpread = (Math.max(...ratios) - Math.min(...ratios)) / canonicalScale;
  return { frame, canonicalScale, ratioSpread, ratios };
}

function round(value, digits = 8) {
  return Number(Number(value).toFixed(digits));
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

const scriptRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const assetStore = path.resolve(option(
  "--asset-store",
  process.env.INTERIOR_COMPONENT_ASSET_STORE
    || "/home/agentops/agent-runtime/shared-assets/interior-component-library-v6",
));
const toolsRoot = path.resolve(option("--tools-root", path.join(assetStore, "tools")));
const outputPath = path.resolve(option("--out", path.join(scriptRoot, "runtime-geometry-audit.v1.json")));
const modulePath = path.resolve(option(
  "--module-out",
  path.join(scriptRoot, "assets/component-library/catalog/runtime-geometry-admission.v1.js"),
));
const catalogPath = path.join(scriptRoot, "assets/component-library/catalog/public-assets.json");
const inventoryPath = path.join(assetStore, "catalog/asset-store-inventory.json");
const packagePath = path.join(toolsRoot, "package.json");

for (const required of [catalogPath, inventoryPath, packagePath]) {
  if (!fs.statSync(required, { throwIfNoEntry: false })?.isFile()) fail(`missing required file: ${required}`);
}

const requireFromTools = createRequire(pathToFileURL(packagePath));
const { NodeIO, getBounds } = requireFromTools("@gltf-transform/core");
const { ALL_EXTENSIONS } = requireFromTools("@gltf-transform/extensions");
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8"));
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
if (catalog.schema !== "interior.public-component-catalog.v5") fail("unsupported component catalog");
if (inventory.schema !== "interior.public-component-asset-store.v1") fail("unsupported asset inventory");
if (catalog.catalogDigestSha256 !== inventory.catalogDigestSha256) {
  fail("component catalog and asset inventory digests differ");
}

const receipts = new Map(inventory.results.map((row) => [row.id, row]));
const rows = [];
const started = Date.now();
for (const [index, asset] of catalog.assets.entries()) {
  const receipt = receipts.get(asset.id);
  if (!receipt?.ok || !receipt.runtimePath) {
    rows.push({ assetId: asset.id, status: "rejected", reason: "missing-validated-runtime-receipt" });
    continue;
  }
  const runtimePath = path.join(assetStore, receipt.runtimePath);
  try {
    const document = await io.read(runtimePath);
    const scenes = document.getRoot().listScenes();
    if (!scenes.length) throw new Error("GLB has no scene");
    const sceneBounds = scenes.map((scene) => getBounds(scene));
    const minimum = [0, 1, 2].map((axis) => Math.min(...sceneBounds.map((bounds) => bounds.min[axis])));
    const maximum = [0, 1, 2].map((axis) => Math.max(...sceneBounds.map((bounds) => bounds.max[axis])));
    const measured = {
      width: maximum[0] - minimum[0],
      height: maximum[1] - minimum[1],
      depth: maximum[2] - minimum[2],
    };
    if (Object.values(measured).some((value) => !Number.isFinite(value) || value <= 0)) {
      throw new Error("GLB has invalid scene bounds");
    }
    const candidates = ["native", "quarter-turn"].map((frame) => (
      fitFrame(asset.defaultDimensions, measured, frame)
    ));
    candidates.sort((left, right) => left.ratioSpread - right.ratioSpread
      || (left.frame === "native" ? -1 : 1));
    const best = candidates[0];
    const accepted = Number.isFinite(best.canonicalScale)
      && best.canonicalScale > 0
      && best.ratioSpread <= 0.35;
    rows.push({
      assetId: asset.id,
      status: accepted ? "accepted" : "rejected",
      frame: best.frame,
      canonicalYawRadians: best.frame === "quarter-turn" ? Math.PI / 2 : 0,
      canonicalScale: round(best.canonicalScale),
      ratioSpread: round(best.ratioSpread),
      measuredBounds: Object.fromEntries(
        Object.entries(measured).map(([key, value]) => [key, round(value)]),
      ),
      authoredDimensions: asset.defaultDimensions,
      runtimePath: receipt.runtimePath,
      runtimeSha256: receipt.runtimeSha256,
      ...(accepted ? {} : { reason: "catalog-runtime-bounds-mismatch" }),
    });
  } catch (error) {
    rows.push({
      assetId: asset.id,
      status: "rejected",
      reason: "runtime-geometry-read-failed",
      error: error.message,
    });
  }
  if ((index + 1) % 50 === 0) process.stderr.write(`audited ${index + 1}/${catalog.assets.length}\n`);
}

const accepted = rows.filter((row) => row.status === "accepted");
const rejected = rows.filter((row) => row.status === "rejected");
const nonNative = accepted.filter((row) => row.frame !== "native");
const result = {
  schema: "interior.component-runtime-geometry-audit.v1",
  generatedAt: new Date().toISOString(),
  catalogDigestSha256: catalog.catalogDigestSha256,
  inventorySha256: crypto.createHash("sha256").update(fs.readFileSync(inventoryPath)).digest("hex"),
  assetCount: catalog.assets.length,
  acceptedCount: accepted.length,
  rejectedCount: rejected.length,
  quarterTurnCount: nonNative.length,
  elapsedMs: Date.now() - started,
  rows,
};
result.auditDigestSha256 = canonicalSha256({ ...result, auditDigestSha256: null });

const moduleDocument = {
  schema: "interior.component-runtime-geometry-admission.v1",
  catalogDigestSha256: result.catalogDigestSha256,
  auditDigestSha256: result.auditDigestSha256,
  assetCount: result.assetCount,
  acceptedCount: result.acceptedCount,
  rejectedCount: result.rejectedCount,
  nonDefaultFrames: nonNative.map((row) => ({
    assetId: row.assetId,
    frame: row.frame,
    canonicalYawRadians: round(row.canonicalYawRadians),
    canonicalScale: row.canonicalScale,
    ratioSpread: row.ratioSpread,
    runtimeSha256: row.runtimeSha256,
  })),
  rejectedAssets: rejected.map((row) => ({
    assetId: row.assetId,
    reason: row.reason,
    ...(row.error ? { error: row.error } : {}),
  })),
};
moduleDocument.admissionDigestSha256 = canonicalSha256({
  ...moduleDocument,
  admissionDigestSha256: null,
});

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`);
fs.mkdirSync(path.dirname(modulePath), { recursive: true });
fs.writeFileSync(
  modulePath,
  `// Generated by audit_component_runtime_geometry.mjs; do not edit manually.\n`
    + `export const RUNTIME_GEOMETRY_ADMISSION = Object.freeze(${JSON.stringify(moduleDocument, null, 2)});\n`
    + "export const RUNTIME_GEOMETRY_NON_DEFAULT_BY_ID = new Map(\n"
    + "  RUNTIME_GEOMETRY_ADMISSION.nonDefaultFrames.map((row) => [row.assetId, row]),\n"
    + ");\n"
    + "export const RUNTIME_GEOMETRY_REJECTED_ASSET_IDS = new Set(\n"
    + "  RUNTIME_GEOMETRY_ADMISSION.rejectedAssets.map((row) => row.assetId),\n"
    + ");\n",
);

console.log(JSON.stringify({
  ok: rows.length === catalog.assets.length,
  outputPath,
  modulePath,
  assetCount: result.assetCount,
  acceptedCount: result.acceptedCount,
  rejectedCount: result.rejectedCount,
  quarterTurnCount: result.quarterTurnCount,
  elapsedMs: result.elapsedMs,
  auditDigestSha256: result.auditDigestSha256,
}, null, 2));
