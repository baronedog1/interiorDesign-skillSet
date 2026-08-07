import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  COMPONENT_CATALOG,
  COMPONENT_CATEGORIES,
  COMPONENT_LIBRARY_BY_SEMANTIC,
  COMPONENT_LIBRARY_VERSION,
  FIXED_PURPLE,
  FIXED_PURPLE_COMPONENTS,
  MOVABLE_GREEN,
  MOVABLE_GREEN_COMPONENTS,
  assertComponentRoute,
  getComponentDefinition,
} from "@interior/component-catalog";

const APPEARANCE_MODES = new Set(["white-model", "source-color"]);
const FINISH_PRESETS = new Set(["source-authored", "modern-light-wood"]);
const gltfLoader = new GLTFLoader();
const externalSceneCache = new Map();

function cloneMaterial(material) {
  if (Array.isArray(material)) return material.map((item) => item.clone());
  return material.clone();
}

function mapMaterial(material, mapper) {
  if (Array.isArray(material)) return material.map(mapper);
  return mapper(material);
}

function whiteMaterialFromSource(sourceMaterial) {
  return mapMaterial(sourceMaterial, (source) => {
    const material = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.82,
      metalness: 0,
      emissive: 0xffffff,
      emissiveIntensity: 0.16,
      transparent: Boolean(source.transparent),
      opacity: source.transparent ? Math.max(0.22, Number(source.opacity || 1)) : 1,
      side: source.side,
      alphaTest: source.alphaTest || 0,
    });
    material.name = `${source.name || "material"}-white-model`;
    return material;
  });
}

function normalizeFinishPreset(value) {
  const preset = value || "source-authored";
  if (!FINISH_PRESETS.has(preset)) throw new Error(`unsupported component finish preset: ${preset}`);
  return preset;
}

function projectFinishMaterialFromSource(sourceMaterial, finishPreset) {
  const preset = normalizeFinishPreset(finishPreset);
  if (preset === "source-authored") return cloneMaterial(sourceMaterial);
  return mapMaterial(sourceMaterial, (source) => {
    const material = source.clone();
    const name = String(source.name || "").toLowerCase();
    const isMetal = /(metal|chrome|handle|border|fastener|oven|hood)/.test(name);
    const isCounter = /(counter|ceramic|fayence|sink)/.test(name);
    const isBody = /(body|box|white)/.test(name);
    const isGlass = /(glass)/.test(name);
    const isWood = /(door|closet|cupboard|plastic|pLASTIC)/i.test(source.name || "");
    for (const key of ["map", "aoMap", "bumpMap", "displacementMap", "emissiveMap", "metalnessMap", "normalMap", "roughnessMap"]) {
      if (key in material) material[key] = null;
    }
    if (material.color) {
      if (isGlass) material.color.setHex(0x64706d);
      else if (isMetal) material.color.setHex(0x454540);
      else if (isCounter) material.color.setHex(0xd8d4cc);
      else if (isBody) material.color.setHex(0xe4ded4);
      else if (isWood) material.color.setHex(0x9a7555);
      else material.color.setHex(0xa07c5b);
    }
    if ("metalness" in material) material.metalness = isMetal ? 0.62 : 0;
    if ("roughness" in material) material.roughness = isGlass ? 0.22 : isMetal ? 0.36 : 0.68;
    if ("emissive" in material && material.emissive) material.emissive.setHex(0x000000);
    if (isGlass) {
      material.transparent = true;
      material.opacity = 0.48;
      material.depthWrite = false;
    } else {
      material.transparent = false;
      material.opacity = 1;
      material.depthWrite = true;
    }
    material.name = `${source.name || "material"}-${preset}`;
    material.needsUpdate = true;
    return material;
  });
}

function attachAppearanceMaterials(object, whiteModelMaterial, sourceColorMaterial) {
  object.userData.appearanceMaterials = {
    whiteModel: whiteModelMaterial,
    sourceColor: sourceColorMaterial,
  };
}

function normalizeAppearanceMode(mode) {
  if (!APPEARANCE_MODES.has(mode)) throw new Error(`unsupported component appearance: ${mode}`);
  return mode;
}

export function setComponentAppearance(group, mode = "white-model") {
  const appearance = normalizeAppearanceMode(mode);
  group.traverse((object) => {
    if (object.isMesh && object.userData.appearanceMaterials) {
      object.material = appearance === "source-color"
        ? object.userData.appearanceMaterials.sourceColor
        : object.userData.appearanceMaterials.whiteModel;
    }
  });
  group.userData.appearance = appearance;
  return group;
}

export function setAllComponentAppearance(root, mode = "white-model") {
  const appearance = normalizeAppearanceMode(mode);
  root.traverse((object) => {
    if ([MOVABLE_GREEN, FIXED_PURPLE].includes(object.userData?.placementClass) && object.userData?.componentId) {
      setComponentAppearance(object, appearance);
    }
  });
  return appearance;
}

// Kept as an API alias for existing projects; behavior now covers both public partitions.
export const setAllMovableComponentAppearance = setAllComponentAppearance;

function externalAssetUrl(definition) {
  if (definition.assetPath.startsWith("data:")) return definition.assetPath;
  return new URL(definition.assetPath, import.meta.url).href;
}

function loadExternalScene(definition) {
  const url = externalAssetUrl(definition);
  if (!externalSceneCache.has(url)) {
    externalSceneCache.set(url, new Promise((resolve, reject) => {
      gltfLoader.load(url, (gltf) => resolve(gltf.scene), undefined, reject);
    }));
  }
  return externalSceneCache.get(url);
}

function prepareExternalMeshMaterials(root, definition, finishPreset) {
  root.traverse((object) => {
    if (!object.isMesh) return;
    if (definition.sourceProvenance === "sweet-home-3d-blendswap-cc0") {
      object.geometry = object.geometry.clone();
      object.geometry.deleteAttribute("normal");
      object.geometry.computeVertexNormals();
      object.geometry.normalizeNormals();
    }
    const sourceColorMaterial = projectFinishMaterialFromSource(object.material, finishPreset);
    const whiteModelMaterial = whiteMaterialFromSource(sourceColorMaterial);
    attachAppearanceMaterials(object, whiteModelMaterial, sourceColorMaterial);
    object.castShadow = true;
    object.receiveShadow = true;
  });
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)];
}

async function mountExternalComponent(group, definition, uniformScale, axisScale, appearance, finishPreset) {
  const prototype = await loadExternalScene(definition);
  const model = prototype.clone(true);
  model.name = `${definition.id}-authored-model`;
  prepareExternalMeshMaterials(model, definition, finishPreset);
  model.updateMatrixWorld(true);

  const bounds = new THREE.Box3().setFromObject(model);
  const measured = bounds.getSize(new THREE.Vector3());
  if ([measured.x, measured.y, measured.z].some((value) => !Number.isFinite(value) || value <= 0)) {
    throw new Error(`${definition.id}: external model has invalid bounds`);
  }
  const authored = definition.defaultDimensions;
  const canonicalRatios = [
    authored.width / measured.x,
    authored.height / measured.y,
    authored.depth / measured.z,
  ];
  const canonicalScale = median(canonicalRatios);
  const ratioSpread = (Math.max(...canonicalRatios) - Math.min(...canonicalRatios)) / canonicalScale;
  if (!Number.isFinite(canonicalScale) || canonicalScale <= 0 || ratioSpread > 0.35) {
    throw new Error(`${definition.id}: catalog dimensions disagree with source GLB bounds`);
  }
  model.scale.set(
    canonicalScale * uniformScale * axisScale.width,
    canonicalScale * uniformScale * axisScale.height,
    canonicalScale * uniformScale * axisScale.depth,
  );
  model.updateMatrixWorld(true);

  const scaledBounds = new THREE.Box3().setFromObject(model);
  const scaledCenter = scaledBounds.getCenter(new THREE.Vector3());
  model.position.x -= scaledCenter.x;
  model.position.y -= scaledBounds.min.y;
  model.position.z -= scaledCenter.z;
  model.updateMatrixWorld(true);
  group.add(model);
  setComponentAppearance(group, appearance);
  group.userData.externalAssetReady = true;
  group.userData.authoredBounds = {
    width: scaledBounds.max.x - scaledBounds.min.x,
    depth: scaledBounds.max.z - scaledBounds.min.z,
    height: scaledBounds.max.y - scaledBounds.min.y,
  };
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("interior-component-ready", {
      detail: { componentId: definition.id, group },
    }));
  }
  return group;
}

function addTraceBoundFootprint(group, dimensions, adjustments = {}) {
  const outline = adjustments.outline;
  if (!Array.isArray(outline) || outline.length < 4) return null;
  const points = outline.map(([x, z]) => new THREE.Vector2(
    Number(x) * dimensions.width,
    -Number(z) * dimensions.depth,
  ));
  if (points.some((point) => !Number.isFinite(point.x) || !Number.isFinite(point.y))) {
    throw new Error(`${group.name}: trace footprint contains invalid coordinates`);
  }
  const geometry = new THREE.ExtrudeGeometry(new THREE.Shape(points), {
    depth: 0.01,
    bevelEnabled: false,
    curveSegments: 12,
    steps: 1,
  });
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ visible: false }));
  mesh.name = "trace-bound-footprint";
  mesh.rotation.x = -Math.PI / 2;
  mesh.userData.traceFootprint = true;
  mesh.userData.sourceOutlineHash = adjustments.sourceOutlineHash || null;
  mesh.userData.normalizedOutline = outline.map((point) => [...point]);
  mesh.visible = false;
  group.add(mesh);
  return mesh;
}

export function clampUniformScale(definition, scale) {
  const value = Number(scale ?? 1);
  if (!Number.isFinite(value)) return 1;
  return Math.max(definition.uniformScaleRange.min, Math.min(definition.uniformScaleRange.max, value));
}

export function scaledDimensions(definition, uniformScale = 1) {
  const scale = clampUniformScale(definition, uniformScale);
  return {
    width: definition.defaultDimensions.width * scale,
    depth: definition.defaultDimensions.depth * scale,
    height: definition.defaultDimensions.height * scale,
  };
}

function clampAxisScale(definition, axis, value) {
  const range = definition.editorCapabilities?.axisScaleRange?.[axis];
  if (!Array.isArray(range) || range.length !== 2) return 1;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 1;
  return Math.max(Number(range[0]), Math.min(Number(range[1]), numeric));
}

export function resolvedVisualScale(definition, options = {}) {
  const uniformScale = clampUniformScale(definition, options.uniformScale ?? 1);
  const base = scaledDimensions(definition, uniformScale);
  const requested = options.visualDimensions;
  const scaleMode = definition.editorCapabilities?.scaleMode || "uniform-only";
  if (!requested) {
    return {
      uniformScale,
      axisScale: { width: 1, depth: 1, height: 1 },
      dimensions: base,
      scaleMode,
    };
  }
  if (scaleMode !== "axis-limited") {
    throw new Error(`${definition.id}: visualDimensions are only allowed for reviewed axis-limited components`);
  }
  const dimensions = {};
  const axisScale = {};
  for (const axis of ["width", "depth", "height"]) {
    const value = Number(requested[axis] ?? base[axis]);
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`${definition.id}: visualDimensions.${axis} must be positive`);
    }
    axisScale[axis] = clampAxisScale(definition, axis, value / base[axis]);
    dimensions[axis] = base[axis] * axisScale[axis];
  }
  return { uniformScale, axisScale, dimensions, scaleMode };
}

export function resolvedComponentDimensions(definition, options = {}) {
  const scaled = scaledDimensions(definition, options.uniformScale ?? 1);
  const target = options.targetDimensions;
  if (!target) return scaled;
  const width = Number(target.width);
  const depth = Number(target.depth);
  const height = target.height === undefined ? scaled.height : Number(target.height);
  if (![width, depth, height].every((value) => Number.isFinite(value) && value > 0)) {
    throw new Error(`${definition.id}: targetDimensions must contain positive width/depth/height values`);
  }
  return { width, depth, height };
}

export function createWhiteModelComponent(componentId, options = {}) {
  const definition = options.semantic
    ? assertComponentRoute(componentId, options.semantic)
    : getComponentDefinition(componentId);
  if (!definition) throw new Error(`unknown componentId: ${componentId}`);
  if (definition.builder !== "external-gltf") throw new Error(`${componentId}: procedural catalog builders are retired`);
  const visual = resolvedVisualScale(definition, options);
  const uniformScale = visual.uniformScale;
  const authoredDimensions = visual.dimensions;
  const footprintDimensions = resolvedComponentDimensions(definition, {
    uniformScale,
    targetDimensions: options.targetDimensions,
  });
  const appearance = normalizeAppearanceMode(options.appearance || "white-model");
  const finishPreset = normalizeFinishPreset(options.finishPreset);
  const group = new THREE.Group();
  group.name = componentId;
  Object.assign(group.userData, {
    componentId,
    uniformScale,
    dimensions: footprintDimensions,
    authoredDimensions,
    visualDimensions: visual.dimensions,
    axisScale: visual.axisScale,
    scaleMode: visual.scaleMode,
    dimensionMode: options.targetDimensions
      ? `trace-footprint-with-${visual.scaleMode}-visual-scale`
      : visual.scaleMode,
    appearance,
    finishPreset,
    appearanceVariants: [...definition.appearanceVariants],
    placementClass: definition.placementClass,
    shapeClass: definition.shapeClass,
    shapeAdjustments: { ...(options.shapeAdjustments || {}) },
    traceFootprintBound: Boolean(options.shapeAdjustments?.outline?.length),
    sourceOutlineHash: options.shapeAdjustments?.sourceOutlineHash || null,
    sourceLicense: definition.sourceLicense,
    sourceUrl: definition.sourceUrl,
    researchOnly: definition.researchOnly,
    commercialUseAllowed: definition.commercialUseAllowed,
    commercialReviewRequired: definition.commercialReviewRequired,
    licenseEvidence: definition.licenseEvidence,
    externalAssetReady: false,
  });
  addTraceBoundFootprint(group, footprintDimensions, options.shapeAdjustments);
  if (typeof window === "undefined") {
    group.userData.externalAssetDeferred = true;
    group.userData.readyPromise = Promise.resolve(group);
  } else {
    group.userData.readyPromise = mountExternalComponent(
      group,
      definition,
      uniformScale,
      visual.axisScale,
      appearance,
      finishPreset,
    );
  }
  return group;
}

export function libraryAudit() {
  const ids = new Set();
  const issues = [];
  for (const item of COMPONENT_CATALOG) {
    if (ids.has(item.id)) issues.push(`duplicate component id: ${item.id}`);
    ids.add(item.id);
    if (item.builder !== "external-gltf") issues.push(`retired procedural builder: ${item.id}`);
    const scaleMode = item.editorCapabilities?.scaleMode || "uniform-only";
    if (!item.lockAspectRatio && scaleMode !== "axis-limited") {
      issues.push(`undeclared non-proportional scale: ${item.id}`);
    }
    if (scaleMode === "axis-limited"
        && (item.shapeClass !== "rectilinear" || !item.editorCapabilities?.axisScaleRange)) {
      issues.push(`invalid axis-limited component: ${item.id}`);
    }
    if (item.geometryProfile !== "authored-gltf-pbr-v2") issues.push(`invalid geometry profile: ${item.id}`);
    if (!item.assetPath || !item.sourceUrl || !item.sourceLicense) issues.push(`incomplete provenance: ${item.id}`);
    if (!item.appearanceVariants?.includes("white-model") || !item.appearanceVariants?.includes("source-color")) {
      issues.push(`missing dual appearance: ${item.id}`);
    }
    if (item.primitiveBoxOnly !== false) issues.push(`primitive-only asset: ${item.id}`);
    if (item.researchOnly) issues.push(`research use is not allowed: ${item.id}`);
    if (item.sourceProvenance === "amazon-berkeley-objects"
        && (item.commercialReviewRequired !== true || item.commercialUseAllowed !== false)) {
      issues.push(`ABO registry conflict policy is missing: ${item.id}`);
    }
    if (!["CC0-1.0", "CC-BY-4.0"].includes(item.sourceLicense)) issues.push(`unsupported public license: ${item.id}`);
  }
  for (const [semantic, catalog] of Object.entries(COMPONENT_LIBRARY_BY_SEMANTIC)) {
    for (const item of catalog) {
      if (item.placementClass !== semantic) issues.push(`cross-library component: ${item.id}`);
    }
  }
  return {
    version: COMPONENT_LIBRARY_VERSION,
    componentCount: COMPONENT_CATALOG.length,
    partitionCounts: {
      [MOVABLE_GREEN]: MOVABLE_GREEN_COMPONENTS.length,
      [FIXED_PURPLE]: FIXED_PURPLE_COMPONENTS.length,
    },
    categoryCount: Object.keys(COMPONENT_CATEGORIES).length,
    builderCount: 1,
    externalAssetCount: COMPONENT_CATALOG.length,
    retainedAccessoryCount: 0,
    dualAppearanceCount: COMPONENT_CATALOG.filter((item) => item.appearanceVariants?.length === 2).length,
    researchOnlyCount: COMPONENT_CATALOG.filter((item) => item.researchOnly).length,
    researchApprovedCount: COMPONENT_CATALOG.filter((item) => !item.researchOnly).length,
    commercialSafeCount: COMPONENT_CATALOG.filter((item) => item.commercialUseAllowed).length,
    commercialReviewRequiredCount: COMPONENT_CATALOG.filter((item) => item.commercialReviewRequired).length,
    attributionRequiredCount: COMPONENT_CATALOG.filter((item) => item.sourceLicense === "CC-BY-4.0").length,
    issues,
    ok: COMPONENT_CATALOG.length > 0 && issues.length === 0,
  };
}

export {
  COMPONENT_CATALOG,
  COMPONENT_CATEGORIES,
  COMPONENT_LIBRARY_BY_SEMANTIC,
  COMPONENT_LIBRARY_VERSION,
  FIXED_PURPLE,
  FIXED_PURPLE_COMPONENTS,
  MOVABLE_GREEN,
  MOVABLE_GREEN_COMPONENTS,
  assertComponentRoute,
  getComponentDefinition,
};
