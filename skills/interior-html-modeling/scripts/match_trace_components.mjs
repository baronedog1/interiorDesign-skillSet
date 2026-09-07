#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  FIXED_PURPLE_COMPONENTS,
} from "../assets/component-library/fixed-purple/catalog.js";
import {
  MOVABLE_GREEN_COMPONENTS,
} from "../assets/component-library/movable-green/catalog.js";
import {
  RUNTIME_GEOMETRY_ADMISSION,
  RUNTIME_GEOMETRY_NON_DEFAULT_BY_ID,
  RUNTIME_GEOMETRY_REJECTED_ASSET_IDS,
} from "../assets/component-library/catalog/runtime-geometry-admission.v1.js";
import {
  inspectTraceShape,
} from "./trace_shape_contract.mjs";

const COMPONENT_LIBRARY_VERSION = "6.1.1";
const COMPONENT_LIBRARY_BY_SEMANTIC = {
  "movable-green": MOVABLE_GREEN_COMPONENTS,
  "fixed-purple": FIXED_PURPLE_COMPONENTS,
};
const ALL_COMPONENTS = [...new Map(
  Object.values(COMPONENT_LIBRARY_BY_SEMANTIC)
    .flat()
    .map((candidate) => [candidate.id, candidate]),
).values()];
const FUNCTIONAL_CLASS_CANONICAL = new Map([
  ["area-rug", "rug"],
  ["floor-rug", "rug"],
  ["carpet", "rug"],
]);

function canonicalFunctionalClass(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return FUNCTIONAL_CLASS_CANONICAL.get(normalized) || normalized;
}

function targetHeightForClass(functionalClass, fallback) {
  const value = canonicalFunctionalClass(functionalClass);
  const rules = [
    [/^rug$/, 0.03], [/table-light|desk-lamp/, 0.38], [/cooktop/, 0.12],
    [/refrigerator|fridge/, 1.85], [/wardrobe|closet/, 2.20], [/bookcase|shelving/, 2.10],
    [/washing-machine|washer|dryer/, 0.90], [/base-cabinet|sink-base-cabinet|bathroom-vanity|washbasin/, 0.86],
    [/toilet/, 0.72], [/double-bed|single-bed|queen-bed|king-bed/, 0.55], [/sofa-bed|sofa/, 0.78],
    [/dining-chair|office-chair|accent-chair|child-chair/, 0.88], [/dining-table|desk/, 0.75],
    [/coffee-table|side-table|nightstand/, 0.48], [/dresser/, 0.82], [/shoe-cabinet/, 1.05],
    [/tv-console|media-console/, 0.55],
  ];
  return rules.find(([pattern]) => pattern.test(value))?.[1] || Number(fallback || 0.9);
}

const scriptRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const tagDocument = JSON.parse(fs.readFileSync(
  path.join(scriptRoot, "assets/component-library/catalog/functional-class-tags.v1.json"),
  "utf8",
));
const tagPayload = { ...tagDocument, tagsDigestSha256: null };
const tagDigest = crypto.createHash("sha256").update(JSON.stringify(tagPayload)).digest("hex");
if (tagDocument.schema !== "interior.component-functional-class-tags.v1"
    || tagDigest !== tagDocument.tagsDigestSha256) {
  throw new Error("functional-class tag catalog is missing or has an invalid digest");
}
const FUNCTIONAL_CLASSES_BY_ASSET = new Map(tagDocument.assets.map((row) => [
  row.assetId,
  new Set(row.supportedFunctionalClasses),
]));

if (RUNTIME_GEOMETRY_ADMISSION.schema !== "interior.component-runtime-geometry-admission.v1") {
  throw new Error("runtime geometry admission is missing or invalid");
}

const axisDocument = JSON.parse(fs.readFileSync(
  path.join(scriptRoot, "assets/component-library/catalog/directional-axis-tags.v1.json"),
  "utf8",
));
if (axisDocument.schema !== "interior.component-directional-axis-tags.v1") {
  throw new Error("directional-axis tag catalog is missing or invalid");
}
const componentIds = new Set(Object.values(COMPONENT_LIBRARY_BY_SEMANTIC)
  .flat().map((candidate) => candidate.id));
const axisAssetIds = axisDocument.assets.map((row) => row.assetId);
if (new Set(axisAssetIds).size !== axisAssetIds.length) {
  throw new Error("directional-axis tag catalog contains duplicate assetId values");
}
for (const row of axisDocument.assets) {
  if (!componentIds.has(row.assetId)) {
    throw new Error(`directional-axis tag references unknown asset ${row.assetId}`);
  }
  const entries = Object.entries(row.axes || {});
  if (!entries.length || entries.some(([role, axis]) => (
    !["front", "back", "headboard"].includes(role)
    || !["+X", "-X", "+Z", "-Z"].includes(axis)
  ))) {
    throw new Error(`directional-axis tag is invalid for ${row.assetId}`);
  }
}
const AXES_BY_ASSET = new Map(axisDocument.assets.map((row) => [row.assetId, row]));

function supportsFunctionalClass(candidate, functionalClass) {
  const requested = canonicalFunctionalClass(functionalClass);
  return [...(FUNCTIONAL_CLASSES_BY_ASSET.get(candidate.id) || [])]
    .some((value) => canonicalFunctionalClass(value) === requested);
}

function validateAssemblies(trace) {
  const objects = new Map(trace.objects.map((object) => [object.traceId, object]));
  const assemblies = Array.isArray(trace.assemblies) ? trace.assemblies : [];
  const assemblyIds = new Set();
  const memberIds = new Set();
  for (const assembly of assemblies) {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(assembly.id || "") || assemblyIds.has(assembly.id)) {
      fail("assembly IDs must be unique kebab-case values");
    }
    assemblyIds.add(assembly.id);
    if (!/^[a-z0-9][a-z0-9-]*$/.test(assembly.functionalClass || "")) {
      fail(`${assembly.id}: assembly functionalClass is required`);
    }
    if (assembly.compositionPolicy !== "source-evidenced-atomic-members") {
      fail(`${assembly.id}: assembly compositionPolicy must preserve source-evidenced atomic members`);
    }
    if (!Array.isArray(assembly.childTraceIds) || assembly.childTraceIds.length < 2
        || new Set(assembly.childTraceIds).size !== assembly.childTraceIds.length) {
      fail(`${assembly.id}: assembly needs at least two unique childTraceIds`);
    }
    for (const traceId of assembly.childTraceIds) {
      const object = objects.get(traceId);
      if (!object) fail(`${assembly.id}: unknown child trace ${traceId}`);
      if (memberIds.has(traceId)) fail(`${traceId}: object belongs to more than one assembly`);
      memberIds.add(traceId);
      if (object.assemblyId !== assembly.id) fail(`${traceId}: assemblyId differs from ${assembly.id}`);
      if (!/^[a-z0-9][a-z0-9-]*$/.test(object.assemblyRole || "")) {
        fail(`${traceId}: assemblyRole is required`);
      }
      if (object.roomId !== assembly.roomId) fail(`${traceId}: assembly members must share roomId`);
    }
  }
  for (const object of trace.objects) {
    if (object.assemblyId && !memberIds.has(object.traceId)) {
      fail(`${object.traceId}: assemblyId is not declared by trace.assemblies`);
    }
  }
  return assemblies;
}

function getAnyComponentDefinition(componentId) {
  return ALL_COMPONENTS.find((item) => item.id === componentId) || null;
}

function option(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

const MAX_STANDALONE_ASSET_BYTES = 8 * 1024 * 1024;
const DEFAULT_PROJECT_RUNTIME_ASSET_BYTES = 14 * 1024 * 1024;
const projectRuntimeAssetBudget = Number(
  option("--max-project-runtime-bytes") || DEFAULT_PROJECT_RUNTIME_ASSET_BYTES,
);
if (!Number.isInteger(projectRuntimeAssetBudget)
    || projectRuntimeAssetBudget <= 0
    || projectRuntimeAssetBudget > DEFAULT_PROJECT_RUNTIME_ASSET_BYTES) {
  fail(`--max-project-runtime-bytes must be between 1 and ${DEFAULT_PROJECT_RUNTIME_ASSET_BYTES}`);
}
const assetStore = path.resolve(
  option("--asset-store")
    || process.env.INTERIOR_COMPONENT_ASSET_STORE
    || "/home/agentops/agent-runtime/shared-assets/interior-component-library-v6",
);
const inventoryPath = path.join(assetStore, "catalog/asset-store-inventory.json");
if (!fs.statSync(inventoryPath, { throwIfNoEntry: false })?.isFile()) {
  fail(`validated component asset store is unavailable: ${inventoryPath}`);
}
const assetInventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8"));
if (assetInventory.schema !== "interior.public-component-asset-store.v1") {
  fail("component asset store inventory schema is invalid");
}
const ASSET_RUNTIME_BY_ID = new Map(assetInventory.results.map((row) => [row.id, row]));

function webDeliveryEvidence(candidate) {
  const receipt = ASSET_RUNTIME_BY_ID.get(candidate.id);
  return {
    runtimeBytes: Number(receipt?.runtimeBytes || 0),
    webEmbeddable: Number(receipt?.runtimeBytes || 0) > 0
      && Number(receipt.runtimeBytes) <= MAX_STANDALONE_ASSET_BYTES,
  };
}

function fail(message) {
  throw new Error(message);
}

function discoverImportReceipt(root) {
  const pending = [root];
  const matches = [];
  while (pending.length) {
    const directory = pending.pop();
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const candidate = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "component-library" && entry.name !== "vendor") pending.push(candidate);
        continue;
      }
      if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
      try {
        const value = JSON.parse(fs.readFileSync(candidate, "utf8"));
        if (value.schema === "interior.floorplan-import-receipt.v1") matches.push({ candidate, value });
      } catch {
        // Non-JSON files with a .json suffix are ignored during semantic discovery.
      }
    }
  }
  const distinct = new Map(matches.map((match) => [JSON.stringify(match.value), match]));
  if (distinct.size !== 1) fail(`project requires one unambiguous floorplan import receipt; found ${distinct.size}`);
  return [...distinct.values()][0];
}

function assertTraceObject(object) {
  if (!object.traceId) fail("every trace object requires traceId");
  if (!object.sourceObjectCandidateId) fail(`${object.traceId}: sourceObjectCandidateId is required`);
  if (!["movable-green", "fixed-purple"].includes(object.semantic)) fail(`${object.traceId}: semantic must be movable-green or fixed-purple`);
  if (!object.shapeClass) fail(`${object.traceId}: shapeClass is required`);
  if (!/^[a-z0-9][a-z0-9-]*$/.test(object.functionalClass || "")) {
    fail(`${object.traceId}: one atomic functionalClass is required`);
  }
  if (object.atomicObject !== true) fail(`${object.traceId}: atomicObject must be true`);
  if (object.quantity !== 1) fail(`${object.traceId}: quantity must be exactly 1`);
  if (!(object.bbox?.width > 0 && object.bbox?.depth > 0)) fail(`${object.traceId}: bbox width/depth must be positive`);
  if (!(Array.isArray(object.center) && object.center.length === 2 && object.center.every(Number.isFinite))) fail(`${object.traceId}: center must be [x,z]`);
  if (!Number.isFinite(object.rotationY)) fail(`${object.traceId}: rotationY must be explicit and numeric`);
  if (!object.orientation || !["source-symbol", "source-outline-axis", "user-explicit-layout"].includes(object.orientation.evidence)) {
    fail(`${object.traceId}: source-bound orientation evidence is required`);
  }
  const sourceAxes = object.orientation.localAxes;
  if (!sourceAxes || !Object.keys(sourceAxes).length) fail(`${object.traceId}: orientation.localAxes must not be empty`);
  for (const [role, axis] of Object.entries(sourceAxes)) {
    if (!["front", "back", "headboard"].includes(role) || !["+X", "-X", "+Z", "-Z"].includes(axis)) {
      fail(`${object.traceId}: invalid source orientation ${role}=${axis}`);
    }
  }
  inspectTraceShape(object.shapeClass, object.shapeEvidence, object.traceId);
}

function textScore(object, candidate) {
  const text = [
    object.name,
    object.typeHint,
    object.categoryHint,
    ...(object.keywords || []),
  ].filter(Boolean).join(" ").toLowerCase();
  let score = 0;
  if (text.includes(candidate.name.toLowerCase())) score += 12;
  if (text.includes(candidate.categoryName.toLowerCase())) score += 2;
  if (text.includes(candidate.category.toLowerCase())) score += 1;
  candidate.tags.forEach((tag) => {
    if (text.includes(tag.toLowerCase())) score += 2;
  });
  if (supportsFunctionalClass(candidate, object.functionalClass)) score += 20;
  if (candidate.shapeClass === object.shapeClass) score += 4;
  if (object.styleIntent && candidate.styleCompatibility?.includes(object.styleIntent)) score += 4;
  if (object.styleIntent && candidate.styleNeutral) score += 1;
  return score;
}

function supportsIntent(object, candidate) {
  if (object.styleIntent && candidate.excludedStyleIntents?.includes(object.styleIntent)) return false;
  return supportsFunctionalClass(candidate, object.functionalClass);
}

function candidateDimensionFrame(object, candidate) {
  // Trace width/depth are object-local dimensions. calibratedAssetYaw() aligns
  // the asset's directional axis later, so swapping dimensions here applies
  // the same quarter turn twice and can inflate a cabinet or sofa around the
  // camera. Footprint fitting must always use the asset's native local frame.
  return {
    width: candidate.defaultDimensions.width,
    depth: candidate.defaultDimensions.depth,
    quarterTurn: false,
  };
}

function scaleFit(object, candidate) {
  const frame = candidateDimensionFrame(object, candidate);
  const scaleWidth = object.bbox.width / frame.width;
  const scaleDepth = object.bbox.depth / frame.depth;
  const spread = Math.abs(scaleWidth - scaleDepth) / Math.max(scaleWidth, scaleDepth);
  if (![scaleWidth, scaleDepth].every((value) => Number.isFinite(value) && value > 0)) return null;
  const canonicalClass = canonicalFunctionalClass(object.functionalClass);
  if (canonicalClass === "rug") {
    return {
      uniformScale: 1,
      rawUniformScale: 1,
      scaleWidth,
      scaleDepth,
      spread,
      axisScale: { width: scaleWidth, depth: scaleDepth, height: 1 },
      scaleMode: "planar-free",
      prototypeWidth: frame.width,
      prototypeDepth: frame.depth,
      dimensionFrame: frame.quarterTurn ? "quarter-turn" : "native",
      sizeScore: Math.max(0, 10 - Math.abs(1 - scaleWidth) - Math.abs(1 - scaleDepth)),
    };
  }
  if (candidate.editorCapabilities?.scaleMode === "axis-limited") {
    const widthRange = candidate.editorCapabilities.axisScaleRange.width;
    const depthRange = candidate.editorCapabilities.axisScaleRange.depth;
    const recommendedRangePenalty = Number(
      scaleWidth < widthRange[0] || scaleWidth > widthRange[1]
      || scaleDepth < depthRange[0] || scaleDepth > depthRange[1],
    );
    return {
      uniformScale: 1,
      rawUniformScale: 1,
      scaleWidth,
      scaleDepth,
      spread,
      axisScale: { width: scaleWidth, depth: scaleDepth, height: 1 },
      scaleMode: "axis-limited",
      prototypeWidth: frame.width,
      prototypeDepth: frame.depth,
      dimensionFrame: frame.quarterTurn ? "quarter-turn" : "native",
      sizeScore: Math.max(0, 8 - Math.abs(1 - scaleWidth) - Math.abs(1 - scaleDepth)
        - recommendedRangePenalty * 2),
    };
  }
  const rawUniformScale = (scaleWidth + scaleDepth) / 2;
  const rangePenalty = Number(
    rawUniformScale < candidate.uniformScaleRange.min
    || rawUniformScale > candidate.uniformScaleRange.max,
  );
  return {
    uniformScale: rawUniformScale,
    rawUniformScale,
    scaleWidth,
    scaleDepth,
    spread,
    axisScale: { width: 1, depth: 1, height: 1 },
    scaleMode: "uniform-only",
    prototypeWidth: frame.width,
    prototypeDepth: frame.depth,
    dimensionFrame: frame.quarterTurn ? "quarter-turn" : "native",
    sizeScore: Math.max(0, 8 - spread * 12 - Math.abs(1 - rawUniformScale) * 2
      - rangePenalty * 2),
  };
}

function rankCandidates(object) {
  const ranked = ALL_COMPONENTS
    .filter((candidate) => !RUNTIME_GEOMETRY_REJECTED_ASSET_IDS.has(candidate.id)
      && supportsIntent(object, candidate))
    .map((candidate) => {
      const fit = scaleFit(object, candidate);
      if (!fit) return null;
      const delivery = webDeliveryEvidence(candidate);
      return {
        candidate,
        ...delivery,
        uniformScale: fit.uniformScale,
        rawUniformScale: fit.rawUniformScale,
        scaleWidth: fit.scaleWidth,
        scaleDepth: fit.scaleDepth,
        spread: fit.spread,
        axisScale: fit.axisScale,
        scaleMode: fit.scaleMode,
        prototypeWidth: fit.prototypeWidth,
        prototypeDepth: fit.prototypeDepth,
        dimensionFrame: fit.dimensionFrame,
        score: textScore(object, candidate) + fit.sizeScore
          + (AXES_BY_ASSET.has(candidate.id) ? 6 : 0),
      };
    })
    .filter(Boolean)
    .sort((left, right) => Number(right.webEmbeddable) - Number(left.webEmbeddable)
      || right.score - left.score
      || left.runtimeBytes - right.runtimeBytes
      || left.candidate.id.localeCompare(right.candidate.id));
  return ranked.some((row) => row.webEmbeddable)
    ? ranked.filter((row) => row.webEmbeddable)
    : ranked;
}

function explicitWinner(object) {
  const candidate = getAnyComponentDefinition(object.componentHint);
  if (!candidate) {
    fail(`${object.traceId}: componentHint ${object.componentHint} is not in the managed component library`);
  }
  if (RUNTIME_GEOMETRY_REJECTED_ASSET_IDS.has(candidate.id)) {
    fail(`${object.traceId}: componentHint ${candidate.id} is excluded by runtime geometry audit`);
  }
  if (!supportsIntent(object, candidate)) {
    fail(`${object.traceId}: componentHint ${candidate.id} conflicts with functional/style intent`);
  }
  const fit = scaleFit(object, candidate);
  if (!fit) {
    fail(`${object.traceId}: componentHint ${candidate.id} is outside the trace reshape range`);
  }
  return {
    candidate,
    ...webDeliveryEvidence(candidate),
    uniformScale: fit.uniformScale,
    rawUniformScale: fit.rawUniformScale,
    scaleWidth: fit.scaleWidth,
    scaleDepth: fit.scaleDepth,
    spread: fit.spread,
    axisScale: fit.axisScale,
    scaleMode: fit.scaleMode,
    prototypeWidth: fit.prototypeWidth,
    prototypeDepth: fit.prototypeDepth,
    dimensionFrame: fit.dimensionFrame,
    score: textScore(object, candidate) + fit.sizeScore,
  };
}

function uniqueRuntimeBytes(winners) {
  const assets = new Map();
  for (const winner of winners) {
    if (winner?.candidate?.id) assets.set(winner.candidate.id, winner.runtimeBytes);
  }
  return [...assets.values()].reduce((total, bytes) => total + bytes, 0);
}

function qualityScore(winners) {
  return winners.reduce((total, winner) => total + Number(winner?.score || 0), 0);
}

function commonCandidateIds(indices, optionsByIndex) {
  const [first, ...rest] = indices;
  return optionsByIndex[first]
    .filter(Boolean)
    .map((winner) => winner.candidate.id)
    .filter((candidateId) => rest.every((index) => (
      optionsByIndex[index].some((winner) => winner.candidate.id === candidateId)
    )));
}

function selectProjectWinners(objects) {
  const optionsByIndex = objects.map((object) => {
    assertTraceObject(object);
    const options = object.componentHint ? [explicitWinner(object)] : rankCandidates(object);
    return options.filter((winner) => winner.webEmbeddable);
  });
  const gaps = objects
    .map((object, index) => ({ object, options: optionsByIndex[index] }))
    .filter((row) => row.options.length === 0)
    .map((row) => `${row.object.traceId}:${row.object.functionalClass}`);
  if (gaps.length) {
    fail(`ASSET_MATCH_GAP: no exact managed asset for ${gaps.join(", ")}`);
  }
  let winners = optionsByIndex.map((options) => options[0] || null);
  const initialRuntimeBytes = uniqueRuntimeBytes(winners);
  const optimizationSteps = [];

  while (uniqueRuntimeBytes(winners) > projectRuntimeAssetBudget) {
    const currentRuntimeBytes = uniqueRuntimeBytes(winners);
    const currentQuality = qualityScore(winners);
    const moves = [];
    const evaluate = (indices, candidateId, kind) => {
      const replacements = indices.map((index) => (
        optionsByIndex[index].find((winner) => winner.candidate.id === candidateId)
      ));
      if (replacements.some((winner) => !winner)) return;
      if (indices.every((index, offset) => winners[index].candidate.id === replacements[offset].candidate.id)) return;
      const next = [...winners];
      indices.forEach((index, offset) => { next[index] = replacements[offset]; });
      const nextRuntimeBytes = uniqueRuntimeBytes(next);
      const savedBytes = currentRuntimeBytes - nextRuntimeBytes;
      if (savedBytes <= 0) return;
      const qualityLoss = currentQuality - qualityScore(next);
      moves.push({
        indices,
        candidateId,
        kind,
        next,
        nextRuntimeBytes,
        savedBytes,
        qualityLoss,
        nonNegativeLossPerMiB: Math.max(0, qualityLoss) / (savedBytes / (1024 * 1024)),
      });
    };

    for (let index = 0; index < objects.length; index += 1) {
      if (objects[index].componentHint || !winners[index]) continue;
      for (const optionRow of optionsByIndex[index]) {
        evaluate([index], optionRow.candidate.id, "single-object-smaller-or-reused-asset");
      }
    }

    const groups = new Map();
    const addGroup = (key, index) => groups.set(key, [...(groups.get(key) || []), index]);
    objects.forEach((object, index) => {
      if (object.componentHint || !winners[index]) return;
      addGroup(`class:${object.semantic}:${object.functionalClass}`, index);
      addGroup(`asset:${winners[index].candidate.id}`, index);
    });
    for (const [key, indices] of groups) {
      if (indices.length < 2) continue;
      for (const candidateId of commonCandidateIds(indices, optionsByIndex)) {
        evaluate(indices, candidateId, key.startsWith("class:")
          ? "same-functional-class-project-reuse"
          : "replace-shared-project-asset");
      }
    }

    moves.sort((left, right) => (
      left.nonNegativeLossPerMiB - right.nonNegativeLossPerMiB
      || left.qualityLoss - right.qualityLoss
      || right.savedBytes - left.savedBytes
      || left.nextRuntimeBytes - right.nextRuntimeBytes
      || left.kind.localeCompare(right.kind)
      || left.candidateId.localeCompare(right.candidateId)
      || left.indices.join(",").localeCompare(right.indices.join(","))
    ));
    const selected = moves[0];
    if (!selected) {
      fail(`ASSET_PROJECT_BUDGET_GAP: exact functional-class assets require ${currentRuntimeBytes} bytes, above the ${projectRuntimeAssetBudget}-byte project budget`);
    }
    winners = selected.next;
    optimizationSteps.push({
      sequence: optimizationSteps.length + 1,
      kind: selected.kind,
      traceIds: selected.indices.map((index) => objects[index].traceId),
      componentId: selected.candidateId,
      savedBytes: selected.savedBytes,
      qualityLoss: Number(selected.qualityLoss.toFixed(4)),
      projectRuntimeBytesAfter: selected.nextRuntimeBytes,
    });
  }

  const finalRuntimeBytes = uniqueRuntimeBytes(winners);
  return {
    winners,
    evidence: {
      schema: "interior.project-runtime-asset-budget.v1",
      maxProjectRuntimeBytes: projectRuntimeAssetBudget,
      maxSingleAssetRuntimeBytes: MAX_STANDALONE_ASSET_BYTES,
      initialProjectRuntimeBytes: initialRuntimeBytes,
      finalProjectRuntimeBytes: finalRuntimeBytes,
      initialDistinctAssetCount: new Set(optionsByIndex.filter((options) => options[0]).map((options) => options[0].candidate.id)).size,
      finalDistinctAssetCount: new Set(winners.filter(Boolean).map((winner) => winner.candidate.id)).size,
      unmatchedCount: winners.filter((winner) => !winner).length,
      optimizationApplied: optimizationSteps.length > 0,
      optimizationSteps,
      accepted: finalRuntimeBytes <= projectRuntimeAssetBudget,
    },
  };
}

const PROJECT_WINNER_BY_TRACE = new Map();
let projectBudgetEvidence = null;

function matchOne(object) {
  assertTraceObject(object);
  const shape = inspectTraceShape(object.shapeClass, object.shapeEvidence, object.traceId);
  let winner;
  let matchMethod;
  const assetFunctionalClass = canonicalFunctionalClass(object.functionalClass);
  if (object.componentHint) {
    winner = explicitWinner(object);
    matchMethod = "explicit-proportional-source-route";
  } else {
    winner = PROJECT_WINNER_BY_TRACE.get(object.traceId);
    if (!winner) fail(`ASSET_MATCH_GAP ${object.traceId}: ${object.functionalClass}`);
    matchMethod = "same-functional-class-nearest-fit";
  }
  if (!winner.webEmbeddable) {
    fail(`ASSET_WEB_VARIANT_GAP ${object.traceId}: ${winner.candidate.id} has no reviewed runtime model within ${MAX_STANDALONE_ASSET_BYTES} bytes`);
  }
  return {
    sourceTraceId: object.traceId,
    sourceObjectCandidateId: object.sourceObjectCandidateId,
    sourceName: object.name,
    semantic: object.semantic,
    sourceShapeClass: object.shapeClass,
    assetShapeClass: winner.candidate.shapeClass,
    componentId: winner.candidate.id,
    componentName: winner.candidate.name,
    category: winner.candidate.category,
    functionalClass: object.functionalClass,
    assetFunctionalClass,
    ...(object.assemblyId ? { assemblyId: object.assemblyId, assemblyRole: object.assemblyRole } : {}),
    atomicObject: true,
    quantity: 1,
    libraryPartition: winner.candidate.libraryPartition,
    libraryDirectory: winner.candidate.libraryDirectory,
    matchMethod,
    score: Number(winner.score.toFixed(4)),
    uniformScale: Number(winner.uniformScale.toFixed(4)),
    axisScale: winner.axisScale,
    scaleMode: winner.scaleMode,
    evidence: {
      shapeClassExact: winner.candidate.shapeClass === object.shapeClass,
      shapeCompatibility: winner.candidate.shapeClass === object.shapeClass ? "exact" : "nearest-functional-class",
      semanticExact: winner.candidate.placementClass === object.semantic,
      sourceSemantic: object.semantic,
      assetPlacementClass: winner.candidate.placementClass,
      functionalClassExact: canonicalFunctionalClass(object.functionalClass) === assetFunctionalClass,
      functionalClassMatch: object.functionalClass === assetFunctionalClass ? "exact" : "canonical-equivalent",
      assetFunctionalClassTagDigestSha256: tagDocument.tagsDigestSha256,
      runtimeGeometryAdmissionDigestSha256: RUNTIME_GEOMETRY_ADMISSION.admissionDigestSha256,
      targetFootprintExact: true,
      authoredGeometryScalePolicy: winner.scaleMode,
      outlineBoundToCollisionFootprint: true,
      sourceOutlineHash: shape.outlineHash,
      sourceOutlinePointCount: shape.metrics.pointCount,
      sourceShapeMetrics: shape.metrics,
      outlineSource: shape.outlineSource,
      traceReshape: {
        mode: winner.scaleMode === "axis-limited"
          ? "axis-limited-authored-cabinet-with-trace-footprint"
          : "proportional-authored-model-with-trace-footprint",
        widthScaleFromPrototype: Number(winner.scaleWidth.toFixed(6)),
        depthScaleFromPrototype: Number(winner.scaleDepth.toFixed(6)),
        rawUniformScale: Number(winner.rawUniformScale.toFixed(6)),
        builderUniformScale: Number(winner.uniformScale.toFixed(6)),
        prototypeWidth: Number(winner.prototypeWidth.toFixed(6)),
        prototypeDepth: Number(winner.prototypeDepth.toFixed(6)),
        dimensionFrame: winner.dimensionFrame,
        axisScale: winner.axisScale,
      },
      proportionalScaleSpread: Number(winner.spread.toFixed(4)),
      targetWidth: object.bbox.width,
      targetDepth: object.bbox.depth,
      runtimeBytes: winner.runtimeBytes,
      webEmbeddable: winner.webEmbeddable,
      maxStandaloneAssetBytes: MAX_STANDALONE_ASSET_BYTES,
    },
  };
}

const tracePath = option("--trace");
const outputPath = option("--out");
if (!tracePath || !outputPath) {
  console.error("usage: match_trace_components.mjs --trace <trace-components.json> --out <component-layout.json> [--asset-store <store>] [--max-project-runtime-bytes <bytes>] [--commercial|--publish]");
  process.exit(2);
}
const resolvedOutputPath = path.resolve(outputPath);
const temporaryLayoutPath = `${resolvedOutputPath}.materializing`;
fs.rmSync(resolvedOutputPath, { force: true });
fs.rmSync(temporaryLayoutPath, { force: true });
const commercial = process.argv.includes("--commercial");
const publish = process.argv.includes("--publish");
if (commercial && publish) fail("choose only one policy gate: --commercial or --publish");
const materializationPolicy = publish ? "publish" : commercial ? "commercial" : "research";

const traceBytes = fs.readFileSync(tracePath);
const traceSha256 = crypto.createHash("sha256").update(traceBytes).digest("hex");
const importReceipt = discoverImportReceipt(path.dirname(resolvedOutputPath));
if (importReceipt.value.traceComponentsSha256 !== traceSha256) {
  fail("trace-components differs from the floorplan revision imported into this project");
}
const trace = JSON.parse(traceBytes);
if (trace.schema !== "interior.trace-components.v2") fail("trace schema must be interior.trace-components.v2");
if (!Array.isArray(trace.objects)) fail("trace objects must be an array");
const traceIds = trace.objects.map((object) => object.traceId);
if (new Set(traceIds).size !== traceIds.length) fail("traceId values must be unique");
const assemblies = validateAssemblies(trace);
const projectSelection = selectProjectWinners(trace.objects);
trace.objects.forEach((object, index) => {
  PROJECT_WINNER_BY_TRACE.set(object.traceId, projectSelection.winners[index]);
});
projectBudgetEvidence = projectSelection.evidence;
const matches = trace.objects.map((object) => matchOne(object));

function localAxisVector(axis) {
  return ({ "+X": [1, 0], "-X": [-1, 0], "+Z": [0, 1], "-Z": [0, -1] })[axis];
}

function rotatePlanVector(vector, yaw) {
  if (!vector) return null;
  const cos = Math.cos(yaw);
  const sin = Math.sin(yaw);
  return [
    Number((vector[0] * cos - vector[1] * sin).toFixed(6)),
    Number((vector[0] * sin + vector[1] * cos).toFixed(6)),
  ];
}

function normalizeYaw(value) {
  let result = value;
  while (result > Math.PI) result -= Math.PI * 2;
  while (result <= -Math.PI) result += Math.PI * 2;
  return Number(result.toFixed(6));
}

function calibratedAssetYaw(source, componentId) {
  const sourceAxes = source.orientation.localAxes;
  const assetAxes = AXES_BY_ASSET.get(componentId)?.axes || {};
  const role = ["headboard", "back", "front"].find((candidate) => sourceAxes[candidate] && assetAxes[candidate]);
  if (!role) return Number(source.rotationY);
  const desired = rotatePlanVector(localAxisVector(sourceAxes[role]), Number(source.rotationY));
  const geometryYaw = Number(
    RUNTIME_GEOMETRY_NON_DEFAULT_BY_ID.get(componentId)?.canonicalYawRadians || 0,
  );
  const asset = rotatePlanVector(localAxisVector(assetAxes[role]), geometryYaw);
  return normalizeYaw(Math.atan2(desired[1], desired[0]) - Math.atan2(asset[1], asset[0]));
}

function worldOrientation(componentId, rotationY) {
  const row = AXES_BY_ASSET.get(componentId);
  const geometryYaw = Number(
    RUNTIME_GEOMETRY_NON_DEFAULT_BY_ID.get(componentId)?.canonicalYawRadians || 0,
  );
  const vectors = {};
  for (const [role, axis] of Object.entries(row?.axes || {})) {
    vectors[role] = rotatePlanVector(localAxisVector(axis), rotationY + geometryYaw);
  }
  return {
    yawRadians: Number(rotationY.toFixed(6)),
    vectors,
    evidence: row ? axisDocument.evidencePolicy : "source-plan-yaw-only",
  };
}
const placements = matches.map((match) => {
  const source = trace.objects.find((object) => object.traceId === match.sourceTraceId);
  const shape = inspectTraceShape(source.shapeClass, source.shapeEvidence, source.traceId);
  const modelYaw = calibratedAssetYaw(source, match.componentId);
  const definition = getAnyComponentDefinition(match.componentId);
  if (!definition) fail(`${match.sourceTraceId}: selected asset definition is missing`);
  const assetHeight = targetHeightForClass(
    source.functionalClass,
    Number(definition.defaultDimensions.height || 0.1) * Number(match.uniformScale || 1),
  );
  return {
    id: `component-${source.traceId}`,
    name: source.name || match.componentName,
    componentId: match.componentId,
    assetStatus: "matched",
    sourceTraceId: source.traceId,
    sourceObjectCandidateId: source.sourceObjectCandidateId,
    semantic: source.semantic,
    category: match.category,
    functionalClass: match.functionalClass,
    assetFunctionalClass: match.assetFunctionalClass,
    ...(source.assemblyId ? { assemblyId: source.assemblyId, assemblyRole: source.assemblyRole } : {}),
    atomicObject: true,
    quantity: 1,
    libraryPartition: match.libraryPartition,
    libraryDirectory: match.libraryDirectory,
    roomId: source.roomId || null,
    position: [...source.center],
    rotationY: modelYaw,
    planFootprintRotationY: Number(source.rotationY),
    worldOrientation: {
      ...worldOrientation(match.componentId, modelYaw),
      sourceEvidence: source.orientation.evidence,
    },
    uniformScale: match.uniformScale,
    visualDimensions: {
      width: Number(source.bbox.width),
      depth: Number(source.bbox.depth),
      height: Number(assetHeight.toFixed(6)),
    },
    targetDimensions: {
      width: Number(source.bbox.width),
      depth: Number(source.bbox.depth),
      height: Number(assetHeight.toFixed(6)),
    },
    sourcePosition: [...source.center],
    sourceRotationY: Number(source.rotationY),
    sourceDimensions: {
      width: Number(source.bbox.width),
      depth: Number(source.bbox.depth),
    },
    sourceShapeEvidence: {
      coordinateSpace: "bbox-normalized",
      outlineSource: shape.outlineSource,
      outline: shape.outline,
      curveEdgeRatio: shape.metrics.curveEdgeRatio,
      handedness: shape.metrics.handedness,
      ...(shape.shapeAdjustments.arcRadians === undefined
        ? {}
        : { arcRadians: shape.shapeAdjustments.arcRadians }),
      ...(shape.shapeAdjustments.returnDepthRatio === undefined
        ? {}
        : { returnDepthRatio: shape.shapeAdjustments.returnDepthRatio }),
    },
    sourceShapeMetrics: shape.metrics,
    shapeAdjustments: shape.shapeAdjustments,
    traceReshape: { ...match.evidence.traceReshape },
    traceLock: {
      position: true,
      dimensions: true,
      rotation: true,
      outline: true,
      source: source.extractionEvidence?.source || "trace-components",
    },
    collisionTolerance: Number(source.collisionTolerance || 0.006),
    ...(source.joinGroup ? { joinGroup: source.joinGroup } : {}),
    ...(source.hostWallIds
      ? {
        attachmentMode: "flush-to-host-wall",
        hostWallIds: [...source.hostWallIds],
      }
      : {}),
  };
});
function nearestPlacement(source, candidates) {
  return candidates
    .map((target) => ({
      target,
      distance: Math.hypot(
        Number(target.position[0]) - Number(source.position[0]),
        Number(target.position[1]) - Number(source.position[1]),
      ),
    }))
    .sort((left, right) => left.distance - right.distance || left.target.id.localeCompare(right.target.id))[0]?.target;
}

const axes = [];
const axisKeys = new Set();
for (const placement of placements) {
  const row = AXES_BY_ASSET.get(placement.componentId);
  for (const [role, localAxis] of Object.entries(row?.axes || {})) {
    const key = `${placement.componentId}::${role}`;
    if (axisKeys.has(key)) continue;
    axisKeys.add(key);
    axes.push({
      assetId: placement.componentId,
      role,
      localAxis,
      evidence: axisDocument.evidencePolicy,
    });
  }
}

const facing = [];
const facingTargets = {
  "dining-chair": ["dining-table"],
  "bar-stool": ["bar-counter", "dining-table"],
  "office-chair": ["desk"],
  "child-chair": ["child-table", "desk"],
  sofa: ["tv-console", "media-console"],
  "sectional-sofa": ["tv-console", "media-console"],
  "sofa-bed": ["tv-console", "media-console"],
};
for (const source of placements) {
  if (!source.worldOrientation.vectors.front) continue;
  const targetClasses = facingTargets[source.functionalClass] || [];
  const target = nearestPlacement(source, placements.filter((candidate) => (
    candidate.roomId === source.roomId
    && candidate.id !== source.id
    && targetClasses.includes(candidate.functionalClass)
  )));
  if (target) facing.push({ sourceId: source.id, targetId: target.id, axisRole: "front" });
}

const wallAttachment = [];
for (const placement of placements) {
  const axisRole = placement.worldOrientation.vectors.headboard
    ? "headboard"
    : placement.worldOrientation.vectors.back ? "back" : null;
  if (!axisRole) continue;
  for (const wallId of placement.hostWallIds || []) {
    wallAttachment.push({ sourceId: placement.id, wallId, axisRole });
  }
}

const result = {
  schema: "interior.component-layout.v5",
  libraryVersion: COMPONENT_LIBRARY_VERSION,
  source: {
    traceSpec: path.basename(tracePath),
    traceComponentsSha256: traceSha256,
    sourceObjectCandidateIds: trace.objects.map(
      (object) => object.sourceObjectCandidateId,
    ),
    movableGreenCount: trace.objects.filter((object) => object.semantic === "movable-green").length,
    fixedPurpleCount: trace.objects.filter((object) => object.semantic === "fixed-purple").length,
    removedNoise: trace.removedNoise || [],
    libraryPartitions: {
      "movable-green": "component-library/movable-green",
      "fixed-purple": "component-library/fixed-purple",
    },
    matchPolicy: "canonical-functional-class-project-budget-v3",
    assetBudget: projectBudgetEvidence,
    workflowStage: "coauthoring-draft",
    assetNotices: [],
  },
  matches,
  placements,
  assemblies: assemblies.map((assembly) => ({
    id: assembly.id,
    functionalClass: assembly.functionalClass,
    roomId: assembly.roomId,
    compositionPolicy: assembly.compositionPolicy,
    childTraceIds: [...assembly.childTraceIds],
    childPlacementIds: assembly.childTraceIds.map((traceId) => `component-${traceId}`),
  })),
  relationHints: {
    schema: "interior.layout-relation-hints.v3",
    directionalAxes: axes,
    worldOrientations: placements.map((placement) => ({
      sourceId: placement.id,
      ...placement.worldOrientation,
    })),
    facing,
    wallAttachment,
    allowedContacts: [],
    spaceDividerMarkers: [],
  },
};

const projectRoot = path.dirname(resolvedOutputPath);
fs.mkdirSync(projectRoot, { recursive: true });
fs.writeFileSync(temporaryLayoutPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
const materializer = path.join(path.dirname(fileURLToPath(import.meta.url)), "materialize_component_assets.mjs");
const materialized = spawnSync(process.execPath, [
  materializer,
  "--project", projectRoot,
  "--layout", temporaryLayoutPath,
  "--store", assetStore,
  ...(publish ? ["--publish"] : commercial ? ["--commercial"] : []),
], { encoding: "utf8" });
if (materialized.status !== 0) {
  fs.rmSync(temporaryLayoutPath, { force: true });
  fail(`component assets could not be materialized: ${materialized.stderr || materialized.stdout}`);
}
const lockPath = path.join(projectRoot, "component-assets.lock.json");
if (!fs.statSync(lockPath, { throwIfNoEntry: false })?.isFile()) {
  fs.rmSync(temporaryLayoutPath, { force: true });
  fail("asset materializer did not produce component-assets.lock.json");
}
const lock = JSON.parse(fs.readFileSync(lockPath, "utf8"));
const expectedAssetIds = [...new Set(placements.map((placement) => placement.componentId).filter(Boolean))].sort();
const lockedAssetIds = (lock.assets || []).map((asset) => asset.id).sort();
if (lock.schema !== "interior.project-component-assets.v1"
    || lock.policy !== materializationPolicy
    || JSON.stringify(expectedAssetIds) !== JSON.stringify(lockedAssetIds)) {
  fs.rmSync(temporaryLayoutPath, { force: true });
  fail("asset lock does not exactly cover every selected placement asset");
}
for (const asset of lock.assets) {
  const target = path.join(projectRoot, asset.targetPath);
  if (!fs.statSync(target, { throwIfNoEntry: false })?.isFile()) {
    fs.rmSync(temporaryLayoutPath, { force: true });
    fail(`${asset.id}: materialized project asset is missing`);
  }
}
result.source.assetMaterialization = {
  status: "complete",
  policy: materializationPolicy,
  lockFile: path.basename(lockPath),
  lockSha256: crypto.createHash("sha256").update(fs.readFileSync(lockPath)).digest("hex"),
  distinctAssetCount: lock.assetCount,
  placementCount: placements.length,
  unmatchedCount: placements.filter((placement) => placement.assetStatus !== "matched").length,
};
fs.writeFileSync(temporaryLayoutPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
fs.renameSync(temporaryLayoutPath, resolvedOutputPath);
const coauthoringCompiler = path.join(path.dirname(fileURLToPath(import.meta.url)), "compile_coauthoring_model.mjs");
const structurePath = path.join(projectRoot, "structure-data.json");
const sceneRigPath = path.join(projectRoot, "scene-rig.json");
if (fs.statSync(structurePath, { throwIfNoEntry: false })?.isFile()
    && fs.statSync(sceneRigPath, { throwIfNoEntry: false })?.isFile()) {
  const compiled = spawnSync(process.execPath, [
    coauthoringCompiler,
    structurePath,
    resolvedOutputPath,
    sceneRigPath,
    path.join(projectRoot, "coauthoring-model.json"),
    path.join(projectRoot, "coauthoring-model.js"),
    path.join(projectRoot, "coauthoring-model-compilation.json"),
  ], { encoding: "utf8" });
  if (compiled.status !== 0) {
    fail(`coauthoring model compilation failed: ${compiled.stderr || compiled.stdout}`);
  }
}
console.log(JSON.stringify({
  ok: true,
  traceObjects: trace.objects.length,
  matches: matches.length,
  placements: placements.length,
  unmatched: placements.filter((placement) => placement.assetStatus !== "matched").length,
  assetMaterialization: "complete",
  projectRuntimeAssetBytes: projectBudgetEvidence.finalProjectRuntimeBytes,
  projectRuntimeAssetBudgetBytes: projectBudgetEvidence.maxProjectRuntimeBytes,
  budgetOptimizationSteps: projectBudgetEvidence.optimizationSteps.length,
  output: resolvedOutputPath,
  coauthoringModel: "coauthoring-model.json",
}, null, 2));
