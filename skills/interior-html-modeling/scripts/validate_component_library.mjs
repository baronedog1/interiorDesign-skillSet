#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  FIXED_PURPLE_COMPONENTS,
} from "../assets/component-library/fixed-purple/catalog.js";
import {
  MOVABLE_GREEN_COMPONENTS,
} from "../assets/component-library/movable-green/catalog.js";

const COMPONENT_CATALOG = [...MOVABLE_GREEN_COMPONENTS, ...FIXED_PURPLE_COMPONENTS];

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const canonicalPath = path.join(root, "assets/component-library/catalog/public-assets.json");
const canonical = JSON.parse(fs.readFileSync(canonicalPath, "utf8"));
const issues = [];
if (canonical.schema !== "interior.public-component-catalog.v5") issues.push("unsupported canonical catalog schema");
const digestPayload = JSON.stringify({ ...canonical, catalogDigestSha256: null });
const digest = crypto.createHash("sha256").update(digestPayload).digest("hex");
if (digest !== canonical.catalogDigestSha256) issues.push("canonical catalog digest mismatch");

const selectionPath = path.join(root, canonical.sourceAssetSelection?.path || "");
if (!canonical.sourceAssetSelection || !fs.existsSync(selectionPath)) {
  issues.push("canonical source asset selection is missing");
} else {
  const selectionBytes = fs.readFileSync(selectionPath);
  const selection = JSON.parse(selectionBytes);
  const selectionDigest = crypto.createHash("sha256")
    .update(JSON.stringify({ ...selection, selectionDigestSha256: null }))
    .digest("hex");
  if (selection.schema !== "interior.public-component-selection.v2") issues.push("unsupported selection schema");
  if (selectionDigest !== selection.selectionDigestSha256
      || selection.selectionDigestSha256 !== canonical.sourceAssetSelection.selectionDigestSha256) {
    issues.push("selection digest mismatch");
  }
  if (crypto.createHash("sha256").update(selectionBytes).digest("hex") !== canonical.sourceAssetSelection.sha256) {
    issues.push("selection file hash mismatch");
  }
  const selectedIds = selection.assets.map((asset) => asset.id).sort();
  const catalogIds = canonical.assets.map((asset) => asset.id).sort();
  if (JSON.stringify(selectedIds) !== JSON.stringify(catalogIds)) issues.push("selection IDs differ from canonical catalog");
}

const exclusionsPath = path.join(root, canonical.sourceAssetExclusions?.path || "");
if (!canonical.sourceAssetExclusions || !fs.existsSync(exclusionsPath)) {
  issues.push("canonical source asset exclusions are missing");
} else {
  const exclusionBytes = fs.readFileSync(exclusionsPath);
  const exclusions = JSON.parse(exclusionBytes);
  if (exclusions.schema !== "interior.public-source-asset-exclusions.v1") issues.push("unsupported exclusions schema");
  if (exclusions.assets.length !== canonical.sourceAssetExclusions.count) issues.push("exclusion count mismatch");
  if (crypto.createHash("sha256").update(exclusionBytes).digest("hex") !== canonical.sourceAssetExclusions.sha256) {
    issues.push("exclusions file hash mismatch");
  }
}

const canonicalIds = canonical.assets.map((asset) => asset.id).sort();
const runtimeIds = COMPONENT_CATALOG.map((asset) => asset.id).sort();
if (JSON.stringify(canonicalIds) !== JSON.stringify(runtimeIds)) {
  issues.push("runtime catalogs do not exactly match canonical public-assets.json");
}
if (COMPONENT_CATALOG.length !== canonical.counts.total) {
  issues.push(`expected ${canonical.counts.total} components, got ${COMPONENT_CATALOG.length}`);
}
if (MOVABLE_GREEN_COMPONENTS.length !== canonical.counts.byPlacement["movable-green"]) {
  issues.push("movable-green count differs from canonical catalog");
}
if (FIXED_PURPLE_COMPONENTS.length !== canonical.counts.byPlacement["fixed-purple"]) {
  issues.push("fixed-purple count differs from canonical catalog");
}

const functionalTagPath = path.join(root, "assets/component-library/catalog/functional-class-tags.v1.json");
if (!fs.existsSync(functionalTagPath)) {
  issues.push("functional-class tag catalog is missing");
}
const functionalTags = fs.existsSync(functionalTagPath)
  ? JSON.parse(fs.readFileSync(functionalTagPath, "utf8"))
  : { assets: [] };
const functionalTagDigest = crypto.createHash("sha256")
  .update(JSON.stringify({ ...functionalTags, tagsDigestSha256: null }))
  .digest("hex");
if (functionalTags.schema !== "interior.component-functional-class-tags.v1"
    || functionalTagDigest !== functionalTags.tagsDigestSha256) {
  issues.push("functional-class tag catalog schema or digest is invalid");
}
const tagRows = new Map();
for (const row of functionalTags.assets || []) {
  if (tagRows.has(row.assetId)) issues.push(`${row.assetId}: duplicate functional-class tag row`);
  if (!Array.isArray(row.supportedFunctionalClasses) || !row.supportedFunctionalClasses.length
      || row.supportedFunctionalClasses.some((value) => !/^[a-z0-9][a-z0-9-]*$/.test(value))) {
    issues.push(`${row.assetId}: invalid supportedFunctionalClasses`);
  }
  tagRows.set(row.assetId, row);
}
if (JSON.stringify([...tagRows.keys()].sort()) !== JSON.stringify(canonicalIds)) {
  issues.push("functional-class tag IDs differ from the canonical asset catalog");
}

const allowedStyles = new Set(canonical.taxonomy.styles);
const forbiddenInteriorTerms = /\b(?:drill|gamepad|gaming console|street lamp|cash register|metal detector|circuit board|lubricant spray|bench vice)\b/i;
const ids = new Set();
const names = new Set();
for (const asset of COMPONENT_CATALOG) {
  if (ids.has(asset.id)) issues.push(`${asset.id}: duplicate ID`);
  ids.add(asset.id);
  if (names.has(asset.name)) issues.push(`${asset.id}: duplicate display name`);
  names.add(asset.name);
  if (asset.builder !== "external-gltf") issues.push(`${asset.id}: procedural builders are retired`);
  const classRow = tagRows.get(asset.id);
  if (!classRow || classRow.category !== asset.category) issues.push(`${asset.id}: functional-class category mismatch`);
  if (asset.functionalClass && !classRow?.supportedFunctionalClasses.includes(asset.functionalClass)) {
    issues.push(`${asset.id}: original functionalClass was not preserved in the tag catalog`);
  }
  if (asset.primitiveBoxOnly !== false) issues.push(`${asset.id}: primitive-only model is forbidden`);
  if (asset.geometryProfile !== "authored-gltf-pbr-v2") issues.push(`${asset.id}: invalid geometry profile`);
  if (asset.appearance !== "dual-white-source-color") issues.push(`${asset.id}: invalid appearance contract`);
  if (!asset.appearanceVariants?.includes("white-model") || !asset.appearanceVariants?.includes("source-color")) {
    issues.push(`${asset.id}: white-model/source-color are both required`);
  }
  const scaleMode = asset.editorCapabilities?.scaleMode || "uniform-only";
  if (!asset.lockAspectRatio && scaleMode !== "axis-limited") {
    issues.push(`${asset.id}: non-proportional scaling lacks an axis-limited contract`);
  }
  if (scaleMode === "axis-limited"
      && (asset.shapeClass !== "rectilinear" || !asset.editorCapabilities?.axisScaleRange)) {
    issues.push(`${asset.id}: axis-limited scaling is restricted to reviewed rectilinear components`);
  }
  if (!asset.assetPath?.startsWith("./models/")) issues.push(`${asset.id}: invalid runtime asset path`);
  if (!asset.sourceUrl || !asset.sourceApiUrl || !asset.sourceLicense || !asset.sourceProvenance || !asset.licenseEvidence) {
    issues.push(`${asset.id}: incomplete source provenance`);
  }
  if (!Array.isArray(asset.tags) || asset.tags.length < 2) issues.push(`${asset.id}: tags are incomplete`);
  if (!Array.isArray(asset.useCaseTags) || !asset.useCaseTags.length) issues.push(`${asset.id}: use-case tags are required`);
  if (!asset.mountType) issues.push(`${asset.id}: mountType is required`);
  if (asset.category === "sofa" && !Number.isInteger(asset.seatingCapacity)) {
    issues.push(`${asset.id}: sofa seatingCapacity is required`);
  }
  if (["sofa", "chair", "stool"].includes(asset.category)
      && Number.isInteger(asset.seatingCapacity)
      && !asset.useCaseTags.includes(`${asset.seatingCapacity}人位`)) {
    issues.push(`${asset.id}: seating capacity and use-case tags disagree`);
  }
  for (const style of asset.styleCompatibility || []) {
    if (!allowedStyles.has(style)) issues.push(`${asset.id}: unsupported platform style ${style}`);
  }
  if (asset.id !== "ph-plastic-monobloc-chair-01"
      && !asset.styleCompatibility?.length
      && asset.styleNeutral !== true) {
    issues.push(`${asset.id}: empty style compatibility requires styleNeutral=true`);
  }
  if (JSON.stringify(asset.styleCompatibility || []) !== JSON.stringify(asset.platform?.compatibility || [])) {
    issues.push(`${asset.id}: duplicate style fields disagree`);
  }
  if (!asset.name || !asset.shortName) issues.push(`${asset.id}: display names are incomplete`);
  if (forbiddenInteriorTerms.test(`${asset.sourceName} ${(asset.sourceTags || []).join(" ")}`)) {
    issues.push(`${asset.id}: non-interior asset entered the catalog`);
  }
  if (asset.researchOnly) issues.push(`${asset.id}: selected public assets must allow the requested research use`);
  if (!["CC0-1.0", "CC-BY-4.0"].includes(asset.sourceLicense)) {
    issues.push(`${asset.id}: unsupported source license ${asset.sourceLicense}`);
  }
  if (asset.sourceProvenance === "amazon-berkeley-objects" && asset.sourceLicense !== "CC-BY-4.0") {
    issues.push(`${asset.id}: ABO license must match the official CC BY 4.0 file`);
  }
  if (asset.sourceProvenance === "amazon-berkeley-objects"
      && asset.categoryEvidence !== "official-title-reconciled") {
    issues.push(`${asset.id}: ABO title and official product type were not reconciled`);
  }
  if (asset.sourceProvenance === "amazon-berkeley-objects"
      && (asset.commercialReviewRequired !== true || asset.commercialUseAllowed !== false
        || asset.licenseEvidence.status !== "provider-direct-confirmed-registry-conflict")) {
    issues.push(`${asset.id}: ABO registry conflict must remain visible and block automated commercial use`);
  }
  if (asset.sourceProvenance === "poly-haven"
      && (asset.commercialReviewRequired !== false || asset.commercialUseAllowed !== true
        || asset.licenseEvidence.status !== "provider-direct-confirmed")) {
    issues.push(`${asset.id}: Poly Haven CC0 commercial policy is inconsistent`);
  }
  if (asset.sourceProvenance === "poly-haven"
      && asset.categoryEvidence !== "curated-official-interior-asset") {
    issues.push(`${asset.id}: Poly Haven asset did not come from the reviewed interior allowlist`);
  }
  if (asset.sourceProvenance === "sweet-home-3d-blendswap-cc0"
      && (asset.sourceLicense !== "CC0-1.0"
        || asset.commercialUseAllowed !== true
        || asset.commercialReviewRequired !== false
        || asset.categoryEvidence !== "reviewed-official-library-record")) {
    issues.push(`${asset.id}: Sweet Home 3D CC0 source or policy is inconsistent`);
  }
  if (asset.styleNeutral && asset.styleCompatibility?.length) {
    issues.push(`${asset.id}: style-neutral component cannot also claim a style`);
  }
  if (asset.stylePolicy === "source-or-name-derived"
      && asset.styleCompatibility?.includes("新中式")
      && (asset.sourceTags || []).some((tag) => ["old", "vintage", "antique", "ornate", "traditional"].includes(tag))) {
    issues.push(`${asset.id}: antique source may not auto-match new Chinese intent`);
  }
}

for (const requiredClass of [
  "dining-chair", "dining-table", "toilet", "vanity", "washbasin", "cooktop", "tv-console",
]) {
  if (![...tagRows.values()].some((row) => row.supportedFunctionalClasses?.includes(requiredClass))) {
    issues.push(`component library has no tagged ${requiredClass} asset`);
  }
}

const monobloc = COMPONENT_CATALOG.find((asset) => asset.id === "ph-plastic-monobloc-chair-01");
if (!monobloc) {
  issues.push("practical monobloc chair fixture is missing");
} else {
  if (monobloc.styleCompatibility?.length) issues.push("monobloc chair must not receive a fake style tag");
  for (const required of ["简易", "大排档", "易清洁"]) {
    if (!monobloc.useCaseTags.includes(required)) issues.push(`monobloc chair missing use-case tag: ${required}`);
  }
}

const categoryCounts = Object.fromEntries(Object.keys(canonical.counts.byCategory).map((category) => [
  category,
  COMPONENT_CATALOG.filter((asset) => asset.category === category).length,
]));
for (const [category, count] of Object.entries(categoryCounts)) {
  if (count < 20) issues.push(`${category}: expected at least 20 curated models, got ${count}`);
}

const result = {
  ok: issues.length === 0,
  schema: canonical.schema,
  catalogDigestSha256: canonical.catalogDigestSha256,
  componentCount: COMPONENT_CATALOG.length,
  partitionCounts: {
    "movable-green": MOVABLE_GREEN_COMPONENTS.length,
    "fixed-purple": FIXED_PURPLE_COMPONENTS.length,
  },
  providerCounts: canonical.counts.byProvider,
  categoryCounts,
  researchOnlyCount: COMPONENT_CATALOG.filter((asset) => asset.researchOnly).length,
  researchApprovedCount: COMPONENT_CATALOG.filter((asset) => !asset.researchOnly).length,
  commercialSafeCount: COMPONENT_CATALOG.filter((asset) => asset.commercialUseAllowed).length,
  commercialReviewRequiredCount: COMPONENT_CATALOG.filter((asset) => asset.commercialReviewRequired).length,
  attributionRequiredCount: COMPONENT_CATALOG.filter((asset) => asset.sourceLicense === "CC-BY-4.0").length,
  dualAppearanceCount: COMPONENT_CATALOG.filter((asset) => asset.appearanceVariants?.length === 2).length,
  functionalClassTagDigestSha256: functionalTags.tagsDigestSha256,
  proceduralAssetCount: COMPONENT_CATALOG.filter((asset) => asset.builder !== "external-gltf").length,
  issues,
};
console.log(JSON.stringify(result, null, 2));
if (!result.ok) process.exit(1);
