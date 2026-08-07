#!/usr/bin/env node
import fs from "node:fs";
import {
  COMPONENT_CATALOG,
  createWhiteModelComponent,
  libraryAudit,
} from "@interior/component-library";

const issues = [];
const assetPaths = new Map();
const sourceKeys = new Map();
for (const definition of COMPONENT_CATALOG) {
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

const layoutPath = process.argv[2];
let traceBoundGeometryCount = 0;
let explicitAdditionGeometryCount = 0;
if (layoutPath) {
  const layout = JSON.parse(fs.readFileSync(layoutPath, "utf8"));
  if (layout.schema !== "interior.component-layout.v4") issues.push("trace-bound check requires component-layout.v4");
  for (const placement of layout.placements || []) {
    try {
      const group = createWhiteModelComponent(placement.componentId, {
        semantic: placement.semantic,
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
}

const baseAudit = libraryAudit();
const result = {
  ok: baseAudit.ok && issues.length === 0,
  componentCount: COMPONENT_CATALOG.length,
  externalAssetCount: COMPONENT_CATALOG.filter((item) => item.builder === "external-gltf").length,
  proceduralAssetCount: COMPONENT_CATALOG.filter((item) => item.builder !== "external-gltf").length,
  uniqueRuntimePathCount: assetPaths.size,
  uniqueSourceModelCount: sourceKeys.size,
  traceBoundGeometryCount,
  explicitAdditionGeometryCount,
  issues,
};
console.log(JSON.stringify(result, null, 2));
if (!result.ok) process.exit(1);
