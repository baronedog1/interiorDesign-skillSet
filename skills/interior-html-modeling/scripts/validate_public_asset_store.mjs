#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function option(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function digestFile(file) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let bytes;
    while ((bytes = fs.readSync(fd, buffer, 0, buffer.length, null)) > 0) hash.update(buffer.subarray(0, bytes));
  } finally {
    fs.closeSync(fd);
  }
  return hash.digest("hex");
}

function validateGlb(file) {
  const stat = fs.statSync(file, { throwIfNoEntry: false });
  if (!stat?.isFile() || stat.size < 20) return "missing or too small";
  const header = Buffer.alloc(12);
  const fd = fs.openSync(file, "r");
  try {
    fs.readSync(fd, header, 0, 12, 0);
  } finally {
    fs.closeSync(fd);
  }
  if (header.toString("ascii", 0, 4) !== "glTF") return "invalid GLB magic";
  if (header.readUInt32LE(4) !== 2) return "invalid GLB version";
  if (header.readUInt32LE(8) !== stat.size) return "declared GLB length differs from file size";
  return null;
}

const store = path.resolve(
  option("--store")
    || process.env.INTERIOR_COMPONENT_ASSET_STORE
    || "/home/agentops/agent-runtime/shared-assets/interior-component-library-v5",
);
const quick = process.argv.includes("--quick");
const catalogPath = path.join(store, "catalog/public-asset-catalog.json");
const inventoryPath = path.join(store, "catalog/asset-store-inventory.json");
const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8"));
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
const issues = [];
const pendingParts = [];
const stack = [store];
while (stack.length) {
  const directory = stack.pop();
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) stack.push(full);
    else if (/\.part(?:-\d+)?$/.test(entry.name)) pendingParts.push(path.relative(store, full));
  }
}
if (pendingParts.length) issues.push(`asset store contains ${pendingParts.length} unfinished part files`);
if (catalog.schema !== "interior.public-component-catalog.v5") issues.push("unsupported catalog schema");
if (inventory.schema !== "interior.public-component-asset-store.v1") issues.push("unsupported inventory schema");
if (catalog.catalogDigestSha256 !== inventory.catalogDigestSha256) issues.push("catalog/inventory digest mismatch");
if (inventory.counts.planned !== catalog.assets.length) issues.push("planned count differs from catalog");
if (inventory.counts.completed !== catalog.assets.length || inventory.counts.failed !== 0) {
  issues.push(`asset store incomplete: ${inventory.counts.completed}/${catalog.assets.length}, failed ${inventory.counts.failed}`);
}

const receipts = new Map(inventory.results.map((receipt) => [receipt.id, receipt]));
let verifiedBytes = 0;
let warningCount = 0;
for (const asset of catalog.assets) {
  const receipt = receipts.get(asset.id);
  if (!receipt) {
    issues.push(`${asset.id}: missing receipt`);
    continue;
  }
  const runtime = path.join(store, receipt.runtimePath);
  const source = path.join(store, receipt.sourcePath);
  const glbIssue = validateGlb(runtime);
  if (glbIssue) issues.push(`${asset.id}: ${glbIssue}`);
  if (!fs.statSync(source, { throwIfNoEntry: false })?.isFile()) issues.push(`${asset.id}: editable source entry is missing`);
  const sourceManifest = receipt.sourceManifest;
  if (!sourceManifest || !Array.isArray(sourceManifest.files) || !sourceManifest.files.length) {
    issues.push(`${asset.id}: editable source manifest is missing`);
  } else {
    const sourceFiles = [];
    for (const entry of sourceManifest.files) {
      const sourceFile = path.join(store, entry.path);
      const stat = fs.statSync(sourceFile, { throwIfNoEntry: false });
      if (!stat?.isFile() || stat.size !== entry.bytes) {
        issues.push(`${asset.id}: editable source dependency is missing or changed: ${entry.path}`);
        continue;
      }
      sourceFiles.push({ ...entry, sha256: quick ? entry.sha256 : digestFile(sourceFile) });
      if (!quick && sourceFiles.at(-1).sha256 !== entry.sha256) {
        issues.push(`${asset.id}: editable source dependency hash mismatch: ${entry.path}`);
      }
    }
    if (sourceFiles.length === sourceManifest.files.length) {
      const treeSha256 = crypto.createHash("sha256").update(JSON.stringify(sourceFiles)).digest("hex");
      if (!quick && treeSha256 !== sourceManifest.treeSha256) issues.push(`${asset.id}: editable source tree hash mismatch`);
    }
  }
  if (!quick && !glbIssue && digestFile(runtime) !== receipt.runtimeSha256) issues.push(`${asset.id}: runtime hash mismatch`);
  if (receipt.sourceSha256 !== receipt.sourceManifest?.treeSha256) issues.push(`${asset.id}: source hash differs from source tree hash`);
  if (receipt.license !== asset.sourceLicense
      || Boolean(receipt.researchOnly) !== Boolean(asset.researchOnly)
      || Boolean(receipt.commercialUseAllowed) !== Boolean(asset.commercialUseAllowed)
      || Boolean(receipt.commercialReviewRequired) !== Boolean(asset.commercialReviewRequired)) {
    issues.push(`${asset.id}: receipt license policy differs from catalog`);
  }
  verifiedBytes += Number(receipt.runtimeBytes || 0);
  warningCount += receipt.warnings?.length || 0;
}

const result = {
  ok: issues.length === 0,
  store,
  quick,
  catalogDigestSha256: catalog.catalogDigestSha256,
  planned: catalog.assets.length,
  validated: inventory.results.length,
  failed: inventory.failures.length,
  verifiedRuntimeBytes: verifiedBytes,
  optionalPreviewWarningCount: warningCount,
  unfinishedPartFileCount: pendingParts.length,
  issues,
};
console.log(JSON.stringify(result, null, 2));
if (!result.ok) process.exit(1);
