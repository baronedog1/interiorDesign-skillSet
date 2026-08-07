import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function option(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

function digestFile(file) {
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let bytes;
    while ((bytes = fs.readSync(fd, buffer, 0, buffer.length, null)) > 0) {
      hash.update(buffer.subarray(0, bytes));
    }
  } finally {
    fs.closeSync(fd);
  }
  return hash.digest("hex");
}

const project = path.resolve(option("--project") || "");
if (!project || project === path.parse(project).root) {
  fail("usage: materialize_component_assets.mjs --project <html-project> [--layout <layout-in-project>] [--store <asset-store>] [--all] [--commercial|--publish]");
}
const store = path.resolve(
  option("--store")
    || process.env.INTERIOR_COMPONENT_ASSET_STORE
    || "/home/agentops/agent-runtime/shared-assets/interior-component-library-v5",
);
const commercial = process.argv.includes("--commercial");
const publish = process.argv.includes("--publish");
if (commercial && publish) fail("choose only one policy gate: --commercial or --publish");

const catalogPath = path.join(project, "component-library/catalog/public-assets.json");
const inventoryPath = path.join(store, "catalog/asset-store-inventory.json");
const layoutPath = path.resolve(option("--layout") || path.join(project, "component-layout.json"));
if (path.dirname(layoutPath) !== project) {
  fail("--layout must be a file in the declared project root");
}
for (const file of [catalogPath, inventoryPath]) {
  if (!fs.statSync(file, { throwIfNoEntry: false })?.isFile()) fail(`missing required file: ${file}`);
}

const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8"));
const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
if (catalog.schema !== "interior.public-component-catalog.v5") fail("unsupported component catalog");
if (inventory.schema !== "interior.public-component-asset-store.v1") fail("unsupported asset store inventory");
if (inventory.catalogDigestSha256 !== catalog.catalogDigestSha256) {
  fail("asset store inventory does not belong to the installed component catalog");
}

let requestedIds;
if (process.argv.includes("--all")) {
  requestedIds = catalog.assets.map((asset) => asset.id);
} else {
  if (!fs.statSync(layoutPath, { throwIfNoEntry: false })?.isFile()) fail(`missing component layout: ${layoutPath}`);
  const layout = JSON.parse(fs.readFileSync(layoutPath, "utf8"));
  requestedIds = [...new Set((layout.placements || []).map((placement) => placement.componentId))];
}

const assets = new Map(catalog.assets.map((asset) => [asset.id, asset]));
const receipts = new Map(inventory.results.map((receipt) => [receipt.id, receipt]));
const records = [];
for (const id of requestedIds.sort()) {
  const asset = assets.get(id);
  const receipt = receipts.get(id);
  if (!asset) fail(`${id}: not present in canonical public asset catalog`);
  if (!receipt) fail(`${id}: source/runtime model did not pass asset-store validation`);
  if ((commercial || publish) && asset.commercialUseAllowed !== true) {
    fail(`${id}: automated commercial/published use is blocked by ${asset.licenseEvidence?.status || asset.sourceLicense}`);
  }
  const source = path.join(store, receipt.runtimePath);
  if (!fs.statSync(source, { throwIfNoEntry: false })?.isFile()) fail(`${id}: validated runtime model is missing`);
  const sourceSha256 = digestFile(source);
  if (sourceSha256 !== receipt.runtimeSha256) fail(`${id}: runtime model hash changed after validation`);

  const relative = asset.assetPath.replace(/^\.\//, "");
  const target = path.join(project, "component-library", relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.rmSync(target, { force: true });
  let materialization = "hardlink";
  try {
    fs.linkSync(source, target);
  } catch {
    fs.copyFileSync(source, target);
    materialization = "copy";
  }
  records.push({
    id,
    provider: asset.sourceProvenance,
    sourceLicense: asset.sourceLicense,
    sourceUrl: asset.sourceUrl,
    sourceAuthors: asset.sourceAuthors,
    attributionRequired: asset.sourceLicense === "CC-BY-4.0",
    licenseEvidence: asset.licenseEvidence,
    commercialUseAllowed: asset.commercialUseAllowed,
    commercialReviewRequired: asset.commercialReviewRequired,
    modificationNotice: asset.editorCapabilities?.scaleMode === "axis-limited"
      ? "Converted to runtime GLB; reviewed rectilinear dimensions may be adjusted only within catalog axis ranges; white-model material is optional."
      : "Converted or copied to runtime GLB; displayed with uniform scaling and optional white-model material override.",
    researchOnly: asset.researchOnly,
    runtimeSha256: receipt.runtimeSha256,
    runtimeBytes: receipt.runtimeBytes,
    targetPath: path.relative(project, target),
    materialization,
  });
}

const lock = {
  schema: "interior.project-component-assets.v1",
  generatedAt: new Date().toISOString(),
  catalogDigestSha256: catalog.catalogDigestSha256,
  policy: publish ? "publish" : commercial ? "commercial" : "research",
  assetCount: records.length,
  assets: records,
};
const lockPath = path.join(project, "component-assets.lock.json");
fs.writeFileSync(lockPath, `${JSON.stringify(lock, null, 2)}\n`);
console.log(JSON.stringify({
  ok: true,
  project,
  assetStore: store,
  policy: lock.policy,
  assetCount: records.length,
  bytes: records.reduce((sum, record) => sum + record.runtimeBytes, 0),
  lockPath,
}, null, 2));
