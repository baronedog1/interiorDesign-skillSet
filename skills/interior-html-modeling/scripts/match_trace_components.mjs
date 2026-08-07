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
  inspectTraceShape,
} from "./trace_shape_contract.mjs";

const COMPONENT_LIBRARY_VERSION = "5.0.0";
const COMPONENT_LIBRARY_BY_SEMANTIC = {
  "movable-green": MOVABLE_GREEN_COMPONENTS,
  "fixed-purple": FIXED_PURPLE_COMPONENTS,
};

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

function supportsFunctionalClass(candidate, functionalClass) {
  return FUNCTIONAL_CLASSES_BY_ASSET.get(candidate.id)?.has(functionalClass) === true;
}

function getComponentDefinition(componentId, semantic) {
  return (COMPONENT_LIBRARY_BY_SEMANTIC[semantic] || [])
    .find((item) => item.id === componentId) || null;
}

function option(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

function fail(message) {
  throw new Error(message);
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
  if (!Number.isFinite(Number(object.rotationY ?? 0))) fail(`${object.traceId}: rotationY must be numeric`);
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
  if (object.styleIntent && candidate.styleCompatibility?.includes(object.styleIntent)) score += 4;
  if (object.styleIntent && candidate.styleNeutral) score += 1;
  return score;
}

function supportsIntent(object, candidate) {
  if (object.styleIntent && candidate.excludedStyleIntents?.includes(object.styleIntent)) return false;
  return supportsFunctionalClass(candidate, object.functionalClass);
}

function scaleFit(object, candidate) {
  const scaleWidth = object.bbox.width / candidate.defaultDimensions.width;
  const scaleDepth = object.bbox.depth / candidate.defaultDimensions.depth;
  const spread = Math.abs(scaleWidth - scaleDepth) / Math.max(scaleWidth, scaleDepth);
  if (candidate.editorCapabilities?.scaleMode === "axis-limited") {
    const widthRange = candidate.editorCapabilities.axisScaleRange.width;
    const depthRange = candidate.editorCapabilities.axisScaleRange.depth;
    if (scaleWidth < widthRange[0] || scaleWidth > widthRange[1]
        || scaleDepth < depthRange[0] || scaleDepth > depthRange[1]) return null;
    return {
      uniformScale: 1,
      rawUniformScale: 1,
      scaleWidth,
      scaleDepth,
      spread,
      axisScale: { width: scaleWidth, depth: scaleDepth, height: 1 },
      scaleMode: "axis-limited",
      sizeScore: Math.max(0, 8 - Math.abs(1 - scaleWidth) - Math.abs(1 - scaleDepth)),
    };
  }
  const rawUniformScale = (scaleWidth + scaleDepth) / 2;
  if (
    spread > 0.25
    ||
    rawUniformScale < candidate.uniformScaleRange.min
    || rawUniformScale > candidate.uniformScaleRange.max
  ) return null;
  return {
    uniformScale: rawUniformScale,
    rawUniformScale,
    scaleWidth,
    scaleDepth,
    spread,
    axisScale: { width: 1, depth: 1, height: 1 },
    scaleMode: "uniform-only",
    sizeScore: Math.max(0, 8 - spread * 12 - Math.abs(1 - rawUniformScale) * 2),
  };
}

function rankCandidates(object) {
  return (COMPONENT_LIBRARY_BY_SEMANTIC[object.semantic] || [])
    .filter((candidate) => candidate.shapeClass === object.shapeClass && supportsIntent(object, candidate))
    .map((candidate) => {
      const fit = scaleFit(object, candidate);
      if (!fit) return null;
      return {
        candidate,
        uniformScale: fit.uniformScale,
        rawUniformScale: fit.rawUniformScale,
        scaleWidth: fit.scaleWidth,
        scaleDepth: fit.scaleDepth,
        spread: fit.spread,
        axisScale: fit.axisScale,
        scaleMode: fit.scaleMode,
        score: textScore(object, candidate) + fit.sizeScore,
      };
    })
    .filter(Boolean)
    .sort((left, right) => right.score - left.score || left.candidate.id.localeCompare(right.candidate.id));
}

function matchOne(object) {
  assertTraceObject(object);
  const shape = inspectTraceShape(object.shapeClass, object.shapeEvidence, object.traceId);
  let winner;
  let matchMethod;
  if (object.componentHint) {
    const candidate = getComponentDefinition(object.componentHint, object.semantic);
    if (!candidate) {
      fail(`${object.traceId}: componentHint ${object.componentHint} is not in ${object.semantic}`);
    }
    if (candidate.shapeClass !== object.shapeClass) {
      fail(`${object.traceId}: componentHint shape ${candidate.shapeClass} does not match ${object.shapeClass}`);
    }
    if (!supportsIntent(object, candidate)) {
      fail(`${object.traceId}: componentHint ${candidate.id} conflicts with functional/style intent`);
    }
    const fit = scaleFit(object, candidate);
    if (!fit) {
      fail(`${object.traceId}: componentHint ${candidate.id} is outside the trace reshape range`);
    }
    winner = {
      candidate,
      uniformScale: fit.uniformScale,
      rawUniformScale: fit.rawUniformScale,
      scaleWidth: fit.scaleWidth,
      scaleDepth: fit.scaleDepth,
      spread: fit.spread,
      axisScale: fit.axisScale,
      scaleMode: fit.scaleMode,
      score: textScore(object, candidate) + fit.sizeScore,
    };
    matchMethod = "explicit-proportional-source-route";
  } else {
    const ranked = rankCandidates(object);
    if (!ranked.length) fail(`${object.traceId}: no exact semantic/shape candidate fits the proportional size range`);
    [winner] = ranked;
    matchMethod = "semantic-shape-proportional-source-score";
  }
  return {
    sourceTraceId: object.traceId,
    sourceObjectCandidateId: object.sourceObjectCandidateId,
    sourceName: object.name,
    semantic: object.semantic,
    sourceShapeClass: object.shapeClass,
    componentId: winner.candidate.id,
    componentName: winner.candidate.name,
    category: winner.candidate.category,
    functionalClass: object.functionalClass,
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
      shapeClassExact: true,
      semanticExact: true,
      functionalClassExact: true,
      assetFunctionalClassTagDigestSha256: tagDocument.tagsDigestSha256,
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
        axisScale: winner.axisScale,
      },
      proportionalScaleSpread: Number(winner.spread.toFixed(4)),
      targetWidth: object.bbox.width,
      targetDepth: object.bbox.depth,
    },
  };
}

const tracePath = option("--trace");
const outputPath = option("--out");
if (!tracePath || !outputPath) {
  console.error("usage: match_trace_components.mjs --trace <trace-components.json> --out <component-layout.json> [--asset-store <store>] [--commercial|--publish]");
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

const trace = JSON.parse(fs.readFileSync(tracePath, "utf8"));
if (trace.schema !== "interior.trace-components.v2") fail("trace schema must be interior.trace-components.v2");
if (!Array.isArray(trace.objects)) fail("trace objects must be an array");
const traceIds = trace.objects.map((object) => object.traceId);
if (new Set(traceIds).size !== traceIds.length) fail("traceId values must be unique");

const matches = trace.objects.map(matchOne);
const placements = matches.map((match) => {
  const source = trace.objects.find((object) => object.traceId === match.sourceTraceId);
  const shape = inspectTraceShape(source.shapeClass, source.shapeEvidence, source.traceId);
  return {
    id: `component-${source.traceId}`,
    name: source.name || match.componentName,
    componentId: match.componentId,
    sourceTraceId: source.traceId,
    sourceObjectCandidateId: source.sourceObjectCandidateId,
    semantic: source.semantic,
    category: match.category,
    functionalClass: match.functionalClass,
    atomicObject: true,
    quantity: 1,
    libraryPartition: match.libraryPartition,
    libraryDirectory: match.libraryDirectory,
    roomId: source.roomId || null,
    position: [...source.center],
    rotationY: Number(source.rotationY || 0),
    uniformScale: match.uniformScale,
    ...(match.scaleMode === "axis-limited"
      ? {
        visualDimensions: {
          width: Number(source.bbox.width),
          depth: Number(source.bbox.depth),
        },
      }
      : {}),
    targetDimensions: {
      width: Number(source.bbox.width),
      depth: Number(source.bbox.depth),
    },
    sourcePosition: [...source.center],
    sourceRotationY: Number(source.rotationY || 0),
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
const result = {
  schema: "interior.component-layout.v4",
  libraryVersion: COMPONENT_LIBRARY_VERSION,
  source: {
    traceSpec: path.basename(tracePath),
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
    matchPolicy: "exact-semantic-functional-class-shape-then-reviewed-resize-v1",
  },
  matches,
  placements,
  relationHints: {
    schema: "interior.layout-relation-hints.v2",
    directionalAxes: [],
    facing: [],
    wallAttachment: [],
    allowedContacts: [],
    spaceDividerMarkers: [],
  },
};

const projectRoot = path.dirname(resolvedOutputPath);
fs.mkdirSync(projectRoot, { recursive: true });
const assetStore = path.resolve(
  option("--asset-store")
    || process.env.INTERIOR_COMPONENT_ASSET_STORE
    || "/home/agentops/agent-runtime/shared-assets/interior-component-library-v5",
);
const inventoryPath = path.join(assetStore, "catalog/asset-store-inventory.json");
if (!fs.statSync(inventoryPath, { throwIfNoEntry: false })?.isFile()) {
  fail(`validated component asset store is unavailable: ${inventoryPath}`);
}
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
const expectedAssetIds = [...new Set(placements.map((placement) => placement.componentId))].sort();
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
};
fs.writeFileSync(temporaryLayoutPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
fs.renameSync(temporaryLayoutPath, resolvedOutputPath);
console.log(JSON.stringify({
  ok: true,
  traceObjects: trace.objects.length,
  matches: matches.length,
  placements: placements.length,
  assetMaterialization: "complete",
  output: resolvedOutputPath,
}, null, 2));
