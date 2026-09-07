#!/usr/bin/env node
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  FIXED_PURPLE_COMPONENTS,
} from "../assets/component-library/fixed-purple/catalog.js";
import {
  MOVABLE_GREEN_COMPONENTS,
} from "../assets/component-library/movable-green/catalog.js";
import {
  RUNTIME_GEOMETRY_ADMISSION,
  RUNTIME_GEOMETRY_REJECTED_ASSET_IDS,
} from "../assets/component-library/catalog/runtime-geometry-admission.v1.js";
import {
  componentCollisionPairs,
  componentFootprint,
  connectionOpeningPolygon,
  polygonContainedByBoundary,
  polygonsOverlap,
  rotatedRectangle,
} from "../assets/component-library/shared/placement-geometry.js";
import {
  inspectTraceShape,
  sameShapeAdjustments,
} from "./trace_shape_contract.mjs";
import { auditPlacementHeight } from "./placement_height_guard.mjs";

const COMPONENT_LIBRARY_VERSION = "6.1.1";
const MAX_PROJECT_RUNTIME_ASSET_BYTES = 14 * 1024 * 1024;
const COMPONENT_LIBRARY_BY_SEMANTIC = {
  "movable-green": MOVABLE_GREEN_COMPONENTS,
  "fixed-purple": FIXED_PURPLE_COMPONENTS,
};

const scriptRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const tagDocument = JSON.parse(fs.readFileSync(
  path.join(scriptRoot, "assets/component-library/catalog/functional-class-tags.v1.json"),
  "utf8",
));
const unsignedTagDocument = { ...tagDocument, tagsDigestSha256: null };
const tagDigest = crypto.createHash("sha256").update(JSON.stringify(unsignedTagDocument)).digest("hex");
if (tagDocument.schema !== "interior.component-functional-class-tags.v1"
    || tagDigest !== tagDocument.tagsDigestSha256) {
  throw new Error("functional-class tag catalog is missing or has an invalid digest");
}
const FUNCTIONAL_CLASSES_BY_ASSET = new Map(tagDocument.assets.map((row) => [
  row.assetId,
  new Set(row.supportedFunctionalClasses),
]));
const FUNCTIONAL_CLASS_CANONICAL = new Map([
  ["area-rug", "rug"], ["floor-rug", "rug"], ["carpet", "rug"],
]);
const canonicalFunctionalClass = (value) => {
  const normalized = String(value || "").trim().toLowerCase();
  return FUNCTIONAL_CLASS_CANONICAL.get(normalized) || normalized;
};
if (RUNTIME_GEOMETRY_ADMISSION.schema !== "interior.component-runtime-geometry-admission.v1") {
  throw new Error("runtime geometry admission is missing or invalid");
}

function exactFunctionalClassEvidence(row, definition) {
  return /^[a-z0-9][a-z0-9-]*$/.test(row?.functionalClass || "")
    && row?.atomicObject === true
    && row?.quantity === 1
    && Boolean(definition)
    && canonicalFunctionalClass(row.assetFunctionalClass) === canonicalFunctionalClass(row.functionalClass)
    && [...(FUNCTIONAL_CLASSES_BY_ASSET.get(definition.id) || [])]
      .some((value) => canonicalFunctionalClass(value) === canonicalFunctionalClass(row.functionalClass));
}

function getComponentDefinition(componentId, semantic) {
  return (COMPONENT_LIBRARY_BY_SEMANTIC[semantic] || [])
    .find((item) => item.id === componentId)
    || Object.values(COMPONENT_LIBRARY_BY_SEMANTIC).flat()
      .find((item) => item.id === componentId)
    || null;
}

const file = process.argv[2];
const structureFile = process.argv[3];
if (!file) {
  console.error("usage: validate_component_layout.mjs <component-layout.json> [structure-data.json]");
  process.exit(2);
}

const data = JSON.parse(fs.readFileSync(file, "utf8"));
const structure = structureFile ? JSON.parse(fs.readFileSync(structureFile, "utf8")) : null;
const issues = [];
const advisories = [];
const scaleAdvisories = [];
if (data.schema !== "interior.component-layout.v5") issues.push("invalid component layout schema");
if (data.libraryVersion !== COMPONENT_LIBRARY_VERSION) issues.push("invalid component library version");
const projectRoot = path.dirname(path.resolve(file));
const tracePath = path.resolve(projectRoot, data.source?.traceSpec || "trace-components.json");
const traceFile = fs.statSync(tracePath, { throwIfNoEntry: false })?.isFile()
  ? fs.readFileSync(tracePath)
  : null;
const trace = traceFile ? JSON.parse(traceFile) : null;
if (!traceFile || trace?.schema !== "interior.trace-components.v2") {
  issues.push("component layout source trace-components is missing or invalid");
} else if (crypto.createHash("sha256").update(traceFile).digest("hex") !== data.source?.traceComponentsSha256) {
  issues.push("component layout source trace-components digest differs from the current artifact");
}
const materialization = data.source?.assetMaterialization;
const lockPath = path.join(projectRoot, materialization?.lockFile || "");
let assetLock = null;
if (materialization?.status !== "complete"
    || !["research", "commercial", "publish"].includes(materialization?.policy)
    || materialization?.lockFile !== "component-assets.lock.json"
    || !/^[a-f0-9]{64}$/.test(materialization?.lockSha256 || "")
    || !fs.statSync(lockPath, { throwIfNoEntry: false })?.isFile()) {
  issues.push("component layout lacks a complete, hash-bound project asset lock");
} else {
  const lockBytes = fs.readFileSync(lockPath);
  if (crypto.createHash("sha256").update(lockBytes).digest("hex") !== materialization.lockSha256) {
    issues.push("component asset lock hash differs from component layout");
  } else {
    assetLock = JSON.parse(lockBytes);
    if (assetLock.schema !== "interior.project-component-assets.v1") {
      issues.push("invalid component asset lock schema");
    } else if (assetLock.policy !== materialization.policy) {
      issues.push("component asset lock policy differs from component layout");
    }
  }
}
const sourceTotal = Number(data.source?.movableGreenCount || 0) + Number(data.source?.fixedPurpleCount || 0);
const sourcePlacements = (data.placements || []).filter(
  (placement) => placement.placementOrigin !== "user-explicit-addition",
);
const additionPlacements = (data.placements || []).filter(
  (placement) => placement.placementOrigin === "user-explicit-addition",
);
const removedTraceIds = Array.isArray(data.source?.removedSourceTraceIds)
  ? data.source.removedSourceTraceIds
  : [];
if (data.matches?.length !== sourceTotal) issues.push("source count does not equal match count");
if (sourcePlacements.length + removedTraceIds.length !== sourceTotal) {
  issues.push("source count does not equal active placement plus removed trace count");
}
if (new Set(removedTraceIds).size !== removedTraceIds.length) issues.push("removedSourceTraceIds contains duplicates");

const traceIds = new Set();
const sourceObjectCandidateIds = new Set();
(data.matches || []).forEach((match) => {
  if (!match.sourceTraceId) issues.push("match missing sourceTraceId");
  if (RUNTIME_GEOMETRY_REJECTED_ASSET_IDS.has(match.componentId)) {
    issues.push(`${match.sourceTraceId}: component is excluded by runtime geometry audit`);
  }
  if (!match.sourceObjectCandidateId) {
    issues.push(`match missing sourceObjectCandidateId: ${match.sourceTraceId}`);
  }
  if (sourceObjectCandidateIds.has(match.sourceObjectCandidateId)) {
    issues.push(`duplicate sourceObjectCandidateId: ${match.sourceObjectCandidateId}`);
  }
  sourceObjectCandidateIds.add(match.sourceObjectCandidateId);
  if (traceIds.has(match.sourceTraceId)) issues.push(`duplicate sourceTraceId: ${match.sourceTraceId}`);
  traceIds.add(match.sourceTraceId);
  const definition = getComponentDefinition(match.componentId, match.libraryPartition || match.semantic);
  if (!definition) issues.push(`component is not in ${match.libraryPartition || match.semantic}: ${match.componentId}`);
  if (!exactFunctionalClassEvidence(match, definition)) {
    issues.push(`match lacks exact atomic functional-class evidence: ${match.sourceTraceId}`);
  }
  if (match.evidence?.functionalClassExact !== true
      || match.evidence?.assetFunctionalClassTagDigestSha256 !== tagDocument.tagsDigestSha256
      || match.evidence?.runtimeGeometryAdmissionDigestSha256
        !== RUNTIME_GEOMETRY_ADMISSION.admissionDigestSha256) {
    issues.push(`match functional-class tag evidence is stale: ${match.sourceTraceId}`);
  }
  if (definition && match.assetShapeClass !== definition.shapeClass) {
    issues.push(`asset shape evidence differs from catalog: ${match.sourceTraceId}`);
  }
  if (definition && match.libraryPartition !== definition.libraryPartition) issues.push(`libraryPartition mismatch: ${match.sourceTraceId}`);
  if (definition && match.libraryDirectory !== definition.libraryDirectory) issues.push(`libraryDirectory mismatch: ${match.sourceTraceId}`);
  if (Object.prototype.hasOwnProperty.call(match, "fallback")) issues.push(`fallback is prohibited: ${match.sourceTraceId}`);
  if (![
    "explicit-proportional-source-route",
    "same-functional-class-nearest-fit",
  ].includes(match.matchMethod)) {
    issues.push(`invalid match method: ${match.sourceTraceId}`);
  }
  if (
    match.evidence?.outlineBoundToCollisionFootprint !== true
    || !["uniform-only", "axis-limited", "planar-free"].includes(match.evidence?.authoredGeometryScalePolicy)
    || !/^[a-f0-9]{64}$/.test(match.evidence?.sourceOutlineHash || "")
    || !(Number(match.evidence?.sourceOutlinePointCount) >= 4)
  ) {
    issues.push(`match lacks outline evidence: ${match.sourceTraceId}`);
  }
  if (match.evidence?.webEmbeddable !== true
      || !(Number(match.evidence?.runtimeBytes) > 0)
      || Number(match.evidence.runtimeBytes) > Number(match.evidence?.maxStandaloneAssetBytes)) {
    issues.push(`match lacks a delivery-sized reviewed runtime asset: ${match.sourceTraceId}`);
  }
  if (
    ![
      "proportional-authored-model-with-trace-footprint",
      "axis-limited-authored-cabinet-with-trace-footprint",
    ].includes(match.evidence?.traceReshape?.mode)
    || ![
      match.evidence?.traceReshape?.widthScaleFromPrototype,
      match.evidence?.traceReshape?.depthScaleFromPrototype,
      match.evidence?.traceReshape?.rawUniformScale,
      match.evidence?.traceReshape?.builderUniformScale,
    ].every((value) => Number.isFinite(Number(value)) && Number(value) > 0)
  ) {
    issues.push(`match lacks proportional source-model evidence: ${match.sourceTraceId}`);
  }
});

const assetBudget = data.source?.assetBudget;
const runtimeBytesByAsset = new Map();
for (const match of data.matches || []) {
  const runtimeBytes = Number(match.evidence?.runtimeBytes || 0);
  const previous = runtimeBytesByAsset.get(match.componentId);
  if (previous !== undefined && previous !== runtimeBytes) {
    issues.push(`inconsistent runtime bytes for shared asset: ${match.componentId}`);
  }
  runtimeBytesByAsset.set(match.componentId, runtimeBytes);
}
const computedProjectRuntimeBytes = [...runtimeBytesByAsset.values()]
  .reduce((total, bytes) => total + bytes, 0);
if (data.source?.matchPolicy !== "canonical-functional-class-project-budget-v3") {
  issues.push("component layout does not use the project-budget matching policy");
}
if (assetBudget?.schema !== "interior.project-runtime-asset-budget.v1"
    || assetBudget.accepted !== true
    || !Number.isInteger(Number(assetBudget.maxProjectRuntimeBytes))
    || Number(assetBudget.maxProjectRuntimeBytes) <= 0
    || Number(assetBudget.maxProjectRuntimeBytes) > MAX_PROJECT_RUNTIME_ASSET_BYTES
    || Number(assetBudget.maxSingleAssetRuntimeBytes) !== 8 * 1024 * 1024
    || Number(assetBudget.finalProjectRuntimeBytes) !== computedProjectRuntimeBytes
    || Number(assetBudget.finalDistinctAssetCount) !== runtimeBytesByAsset.size
    || computedProjectRuntimeBytes > Number(assetBudget.maxProjectRuntimeBytes)
    || !Array.isArray(assetBudget.optimizationSteps)) {
  issues.push("project runtime asset budget evidence is missing, stale, or above the delivery-safe limit");
}
if (assetLock?.assets) {
  const lockedRuntimeBytes = new Map(assetLock.assets.map((asset) => [
    asset.id,
    Number(asset.runtimeBytes || asset.bytes || 0),
  ]));
  if (lockedRuntimeBytes.size !== runtimeBytesByAsset.size
      || [...runtimeBytesByAsset].some(([assetId, bytes]) => lockedRuntimeBytes.get(assetId) !== bytes)) {
    issues.push("project asset lock runtime bytes differ from budget evidence");
  }
}

const assemblyIds = new Set();
const assemblyMemberTraceIds = new Set();
for (const assembly of data.assemblies || []) {
  if (!/^[a-z0-9][a-z0-9-]*$/.test(assembly.id || "") || assemblyIds.has(assembly.id)) {
    issues.push("assembly IDs must be unique kebab-case values");
    continue;
  }
  assemblyIds.add(assembly.id);
  if (assembly.compositionPolicy !== "source-evidenced-atomic-members") {
    issues.push(`${assembly.id}: invalid assembly compositionPolicy`);
  }
  if (!Array.isArray(assembly.childTraceIds) || assembly.childTraceIds.length < 2
      || new Set(assembly.childTraceIds).size !== assembly.childTraceIds.length) {
    issues.push(`${assembly.id}: invalid childTraceIds`);
    continue;
  }
  const expectedPlacementIds = assembly.childTraceIds.map((traceId) => `component-${traceId}`);
  if (JSON.stringify(assembly.childPlacementIds) !== JSON.stringify(expectedPlacementIds)) {
    issues.push(`${assembly.id}: childPlacementIds differ from childTraceIds`);
  }
  for (const traceId of assembly.childTraceIds) {
    if (assemblyMemberTraceIds.has(traceId)) issues.push(`${traceId}: belongs to multiple assemblies`);
    assemblyMemberTraceIds.add(traceId);
    const match = (data.matches || []).find((row) => row.sourceTraceId === traceId);
    const placement = (data.placements || []).find((row) => row.sourceTraceId === traceId);
    if (!match || !placement) issues.push(`${assembly.id}: missing member ${traceId}`);
    if (match?.assemblyId !== assembly.id || placement?.assemblyId !== assembly.id) {
      issues.push(`${traceId}: assembly membership differs from ${assembly.id}`);
    }
    if (!match?.assemblyRole || match.assemblyRole !== placement?.assemblyRole) {
      issues.push(`${traceId}: assemblyRole is missing or inconsistent`);
    }
    if (placement?.roomId !== assembly.roomId) issues.push(`${traceId}: assembly roomId mismatch`);
  }
}
for (const placement of data.placements || []) {
  if (placement.assemblyId && !assemblyMemberTraceIds.has(placement.sourceTraceId)) {
    issues.push(`${placement.sourceTraceId}: undeclared assembly membership`);
  }
}

const placementIds = new Set();
const designAdditionIds = new Set();
let traceExactPlacementCount = 0;
let outlineExactPlacementCount = 0;
let reviewedAdjustmentCount = 0;
const nearlyEqual = (left, right, tolerance = 0.0001) => (
  Number.isFinite(Number(left))
  && Number.isFinite(Number(right))
  && Math.abs(Number(left) - Number(right)) <= tolerance
);
const samePosition = (left, right, tolerance = 0.0001) => (
  Array.isArray(left)
  && Array.isArray(right)
  && left.length === 2
  && right.length === 2
  && left.every((value, index) => nearlyEqual(value, right[index], tolerance))
);
function inspectReviewedAdjustment(placement) {
  const adjustment = placement.reviewedAdjustment;
  if (!adjustment) return { valid: false, fields: new Set(), absent: true };
  const fields = new Set(adjustment.changedFields || []);
  const allowedFields = new Set(["position", "rotationY"]);
  const validUserAuthority = adjustment.authority === "user-explicit-layout-correction"
    && typeof adjustment.userInstructionRef === "string"
    && adjustment.userInstructionRef.trim().length >= 8
    && typeof adjustment.reviewedAt === "string"
    && adjustment.reviewedAt.includes("T");
  const valid = adjustment.schema === "interior.reviewed-layout-adjustment.v1"
    && validUserAuthority
    && typeof adjustment.reasonCode === "string"
    && adjustment.reasonCode.trim().length >= 8
    && typeof adjustment.reason === "string"
    && adjustment.reason.trim().length >= 12
    && fields.size === adjustment.changedFields?.length
    && fields.size > 0
    && [...fields].every((field) => allowedFields.has(field))
    && samePosition(adjustment.previous?.position, placement.sourcePosition)
    && nearlyEqual(adjustment.previous?.rotationY, placement.sourceRotationY || 0)
    && samePosition(adjustment.active?.position, placement.position)
    && nearlyEqual(adjustment.active?.rotationY, placement.planFootprintRotationY)
    && (fields.has("position") ? placement.traceLock?.position === false : placement.traceLock?.position === true)
    && (fields.has("rotationY") ? placement.traceLock?.rotation === false : placement.traceLock?.rotation === true);
  return { valid, fields, absent: false };
}
(data.placements || []).forEach((placement) => {
  if (placementIds.has(placement.id)) issues.push(`duplicate placement id: ${placement.id}`);
  placementIds.add(placement.id);
  const definition = getComponentDefinition(placement.componentId, placement.libraryPartition || placement.semantic);
  if (placement.finishPreset !== undefined
      && !["source-authored", "modern-light-wood"].includes(placement.finishPreset)) {
    issues.push(`unsupported finishPreset: ${placement.id}`);
  }
  if (placement.finishPreset === "modern-light-wood"
      && (definition?.shapeClass !== "rectilinear"
        || definition?.editorCapabilities?.scaleMode !== "axis-limited")) {
    issues.push(`modern-light-wood is restricted to reviewed rectilinear cabinetry: ${placement.id}`);
  }
  const isAddition = placement.placementOrigin === "user-explicit-addition";
  if (isAddition) {
    if (!placement.designAdditionId || designAdditionIds.has(placement.designAdditionId)) {
      issues.push(`invalid or duplicate designAdditionId: ${placement.id}`);
    }
    designAdditionIds.add(placement.designAdditionId);
    if (!placement.userInstructionRef || !placement.roomId) {
      issues.push(`user-added component lacks instruction or room evidence: ${placement.id}`);
    }
    if (placement.sourceTraceId || placement.sourceObjectCandidateId) {
      issues.push(`user-added component may not impersonate source trace evidence: ${placement.id}`);
    }
    if (!definition || definition.placementClass !== (placement.libraryPartition || placement.semantic)) {
      issues.push(`user-added component is not in ${placement.libraryPartition || placement.semantic}: ${placement.id}`);
      return;
    }
    const scale = Number(placement.uniformScale ?? 1);
    if (!(scale >= definition.uniformScaleRange.min && scale <= definition.uniformScaleRange.max)) {
      scaleAdvisories.push(`scale outside catalog recommendation: ${placement.id}`);
    }
    if (!(Array.isArray(placement.position)
      && placement.position.length === 2
      && placement.position.every(Number.isFinite))) {
      issues.push(`invalid position: ${placement.id}`);
    }
    if (!(Number(placement.targetDimensions?.width) > 0
      && Number(placement.targetDimensions?.depth) > 0)) {
      issues.push(`missing positive targetDimensions: ${placement.id}`);
    }
    if (definition.editorCapabilities?.scaleMode === "axis-limited") {
      const base = {
        width: definition.defaultDimensions.width * scale,
        depth: definition.defaultDimensions.depth * scale,
        height: definition.defaultDimensions.height * scale,
      };
      for (const axis of ["width", "depth", "height"]) {
        const value = Number(placement.visualDimensions?.[axis] ?? base[axis]);
        const range = definition.editorCapabilities.axisScaleRange?.[axis];
        const ratio = value / base[axis];
        if (!Array.isArray(range) || !Number.isFinite(value) || value <= 0
            || ratio < range[0] - 1e-6 || ratio > range[1] + 1e-6) {
          if (!Number.isFinite(value) || value <= 0 || !Array.isArray(range)) {
            issues.push(`invalid axis-limited ${axis}: ${placement.id}`);
          } else {
            scaleAdvisories.push(`axis-limited ${axis} outside catalog recommendation: ${placement.id}`);
          }
        }
      }
    } else if (placement.visualDimensions && !["width", "depth", "height"].every(
      (axis) => Number(placement.visualDimensions?.[axis]) > 0
    )) {
      issues.push(`visualDimensions must be positive: ${placement.id}`);
    }
    return;
  }
  const match = (data.matches || []).find((item) => item.sourceTraceId === placement.sourceTraceId);
  if (!exactFunctionalClassEvidence(placement, definition)
      && !exactFunctionalClassEvidence(match, definition)) {
    issues.push(`placement lacks exact atomic functional-class evidence: ${placement.id}`);
  }
  if (!match || match.componentId !== placement.componentId) issues.push(`placement has no exact match: ${placement.id}`);
  if (
    !placement.sourceObjectCandidateId
    || placement.sourceObjectCandidateId !== match?.sourceObjectCandidateId
  ) {
    issues.push(`placement source object evidence differs from match: ${placement.id}`);
  }
  if (!definition) issues.push(`placement component is not in ${placement.libraryPartition || placement.semantic}: ${placement.id}`);
  if (definition && placement.libraryPartition !== definition.libraryPartition) issues.push(`placement libraryPartition mismatch: ${placement.id}`);
  if (definition && placement.libraryDirectory !== definition.libraryDirectory) issues.push(`placement libraryDirectory mismatch: ${placement.id}`);
  if (definition) {
    const scale = Number(placement.uniformScale);
    if (!(scale >= definition.uniformScaleRange.min && scale <= definition.uniformScaleRange.max)) {
      scaleAdvisories.push(`scale outside catalog recommendation: ${placement.id}`);
    }
    const scaleMode = definition.editorCapabilities?.scaleMode || "uniform-only";
    const visual = placement.visualDimensions;
    if (visual && !["width", "depth", "height"].every((axis) => Number(visual?.[axis]) > 0)) {
      issues.push(`visualDimensions must be positive: ${placement.id}`);
    }
    if (scaleMode === "axis-limited") {
      const base = {
        width: definition.defaultDimensions.width * scale,
        depth: definition.defaultDimensions.depth * scale,
        height: definition.defaultDimensions.height * scale,
      };
      for (const axis of ["width", "depth", "height"]) {
        const value = Number(visual?.[axis] ?? base[axis]);
        const range = definition.editorCapabilities.axisScaleRange?.[axis];
        const ratio = value / base[axis];
        if (!Number.isFinite(value) || value <= 0 || !Array.isArray(range)
            || ratio < range[0] - 1e-6 || ratio > range[1] + 1e-6) {
          if (!Number.isFinite(value) || value <= 0 || !Array.isArray(range)) {
            issues.push(`invalid axis-limited ${axis}: ${placement.id}`);
          } else {
            scaleAdvisories.push(`axis-limited ${axis} outside catalog recommendation: ${placement.id}`);
          }
        }
      }
    }
  }
  if (!(Array.isArray(placement.position) && placement.position.length === 2 && placement.position.every(Number.isFinite))) {
    issues.push(`invalid position: ${placement.id}`);
  }
  const targetDimensions = placement.targetDimensions;
  const sourceDimensions = placement.sourceDimensions;
  const sourcePosition = placement.sourcePosition;
  const sourceRotationY = placement.sourceRotationY;
  const traceLock = placement.traceLock;
  if (!(targetDimensions
    && Number(targetDimensions.width) > 0
    && Number(targetDimensions.depth) > 0)) {
    issues.push(`missing positive targetDimensions: ${placement.id}`);
  }
  if (!(sourceDimensions
    && Number(sourceDimensions.width) > 0
    && Number(sourceDimensions.depth) > 0)) {
    issues.push(`missing positive sourceDimensions: ${placement.id}`);
  }
  if (!(Array.isArray(sourcePosition)
    && sourcePosition.length === 2
    && sourcePosition.every(Number.isFinite))) {
    issues.push(`invalid sourcePosition: ${placement.id}`);
  }
  if (!Number.isFinite(Number(sourceRotationY))) {
    issues.push(`invalid sourceRotationY: ${placement.id}`);
  }
  const adjustmentAudit = inspectReviewedAdjustment(placement);
  if (!adjustmentAudit.absent && !adjustmentAudit.valid) {
    issues.push(`invalid reviewed layout adjustment: ${placement.id}`);
  }
  if (adjustmentAudit.valid) reviewedAdjustmentCount += 1;
  const positionLockValid = traceLock?.position === true
    || (adjustmentAudit.valid && adjustmentAudit.fields.has("position"));
  const rotationLockValid = traceLock?.rotation === true
    || (adjustmentAudit.valid && adjustmentAudit.fields.has("rotationY"));
  if (!(positionLockValid
    && traceLock?.dimensions === true
    && rotationLockValid
    && traceLock?.outline === true
    && typeof traceLock?.source === "string"
    && traceLock.source)) {
    issues.push(`traceLock or reviewed adjustment is incomplete: ${placement.id}`);
  }
  const exactPosition = Array.isArray(sourcePosition)
    && sourcePosition.length === 2
    && sourcePosition.every((value, index) => nearlyEqual(value, placement.position?.[index]));
  const exactDimensions = targetDimensions
    && sourceDimensions
    && nearlyEqual(targetDimensions.width, sourceDimensions.width)
    && nearlyEqual(targetDimensions.depth, sourceDimensions.depth);
  const exactRotation = nearlyEqual(sourceRotationY, placement.planFootprintRotationY);
  if (!exactPosition && !(adjustmentAudit.valid && adjustmentAudit.fields.has("position"))) {
    issues.push(`placement shifted away from source trace without review: ${placement.id}`);
  }
  if (!exactDimensions) issues.push(`placement dimensions differ from source trace: ${placement.id}`);
  if (!exactRotation && !(adjustmentAudit.valid && adjustmentAudit.fields.has("rotationY"))) {
    issues.push(`placement plan footprint rotation differs from source trace without review: ${placement.id}`);
  }
  if (exactPosition && exactDimensions && exactRotation) traceExactPlacementCount += 1;
  try {
    const inspectedShape = inspectTraceShape(
      match?.sourceShapeClass,
      placement.sourceShapeEvidence,
      placement.sourceTraceId,
    );
    const metricsMatch = JSON.stringify(inspectedShape.metrics)
      === JSON.stringify(placement.sourceShapeMetrics);
    const hashMatch = inspectedShape.outlineHash === match?.evidence?.sourceOutlineHash;
    const adjustmentsMatch = sameShapeAdjustments(
      inspectedShape.shapeAdjustments,
      placement.shapeAdjustments,
    );
    if (!metricsMatch) issues.push(`shape metrics differ from source outline: ${placement.id}`);
    if (!hashMatch) issues.push(`source outline hash mismatch: ${placement.id}`);
    if (!adjustmentsMatch) issues.push(`shape parameters are not bound to source outline: ${placement.id}`);
    if (metricsMatch && hashMatch && adjustmentsMatch) outlineExactPlacementCount += 1;
  } catch (error) {
    issues.push(`${placement.id}: ${error.message}`);
  }
  if (match?.evidence) {
    if (!match.evidence.targetFootprintExact) issues.push(`match lacks exact source-footprint evidence: ${placement.id}`);
    if (!["uniform-only", "axis-limited", "planar-free"].includes(match.evidence.authoredGeometryScalePolicy)) {
      issues.push(`match lacks authored-geometry scale policy: ${placement.id}`);
    }
    if (!nearlyEqual(match.evidence.targetWidth, sourceDimensions?.width)
      || !nearlyEqual(match.evidence.targetDepth, sourceDimensions?.depth)) {
      issues.push(`match target dimensions differ from source trace: ${placement.id}`);
    }
    const prototypeWidth = Number(match.evidence?.traceReshape?.prototypeWidth);
    const prototypeDepth = Number(match.evidence?.traceReshape?.prototypeDepth);
    const expectedWidthScale = Number(sourceDimensions?.width) / prototypeWidth;
    const expectedDepthScale = Number(sourceDimensions?.depth) / prototypeDepth;
    const expectedSpread = Math.abs(expectedWidthScale - expectedDepthScale)
      / Math.max(expectedWidthScale, expectedDepthScale);
    if (
      ![
        "proportional-authored-model-with-trace-footprint",
        "axis-limited-authored-cabinet-with-trace-footprint",
      ].includes(placement.traceReshape?.mode)
      || !nearlyEqual(placement.traceReshape?.widthScaleFromPrototype, expectedWidthScale)
      || !nearlyEqual(placement.traceReshape?.depthScaleFromPrototype, expectedDepthScale)
      || JSON.stringify(placement.traceReshape) !== JSON.stringify(match.evidence.traceReshape)
    ) {
      issues.push(`source footprint or proportional authored scale differs from match: ${placement.id}`);
    }
    if (!nearlyEqual(match.evidence?.proportionalScaleSpread, expectedSpread)) {
      issues.push(`proportional scale spread differs from source and authored model: ${placement.id}`);
    }
  }
});
const declaredObjectIds = data.source?.sourceObjectCandidateIds || [];
if (
  new Set(declaredObjectIds).size !== declaredObjectIds.length
  || declaredObjectIds.length !== sourceTotal
  || declaredObjectIds.some((candidateId) => !sourceObjectCandidateIds.has(candidateId))
) {
  issues.push("source object candidate registry differs from matches");
}
if (trace) {
  const canonicalTraceRows = (trace.objects || []).map((row) => ({
    traceId: row.traceId,
    sourceObjectCandidateId: row.sourceObjectCandidateId,
    semantic: row.semantic,
    functionalClass: row.functionalClass,
  })).sort((left, right) => left.traceId.localeCompare(right.traceId));
  const canonicalMatchRows = (data.matches || []).map((row) => ({
    traceId: row.sourceTraceId,
    sourceObjectCandidateId: row.sourceObjectCandidateId,
    semantic: row.semantic,
    functionalClass: row.functionalClass,
  })).sort((left, right) => left.traceId.localeCompare(right.traceId));
  if (JSON.stringify(canonicalTraceRows) !== JSON.stringify(canonicalMatchRows)) {
    issues.push("component matches do not exactly represent the current trace-components artifact");
  }
}
removedTraceIds.forEach((traceId) => {
  if (!(data.matches || []).some((match) => match.sourceTraceId === traceId)) {
    issues.push(`removed trace has no match: ${traceId}`);
  }
  if ((data.placements || []).some((placement) => placement.sourceTraceId === traceId)) {
    issues.push(`trace is both active and removed: ${traceId}`);
  }
});

const placementById = new Map((data.placements || []).map((placement) => [placement.id, placement]));
if (assetLock) {
  const expectedAssetIds = [...new Set(
    (data.placements || []).map((placement) => placement.componentId),
  )].sort();
  const lockedAssetIds = (assetLock.assets || []).map((asset) => asset.id).sort();
  if (JSON.stringify(expectedAssetIds) !== JSON.stringify(lockedAssetIds)
      || materialization.distinctAssetCount !== lockedAssetIds.length
      || materialization.placementCount !== (data.placements || []).length) {
    issues.push("component asset lock does not exactly cover the current placements");
  }
  for (const asset of assetLock.assets || []) {
    const target = path.join(projectRoot, asset.targetPath || "");
    if (!fs.statSync(target, { throwIfNoEntry: false })?.isFile()
        || crypto.createHash("sha256").update(fs.readFileSync(target)).digest("hex") !== asset.runtimeSha256) {
      issues.push(`missing or changed materialized asset: ${asset.id}`);
    }
  }
}
const rawCollisionPairs = componentCollisionPairs(
  data.placements || [],
  (componentId, semantic) => getComponentDefinition(componentId, semantic),
);
const pairKey = (firstId, secondId) => [firstId, secondId].sort().join("::");
const allowedContacts = data.relationHints?.allowedContacts || [];
const allowedContactKeys = new Set();
allowedContacts.forEach((contact) => {
  const first = placementById.get(contact.firstId);
  const second = placementById.get(contact.secondId);
  const classes = new Set([first?.functionalClass, second?.functionalClass]);
  const validIds = Boolean(first && second && first.id !== second.id);
  const validReason = contact.kind === "chair-tucked-under-table";
  const validClasses = classes.size === 2
    && classes.has("dining-chair")
    && classes.has("dining-table");
  const exactFields = Object.keys(contact)
    .every((key) => ["firstId", "secondId", "kind"].includes(key));
  if (!validIds || !validReason || !validClasses || !exactFields) {
    issues.push(`invalid allowed contact: ${contact.firstId} <-> ${contact.secondId}`);
    return;
  }
  allowedContactKeys.add(pairKey(contact.firstId, contact.secondId));
});
const collisionPairs = rawCollisionPairs.filter(
  (collision) => !allowedContactKeys.has(pairKey(collision.firstId, collision.secondId)),
);
collisionPairs.forEach((collision) => {
  advisories.push(`source-layout contact risk: ${collision.firstId} <-> ${collision.secondId}`);
});

function wallFootprint(wall) {
  const dx = wall.end[0] - wall.start[0];
  const dz = wall.end[1] - wall.start[1];
  return rotatedRectangle(
    [(wall.start[0] + wall.end[0]) / 2, (wall.start[1] + wall.end[1]) / 2],
    Math.hypot(dx, dz),
    Number(wall.thickness),
    Math.atan2(dz, dx),
  );
}

const relationHintIssues = [];
const relationHints = data.relationHints;
if (relationHints?.schema !== "interior.layout-relation-hints.v3") {
  relationHintIssues.push("missing or invalid relation hint contract");
}
const allowedHintKeys = new Set([
  "schema", "directionalAxes", "worldOrientations", "facing", "wallAttachment", "allowedContacts", "spaceDividerMarkers",
]);
if (relationHints && Object.keys(relationHints).some((key) => !allowedHintKeys.has(key))) {
  relationHintIssues.push("relation hints contain legacy or calculated fields");
}
const assetIds = new Set([...placementById.values()].map((placement) => placement.componentId));
const axisRecords = new Map();
for (const axis of relationHints?.directionalAxes || []) {
  const key = `${axis.assetId}::${axis.role}`;
  if (axisRecords.has(key)
      || !assetIds.has(axis.assetId)
      || !["front", "back", "headboard"].includes(axis.role)
      || !["+X", "-X", "+Z", "-Z"].includes(axis.localAxis)
      || axis.evidence !== "historical-browser-reviewed-consensus") {
    relationHintIssues.push(`invalid directional axis: ${key}`);
    continue;
  }
  axisRecords.set(key, axis.localAxis);
}

const orientationIds = new Set();
for (const orientation of relationHints?.worldOrientations || []) {
  const placement = placementById.get(orientation.sourceId);
  const vectors = orientation.vectors || {};
  const vectorsValid = Object.values(vectors).every((vector) => (
    Array.isArray(vector)
    && vector.length === 2
    && vector.every(Number.isFinite)
    && Math.abs(Math.hypot(...vector) - 1) <= 0.00001
  ));
  if (!placement
      || orientationIds.has(orientation.sourceId)
      || !Number.isFinite(Number(orientation.yawRadians))
      || !["historical-browser-reviewed-consensus", "source-plan-yaw-only"].includes(orientation.evidence)
      || !vectorsValid
      || !nearlyEqual(orientation.yawRadians, placement.rotationY || 0)
      || JSON.stringify(vectors) !== JSON.stringify(placement.worldOrientation?.vectors || {})) {
    relationHintIssues.push(`invalid world orientation: ${orientation.sourceId}`);
    continue;
  }
  orientationIds.add(orientation.sourceId);
}
if (orientationIds.size !== placementById.size) {
  relationHintIssues.push("world orientations must cover every placement exactly once");
}
const dividerIds = new Set((structure?.semanticDividers || []).map((divider) => divider.id));
const dividerMarkerIds = new Set();
for (const marker of relationHints?.spaceDividerMarkers || []) {
  if (!marker.id
      || dividerMarkerIds.has(marker.id)
      || !dividerIds.has(marker.semanticDividerId)
      || marker.kind !== "space-threshold"
      || marker.visible !== true
      || typeof marker.required !== "boolean"
      || !(Number(marker.width) > 0 && Number(marker.width) <= 0.15)
      || !(Number(marker.height) > 0 && Number(marker.height) <= 0.05)) {
    relationHintIssues.push(`invalid space divider marker: ${marker.id || marker.semanticDividerId}`);
    continue;
  }
  dividerMarkerIds.add(marker.id);
}

for (const relation of relationHints?.facing || []) {
  const sourcePlacement = placementById.get(relation.sourceId);
  const targetPlacement = placementById.get(relation.targetId);
  if (!sourcePlacement
      || !targetPlacement
      || !axisRecords.has(`${sourcePlacement.componentId}::${relation.axisRole}`)
      || Object.keys(relation).some((key) => !["sourceId", "targetId", "axisRole"].includes(key))) {
    relationHintIssues.push(`unresolved facing hint: ${relation.sourceId}`);
  }
}

if (structure) {
  for (const relation of relationHints?.wallAttachment || []) {
    const item = placementById.get(relation.sourceId);
    const wall = (structure.walls || []).find((candidate) => candidate.id === relation.wallId);
    if (!item
        || !wall
        || !axisRecords.has(`${item.componentId}::${relation.axisRole}`)
        || Object.keys(relation).some((key) => !["sourceId", "wallId", "axisRole"].includes(key))) {
      relationHintIssues.push(`unresolved wall attachment hint: ${relation.sourceId}`);
    }
  }
}
issues.push(...relationHintIssues);

const structurePlacementIssues = [];
const heightGuardIssues = [];
const heightGuardAudit = [];
if (structure) {
  (data.placements || []).forEach((placement) => {
    const definition = getComponentDefinition(placement.componentId, placement.semantic);
    const heightAudit = auditPlacementHeight(structure, placement, definition);
    if (heightAudit) heightGuardAudit.push(heightAudit);
    if (heightAudit && !heightAudit.ok) {
      heightGuardIssues.push(
        `${placement.id}: top ${heightAudit.top.toFixed(3)}m exceeds ${heightAudit.limit.toFixed(3)}m guard (${heightAudit.source})`,
      );
    }
    const elevation = Number(placement.elevation ?? definition?.defaultElevation ?? 0);
    if (definition?.mountType === "wall" && !(elevation > 0)) {
      heightGuardIssues.push(`${placement.id}: wall cabinet requires positive elevation`);
    }
    const footprint = componentFootprint(placement, definition);
    if (!footprint.length) return;
    const hostWallIds = new Set(placement.hostWallIds || []);
    const hostWalls = (structure.walls || []).filter(
      (wall) => wall.enabled !== false && hostWallIds.has(wall.id),
    );
    const attachedToHost = placement.attachmentMode === "flush-to-host-wall"
      && hostWalls.some((wall) => polygonsOverlap(footprint, wallFootprint(wall)));
    const footprintInside = polygonContainedByBoundary(
      footprint,
      structure.floorBoundary || [],
    );
    if (!footprintInside) {
      structurePlacementIssues.push(`${placement.id}: footprint leaves floor boundary`);
      return;
    }
    if (placement.attachmentMode === "flush-to-host-wall" && !attachedToHost) {
      structurePlacementIssues.push(`${placement.id}: detached from host wall`);
      return;
    }
    const wall = (structure.walls || []).find(
      (candidate) => candidate.enabled !== false
        && !hostWallIds.has(candidate.id)
        && polygonsOverlap(footprint, wallFootprint(candidate)),
    );
    if (wall) structurePlacementIssues.push(`${placement.id}: intersects wall ${wall.id}`);
    const connection = (structure.connections || []).find(
      (candidate) => ["door", "open-passage", "sliding-door"].includes(candidate.kind)
        && polygonsOverlap(footprint, connectionOpeningPolygon(candidate)),
    );
    if (connection) {
      structurePlacementIssues.push(
        `${placement.id}: crosses door or passage opening ${connection.id}`,
      );
    }
  });
}
issues.push(...heightGuardIssues);
advisories.push(...scaleAdvisories);
const outsideFloorFootprintIssues = structurePlacementIssues.filter(
  (item) => item.includes("footprint leaves floor boundary"),
);
issues.push(...outsideFloorFootprintIssues);
advisories.push(...structurePlacementIssues
  .filter((item) => !outsideFloorFootprintIssues.includes(item))
  .map((item) => `source-layout structure risk: ${item}`));

const result = {
  ok: issues.length === 0,
  sourceObjects: sourceTotal,
  matches: data.matches?.length || 0,
  placements: data.placements?.length || 0,
  sourcePlacements: sourcePlacements.length,
  userExplicitAdditions: additionPlacements.length,
  removedSourceTraceIds: removedTraceIds,
  uniqueTraceIds: traceIds.size,
  uniquePlacementIds: placementIds.size,
  traceExactPlacementCount,
  reviewedAdjustmentCount,
  outlineExactPlacementCount,
  rawCollisionPairs,
  allowedContacts,
  collisionPairs,
  scaleAdvisories,
  relationHintIssues,
  relationHintSchema: relationHints?.schema || null,
  spaceDividerMarkerCount: dividerMarkerIds.size,
  structurePlacementIssues,
  outsideFloorFootprintIssues,
  heightGuardIssues,
  heightGuardAudit,
  projectRuntimeAssetBytes: computedProjectRuntimeBytes,
  projectRuntimeAssetBudgetBytes: Number(assetBudget?.maxProjectRuntimeBytes || 0),
  projectDistinctAssetCount: runtimeBytesByAsset.size,
  projectBudgetOptimizationSteps: assetBudget?.optimizationSteps?.length || 0,
  advisories,
  structureChecked: Boolean(structure),
  fallbackCount: (data.matches || []).filter((match) => Object.prototype.hasOwnProperty.call(match, "fallback")).length,
  issues,
};
console.log(JSON.stringify(result, null, 2));
if (!result.ok) process.exit(1);
