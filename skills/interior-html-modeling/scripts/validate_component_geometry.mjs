#!/usr/bin/env node
import fs from "node:fs";
import { register } from "node:module";

register("./node_component_loader.mjs", import.meta.url);

const {
  COMPONENT_CATALOG,
  createWhiteModelComponent,
} = await import("@interior/component-library");

const layoutPath = process.argv[2];
if (!layoutPath) {
  console.error("usage: validate_component_geometry.mjs <component-layout.json>");
  process.exit(2);
}

const layout = JSON.parse(fs.readFileSync(layoutPath, "utf8"));
const placements = layout.placements || [];
const unmatched = placements.filter((placement) => placement.assetStatus !== "matched" || !placement.componentId);
const projectComponentIds = new Set(placements.map((placement) => placement.componentId));
const projectDefinitions = COMPONENT_CATALOG.filter((definition) => projectComponentIds.has(definition.id));

const issues = [];
const assetPaths = new Map();
const sourceKeys = new Map();
if (layout.schema !== "interior.component-layout.v5") issues.push("trace-bound check requires component-layout.v5");
if (unmatched.length) issues.push(`non-managed placements are forbidden: ${unmatched.map((item) => item.id).join(", ")}`);
for (const componentId of projectComponentIds) {
  if (!COMPONENT_CATALOG.some((definition) => definition.id === componentId)) {
    issues.push(`${componentId}: component definition is missing`);
  }
}
for (const definition of projectDefinitions) {
  if (definition.builder !== "external-gltf") issues.push(`${definition.id}: procedural geometry is retired`);
  const scaleMode = definition.editorCapabilities?.scaleMode || "uniform-only";
  if (!definition.lockAspectRatio
      && (scaleMode !== "axis-limited" || definition.shapeClass !== "rectilinear")) {
    issues.push(`${definition.id}: undeclared non-proportional authored geometry`);
  }
  if (definition.primitiveBoxOnly !== false) issues.push(`${definition.id}: primitive-only geometry is forbidden`);
  const pathOwner = assetPaths.get(definition.assetPath);
  if (pathOwner) issues.push(`${definition.id}: runtime path duplicates ${pathOwner}`);
  else assetPaths.set(definition.assetPath, definition.id);
  const sourceKey = `${definition.sourceProvenance}:${definition.sourceId}`;
  const sourceOwner = sourceKeys.get(sourceKey);
  if (sourceOwner) issues.push(`${definition.id}: source model duplicates ${sourceOwner}`);
  else sourceKeys.set(sourceKey, definition.id);
}

let traceBoundGeometryCount = 0;
let explicitAdditionGeometryCount = 0;
for (const placement of placements) {
  try {
    const group = createWhiteModelComponent(placement.componentId, {
      semantic: placement.libraryPartition || placement.semantic,
      uniformScale: placement.uniformScale,
      targetDimensions: placement.targetDimensions,
      visualDimensions: placement.visualDimensions,
      shapeAdjustments: placement.shapeAdjustments,
      finishPreset: placement.finishPreset,
    });
    const footprint = group.getObjectByName("trace-bound-footprint");
    if (placement.placementOrigin === "user-explicit-addition") {
      const validAddition = group.userData.externalAssetDeferred === true
        && group.userData.traceFootprintBound === false
        && !footprint
        && Number(group.userData.visualDimensions?.width) > 0
        && Number(group.userData.visualDimensions?.depth) > 0
        && Number(group.userData.visualDimensions?.height) > 0;
      if (!validAddition) issues.push(`${placement.id}: explicit addition geometry contract failed`);
      else explicitAdditionGeometryCount += 1;
      continue;
    }
    const expectedHash = placement.shapeAdjustments?.sourceOutlineHash;
    const expectedOutline = placement.sourceShapeEvidence?.outline;
    const valid = group.userData.externalAssetDeferred === true
      && group.userData.traceFootprintBound === true
      && group.userData.sourceOutlineHash === expectedHash
      && footprint?.userData.traceFootprint === true
      && footprint.userData.sourceOutlineHash === expectedHash
      && JSON.stringify(footprint.userData.normalizedOutline) === JSON.stringify(expectedOutline);
    if (!valid) issues.push(`${placement.id}: collision footprint does not reference the source trace`);
    else traceBoundGeometryCount += 1;
  } catch (error) {
    issues.push(`${placement.id}: ${error.message}`);
  }
}

const result = {
  ok: issues.length === 0,
  catalogComponentCount: COMPONENT_CATALOG.length,
  componentCount: projectDefinitions.length,
  placementCount: placements.length,
  externalAssetCount: projectDefinitions.filter((item) => item.builder === "external-gltf").length,
  proceduralAssetCount: projectDefinitions.filter((item) => item.builder !== "external-gltf").length,
  uniqueRuntimePathCount: assetPaths.size,
  uniqueSourceModelCount: sourceKeys.size,
  traceBoundGeometryCount,
  explicitAdditionGeometryCount,
  issues,
};
console.log(JSON.stringify(result, null, 2));
if (!result.ok) process.exit(1);
