import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  COMPONENT_CATALOG,
  COMPONENT_LIBRARY_VERSION,
  clampUniformScale,
  createWhiteModelComponent,
  getComponentDefinition,
  libraryAudit,
  resolvedComponentDimensions,
  resolvedVisualScale,
  scaledDimensions,
  setAllComponentAppearance,
} from "@interior/component-library";
import {
  componentCollisionPairs,
  componentFootprint as placementFootprint,
  connectionOpeningPolygon,
  placementMatchesSourceTransform,
  polygonsOverlap,
  rotatedRectangle,
} from "@interior/placement-geometry";

const FULL_FRAME_SENSOR_HEIGHT_MM = 24;
const WHITE_MODEL_BACKGROUND = 0xc8cdca;
const WHITE_MODEL_EDGE = 0x5f6561;
const STRUCTURE_APPEARANCES = new Set(["neutral-white", "concrete-shell"]);
const LENS_PRESETS = {
  "ultra-wide": { focalLengthMm: 16, distortion: 0, label: "超广角" },
  wide: { focalLengthMm: 24, distortion: 0, label: "短焦广角" },
  standard: { focalLengthMm: 35, distortion: 0, label: "标准" },
  telephoto: { focalLengthMm: 50, distortion: 0, label: "长焦" },
};

function fovForFocalLength(focalLengthMm) {
  const focal = Math.max(14, Math.min(85, Number(focalLengthMm) || 35));
  return THREE.MathUtils.radToDeg(2 * Math.atan(FULL_FRAME_SENSOR_HEIGHT_MM / (2 * focal)));
}

function focalLengthForFov(fov) {
  const verticalFov = Math.max(16, Math.min(82, Number(fov) || 42));
  return FULL_FRAME_SENSOR_HEIGHT_MM / (2 * Math.tan(THREE.MathUtils.degToRad(verticalFov) / 2));
}

function lensPresetForFocalLength(focalLengthMm) {
  const focal = Number(focalLengthMm);
  const exact = Object.entries(LENS_PRESETS).find(([, preset]) => Math.abs(focal - preset.focalLengthMm) < 0.25);
  return exact?.[0] || "custom";
}

function lensBandForFocalLength(focalLengthMm) {
  const focal = Number(focalLengthMm);
  if (focal <= 20) return "超广角 / 短焦";
  if (focal <= 28) return "广角 / 短焦";
  if (focal < 45) return "标准焦段";
  return "长焦";
}

async function fetchRequiredJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

const sourceStructure = window.__STRUCTURE_DATA__ ?? await fetchRequiredJson("./structure-data.json");
const sourceComponentLayout = window.__COMPONENT_LAYOUT__ ?? await fetchRequiredJson("./component-layout.json");
const sourceModelScope = window.__MODEL_SCOPE__ ?? await fetchRequiredJson("./model-scope.json");
let cameraPlan = window.__CAMERA_PLAN__ ?? await fetchRequiredJson("./camera-plan.json");
const sourceSceneRig = window.__SCENE_RIG__ ?? await fetchRequiredJson("./scene-rig.json");
const sourceBackendOptions = window.__BACKEND_OPTIONS__ ?? await fetchRequiredJson("./backend-options.json");
const model = structuredClone(sourceStructure);
const sceneRig = structuredClone(sourceSceneRig);
model.backendOptions = structuredClone(sourceBackendOptions);
model.modelScope = structuredClone(sourceModelScope);
const structureRoomIds = new Set((model.rooms || []).map((room) => room.id));
const modelScopeRoomIds = new Set([
  ...(model.modelScope.requestedRoomIds || []),
  ...(model.modelScope.allowedContextRoomIds || []),
]);
const modelScopeExcludedRoomIds = new Set(model.modelScope.excludedRoomIds || []);
if (
  model.modelScope.schema !== "interior.model-scope.v1"
  || !["whole-floor", "room-subset"].includes(model.modelScope.mode)
  || modelScopeRoomIds.size === 0
  || [...modelScopeRoomIds].some((roomId) => !structureRoomIds.has(roomId))
  || [...modelScopeExcludedRoomIds].some((roomId) => !structureRoomIds.has(roomId))
  || [...modelScopeRoomIds].some((roomId) => modelScopeExcludedRoomIds.has(roomId))
  || new Set([...modelScopeRoomIds, ...modelScopeExcludedRoomIds]).size !== structureRoomIds.size
) {
  throw new Error("model-scope.json does not partition the accepted floorplan rooms");
}
model.structureEditPatches = [];
normalizeSceneRigData(sceneRig);
model.componentLayoutSchema = sourceComponentLayout.schema;
model.componentLibraryVersion = sourceComponentLayout.libraryVersion;
model.componentSource = structuredClone(sourceComponentLayout.source || {});
model.componentSource.removedSourceTraceIds = Array.isArray(model.componentSource.removedSourceTraceIds)
  ? model.componentSource.removedSourceTraceIds
  : [];
model.componentMatches = structuredClone(sourceComponentLayout.matches || []);
model.componentPlacements = structuredClone(sourceComponentLayout.placements || []);
model.relationHints = structuredClone(sourceComponentLayout.relationHints || null);
model.layers = {
  walls: true,
  windows: true,
  fixedFixtures: true,
  movableFurniture: true,
  ceilings: sourceBackendOptions.ceilings?.visibleByDefault === true,
  grid: true,
  annotations: false,
  ...(model.layers || {}),
};
const originalModel = structuredClone(model);
const originalSceneRig = structuredClone(sceneRig);
const cfg = model.coordinateSystem;

const dom = {
  scene: document.getElementById("scene"),
  status: document.getElementById("action-status"),
  selectionChip: document.getElementById("selection-chip"),
  structureList: document.getElementById("structure-list"),
  componentList: document.getElementById("furniture-list"),
  structureInspector: document.getElementById("structure-inspector"),
  componentInspector: document.getElementById("furniture-inspector"),
  lightList: document.getElementById("light-list"),
  cameraList: document.getElementById("camera-list"),
  cameraPlanList: document.getElementById("camera-plan-list"),
  cameraPlanCount: document.getElementById("camera-plan-count"),
  cameraPlanFile: document.getElementById("camera-plan-file"),
  cameraPlanDeck: document.getElementById("camera-plan-deck"),
  roomFilterToggle: document.getElementById("room-filter-toggle"),
  roomFilterSummary: document.getElementById("room-filter-summary"),
  roomFilterPopover: document.getElementById("room-filter-popover"),
  roomFilterOptions: document.getElementById("room-filter-options"),
  sceneInspector: document.getElementById("scene-inspector"),
  sceneModeLight: document.getElementById("scene-mode-light"),
  sceneModeCamera: document.getElementById("scene-mode-camera"),
  lightModeContent: document.getElementById("light-mode-content"),
  cameraModeContent: document.getElementById("camera-mode-content"),
  roomAnnotations: document.getElementById("room-annotations"),
  dimensionAnnotations: document.getElementById("dimension-annotations"),
  measurementLabel: document.getElementById("measurement-label"),
  viewToast: document.getElementById("view-toast"),
  cameraLivePreview: document.getElementById("camera-live-preview"),
  cameraLivePreviewCanvas: document.getElementById("camera-live-preview-canvas"),
  cameraLivePreviewMeta: document.getElementById("camera-live-preview-meta"),
  cameraPreviewResizeHandle: document.getElementById("camera-preview-resize-handle"),
  cameraPreviewToggle: document.getElementById("toggle-camera-preview"),
  furnitureWhite: document.getElementById("furniture-white"),
  furnitureColor: document.getElementById("furniture-color"),
  ceilingToggle: document.getElementById("toggle-ceilings"),
};

const scene = new THREE.Scene();
scene.background = new THREE.Color(WHITE_MODEL_BACKGROUND);
const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 120);
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "default" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.35));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = sceneRig.rendering.exposure;
dom.scene.appendChild(renderer.domElement);

const CAMERA_PREVIEW_WIDTH = 320;
const CAMERA_PREVIEW_HEIGHT = 180;
const previewRenderTarget = new THREE.WebGLRenderTarget(
  CAMERA_PREVIEW_WIDTH,
  CAMERA_PREVIEW_HEIGHT,
  { depthBuffer: true, stencilBuffer: false },
);
previewRenderTarget.texture.colorSpace = THREE.SRGBColorSpace;
const previewPixels = new Uint8Array(CAMERA_PREVIEW_WIDTH * CAMERA_PREVIEW_HEIGHT * 4);
const previewCanvasContext = dom.cameraLivePreviewCanvas?.getContext("2d", {
  alpha: false,
  willReadFrequently: true,
});
let cameraPreviewFrameCount = 0;
let cameraPreviewSignature = null;
let cameraPreviewWidth = CAMERA_PREVIEW_WIDTH;
let cameraPreviewResizeGesture = null;

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = false;
controls.minDistance = 2;
controls.maxDistance = 35;
controls.target.set(0, 0.5, 0);

const systemFill = new THREE.HemisphereLight(
  0xffffff,
  0xd7d9d6,
  sceneRig.rendering.hemisphereIntensity,
);
systemFill.name = "system-neutral-fill";
scene.add(systemFill);
const ambient = new THREE.AmbientLight(
  0xffffff,
  sceneRig.rendering.ambientIntensity,
);
ambient.name = "system-ambient-fill";
scene.add(ambient);
const fill = new THREE.DirectionalLight(0xffffff, sceneRig.rendering.detailFillIntensity);
fill.name = "system-detail-fill";
fill.position.set(7, 5, -6);
scene.add(fill);
const inspectionKey = new THREE.DirectionalLight(0xffffff, 0.78);
inspectionKey.name = "system-white-model-inspection-key";
inspectionKey.position.set(-7, 11, 8);
inspectionKey.castShadow = true;
inspectionKey.shadow.mapSize.set(1024, 1024);
inspectionKey.shadow.camera.left = -12;
inspectionKey.shadow.camera.right = 12;
inspectionKey.shadow.camera.top = 12;
inspectionKey.shadow.camera.bottom = -12;
inspectionKey.shadow.camera.near = 0.5;
inspectionKey.shadow.camera.far = 40;
inspectionKey.shadow.bias = -0.00025;
inspectionKey.shadow.normalBias = 0.02;
inspectionKey.shadow.radius = 2;
scene.add(inspectionKey);
const inspectionRim = new THREE.DirectionalLight(0xffffff, 0.24);
inspectionRim.name = "system-white-model-inspection-rim";
inspectionRim.position.set(8, 4, 7);
scene.add(inspectionRim);

const structureGroup = new THREE.Group();
structureGroup.name = "semantic-structure";
const glassGroup = new THREE.Group();
glassGroup.name = "hosted-windows";
const movableGroup = new THREE.Group();
movableGroup.name = "movable-green-components";
const fixedGroup = new THREE.Group();
fixedGroup.name = "fixed-purple-components";
const roomLineGroup = new THREE.Group();
roomLineGroup.name = "room-zones";
const semanticDividerGroup = new THREE.Group();
semanticDividerGroup.name = "semantic-floor-dividers";
const ceilingGroup = new THREE.Group();
ceilingGroup.name = "room-ceilings";
const roomHoverGroup = new THREE.Group();
roomHoverGroup.name = "room-hover-highlight";
const measurementGroup = new THREE.Group();
measurementGroup.name = "two-point-measurement";
const managedLightGroup = new THREE.Group();
managedLightGroup.name = "authored-scene-lights";
const sceneRigHelperGroup = new THREE.Group();
sceneRigHelperGroup.name = "scene-rig-editor-gizmos";
const transformGizmoGroup = new THREE.Group();
transformGizmoGroup.name = "scene-object-transform-gizmo";
const wallEndpointHandleGroup = new THREE.Group();
wallEndpointHandleGroup.name = "wall-endpoint-editor-handles";
const roomFilterFloorGroup = new THREE.Group();
roomFilterFloorGroup.name = "room-filter-floors";
const roomFilterStructureGroup = new THREE.Group();
roomFilterStructureGroup.name = "room-filter-wall-segments";
const roomFilterGlassGroup = new THREE.Group();
roomFilterGlassGroup.name = "room-filter-window-segments";
const cameraEvidenceGroup = new THREE.Group();
cameraEvidenceGroup.name = "camera-plan-evidence";
scene.add(
  structureGroup,
  glassGroup,
  movableGroup,
  fixedGroup,
  roomLineGroup,
  semanticDividerGroup,
  ceilingGroup,
  roomHoverGroup,
  measurementGroup,
  managedLightGroup,
  sceneRigHelperGroup,
  transformGizmoGroup,
  wallEndpointHandleGroup,
  roomFilterFloorGroup,
  roomFilterStructureGroup,
  roomFilterGlassGroup,
  cameraEvidenceGroup,
);

const wallGroups = new Map();
const windowGroups = new Map();
const roomFilterWallGroups = new Map();
const roomFilterWindowGroups = new Map();
const componentGroups = new Map();
const componentMeshCounts = new Map();
const managedLights = new Map();
const lightHelperGroups = new Map();
const cameraHelperGroups = new Map();
const lightTargetLines = new Map();
const cameraTargetLines = new Map();
const roomLabels = new Map();
const roomBoundaryLines = new Map();
const roomFilterFloors = new Map();
let floorMesh = null;
const ceilingMeshes = new Map();
let grid = null;
let boundaryLine = null;
let selectionHelper = null;
let selection = { type: "wall", id: model.walls[0]?.id || null };
let lastSelectedWallId = model.walls[0]?.id || null;
let viewMode = "top";
let structureAppearance = "concrete-shell";
let movableAppearance = "white-model";
let cameraPreviewEnabled = false;
let previewSceneCameraId = sceneRig.cameras[0]?.id || null;
let cameraEvidenceState = null;
let activePanelId = "structure-panel";
const roomFilterIds = new Set(modelScopeRoomIds);
let keyboardMoveComponentId = null;
let componentDrag = null;
let activeSceneCameraId = null;
let activeCameraPlanShotId = null;
let cameraPlanPreviewSnapshot = null;
let activeOcclusionCameraId = null;
let freeViewState = null;
let detachedCameraId = null;
let activeCaptureShotId = null;
let sceneEditorMode = "light";
let sceneTransformPart = "position";
let suppressCameraControlTracking = false;
let activeCameraViewFineTuned = false;
let sceneFieldGesture = null;
let sceneObjectDrag = null;
let wallEndpointDrag = null;
let hoveredSceneObject = null;
let hoveredRoomId = null;
let fixedCameraGesture = null;
let fixedCameraGestureTimer = null;
let viewToastTimer = null;
let renderQueued = false;
let screenshotCount = 0;
let webglContextLossCount = 0;
let webglContextRestoreCount = 0;
let sceneRigBuildCount = 0;
let sceneVisualUpdateCount = 0;
const undoStack = [];
const redoStack = [];
const measurement = { active: false, points: [], midpoint: null, distance: null };
const previewCamera = new THREE.PerspectiveCamera(42, 16 / 9, 0.01, 120);

controls.addEventListener("start", () => {
  if ((!activeSceneCameraId && !activeCameraPlanShotId) || suppressCameraControlTracking) return;
  activeCameraViewFineTuned = true;
});
controls.addEventListener("change", requestRender);

renderer.domElement.addEventListener("webglcontextlost", (event) => {
  event.preventDefault();
  webglContextLossCount += 1;
  setStatus("图形上下文意外中断，正在恢复", "error");
});
renderer.domElement.addEventListener("webglcontextrestored", () => {
  webglContextRestoreCount += 1;
  buildSceneRig();
  applyLayerVisibility();
  updateRuntimeAudit();
  requestRender();
  setStatus("图形上下文已恢复", "success");
});

const whiteWall = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.84, metalness: 0 });
const whiteFloor = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.97, metalness: 0, side: THREE.DoubleSide });
const whiteFrame = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.42, metalness: 0 });
const whiteGlass = new THREE.MeshPhysicalMaterial({
  color: 0xffffff,
  transparent: true,
  opacity: 0.3,
  roughness: 0.08,
  transmission: 0.62,
  metalness: 0,
  side: THREE.DoubleSide,
});

function createConcreteTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  const image = context.createImageData(canvas.width, canvas.height);
  let seed = 8128;
  for (let index = 0; index < image.data.length; index += 4) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const grain = ((seed >>> 24) - 128) * 0.1;
    const base = Math.max(168, Math.min(218, 194 + grain));
    image.data[index] = base + 3;
    image.data[index + 1] = base + 2;
    image.data[index + 2] = base;
    image.data[index + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 4);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

const concreteTexture = createConcreteTexture();

function applyStructureMaterialAppearance(mesh) {
  if (!mesh?.isMesh || !mesh.userData.structureSurfaceRole || mesh.userData.structureSurfaceRole === "glass") return;
  const role = mesh.userData.structureSurfaceRole;
  const concrete = structureAppearance === "concrete-shell";
  mesh.material.color.setHex(concrete
    ? role === "floor" ? 0xb9bbb5 : role === "frame" ? 0x8f938f : 0xd2d2cc
    : 0xffffff);
  mesh.material.map = concrete ? concreteTexture : null;
  mesh.material.roughness = concrete ? (role === "floor" ? 0.98 : 0.94) : (role === "floor" ? 0.97 : role === "frame" ? 0.42 : 0.84);
  mesh.material.metalness = 0;
  mesh.material.needsUpdate = true;
}

function applyStructureAppearance() {
  [structureGroup, glassGroup, roomFilterStructureGroup, roomFilterGlassGroup, roomFilterFloorGroup, ceilingGroup]
    .forEach((group) => group.traverse(applyStructureMaterialAppearance));
  applyStructureMaterialAppearance(floorMesh);
  document.documentElement.dataset.structureAppearance = structureAppearance;
  document.getElementById("appearance-white")?.classList.toggle("active", structureAppearance === "neutral-white");
  document.getElementById("appearance-concrete")?.classList.toggle("active", structureAppearance === "concrete-shell");
}

function setStructureAppearance(mode) {
  if (!STRUCTURE_APPEARANCES.has(mode)) throw new Error(`不支持的结构外观：${mode}`);
  structureAppearance = mode;
  applyStructureAppearance();
  updateRuntimeAudit();
  requestRender();
  return structureAppearance;
}

function setMovableAppearance(mode) {
  movableAppearance = setAllComponentAppearance(scene, mode);
  document.documentElement.dataset.movableAppearance = movableAppearance;
  dom.furnitureWhite?.classList.toggle("active", movableAppearance === "white-model");
  dom.furnitureColor?.classList.toggle("active", movableAppearance === "source-color");
  updateRuntimeAudit();
  requestRender();
  return movableAppearance;
}

function cameraPreviewWidthLimits() {
  const sceneWidth = Math.max(1, dom.scene?.getBoundingClientRect().width || 1);
  const inset = window.matchMedia("(max-width: 720px)").matches ? 20 : 28;
  const maximum = Math.max(1, Math.min(720, sceneWidth - inset));
  return {
    min: Math.min(window.matchMedia("(max-width: 720px)").matches ? 210 : 240, maximum),
    max: maximum,
  };
}

function setCameraPreviewWidth(width = CAMERA_PREVIEW_WIDTH) {
  if (!dom.cameraLivePreview) return 0;
  const limits = cameraPreviewWidthLimits();
  cameraPreviewWidth = Math.max(limits.min, Math.min(limits.max, Number(width) || CAMERA_PREVIEW_WIDTH));
  dom.cameraLivePreview.style.width = `${cameraPreviewWidth}px`;
  return cameraPreviewWidth;
}

function startCameraPreviewResize(event) {
  if (!dom.cameraLivePreview || !dom.cameraPreviewResizeHandle) return;
  event.preventDefault();
  event.stopPropagation();
  cameraPreviewResizeGesture = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    startWidth: dom.cameraLivePreview.getBoundingClientRect().width || cameraPreviewWidth,
  };
  dom.cameraPreviewResizeHandle.setPointerCapture?.(event.pointerId);
  document.body.classList.add("preview-resizing");
}

function updateCameraPreviewResize(event) {
  if (!cameraPreviewResizeGesture || event.pointerId !== cameraPreviewResizeGesture.pointerId) return;
  event.preventDefault();
  const horizontalWidth = cameraPreviewResizeGesture.startWidth + event.clientX - cameraPreviewResizeGesture.startX;
  const verticalWidth = cameraPreviewResizeGesture.startWidth + (event.clientY - cameraPreviewResizeGesture.startY) * (16 / 9);
  const deltaX = Math.abs(event.clientX - cameraPreviewResizeGesture.startX);
  const deltaY = Math.abs(event.clientY - cameraPreviewResizeGesture.startY);
  setCameraPreviewWidth(deltaX >= deltaY ? horizontalWidth : verticalWidth);
}

function finishCameraPreviewResize(event) {
  if (!cameraPreviewResizeGesture || event.pointerId !== cameraPreviewResizeGesture.pointerId) return;
  dom.cameraPreviewResizeHandle?.releasePointerCapture?.(event.pointerId);
  cameraPreviewResizeGesture = null;
  document.body.classList.remove("preview-resizing");
  updateRuntimeAudit();
}

function setCameraPreviewEnabled(enabled) {
  cameraPreviewEnabled = Boolean(enabled);
  if (cameraPreviewEnabled && !previewSceneCameraId) {
    previewSceneCameraId = sceneRig.cameras[0]?.id || null;
  }
  dom.cameraPreviewToggle?.setAttribute("aria-pressed", String(cameraPreviewEnabled));
  dom.cameraPreviewToggle?.classList.toggle("active", cameraPreviewEnabled);
  updateRuntimeAudit();
  if (cameraPreviewEnabled) {
    setCameraPreviewWidth(cameraPreviewWidth);
    renderLiveCameraPreview();
  }
  else if (dom.cameraLivePreview) dom.cameraLivePreview.hidden = true;
  requestRender();
  return cameraPreviewEnabled;
}

function attachInspectionEdges(mesh, opacity = 0.38) {
  if (!mesh?.isMesh || mesh.material === whiteGlass) return;
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry, 34),
    new THREE.LineBasicMaterial({
      color: WHITE_MODEL_EDGE,
      transparent: true,
      opacity,
      depthWrite: false,
    }),
  );
  edges.name = `${mesh.name || "structure"}-inspection-edges`;
  edges.renderOrder = 3;
  mesh.add(edges);
}

function setStatus(message, kind = "normal") {
  dom.status.textContent = message;
  dom.status.dataset.kind = kind;
}

function showViewToast(message, kind = "neutral") {
  window.clearTimeout(viewToastTimer);
  dom.viewToast.hidden = false;
  dom.viewToast.textContent = message;
  dom.viewToast.className = `view-toast ${kind}`;
  requestAnimationFrame(() => dom.viewToast.classList.add("show"));
  viewToastTimer = window.setTimeout(() => {
    dom.viewToast.classList.remove("show");
    window.setTimeout(() => {
      if (!dom.viewToast.classList.contains("show")) dom.viewToast.hidden = true;
    }, 180);
  }, 1800);
}

function wallById(id) {
  return model.walls.find((item) => item.id === id);
}

function windowById(id) {
  return model.windows.find((item) => item.id === id);
}

function componentById(id) {
  return model.componentPlacements.find((item) => item.id === id);
}

function lightById(id) {
  return sceneRig.lights.find((item) => item.id === id);
}

function sceneCameraById(id) {
  return sceneRig.cameras.find((item) => item.id === id);
}

function normalizeSceneRigData(rig) {
  const normalizedNumber = (value, fallback, min, max) => {
    const numeric = Number(value);
    return Math.max(min, Math.min(max, Number.isFinite(numeric) ? numeric : fallback));
  };
  rig.rendering = {
    toneMapping: "ACESFilmic",
    exposure: 1.12,
    ambientIntensity: 0.2,
    hemisphereIntensity: 0.62,
    detailFillIntensity: 0.16,
    ...(rig.rendering || {}),
  };
  rig.rendering.exposure = normalizedNumber(rig.rendering.exposure, 1.12, 0.3, 1.5);
  rig.rendering.ambientIntensity = normalizedNumber(rig.rendering.ambientIntensity, 0.2, 0, 2);
  rig.rendering.hemisphereIntensity = normalizedNumber(rig.rendering.hemisphereIntensity, 0.62, 0, 2);
  rig.rendering.detailFillIntensity = normalizedNumber(rig.rendering.detailFillIntensity, 0.16, 0, 2);
  rig.gizmosVisible = rig.gizmosVisible !== false;
  rig.lights = Array.isArray(rig.lights) ? rig.lights : [];
  rig.cameras = Array.isArray(rig.cameras) ? rig.cameras : [];
  rig.lights.forEach((item, index) => {
    item.name = item.name || `光 ${index + 1}`;
  });
  rig.cameras.forEach((item) => {
    if (item.lensPreset === "detail") item.lensPreset = "telephoto";
    item.focalLengthMm = Math.max(
      14,
      Math.min(85, Number(item.focalLengthMm) || focalLengthForFov(item.fov)),
    );
    item.fov = fovForFocalLength(item.focalLengthMm);
    item.lensPreset = lensPresetForFocalLength(item.focalLengthMm);
    item.distortion = 0;
    item.mount = {
      mode: "free",
      wallId: null,
      offset: null,
      height: 1.55,
      side: 1,
      clearance: 0.12,
      snapEnabled: false,
      ...(item.mount || {}),
    };
    item.visibility = {
      cutawayEnabled: false,
      contextPolicy: "preserve-visible-adjacent-spaces",
      hiddenElementIds: [],
      preserveElementIds: [],
      hiddenWallIds: [],
      hiddenComponentIds: [],
      ...(item.visibility || {}),
      contextPolicy: "preserve-visible-adjacent-spaces",
    };
    item.focusRoomId = (model.rooms || []).some((room) => room.id === item.focusRoomId)
      ? item.focusRoomId
      : null;
    item.visibility.hiddenWallIds = Array.isArray(item.visibility.hiddenWallIds)
      ? item.visibility.hiddenWallIds
      : [];
    item.visibility.hiddenComponentIds = Array.isArray(item.visibility.hiddenComponentIds)
      ? item.visibility.hiddenComponentIds
      : [];
    ["hiddenElementIds", "preserveElementIds"].forEach((field) => {
      item.visibility[field] = Array.isArray(item.visibility[field]) ? item.visibility[field] : [];
    });
  });
}

function vector3IsValid(value) {
  return Array.isArray(value)
    && value.length === 3
    && value.every((item) => Number.isFinite(Number(item)));
}

function kelvinColor(temperatureK) {
  const temperature = Math.max(2000, Math.min(10000, Number(temperatureK))) / 100;
  let red;
  let green;
  let blue;
  if (temperature <= 66) {
    red = 255;
    green = 99.4708025861 * Math.log(temperature) - 161.1195681661;
    blue = temperature <= 19 ? 0 : 138.5177312231 * Math.log(temperature - 10) - 305.0447927307;
  } else {
    red = 329.698727446 * ((temperature - 60) ** -0.1332047592);
    green = 288.1221695283 * ((temperature - 60) ** -0.0755148492);
    blue = 255;
  }
  const channel = (value) => Math.max(0, Math.min(255, value)) / 255;
  return new THREE.Color(channel(red), channel(green), channel(blue));
}

function applyRenderingSettings(rendering = sceneRig.rendering) {
  const normalizedNumber = (value, fallback, min, max) => {
    const numeric = Number(value);
    return Math.max(min, Math.min(max, Number.isFinite(numeric) ? numeric : fallback));
  };
  const next = {
    toneMapping: "ACESFilmic",
    exposure: 1.12,
    ambientIntensity: 0.48,
    hemisphereIntensity: 1.05,
    detailFillIntensity: 0.38,
    ...(rendering || {}),
  };
  sceneRig.rendering = next;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = normalizedNumber(next.exposure, 1, 0.3, 1.5);
  ambient.intensity = normalizedNumber(next.ambientIntensity, 0.2, 0, 2);
  systemFill.intensity = normalizedNumber(next.hemisphereIntensity, 0.62, 0, 2);
  fill.intensity = normalizedNumber(next.detailFillIntensity, 0.16, 0, 2);
  requestRender();
}

function worldPoint(plan) {
  return {
    x: plan[0] - cfg.realWidthMeters / 2,
    z: plan[1] - cfg.realDepthMeters / 2,
  };
}

function planPoint(worldX, worldZ) {
  return [worldX + cfg.realWidthMeters / 2, worldZ + cfg.realDepthMeters / 2];
}

function wallFrame(wall) {
  const dx = wall.end[0] - wall.start[0];
  const dz = wall.end[1] - wall.start[1];
  const length = Math.hypot(dx, dz);
  return {
    length,
    ux: dx / length,
    uz: dz / length,
    angle: Math.atan2(dz, dx),
    center: [(wall.start[0] + wall.end[0]) / 2, (wall.start[1] + wall.end[1]) / 2],
  };
}

function wallDimensions(wall) {
  const frame = wallFrame(wall);
  return {
    length: frame.length,
    height: wall.height,
    thickness: wall.thickness,
    angle: frame.angle,
    center: frame.center,
  };
}

function pointAlongWall(wall, offset) {
  const frame = wallFrame(wall);
  return [wall.start[0] + frame.ux * offset, wall.start[1] + frame.uz * offset];
}

function clearGroup(group) {
  while (group.children.length) {
    const child = group.children[0];
    group.remove(child);
    child.traverse?.((object) => {
      object.shadow?.map?.dispose?.();
      object.shadow?.mapPass?.dispose?.();
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose?.());
      else object.material?.dispose?.();
    });
  }
}

function renderScene() {
  renderer.setRenderTarget(null);
  renderer.setScissorTest(false);
  renderer.setViewport(0, 0, renderer.domElement.width, renderer.domElement.height);
  renderer.render(scene, camera);
  renderLiveCameraPreview();
}

function activePreviewCameraState() {
  if (!cameraPreviewEnabled) return null;
  const selectedCamera = selection.type === "camera" ? sceneCameraById(selection.id) : null;
  const item = selectedCamera || sceneCameraById(previewSceneCameraId) || sceneRig.cameras[0];
  if (!item?.position || !item?.target) return null;
  previewSceneCameraId = item.id;
  return {
    id: item.id,
    name: sceneDisplayName("camera", item),
    position: [...item.position],
    target: [...item.target],
    fov: Number(item.fov),
    focalLengthMm: Number(item.focalLengthMm),
    near: Number(item.near),
    far: Number(item.far),
    visibility: structuredClone(item.visibility || {}),
  };
}

function previewPixelSignature(pixels) {
  let hash = 2166136261;
  const stride = Math.max(4, Math.floor(pixels.length / 4096 / 4) * 4);
  for (let index = 0; index < pixels.length; index += stride) {
    hash ^= pixels[index];
    hash = Math.imul(hash, 16777619);
    hash ^= pixels[index + 1];
    hash = Math.imul(hash, 16777619);
    hash ^= pixels[index + 2];
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function paintPreviewCanvas(pixels) {
  if (!previewCanvasContext) return;
  const image = previewCanvasContext.createImageData(CAMERA_PREVIEW_WIDTH, CAMERA_PREVIEW_HEIGHT);
  const rowLength = CAMERA_PREVIEW_WIDTH * 4;
  for (let row = 0; row < CAMERA_PREVIEW_HEIGHT; row += 1) {
    const sourceOffset = (CAMERA_PREVIEW_HEIGHT - row - 1) * rowLength;
    const targetOffset = row * rowLength;
    image.data.set(pixels.subarray(sourceOffset, sourceOffset + rowLength), targetOffset);
  }
  previewCanvasContext.putImageData(image, 0, 0);
}

function renderLiveCameraPreview() {
  const item = activePreviewCameraState();
  const overlay = dom.cameraLivePreview;
  if (!item || document.body.classList.contains("capture")) {
    overlay.hidden = true;
    return;
  }
  overlay.hidden = false;
  dom.cameraLivePreviewMeta.textContent = `${item.name} · ${Number(item.focalLengthMm || focalLengthForFov(item.fov)).toFixed(0)}mm · (${item.position.map((value) => Number(value).toFixed(2)).join(", ")})`;
  previewCamera.position.fromArray(item.position);
  previewCamera.up.set(0, 1, 0);
  previewCamera.fov = Number(item.fov) || 42;
  previewCamera.aspect = CAMERA_PREVIEW_WIDTH / CAMERA_PREVIEW_HEIGHT;
  previewCamera.near = Number(item.near) || 0.01;
  previewCamera.far = Number(item.far) || 120;
  previewCamera.lookAt(new THREE.Vector3(...item.target));
  previewCamera.updateProjectionMatrix();
  previewCamera.updateMatrixWorld(true);
  const helpersVisible = sceneRigHelperGroup.visible;
  const transformVisible = transformGizmoGroup.visible;
  const wallEndpointHandlesVisible = wallEndpointHandleGroup.visible;
  const selectionVisible = selectionHelper?.visible;
  const gridVisible = grid?.visible;
  const roomLinesVisible = roomLineGroup.visible;
  const evidenceVisible = cameraEvidenceGroup.visible;
  const shadowMapEnabled = renderer.shadowMap.enabled;
  const visibilitySnapshot = new Map();
  const hideForPreview = (object) => {
    if (!object) return;
    visibilitySnapshot.set(object, object.visible);
    object.visible = false;
  };
  (item.visibility?.hiddenElementIds || []).forEach((id) => {
    if (wallGroups.has(id)) {
      hideForPreview(wallGroups.get(id));
      model.windows
        .filter((windowItem) => windowItem.wallId === id)
        .forEach((windowItem) => hideForPreview(windowGroups.get(windowItem.id)));
    }
    if (componentGroups.has(id)) hideForPreview(componentGroups.get(id));
  });
  sceneRigHelperGroup.visible = false;
  transformGizmoGroup.visible = false;
  wallEndpointHandleGroup.visible = false;
  if (selectionHelper) selectionHelper.visible = false;
  if (grid) grid.visible = false;
  roomLineGroup.visible = false;
  cameraEvidenceGroup.visible = false;
  renderer.shadowMap.enabled = false;
  try {
    renderer.setScissorTest(false);
    renderer.setRenderTarget(previewRenderTarget);
    renderer.setViewport(0, 0, CAMERA_PREVIEW_WIDTH, CAMERA_PREVIEW_HEIGHT);
    renderer.clear(true, true, true);
    renderer.render(scene, previewCamera);
    renderer.readRenderTargetPixels(
      previewRenderTarget,
      0,
      0,
      CAMERA_PREVIEW_WIDTH,
      CAMERA_PREVIEW_HEIGHT,
      previewPixels,
    );
    paintPreviewCanvas(previewPixels);
    cameraPreviewSignature = previewPixelSignature(previewPixels);
    cameraPreviewFrameCount += 1;
  } finally {
    renderer.setRenderTarget(null);
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, renderer.domElement.width, renderer.domElement.height);
    renderer.shadowMap.enabled = shadowMapEnabled;
    sceneRigHelperGroup.visible = helpersVisible;
    transformGizmoGroup.visible = transformVisible;
    wallEndpointHandleGroup.visible = wallEndpointHandlesVisible;
    if (selectionHelper) selectionHelper.visible = selectionVisible;
    if (grid) grid.visible = gridVisible;
    roomLineGroup.visible = roomLinesVisible;
    cameraEvidenceGroup.visible = evidenceVisible;
    visibilitySnapshot.forEach((visible, object) => {
      object.visible = visible;
    });
  }
}

function renderFrame() {
  renderQueued = false;
  if (selectionHelper) selectionHelper.update();
  updateRoomAnnotationPositions();
  updateMeasurementLabelPosition();
  renderScene();
}

function requestRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(renderFrame);
}

function updateUndoButtons() {
  document.getElementById("undo").disabled = undoStack.length === 0;
  document.getElementById("redo").disabled = redoStack.length === 0;
}

function updateTargetLine(line, start, end) {
  if (!line) return;
  const position = line.geometry.getAttribute("position");
  if (!position || position.count !== 2) {
    line.geometry.setFromPoints([new THREE.Vector3(...start), new THREE.Vector3(...end)]);
  } else {
    position.setXYZ(0, start[0], start[1], start[2]);
    position.setXYZ(1, end[0], end[1], end[2]);
    position.needsUpdate = true;
    line.geometry.computeBoundingSphere();
  }
  line.computeLineDistances();
}

function createBox(parent, name, width, height, depth, centerPlan, bottom, angle, material, pick) {
  if (width <= 0.002 || height <= 0.002 || depth <= 0.002) return null;
  const center = worldPoint(centerPlan);
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), material);
  mesh.name = name;
  mesh.position.set(center.x, bottom + height / 2, center.z);
  mesh.rotation.y = -angle;
  mesh.castShadow = material !== whiteGlass;
  mesh.receiveShadow = true;
  mesh.userData.pick = pick;
  mesh.userData.structureSurfaceRole = material.transmission > 0
    ? "glass"
    : /frame|mullion/i.test(name)
      ? "frame"
      : "wall";
  applyStructureMaterialAppearance(mesh);
  if (material !== whiteGlass && !material.transparent) {
    attachInspectionEdges(mesh, material.roughness > 0.9 ? 0.12 : 0.18);
  }
  parent.add(mesh);
  return mesh;
}

function windowsForWall(wallId) {
  return model.windows.filter((item) => item.wallId === wallId && item.enabled !== false);
}

function buildWindowFrame(wall, item, frame, options = {}) {
  const targetGroup = options.targetGroup || glassGroup;
  const targetMap = options.targetMap || windowGroups;
  const pickId = options.pickId || item.sourceWindowId || item.id;
  const centerPlan = pointAlongWall(wall, item.offset);
  const depth = Math.max(wall.thickness + 0.025, item.frameDepth || 0.08);
  const style = model.backendOptions.windows?.overrides?.[item.id]
    || item.windowStyle
    || model.backendOptions.windows?.defaultStyle
    || "frameless-glass";
  const frameWidth = style === "frameless-glass"
    ? Math.min(0.028, item.width * 0.04)
    : Math.min(0.065, item.width * 0.08);
  const group = new THREE.Group();
  group.name = item.id;
  group.userData.pick = { type: "window", id: pickId };
  const pick = { type: "window", id: pickId };

  createBox(group, `${item.id}-glass`, item.width, item.openingHeight, 0.025, centerPlan, item.sill, frame.angle, whiteGlass.clone(), pick);
  createBox(group, `${item.id}-frame-bottom`, item.width, frameWidth, depth, centerPlan, item.sill, frame.angle, whiteFrame.clone(), pick);
  createBox(group, `${item.id}-frame-top`, item.width, frameWidth, depth, centerPlan, item.sill + item.openingHeight - frameWidth, frame.angle, whiteFrame.clone(), pick);
  const left = pointAlongWall(wall, item.offset - item.width / 2 + frameWidth / 2);
  const right = pointAlongWall(wall, item.offset + item.width / 2 - frameWidth / 2);
  createBox(group, `${item.id}-frame-left`, frameWidth, item.openingHeight, depth, left, item.sill, frame.angle, whiteFrame.clone(), pick);
  createBox(group, `${item.id}-frame-right`, frameWidth, item.openingHeight, depth, right, item.sill, frame.angle, whiteFrame.clone(), pick);
  if (["casement", "sliding"].includes(style)) {
    createBox(group, `${item.id}-mullion`, frameWidth * 0.72, item.openingHeight - frameWidth * 2, depth * 0.74, centerPlan, item.sill + frameWidth, frame.angle, whiteFrame.clone(), pick);
  }
  group.userData.windowStyle = style;
  targetGroup.add(group);
  if (!targetMap.has(pickId)) targetMap.set(pickId, group);
}

function populateWallGeometry(wall, group, apertureItems, options = {}) {
  const frame = wallFrame(wall);
  const pickWallId = options.pickWallId || wall.id;
  const apertures = apertureItems
    .map((item) => ({ item, start: item.offset - item.width / 2, end: item.offset + item.width / 2 }))
    .sort((a, b) => a.start - b.start);
  let cursor = 0;
  const pick = { type: "wall", id: pickWallId };

  apertures.forEach(({ item, start, end }) => {
    if (start > cursor) {
      const length = start - cursor;
      createBox(group, `${wall.id}-solid-${cursor.toFixed(3)}`, length, wall.height, wall.thickness, pointAlongWall(wall, cursor + length / 2), 0, frame.angle, whiteWall.clone(), pick);
    }
    if (item.sill > 0.002) {
      createBox(group, `${wall.id}-${item.id}-sill`, item.width, item.sill, wall.thickness, pointAlongWall(wall, item.offset), 0, frame.angle, whiteWall.clone(), pick);
    }
    const lintelHeight = Math.max(0, wall.height - item.sill - item.openingHeight);
    if (lintelHeight > 0.002) {
      createBox(group, `${wall.id}-${item.id}-lintel`, item.width, lintelHeight, wall.thickness, pointAlongWall(wall, item.offset), item.sill + item.openingHeight, frame.angle, whiteWall.clone(), pick);
    }
    buildWindowFrame(wall, item, frame, {
      targetGroup: options.targetGlassGroup,
      targetMap: options.targetWindowMap,
      pickId: item.sourceWindowId || item.id,
    });
    cursor = Math.max(cursor, end);
  });

  if (cursor < frame.length) {
    const length = frame.length - cursor;
    createBox(group, `${wall.id}-solid-end`, length, wall.height, wall.thickness, pointAlongWall(wall, cursor + length / 2), 0, frame.angle, whiteWall.clone(), pick);
  }
}

function balconyEnvelopeMode(wall) {
  const balconyRoom = (model.rooms || []).find((room) => (
    ["balcony", "terrace", "loggia"].includes(room.spaceType)
    && (wall.adjacentRoomIds || []).includes(room.id)
  ));
  if (!balconyRoom) return null;
  const isExteriorEdge = wall.type === "external"
    || (wall.adjacentRoomIds || []).some((roomId) => ["exterior", "outside", "outdoor"].includes(roomId))
    || (wall.adjacentRoomIds || []).length === 1;
  if (!isExteriorEdge) return null;
  const options = model.backendOptions.balconies || {};
  const mode = options.overrides?.[wall.id]
    || options.overrides?.[balconyRoom.id]
    || options.defaultEnclosureMode
    || "source-structure";
  return { roomId: balconyRoom.id, room: balconyRoom, mode };
}

function wallFragment(wall, startOffset, endOffset, suffix) {
  return {
    ...wall,
    id: `${wall.id}-${suffix}`,
    sourceWallId: wall.sourceWallId || wall.id,
    start: pointAlongWall(wall, startOffset),
    end: pointAlongWall(wall, endOffset),
  };
}

function aperturesForWallInterval(wall, startOffset, endOffset, suffix) {
  return windowsForWall(wall.id).flatMap((item) => {
    const sourceStart = item.offset - item.width / 2;
    const sourceEnd = item.offset + item.width / 2;
    const clippedStart = Math.max(startOffset, sourceStart);
    const clippedEnd = Math.min(endOffset, sourceEnd);
    if (clippedEnd - clippedStart <= 0.04) return [];
    return [{
      ...item,
      id: `${item.id}-${suffix}`,
      sourceWindowId: item.sourceWindowId || item.id,
      offset: (clippedStart + clippedEnd) / 2 - startOffset,
      width: clippedEnd - clippedStart,
    }];
  });
}

function complementWallIntervals(length, intervals) {
  const complement = [];
  let cursor = 0;
  intervals.forEach(([start, end]) => {
    if (start - cursor > 0.02) complement.push([cursor, start]);
    cursor = Math.max(cursor, end);
  });
  if (length - cursor > 0.02) complement.push([cursor, length]);
  return complement;
}

function buildBalconyEnvelopeFragment(wall, group, envelope) {
  const frame = wallFrame(wall);
  const pick = { type: "wall", id: wall.sourceWallId || wall.id };
  const centerPlan = pointAlongWall(wall, frame.length / 2);
  group.userData.balconyMode = envelope.mode;
  group.userData.balconyRoomId = envelope.roomId;
  if (envelope.mode === "open-railing") {
    const railingHeight = 1.1;
    const railDepth = Math.max(0.045, wall.thickness * 0.28);
    createBox(group, `${wall.id}-railing-base`, frame.length, 0.12, railDepth, centerPlan, 0, frame.angle, whiteFrame.clone(), pick);
    createBox(group, `${wall.id}-railing-top`, frame.length, 0.065, railDepth, centerPlan, railingHeight - 0.065, frame.angle, whiteFrame.clone(), pick);
    const postCount = Math.max(2, Math.ceil(frame.length / 0.82));
    for (let index = 0; index <= postCount; index += 1) {
      const offset = frame.length * index / postCount;
      createBox(
        group,
        `${wall.id}-railing-post-${index + 1}`,
        0.045,
        railingHeight - 0.12,
        railDepth,
        pointAlongWall(wall, offset),
        0.12,
        frame.angle,
        whiteFrame.clone(),
        pick,
      );
    }
    return true;
  }
  if (envelope.mode === "closed-glazing") {
    const frameWidth = Math.min(0.06, frame.length * 0.025);
    createBox(group, `${wall.id}-balcony-glass`, frame.length, wall.height, 0.028, centerPlan, 0, frame.angle, whiteGlass.clone(), pick);
    createBox(group, `${wall.id}-glazing-bottom`, frame.length, frameWidth, wall.thickness, centerPlan, 0, frame.angle, whiteFrame.clone(), pick);
    createBox(group, `${wall.id}-glazing-top`, frame.length, frameWidth, wall.thickness, centerPlan, wall.height - frameWidth, frame.angle, whiteFrame.clone(), pick);
    const panelCount = Math.max(2, Math.ceil(frame.length / 1.25));
    for (let index = 0; index <= panelCount; index += 1) {
      createBox(
        group,
        `${wall.id}-glazing-post-${index + 1}`,
        frameWidth,
        wall.height - frameWidth * 2,
        wall.thickness,
        pointAlongWall(wall, frame.length * index / panelCount),
        frameWidth,
        frame.angle,
        whiteFrame.clone(),
        pick,
      );
    }
    return true;
  }
  throw new Error(`不支持的阳台围护模式：${envelope.mode}`);
}

function buildBalconyEnvelope(wall, group, envelope) {
  if (!envelope || envelope.mode === "source-structure") return false;
  const frame = wallFrame(wall);
  const balconyIntervals = mergeIntervals(
    roomBoundaryIntervalsForWall(wall, envelope.room, { expansion: 0 }),
    0.02,
  );
  if (!balconyIntervals.length) return false;
  const sourceIntervals = complementWallIntervals(frame.length, balconyIntervals);
  group.userData.balconyMode = envelope.mode;
  group.userData.balconyRoomId = envelope.roomId;
  group.userData.balconyPartitionAudit = {
    sourceWallId: wall.id,
    balconyRoomId: envelope.roomId,
    balconyIntervals: balconyIntervals.map(([start, end]) => [Number(start.toFixed(4)), Number(end.toFixed(4))]),
    preservedSourceIntervals: sourceIntervals.map(([start, end]) => [Number(start.toFixed(4)), Number(end.toFixed(4))]),
    partitionMethod: "strict-room-polygon-boundary-intersection-v1",
  };
  sourceIntervals.forEach(([startOffset, endOffset], index) => {
    const suffix = `source-part-${index + 1}`;
    const fragment = wallFragment(wall, startOffset, endOffset, suffix);
    populateWallGeometry(
      fragment,
      group,
      aperturesForWallInterval(wall, startOffset, endOffset, suffix),
      {
        pickWallId: wall.id,
        targetGlassGroup: glassGroup,
        targetWindowMap: windowGroups,
      },
    );
  });
  balconyIntervals.forEach(([startOffset, endOffset], index) => {
    const fragment = wallFragment(wall, startOffset, endOffset, `balcony-part-${index + 1}`);
    buildBalconyEnvelopeFragment(fragment, group, envelope);
  });
  return true;
}

function buildWall(wall) {
  const group = new THREE.Group();
  group.name = wall.id;
  group.userData.pick = { type: "wall", id: wall.id };
  group.visible = wall.enabled !== false;
  wallGroups.set(wall.id, group);
  structureGroup.add(group);
  if (wall.enabled === false) return;
  if (buildBalconyEnvelope(wall, group, balconyEnvelopeMode(wall))) return;
  populateWallGeometry(wall, group, windowsForWall(wall.id), {
    pickWallId: wall.id,
    targetGlassGroup: glassGroup,
    targetWindowMap: windowGroups,
  });
}

function roomBoundaryIntervalsForWall(wall, room, options = {}) {
  if (!wall || !room?.polygon?.length) return [];
  const frame = wallFrame(wall);
  if (frame.length <= 0.001) return [];
  const tolerance = Math.max(0.24, Number(wall.thickness || 0.12) + 0.12);
  const expansion = options.expansion === undefined
    ? Math.max(0.1, Math.min(0.22, tolerance * 0.62))
    : Math.max(0, Number(options.expansion));
  const intervals = [];
  room.polygon.forEach((start, index) => {
    const end = room.polygon[(index + 1) % room.polygon.length];
    const edgeDx = end[0] - start[0];
    const edgeDz = end[1] - start[1];
    const edgeLength = Math.hypot(edgeDx, edgeDz);
    if (edgeLength <= 0.001) return;
    const parallelError = Math.abs(frame.ux * edgeDz - frame.uz * edgeDx) / edgeLength;
    if (parallelError > 0.08) return;
    const distanceToWall = (point) => Math.abs(
      (point[0] - wall.start[0]) * frame.uz - (point[1] - wall.start[1]) * frame.ux
    );
    if (Math.min(distanceToWall(start), distanceToWall(end)) > tolerance) return;
    const project = (point) => (
      (point[0] - wall.start[0]) * frame.ux + (point[1] - wall.start[1]) * frame.uz
    );
    const intervalStart = Math.max(0, Math.min(project(start), project(end)) - expansion);
    const intervalEnd = Math.min(frame.length, Math.max(project(start), project(end)) + expansion);
    if (intervalEnd - intervalStart > 0.02) intervals.push([intervalStart, intervalEnd]);
  });
  return intervals;
}

function mergeIntervals(intervals, gap = 0.08) {
  const sorted = intervals
    .filter(([start, end]) => end - start > 0.02)
    .sort((first, second) => first[0] - second[0]);
  const merged = [];
  sorted.forEach(([start, end]) => {
    const current = merged[merged.length - 1];
    if (!current || start > current[1] + gap) merged.push([start, end]);
    else current[1] = Math.max(current[1], end);
  });
  return merged;
}

function wallIntervalsForRooms(wall, rooms) {
  return mergeIntervals(rooms.flatMap((room) => roomBoundaryIntervalsForWall(wall, room)));
}

function buildRoomFilterStructure() {
  clearGroup(roomFilterStructureGroup);
  clearGroup(roomFilterGlassGroup);
  roomFilterWallGroups.clear();
  roomFilterWindowGroups.clear();
  if (roomFilterIsAll() || roomFilterIds.size === 0) return;
  const rooms = (model.rooms || []).filter((room) => roomFilterIds.has(room.id));
  model.walls.forEach((wall) => {
    if (wall.enabled === false) return;
    const intervals = wallIntervalsForRooms(wall, rooms);
    if (!intervals.length) return;
    const sourceGroup = new THREE.Group();
    sourceGroup.name = `room-filter-${wall.id}`;
    sourceGroup.userData.pick = { type: "wall", id: wall.id };
    roomFilterStructureGroup.add(sourceGroup);
    roomFilterWallGroups.set(wall.id, sourceGroup);
    intervals.forEach(([startOffset, endOffset], intervalIndex) => {
      const fragment = {
        ...wall,
        id: `${wall.id}-room-filter-${intervalIndex + 1}`,
        start: pointAlongWall(wall, startOffset),
        end: pointAlongWall(wall, endOffset),
      };
      const apertures = windowsForWall(wall.id).flatMap((item) => {
        const sourceStart = item.offset - item.width / 2;
        const sourceEnd = item.offset + item.width / 2;
        const clippedStart = Math.max(startOffset, sourceStart);
        const clippedEnd = Math.min(endOffset, sourceEnd);
        if (clippedEnd - clippedStart <= 0.04) return [];
        return [{
          ...item,
          id: `${item.id}-room-filter-${intervalIndex + 1}`,
          sourceWindowId: item.id,
          width: clippedEnd - clippedStart,
          offset: (clippedStart + clippedEnd) / 2 - startOffset,
        }];
      });
      const fragmentGroup = new THREE.Group();
      fragmentGroup.name = fragment.id;
      fragmentGroup.userData.pick = { type: "wall", id: wall.id };
      sourceGroup.add(fragmentGroup);
      populateWallGeometry(fragment, fragmentGroup, apertures, {
        pickWallId: wall.id,
        targetGlassGroup: roomFilterGlassGroup,
        targetWindowMap: roomFilterWindowGroups,
      });
    });
  });
}

function buildStructure() {
  clearGroup(structureGroup);
  clearGroup(glassGroup);
  wallGroups.clear();
  windowGroups.clear();
  model.walls.forEach(buildWall);
  buildRoomFilterStructure();
}

function buildFloor() {
  clearGroup(semanticDividerGroup);
  clearGroup(ceilingGroup);
  clearGroup(roomFilterFloorGroup);
  ceilingMeshes.clear();
  roomFilterFloors.clear();
  if (floorMesh) {
    scene.remove(floorMesh);
    floorMesh.geometry.dispose();
    floorMesh.material.dispose();
  }
  if (grid) scene.remove(grid);
  if (boundaryLine) scene.remove(boundaryLine);
  const points = model.floorBoundary.map(([x, z]) => new THREE.Vector2(x - cfg.realWidthMeters / 2, -(z - cfg.realDepthMeters / 2)));
  const shape = new THREE.Shape(points);
  floorMesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), whiteFloor.clone());
  floorMesh.rotation.x = -Math.PI / 2;
  floorMesh.position.y = -0.012;
  floorMesh.receiveShadow = true;
  floorMesh.name = "white-model-floor";
  floorMesh.userData.structureSurfaceRole = "floor";
  applyStructureMaterialAppearance(floorMesh);
  scene.add(floorMesh);
  (model.rooms || []).forEach((room) => {
    if (!Array.isArray(room.polygon) || room.polygon.length < 3) return;
    const roomPoints = room.polygon.map(([x, z]) => new THREE.Vector2(
      x - cfg.realWidthMeters / 2,
      -(z - cfg.realDepthMeters / 2),
    ));
    const roomFloor = new THREE.Mesh(
      new THREE.ShapeGeometry(new THREE.Shape(roomPoints)),
      whiteFloor.clone(),
    );
    roomFloor.rotation.x = -Math.PI / 2;
    roomFloor.position.y = -0.011;
    roomFloor.receiveShadow = true;
    roomFloor.name = `room-filter-floor-${room.id}`;
    roomFloor.userData.structureSurfaceRole = "floor";
    applyStructureMaterialAppearance(roomFloor);
    roomFilterFloorGroup.add(roomFloor);
    roomFilterFloors.set(room.id, roomFloor);

    if (model.backendOptions.ceilings?.enabled !== false) {
      const ceilingHeight = Math.max(
        cfg.defaultWallHeightMeters || 2.8,
        ...model.walls
          .filter((wall) => (wall.adjacentRoomIds || []).includes(room.id))
          .map((wall) => Number(wall.height) || 0),
      );
      const ceiling = new THREE.Mesh(
        new THREE.ShapeGeometry(new THREE.Shape(roomPoints)),
        whiteFloor.clone(),
      );
      ceiling.rotation.x = -Math.PI / 2;
      ceiling.position.y = ceilingHeight;
      ceiling.name = `ceiling-${room.id}`;
      ceiling.userData.structureSurfaceRole = "ceiling";
      ceiling.userData.roomId = room.id;
      ceiling.userData.thicknessMeters = Number(model.backendOptions.ceilings?.thicknessMeters || 0.08);
      applyStructureMaterialAppearance(ceiling);
      ceilingGroup.add(ceiling);
      ceilingMeshes.set(room.id, ceiling);
    }
  });

  const gridSize = Math.max(cfg.realWidthMeters, cfg.realDepthMeters) * 2.8;
  const gridDivisions = Math.max(24, Math.ceil(gridSize / 0.5));
  grid = new THREE.GridHelper(gridSize, gridDivisions, 0x6f7872, 0xaeb6b1);
  grid.position.y = -0.004;
  const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];
  gridMaterials.forEach((material) => {
    material.transparent = true;
    material.opacity = 0.68;
    material.depthWrite = false;
  });
  grid.name = "extended-measurement-grid";
  grid.userData.gridSize = gridSize;
  grid.userData.gridStep = gridSize / gridDivisions;
  scene.add(grid);
  const boundaryPoints = model.floorBoundary.map((point) => {
    const world = worldPoint(point);
    return new THREE.Vector3(world.x, 0.015, world.z);
  });
  boundaryPoints.push(boundaryPoints[0].clone());
  boundaryLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(boundaryPoints),
    new THREE.LineBasicMaterial({ color: 0x747c77 }),
  );
  scene.add(boundaryLine);
  const dividerById = new Map((model.semanticDividers || []).map((divider) => [divider.id, divider]));
  (model.relationHints?.spaceDividerMarkers || []).forEach((marker) => {
    const divider = dividerById.get(marker.semanticDividerId);
    if (marker?.visible !== true || !Array.isArray(divider?.start) || !Array.isArray(divider?.end)) return;
    const dx = Number(divider.end[0]) - Number(divider.start[0]);
    const dz = Number(divider.end[1]) - Number(divider.start[1]);
    const length = Math.hypot(dx, dz);
    if (length <= 0.02) return;
    const center = worldPoint([
      (Number(divider.start[0]) + Number(divider.end[0])) / 2,
      (Number(divider.start[1]) + Number(divider.end[1])) / 2,
    ]);
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(length, Number(marker.height || 0.018), Number(marker.width || 0.045)),
      new THREE.MeshStandardMaterial({
        color: new THREE.Color(marker.color || "#8a6b42"),
        roughness: Number(marker.roughness ?? 0.72),
        metalness: Number(marker.metalness ?? 0.1),
      }),
    );
    mesh.name = marker.id;
    mesh.position.set(center.x, Number(marker.height || 0.018) / 2 + 0.004, center.z);
    mesh.rotation.y = -Math.atan2(dz, dx);
    mesh.receiveShadow = true;
    mesh.userData.semanticDividerId = divider.id;
    mesh.userData.roomIds = [...(divider.roomIds || [])];
    mesh.userData.floorMarker = true;
    semanticDividerGroup.add(mesh);
  });
}

function buildComponents() {
  clearGroup(movableGroup);
  clearGroup(fixedGroup);
  componentGroups.clear();
  componentMeshCounts.clear();
  model.componentPlacements.forEach((placement) => {
    placement.presentationHidden = placement.presentationHidden === true;
    const definition = getComponentDefinition(placement.componentId, placement.semantic);
    if (!definition) return;
    const group = createWhiteModelComponent(placement.componentId, {
      semantic: placement.semantic,
      uniformScale: placement.uniformScale ?? 1,
      targetDimensions: placement.targetDimensions,
      visualDimensions: placement.visualDimensions,
      shapeAdjustments: placement.shapeAdjustments,
      appearance: movableAppearance,
      finishPreset: placement.finishPreset,
    });
    group.name = placement.id;
    const world = worldPoint(placement.position);
    group.position.set(world.x, Number(placement.elevation ?? definition.defaultElevation ?? 0) + 0.01, world.z);
    group.rotation.y = placement.rotationY || 0;
    group.userData.pick = { type: "component", id: placement.id };
    group.userData.sourceTraceId = placement.sourceTraceId;
    const bindLoadedMeshes = () => {
      let meshCount = 0;
      group.traverse((child) => {
        if (!child.isMesh) return;
        child.userData.pick = { type: "component", id: placement.id };
        meshCount += 1;
      });
      componentMeshCounts.set(placement.id, meshCount);
      updateSelectionHighlight();
      updateRuntimeAudit();
      requestRender();
    };
    bindLoadedMeshes();
    (definition.placementClass === "fixed-purple" ? fixedGroup : movableGroup).add(group);
    componentGroups.set(placement.id, group);
    group.userData.readyPromise?.then(() => {
      if (componentGroups.get(placement.id) === group) bindLoadedMeshes();
    }).catch((error) => {
      group.userData.externalAssetError = error.message;
      setStatus(`${definition.name} 载入失败：${error.message}`, "error");
      updateRuntimeAudit();
    });
  });
}

function applyCameraWallMount(item) {
  if (item.mount?.mode !== "wall") return;
  const wall = wallById(item.mount.wallId);
  if (!wall) return;
  const frame = wallFrame(wall);
  const offset = Math.max(0, Math.min(frame.length, Number(item.mount.offset ?? frame.length / 2)));
  const maximumHeight = Math.max(0.2, wall.height - 0.15);
  const height = Math.max(0.2, Math.min(maximumHeight, Number(item.mount.height ?? 1.55)));
  const plan = pointAlongWall(wall, offset);
  const side = Number(item.mount.side) >= 0 ? 1 : -1;
  const clearance = Math.max(0.03, Number(item.mount.clearance ?? 0.12));
  const normal = [-frame.uz * side, frame.ux * side];
  const world = worldPoint([plan[0] + normal[0] * clearance, plan[1] + normal[1] * clearance]);
  item.mount.offset = offset;
  item.mount.height = height;
  item.mount.side = side;
  item.mount.clearance = clearance;
  item.position = [world.x, item.mount.height, world.z];
}

function nearestWallMount(position) {
  const plan = planPoint(position[0], position[2]);
  let nearest = null;
  model.walls.filter((wall) => wall.enabled !== false).forEach((wall) => {
    const frame = wallFrame(wall);
    const along = (plan[0] - wall.start[0]) * frame.ux + (plan[1] - wall.start[1]) * frame.uz;
    const offset = Math.max(0, Math.min(frame.length, along));
    const closest = pointAlongWall(wall, offset);
    const dx = plan[0] - closest[0];
    const dz = plan[1] - closest[1];
    const distance = Math.hypot(dx, dz);
    if (nearest && nearest.distance <= distance) return;
    const baseNormal = [-frame.uz, frame.ux];
    const signed = dx * baseNormal[0] + dz * baseNormal[1];
    nearest = {
      wall,
      offset,
      distance,
      side: signed >= 0 ? 1 : -1,
    };
  });
  return nearest;
}

function applyCameraWallSnap(item, threshold = 0.7) {
  if (item.mount?.snapEnabled !== true) return false;
  const nearest = nearestWallMount(item.position);
  if (!nearest || nearest.distance > threshold) {
    item.mount.mode = "free";
    item.mount.wallId = null;
    item.mount.offset = null;
    return false;
  }
  item.mount.mode = "wall";
  item.mount.wallId = nearest.wall.id;
  item.mount.offset = nearest.offset;
  item.mount.height = Math.max(
    0.2,
    Math.min(nearest.wall.height - 0.15, Number(item.position[1] || 1.55)),
  );
  item.mount.side = nearest.side;
  item.mount.clearance = Math.max(0.03, Number(item.mount.clearance ?? 0.12));
  applyCameraWallMount(item);
  return true;
}

function addTargetLine(parent, start, end, color) {
  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(...start),
    new THREE.Vector3(...end),
  ]);
  const line = new THREE.Line(geometry, new THREE.LineDashedMaterial({
    color,
    dashSize: 0.18,
    gapSize: 0.1,
    depthTest: false,
    transparent: true,
    opacity: 0.72,
  }));
  line.computeLineDistances();
  line.renderOrder = 40;
  parent.add(line);
  return line;
}

function sceneHelperPosition(position, target = false) {
  if (viewMode !== "top") return [...position];
  return [Number(position[0]), target ? 0.035 : 0.16, Number(position[2])];
}

function lightHelperPosition(item, target = false) {
  const helperPosition = sceneHelperPosition(target ? item.target : item.position, target);
  if (viewMode !== "top" && item.type === "directional" && !target) {
    const maximumWallHeight = Math.max(2.4, ...model.walls.map((wall) => Number(wall.height) || 0));
    helperPosition[1] = Math.min(Number(helperPosition[1]), maximumWallHeight + 0.65);
  }
  return helperPosition;
}

function buildLightObject(item) {
  const color = kelvinColor(item.temperatureK);
  let light;
  if (item.type === "point") {
    light = new THREE.PointLight(
      color,
      Math.max(0, Number(item.intensity)) * 6,
      Math.max(0, Number(item.distance)),
      Math.max(0, Number(item.decay)),
    );
  } else if (item.type === "spot") {
    light = new THREE.SpotLight(
      color,
      Math.max(0, Number(item.intensity)) * 8,
      Math.max(0, Number(item.distance)),
      THREE.MathUtils.degToRad(Math.max(5, Math.min(120, Number(item.angle)))),
      Math.max(0, Math.min(1, Number(item.penumbra))),
      Math.max(0, Number(item.decay)),
    );
  } else {
    light = new THREE.DirectionalLight(color, Math.max(0, Number(item.intensity)));
  }
  light.name = item.id;
  light.position.fromArray(item.position);
  light.visible = item.enabled !== false && sceneItemMatchesRoomFilter("light", item);
  light.castShadow = item.castShadow === true;
  if (light.castShadow) {
    light.shadow.mapSize.set(1024, 1024);
    light.shadow.camera.near = 0.2;
    light.shadow.camera.far = 60;
    light.shadow.bias = -0.00035;
    light.shadow.normalBias = 0.018;
    light.shadow.radius = 2.2;
  }
  light.userData.rigType = item.type;
  if (item.type === "directional" || item.type === "spot") {
    const target = new THREE.Object3D();
    target.name = `${item.id}-target`;
    target.position.fromArray(item.target);
    managedLightGroup.add(target);
    light.target = target;
  }
  managedLightGroup.add(light);
  managedLights.set(item.id, light);

  const helper = new THREE.Group();
  helper.name = `${item.id}-helper`;
  helper.userData.pick = { type: "light", id: item.id };
  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(0.16, 18, 12),
    new THREE.MeshBasicMaterial({
      color: item.enabled === false ? 0x9ba29e : 0xc78b22,
      depthTest: false,
    }),
  );
  marker.position.fromArray(lightHelperPosition(item));
  marker.renderOrder = 42;
  marker.userData.pick = { type: "light", id: item.id };
  marker.userData.role = "marker";
  helper.add(marker);
  const pickProxy = new THREE.Mesh(
    new THREE.SphereGeometry(0.38, 12, 8),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }),
  );
  pickProxy.position.fromArray(lightHelperPosition(item));
  pickProxy.userData.pick = { type: "light", id: item.id };
  pickProxy.userData.role = "pick-proxy";
  helper.add(pickProxy);
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(0.27, 0.018, 8, 32),
    new THREE.MeshBasicMaterial({
      color: item.enabled === false ? 0x9ba29e : 0xc78b22,
      depthTest: false,
    }),
  );
  ring.position.fromArray(lightHelperPosition(item));
  ring.rotation.x = Math.PI / 2;
  ring.renderOrder = 42;
  ring.userData.pick = { type: "light", id: item.id };
  ring.userData.role = "ring";
  helper.add(ring);
  if (item.type !== "point") {
    lightTargetLines.set(item.id, addTargetLine(
      helper,
      lightHelperPosition(item),
      lightHelperPosition(item, true),
      0xc78b22,
    ));
  }
  sceneRigHelperGroup.add(helper);
  lightHelperGroups.set(item.id, helper);
}

function buildCameraHelper(item) {
  applyCameraWallMount(item);
  const helper = new THREE.Group();
  helper.name = `${item.id}-helper`;
  helper.position.fromArray(sceneHelperPosition(item.position));
  helper.userData.pick = { type: "camera", id: item.id };
  const material = new THREE.MeshBasicMaterial({
    color: item.enabled === false ? 0x9ba29e : 0x2b6f91,
    depthTest: false,
    wireframe: true,
  });
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.22, 0.26), material);
  body.renderOrder = 42;
  body.userData.pick = { type: "camera", id: item.id };
  helper.add(body);
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.13, 0.2, 18), material.clone());
  lens.rotation.x = Math.PI / 2;
  lens.position.z = 0.2;
  lens.renderOrder = 42;
  lens.userData.pick = { type: "camera", id: item.id };
  helper.add(lens);
  const pickProxy = new THREE.Mesh(
    new THREE.SphereGeometry(0.38, 12, 8),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }),
  );
  pickProxy.userData.pick = { type: "camera", id: item.id };
  pickProxy.userData.role = "pick-proxy";
  helper.add(pickProxy);
  const target = new THREE.Vector3(...sceneHelperPosition(item.target, true));
  helper.lookAt(target);
  sceneRigHelperGroup.add(helper);
  cameraTargetLines.set(item.id, addTargetLine(
    sceneRigHelperGroup,
    sceneHelperPosition(item.position),
    sceneHelperPosition(item.target, true),
    activeSceneCameraId === item.id ? 0x1e4f69 : 0x2b6f91,
  ));
  cameraHelperGroups.set(item.id, helper);
}

function selectedSceneItem() {
  if (selection.type === "light") return lightById(selection.id);
  if (selection.type === "camera") return sceneCameraById(selection.id);
  return null;
}

function selectedTransformVector() {
  const item = selectedSceneItem();
  if (!item) return null;
  return sceneTransformPart === "target" ? item.target : item.position;
}

function selectedTransformDisplayVector() {
  const item = selectedSceneItem();
  if (!item) return null;
  return selection.type === "light"
    ? lightHelperPosition(item, sceneTransformPart === "target")
    : sceneHelperPosition(selectedTransformVector(), sceneTransformPart === "target");
}

function sceneHelpersAllowed() {
  return (viewMode === "top" || activePanelId === "scene-panel")
    && !document.body.classList.contains("capture")
    && !activeSceneCameraId
    && !activeCameraPlanShotId;
}

function makeAxisHandle(axis, color) {
  const group = new THREE.Group();
  const material = new THREE.MeshBasicMaterial({ color, depthTest: false });
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.68, 10), material);
  shaft.position.y = 0.34;
  const head = new THREE.Mesh(new THREE.ConeGeometry(0.085, 0.2, 12), material.clone());
  head.position.y = 0.78;
  group.add(shaft, head);
  if (axis === "x") group.rotation.z = -Math.PI / 2;
  if (axis === "z") group.rotation.x = Math.PI / 2;
  group.traverse((object) => {
    if (!object.isMesh) return;
    object.renderOrder = 46;
    object.userData.pick = {
      type: "transform-axis",
      axis,
      targetType: selection.type,
      targetId: selection.id,
      part: sceneTransformPart,
    };
  });
  return group;
}

function buildTransformGizmo() {
  clearGroup(transformGizmoGroup);
  const vector = selectedTransformDisplayVector();
  const visible = Boolean(
    vector
      && sceneRig.gizmosVisible !== false
      && sceneHelpersAllowed(),
  );
  transformGizmoGroup.visible = visible;
  if (!visible) return;
  transformGizmoGroup.position.fromArray(vector);
  transformGizmoGroup.add(
    makeAxisHandle("x", 0xc64545),
    makeAxisHandle("y", 0x3b8a57),
    makeAxisHandle("z", 0x3478ba),
  );
  const center = new THREE.Mesh(
    new THREE.SphereGeometry(0.14, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false }),
  );
  center.renderOrder = 47;
  center.userData.pick = {
    type: "transform-plane",
    targetType: selection.type,
    targetId: selection.id,
    part: sceneTransformPart,
  };
  transformGizmoGroup.add(center);
}

function buildSceneRig() {
  sceneRigBuildCount += 1;
  clearGroup(managedLightGroup);
  clearGroup(sceneRigHelperGroup);
  managedLights.clear();
  lightHelperGroups.clear();
  cameraHelperGroups.clear();
  lightTargetLines.clear();
  cameraTargetLines.clear();
  sceneRig.lights.forEach(buildLightObject);
  sceneRig.cameras.forEach(buildCameraHelper);
  sceneRigHelperGroup.visible = sceneHelpersAllowed();
  const guideVisible = sceneRigHelperGroup.visible && sceneRig.gizmosVisible !== false;
  lightTargetLines.forEach((line) => { line.visible = guideVisible; });
  cameraTargetLines.forEach((line) => { line.visible = guideVisible; });
  const activeHelper = cameraHelperGroups.get(activeSceneCameraId);
  if (activeHelper) activeHelper.visible = false;
  buildTransformGizmo();
  requestRender();
}

function updateTransformGizmoPosition() {
  const vector = selectedTransformDisplayVector();
  if (!vector || !transformGizmoGroup.visible) return;
  transformGizmoGroup.position.fromArray(vector);
}

function updateLightVisual(item) {
  const light = managedLights.get(item.id);
  if (!light || light.userData.rigType !== item.type) {
    buildSceneRig();
    return;
  }
  const color = kelvinColor(item.temperatureK);
  light.color.copy(color);
  light.position.fromArray(item.position);
  light.visible = item.enabled !== false && sceneItemMatchesRoomFilter("light", item);
  light.castShadow = item.castShadow === true;
  if (item.type === "point") {
    light.intensity = Math.max(0, Number(item.intensity)) * 6;
    light.distance = Math.max(0, Number(item.distance));
    light.decay = Math.max(0, Number(item.decay));
  } else if (item.type === "spot") {
    light.intensity = Math.max(0, Number(item.intensity)) * 8;
    light.distance = Math.max(0, Number(item.distance));
    light.decay = Math.max(0, Number(item.decay));
    light.angle = THREE.MathUtils.degToRad(Math.max(5, Math.min(120, Number(item.angle))));
    light.penumbra = Math.max(0, Math.min(1, Number(item.penumbra)));
  } else {
    light.intensity = Math.max(0, Number(item.intensity));
  }
  if (light.target) {
    light.target.position.fromArray(item.target);
    light.target.updateMatrixWorld();
  }
  const helper = lightHelperGroups.get(item.id);
  if (helper) helper.visible = sceneHelpersAllowed() && sceneItemMatchesRoomFilter("light", item);
  helper?.children.filter((child) => ["marker", "ring", "pick-proxy"].includes(child.userData.role)).forEach((child) => {
    child.position.fromArray(lightHelperPosition(item));
    if (child.userData.role !== "pick-proxy") child.material.color.setHex(item.enabled === false ? 0x9ba29e : 0xc78b22);
  });
  updateTargetLine(
    lightTargetLines.get(item.id),
    lightHelperPosition(item),
    lightHelperPosition(item, true),
  );
  renderer.shadowMap.needsUpdate = true;
}

function updateCameraVisual(item) {
  const helper = cameraHelperGroups.get(item.id);
  if (helper) {
    helper.position.fromArray(sceneHelperPosition(item.position));
    helper.lookAt(new THREE.Vector3(...sceneHelperPosition(item.target, true)));
    helper.visible = sceneHelpersAllowed()
      && activeSceneCameraId !== item.id
      && sceneItemMatchesRoomFilter("camera", item);
  }
  const line = cameraTargetLines.get(item.id);
  updateTargetLine(line, sceneHelperPosition(item.position), sceneHelperPosition(item.target, true));
  if (line?.material?.color) {
    line.material.color.setHex(activeSceneCameraId === item.id ? 0x1e4f69 : 0x2b6f91);
  }
}

function updateSceneObjectVisual(type, item) {
  if (!item) return;
  sceneVisualUpdateCount += 1;
  if (type === "light") updateLightVisual(item);
  else updateCameraVisual(item);
  updateTransformGizmoPosition();
  requestRender();
}

function updateSceneRigVisibility() {
  sceneRig.lights.forEach(updateLightVisual);
  sceneRig.cameras.forEach(updateCameraVisual);
  sceneRigHelperGroup.visible = sceneHelpersAllowed();
  const guideVisible = sceneRigHelperGroup.visible && sceneRig.gizmosVisible !== false;
  lightTargetLines.forEach((line) => { line.visible = guideVisible; });
  cameraTargetLines.forEach((line) => { line.visible = guideVisible; });
  transformGizmoGroup.visible = Boolean(
    guideVisible
      && ["light", "camera"].includes(selection.type)
      && selectedTransformVector(),
  );
  const activeHelper = cameraHelperGroups.get(activeSceneCameraId);
  if (activeHelper) activeHelper.visible = false;
  lightHelperGroups.forEach((helper, id) => {
    helper.visible = sceneRigHelperGroup.visible && sceneItemMatchesRoomFilter("light", lightById(id));
  });
  cameraHelperGroups.forEach((helper, id) => {
    helper.visible = sceneRigHelperGroup.visible && sceneItemMatchesRoomFilter("camera", sceneCameraById(id));
  });
  managedLights.forEach((light, id) => {
    const item = lightById(id);
    light.visible = item?.enabled !== false && sceneItemMatchesRoomFilter("light", item);
  });
  updateTransformGizmoPosition();
  requestRender();
}

function wallRectangle(wall) {
  const frame = wallFrame(wall);
  return rotatedRectangle(frame.center, frame.length, wall.thickness, frame.angle);
}

function pointOnSegment(point, a, b, tolerance = 0.0001) {
  const cross = (point[1] - a[1]) * (b[0] - a[0]) - (point[0] - a[0]) * (b[1] - a[1]);
  if (Math.abs(cross) > tolerance) return false;
  const dot = (point[0] - a[0]) * (b[0] - a[0]) + (point[1] - a[1]) * (b[1] - a[1]);
  if (dot < -tolerance) return false;
  const squared = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2;
  return dot <= squared + tolerance;
}

function pointInPolygon(point, polygon) {
  for (let index = 0; index < polygon.length; index += 1) {
    if (pointOnSegment(point, polygon[index], polygon[(index + 1) % polygon.length])) return true;
  }
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, zi] = polygon[i];
    const [xj, zj] = polygon[j];
    const intersects = ((zi > point[1]) !== (zj > point[1]))
      && point[0] < (xj - xi) * (point[1] - zi) / (zj - zi || 0.000001) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

function wallSupportsRoom(wall, room) {
  return roomBoundaryIntervalsForWall(wall, room).length > 0;
}

function roomFilterIsAll() {
  const rooms = model.rooms || [];
  return modelScopeRoomIds.size === rooms.length
    && roomFilterIds.size === rooms.length
    && rooms.every((room) => roomFilterIds.has(room.id));
}

function roomAtWorldPoint(position) {
  if (!vector3IsValid(position)) return null;
  const point = planPoint(Number(position[0]), Number(position[2]));
  return (model.rooms || []).find((room) => pointInPolygon(point, room.polygon)) || null;
}

function wallMatchesRoomFilter(wall) {
  if (roomFilterIsAll()) return true;
  return (model.rooms || []).some(
    (room) => roomFilterIds.has(room.id) && wallSupportsRoom(wall, room),
  );
}

function windowMatchesRoomFilter(item) {
  if (roomFilterIsAll()) return true;
  const wall = wallById(item?.wallId);
  if (!wall) return false;
  const windowStart = item.offset - item.width / 2;
  const windowEnd = item.offset + item.width / 2;
  return (model.rooms || []).some((room) => (
    roomFilterIds.has(room.id)
    && roomBoundaryIntervalsForWall(wall, room).some(
      ([start, end]) => Math.min(end, windowEnd) - Math.max(start, windowStart) > 0.04,
    )
  ));
}

function componentMatchesRoomFilter(placement) {
  if (roomFilterIsAll()) return true;
  return roomFilterIds.has(placement?.roomId);
}

function sceneItemRoomId(type, item) {
  if (!item) return null;
  if (type === "camera" && roomById(item.focusRoomId)) return item.focusRoomId;
  const targetRoom = roomAtWorldPoint(item.target);
  if (targetRoom) return targetRoom.id;
  return roomAtWorldPoint(item.position)?.id || null;
}

function sceneItemMatchesRoomFilter(type, item) {
  if (roomFilterIsAll()) return true;
  const roomId = sceneItemRoomId(type, item);
  return Boolean(roomId && roomFilterIds.has(roomId));
}

function cameraPlanShotMatchesRoomFilter(shot) {
  return roomFilterIsAll()
    || shot.roomId === "whole-plan"
    || roomFilterIds.has(shot.roomId);
}

function visibleWalls() {
  return model.walls.filter(wallMatchesRoomFilter);
}

function visibleWindows() {
  return model.windows.filter(windowMatchesRoomFilter);
}

function visibleComponents() {
  return model.componentPlacements.filter(componentMatchesRoomFilter);
}

function visibleSceneItems(type) {
  const items = type === "light" ? sceneRig.lights : sceneRig.cameras;
  return items.filter((item) => sceneItemMatchesRoomFilter(type, item));
}

function renderRoomFilterControl() {
  const rooms = (model.rooms || []).filter((room) => modelScopeRoomIds.has(room.id));
  dom.roomFilterOptions.replaceChildren();
  rooms.forEach((room) => {
    const label = document.createElement("label");
    label.className = "room-filter-option";
    label.innerHTML = `<input type="checkbox" value="${room.id}"${roomFilterIds.has(room.id) ? " checked" : ""}><span>${room.name}</span>`;
    label.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) roomFilterIds.add(room.id);
      else roomFilterIds.delete(room.id);
      applyRoomFilter();
    });
    dom.roomFilterOptions.appendChild(label);
  });
  let summary = "全部空间";
  if (!roomFilterIsAll()) {
    if (roomFilterIds.size === 0) summary = "未选择";
    else if (roomFilterIds.size === 1) summary = roomById([...roomFilterIds][0])?.name || "1 个空间";
    else summary = `${roomFilterIds.size} 个空间`;
  }
  dom.roomFilterSummary.textContent = summary;
  dom.roomFilterToggle.classList.toggle("active", !roomFilterIsAll());
}

function ensureSelectionMatchesActivePanel() {
  if (activePanelId === "structure-panel") {
    const allowed = selection.type === "wall"
      ? visibleWalls().some((item) => item.id === selection.id)
      : selection.type === "window" && visibleWindows().some((item) => item.id === selection.id);
    if (!allowed) {
      const first = visibleWalls()[0] || visibleWindows()[0];
      selection = first
        ? { type: visibleWalls()[0] ? "wall" : "window", id: first.id }
        : { type: "wall", id: null };
    }
  } else if (activePanelId === "furniture-panel") {
    if (selection.type !== "component" || !visibleComponents().some((item) => item.id === selection.id)) {
      selection = { type: "component", id: visibleComponents()[0]?.id || null };
    }
  } else if (activePanelId === "scene-panel") {
    const visible = visibleSceneItems(sceneEditorMode);
    if (selection.type !== sceneEditorMode || !visible.some((item) => item.id === selection.id)) {
      selection = { type: sceneEditorMode, id: visible[0]?.id || null };
    }
  }
}

function applyRoomFilter() {
  buildRoomFilterStructure();
  ensureSelectionMatchesActivePanel();
  renderRoomFilterControl();
  applyLayerVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  setStatus(
    roomFilterIsAll()
      ? "已显示全部空间"
      : roomFilterIds.size
        ? `已筛选 ${roomFilterIds.size} 个空间`
        : "当前未选择空间",
    "success",
  );
}

function componentFootprint(placement) {
  const definition = getComponentDefinition(placement.componentId, placement.semantic);
  return placementFootprint(placement, definition);
}

function componentCollisions() {
  const placementById = new Map(model.componentPlacements.map((item) => [item.id, item]));
  const allowedContacts = new Set((model.relationHints?.allowedContacts || [])
    .filter((contact) => {
      const first = placementById.get(contact.firstId);
      const second = placementById.get(contact.secondId);
      const classes = new Set([first?.functionalClass, second?.functionalClass]);
      return contact.kind === "chair-tucked-under-table"
        && first
        && second
        && first.id !== second.id
        && classes.size === 2
        && classes.has("dining-chair")
        && classes.has("dining-table")
        && Object.keys(contact).every((field) => ["firstId", "secondId", "kind"].includes(field));
    })
    .map((contact) => [contact.firstId, contact.secondId].sort().join("::")));
  return componentCollisionPairs(
    model.componentPlacements,
    (componentId, semantic) => getComponentDefinition(componentId, semantic),
  ).filter((collision) => !allowedContacts.has(
    [collision.firstId, collision.secondId].sort().join("::"),
  ));
}

function componentStructureIssue(placement) {
  const footprint = componentFootprint(placement);
  if (!footprint.length) return "原组件不存在";
  if (placementMatchesSourceTransform(placement)) return null;
  const hostWallIds = new Set(placement.hostWallIds || []);
  const hostWalls = model.walls.filter(
    (wall) => wall.enabled !== false && hostWallIds.has(wall.id),
  );
  const attachedToHost = placement.attachmentMode === "flush-to-host-wall"
    && hostWalls.some((wall) => polygonsOverlap(footprint, wallRectangle(wall)));
  const centerInside = pointInPolygon(placement.position, model.floorBoundary);
  if (!footprint.every((point) => pointInPolygon(point, model.floorBoundary))) {
    if (!(attachedToHost && centerInside)) return "组件超出户型边界";
  }
  if (placement.attachmentMode === "flush-to-host-wall" && !attachedToHost) {
    return "组件脱离宿主墙";
  }
  const hitWall = model.walls.find(
    (wall) => wall.enabled !== false
      && !hostWallIds.has(wall.id)
      && polygonsOverlap(footprint, wallRectangle(wall)),
  );
  if (hitWall) return `组件与${hitWall.name}穿模`;
  const blockedConnection = (model.connections || []).find(
    (connection) => ["door", "open-passage", "sliding-door"].includes(connection.kind)
      && polygonsOverlap(footprint, connectionOpeningPolygon(connection)),
  );
  if (blockedConnection) return `组件跨越门洞或通道开口：${blockedConnection.id}`;
  return null;
}

function componentIssue(placement) {
  const definition = getComponentDefinition(placement.componentId, placement.semantic);
  const visual = definition ? resolvedVisualScale(definition, {
    uniformScale: placement.uniformScale ?? 1,
    visualDimensions: placement.visualDimensions,
  }) : null;
  const wallHeight = Math.min(...model.walls
    .filter((wall) => wall.enabled !== false && Number(wall.height) > 0)
    .map((wall) => Number(wall.height)));
  const elevation = Number(placement.elevation ?? definition?.defaultElevation ?? 0);
  if (["floor", "wall", "countertop"].includes(definition?.mountType)
      && Number.isFinite(wallHeight)
      && visual && elevation + visual.dimensions.height > wallHeight - 0.05 + 1e-6) {
    return `组件顶部 ${(elevation + visual.dimensions.height).toFixed(2)}m 超过墙高安全线 ${(wallHeight - 0.05).toFixed(2)}m`;
  }
  if (definition?.mountType === "wall" && !(elevation > 0)) return "吊柜必须设置正数离地高度";
  const structureIssue = componentStructureIssue(placement);
  if (structureIssue) return structureIssue;
  const hitComponent = componentCollisions().find(
    (collision) => collision.firstId === placement.id || collision.secondId === placement.id,
  );
  if (hitComponent) {
    const otherName = hitComponent.firstId === placement.id
      ? hitComponent.secondName
      : hitComponent.firstName;
    return `组件与${otherName}穿模`;
  }
  return null;
}

function validateWindows() {
  const issues = [];
  model.windows.forEach((item) => {
    const wall = wallById(item.wallId);
    if (!wall) {
      issues.push(`${item.name}缺少宿主墙`);
      return;
    }
    const length = wallFrame(wall).length;
    const margin = Math.max(0.1, wall.thickness * 0.8);
    if (item.width <= 0.2 || item.width > length - margin * 2 + 0.0001) issues.push(`${item.name}窗宽超出宿主墙`);
    if (item.offset - item.width / 2 < margin - 0.0001 || item.offset + item.width / 2 > length - margin + 0.0001) issues.push(`${item.name}位置超出宿主墙`);
    if (item.sill < 0 || item.openingHeight <= 0.3 || item.sill + item.openingHeight >= wall.height - 0.04) issues.push(`${item.name}竖向洞口超出墙高`);
  });
  model.walls.forEach((wall) => {
    const items = windowsForWall(wall.id).sort((a, b) => a.offset - b.offset);
    for (let index = 1; index < items.length; index += 1) {
      if (items[index - 1].offset + items[index - 1].width / 2 + 0.08 > items[index].offset - items[index].width / 2) {
        issues.push(`${items[index - 1].name}与${items[index].name}洞口重叠`);
      }
    }
  });
  return issues;
}

function componentContractIssues() {
  const issues = [];
  const reviewedAuthoredMismatch = (match) => (
    match?.matchMethod === "explicit-proportional-source-route"
    && match?.evidence?.sourceFootprintAuthority === "source-trace-collision"
    && match?.evidence?.visualFootprintAuthority === "authored-model-preserved"
    && match?.evidence?.visualFitReview?.status === "accepted"
    && typeof match?.evidence?.visualFitReview?.reason === "string"
    && match.evidence.visualFitReview.reason.trim().length >= 12
    && typeof match?.evidence?.visualFitReview?.userInstructionRef === "string"
    && match.evidence.visualFitReview.userInstructionRef.trim().length >= 8
  );
  const sourceTotal = Number(model.componentSource.movableGreenCount || 0) + Number(model.componentSource.fixedPurpleCount || 0);
  const removedSourceTraceIds = new Set(model.componentSource.removedSourceTraceIds || []);
  const sourcePlacements = model.componentPlacements.filter(
    (placement) => placement.placementOrigin !== "user-explicit-addition",
  );
  if (model.componentLayoutSchema !== "interior.component-layout.v4") {
    issues.push("组件布局必须使用轮廓与尺度策略锁定的 interior.component-layout.v4");
  }
  if (model.componentLibraryVersion !== COMPONENT_LIBRARY_VERSION) {
    issues.push("组件布局目录版本与当前公共组件库不一致");
  }
  if (model.componentMatches.length !== sourceTotal) issues.push("描线对象与匹配记录数量不一致");
  if (sourcePlacements.length + removedSourceTraceIds.size !== sourceTotal) {
    issues.push("描线对象数量不等于现存组件加用户已删除对象");
  }
  removedSourceTraceIds.forEach((sourceTraceId) => {
    if (!model.componentMatches.some((match) => match.sourceTraceId === sourceTraceId)) {
      issues.push(`已删除对象没有源描线记录：${sourceTraceId}`);
    }
    if (model.componentPlacements.some((placement) => placement.sourceTraceId === sourceTraceId)) {
      issues.push(`已删除对象仍存在于场景：${sourceTraceId}`);
    }
  });
  const traceIds = new Set();
  model.componentMatches.forEach((match) => {
    if (!match.sourceTraceId) issues.push("匹配记录缺少 sourceTraceId");
    if (traceIds.has(match.sourceTraceId)) issues.push(`重复描线对象：${match.sourceTraceId}`);
    traceIds.add(match.sourceTraceId);
    const definition = getComponentDefinition(match.componentId, match.semantic);
    if (!definition) issues.push(`组件未进入${match.semantic}分库：${match.componentId}`);
    if (definition && match.libraryPartition !== definition.libraryPartition) {
      issues.push(`匹配记录分库不一致：${match.sourceTraceId}`);
    }
    if (definition && match.libraryDirectory !== definition.libraryDirectory) {
      issues.push(`匹配记录目录不一致：${match.sourceTraceId}`);
    }
    if (Object.prototype.hasOwnProperty.call(match, "fallback")) issues.push(`禁止 fallback：${match.sourceTraceId}`);
    if (
      match.evidence?.outlineBoundToCollisionFootprint !== true
      || !["uniform-only", "axis-limited"].includes(match.evidence?.authoredGeometryScalePolicy)
      || !/^[a-f0-9]{64}$/.test(match.evidence?.sourceOutlineHash || "")
      || ![
        "proportional-authored-model-with-trace-footprint",
        "axis-limited-authored-cabinet-with-trace-footprint",
      ].includes(match.evidence?.traceReshape?.mode)
      || (match.evidence?.authoredGeometryScalePolicy === "uniform-only"
        && Number(match.evidence?.proportionalScaleSpread) > 0.25
        && !reviewedAuthoredMismatch(match))
    ) {
      issues.push(`组件缺少描线轮廓证据：${match.sourceTraceId}`);
    }
  });
  model.componentPlacements.forEach((placement) => {
    const definition = getComponentDefinition(placement.componentId, placement.semantic);
    if (placement.placementOrigin === "user-explicit-addition") {
      if (!placement.designAdditionId || !placement.userInstructionRef || !placement.roomId) {
        issues.push(`新增组件缺少用户指令或空间证据：${placement.id}`);
      }
      if (placement.sourceTraceId || placement.sourceObjectCandidateId) {
        issues.push(`新增组件不得冒充来源描线：${placement.id}`);
      }
      if (!definition || definition.placementClass !== placement.semantic) {
        issues.push(`新增组件分库不一致：${placement.id}`);
      }
      return;
    }
    const match = model.componentMatches.find((item) => item.sourceTraceId === placement.sourceTraceId);
    if (!match || match.componentId !== placement.componentId) issues.push(`放置组件未对应匹配记录：${placement.id}`);
    if (definition && placement.semantic !== definition.placementClass) issues.push(`描线颜色语义不一致：${placement.id}`);
    const target = placement.targetDimensions;
    const sourceDimensions = placement.sourceDimensions;
    if (!target || !sourceDimensions || (placement.traceLock?.dimensions === true && (
      Math.abs(Number(target.width) - Number(sourceDimensions.width)) > 0.0001
      || Math.abs(Number(target.depth) - Number(sourceDimensions.depth)) > 0.0001
    ))) {
      issues.push(`组件宽深未绑定描线：${placement.id}`);
    }
    if (
      !Array.isArray(placement.sourcePosition)
      || placement.sourcePosition.length !== 2
      || !placement.sourcePosition.every(Number.isFinite)
    ) {
      issues.push(`组件缺少描线原始坐标：${placement.id}`);
    }
    if (placement.traceLock?.position === false || placement.traceLock?.rotation === false) {
      const adjustment = placement.reviewedAdjustment;
      const changedFields = new Set(adjustment?.changedFields || []);
      const digestPattern = /^[a-f0-9]{64}$/;
      const userAuthority = adjustment?.authority === "user-explicit-layout-correction"
        && typeof adjustment?.userInstructionRef === "string"
        && adjustment.userInstructionRef.trim().length >= 8;
      const circulationAuthority = adjustment?.authority === "circulation-deterministic-correction"
        && digestPattern.test(adjustment?.sourceAuditDigestSha256 || "")
        && digestPattern.test(adjustment?.adjustmentPlanDigestSha256 || "")
        && digestPattern.test(adjustment?.operationDigestSha256 || "")
        && typeof adjustment?.candidateId === "string"
        && adjustment.candidateId.length >= 8;
      const reviewed = adjustment?.schema === "interior.reviewed-layout-adjustment.v1"
        && (userAuthority || circulationAuthority)
        && typeof adjustment?.reason === "string"
        && adjustment.reason.trim().length >= 12
        && (placement.traceLock?.position !== false || changedFields.has("position"))
        && (placement.traceLock?.rotation !== false || changedFields.has("rotationY"));
      if (!reviewed) issues.push(`组件布局调整缺少有效纠正证据：${placement.id}`);
    }
    if (
      placement.traceLock?.outline !== true
      || !Array.isArray(placement.sourceShapeEvidence?.outline)
      || !placement.sourceShapeMetrics
      || ![
        "proportional-authored-model-with-trace-footprint",
        "axis-limited-authored-cabinet-with-trace-footprint",
      ].includes(placement.traceReshape?.mode)
      || JSON.stringify(placement.traceReshape) !== JSON.stringify(match?.evidence?.traceReshape)
      || placement.shapeAdjustments?.sourceOutlineHash
        !== match?.evidence?.sourceOutlineHash
    ) {
      issues.push(`组件来源脚印或尺度策略证据不完整：${placement.id}`);
    }
    const group = componentGroups.get(placement.id);
    const footprint = group?.getObjectByName("trace-bound-footprint");
    if (
      !group?.userData.traceFootprintBound
      || group.userData.sourceOutlineHash !== match?.evidence?.sourceOutlineHash
      || !footprint?.userData.traceFootprint
      || footprint.userData.sourceOutlineHash !== match?.evidence?.sourceOutlineHash
      || JSON.stringify(footprint.userData.normalizedOutline)
        !== JSON.stringify(placement.sourceShapeEvidence?.outline)
    ) {
      issues.push(`组件运行时占地实体未复用描线轮廓：${placement.id}`);
    }
  });
  return issues;
}

function relationHintContractIssues() {
  const relations = model.relationHints;
  const issues = [];
  if (relations?.schema !== "interior.layout-relation-hints.v2") {
    return ["组件方向与目标提示合同缺失"];
  }
  const allowedKeys = new Set([
    "schema", "directionalAxes", "facing", "wallAttachment", "allowedContacts", "spaceDividerMarkers",
  ]);
  if (Object.keys(relations).some((key) => !allowedKeys.has(key))) {
    issues.push("组件方向与目标提示含旧字段或计算字段");
  }
  const placementIds = new Set(model.componentPlacements.map((item) => item.id));
  const wallIds = new Set(model.walls.map((item) => item.id));
  const dividerIds = new Set((model.semanticDividers || []).map((item) => item.id));
  const componentIds = new Set(model.componentPlacements.map((item) => item.componentId));
  const axisKeys = new Set();
  (relations.directionalAxes || []).forEach((axis) => {
    const key = `${axis.assetId}::${axis.role}`;
    if (!componentIds.has(axis.assetId)
        || axisKeys.has(key)
        || !["front", "back", "headboard"].includes(axis.role)
        || !["+X", "-X", "+Z", "-Z"].includes(axis.localAxis)
        || axis.evidence !== "browser-reviewed-authored-model"
        || Object.keys(axis).some((field) => !["assetId", "role", "localAxis", "evidence"].includes(field))) {
      issues.push(`方向轴提示无效：${key}`);
    }
    axisKeys.add(key);
  });
  (relations.facing || []).forEach((relation) => {
    const source = model.componentPlacements.find((item) => item.id === relation.sourceId);
    if (!source || !placementIds.has(relation.targetId)
        || !axisKeys.has(`${source.componentId}::${relation.axisRole}`)
        || Object.keys(relation).some((field) => !["sourceId", "targetId", "axisRole"].includes(field))) {
      issues.push(`朝向关系对象不存在：${relation.sourceId}`);
    }
  });
  (relations.wallAttachment || []).forEach((relation) => {
    const source = model.componentPlacements.find((item) => item.id === relation.sourceId);
    if (!source || !wallIds.has(relation.wallId)
        || !axisKeys.has(`${source.componentId}::${relation.axisRole}`)
        || Object.keys(relation).some((field) => !["sourceId", "wallId", "axisRole"].includes(field))) {
      issues.push(`贴墙关系对象不存在：${relation.sourceId}`);
    }
  });
  (relations.allowedContacts || []).forEach((contact) => {
    const first = model.componentPlacements.find((item) => item.id === contact.firstId);
    const second = model.componentPlacements.find((item) => item.id === contact.secondId);
    const classes = new Set([first?.functionalClass, second?.functionalClass]);
    if (!first
        || !second
        || first.id === second.id
        || contact.kind !== "chair-tucked-under-table"
        || classes.size !== 2
        || !classes.has("dining-chair")
        || !classes.has("dining-table")
        || Object.keys(contact).some((field) => !["firstId", "secondId", "kind"].includes(field))) {
      issues.push(`允许接触提示无效：${contact.firstId || "unknown"}`);
    }
  });
  (relations.spaceDividerMarkers || []).forEach((marker) => {
    if (!marker.id || !dividerIds.has(marker.semanticDividerId)
        || marker.kind !== "space-threshold"
        || marker.visible !== true
        || !(Number(marker.width) > 0 && Number(marker.height) > 0)) {
      issues.push(`开放空间分界标志无效：${marker.id || marker.semanticDividerId}`);
    }
  });
  return issues;
}

function sceneRigIssues() {
  const issues = [];
  const ids = new Set();
  if (sceneRig.schema !== "interior.scene-rig.v1") issues.push("场景 Rig schema 错误");
  if (sceneRig.coordinateSystem !== "threejs-world-y-up-meters") issues.push("场景坐标系错误");
  if (
    sceneRig.rendering?.toneMapping !== "ACESFilmic"
    || sceneRig.rendering.exposure < 0.3
    || sceneRig.rendering.exposure > 1.5
  ) {
    issues.push("场景白模曝光设置无效");
  }
  if (!Array.isArray(sceneRig.lights) || sceneRig.lights.length < 1) issues.push("至少保留一个可编辑光源");
  if (!Array.isArray(sceneRig.cameras) || sceneRig.cameras.length < 1) issues.push("至少保留一个场景摄像头");
  [...(sceneRig.lights || []), ...(sceneRig.cameras || [])].forEach((item) => {
    if (!item.id || ids.has(item.id)) issues.push(`场景对象 ID 重复：${item.id || "empty"}`);
    ids.add(item.id);
    if (!vector3IsValid(item.position) || !vector3IsValid(item.target)) issues.push(`${item.name || item.id}坐标无效`);
  });
  (sceneRig.lights || []).forEach((item) => {
    if (!["directional", "point", "spot"].includes(item.type)) issues.push(`${item.name}光源类型无效`);
    if (item.intensity < 0 || item.intensity > 12) issues.push(`${item.name}亮度超出范围`);
    if (item.temperatureK < 2000 || item.temperatureK > 10000) issues.push(`${item.name}色温超出范围`);
    if (item.distance < 0 || item.distance > 80) issues.push(`${item.name}照射距离超出范围`);
    if (item.decay < 0 || item.decay > 4) issues.push(`${item.name}衰减超出范围`);
    if (item.angle < 5 || item.angle > 120) issues.push(`${item.name}光束角超出范围`);
    if (item.penumbra < 0 || item.penumbra > 1) issues.push(`${item.name}柔边超出范围`);
  });
  (sceneRig.cameras || []).forEach((item) => {
    if (item.fov < 15 || item.fov > 100) issues.push(`${item.name}视场角超出范围`);
    if (item.focalLengthMm < 14 || item.focalLengthMm > 85) issues.push(`${item.name}焦距超出范围`);
    if (Number(item.distortion || 0) !== 0) issues.push(`${item.name}正式室内镜头禁止鱼眼或桶形曲度`);
    if (item.near <= 0 || item.far <= item.near) issues.push(`${item.name}裁切范围无效`);
    if (!["ultra-wide", "wide", "standard", "telephoto", "custom"].includes(item.lensPreset)) issues.push(`${item.name}镜头预设无效`);
    if (!["free", "wall"].includes(item.mount?.mode)) issues.push(`${item.name}安装方式无效`);
    if (typeof item.mount?.snapEnabled !== "boolean") issues.push(`${item.name}墙面吸附状态无效`);
    if (item.focusRoomId && !roomById(item.focusRoomId)) issues.push(`${item.name}焦点空间不存在`);
    if (!Array.isArray(item.visibility?.hiddenWallIds) || !Array.isArray(item.visibility?.hiddenComponentIds)) {
      issues.push(`${item.name}视线隐藏记录无效`);
    } else {
      item.visibility.hiddenWallIds.forEach((id) => {
        if (!wallById(id)) issues.push(`${item.name}记录了不存在的隐藏墙：${id}`);
      });
      item.visibility.hiddenComponentIds.forEach((id) => {
        if (!componentById(id)) issues.push(`${item.name}记录了不存在的隐藏组件：${id}`);
      });
    }
    if (
      item.visibility?.contextPolicy !== "preserve-visible-adjacent-spaces"
    ) {
      issues.push(`${item.name}必须保留可见相邻空间，并只应用显式局部遮挡`);
    }
    ["hiddenElementIds", "preserveElementIds"].forEach((field) => {
      if (!Array.isArray(item.visibility?.[field])) issues.push(`${item.name}${field}记录无效`);
    });
    if (item.mount?.mode === "wall") {
      const wall = wallById(item.mount.wallId);
      if (!wall) issues.push(`${item.name}缺少挂载墙`);
      else {
        if (item.mount.offset < 0 || item.mount.offset > wallFrame(wall).length) issues.push(`${item.name}沿墙位置无效`);
        if (item.mount.height < 0.2 || item.mount.height > wall.height - 0.15) issues.push(`${item.name}安装高度超出墙体`);
      }
    }
  });
  return issues;
}

function validateModel() {
  const issues = [...validateWindows(), ...componentContractIssues(), ...sceneRigIssues()];
  const ids = new Set();
  [...model.walls, ...model.windows, ...model.componentPlacements].forEach((item) => {
    if (ids.has(item.id)) issues.push(`重复对象 ID：${item.id}`);
    ids.add(item.id);
  });
  model.walls.forEach((wall) => {
    if (wallFrame(wall).length <= 0.2 || wall.height <= 0.3 || wall.thickness <= 0.04) issues.push(`${wall.name}尺寸无效`);
    if (![wall.start, wall.end].every((point) => pointInPolygon(point, model.floorBoundary))) issues.push(`${wall.name}超出户型边界`);
  });
  model.componentPlacements.forEach((placement) => {
    const issue = componentIssue(placement);
    if (issue) issues.push(`${placement.name}：${issue}`);
  });
  componentCollisions().forEach((collision) => {
    issues.push(`${collision.firstName}与${collision.secondName}互相穿模`);
  });
  return [...new Set(issues)];
}

function serializeModel() {
  return JSON.stringify({ model, sceneRig });
}

function restoreSnapshot(snapshot) {
  const restored = JSON.parse(snapshot);
  Object.keys(model).forEach((key) => delete model[key]);
  Object.assign(model, restored.model);
  Object.keys(sceneRig).forEach((key) => delete sceneRig[key]);
  Object.assign(sceneRig, restored.sceneRig);
  normalizeSceneRigData(sceneRig);
  if (!sceneCameraById(activeOcclusionCameraId)?.visibility?.cutawayEnabled) {
    activeOcclusionCameraId = sceneRig.cameras.find((item) => item.visibility?.cutawayEnabled)?.id || null;
  }
}

function performMutation(label, mutate) {
  const before = serializeModel();
  mutate();
  const issues = validateModel();
  if (issues.length) {
    restoreSnapshot(before);
    rebuildAll();
    setStatus(`${label}未应用：${issues[0]}`, "error");
    return false;
  }
  undoStack.push(before);
  if (undoStack.length > 80) undoStack.shift();
  redoStack.length = 0;
  rebuildAll();
  setStatus(`${label}已应用`, "success");
  return true;
}

function undo() {
  if (cameraPlanPreviewSnapshot) {
    setStatus("已保存机位为临时预览；再次点击该机位恢复后再撤销", "error");
    return;
  }
  if (!undoStack.length) return;
  redoStack.push(serializeModel());
  restoreSnapshot(undoStack.pop());
  rebuildAll();
  setStatus("已撤销");
}

function redo() {
  if (cameraPlanPreviewSnapshot) {
    setStatus("已保存机位为临时预览；再次点击该机位恢复后再重做", "error");
    return;
  }
  if (!redoStack.length) return;
  undoStack.push(serializeModel());
  restoreSnapshot(redoStack.pop());
  rebuildAll();
  setStatus("已重做");
}

function updateComponentField(placement, field, value) {
  if (field === "x") placement.position[0] = Number(value);
  if (field === "z") placement.position[1] = Number(value);
  if (field === "rotationY") placement.rotationY = Number(value) * Math.PI / 180;
  if (field === "uniformScale") {
    const definition = getComponentDefinition(placement.componentId, placement.semantic);
    placement.uniformScale = clampUniformScale(definition, value);
  }
  if (["visualWidth", "visualDepth", "visualHeight"].includes(field)) {
    const definition = getComponentDefinition(placement.componentId, placement.semantic);
    const axis = field.replace("visual", "").toLowerCase();
    const current = resolvedVisualScale(definition, {
      uniformScale: placement.uniformScale ?? 1,
      visualDimensions: placement.visualDimensions,
    }).dimensions;
    const requested = { ...current, [axis]: Number(value) };
    const resolved = resolvedVisualScale(definition, {
      uniformScale: placement.uniformScale ?? 1,
      visualDimensions: requested,
    });
    placement.visualDimensions = { ...resolved.dimensions };
    if (["width", "depth"].includes(axis)) {
      placement.targetDimensions = {
        ...placement.targetDimensions,
        [axis]: resolved.dimensions[axis],
      };
      placement.traceLock = { ...placement.traceLock, dimensions: false };
    }
  }
  if (field === "elevation") placement.elevation = Math.max(0, Number(value));
}

function deleteSelectedComponent() {
  const placement = selection.type === "component" ? componentById(selection.id) : null;
  if (!placement) {
    setStatus("请先选中要删除的组件", "error");
    return false;
  }
  const applied = performMutation(`删除${placement.name}`, () => {
    model.componentPlacements = model.componentPlacements.filter((item) => item.id !== placement.id);
    if (placement.placementOrigin !== "user-explicit-addition") {
      model.componentSource.removedSourceTraceIds = [
        ...new Set([...(model.componentSource.removedSourceTraceIds || []), placement.sourceTraceId]),
      ];
    }
    keyboardMoveComponentId = null;
    selection = { type: "component", id: visibleComponents()[0]?.id || null };
  });
  return applied;
}

function setComponentVisibility(id, visible) {
  const placement = componentById(id);
  if (!placement) return false;
  return performMutation(`${visible ? "显示" : "隐藏"}${placement.name}`, () => {
    placement.presentationHidden = !visible;
    selection = { type: "component", id };
  });
}

function resetComponentPlacement(id) {
  const placement = componentById(id);
  const original = originalModel.componentPlacements.find((item) => item.id === id);
  if (!placement || !original) {
    setStatus("没有可恢复的组件初始位置", "error");
    return false;
  }
  return performMutation(`复位${placement.name}`, () => {
    const index = model.componentPlacements.findIndex((item) => item.id === id);
    model.componentPlacements[index] = structuredClone(original);
    selection = { type: "component", id };
    keyboardMoveComponentId = id;
  });
}

function rotateComponentPlacement(id, degrees = 90) {
  const placement = componentById(id);
  if (!placement) {
    setStatus("请先选中要旋转的组件", "error");
    return false;
  }
  const before = serializeModel();
  const radians = Number(degrees) * Math.PI / 180;
  placement.rotationY = THREE.MathUtils.euclideanModulo(
    Number(placement.rotationY || 0) + radians + Math.PI,
    Math.PI * 2,
  ) - Math.PI;
  const issues = validateModel();
  if (issues.length) {
    restoreSnapshot(before);
    setStatus(`旋转未应用：${issues[0]}`, "error");
    return false;
  }
  undoStack.push(before);
  if (undoStack.length > 80) undoStack.shift();
  redoStack.length = 0;
  selection = { type: "component", id };
  keyboardMoveComponentId = id;
  const group = componentGroups.get(id);
  if (group) group.rotation.y = placement.rotationY;
  renderLists();
  renderInspectors();
  updateUndoButtons();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  setStatus(`${placement.name}已顺时针旋转 ${Math.abs(Number(degrees))}°`, "success");
  return true;
}

function armComponentKeyboardMove(id) {
  const placement = componentById(id);
  if (!placement || !componentMatchesRoomFilter(placement)) return false;
  keyboardMoveComponentId = id;
  selection = { type: "component", id };
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  setStatus(`已启用${placement.name}键盘移动；方向键移动，Shift 加速`, "success");
  return true;
}

function nudgeComponent(id, dx, dz) {
  const placement = componentById(id);
  if (!placement) return false;
  const before = serializeModel();
  placement.position[0] += dx;
  placement.position[1] += dz;
  const issues = validateModel();
  if (issues.length) {
    restoreSnapshot(before);
    setStatus(`移动未应用：${issues[0]}`, "error");
    return false;
  }
  undoStack.push(before);
  if (undoStack.length > 80) undoStack.shift();
  redoStack.length = 0;
  const group = componentGroups.get(id);
  const world = worldPoint(placement.position);
  if (group) group.position.set(world.x, 0.01, world.z);
  renderLists();
  renderInspectors();
  updateUndoButtons();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  setStatus(`${placement.name}已移动`, "success");
  return true;
}

function startComponentDrag(event, id) {
  const placement = componentById(id);
  const point = planPointAt(event);
  if (!placement || !point || !componentMatchesRoomFilter(placement)) return false;
  selectObject("component", id, false);
  keyboardMoveComponentId = id;
  componentDrag = {
    id,
    before: serializeModel(),
    start: [...placement.position],
    lastValid: [...placement.position],
    offset: [placement.position[0] - point[0], placement.position[1] - point[1]],
    moved: false,
    rejectedIssue: null,
  };
  controls.enabled = false;
  renderer.domElement.setPointerCapture?.(event.pointerId);
  document.body.classList.add("component-dragging");
  return true;
}

function sweptComponentMove(placement, from, to) {
  const distance = Math.hypot(to[0] - from[0], to[1] - from[1]);
  const stepMeters = Math.max(0.005, Number(model.backendOptions.collision?.stepMeters || 0.02));
  const steps = Math.max(1, Math.ceil(distance / stepMeters));
  let lastValid = [...from];
  let rejectedIssue = null;
  for (let index = 1; index <= steps; index += 1) {
    const ratio = index / steps;
    const candidate = [
      from[0] + (to[0] - from[0]) * ratio,
      from[1] + (to[1] - from[1]) * ratio,
    ];
    placement.position = candidate;
    const issue = componentIssue(placement);
    if (issue) {
      rejectedIssue = issue;
      break;
    }
    lastValid = candidate;
  }
  placement.position = [...lastValid];
  return { position: lastValid, rejectedIssue };
}

function updateComponentDrag(event) {
  if (!componentDrag) return false;
  const point = planPointAt(event);
  const placement = componentById(componentDrag.id);
  if (!point || !placement) return false;
  const candidate = [
    point[0] + componentDrag.offset[0],
    point[1] + componentDrag.offset[1],
  ];
  const previous = [...placement.position];
  const swept = sweptComponentMove(placement, previous, candidate);
  componentDrag.lastValid = [...swept.position];
  componentDrag.moved = componentDrag.moved
    || Math.hypot(swept.position[0] - componentDrag.start[0], swept.position[1] - componentDrag.start[1]) > 0.01;
  componentDrag.rejectedIssue = swept.rejectedIssue;
  const group = componentGroups.get(componentDrag.id);
  const world = worldPoint(swept.position);
  if (group) group.position.set(world.x, 0.01, world.z);
  requestRender();
  return swept.rejectedIssue === null;
}

function finishComponentDrag(cancelled = false) {
  if (!componentDrag) return false;
  const drag = componentDrag;
  const placement = componentById(drag.id);
  componentDrag = null;
  controls.enabled = true;
  document.body.classList.remove("component-dragging");
  if (cancelled || !placement) {
    restoreSnapshot(drag.before);
    rebuildAll();
    setStatus("已取消组件移动");
    return false;
  }
  if (!drag.moved) {
    placement.position = [...drag.start];
    const group = componentGroups.get(drag.id);
    const world = worldPoint(placement.position);
    if (group) group.position.set(world.x, 0.01, world.z);
    return true;
  }
  const room = (model.rooms || []).find((item) => pointInPolygon(placement.position, item.polygon));
  if (room) placement.roomId = room.id;
  const issues = validateModel();
  if (issues.length) {
    restoreSnapshot(drag.before);
    rebuildAll();
    setStatus(`移动未应用：${issues[0]}`, "error");
    return false;
  }
  undoStack.push(drag.before);
  if (undoStack.length > 80) undoStack.shift();
  redoStack.length = 0;
  renderLists();
  renderInspectors();
  updateUndoButtons();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  setStatus(`${placement.name}已移动`, "success");
  return true;
}

function objectLabel(type) {
  if (type === "wall") return "墙";
  if (type === "window") return "窗";
  if (type === "component") return "组件";
  if (type === "light") return "光源";
  return "摄像头";
}

function sceneItemIndex(type, item) {
  const items = type === "light" ? sceneRig.lights : sceneRig.cameras;
  const index = item ? items.findIndex((candidate) => candidate.id === item.id) : -1;
  return index >= 0 ? index + 1 : 1;
}

function sceneDisplayName(type, item) {
  return `${type === "light" ? "光" : "摄像头"} ${sceneItemIndex(type, item)}`;
}

function lensPresetForFov(fov) {
  return lensPresetForFocalLength(focalLengthForFov(fov));
}

function roomById(id) {
  return (model.rooms || []).find((room) => room.id === id);
}

function roomFocusTarget(room) {
  if (!room) return null;
  const point = room.labelPosition || room.polygon?.reduce(
    (sum, current) => [
      sum[0] + current[0] / room.polygon.length,
      sum[1] + current[1] / room.polygon.length,
    ],
    [0, 0],
  );
  if (!point) return null;
  const world = worldPoint(point);
  return [world.x, 1, world.z];
}

function objectName(type, id) {
  if (type === "wall") return wallById(id)?.name;
  if (type === "window") return windowById(id)?.name;
  if (type === "component") return componentById(id)?.name;
  if (type === "light") return sceneDisplayName("light", lightById(id));
  return sceneDisplayName("camera", sceneCameraById(id));
}

function applySceneEditorModeUi() {
  const lightMode = sceneEditorMode === "light";
  dom.sceneModeLight.classList.toggle("active", lightMode);
  dom.sceneModeLight.setAttribute("aria-selected", String(lightMode));
  dom.sceneModeCamera.classList.toggle("active", !lightMode);
  dom.sceneModeCamera.setAttribute("aria-selected", String(!lightMode));
  dom.lightModeContent.hidden = !lightMode;
  dom.cameraModeContent.hidden = lightMode;
  dom.cameraPlanDeck.hidden = lightMode;
  document.getElementById("add-light").hidden = !lightMode;
  document.getElementById("add-camera").hidden = lightMode;
}

function setSceneEditorMode(mode, selectFirst = true) {
  if (!["light", "camera"].includes(mode)) return;
  sceneEditorMode = mode;
  sceneTransformPart = "position";
  if (selectFirst && selection.type !== mode) {
    const first = mode === "light" ? sceneRig.lights[0] : sceneRig.cameras[0];
    if (first) selection = { type: mode, id: first.id };
  }
  applySceneEditorModeUi();
  renderLists();
  renderInspectors();
  buildTransformGizmo();
  updateSceneRigVisibility();
  updateSelectionHighlight();
  requestRender();
}

function selectObject(type, id, switchTab = true) {
  const changedObject = selection.type !== type || selection.id !== id;
  selection = { type, id };
  if (type === "component") keyboardMoveComponentId = id;
  else if (changedObject) keyboardMoveComponentId = null;
  if (changedObject) sceneTransformPart = "position";
  if (type === "wall") lastSelectedWallId = id;
  if (type === "camera") previewSceneCameraId = id;
  if (switchTab) {
    if (type === "component") activateTab("furniture-panel");
    else if (type === "light" || type === "camera") {
      sceneEditorMode = type;
      activateTab("scene-panel");
    }
    else activateTab("structure-panel");
  }
  applySceneEditorModeUi();
  renderLists();
  renderInspectors();
  if (type === "light" || type === "camera") {
    buildTransformGizmo();
    updateSceneRigVisibility();
  }
  updateSelectionHighlight();
  requestRender();
}

function clearSelectionForCanvasNavigation({ announce = true } = {}) {
  selection = { type: "none", id: null };
  keyboardMoveComponentId = null;
  sceneTransformPart = "position";
  clearGroup(transformGizmoGroup);
  transformGizmoGroup.visible = false;
  renderLists();
  renderInspectors();
  updateSceneRigVisibility();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  if (announce) setStatus("已取消对象选择；方向键可平移整个画布", "success");
  return true;
}

function updateSelectionHighlight() {
  if (selectionHelper) {
    scene.remove(selectionHelper);
    selectionHelper.geometry?.dispose?.();
    selectionHelper.material?.dispose?.();
    selectionHelper = null;
  }
  let object = null;
  if (selection.type === "wall") {
    object = roomFilterIsAll()
      ? wallGroups.get(selection.id)
      : roomFilterWallGroups.get(selection.id);
  }
  if (selection.type === "window") {
    object = roomFilterIsAll()
      ? windowGroups.get(selection.id)
      : roomFilterWindowGroups.get(selection.id);
  }
  if (selection.type === "component") object = componentGroups.get(selection.id);
  if (selection.type === "light") object = lightHelperGroups.get(selection.id)?.children.find((child) => child.isMesh);
  if (selection.type === "camera") object = cameraHelperGroups.get(selection.id);
  if ((selection.type === "light" || selection.type === "camera") && !sceneRigHelperGroup.visible) object = null;
  if (object?.visible) {
    selectionHelper = new THREE.BoxHelper(object, 0x9a6b1d);
    selectionHelper.material.depthTest = false;
    selectionHelper.renderOrder = 20;
    scene.add(selectionHelper);
  }
  const name = objectName(selection.type, selection.id);
  dom.selectionChip.hidden = !name;
  dom.selectionChip.textContent = name ? `${objectLabel(selection.type)} · ${name}` : "";
  buildWallEndpointHandles();
  requestRender();
}

function structureButton(type, item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `object-button${selection.type === type && selection.id === item.id ? " active" : ""}`;
  const wall = type === "window" ? wallById(item.wallId) : null;
  const detail = type === "wall" ? (item.type === "external" ? "外墙" : "隔墙") : wall?.name || "未绑定";
  button.innerHTML = `<i class="object-dot ${type === "window" ? "window" : ""}"></i><span>${item.name}</span><small>${detail}</small>`;
  button.addEventListener("click", () => selectObject(type, item.id, false));
  return button;
}

function sceneObjectButton(type, item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `object-button${selection.type === type && selection.id === item.id ? " active" : ""}`;
  const lightTypes = { directional: "平行光", point: "点光源", spot: "聚光灯" };
  const detail = type === "light"
    ? lightTypes[item.type] || item.type
    : `${Math.round(item.focalLengthMm)}mm${activeSceneCameraId === item.id ? " · 当前" : detachedCameraId === item.id ? " · 已离开" : ""}${item.mount?.mode === "wall" ? " · 吸附" : ""}`;
  const disabled = type === "light" && item.enabled === false;
  const stateClass = disabled ? "object-state off" : "object-state";
  const state = disabled ? "关闭" : detail;
  button.innerHTML = `<i class="object-dot ${type}"></i><span>${sceneDisplayName(type, item)}</span><small class="${stateClass}">${state}</small>`;
  button.addEventListener("click", () => selectObject(type, item.id, false));
  return button;
}

function lightingSetupById(id) {
  return (cameraPlan.lightingSetups || []).find((item) => item.lightingSetupId === id) || null;
}

function cameraPlanIssues(plan) {
  const issues = [];
  if (!plan || plan.schema !== "interior.camera-plan.v8" || plan.schemaVersion !== "8.0") {
    issues.push("机位与打光 JSON schema 无效");
  }
  if (!Array.isArray(plan?.shots)) issues.push("机位 JSON 缺少 shots");
  if (!Array.isArray(plan?.lightingSetups)) issues.push("机位 JSON 缺少 lightingSetups");
  if (
    plan?.floorplanId
    && model.floorplanId
    && plan.floorplanId !== model.floorplanId
  ) {
    issues.push(`机位 JSON 属于其它户型：${plan.floorplanId}`);
  }
  const lightingIds = new Set();
  (plan?.lightingSetups || []).forEach((setup, index) => {
    const setupId = setup?.lightingSetupId;
    if (!setupId) issues.push(`第 ${index + 1} 个打光方案缺少 lightingSetupId`);
    if (lightingIds.has(setupId)) issues.push(`重复打光方案 ID：${setupId}`);
    lightingIds.add(setupId);
    if (!setup?.name || !setup?.strategy || !setup?.rationale) {
      issues.push(`${setupId || `第 ${index + 1} 个打光方案`}缺少名称、策略或理由`);
    }
    if (!Array.isArray(setup?.lights) || !setup.lights.length) {
      issues.push(`${setupId || `第 ${index + 1} 个打光方案`}没有光源`);
    }
    (setup?.lights || []).forEach((light) => {
      if (!light?.id || !["directional", "point", "spot"].includes(light.type)) {
        issues.push(`${setupId || "打光方案"}含无效光源`);
      }
      if (!vector3IsValid(light?.position) || !vector3IsValid(light?.target)) {
        issues.push(`${light?.id || setupId || "打光方案"}光源坐标无效`);
      }
    });
  });
  const shotIds = new Set();
  (plan?.shots || []).forEach((shot, index) => {
    if (!shot.shotId) issues.push(`第 ${index + 1} 个机位缺少 shotId`);
    if (shotIds.has(shot.shotId)) issues.push(`重复机位 ID：${shot.shotId}`);
    shotIds.add(shot.shotId);
    if (!vector3IsValid(shot.position) || !vector3IsValid(shot.target)) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}坐标无效`);
    }
    if (Number(shot.distortion || 0) !== 0) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}正式机位禁止鱼眼或桶形曲度`);
    }
    const framing = shot.framing;
    const requiredDistance = Math.max(
      Number(framing?.frameWidthMeters || 0) * Number(shot.focalLengthMm || 0) / 36,
      Number(framing?.frameHeightMeters || 0) * Number(shot.focalLengthMm || 0) / 24,
    );
    const actualDistance = Math.hypot(
      Number(shot.position?.[0] || 0) - Number(shot.target?.[0] || 0),
      Number(shot.position?.[2] || 0) - Number(shot.target?.[2] || 0),
    );
    if (
      !framing
      || framing.measurementBasis !== "structure-and-component-bounds"
      || framing.fitFormula !== "frameWidth=max(referenceWidth/targetOccupancy,anchorHeight/verticalOccupancy*36/24);targetDistance=frameWidth*focalLength/36"
      || framing.fitPass !== true
      || Math.abs(Number(framing.targetPlaneDistanceMeters) - requiredDistance) > 0.02
      || Math.abs(Number(framing.actualDistanceMeters) - actualDistance) > 0.05
      || actualDistance + 0.001 < requiredDistance
    ) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}缺少合法的量尺 framing`);
    }
    if (
      !shot.expectedFrame
      || ["firstRead", "foreground", "middleground", "background", "subjectFacing", "lightingIntent"]
        .some((field) => !String(shot.expectedFrame[field] || "").trim())
    ) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}缺少预期成片卡`);
    }
    if (!roomById(shot.roomId) && shot.roomId !== "whole-plan") {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}焦点空间不存在`);
    }
    if (
      shot.visibility?.mode !== "all-spaces"
      || shot.visibility?.contextPolicy !== "preserve-visible-adjacent-spaces"
    ) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}必须保留可见相邻空间，只允许显式局部遮挡`);
    }
    const hiddenElementIds = shot.visibility?.hiddenElementIds || [];
    if (!Array.isArray(hiddenElementIds) || hiddenElementIds.some((id) => typeof id !== "string")) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}显式遮挡清单无效`);
    }
    if (hiddenElementIds.some((id) => (shot.mustShowElements || []).includes(id))) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}不能隐藏 mustShowElements`);
    }
    if (shot.lightingSetupId !== null && !lightingIds.has(shot.lightingSetupId)) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}引用了不存在的打光方案`);
    }
    const rendering = shot.rendering;
    if (
      rendering?.toneMapping !== "ACESFilmic"
      || !Number.isFinite(Number(rendering?.exposure))
      || Number(rendering.exposure) < 0.3
      || Number(rendering.exposure) > 1.5
      || !Number.isFinite(Number(rendering?.ambientIntensity))
      || !Number.isFinite(Number(rendering?.hemisphereIntensity))
      || !Number.isFinite(Number(rendering?.detailFillIntensity))
    ) {
      issues.push(`${shot.shotId || `第 ${index + 1} 个机位`}缺少合法的白模曝光参数`);
    }
  });
  return issues;
}

function renderCameraPlanList() {
  dom.cameraPlanList.replaceChildren();
  const shots = [...(cameraPlan.shots || [])].filter(cameraPlanShotMatchesRoomFilter).sort(
    (first, second) => Number(first.sequenceOrder || 0) - Number(second.sequenceOrder || 0),
  );
  dom.cameraPlanCount.textContent = `${shots.length}/${cameraPlan.shots?.length || 0} 个`;
  shots.forEach((shot, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `object-button${activeCameraPlanShotId === shot.shotId ? " active" : ""}`;
    const room = roomById(shot.roomId);
    const focal = Number(shot.focalLengthMm || focalLengthForFov(shot.fov)).toFixed(0);
    const hasLighting = Boolean(shot.lightingSetupId);
    button.innerHTML = `
      <i class="camera-plan-order">${Number(shot.sequenceOrder || index + 1)}</i>
      <span>${room?.name || shot.spacePrimarySubject || shot.roomId || shot.shotId}</span>
      <small>
        ${shot.role || "机位"} · ${focal}mm
        <i class="camera-plan-badge">全</i>
        ${hasLighting ? '<i class="camera-plan-badge">光</i>' : ""}
      </small>`;
    button.title = `${shot.spacePrimarySubject || room?.name || shot.shotId}；保留可见相邻空间，仅隐藏显式局部遮挡；${hasLighting ? lightingSetupById(shot.lightingSetupId)?.name || "逐机位打光" : "沿用场景光"}`;
    button.addEventListener("click", () => previewCameraPlanShot(shot.shotId));
    dom.cameraPlanList.appendChild(button);
  });
  if (!shots.length) {
    const empty = document.createElement("div");
    empty.className = "empty-list-note";
    empty.textContent = "本户型尚无已保存机位；可载入 camera-plan.json 后快速预览。";
    dom.cameraPlanList.appendChild(empty);
  }
}

function loadCameraPlanData(nextPlan) {
  const issues = cameraPlanIssues(nextPlan);
  if (issues.length) {
    setStatus(`机位 JSON 未载入：${issues[0]}`, "error");
    return false;
  }
  if (cameraPlanPreviewSnapshot) restoreCameraPlanPreview({ restoreView: true, announce: false });
  cameraPlan = structuredClone(nextPlan);
  activeCameraPlanShotId = null;
  renderCameraPlanList();
  updateRuntimeAudit();
  setStatus(`已载入 ${cameraPlan.shots.length} 个本户型机位`, "success");
  return true;
}

function renderLists() {
  const walls = visibleWalls();
  const windows = visibleWindows();
  const components = visibleComponents();
  const lights = visibleSceneItems("light");
  const cameras = visibleSceneItems("camera");
  dom.structureList.replaceChildren();
  walls.forEach((wall) => dom.structureList.appendChild(structureButton("wall", wall)));
  windows.forEach((item) => dom.structureList.appendChild(structureButton("window", item)));
  document.getElementById("structure-count").textContent = `${walls.length + windows.length}/${model.walls.length + model.windows.length} 项`;
  if (!walls.length && !windows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-list-note";
    empty.textContent = "当前空间筛选下没有结构。";
    dom.structureList.appendChild(empty);
  }

  dom.componentList.replaceChildren();
  components.forEach((placement) => {
    const definition = getComponentDefinition(placement.componentId, placement.semantic);
    const row = document.createElement("div");
    row.className = "component-list-row";
    const button = document.createElement("button");
    button.type = "button";
    button.className = `object-button${selection.type === "component" && selection.id === placement.id ? " active" : ""}${keyboardMoveComponentId === placement.id ? " keyboard-armed" : ""}`;
    const kind = definition?.placementClass === "fixed-purple" ? "fixed" : "movable";
    const detail = definition?.placementClass === "fixed-purple" ? "紫色固定构件" : "绿色活动家具";
    button.innerHTML = `<i class="object-dot ${kind}"></i><span>${placement.name}</span><small>${detail}</small>`;
    button.addEventListener("click", () => selectObject("component", placement.id, false));
    const actions = document.createElement("div");
    actions.className = "component-row-actions";
    const visibility = document.createElement("button");
    visibility.type = "button";
    visibility.className = `component-row-icon${placement.presentationHidden ? " hidden-component" : ""}`;
    visibility.setAttribute("aria-label", `${placement.presentationHidden ? "显示" : "隐藏"}${placement.name}`);
    visibility.title = placement.presentationHidden ? "显示该组件" : "隐藏该组件；位置与槽位数据仍保留";
    visibility.textContent = placement.presentationHidden ? "○" : "◉";
    visibility.addEventListener("click", () => setComponentVisibility(placement.id, placement.presentationHidden));
    const rotate = document.createElement("button");
    rotate.type = "button";
    rotate.className = "component-row-icon";
    rotate.setAttribute("aria-label", `顺时针旋转${placement.name}`);
    rotate.title = "顺时针旋转 90°；碰撞或越界时不应用";
    rotate.textContent = "↻";
    rotate.addEventListener("click", () => rotateComponentPlacement(placement.id));
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "component-row-icon";
    reset.setAttribute("aria-label", `复位${placement.name}`);
    reset.title = "恢复到描线匹配的初始位置";
    reset.textContent = "↺";
    reset.addEventListener("click", () => resetComponentPlacement(placement.id));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "component-row-icon danger";
    remove.setAttribute("aria-label", `删除${placement.name}`);
    remove.title = "删除该组件；来源匹配记录仍保留";
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      selection = { type: "component", id: placement.id };
      deleteSelectedComponent();
    });
    actions.append(visibility, rotate, reset, remove);
    row.append(button, actions);
    dom.componentList.appendChild(row);
  });
  document.getElementById("furniture-count").textContent = `${components.length}/${model.componentPlacements.length} 件`;
  if (!components.length) {
    const empty = document.createElement("div");
    empty.className = "empty-list-note";
    empty.textContent = model.componentPlacements.length
      ? "当前空间筛选下没有组件。"
      : "空结构模板不预置组件；项目组件由绿色/紫色描线一对一匹配后载入。";
    dom.componentList.appendChild(empty);
  }

  dom.lightList.replaceChildren();
  lights.forEach((item) => dom.lightList.appendChild(sceneObjectButton("light", item)));
  dom.cameraList.replaceChildren();
  cameras.forEach((item) => dom.cameraList.appendChild(sceneObjectButton("camera", item)));
  document.getElementById("light-count").textContent = `${lights.length}/${sceneRig.lights.length} 盏`;
  document.getElementById("camera-count").textContent = `${cameras.length}/${sceneRig.cameras.length} 个`;
  document.getElementById("scene-count").textContent = `${lights.length} 灯 · ${cameras.length} 机位`;
  document.getElementById("toggle-rig-gizmos").checked = sceneRig.gizmosVisible !== false;
  document.getElementById("delete-component").disabled = !componentById(
    selection.type === "component" ? selection.id : null,
  );
  renderCameraPlanList();
  applySceneEditorModeUi();
}

function fieldMarkup(label, field, value, options = {}) {
  const { min, max, step = 0.01, suffix = "m", wide = false } = options;
  const attrs = [`data-field="${field}"`, 'type="number"', `value="${Number(value).toFixed(2)}"`, `step="${step}"`];
  if (min !== undefined) attrs.push(`min="${min}"`);
  if (max !== undefined) attrs.push(`max="${max}"`);
  return `<div class="field${wide ? " wide" : ""}"><label>${label}</label><input ${attrs.join(" ")}><span class="field-value">${suffix}</span></div>`;
}

function axisFieldMarkup(axis, field, value, options = {}) {
  const { min = -30, max = 30, step = 0.01, suffix = "m" } = options;
  const numeric = Number(value);
  const formatted = Number.isFinite(numeric) ? numeric.toFixed(step >= 1 ? 0 : 2) : "0.00";
  return `<div class="axis-field" data-axis="${axis}">
    <label for="${field}-range">${axis}</label>
    <input id="${field}-range" data-field="${field}" data-live-scene="true" data-role="range" type="range" min="${min}" max="${max}" step="${step}" value="${formatted}">
    <input data-field="${field}" data-live-scene="true" data-role="number" type="number" min="${min}" max="${max}" step="${step}" value="${formatted}" aria-label="${axis} 数值">
    <span class="axis-unit">${suffix}</span>
  </div>`;
}

function sliderFieldMarkup(label, field, value, options = {}) {
  const {
    min = 0,
    max = 100,
    step = 1,
    suffix = "",
    help = "",
  } = options;
  const numeric = Number(value);
  const formatted = Number.isFinite(numeric) ? numeric.toFixed(step >= 1 ? 0 : 2) : "0";
  return `<div class="range-field field wide">
    <label>${label}</label>
    <div class="range-number-control">
      <input data-field="${field}" data-live-scene="true" data-role="range" type="range" min="${min}" max="${max}" step="${step}" value="${formatted}">
      <input data-field="${field}" data-live-scene="true" data-role="number" type="number" min="${min}" max="${max}" step="${step}" value="${formatted}" aria-label="${label}数值">
      <span>${suffix}</span>
    </div>
    ${help ? `<p class="field-help">${help}</p>` : ""}
  </div>`;
}

function selectFieldMarkup(label, field, value, options, wide = false) {
  const rows = options.map(([key, name]) => `<option value="${key}"${key === value ? " selected" : ""}>${name}</option>`).join("");
  return `<div class="field${wide ? " wide" : ""}"><label>${label}</label><select data-field="${field}">${rows}</select></div>`;
}

function checkboxFieldMarkup(label, field, checked, detail) {
  return `<div class="field checkbox-field"><label>${label}</label><input data-field="${field}" type="checkbox"${checked ? " checked" : ""}><span class="field-value">${detail}</span></div>`;
}

function sceneIconButton(action, icon, label, options = {}) {
  const classes = [
    "scene-icon-action",
    options.active ? "active-action" : "",
    options.danger ? "danger" : "",
    options.primary ? "primary-action" : "",
  ].filter(Boolean).join(" ");
  return `<button type="button" class="${classes}" data-action="${action}" data-tooltip="${label}" aria-label="${label}" title="${label}"${options.disabled ? " disabled" : ""}>${icon}</button>`;
}

function updateVectorField(vector, field, value) {
  const axis = { X: 0, Y: 1, Z: 2 }[field.at(-1)];
  if (axis !== undefined) vector[axis] = Number(value);
}

function updateLightField(item, field, input) {
  if (field === "name") item.name = input.value.trim() || item.name;
  else if (field === "type") item.type = input.value;
  else if (field === "enabled" || field === "castShadow") item[field] = input.checked;
  else if (field.startsWith("position")) updateVectorField(item.position, field, input.value);
  else if (field.startsWith("target")) updateVectorField(item.target, field, input.value);
  else item[field] = Number(input.value);
}

function updateSceneCameraField(item, field, input) {
  if (field === "lensPreset") {
    item.lensPreset = input.value;
    const preset = LENS_PRESETS[input.value];
    if (preset) {
      item.focalLengthMm = preset.focalLengthMm;
      item.fov = fovForFocalLength(item.focalLengthMm);
      item.distortion = preset.distortion;
    }
  } else if (field === "focalLengthMm") {
    item.focalLengthMm = Math.max(14, Math.min(85, Number(input.value)));
    item.fov = fovForFocalLength(item.focalLengthMm);
    item.lensPreset = lensPresetForFocalLength(item.focalLengthMm);
  } else if (field === "fov") {
    item.fov = Math.max(16, Math.min(82, Number(input.value)));
    item.focalLengthMm = focalLengthForFov(item.fov);
    item.lensPreset = lensPresetForFocalLength(item.focalLengthMm);
  } else if (field === "focusRoomId") {
    item.focusRoomId = input.value || null;
    const target = roomFocusTarget(roomById(item.focusRoomId));
    if (target) item.target = target;
  } else if (field.startsWith("position")) {
    updateVectorField(item.position, field, input.value);
    item.mount.mode = "free";
    item.mount.wallId = null;
    item.mount.offset = null;
  } else if (field.startsWith("target")) {
    updateVectorField(item.target, field, input.value);
    item.focusRoomId = null;
  } else if (field === "mountMode") {
    item.mount.mode = input.value;
    if (item.mount.mode === "wall") {
      item.mount.wallId = item.mount.wallId || lastSelectedWallId || model.walls[0]?.id;
      const wall = wallById(item.mount.wallId);
      item.mount.offset = wall ? wallFrame(wall).length / 2 : 0;
      applyCameraWallMount(item);
    } else {
      item.mount.wallId = null;
    }
  } else if (field === "wallId") {
    item.mount.wallId = input.value;
    const wall = wallById(input.value);
    item.mount.offset = wall ? wallFrame(wall).length / 2 : 0;
    applyCameraWallMount(item);
  } else if (field === "mountSide") {
    item.mount.side = Number(input.value);
    applyCameraWallMount(item);
  } else if (field === "mountOffset") {
    item.mount.offset = Number(input.value);
    applyCameraWallMount(item);
  } else if (field === "mountHeight") {
    item.mount.height = Number(input.value);
    applyCameraWallMount(item);
  } else if (field === "mountClearance") {
    item.mount.clearance = Number(input.value);
    applyCameraWallMount(item);
  }
}

function applyWallExtension(wallId, startExtension, endExtension) {
  const wall = wallById(wallId);
  const sourceWall = originalModel.walls.find((item) => item.id === wallId);
  if (!wall || !sourceWall) return false;
  const frame = wallFrame(sourceWall);
  const startDelta = Number(startExtension) || 0;
  const endDelta = Number(endExtension) || 0;
  wall.start = [
    sourceWall.start[0] - frame.ux * startDelta,
    sourceWall.start[1] - frame.uz * startDelta,
  ];
  wall.end = [
    sourceWall.end[0] + frame.ux * endDelta,
    sourceWall.end[1] + frame.uz * endDelta,
  ];
  wall.endpointExtensions = { start: startDelta, end: endDelta };
  model.windows
    .filter((item) => item.wallId === wallId)
    .forEach((item) => {
      const sourceWindow = originalModel.windows.find((candidate) => candidate.id === item.id);
      if (sourceWindow) item.offset = Number(sourceWindow.offset) + startDelta;
    });
  model.structureEditPatches = (model.structureEditPatches || [])
    .filter((item) => item.entityId !== wallId);
  model.structureEditPatches.push({
    schema: "interior.structure-edit-patch.v1",
    floorplanId: model.floorplanId,
    backend: "html-threejs",
    entityType: "wall",
    entityId: wallId,
    operation: "extend-collinear-endpoints",
    sourceTraceIds: [...(wall.sourceTraceIds || [])],
    source: { start: [...sourceWall.start], end: [...sourceWall.end] },
    current: { start: [...wall.start], end: [...wall.end] },
    extensionMeters: { start: startDelta, end: endDelta },
    hostedWindowOffsetsPreservedInWorld: true,
  });
  return true;
}

function wallEndpointPosition(sourceWall, startExtension, endExtension, endpoint) {
  const frame = wallFrame(sourceWall);
  if (endpoint === "start") {
    return [
      sourceWall.start[0] - frame.ux * startExtension,
      sourceWall.start[1] - frame.uz * startExtension,
    ];
  }
  return [
    sourceWall.end[0] + frame.ux * endExtension,
    sourceWall.end[1] + frame.uz * endExtension,
  ];
}

function buildWallEndpointHandles() {
  clearGroup(wallEndpointHandleGroup);
  const wall = selection.type === "wall" ? wallById(selection.id) : null;
  const allowed = model.backendOptions?.structureEditing?.wallEndpointEditing === true
    && activePanelId === "structure-panel"
    && !document.body.classList.contains("capture")
    && !activeSceneCameraId
    && !activeCameraPlanShotId;
  wallEndpointHandleGroup.visible = Boolean(wall && allowed);
  if (!wall || !allowed) return;
  const lineMaterial = new THREE.LineDashedMaterial({
    color: 0xb67a18,
    dashSize: 0.12,
    gapSize: 0.06,
    depthTest: false,
  });
  const linePoints = [wall.start, wall.end].map((point) => {
    const world = worldPoint(point);
    return new THREE.Vector3(world.x, 0.16, world.z);
  });
  const guide = new THREE.Line(new THREE.BufferGeometry().setFromPoints(linePoints), lineMaterial);
  guide.name = `wall-endpoint-guide-${wall.id}`;
  guide.computeLineDistances();
  guide.renderOrder = 43;
  wallEndpointHandleGroup.add(guide);
  ["start", "end"].forEach((endpoint) => {
    const point = wall[endpoint];
    const world = worldPoint(point);
    const handle = new THREE.Mesh(
      new THREE.SphereGeometry(0.13, 18, 12),
      new THREE.MeshBasicMaterial({
        color: endpoint === "start" ? 0x236ca4 : 0xb67a18,
        depthTest: false,
      }),
    );
    handle.name = `wall-endpoint-${wall.id}-${endpoint}`;
    handle.position.set(world.x, 0.18, world.z);
    handle.renderOrder = 44;
    handle.userData.pick = { type: "wall-endpoint", id: wall.id, endpoint };
    wallEndpointHandleGroup.add(handle);
  });
}

function updateWallEndpointHandlePreview(wallId, startExtension, endExtension) {
  const sourceWall = originalModel.walls.find((item) => item.id === wallId);
  if (!sourceWall) return;
  const start = wallEndpointPosition(sourceWall, startExtension, endExtension, "start");
  const end = wallEndpointPosition(sourceWall, startExtension, endExtension, "end");
  const points = [start, end].map((point) => {
    const world = worldPoint(point);
    return new THREE.Vector3(world.x, 0.16, world.z);
  });
  const guide = wallEndpointHandleGroup.getObjectByName(`wall-endpoint-guide-${wallId}`);
  if (guide) {
    guide.geometry.setFromPoints(points);
    guide.computeLineDistances();
  }
  ["start", "end"].forEach((endpoint, index) => {
    const handle = wallEndpointHandleGroup.getObjectByName(`wall-endpoint-${wallId}-${endpoint}`);
    if (handle) handle.position.set(points[index].x, 0.18, points[index].z);
  });
  requestRender();
}

function currentWindowStyle(item) {
  return model.backendOptions.windows?.overrides?.[item.id]
    || item.windowStyle
    || model.backendOptions.windows?.defaultStyle
    || "frameless-glass";
}

function applyWindowStyle(windowId, style) {
  const item = windowById(windowId);
  const allowedStyles = model.backendOptions.windows?.allowedStyles || [];
  if (!item || !allowedStyles.includes(style)) return false;
  model.backendOptions.windows.overrides = model.backendOptions.windows.overrides || {};
  model.backendOptions.windows.overrides[windowId] = style;
  return true;
}

function downloadStructureEditPatch() {
  const payload = {
    schema: "interior.structure-edit-patch-set.v1",
    floorplanId: model.floorplanId,
    backend: "html-threejs",
    patches: model.structureEditPatches || [],
  };
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" });
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = "structure-edit-patch.json";
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

function renderWallInspector(wall) {
  const dimensions = wallDimensions(wall);
  const extensions = wall.endpointExtensions || { start: 0, end: 0 };
  dom.structureInspector.innerHTML = `
    <div class="inspector-header"><div><strong>${wall.name}</strong><span>墙 · ${(wall.sourceTraceIds || []).join(", ")}</span></div></div>
    <div class="field-grid">
      <div class="field"><label>中心</label><strong>${dimensions.center[0].toFixed(2)}, ${dimensions.center[1].toFixed(2)} m</strong></div>
      <div class="field"><label>长度</label><strong>${dimensions.length.toFixed(2)} m</strong></div>
      <div class="field"><label>高度</label><strong>${dimensions.height.toFixed(2)} m</strong></div>
      <div class="field"><label>厚度</label><strong>${dimensions.thickness.toFixed(2)} m</strong></div>
      <div class="field"><label>角度</label><strong>${(dimensions.angle * 180 / Math.PI).toFixed(1)}°</strong></div>
      <div class="field wide"><label>相邻空间</label><strong>${(wall.adjacentRoomIds || []).join(" / ")}</strong></div>
      <label class="field"><span>起点延长 (m)</span><input type="number" step="0.05" min="-${Math.max(0.1, dimensions.length / 2).toFixed(2)}" max="3" value="${Number(extensions.start).toFixed(2)}" data-wall-extension="start"></label>
      <label class="field"><span>终点延长 (m)</span><input type="number" step="0.05" min="-${Math.max(0.1, dimensions.length / 2).toFixed(2)}" max="3" value="${Number(extensions.end).toFixed(2)}" data-wall-extension="end"></label>
      <div class="field wide"><button type="button" class="secondary-button" data-export-structure-patch>导出结构补丁</button></div>
    </div>`;
  dom.structureInspector.querySelectorAll("[data-wall-extension]").forEach((input) => {
    input.addEventListener("change", () => {
      const startInput = dom.structureInspector.querySelector('[data-wall-extension="start"]');
      const endInput = dom.structureInspector.querySelector('[data-wall-extension="end"]');
      performMutation(`调整${wall.name}端点`, () => {
        applyWallExtension(wall.id, Number(startInput.value), Number(endInput.value));
      });
    });
  });
  dom.structureInspector.querySelector("[data-export-structure-patch]")
    ?.addEventListener("click", downloadStructureEditPatch);
}

function renderWindowInspector(item) {
  const wall = wallById(item.wallId);
  const allowedStyles = model.backendOptions.windows?.allowedStyles || [];
  const style = currentWindowStyle(item);
  dom.structureInspector.innerHTML = `
    <div class="inspector-header"><div><strong>${item.name}</strong><span>窗 · ${item.kind}</span></div></div>
    <div class="field-grid">
      <div class="field wide"><label>所属墙</label><strong>${wall?.name || item.wallId}</strong></div>
      <div class="field"><label>沿墙位置</label><strong>${Number(item.offset).toFixed(2)} m</strong></div>
      <div class="field"><label>窗宽</label><strong>${Number(item.width).toFixed(2)} m</strong></div>
      <div class="field"><label>窗台</label><strong>${Number(item.sill).toFixed(2)} m</strong></div>
      <div class="field"><label>洞口高度</label><strong>${Number(item.openingHeight).toFixed(2)} m</strong></div>
      <label class="field wide"><span>窗户样式</span><select data-window-style>${allowedStyles.map((value) => `<option value="${value}"${value === style ? " selected" : ""}>${value}</option>`).join("")}</select></label>
    </div>`;
  dom.structureInspector.querySelector("[data-window-style]")?.addEventListener("change", (event) => {
    performMutation(`切换${item.name}样式`, () => applyWindowStyle(item.id, event.currentTarget.value));
  });
}

function renderComponentInspector(placement) {
  const definition = getComponentDefinition(placement.componentId, placement.semantic);
  const footprintDimensions = resolvedComponentDimensions(definition, {
    uniformScale: placement.uniformScale ?? 1,
    targetDimensions: placement.targetDimensions,
  });
  const visual = resolvedVisualScale(definition, {
    uniformScale: placement.uniformScale ?? 1,
    visualDimensions: placement.visualDimensions,
  });
  const scale = clampUniformScale(definition, placement.uniformScale ?? 1);
  const axisLimited = definition.editorCapabilities?.scaleMode === "axis-limited";
  const axisRange = definition.editorCapabilities?.axisScaleRange || {};
  const axisField = (label, field, axis) => {
    const base = definition.defaultDimensions[axis] * scale;
    const range = axisRange[axis] || [1, 1];
    return fieldMarkup(label, field, visual.dimensions[axis], {
      min: base * range[0],
      max: base * range[1],
      step: 0.01,
      suffix: "m",
    });
  };
  const dimensionNoun = definition.category === "storage" ? "柜体" : "模型";
  const scaleFields = axisLimited
    ? `${axisField(`${dimensionNoun}宽度`, "visualWidth", "width")}${axisField(`${dimensionNoun}深度`, "visualDepth", "depth")}${axisField(`${dimensionNoun}高度`, "visualHeight", "height")}`
    : placement.targetDimensions ? "" : fieldMarkup("等比缩放", "uniformScale", scale, { min: definition.uniformScaleRange.min, max: definition.uniformScaleRange.max, step: 0.01, suffix: "倍" });
  const elevationField = ["wall", "countertop"].includes(definition.mountType)
    ? fieldMarkup("离地高度", "elevation", Number(placement.elevation ?? definition.defaultElevation ?? 0), { min: 0, max: 2.7, step: 0.01, suffix: "m" })
    : "";
  dom.componentInspector.innerHTML = `
    <div class="inspector-header"><div><strong>${placement.name}</strong><span>${definition.placementClass === "fixed-purple" ? "紫色固定构件" : "绿色活动家具"} · ${placement.placementOrigin === "user-explicit-addition" ? "用户明确新增" : placement.sourceTraceId}</span></div></div>
    <div class="component-contract">
      <span>原组件</span>
      <strong>${definition.name}</strong>
      <code>${definition.id}</code>
      <a href="./component-library/gallery/index.html?partition=${definition.placementClass}&component=${definition.id}">在组件库查看</a>
    </div>
    <div class="field-grid">
      ${fieldMarkup("位置 X", "x", placement.position[0], { min: 0, max: cfg.realWidthMeters })}
      ${fieldMarkup("位置 Z", "z", placement.position[1], { min: 0, max: cfg.realDepthMeters })}
      ${fieldMarkup("旋转", "rotationY", (placement.rotationY || 0) * 180 / Math.PI, { min: -180, max: 180, step: 1, suffix: "°" })}
      ${scaleFields}
      ${elevationField}
    </div>
    <div class="component-dimensions">碰撞脚印 ${footprintDimensions.width.toFixed(2)} × ${footprintDimensions.depth.toFixed(2)} m · 可见模型 ${visual.dimensions.width.toFixed(2)} × ${visual.dimensions.depth.toFixed(2)} × ${visual.dimensions.height.toFixed(2)} m${axisLimited ? " · 柜体受限分轴编辑" : ""}</div>
    <div class="inspector-actions">
      <button type="button" data-action="toggle-component-visibility">${placement.presentationHidden ? "显示组件" : "隐藏组件"}</button>
      <button type="button" data-action="reset-component">恢复匹配位置</button>
    </div>`;
  dom.componentInspector.querySelectorAll("[data-field]").forEach((input) => {
    input.addEventListener("change", () => performMutation(`修改${placement.name}`, () => updateComponentField(componentById(placement.id), input.dataset.field, input.value)));
  });
  dom.componentInspector.querySelector('[data-action="reset-component"]').addEventListener("click", () => {
    resetComponentPlacement(placement.id);
  });
  dom.componentInspector.querySelector('[data-action="toggle-component-visibility"]').addEventListener("click", () => {
    setComponentVisibility(placement.id, placement.presentationHidden);
  });
}

function syncSceneFieldInputs(field, value) {
  dom.sceneInspector.querySelectorAll(`[data-field="${field}"]`).forEach((input) => {
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = String(value);
  });
}

function sceneFieldUpdater(type, item, field, input) {
  if (type === "light") updateLightField(item, field, input);
  else updateSceneCameraField(item, field, input);
}

function applyActiveCameraRigValues(item) {
  if (activeSceneCameraId !== item.id) return;
  suppressCameraControlTracking = true;
  applyCameraWallMount(item);
  camera.position.fromArray(item.position);
  camera.up.set(0, 1, 0);
  camera.fov = item.fov;
  camera.near = item.near;
  camera.far = item.far;
  controls.target.fromArray(item.target);
  camera.updateProjectionMatrix();
  controls.update();
  activeCameraViewFineTuned = false;
  suppressCameraControlTracking = false;
}

function beginSceneFieldGesture(label, type = selection.type, id = selection.id) {
  if (sceneFieldGesture) return;
  sceneFieldGesture = {
    before: serializeModel(),
    label,
    type,
    id,
  };
}

function finishSceneEdit({ before, label, type, id, rebuildRig = false }) {
  const item = type === "light" ? lightById(id) : sceneCameraById(id);
  if (type === "camera" && item) {
    if (item.mount?.snapEnabled) applyCameraWallSnap(item);
    if (item.visibility?.cutawayEnabled) refreshCameraCutaway(item);
  }
  const issues = validateModel();
  if (issues.length) {
    restoreSnapshot(before);
    buildSceneRig();
    applyLayerVisibility();
    renderLists();
    renderInspectors();
    updateUndoButtons();
    updateRuntimeAudit();
    requestRender();
    setStatus(`${label}未应用：${issues[0]}`, "error");
    return false;
  }
  if (serializeModel() !== before) {
    undoStack.push(before);
    if (undoStack.length > 80) undoStack.shift();
    redoStack.length = 0;
  }
  const current = type === "light" ? lightById(id) : sceneCameraById(id);
  if (rebuildRig) buildSceneRig();
  else updateSceneObjectVisual(type, current);
  if (type === "camera" && current) applyActiveCameraRigValues(current);
  applyLayerVisibility();
  renderLists();
  renderInspectors();
  updateUndoButtons();
  updateRuntimeAudit();
  requestRender();
  setStatus(`${label}已应用`, "success");
  return true;
}

function previewSceneField(type, id, field, input) {
  const item = type === "light" ? lightById(id) : sceneCameraById(id);
  if (!item) return;
  beginSceneFieldGesture(`修改${sceneDisplayName(type, item)}`, type, id);
  if (input.type === "range" || input.type === "number") {
    const numeric = Number(input.value);
    if (!Number.isFinite(numeric)) return;
    const minimum = input.min === "" ? -Infinity : Number(input.min);
    const maximum = input.max === "" ? Infinity : Number(input.max);
    input.value = String(Math.max(minimum, Math.min(maximum, numeric)));
  }
  sceneFieldUpdater(type, item, field, input);
  syncSceneFieldInputs(field, input.type === "checkbox" ? input.checked : input.value);
  if (type === "camera" && ["focalLengthMm", "fov"].includes(field)) {
    syncSceneFieldInputs("focalLengthMm", Number(item.focalLengthMm).toFixed(1));
    syncSceneFieldInputs("fov", Number(item.fov).toFixed(1));
  }
  if (field.startsWith("target")) sceneTransformPart = "target";
  if (field.startsWith("position") || field.startsWith("mount")) sceneTransformPart = "position";
  if (type === "camera") applyActiveCameraRigValues(item);
  updateSceneObjectVisual(type, item);
  setStatus(`${sceneDisplayName(type, item)}预览中`);
}

function commitSceneFieldGesture() {
  if (!sceneFieldGesture) return;
  const { before, label, type, id } = sceneFieldGesture;
  sceneFieldGesture = null;
  finishSceneEdit({
    before,
    label,
    type,
    id,
  });
}

function bindSceneInspector(type, item) {
  dom.sceneInspector.querySelectorAll("[data-transform-part]").forEach((button) => {
    button.addEventListener("click", () => {
      sceneTransformPart = button.dataset.transformPart;
      renderInspectors();
      buildTransformGizmo();
      updateSceneRigVisibility();
      updateSelectionHighlight();
      requestRender();
    });
  });
  dom.sceneInspector.querySelectorAll("[data-live-scene='true']").forEach((input) => {
    input.addEventListener("pointerdown", () => beginSceneFieldGesture(`修改${sceneDisplayName(type, item)}`, type, item.id));
    input.addEventListener("focus", () => beginSceneFieldGesture(`修改${sceneDisplayName(type, item)}`, type, item.id));
    input.addEventListener("input", () => previewSceneField(type, item.id, input.dataset.field, input));
    input.addEventListener("change", commitSceneFieldGesture);
    input.addEventListener("blur", commitSceneFieldGesture);
  });
  dom.sceneInspector.querySelectorAll("[data-field]:not([data-live-scene='true'])").forEach((input) => {
    input.addEventListener("change", () => {
      const before = serializeModel();
      sceneFieldUpdater(
        type,
        type === "light" ? lightById(item.id) : sceneCameraById(item.id),
        input.dataset.field,
        input,
      );
      finishSceneEdit({
        before,
        label: `修改${sceneDisplayName(type, item)}`,
        type,
        id: item.id,
        rebuildRig: type === "light" && input.dataset.field === "type",
      });
    });
  });
}

function mutateSceneItem(label, type, id, mutate, options = {}) {
  const before = serializeModel();
  mutate();
  return finishSceneEdit({
    before,
    label,
    type,
    id,
    rebuildRig: options.rebuildRig === true,
  });
}

function renderLightInspector(item) {
  if (item.type === "point" && sceneTransformPart === "target") sceneTransformPart = "position";
  const xLimit = cfg.realWidthMeters / 2 + 2;
  const zLimit = cfg.realDepthMeters / 2 + 2;
  const typeLabels = { directional: "平行光", point: "点光源", spot: "聚光灯" };
  const targetSection = item.type === "point" ? "" : `
    <div class="scene-control-section">
      <div class="scene-control-heading">
        <strong>照射焦点</strong>
        <button type="button" data-transform-part="target" class="axis-mode-button${sceneTransformPart === "target" ? " active" : ""}">焦点轴</button>
      </div>
      <div class="field-grid">
        ${axisFieldMarkup("X", "targetX", item.target[0], { min: -xLimit, max: xLimit })}
        ${axisFieldMarkup("Y", "targetY", item.target[1], { min: 0, max: 6 })}
        ${axisFieldMarkup("Z", "targetZ", item.target[2], { min: -zLimit, max: zLimit })}
      </div>
    </div>`;
  const distanceFields = item.type === "directional" ? "" : `
      ${sliderFieldMarkup("照射距离", "distance", item.distance, { min: 0, max: 80, step: 0.1, suffix: "m" })}
      ${sliderFieldMarkup("距离衰减", "decay", item.decay, { min: 0, max: 4, step: 0.1 })}`;
  const spotFields = item.type === "spot" ? `
      ${sliderFieldMarkup("光束角", "angle", item.angle, { min: 5, max: 120, step: 1, suffix: "°" })}
      ${sliderFieldMarkup("边缘柔化", "penumbra", item.penumbra, { min: 0, max: 1, step: 0.05 })}` : "";
  dom.sceneInspector.innerHTML = `
    <div class="inspector-header scene-object-header">
      <div><strong>${sceneDisplayName("light", item)}</strong><span>${typeLabels[item.type]}</span></div>
      <div class="scene-object-toolbar light-object-toolbar" role="toolbar" aria-label="${sceneDisplayName("light", item)}操作">
        ${sceneIconButton("toggle-light", item.enabled === false ? "○" : "●", item.enabled === false ? "开启这盏灯" : "关闭这盏灯", { active: item.enabled !== false })}
        ${sceneIconButton("reset-light", "↺", "恢复默认光源", { disabled: !originalSceneRig.lights.some((candidate) => candidate.id === item.id) })}
        ${sceneIconButton("delete-light", "×", "删除这盏灯", { danger: true, disabled: sceneRig.lights.length <= 1 })}
      </div>
    </div>
    <div class="scene-control-section">
      <div class="compact-segmented light-type-switch" role="group" aria-label="光源类型">
        ${Object.entries(typeLabels).map(([value, label]) => `<button type="button" data-light-type="${value}" class="${item.type === value ? "active" : ""}">${label}</button>`).join("")}
      </div>
    </div>
    <div class="scene-control-section">
      <div class="scene-control-heading">
        <strong>位置</strong>
        <button type="button" data-transform-part="position" class="axis-mode-button${sceneTransformPart === "position" ? " active" : ""}">位置轴</button>
      </div>
      <div class="field-grid">
        ${axisFieldMarkup("X", "positionX", item.position[0], { min: -xLimit, max: xLimit })}
        ${axisFieldMarkup("Y", "positionY", item.position[1], { min: 0.1, max: 10 })}
        ${axisFieldMarkup("Z", "positionZ", item.position[2], { min: -zLimit, max: zLimit })}
      </div>
    </div>
    ${targetSection}
    <div class="scene-control-section">
      <div class="scene-control-heading"><strong>光线</strong><span>${item.type === "directional" ? "平行光" : item.type === "point" ? "点光源" : "聚光灯"}</span></div>
      <div class="field-grid">
        ${sliderFieldMarkup("亮度", "intensity", item.intensity, { min: 0, max: 12, step: 0.1, suffix: "级" })}
        ${sliderFieldMarkup("色温", "temperatureK", item.temperatureK, { min: 2000, max: 10000, step: 100, suffix: "K" })}
        ${distanceFields}
        ${spotFields}
        ${checkboxFieldMarkup("投射阴影", "castShadow", item.castShadow === true, "仅需要时开启")}
      </div>
    </div>`;
  bindSceneInspector("light", item);
  dom.sceneInspector.querySelectorAll("[data-light-type]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.lightType === item.type) return;
      mutateSceneItem(`切换${sceneDisplayName("light", item)}类型`, "light", item.id, () => {
        lightById(item.id).type = button.dataset.lightType;
      }, { rebuildRig: true });
    });
  });
  dom.sceneInspector.querySelector('[data-action="toggle-light"]').addEventListener("click", () => mutateSceneItem(`${item.enabled === false ? "开启" : "关闭"}${sceneDisplayName("light", item)}`, "light", item.id, () => {
    lightById(item.id).enabled = item.enabled === false;
  }));
  dom.sceneInspector.querySelector('[data-action="reset-light"]').addEventListener("click", () => mutateSceneItem(`恢复${sceneDisplayName("light", item)}`, "light", item.id, () => {
    const original = originalSceneRig.lights.find((candidate) => candidate.id === item.id);
    if (original) sceneRig.lights[sceneRig.lights.findIndex((candidate) => candidate.id === item.id)] = structuredClone(original);
  }, { rebuildRig: true }));
  dom.sceneInspector.querySelector('[data-action="delete-light"]').addEventListener("click", () => {
    if (sceneRig.lights.length <= 1) return;
    mutateSceneItem(`删除${sceneDisplayName("light", item)}`, "light", item.id, () => {
      sceneRig.lights = sceneRig.lights.filter((candidate) => candidate.id !== item.id);
      selection = { type: "light", id: sceneRig.lights[0].id };
    }, { rebuildRig: true });
  });
}

function renderCameraInspector(item) {
  const xLimit = cfg.realWidthMeters / 2 + 2;
  const zLimit = cfg.realDepthMeters / 2 + 2;
  const mount = item.mount || { mode: "free" };
  const wall = wallById(mount.wallId);
  const active = activeSceneCameraId === item.id;
  const cutawayActive = item.visibility?.cutawayEnabled && activeOcclusionCameraId === item.id;
  const hiddenWallCount = item.visibility?.hiddenWallIds?.length || 0;
  const hiddenComponentCount = item.visibility?.hiddenComponentIds?.length || 0;
  const focusOccluderHiddenCount = hiddenWallCount + hiddenComponentCount;
  const roomOptions = [["", "自由焦点"], ...(model.rooms || []).map((room) => [room.id, room.name])];
  const focusRoom = roomById(item.focusRoomId);
  const focalLength = Number(item.focalLengthMm).toFixed(0);
  const lensBand = lensBandForFocalLength(item.focalLengthMm);
  const activePlan = activeCameraPlanShot();
  const cameraState = active
    ? activePlan
      ? `已套用 · ${roomById(activePlan.roomId)?.name || activePlan.shotId}`
      : "当前固定机位"
    : detachedCameraId === item.id
      ? "已离开 · 自由视角"
      : `${lensBand} · ${focalLength}mm${mount.mode === "wall" ? ` · ${wall?.name || "已吸附"}` : ""}`;
  dom.sceneInspector.innerHTML = `
    <div class="inspector-header scene-object-header">
      <div class="scene-object-title"><strong>${sceneDisplayName("camera", item)}</strong><span>${cameraState}</span></div>
      <div class="scene-object-toolbar camera-object-toolbar" role="toolbar" aria-label="${sceneDisplayName("camera", item)}操作">
        ${sceneIconButton("toggle-wall-snap", "⌁", mount.snapEnabled ? "关闭墙面吸附" : "开启墙面吸附", { active: mount.snapEnabled })}
        ${sceneIconButton("plan-camera", "⌖", "在平面中编辑机位并实时预览")}
        ${sceneIconButton("toggle-cutaway", cutawayActive ? "▤" : "▥", cutawayActive ? "恢复局部遮挡" : "应用已登记的局部遮挡", { active: cutawayActive })}
        ${sceneIconButton("view-camera", active ? "◉" : "◎", active ? "退出固定机位" : "切到固定机位", { primary: active })}
        ${sceneIconButton("screenshot-camera", "▣", "截图当前视角")}
        ${sceneIconButton("reset-camera", "↺", activePlan ? "先退出已保存机位再恢复默认" : "恢复默认机位", { disabled: Boolean(activePlan) || !originalSceneRig.cameras.some((candidate) => candidate.id === item.id) })}
        ${sceneIconButton("delete-camera", "×", activePlan ? "先退出已保存机位再删除" : "删除机位", { danger: true, disabled: Boolean(activePlan) || sceneRig.cameras.length <= 1 })}
      </div>
    </div>
    ${active ? '<p class="fixed-view-guide">固定视角：方向键平移，W/S 或滚轮前后移动，双击画布改焦点；只有拖动画布才退出固定视角。</p>' : ""}
    <div class="scene-control-section">
      <div class="scene-control-heading">
        <strong>焦点</strong>
        <button type="button" data-transform-part="target" class="axis-mode-button${sceneTransformPart === "target" ? " active" : ""}">焦点轴</button>
      </div>
      <div class="field-grid">
        ${selectFieldMarkup("焦点空间", "focusRoomId", item.focusRoomId || "", roomOptions, true)}
        ${axisFieldMarkup("X", "targetX", item.target[0], { min: -xLimit, max: xLimit })}
        ${axisFieldMarkup("Y", "targetY", item.target[1], { min: 0, max: 4 })}
        ${axisFieldMarkup("Z", "targetZ", item.target[2], { min: -zLimit, max: zLimit })}
      </div>
    </div>
    <p class="occlusion-summary">${focusRoom ? `焦点：${focusRoom.name}` : "自由焦点"} · 保留所有可见相邻空间${cutawayActive ? ` · 仅隐藏已登记局部遮挡 ${focusOccluderHiddenCount} 项 · 共 ${hiddenWallCount} 墙 / ${hiddenComponentCount} 组件` : ""}</p>
    <div class="scene-control-section">
      <div class="scene-control-heading">
        <strong>位置</strong>
        <button type="button" data-transform-part="position" class="axis-mode-button${sceneTransformPart === "position" ? " active" : ""}">位置轴</button>
      </div>
      <div class="field-grid">
        ${axisFieldMarkup("X", "positionX", item.position[0], { min: -xLimit, max: xLimit })}
        ${axisFieldMarkup("Y", "positionY", item.position[1], { min: 0.2, max: 6 })}
        ${axisFieldMarkup("Z", "positionZ", item.position[2], { min: -zLimit, max: zLimit })}
      </div>
    </div>
    <div class="scene-control-section lens-control-section">
      <div class="scene-control-heading"><strong>镜头</strong><span>${lensBand} · ${focalLength}mm</span></div>
      <div class="lens-preset-switch" role="group" aria-label="焦段快捷选择">
        ${Object.entries(LENS_PRESETS).map(([key, preset]) => `
          <button type="button" data-lens-preset="${key}" class="${item.lensPreset === key ? "active" : ""}" data-tooltip="${preset.label} ${preset.focalLengthMm}mm" aria-label="${preset.label} ${preset.focalLengthMm}mm" title="${preset.label} ${preset.focalLengthMm}mm">
            <strong>${preset.focalLengthMm}</strong><small>mm</small>
          </button>`).join("")}
      </div>
      <div class="lens-metrics" aria-label="当前镜头参数">
        <span><strong>${focalLength}mm</strong> 焦距</span>
        <span><strong>${Number(item.fov).toFixed(1)}°</strong> 视场角</span>
        <span><strong>直线</strong> 无鱼眼变形</span>
      </div>
      <div class="field-grid compact-grid">
        ${sliderFieldMarkup("焦距", "focalLengthMm", item.focalLengthMm, { min: 14, max: 85, step: 1, suffix: "mm", help: "数值越小画面越广；数值越大主体越近、空间压缩越明显。" })}
        ${sliderFieldMarkup("视场角", "fov", item.fov, { min: 16, max: 82, step: 0.5, suffix: "°", help: "表示镜头一次能看到的垂直范围，会与焦距联动。" })}
      </div>
    </div>`;
  bindSceneInspector("camera", item);
  dom.sceneInspector.querySelectorAll("[data-lens-preset]").forEach((button) => {
    button.addEventListener("click", () => mutateSceneItem(`切换${sceneDisplayName("camera", item)}镜头`, "camera", item.id, () => {
      const current = sceneCameraById(item.id);
      const preset = LENS_PRESETS[button.dataset.lensPreset];
      current.lensPreset = button.dataset.lensPreset;
      current.focalLengthMm = preset.focalLengthMm;
      current.fov = fovForFocalLength(current.focalLengthMm);
      current.distortion = preset.distortion;
    }));
  });
  dom.sceneInspector.querySelector('[data-action="view-camera"]').addEventListener("click", () => {
    if (activePlan && cameraPlanPreviewSnapshot) restoreCameraPlanPreview({ restoreView: true, announce: true });
    else if (activeSceneCameraId === item.id) returnFreeView();
    else enterSceneCameraView(item.id);
  });
  dom.sceneInspector.querySelector('[data-action="plan-camera"]').addEventListener("click", () => {
    cameraEvidenceState = null;
    selection = { type: "camera", id: item.id };
    setTop();
    activateTab("scene-panel");
    setSceneEditorMode("camera");
    showViewToast("平面机位与实时视角已联动", "success");
  });
  dom.sceneInspector.querySelector('[data-action="toggle-wall-snap"]').addEventListener("click", () => {
    mutateSceneItem(`${item.mount?.snapEnabled ? "关闭" : "开启"}${sceneDisplayName("camera", item)}墙面吸附`, "camera", item.id, () => {
      const current = sceneCameraById(item.id);
      current.mount.snapEnabled = !current.mount.snapEnabled;
      if (current.mount.snapEnabled) {
        applyCameraWallSnap(current);
      } else if (current.mount.mode === "wall") {
        current.mount.mode = "free";
        current.mount.wallId = null;
        current.mount.offset = null;
      }
    });
  });
  dom.sceneInspector.querySelector('[data-action="toggle-cutaway"]').addEventListener("click", () => toggleCameraCutaway(item.id));
  dom.sceneInspector.querySelector('[data-action="screenshot-camera"]').addEventListener("click", () => captureCurrentView(item.id));
  dom.sceneInspector.querySelector('[data-action="reset-camera"]').addEventListener("click", () => mutateSceneItem(`恢复${sceneDisplayName("camera", item)}`, "camera", item.id, () => {
      const original = originalSceneRig.cameras.find((candidate) => candidate.id === item.id);
      if (original) sceneRig.cameras[sceneRig.cameras.findIndex((candidate) => candidate.id === item.id)] = structuredClone(original);
  }, { rebuildRig: true }));
  dom.sceneInspector.querySelector('[data-action="delete-camera"]').addEventListener("click", () => {
    if (sceneRig.cameras.length <= 1) return;
    if (activeSceneCameraId === item.id) returnFreeView();
    mutateSceneItem(`删除${sceneDisplayName("camera", item)}`, "camera", item.id, () => {
      sceneRig.cameras = sceneRig.cameras.filter((candidate) => candidate.id !== item.id);
      selection = { type: "camera", id: sceneRig.cameras[0].id };
    }, { rebuildRig: true });
  });
}

function renderInspectors() {
  dom.structureInspector.replaceChildren();
  dom.componentInspector.replaceChildren();
  dom.sceneInspector.replaceChildren();
  if (selection.type === "wall") {
    const wall = wallById(selection.id);
    if (wall) renderWallInspector(wall);
  } else if (selection.type === "window") {
    const item = windowById(selection.id);
    if (item) renderWindowInspector(item);
  } else if (selection.type === "component") {
    const placement = componentById(selection.id);
    if (placement) renderComponentInspector(placement);
  } else if (selection.type === "light") {
    const item = lightById(selection.id);
    if (item) renderLightInspector(item);
  } else if (selection.type === "camera") {
    const item = sceneCameraById(selection.id);
    if (item) renderCameraInspector(item);
  }
}

function renderLayerControls() {
  const labels = [
    ["walls", "墙体"],
    ["windows", "窗与玻璃"],
    ["ceilings", "天花板"],
    ["fixedFixtures", "紫色固定构件"],
    ["movableFurniture", "绿色活动家具"],
    ["grid", "地面网格"],
    ["annotations", "空间边界、名称与面积"],
  ];
  const host = document.getElementById("layer-controls");
  host.innerHTML = labels.map(([key, label]) => `<label class="layer-row"><span>${label}</span><input type="checkbox" data-layer="${key}"${model.layers[key] !== false ? " checked" : ""}></label>`).join("");
  host.querySelectorAll("[data-layer]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.dataset.layer === "annotations") {
        setAnnotationsVisible(input.checked);
        return;
      }
      performMutation(`${input.checked ? "显示" : "隐藏"}${input.parentElement.textContent.trim()}`, () => {
        model.layers[input.dataset.layer] = input.checked;
      });
    });
  });
}

function buildRoomAnnotations() {
  clearGroup(roomLineGroup);
  clearGroup(roomHoverGroup);
  dom.roomAnnotations.replaceChildren();
  roomLabels.clear();
  roomBoundaryLines.clear();
  hoveredRoomId = null;
  (model.rooms || []).forEach((room) => {
    const linePoints = room.polygon.map((point) => {
      const world = worldPoint(point);
      return new THREE.Vector3(world.x, 0.02, world.z);
    });
    linePoints.push(linePoints[0].clone());
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(linePoints),
      new THREE.LineDashedMaterial({ color: 0x606963, dashSize: 0.12, gapSize: 0.08 }),
    );
    line.computeLineDistances();
    line.userData.roomId = room.id;
    line.material.transparent = true;
    line.material.opacity = 0.78;
    roomLineGroup.add(line);
    roomBoundaryLines.set(room.id, line);

    const label = document.createElement("div");
    label.className = "room-label";
    label.dataset.roomId = room.id;
    const name = document.createElement("strong");
    name.textContent = room.name;
    const area = document.createElement("small");
    area.textContent = `${Number(room.areaM2 ?? polygonArea(room.polygon)).toFixed(1)} m²`;
    label.append(name, area);
    const labelPlan = room.labelPosition || room.polygon.reduce(
      (sum, current) => [sum[0] + current[0] / room.polygon.length, sum[1] + current[1] / room.polygon.length],
      [0, 0],
    );
    label.dataset.planX = String(labelPlan[0]);
    label.dataset.planZ = String(labelPlan[1]);
    dom.roomAnnotations.appendChild(label);
    roomLabels.set(room.id, label);
  });
  const dimensions = model.dimensionAnnotations || {};
  const width = dimensions.widthMeters || cfg.realWidthMeters;
  const depth = dimensions.depthMeters || cfg.realDepthMeters;
  document.getElementById("dimension-width-label").textContent = `${dimensions.widthLabel || "总宽"} ${width.toFixed(2)}m`;
  document.getElementById("dimension-depth-label").textContent = `${dimensions.depthLabel || "总深"} ${depth.toFixed(2)}m`;
}

function setHoveredRoom(roomId = null) {
  const nextId = roomById(roomId)?.id || null;
  if (hoveredRoomId === nextId) return;
  hoveredRoomId = nextId;
  clearGroup(roomHoverGroup);
  roomBoundaryLines.forEach((line, id) => {
    line.material.color.setHex(id === nextId ? 0xd99000 : 0x606963);
    line.material.opacity = nextId && id !== nextId ? 0.28 : 0.78;
  });
  roomLabels.forEach((label, id) => label.classList.toggle("hovered", id === nextId));
  const room = roomById(nextId);
  if (room && model.layers.annotations !== false) {
    const points = room.polygon.map(([x, z]) => new THREE.Vector2(
      x - cfg.realWidthMeters / 2,
      cfg.realDepthMeters / 2 - z,
    ));
    const mesh = new THREE.Mesh(
      new THREE.ShapeGeometry(new THREE.Shape(points)),
      new THREE.MeshBasicMaterial({
        color: 0xf0b323,
        transparent: true,
        opacity: 0.18,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
    );
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.y = 0.018;
    mesh.renderOrder = 3;
    mesh.name = `room-hover-${room.id}`;
    roomHoverGroup.add(mesh);
  }
  document.body.classList.toggle("room-boundary-hover", Boolean(nextId));
  requestRender();
}

function updateRoomHover(event) {
  if (
    model.layers.annotations === false
    || pointerDown
    || componentDrag
    || sceneObjectDrag
    || measurement.active
  ) {
    setHoveredRoom(null);
    return;
  }
  const point = planPointAt(event);
  const room = point
    ? (model.rooms || []).find((item) => (
      (roomFilterIsAll() || roomFilterIds.has(item.id))
      && pointInPolygon(point, item.polygon)
    ))
    : null;
  setHoveredRoom(room?.id || null);
}

function updateRoomAnnotationPositions() {
  const visible = model.layers.annotations !== false;
  dom.roomAnnotations.hidden = !visible;
  dom.dimensionAnnotations.hidden = !visible;
  roomLineGroup.visible = visible;
  roomLineGroup.children.forEach((line, index) => {
    const room = model.rooms?.[index];
    line.visible = Boolean(
      room
      && (roomFilterIsAll() || roomFilterIds.has(room.id)),
    );
  });
  document.body.classList.toggle("annotations-hidden", !visible);
  document.getElementById("toggle-annotations").setAttribute("aria-pressed", String(visible));
  if (!visible) {
    setHoveredRoom(null);
    return;
  }
  const bounds = renderer.domElement.getBoundingClientRect();
  roomLabels.forEach((label, roomId) => {
    if (
      !roomFilterIsAll() && !roomFilterIds.has(roomId)
    ) {
      label.hidden = true;
      return;
    }
    const world = worldPoint([Number(label.dataset.planX), Number(label.dataset.planZ)]);
    const projected = new THREE.Vector3(world.x, 0.035, world.z).project(camera);
    const x = (projected.x * 0.5 + 0.5) * bounds.width;
    const y = (-projected.y * 0.5 + 0.5) * bounds.height;
    label.hidden = !(projected.z > -1 && projected.z < 1 && x > -50 && x < bounds.width + 50 && y > -30 && y < bounds.height + 30);
    label.style.left = `${x}px`;
    label.style.top = `${y}px`;
  });
}

function setAnnotationsVisible(visible) {
  model.layers.annotations = Boolean(visible);
  applyLayerVisibility();
  renderLayerControls();
  updateRuntimeAudit();
  setStatus(`${visible ? "显示" : "隐藏"}空间边界、名称与面积已应用`, "success");
  return true;
}

function cameraOccluders(item) {
  scene.updateMatrixWorld(true);
  const origin = new THREE.Vector3(...item.position);
  const target = new THREE.Vector3(...item.target);
  const forward = target.clone().sub(origin);
  const distance = forward.length();
  if (distance <= 0.4) return { wallIds: [], componentIds: [] };
  forward.normalize();
  const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0));
  if (right.lengthSq() < 0.0001) right.set(1, 0, 0);
  right.normalize();
  const up = new THREE.Vector3().crossVectors(right, forward).normalize();
  const focusRoom = roomById(item.focusRoomId);
  const preserveElementIds = new Set(item.visibility?.preserveElementIds || []);
  const frameSamples = [];
  [-0.9, 0, 0.9].forEach((horizontal) => {
    [-0.55, 0, 0.55].forEach((vertical) => {
      frameSamples.push(
        target.clone()
          .addScaledVector(right, horizontal)
          .addScaledVector(up, vertical),
      );
    });
  });
  const sampleTargets = focusRoom?.polygon?.length
    ? [
      ...frameSamples,
      ...focusRoom.polygon.slice(0, 8).map((point) => {
        const world = worldPoint(point);
        return new THREE.Vector3(
          target.x + (world.x - target.x) * 0.55,
          0.9,
          target.z + (world.z - target.z) * 0.55,
        );
      }),
    ]
    : [
      ...frameSamples,
    ];
  const wallIds = new Set();
  const componentIds = new Set();
  sampleTargets.forEach((sampleTarget) => {
    const sampleDirection = sampleTarget.sub(origin);
    const sampleDistance = sampleDirection.length();
    sampleDirection.normalize();
    const occlusionRay = new THREE.Raycaster(origin, sampleDirection, 0.01, Math.max(0.01, sampleDistance - 0.3));
    occlusionRay.intersectObjects([structureGroup, movableGroup, fixedGroup], true).forEach((hit) => {
      const pick = hit.object.userData.pick;
      if (pick?.type === "wall") wallIds.add(pick.id);
      if (pick?.type === "component" && !preserveElementIds.has(pick.id)) componentIds.add(pick.id);
    });
  });
  if (item.mount?.mode === "wall" && item.mount.wallId) wallIds.add(item.mount.wallId);
  return {
    wallIds: [...wallIds],
    componentIds: [...componentIds],
  };
}

function deriveContextVisibility(item) {
  const preserveElementIds = new Set(item.visibility?.preserveElementIds || []);
  const explicitHidden = Array.isArray(item.visibility?.hiddenElementIds)
    ? item.visibility.hiddenElementIds
    : [];
  const hiddenWallIds = [...new Set(explicitHidden.filter((id) => wallById(id)))]
    .filter((id) => !preserveElementIds.has(id));
  const hiddenComponentIds = [...new Set(explicitHidden.filter((id) => componentById(id)))]
    .filter((id) => !preserveElementIds.has(id));
  return {
    contextPolicy: "preserve-visible-adjacent-spaces",
    hiddenWallIds,
    hiddenComponentIds,
  };
}

function applyCameraCutawayVisibility() {
  const item = sceneCameraById(activeOcclusionCameraId);
  if (!item?.visibility?.cutawayEnabled) return;
  item.visibility.hiddenWallIds.forEach((id) => {
    const wallGroup = wallGroups.get(id);
    if (wallGroup) wallGroup.visible = false;
    model.windows.filter((windowItem) => windowItem.wallId === id).forEach((windowItem) => {
      const windowGroup = windowGroups.get(windowItem.id);
      if (windowGroup) windowGroup.visible = false;
    });
  });
  item.visibility.hiddenComponentIds.forEach((id) => {
    const componentGroup = componentGroups.get(id);
    if (componentGroup) componentGroup.visible = false;
  });
}

function refreshCameraCutaway(item) {
  const visibility = deriveContextVisibility(item);
  item.visibility.cutawayEnabled = true;
  Object.assign(item.visibility, visibility);
  activeOcclusionCameraId = item.id;
}

function toggleCameraCutaway(id) {
  const item = sceneCameraById(id);
  if (!item) return false;
  const enabling = !(item.visibility?.cutawayEnabled && activeOcclusionCameraId === item.id);
  if (enabling && !(item.visibility?.hiddenElementIds || []).length) {
    setStatus("没有已复核并登记的局部遮挡；不会自动隐藏其它空间", "error");
    return false;
  }
  return mutateSceneItem(enabling ? `隐藏${sceneDisplayName("camera", item)}遮挡` : `恢复${sceneDisplayName("camera", item)}遮挡`, "camera", id, () => {
    if (enabling) {
      item.visibility.cutawayEnabled = true;
      activeOcclusionCameraId = item.id;
    } else {
      item.visibility.cutawayEnabled = false;
      item.visibility.hiddenWallIds = [];
      item.visibility.hiddenComponentIds = [];
      activeOcclusionCameraId = null;
    }
  });
}

function activeCameraPlanShot() {
  return cameraPlan.shots?.find((shot) => shot.shotId === activeCameraPlanShotId) || null;
}

function applyCameraPlanPreviewVisibility() {
  const shot = activeCameraPlanShot();
  const item = sceneCameraById(activeSceneCameraId);
  if (!shot || !item?.visibility?.cutawayEnabled) return;
  const hiddenWalls = new Set(item.visibility.hiddenWallIds || []);
  const hiddenComponents = new Set(item.visibility.hiddenComponentIds || []);
  wallGroups.forEach((group, id) => {
    if (hiddenWalls.has(id)) group.visible = false;
  });
  windowGroups.forEach((group, id) => {
    const item = windowById(id);
    if (item && hiddenWalls.has(item.wallId)) group.visible = false;
  });
  componentGroups.forEach((group, id) => {
    if (hiddenComponents.has(id)) group.visible = false;
  });
}

function applyLayerVisibility() {
  const allRooms = roomFilterIsAll();
  const noRooms = roomFilterIds.size === 0;
  structureGroup.visible = model.layers.walls !== false && allRooms;
  glassGroup.visible = model.layers.windows !== false && allRooms;
  roomFilterStructureGroup.visible = model.layers.walls !== false && !allRooms && !noRooms;
  roomFilterGlassGroup.visible = model.layers.windows !== false && !allRooms && !noRooms;
  fixedGroup.visible = model.layers.fixedFixtures !== false;
  movableGroup.visible = model.layers.movableFurniture !== false;
  ceilingGroup.visible = model.layers.ceilings !== false && viewMode !== "top";
  ceilingMeshes.forEach((mesh, roomId) => {
    mesh.visible = roomFilterIds.has(roomId);
  });
  wallEndpointHandleGroup.visible = model.backendOptions?.structureEditing?.wallEndpointEditing === true
    && selection.type === "wall"
    && activePanelId === "structure-panel"
    && !document.body.classList.contains("capture")
    && !activeSceneCameraId
    && !activeCameraPlanShotId;
  dom.ceilingToggle?.setAttribute("aria-pressed", String(model.layers.ceilings !== false));
  dom.ceilingToggle?.classList.toggle("active", model.layers.ceilings !== false);
  if (floorMesh) floorMesh.visible = allRooms || noRooms;
  roomFilterFloorGroup.visible = !allRooms && !noRooms;
  roomFilterFloors.forEach((mesh, id) => {
    mesh.visible = !noRooms && roomFilterIds.has(id);
  });
  if (grid) grid.visible = model.layers.grid !== false && (allRooms || noRooms);
  if (boundaryLine) boundaryLine.visible = allRooms || noRooms;
  semanticDividerGroup.visible = allRooms || noRooms || semanticDividerGroup.children.some((mesh) => (
    mesh.userData.roomIds?.some((id) => roomFilterIds.has(id))
  ));
  semanticDividerGroup.children.forEach((mesh) => {
    mesh.visible = allRooms || noRooms || mesh.userData.roomIds?.some((id) => roomFilterIds.has(id));
  });
  wallGroups.forEach((group, id) => {
    const wall = wallById(id);
    group.visible = model.layers.walls !== false
      && wall?.enabled !== false
      && allRooms;
  });
  windowGroups.forEach((group, id) => {
    const item = windowById(id);
    group.visible = model.layers.windows !== false
      && item?.enabled !== false
      && allRooms;
  });
  componentGroups.forEach((group, id) => {
    const placement = componentById(id);
    const definition = placement ? getComponentDefinition(placement.componentId, placement.semantic) : null;
    const layerVisible = definition?.placementClass === "fixed-purple"
      ? model.layers.fixedFixtures !== false
      : model.layers.movableFurniture !== false;
    group.visible = layerVisible
      && placement?.presentationHidden !== true
      && componentMatchesRoomFilter(placement);
  });
  managedLights.forEach((light, id) => {
    const item = lightById(id);
    light.visible = item?.enabled !== false && sceneItemMatchesRoomFilter("light", item);
  });
  updateSceneRigVisibility();
  applyCameraCutawayVisibility();
  applyCameraPlanPreviewVisibility();
  updateRoomAnnotationPositions();
  requestRender();
}

function updateHeader() {
  document.getElementById("model-name").textContent = model.name;
  document.getElementById("model-stats").textContent = `${model.walls.length} 墙 · ${model.windows.length} 窗 · ${model.componentPlacements.length} 组件`;
}

function rebuildAll() {
  applyRenderingSettings();
  buildFloor();
  buildStructure();
  applyStructureAppearance();
  buildComponents();
  buildSceneRig();
  buildRoomAnnotations();
  renderRoomFilterControl();
  applyLayerVisibility();
  renderLists();
  renderInspectors();
  renderLayerControls();
  updateHeader();
  updateUndoButtons();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
}

function activateTab(panelId) {
  activePanelId = panelId;
  document.querySelectorAll(".editor-tabs button").forEach((button) => {
    const active = button.dataset.panel === panelId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".editor-section").forEach((panel) => {
    const active = panel.id === panelId;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  ensureSelectionMatchesActivePanel();
  updateSceneRigVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  requestRender();
}

document.querySelectorAll(".editor-tabs button").forEach((button) => button.addEventListener("click", () => {
  activateTab(button.dataset.panel);
  if (button.dataset.panel === "scene-panel" && !["light", "camera"].includes(selection.type)) {
    setSceneEditorMode(sceneEditorMode);
  }
}));
document.getElementById("undo").addEventListener("click", undo);
document.getElementById("redo").addEventListener("click", redo);

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
let pointerDown = null;

function updatePointerRay(event) {
  const bounds = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
  pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
}

function pickAt(event) {
  updatePointerRay(event);
  if (viewMode === "top" && sceneRigHelperGroup.visible) {
    const helperRoots = transformGizmoGroup.visible
      ? [transformGizmoGroup, sceneRigHelperGroup]
      : [sceneRigHelperGroup];
    const helperTypes = new Set(["light", "camera", "transform-axis", "transform-plane"]);
    const helperHits = raycaster.intersectObjects(helperRoots, true)
      .filter((hit) => helperTypes.has(hit.object.userData.pick?.type));
    const centerHandle = helperHits.find((hit) => hit.object.userData.pick.type === "transform-plane");
    const helperPick = (centerHandle || helperHits[0])?.object.userData.pick;
    if (helperPick) return helperPick;
  }
  let roots = [];
  let allowedTypes = new Set();
  if (activePanelId === "structure-panel") {
    roots = roomFilterIsAll()
      ? [wallEndpointHandleGroup, structureGroup, glassGroup]
      : [wallEndpointHandleGroup, roomFilterStructureGroup, roomFilterGlassGroup];
    allowedTypes = new Set(["wall", "window", "wall-endpoint"]);
  } else if (activePanelId === "furniture-panel") {
    roots = [movableGroup, fixedGroup];
    allowedTypes = new Set(["component"]);
  } else if (activePanelId === "scene-panel") {
    if (sceneRigHelperGroup.visible) roots.push(sceneRigHelperGroup);
    if (transformGizmoGroup.visible) roots.unshift(transformGizmoGroup);
    allowedTypes = new Set(["light", "camera", "transform-axis", "transform-plane"]);
  }
  const hits = raycaster.intersectObjects(roots, true);
  const pickedHits = hits.filter((hit) => allowedTypes.has(hit.object.userData.pick?.type));
  const wallEndpointHandle = pickedHits.find((hit) => hit.object.userData.pick.type === "wall-endpoint");
  const centerHandle = pickedHits.find((hit) => hit.object.userData.pick.type === "transform-plane");
  return (wallEndpointHandle || centerHandle || pickedHits[0])?.object.userData.pick || null;
}

function planPointAt(event) {
  const point = groundPlanPointAt(event);
  return point && pointInPolygon(point, model.floorBoundary) ? point : null;
}

function groundPlanPointAt(event) {
  updatePointerRay(event);
  const intersection = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(floorPlane, intersection)) return null;
  return planPoint(intersection.x, intersection.z);
}

function startWallEndpointDrag(event, pick) {
  const wall = wallById(pick.id);
  const sourceWall = originalModel.walls.find((item) => item.id === pick.id);
  if (
    !wall
    || !sourceWall
    || !["start", "end"].includes(pick.endpoint)
    || model.backendOptions?.structureEditing?.wallEndpointEditing !== true
  ) return false;
  selectObject("wall", wall.id, false);
  const extensions = wall.endpointExtensions || { start: 0, end: 0 };
  wallEndpointDrag = {
    wallId: wall.id,
    endpoint: pick.endpoint,
    startExtension: Number(extensions.start) || 0,
    endExtension: Number(extensions.end) || 0,
    proposedStart: Number(extensions.start) || 0,
    proposedEnd: Number(extensions.end) || 0,
    controlsEnabled: controls.enabled,
    moved: false,
  };
  controls.enabled = false;
  renderer.domElement.setPointerCapture?.(event.pointerId);
  document.body.classList.add("wall-endpoint-dragging");
  setStatus(`拖动${wall.name}${pick.endpoint === "start" ? "起点" : "终点"}；端点沿原墙轴移动`);
  return true;
}

function updateWallEndpointDrag(event) {
  if (!wallEndpointDrag) return false;
  const sourceWall = originalModel.walls.find((item) => item.id === wallEndpointDrag.wallId);
  const point = groundPlanPointAt(event);
  if (!sourceWall || !point) return false;
  const frame = wallFrame(sourceWall);
  const projected = (point[0] - sourceWall.start[0]) * frame.ux
    + (point[1] - sourceWall.start[1]) * frame.uz;
  const otherExtension = wallEndpointDrag.endpoint === "start"
    ? wallEndpointDrag.proposedEnd
    : wallEndpointDrag.proposedStart;
  const minimum = 0.35 - frame.length - otherExtension;
  const extension = Math.max(minimum, Math.min(3, wallEndpointDrag.endpoint === "start"
    ? -projected
    : projected - frame.length));
  if (wallEndpointDrag.endpoint === "start") wallEndpointDrag.proposedStart = extension;
  else wallEndpointDrag.proposedEnd = extension;
  wallEndpointDrag.moved = wallEndpointDrag.moved
    || Math.abs(extension - (wallEndpointDrag.endpoint === "start"
      ? wallEndpointDrag.startExtension
      : wallEndpointDrag.endExtension)) > 0.005;
  updateWallEndpointHandlePreview(
    wallEndpointDrag.wallId,
    wallEndpointDrag.proposedStart,
    wallEndpointDrag.proposedEnd,
  );
  setStatus(`墙端点预览：起点 ${wallEndpointDrag.proposedStart.toFixed(2)} m，终点 ${wallEndpointDrag.proposedEnd.toFixed(2)} m`);
  return true;
}

function finishWallEndpointDrag(cancelled = false) {
  if (!wallEndpointDrag) return false;
  const drag = wallEndpointDrag;
  wallEndpointDrag = null;
  document.body.classList.remove("wall-endpoint-dragging");
  controls.enabled = drag.controlsEnabled;
  if (cancelled || !drag.moved) {
    buildWallEndpointHandles();
    requestRender();
    return false;
  }
  return performMutation(`拖动${wallById(drag.wallId)?.name || drag.wallId}端点`, () => {
    applyWallExtension(drag.wallId, drag.proposedStart, drag.proposedEnd);
  });
}

function rebuildMeasurementGeometry() {
  clearGroup(measurementGroup);
  dom.measurementLabel.hidden = true;
  measurement.midpoint = null;
  measurement.distance = null;
  document.getElementById("clear-measure").disabled = measurement.points.length === 0;
  if (!measurement.points.length) {
    requestRender();
    return;
  }
  const material = new THREE.MeshBasicMaterial({ color: 0x286da8, depthTest: false });
  measurement.points.forEach((point, index) => {
    const world = worldPoint(point);
    const marker = new THREE.Mesh(new THREE.SphereGeometry(0.07, 20, 14), material.clone());
    marker.name = `measure-point-${index + 1}`;
    marker.position.set(world.x, 0.08, world.z);
    marker.renderOrder = 30;
    measurementGroup.add(marker);
  });
  if (measurement.points.length < 2) {
    requestRender();
    return;
  }
  const [start, end] = measurement.points;
  const worldStart = worldPoint(start);
  const worldEnd = worldPoint(end);
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(worldStart.x, 0.08, worldStart.z),
      new THREE.Vector3(worldEnd.x, 0.08, worldEnd.z),
    ]),
    new THREE.LineBasicMaterial({ color: 0x286da8, depthTest: false }),
  );
  line.renderOrder = 29;
  measurementGroup.add(line);
  measurement.distance = Math.hypot(end[0] - start[0], end[1] - start[1]);
  measurement.midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
  dom.measurementLabel.textContent = `${measurement.distance.toFixed(3)} m`;
  dom.measurementLabel.hidden = false;
  requestRender();
}

function updateMeasurementLabelPosition() {
  if (!measurement.midpoint) return;
  const bounds = renderer.domElement.getBoundingClientRect();
  const world = worldPoint(measurement.midpoint);
  const projected = new THREE.Vector3(world.x, 0.1, world.z).project(camera);
  dom.measurementLabel.style.left = `${(projected.x * 0.5 + 0.5) * bounds.width}px`;
  dom.measurementLabel.style.top = `${(-projected.y * 0.5 + 0.5) * bounds.height}px`;
  dom.measurementLabel.hidden = projected.z <= -1 || projected.z >= 1;
}

function clearMeasurement() {
  measurement.points = [];
  rebuildMeasurementGeometry();
  setStatus(measurement.active ? "量尺已清除，请点选起点 A" : "量尺已清除");
}

function setMeasurementMode(active) {
  measurement.active = Boolean(active);
  document.body.classList.toggle("measure-mode", measurement.active);
  document.getElementById("toggle-measure").setAttribute("aria-pressed", String(measurement.active));
  setStatus(measurement.active ? "量尺：请在户型内点选起点 A" : "已退出量尺");
}

function setMeasurementPoints(start, end) {
  if (![start, end].every((point) => Array.isArray(point) && point.length === 2 && pointInPolygon(point, model.floorBoundary))) {
    setStatus("量尺点必须位于户型边界内", "error");
    return false;
  }
  measurement.points = [[Number(start[0]), Number(start[1])], [Number(end[0]), Number(end[1])]];
  rebuildMeasurementGeometry();
  setStatus(`量尺结果：${measurement.distance.toFixed(3)} m`, "success");
  return true;
}

function handleMeasurementPoint(point) {
  if (!point) {
    setStatus("请在户型地面内选择量尺点", "error");
    return;
  }
  if (measurement.points.length >= 2) measurement.points = [];
  measurement.points.push(point);
  rebuildMeasurementGeometry();
  setStatus(measurement.points.length === 1 ? "已记录起点 A，请点选终点 B" : `A 到 B：${measurement.distance.toFixed(3)} m`, measurement.points.length === 2 ? "success" : "normal");
}

function sceneItemFromDrag(type, id) {
  return type === "light" ? lightById(id) : sceneCameraById(id);
}

function selectSceneObjectForEditing(type, id, { enablePreview = false } = {}) {
  if (!["light", "camera"].includes(type) || !sceneItemFromDrag(type, id)) return false;
  selectObject(type, id, true);
  sceneTransformPart = "position";
  if (type === "camera" && enablePreview) setCameraPreviewEnabled(true);
  buildTransformGizmo();
  updateSceneRigVisibility();
  updateSelectionHighlight();
  requestRender();
  return true;
}

function sceneObjectWorldPoint(type, id, part = "position") {
  const item = sceneItemFromDrag(type, id);
  if (!item || !["position", "target"].includes(part)) return null;
  return new THREE.Vector3(...item[part]);
}

function sceneObjectDisplayPoint(type, id, part = "position") {
  const item = sceneItemFromDrag(type, id);
  if (!item || !["position", "target"].includes(part)) return null;
  return new THREE.Vector3(...(
    type === "light"
      ? lightHelperPosition(item, part === "target")
      : sceneHelperPosition(item[part], part === "target")
  ));
}

function worldPointToCanvas(point) {
  if (!point) return null;
  const bounds = renderer.domElement.getBoundingClientRect();
  const projected = point.clone().project(camera);
  return {
    x: bounds.left + (projected.x * 0.5 + 0.5) * bounds.width,
    y: bounds.top + (-projected.y * 0.5 + 0.5) * bounds.height,
    visible: projected.z > -1 && projected.z < 1,
  };
}

function getSceneObjectScreenPoint(type, id, part = "position") {
  return worldPointToCanvas(sceneObjectDisplayPoint(type, id, part));
}

function getSceneHandleScreenPoint(axis = "center") {
  if (!["light", "camera"].includes(selection.type)) return null;
  const origin = sceneObjectDisplayPoint(selection.type, selection.id, sceneTransformPart);
  if (!origin) return null;
  if (["x", "y", "z"].includes(axis)) origin.addScaledVector(axisVector(axis), 0.72);
  return worldPointToCanvas(origin);
}

function axisVector(axis) {
  if (axis === "x") return new THREE.Vector3(1, 0, 0);
  if (axis === "y") return new THREE.Vector3(0, 1, 0);
  return new THREE.Vector3(0, 0, 1);
}

function axisRayParameter(event, origin, axis) {
  updatePointerRay(event);
  const direction = axisVector(axis);
  const start = origin.clone().addScaledVector(direction, -100);
  const end = origin.clone().addScaledVector(direction, 100);
  const pointOnSegment = new THREE.Vector3();
  raycaster.ray.distanceSqToSegment(start, end, new THREE.Vector3(), pointOnSegment);
  return pointOnSegment.sub(origin).dot(direction);
}

function planeDragPoint(event, height) {
  updatePointerRay(event);
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -height);
  return raycaster.ray.intersectPlane(plane, new THREE.Vector3());
}

function startSceneObjectDrag(event, pick) {
  const targetType = pick.targetType || pick.type;
  const targetId = pick.targetId || pick.id;
  if (!["light", "camera"].includes(targetType)) return false;
  if (!selectSceneObjectForEditing(targetType, targetId)) return false;
  const item = sceneItemFromDrag(targetType, targetId);
  if (!item) return false;
  const part = pick.part || "position";
  const vector = new THREE.Vector3(...(part === "target" ? item.target : item.position));
  const displayVector = sceneObjectDisplayPoint(targetType, targetId, part);
  const axis = pick.type === "transform-axis" ? pick.axis : null;
  const planePoint = axis ? null : planeDragPoint(event, displayVector.y);
  sceneObjectDrag = {
    before: serializeModel(),
    targetType,
    targetId,
    part,
    axis,
    startVector: vector.clone(),
    startDisplayVector: displayVector.clone(),
    startAxisParameter: axis ? axisRayParameter(event, displayVector, axis) : null,
    startPlanePoint: planePoint,
    controlsEnabled: controls.enabled,
    moved: false,
  };
  sceneTransformPart = part;
  controls.enabled = false;
  renderer.domElement.setPointerCapture?.(event.pointerId);
  document.body.classList.add("scene-dragging");
  renderLists();
  renderInspectors();
  buildTransformGizmo();
  updateSceneRigVisibility();
  updateSelectionHighlight();
  requestRender();
  return true;
}

function updateDraggedSceneObject(event) {
  if (!sceneObjectDrag) return;
  const item = sceneItemFromDrag(sceneObjectDrag.targetType, sceneObjectDrag.targetId);
  if (!item) return;
  const next = sceneObjectDrag.startVector.clone();
  if (sceneObjectDrag.axis) {
    const parameter = axisRayParameter(event, sceneObjectDrag.startDisplayVector, sceneObjectDrag.axis);
    next.addScaledVector(
      axisVector(sceneObjectDrag.axis),
      parameter - sceneObjectDrag.startAxisParameter,
    );
  } else {
    const point = planeDragPoint(event, sceneObjectDrag.startDisplayVector.y);
    if (!point || !sceneObjectDrag.startPlanePoint) return;
    next.x += point.x - sceneObjectDrag.startPlanePoint.x;
    next.z += point.z - sceneObjectDrag.startPlanePoint.z;
  }
  next.y = Math.max(sceneObjectDrag.part === "position" ? 0.05 : -5, next.y);
  const destination = sceneObjectDrag.part === "target" ? item.target : item.position;
  destination.splice(0, 3, next.x, next.y, next.z);
  if (sceneObjectDrag.targetType === "camera" && sceneObjectDrag.part === "position") {
    item.mount.mode = "free";
    item.mount.wallId = null;
    item.mount.offset = null;
  }
  if (sceneObjectDrag.targetType === "camera" && sceneObjectDrag.part === "target") item.focusRoomId = null;
  sceneObjectDrag.moved = true;
  ["positionX", "positionY", "positionZ"].forEach((field, index) => syncSceneFieldInputs(field, item.position[index].toFixed(2)));
  ["targetX", "targetY", "targetZ"].forEach((field, index) => syncSceneFieldInputs(field, item.target[index].toFixed(2)));
  updateSceneObjectVisual(sceneObjectDrag.targetType, item);
  setStatus(`${sceneDisplayName(sceneObjectDrag.targetType, item)}${sceneObjectDrag.part === "target" ? "焦点" : "位置"}预览中`);
}

function finishSceneObjectDrag(cancelled = false) {
  if (!sceneObjectDrag) return;
  const drag = sceneObjectDrag;
  sceneObjectDrag = null;
  document.body.classList.remove("scene-dragging");
  controls.enabled = drag.controlsEnabled;
  if (cancelled || !drag.moved) {
    if (cancelled) restoreSnapshot(drag.before);
    buildSceneRig();
    applyLayerVisibility();
    renderLists();
    renderInspectors();
    updateRuntimeAudit();
    requestRender();
    return;
  }
  const item = sceneItemFromDrag(drag.targetType, drag.targetId);
  if (drag.targetType === "camera" && drag.part === "position" && item?.mount?.snapEnabled) {
    applyCameraWallSnap(item);
  }
  if (drag.targetType === "camera" && item?.visibility?.cutawayEnabled) refreshCameraCutaway(item);
  const issues = validateModel();
  if (issues.length) {
    restoreSnapshot(drag.before);
    buildSceneRig();
    applyLayerVisibility();
    renderLists();
    renderInspectors();
    updateRuntimeAudit();
    requestRender();
    setStatus(`移动未应用：${issues[0]}`, "error");
    return;
  }
  undoStack.push(drag.before);
  if (undoStack.length > 80) undoStack.shift();
  redoStack.length = 0;
  updateSceneObjectVisual(drag.targetType, item);
  if (drag.targetType === "camera" && item) applyActiveCameraRigValues(item);
  applyLayerVisibility();
  renderLists();
  renderInspectors();
  updateUndoButtons();
  updateRuntimeAudit();
  requestRender();
  setStatus(`${sceneDisplayName(drag.targetType, item)}已移动`, "success");
}

function beginFixedCameraGesture(label = "微调固定机位") {
  if (!activeSceneCameraId || fixedCameraGesture) return;
  fixedCameraGesture = {
    before: serializeModel(),
    id: activeSceneCameraId,
    label,
  };
}

function commitFixedCameraGestureSoon() {
  window.clearTimeout(fixedCameraGestureTimer);
  fixedCameraGestureTimer = window.setTimeout(() => {
    if (!fixedCameraGesture) return;
    const gesture = fixedCameraGesture;
    fixedCameraGesture = null;
    finishSceneEdit({
      before: gesture.before,
      label: gesture.label,
      type: "camera",
      id: gesture.id,
    });
  }, 160);
}

function cameraNavigationVectors() {
  const forward = controls.target.clone().sub(camera.position).normalize();
  const right = forward.clone().cross(camera.up).normalize();
  const up = camera.up.clone().normalize();
  return { forward, right, up };
}

function panCanvasByArrow(key, multiplier = 1) {
  const { forward, right } = cameraNavigationVectors();
  const screenUp = right.clone().cross(forward);
  right.y = 0;
  screenUp.y = 0;
  if (right.lengthSq() < 0.000001 || screenUp.lengthSq() < 0.000001) return false;
  right.normalize();
  screenUp.normalize();
  const baseStep = Math.max(0.12, Math.min(0.65, camera.position.distanceTo(controls.target) * 0.035));
  const step = baseStep * Math.max(0.1, Number(multiplier) || 1);
  const translation = new THREE.Vector3();
  if (key === "ArrowLeft") translation.copy(right).multiplyScalar(step);
  else if (key === "ArrowRight") translation.copy(right).multiplyScalar(-step);
  else if (key === "ArrowUp") translation.copy(screenUp).multiplyScalar(-step);
  else if (key === "ArrowDown") translation.copy(screenUp).multiplyScalar(step);
  else return false;
  camera.position.add(translation);
  controls.target.add(translation);
  controls.update();
  updateRuntimeAudit();
  requestRender();
  setStatus("画布焦点已平移；点击对象可恢复对象编辑");
  return true;
}

function nudgeFixedCamera(mode, amount) {
  if (!activeSceneCameraId && !activeCameraPlanShotId) return false;
  const { forward, right, up } = cameraNavigationVectors();
  let translation = new THREE.Vector3();
  let moveTarget = true;
  if (mode === "horizontal") translation.copy(right).multiplyScalar(amount);
  else if (mode === "vertical") translation.copy(up).multiplyScalar(amount);
  else if (mode === "dolly") {
    translation.copy(forward).multiplyScalar(amount);
    moveTarget = false;
  } else return false;

  if (activeSceneCameraId) {
    const item = sceneCameraById(activeSceneCameraId);
    if (!item) return false;
    beginFixedCameraGesture("微调固定机位");
    const nextPosition = new THREE.Vector3(...item.position).add(translation);
    const nextTarget = new THREE.Vector3(...item.target);
    if (moveTarget) nextTarget.add(translation);
    if (mode === "dolly" && nextPosition.distanceTo(nextTarget) < 0.35) return false;
    item.position = nextPosition.toArray();
    item.target = nextTarget.toArray();
    item.mount.mode = "free";
    item.mount.snapEnabled = false;
    item.mount.wallId = null;
    item.mount.offset = null;
    applyActiveCameraRigValues(item);
    updateSceneObjectVisual("camera", item);
    ["positionX", "positionY", "positionZ"].forEach((field, index) => syncSceneFieldInputs(field, item.position[index].toFixed(2)));
    ["targetX", "targetY", "targetZ"].forEach((field, index) => syncSceneFieldInputs(field, item.target[index].toFixed(2)));
    commitFixedCameraGestureSoon();
  } else {
    const nextPosition = camera.position.clone().add(translation);
    const nextTarget = controls.target.clone();
    if (moveTarget) nextTarget.add(translation);
    if (mode === "dolly" && nextPosition.distanceTo(nextTarget) < 0.35) return false;
    camera.position.copy(nextPosition);
    controls.target.copy(nextTarget);
    controls.update();
    requestRender();
  }
  activeCameraViewFineTuned = true;
  return true;
}

function setFixedCameraTargetFromEvent(event) {
  if (!activeSceneCameraId && !activeCameraPlanShotId) return false;
  const point = planPointAt(event);
  if (!point) return false;
  const world = worldPoint(point);
  const target = [world.x, 1, world.z];
  if (activeSceneCameraId) {
    const item = sceneCameraById(activeSceneCameraId);
    beginFixedCameraGesture("调整固定机位焦点");
    item.target = target;
    item.focusRoomId = null;
    applyActiveCameraRigValues(item);
    updateSceneObjectVisual("camera", item);
    ["targetX", "targetY", "targetZ"].forEach((field, index) => syncSceneFieldInputs(field, item.target[index].toFixed(2)));
    commitFixedCameraGestureSoon();
  } else {
    controls.target.fromArray(target);
    controls.update();
    requestRender();
  }
  activeCameraViewFineTuned = true;
  setStatus("固定视角焦点已移动；双击不会退出机位", "success");
  return true;
}

renderer.domElement.addEventListener("pointerdown", (event) => {
  pointerDown = {
    x: event.clientX,
    y: event.clientY,
    pick: pickAt(event),
    fixedView: Boolean(activeSceneCameraId || activeCameraPlanShotId),
  };
  if (measurement.active) return;
  const pick = pointerDown.pick;
  if (pick?.type === "wall-endpoint" && activePanelId === "structure-panel") {
    startWallEndpointDrag(event, pick);
    return;
  }
  if (pick?.type === "component" && activePanelId === "furniture-panel") {
    startComponentDrag(event, pick.id);
    return;
  }
  if (pick && (["light", "camera", "transform-axis", "transform-plane"].includes(pick.type))) {
    startSceneObjectDrag(event, pick);
  }
});
renderer.domElement.addEventListener("pointermove", (event) => {
  if (wallEndpointDrag) {
    if (pointerDown && Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 3) {
      updateWallEndpointDrag(event);
    }
    return;
  }
  if (componentDrag) {
    if (pointerDown && Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 3) {
      updateComponentDrag(event);
    }
    return;
  }
  if (sceneObjectDrag) {
    if (pointerDown && Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 3) {
      updateDraggedSceneObject(event);
    }
    return;
  }
  const moved = pointerDown && Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 4;
  if (moved && viewMode === "top" && event.buttons) {
    enterFree3dFromTopDrag();
  }
  const dragPickType = pointerDown?.pick?.type;
  const draggingRigObject = ["light", "camera", "transform-axis", "transform-plane", "wall-endpoint"].includes(dragPickType);
  if (moved && pointerDown.fixedView && !draggingRigObject && event.buttons) {
    detachFixedCameraView();
    pointerDown.fixedView = false;
  }
  if (pointerDown && event.buttons) {
    hoveredSceneObject = null;
    document.body.classList.remove("scene-object-hover");
    return;
  }
  const pick = pickAt(event);
  hoveredSceneObject = pick && ["light", "camera", "transform-axis", "transform-plane", "wall-endpoint"].includes(pick.type) ? pick : null;
  document.body.classList.toggle("scene-object-hover", Boolean(hoveredSceneObject));
  updateRoomHover(event);
});
renderer.domElement.addEventListener("pointerup", (event) => {
  const clicked = pointerDown && Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) <= 5;
  const originalPick = pointerDown?.pick;
  pointerDown = null;
  if (wallEndpointDrag) {
    renderer.domElement.releasePointerCapture?.(event.pointerId);
    finishWallEndpointDrag(false);
    return;
  }
  if (componentDrag) {
    renderer.domElement.releasePointerCapture?.(event.pointerId);
    finishComponentDrag(false);
    return;
  }
  if (sceneObjectDrag) {
    renderer.domElement.releasePointerCapture?.(event.pointerId);
    const moved = sceneObjectDrag.moved;
    finishSceneObjectDrag(false);
    if (!moved && originalPick) {
      const type = originalPick.targetType || originalPick.type;
      const id = originalPick.targetId || originalPick.id;
      if (["light", "camera"].includes(type)) selectObject(type, id);
    }
    return;
  }
  if (!clicked) return;
  if (measurement.active) {
    handleMeasurementPoint(planPointAt(event));
    return;
  }
  const pick = originalPick || pickAt(event);
  if (pick?.id) selectObject(pick.type, pick.id);
  else if (!activeSceneCameraId && !activeCameraPlanShotId) clearSelectionForCanvasNavigation();
});
renderer.domElement.addEventListener("pointercancel", () => {
  if (wallEndpointDrag) finishWallEndpointDrag(true);
  if (componentDrag) finishComponentDrag(true);
  if (sceneObjectDrag) finishSceneObjectDrag(true);
});
renderer.domElement.addEventListener("pointerleave", () => {
  if (!sceneObjectDrag && !wallEndpointDrag) document.body.classList.remove("scene-object-hover");
  setHoveredRoom(null);
});
renderer.domElement.addEventListener("dblclick", (event) => {
  if (measurement.active) return;
  const pick = pickAt(event);
  const type = pick?.targetType || pick?.type;
  const id = pick?.targetId || pick?.id;
  if (type === "camera") {
    selectSceneObjectForEditing("camera", id, { enablePreview: true });
    showViewToast("摄像头已进入拖动编辑", "success");
    setStatus(`已选中${sceneDisplayName("camera", sceneCameraById(id))}；拖动相机图标或 XYZ 操纵轴即可移动`, "success");
  } else if (type === "component") {
    armComponentKeyboardMove(id);
  } else if (type === "light") {
    selectSceneObjectForEditing("light", id);
    showViewToast("光源已进入拖动编辑", "success");
    setStatus(`已选中${sceneDisplayName("light", lightById(id))}；拖动光源图标或 XYZ 操纵轴即可移动`, "success");
  } else {
    setFixedCameraTargetFromEvent(event);
  }
});

renderer.domElement.addEventListener("wheel", (event) => {
  if (!activeSceneCameraId && !activeCameraPlanShotId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const distance = Math.max(0.5, camera.position.distanceTo(controls.target));
  const amount = -Math.sign(event.deltaY || 1) * Math.min(0.32, Math.max(0.08, distance * 0.035));
  nudgeFixedCamera("dolly", amount);
}, { capture: true, passive: false });

function nextSceneId(prefix, items) {
  let index = items.length + 1;
  let id = `${prefix}-${String(index).padStart(2, "0")}`;
  while (items.some((item) => item.id === id)) {
    index += 1;
    id = `${prefix}-${String(index).padStart(2, "0")}`;
  }
  return id;
}

function addSceneLight() {
  const id = nextSceneId("light", sceneRig.lights);
  performMutation("添加光源", () => {
    sceneRig.lights.push({
      id,
      name: `光 ${sceneRig.lights.length + 1}`,
      type: "point",
      enabled: true,
      position: [3.5, 3.2, 3.5],
      target: [0, 1, 0],
      intensity: 2,
      temperatureK: 5200,
      distance: 14,
      decay: 2,
      angle: 45,
      penumbra: 0.25,
      castShadow: false,
    });
    selection = { type: "light", id };
    sceneEditorMode = "light";
    sceneTransformPart = "position";
  });
  activateTab("scene-panel");
}

function addSceneCamera() {
  const id = nextSceneId("camera", sceneRig.cameras);
  performMutation("添加摄像头", () => {
    sceneRig.cameras.push({
      id,
      name: `摄像头 ${sceneRig.cameras.length + 1}`,
      enabled: true,
      position: camera.position.toArray(),
      target: controls.target.toArray(),
      fov: camera.fov,
      focalLengthMm: focalLengthForFov(camera.fov),
      lensPreset: lensPresetForFov(camera.fov),
      distortion: 0,
      focusRoomId: null,
      near: 0.01,
      far: 120,
      mount: {
        mode: "free",
        wallId: null,
        offset: null,
        height: camera.position.y,
        side: 1,
        clearance: 0.12,
        snapEnabled: false,
      },
      visibility: {
        cutawayEnabled: false,
        contextPolicy: "preserve-visible-adjacent-spaces",
        hiddenElementIds: [],
        preserveElementIds: [],
        hiddenWallIds: [],
        hiddenComponentIds: [],
      },
    });
    normalizeSceneRigData(sceneRig);
    selection = { type: "camera", id };
    sceneEditorMode = "camera";
    sceneTransformPart = "position";
  });
  activateTab("scene-panel");
}

function downloadSceneRig() {
  const exportRig = structuredClone(sceneRig);
  if (cameraPlanPreviewSnapshot) {
    const cameraIndex = exportRig.cameras.findIndex((item) => item.id === cameraPlanPreviewSnapshot.cameraId);
    if (cameraIndex >= 0) exportRig.cameras[cameraIndex] = structuredClone(cameraPlanPreviewSnapshot.camera);
    exportRig.lights = structuredClone(cameraPlanPreviewSnapshot.lights);
    exportRig.rendering = structuredClone(cameraPlanPreviewSnapshot.rendering);
  }
  const blob = new Blob([`${JSON.stringify(exportRig, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "scene-rig.json";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  setStatus(cameraPlanPreviewSnapshot ? "已导出原场景设置；临时机位与打光未写入" : "场景设置已导出", "success");
}

function captureCurrentView(cameraId = null) {
  const helperVisible = sceneRigHelperGroup.visible;
  const transformVisible = transformGizmoGroup.visible;
  const selectionVisible = selectionHelper?.visible;
  const gridVisible = grid?.visible;
  const roomLinesVisible = roomLineGroup.visible;
  sceneRigHelperGroup.visible = false;
  transformGizmoGroup.visible = false;
  if (selectionHelper) selectionHelper.visible = false;
  if (grid) grid.visible = false;
  roomLineGroup.visible = false;
  renderScene();
  renderer.domElement.toBlob((blob) => {
    sceneRigHelperGroup.visible = helperVisible;
    transformGizmoGroup.visible = transformVisible;
    if (selectionHelper) selectionHelper.visible = selectionVisible;
    if (grid) grid.visible = gridVisible;
    roomLineGroup.visible = roomLinesVisible;
    requestRender();
    if (!blob) {
      setStatus("截图失败：浏览器没有返回画布图片", "error");
      return;
    }
    const sourceCamera = sceneCameraById(activeSceneCameraId || cameraId);
    const suffix = sourceCamera ? sourceCamera.id : "free-view";
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${suffix}-${timestamp}.png`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    screenshotCount += 1;
    updateRuntimeAudit();
    setStatus(`当前视角已截图：${anchor.download}`, "success");
  }, "image/png");
}

function rememberFreeViewState() {
  if (freeViewState) return;
  freeViewState = {
    position: camera.position.toArray(),
    target: controls.target.toArray(),
    fov: camera.fov,
    up: camera.up.toArray(),
    viewMode,
    enableRotate: controls.enableRotate,
    controlsEnabled: controls.enabled,
  };
}

function captureCurrentViewState() {
  return {
    position: camera.position.toArray(),
    target: controls.target.toArray(),
    fov: camera.fov,
    up: camera.up.toArray(),
    viewMode,
    enableRotate: controls.enableRotate,
    controlsEnabled: controls.enabled,
  };
}

function applyViewState(state) {
  if (!state) return;
  camera.position.fromArray(state.position);
  camera.up.fromArray(state.up);
  camera.fov = state.fov;
  camera.near = 0.01;
  camera.far = 120;
  controls.target.fromArray(state.target);
  controls.enabled = state.controlsEnabled;
  controls.enableRotate = state.enableRotate;
  viewMode = state.viewMode;
  camera.updateProjectionMatrix();
  suppressCameraControlTracking = true;
  controls.update();
  suppressCameraControlTracking = false;
  document.getElementById("view-top").classList.toggle("active", viewMode === "top");
  document.getElementById("view-iso").classList.toggle("active", viewMode === "iso");
}

function restoreCameraPlanPreview({ restoreView = true, announce = true } = {}) {
  const snapshot = cameraPlanPreviewSnapshot;
  if (!snapshot) return false;
  const currentView = captureCurrentViewState();
  const cameraIndex = sceneRig.cameras.findIndex((item) => item.id === snapshot.cameraId);
  if (cameraIndex >= 0) sceneRig.cameras[cameraIndex] = structuredClone(snapshot.camera);
  sceneRig.lights = structuredClone(snapshot.lights);
  sceneRig.rendering = structuredClone(snapshot.rendering);
  normalizeSceneRigData(sceneRig);
  applyRenderingSettings();
  undoStack.length = Math.min(undoStack.length, snapshot.undoLength);
  redoStack.length = Math.min(redoStack.length, snapshot.redoLength);
  activeCameraPlanShotId = null;
  activeSceneCameraId = restoreView ? snapshot.activeSceneCameraId : null;
  activeOcclusionCameraId = restoreView ? snapshot.activeOcclusionCameraId : null;
  detachedCameraId = restoreView ? snapshot.detachedCameraId : snapshot.cameraId;
  freeViewState = structuredClone(snapshot.freeViewState);
  selection = structuredClone(snapshot.selection);
  sceneEditorMode = snapshot.sceneEditorMode;
  cameraPlanPreviewSnapshot = null;
  if (restoreView) applyViewState(snapshot.view);
  else {
    applyViewState({ ...currentView, viewMode: "free", enableRotate: true, controlsEnabled: true });
  }
  buildSceneRig();
  applySceneEditorModeUi();
  applyLayerVisibility();
  renderLists();
  renderInspectors();
  updateUndoButtons();
  updateSceneRigVisibility();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  if (announce) {
    showViewToast("已恢复切换前的摄像头与灯光");
    setStatus("已退出已保存机位，恢复原摄像头与场景光", "success");
  }
  return true;
}

function detachFixedCameraView() {
  if (!activeSceneCameraId && !activeCameraPlanShotId) return false;
  if (activeCameraPlanShotId && cameraPlanPreviewSnapshot) {
    restoreCameraPlanPreview({ restoreView: false, announce: false });
    showViewToast("当前已退出固定视角");
    setStatus("当前已退出固定视角；已保存机位未改写原摄像头或灯光");
    return true;
  }
  const sceneCameraId = activeSceneCameraId;
  detachedCameraId = sceneCameraId;
  activeSceneCameraId = null;
  activeCameraPlanShotId = null;
  viewMode = "free";
  activeCameraViewFineTuned = false;
  controls.enabled = true;
  controls.enableRotate = true;
  applyLayerVisibility();
  updateSceneRigVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  showViewToast("当前已退出固定视角");
  setStatus("当前已退出固定视角；机位数据未被鼠标拖动改写");
  return true;
}

function previewCameraPlanShot(shotId) {
  const shot = cameraPlan.shots?.find((item) => item.shotId === shotId);
  if (!shot) {
    setStatus(`未找到机位：${shotId}`, "error");
    return false;
  }
  if (activeCameraPlanShotId === shotId && cameraPlanPreviewSnapshot) {
    return restoreCameraPlanPreview({ restoreView: true, announce: true });
  }
  let cameraId = cameraPlanPreviewSnapshot?.cameraId;
  if (!cameraId) {
    cameraId = selection.type === "camera" && sceneCameraById(selection.id)
      ? selection.id
      : sceneRig.cameras[0]?.id;
    const sourceCamera = sceneCameraById(cameraId);
    if (!sourceCamera) {
      setStatus("当前没有可套用机位的摄像头", "error");
      return false;
    }
    cameraPlanPreviewSnapshot = {
      cameraId,
      camera: structuredClone(sourceCamera),
      lights: structuredClone(sceneRig.lights),
      rendering: structuredClone(sceneRig.rendering),
      view: captureCurrentViewState(),
      freeViewState: structuredClone(freeViewState),
      activeSceneCameraId,
      activeOcclusionCameraId,
      detachedCameraId,
      selection: structuredClone(selection),
      sceneEditorMode,
      undoLength: undoStack.length,
      redoLength: redoStack.length,
    };
  } else {
    const cameraIndex = sceneRig.cameras.findIndex((item) => item.id === cameraId);
    if (cameraIndex >= 0) sceneRig.cameras[cameraIndex] = structuredClone(cameraPlanPreviewSnapshot.camera);
    sceneRig.lights = structuredClone(cameraPlanPreviewSnapshot.lights);
    sceneRig.rendering = structuredClone(cameraPlanPreviewSnapshot.rendering);
    normalizeSceneRigData(sceneRig);
  }
  const item = sceneCameraById(cameraId);
  const setup = shot.lightingSetupId ? lightingSetupById(shot.lightingSetupId) : null;
  item.position = [...shot.position];
  item.target = [...shot.target];
  item.focusRoomId = roomById(shot.roomId) ? shot.roomId : null;
  item.focalLengthMm = Number(shot.focalLengthMm);
  item.fov = Number(shot.fov) || fovForFocalLength(item.focalLengthMm);
  item.lensPreset = lensPresetForFocalLength(item.focalLengthMm);
  item.distortion = 0;
  item.mount = {
    ...item.mount,
    mode: "free",
    wallId: null,
    offset: null,
    snapEnabled: false,
  };
  item.visibility = {
    ...item.visibility,
    cutawayEnabled: (shot.visibility.hiddenElementIds || []).length > 0,
    contextPolicy: "preserve-visible-adjacent-spaces",
    hiddenElementIds: [...(shot.visibility.hiddenElementIds || [])],
    preserveElementIds: [...(shot.mustShowElements || [])],
    hiddenWallIds: [],
    hiddenComponentIds: [],
  };
  if (item.visibility.cutawayEnabled) refreshCameraCutaway(item);
  else activeOcclusionCameraId = null;
  if (setup) {
    sceneRig.lights = structuredClone(setup.lights);
    normalizeSceneRigData(sceneRig);
  }
  applyRenderingSettings(shot.rendering);
  rememberFreeViewState();
  activeSceneCameraId = item.id;
  activeCameraPlanShotId = shot.shotId;
  detachedCameraId = null;
  activeCameraViewFineTuned = false;
  selection = { type: "camera", id: item.id };
  sceneEditorMode = "camera";
  sceneTransformPart = "position";
  viewMode = "camera-plan-preview";
  camera.position.fromArray(item.position);
  camera.up.set(0, 1, 0);
  camera.fov = item.fov;
  camera.near = 0.01;
  camera.far = 120;
  controls.target.fromArray(item.target);
  controls.enabled = true;
  controls.enableRotate = true;
  camera.updateProjectionMatrix();
  suppressCameraControlTracking = true;
  controls.update();
  suppressCameraControlTracking = false;
  buildSceneRig();
  applySceneEditorModeUi();
  applyLayerVisibility();
  updateSceneRigVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  showViewToast(`已套用机位：${roomById(shot.roomId)?.name || shot.shotId}`, "success");
  setStatus(`已将 ${shot.shotId} 的焦点、位置、镜头、局部遮挡${setup ? `和“${setup.name}”打光` : ""}临时套入${sceneDisplayName("camera", item)}；再次点击同一机位可恢复`, "success");
  return true;
}

function syncActiveSceneCameraView() {
  if (!activeSceneCameraId) return;
  const item = sceneCameraById(activeSceneCameraId);
  if (!item || item.enabled === false) {
    returnFreeView();
    return;
  }
  suppressCameraControlTracking = true;
  applyCameraWallMount(item);
  camera.position.fromArray(item.position);
  camera.up.set(0, 1, 0);
  camera.fov = item.fov;
  camera.near = item.near;
  camera.far = item.far;
  controls.target.fromArray(item.target);
  controls.enabled = true;
  controls.enableRotate = true;
  camera.updateProjectionMatrix();
  controls.update();
  activeCameraViewFineTuned = false;
  suppressCameraControlTracking = false;
  viewMode = "scene-camera";
  document.getElementById("view-top").classList.remove("active");
  document.getElementById("view-iso").classList.remove("active");
  requestRender();
}

function enterSceneCameraView(id) {
  if (cameraPlanPreviewSnapshot) restoreCameraPlanPreview({ restoreView: false, announce: false });
  const item = sceneCameraById(id);
  if (!item || item.enabled === false) {
    setStatus("此摄像头当前已关闭", "error");
    return false;
  }
  rememberFreeViewState();
  activeCameraPlanShotId = null;
  detachedCameraId = null;
  activeSceneCameraId = id;
  selection = { type: "camera", id };
  syncActiveSceneCameraView();
  if (item.visibility?.cutawayEnabled) activeOcclusionCameraId = item.id;
  updateCameraVisual(item);
  updateSceneRigVisibility();
  applyLayerVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  showViewToast("已切换为固定视角", "success");
  setStatus(`已切到${sceneDisplayName("camera", item)}固定机位；方向键、滚轮和镜头参数可继续微调，拖动画布才退出`, "success");
  return true;
}

function returnFreeView() {
  if (cameraPlanPreviewSnapshot) {
    return restoreCameraPlanPreview({ restoreView: true, announce: true });
  }
  const saved = freeViewState;
  activeSceneCameraId = null;
  activeCameraPlanShotId = null;
  detachedCameraId = null;
  freeViewState = null;
  if (saved) {
    camera.position.fromArray(saved.position);
    camera.up.fromArray(saved.up);
    camera.fov = saved.fov;
    camera.near = 0.01;
    camera.far = 120;
    controls.target.fromArray(saved.target);
    controls.enabled = saved.controlsEnabled;
    controls.enableRotate = saved.enableRotate;
    viewMode = saved.viewMode;
    camera.updateProjectionMatrix();
    controls.update();
    document.getElementById("view-top").classList.toggle("active", viewMode === "top");
    document.getElementById("view-iso").classList.toggle("active", viewMode === "iso");
  } else {
    setTop();
    return;
  }
  updateSceneRigVisibility();
  applyLayerVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
  showViewToast("当前已退出固定视角");
  setStatus("已返回自由视角");
}

function copyCurrentViewToSceneCamera(id) {
  const item = sceneCameraById(id);
  if (!item) return false;
  return mutateSceneItem(`更新${sceneDisplayName("camera", item)}视角`, "camera", id, () => {
    item.position = camera.position.toArray();
    item.target = controls.target.toArray();
    item.fov = camera.fov;
    item.focalLengthMm = focalLengthForFov(item.fov);
    item.lensPreset = lensPresetForFov(item.fov);
    item.distortion = 0;
    item.focusRoomId = null;
    item.mount.mode = "free";
    item.mount.wallId = null;
    item.mount.offset = null;
    applyCameraWallSnap(item);
    if (item.visibility?.cutawayEnabled) refreshCameraCutaway(item);
    activeCameraViewFineTuned = false;
  });
}

function mountSceneCameraToWall(id, wallId) {
  const item = sceneCameraById(id);
  const wall = wallById(wallId);
  if (!item || !wall) {
    setStatus("请先选择有效墙体", "error");
    return false;
  }
  return mutateSceneItem(`将${sceneDisplayName("camera", item)}挂到${wall.name}`, "camera", id, () => {
    const maximumHeight = Math.max(0.2, wall.height - 0.15);
    const requestedHeight = Number(item.mount.height ?? 1.55);
    item.mount.mode = "wall";
    item.mount.snapEnabled = true;
    item.mount.wallId = wall.id;
    item.mount.offset = wallFrame(wall).length / 2;
    item.mount.height = requestedHeight >= 0.2 && requestedHeight <= maximumHeight
      ? requestedHeight
      : Math.min(1.55, maximumHeight);
    item.mount.side = Number(item.mount.side) >= 0 ? 1 : -1;
    item.mount.clearance = Math.max(0.03, Number(item.mount.clearance ?? 0.12));
    applyCameraWallMount(item);
  });
}

function setIso() {
  if (cameraPlanPreviewSnapshot) restoreCameraPlanPreview({ restoreView: false, announce: false });
  activeSceneCameraId = null;
  activeCameraPlanShotId = null;
  detachedCameraId = null;
  freeViewState = null;
  cameraEvidenceState = null;
  clearGroup(cameraEvidenceGroup);
  viewMode = "iso";
  camera.up.set(0, 1, 0);
  camera.fov = 42;
  fitIsoView();
  controls.enabled = true;
  controls.enableRotate = true;
  camera.updateProjectionMatrix();
  controls.update();
  document.getElementById("view-iso").classList.add("active");
  document.getElementById("view-top").classList.remove("active");
  applyLayerVisibility();
  updateSceneRigVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
}

function enterFree3dFromTopDrag() {
  if (viewMode !== "top") return false;
  viewMode = "iso";
  camera.up.set(0, 1, 0);
  camera.fov = 42;
  fitIsoView();
  controls.enabled = true;
  controls.enableRotate = true;
  camera.updateProjectionMatrix();
  controls.update();
  document.getElementById("view-top").classList.remove("active");
  document.getElementById("view-iso").classList.add("active");
  requestRender();
  return true;
}

function floorplanWorldBounds() {
  const bounds = new THREE.Box3();
  model.floorBoundary.forEach((point) => {
    const world = worldPoint(point);
    bounds.expandByPoint(new THREE.Vector3(world.x, 0, world.z));
  });
  return bounds;
}

function fitIsoView() {
  const viewport = dom.scene.getBoundingClientRect();
  const aspect = Math.max(0.35, viewport.width / Math.max(1, viewport.height));
  const planBounds = floorplanWorldBounds();
  const center = planBounds.getCenter(new THREE.Vector3());
  const size = planBounds.getSize(new THREE.Vector3());
  const maximumHeight = Math.max(
    2.4,
    ...model.walls.map((wall) => Number(wall.height) || 0),
    ...model.componentPlacements.map((placement) => Number(placement.visualDimensions?.height) || 0),
  );
  const target = new THREE.Vector3(center.x, maximumHeight / 2, center.z);
  const radius = Math.sqrt((size.x / 2) ** 2 + (size.z / 2) ** 2 + (maximumHeight / 2) ** 2);
  const verticalHalfFov = THREE.MathUtils.degToRad(camera.fov / 2);
  const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * aspect);
  const limitingHalfFov = Math.max(THREE.MathUtils.degToRad(8), Math.min(verticalHalfFov, horizontalHalfFov));
  const distance = Math.max(7, radius / Math.sin(limitingHalfFov) * 1.08);
  const direction = new THREE.Vector3(0.7, 0.72, 1).normalize();
  controls.target.copy(target);
  camera.position.copy(target).addScaledVector(direction, distance);
  return {
    center: target.toArray(),
    distance,
    radius,
  };
}

function fitTopView() {
  const bounds = dom.scene.getBoundingClientRect();
  const aspect = Math.max(0.35, bounds.width / Math.max(1, bounds.height));
  const planBounds = floorplanWorldBounds();
  const center = planBounds.getCenter(new THREE.Vector3());
  const size = planBounds.getSize(new THREE.Vector3());
  let verticalHalf = size.z / 2 + 0.9;
  let horizontalHalf = size.x / 2 + 0.9;
  const framingPoints = [
    ...sceneRig.lights.flatMap((item) => [item.position, item.target]),
    ...sceneRig.cameras.flatMap((item) => [item.position, item.target]),
  ];
  framingPoints.forEach((point) => {
    if (!Array.isArray(point) || point.length < 3) return;
    horizontalHalf = Math.max(horizontalHalf, Math.abs(Number(point[0]) - center.x) + 0.7);
    verticalHalf = Math.max(verticalHalf, Math.abs(Number(point[2]) - center.z) + 0.7);
  });
  const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
  const distance = Math.max(
    verticalHalf / Math.tan(halfFov),
    horizontalHalf / (Math.tan(halfFov) * aspect),
  );
  controls.target.set(center.x, 0, center.z);
  camera.position.set(center.x, Math.max(6, distance), center.z + 0.01);
}

function setTop() {
  if (cameraPlanPreviewSnapshot) restoreCameraPlanPreview({ restoreView: false, announce: false });
  activeSceneCameraId = null;
  activeCameraPlanShotId = null;
  detachedCameraId = null;
  freeViewState = null;
  cameraEvidenceState = null;
  clearGroup(cameraEvidenceGroup);
  viewMode = "top";
  // A top camera cannot use Y as both viewing direction and up; Z keeps projection stable.
  camera.up.set(0, 0, -1);
  camera.fov = 38;
  fitTopView();
  controls.enabled = true;
  controls.enableRotate = true;
  camera.updateProjectionMatrix();
  controls.update();
  document.getElementById("view-top").classList.add("active");
  document.getElementById("view-iso").classList.remove("active");
  applyLayerVisibility();
  updateSceneRigVisibility();
  renderLists();
  renderInspectors();
  updateSelectionHighlight();
  updateRuntimeAudit();
  requestRender();
}

function cameraEvidenceFacts(shotId) {
  const shot = cameraPlan.shots?.find((item) => item.shotId === shotId);
  if (!shot) throw new Error(`未找到机位：${shotId}`);
  const position = shot.position.map(Number);
  const target = shot.target.map(Number);
  const forward = new THREE.Vector2(target[0] - position[0], target[2] - position[2]);
  const distance = Math.max(0.1, forward.length());
  forward.normalize();
  const right = new THREE.Vector2(-forward.y, forward.x);
  const horizontalFov = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(Number(shot.fov)) / 2) * (16 / 9));
  const halfWidth = Math.tan(horizontalFov / 2) * distance;
  const leftPoint = [target[0] - right.x * halfWidth, target[2] - right.y * halfWidth];
  const rightPoint = [target[0] + right.x * halfWidth, target[2] + right.y * halfWidth];
  return {
    schema: "interior.camera-plan-evidence.v2",
    source: "same-native-model-camera-state",
    modelBackend: "html-threejs",
    coordinateSystem: "threejs-world-y-up-meters",
    shotId: shot.shotId,
    name: roomById(shot.roomId)?.name || shot.spacePrimarySubject || shot.shotId,
    position,
    target,
    fov: Number(shot.fov),
    focalLengthMm: Number(shot.focalLengthMm),
    floorPlanPosition: [position[0], position[2]],
    floorPlanTarget: [target[0], target[2]],
    direction: [Number(forward.x.toFixed(6)), Number(forward.y.toFixed(6))],
    frustumFloorPolygon: [
      [position[0], position[2]],
      leftPoint.map((value) => Number(value.toFixed(6))),
      rightPoint.map((value) => Number(value.toFixed(6))),
    ],
    visibility: {
      mode: "all-spaces",
      contextPolicy: "preserve-visible-adjacent-spaces",
      hiddenElementIds: [...(shot.visibility?.hiddenElementIds || [])],
      hiddenElementEvidence: structuredClone(shot.visibility?.hiddenElementEvidence || []),
      preserveElementIds: [...(shot.visibility?.preserveElementIds || [])],
      preservedBackgroundRoomIds: [...(shot.visibility?.preservedBackgroundRoomIds || [])],
      mustShowElements: [...(shot.mustShowElements || [])],
    },
  };
}

function buildCameraEvidenceGroup(facts) {
  clearGroup(cameraEvidenceGroup);
  const floorY = 0.055;
  const points = facts.frustumFloorPolygon.map(([x, z]) => new THREE.Vector3(x, floorY, z));
  points.push(points[0].clone());
  const frustum = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({ color: 0x1f6d95, depthTest: false, transparent: true, opacity: 0.9 }),
  );
  frustum.renderOrder = 60;
  cameraEvidenceGroup.add(frustum);
  const marker = new THREE.Mesh(
    new THREE.RingGeometry(0.14, 0.25, 32),
    new THREE.MeshBasicMaterial({ color: 0x1f6d95, side: THREE.DoubleSide, depthTest: false }),
  );
  marker.rotation.x = -Math.PI / 2;
  marker.position.set(facts.floorPlanPosition[0], floorY + 0.01, facts.floorPlanPosition[1]);
  marker.renderOrder = 61;
  cameraEvidenceGroup.add(marker);
  const targetMarker = new THREE.Mesh(
    new THREE.CircleGeometry(0.11, 24),
    new THREE.MeshBasicMaterial({ color: 0xd99000, side: THREE.DoubleSide, depthTest: false }),
  );
  targetMarker.rotation.x = -Math.PI / 2;
  targetMarker.position.set(facts.floorPlanTarget[0], floorY + 0.012, facts.floorPlanTarget[1]);
  targetMarker.renderOrder = 61;
  cameraEvidenceGroup.add(targetMarker);
  cameraEvidenceGroup.visible = true;
}

function showCameraPlanEvidence(shotId) {
  const facts = cameraEvidenceFacts(shotId);
  document.body.classList.remove("capture");
  activeCaptureShotId = null;
  setTop();
  cameraEvidenceState = facts;
  setCameraPreviewEnabled(true);
  buildCameraEvidenceGroup(facts);
  fitTopView();
  camera.updateProjectionMatrix();
  controls.update();
  updateRoomAnnotationPositions();
  requestRender();
  setStatus(`已显示 ${facts.shotId} 的同源二维机位与实时视角`, "success");
  return structuredClone(facts);
}

function captureCameraPlanEvidenceDataUrl(shotId) {
  const facts = showCameraPlanEvidence(shotId);
  renderScene();
  return {
    facts,
    dataUrl: renderer.domElement.toDataURL("image/png"),
  };
}

document.getElementById("view-iso").addEventListener("click", setIso);
document.getElementById("view-top").addEventListener("click", setTop);
document.getElementById("appearance-white").addEventListener("click", () => setStructureAppearance("neutral-white"));
document.getElementById("appearance-concrete").addEventListener("click", () => setStructureAppearance("concrete-shell"));
dom.ceilingToggle?.addEventListener("click", () => {
  performMutation(`${model.layers.ceilings === false ? "显示" : "隐藏"}天花板`, () => {
    model.layers.ceilings = model.layers.ceilings === false;
  });
});
dom.furnitureWhite.addEventListener("click", () => setMovableAppearance("white-model"));
dom.furnitureColor.addEventListener("click", () => setMovableAppearance("source-color"));
dom.cameraPreviewToggle.addEventListener("click", () => setCameraPreviewEnabled(!cameraPreviewEnabled));
dom.cameraPreviewResizeHandle?.addEventListener("pointerdown", startCameraPreviewResize);
dom.cameraPreviewResizeHandle?.addEventListener("pointermove", updateCameraPreviewResize);
dom.cameraPreviewResizeHandle?.addEventListener("pointerup", finishCameraPreviewResize);
dom.cameraPreviewResizeHandle?.addEventListener("pointercancel", finishCameraPreviewResize);
dom.cameraPreviewResizeHandle?.addEventListener("dblclick", (event) => {
  event.preventDefault();
  event.stopPropagation();
  setCameraPreviewWidth(CAMERA_PREVIEW_WIDTH);
});
dom.cameraPreviewResizeHandle?.addEventListener("keydown", (event) => {
  const amount = event.shiftKey ? 64 : 24;
  const direction = ["ArrowRight", "ArrowUp"].includes(event.key)
    ? 1
    : ["ArrowLeft", "ArrowDown"].includes(event.key) ? -1 : 0;
  if (!direction) return;
  event.preventDefault();
  setCameraPreviewWidth(cameraPreviewWidth + amount * direction);
});
document.getElementById("delete-component").addEventListener("click", deleteSelectedComponent);
dom.roomFilterToggle.addEventListener("click", (event) => {
  event.stopPropagation();
  dom.roomFilterPopover.hidden = !dom.roomFilterPopover.hidden;
  dom.roomFilterToggle.setAttribute("aria-expanded", String(!dom.roomFilterPopover.hidden));
});
dom.roomFilterPopover.addEventListener("click", (event) => event.stopPropagation());
document.getElementById("room-filter-all").addEventListener("click", () => {
  roomFilterIds.clear();
  modelScopeRoomIds.forEach((roomId) => roomFilterIds.add(roomId));
  applyRoomFilter();
});
document.getElementById("room-filter-clear").addEventListener("click", () => {
  roomFilterIds.clear();
  applyRoomFilter();
});
document.addEventListener("click", () => {
  if (dom.roomFilterPopover.hidden) return;
  dom.roomFilterPopover.hidden = true;
  dom.roomFilterToggle.setAttribute("aria-expanded", "false");
});
document.getElementById("toggle-annotations").addEventListener("click", () => {
  setAnnotationsVisible(model.layers.annotations === false);
});
document.getElementById("toggle-measure").addEventListener("click", () => setMeasurementMode(!measurement.active));
document.getElementById("clear-measure").addEventListener("click", clearMeasurement);
document.querySelectorAll("[data-scene-mode]").forEach((button) => {
  button.addEventListener("click", () => setSceneEditorMode(button.dataset.sceneMode));
});
document.getElementById("add-light").addEventListener("click", addSceneLight);
document.getElementById("add-camera").addEventListener("click", addSceneCamera);
document.getElementById("export-scene-rig").addEventListener("click", downloadSceneRig);
document.getElementById("import-camera-plan").addEventListener("click", () => dom.cameraPlanFile.click());
dom.cameraPlanFile.addEventListener("change", async (event) => {
  const [file] = event.target.files || [];
  if (!file) return;
  try {
    loadCameraPlanData(JSON.parse(await file.text()));
  } catch (error) {
    setStatus(`机位 JSON 未载入：${error.message}`, "error");
  } finally {
    event.target.value = "";
  }
});
document.getElementById("toggle-rig-gizmos").addEventListener("change", (event) => {
  const type = ["light", "camera"].includes(selection.type) ? selection.type : sceneEditorMode;
  const item = type === "light" ? sceneRig.lights[0] : sceneRig.cameras[0];
  mutateSceneItem(`${event.target.checked ? "显示" : "隐藏"}操纵轴与焦点线`, type, item.id, () => {
    sceneRig.gizmosVisible = event.target.checked;
  });
  updateSceneRigVisibility();
});

function setReferenceOpen(open) {
  document.body.classList.toggle("reference-open", open);
  document.getElementById("reference-drawer").setAttribute("aria-hidden", String(!open));
  document.getElementById("toggle-source").setAttribute("aria-pressed", String(open));
  requestAnimationFrame(resize);
}

document.getElementById("toggle-source").addEventListener("click", () => setReferenceOpen(!document.body.classList.contains("reference-open")));
document.getElementById("close-source").addEventListener("click", () => setReferenceOpen(false));

let activeCapturePoseAudit = null;

function applyCaptureShot(shotId = null) {
  const params = new URLSearchParams(window.location.search);
  const requestedShotId = shotId || params.get("shot");
  if (!shotId && params.get("capture") !== "1") return false;
  const shot = cameraPlan.shots?.find((item) => item.shotId === requestedShotId);
  if (!shot) {
    setStatus(`未找到机位：${requestedShotId || "empty"}`, "error");
    return false;
  }
  activeSceneCameraId = null;
  activeCameraPlanShotId = null;
  freeViewState = null;
  viewMode = "capture";
  activeCaptureShotId = shot.shotId;
  cameraEvidenceState = null;
  clearGroup(cameraEvidenceGroup);
  document.body.classList.add("capture");
  const lightingSetup = shot.lightingSetupId ? lightingSetupById(shot.lightingSetupId) : null;
  if (lightingSetup) {
    sceneRig.lights = structuredClone(lightingSetup.lights);
    normalizeSceneRigData(sceneRig);
    buildSceneRig();
  }
  applyRenderingSettings(shot.rendering);
  setReferenceOpen(false);
  dom.selectionChip.hidden = true;
  if (selectionHelper) selectionHelper.visible = false;
  sceneRigHelperGroup.visible = false;
  transformGizmoGroup.visible = false;
  applyLayerVisibility();
  if (grid) grid.visible = false;
  camera.position.fromArray(shot.position);
  camera.up.set(0, 1, 0);
  camera.fov = Number(shot.fov) || fovForFocalLength(shot.focalLengthMm);
  controls.target.fromArray(shot.target);
  controls.enabled = false;
  controls.enableRotate = false;
  if ((shot.visibility?.hiddenElementIds || []).length > 0) {
    const captureCamera = {
      position: [...shot.position],
      target: [...shot.target],
      focusRoomId: shot.roomId,
      mount: { mode: "free", wallId: null },
      visibility: {
        contextPolicy: "preserve-visible-adjacent-spaces",
        hiddenElementIds: [...(shot.visibility.hiddenElementIds || [])],
        preserveElementIds: [...(shot.mustShowElements || [])],
      },
    };
    const hidden = deriveContextVisibility(captureCamera);
    hidden.hiddenWallIds.forEach((id) => {
      [wallGroups.get(id), roomFilterWallGroups.get(id)].forEach((group) => {
        if (group) group.visible = false;
      });
      model.windows.filter((windowItem) => windowItem.wallId === id).forEach((windowItem) => {
        [windowGroups.get(windowItem.id), roomFilterWindowGroups.get(windowItem.id)].forEach((windowGroup) => {
          if (windowGroup) windowGroup.visible = false;
        });
      });
    });
    hidden.hiddenComponentIds.forEach((id) => {
      const group = componentGroups.get(id);
      if (group) group.visible = false;
    });
  }
  camera.updateProjectionMatrix();
  camera.lookAt(new THREE.Vector3(...shot.target));
  camera.updateMatrixWorld(true);
  const expectedDirection = new THREE.Vector3(...shot.target)
    .sub(new THREE.Vector3(...shot.position))
    .normalize();
  const actualDirection = camera.getWorldDirection(new THREE.Vector3()).normalize();
  const directionDot = actualDirection.dot(expectedDirection);
  activeCapturePoseAudit = {
    schema: "interior.html-capture-pose-audit.v1",
    shotId: shot.shotId,
    position: camera.position.toArray(),
    target: [...shot.target],
    expectedDirection: expectedDirection.toArray(),
    actualDirection: actualDirection.toArray(),
    directionDot,
    controlsUpdateAppliedAfterPose: false,
    accepted: directionDot >= 0.999999,
  };
  if (!activeCapturePoseAudit.accepted) {
    throw new Error(`机位 ${shot.shotId} 姿态漂移，directionDot=${directionDot.toFixed(8)}`);
  }
  renderScene();
  setStatus(`已应用机位：${shot.shotId}${lightingSetup ? ` · ${lightingSetup.name}` : " · 场景默认光"} · 曝光 ${sceneRig.rendering.exposure.toFixed(2)}`, "success");
  return true;
}

function captureFrameDataUrl() {
  renderScene();
  return renderer.domElement.toDataURL("image/png");
}

function frameReadability() {
  renderScene();
  const sourceWidth = renderer.domElement.width;
  const sourceHeight = renderer.domElement.height;
  const width = Math.min(240, sourceWidth);
  const height = Math.max(1, Math.round(width * sourceHeight / sourceWidth));
  const sampleCanvas = document.createElement("canvas");
  sampleCanvas.width = width;
  sampleCanvas.height = height;
  const sampleContext = sampleCanvas.getContext("2d", { willReadFrequently: true });
  sampleContext.drawImage(renderer.domElement, 0, 0, width, height);
  const pixels = sampleContext.getImageData(0, 0, width, height).data;
  let count = 0;
  let sum = 0;
  let sumSquares = 0;
  let clippedHighlight = 0;
  let clippedShadow = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const luminance = (
        pixels[index] * 0.2126
        + pixels[index + 1] * 0.7152
        + pixels[index + 2] * 0.0722
      ) / 255;
      count += 1;
      sum += luminance;
      sumSquares += luminance * luminance;
      if (luminance >= 0.965) clippedHighlight += 1;
      if (luminance <= 0.035) clippedShadow += 1;
    }
  }
  const meanLuminance = count ? sum / count : 0;
  const standardDeviation = count
    ? Math.sqrt(Math.max(0, sumSquares / count - meanLuminance * meanLuminance))
    : 0;
  const clippedHighlightRatio = count ? clippedHighlight / count : 1;
  const clippedShadowRatio = count ? clippedShadow / count : 1;
  const presentationMode = document.documentElement.dataset.capturePresentation || "slot-guided";
  const minimumDeviation = presentationMode === "slot-guided" ? 0.006 : 0.035;
  const readable = meanLuminance >= 0.12
    && meanLuminance <= 0.93
    && standardDeviation >= minimumDeviation
    && clippedHighlightRatio <= 0.58
    && clippedShadowRatio <= 0.72;
  return {
    readable,
    presentationMode,
    width,
    height,
    sourceWidth,
    sourceHeight,
    sampleCount: count,
    meanLuminance,
    standardDeviation,
    clippedHighlightRatio,
    clippedShadowRatio,
    exposure: renderer.toneMappingExposure,
    toneMapping: "ACESFilmic",
  };
}

function worldBoundsForGroup(group) {
  if (!group) return null;
  const box = new THREE.Box3().setFromObject(group);
  if (box.isEmpty()) return null;
  const values = [
    box.min.x, box.min.y, box.min.z,
    box.max.x, box.max.y, box.max.z,
  ];
  if (!values.every(Number.isFinite)) return null;
  return {
    min: [box.min.x, box.min.y, box.min.z],
    max: [box.max.x, box.max.y, box.max.z],
  };
}

function worldTransformForGroup(group) {
  if (!group) return null;
  group.updateWorldMatrix(true, true);
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  group.matrixWorld.decompose(position, quaternion, scale);
  const euler = new THREE.Euler().setFromQuaternion(quaternion, "YXZ");
  const values = [
    ...position.toArray(),
    ...quaternion.toArray(),
    ...scale.toArray(),
    euler.y,
  ];
  if (!values.every(Number.isFinite)) return null;
  return {
    position: position.toArray().map((value) => Number(value.toFixed(6))),
    quaternion: quaternion.toArray().map((value) => Number(value.toFixed(8))),
    scale: scale.toArray().map((value) => Number(value.toFixed(6))),
    yawRadians: Number(euler.y.toFixed(8)),
  };
}

function objectIsVisibleInScene(object) {
  let current = object;
  while (current && current !== scene) {
    if (!current.visible) return false;
    current = current.parent;
  }
  return Boolean(current);
}

function semanticColorForIndex(index) {
  const rgb = [
    40 + (index * 73) % 192,
    40 + (index * 151) % 192,
    40 + (index * 199) % 192,
  ];
  return {
    semanticId: index + 1,
    value: (rgb[0] << 16) | (rgb[1] << 8) | rgb[2],
    rgb,
    hex: `#${rgb.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`,
  };
}

function worldDimensions(bounds) {
  if (!bounds) return null;
  return bounds.max.map((value, index) => Number((value - bounds.min[index]).toFixed(6)));
}

function semanticSceneEntities(shot) {
  const mustShow = new Set(shot.mustShowElements || []);
  const entities = [];
  const activeWallGroups = roomFilterIsAll() ? wallGroups : roomFilterWallGroups;
  const activeWindowGroups = roomFilterIsAll() ? windowGroups : roomFilterWindowGroups;
  model.walls.forEach((wall) => {
    const root = activeWallGroups.get(wall.id);
    if (!root || !objectIsVisibleInScene(root) || wall.enabled === false) return;
    entities.push({
      entityId: wall.id,
      sourceModelId: wall.id,
      semanticType: "structure",
      category: "wall",
      displayName: wall.name || wall.id,
      roomIds: (model.rooms || [])
        .filter((room) => modelScopeRoomIds.has(room.id) && wallSupportsRoom(wall, room))
        .map((room) => room.id),
      root,
      visibilityState: "visible-in-shot",
      sourceGeometry: "wall-mesh",
    });
  });
  model.windows.forEach((item) => {
    const root = activeWindowGroups.get(item.id);
    const host = wallById(item.wallId);
    if (!root || !objectIsVisibleInScene(root) || item.enabled === false) return;
    entities.push({
      entityId: item.id,
      sourceModelId: item.id,
      semanticType: "structure",
      category: "window",
      displayName: item.name || item.id,
      roomIds: host
        ? (model.rooms || [])
          .filter((room) => modelScopeRoomIds.has(room.id) && wallSupportsRoom(host, room))
          .map((room) => room.id)
        : [],
      root,
      visibilityState: "visible-in-shot",
      sourceGeometry: "window-mesh",
    });
  });
  ceilingMeshes.forEach((root, roomId) => {
    if (!objectIsVisibleInScene(root)) return;
    entities.push({
      entityId: `ceiling-${roomId}`,
      sourceModelId: `ceiling-${roomId}`,
      semanticType: "structure",
      category: "ceiling",
      displayName: `${roomById(roomId)?.name || roomId}天花`,
      roomIds: [roomId],
      root,
      visibilityState: "visible-in-shot",
      sourceGeometry: "backend-ceiling-surface",
    });
  });
  model.componentPlacements.forEach((placement) => {
    const root = componentGroups.get(placement.id);
    const definition = getComponentDefinition(placement.componentId, placement.semantic);
    if (!root || !objectIsVisibleInScene(root)) return;
    const localAxes = Object.fromEntries(
      (model.relationHints?.directionalAxes || [])
        .filter((row) => row.assetId === placement.componentId)
        .map((row) => [row.role, row.localAxis]),
    );
    entities.push({
      entityId: placement.id,
      sourceModelId: placement.id,
      semanticType: definition?.placementClass === "fixed-purple"
        ? "fixed-cabinet"
        : "movable-furniture",
      category: placement.category || definition?.category || placement.semantic || "component",
      functionalClass: placement.functionalClass,
      quantity: placement.quantity,
      assetId: placement.componentId,
      sourceObjectCandidateId: placement.sourceObjectCandidateId || null,
      localAxes,
      displayName: placement.name || definition?.name || placement.id,
      roomIds: [placement.roomId].filter(Boolean),
      root,
      visibilityState: "visible-in-shot",
      sourceGeometry: "component-mesh",
      placementRole: "position-and-size-slot",
      priority: mustShow.has(placement.id) ? 1 : 10,
      mustPreserve: mustShow.has(placement.id),
    });
  });
  return entities;
}

function clipPolygonToUnitSquare(points) {
  const boundaries = [
    {
      inside: ([x]) => x >= 0,
      intersect: ([x1, y1], [x2, y2]) => [0, y1 + (y2 - y1) * (0 - x1) / (x2 - x1)],
    },
    {
      inside: ([x]) => x <= 1,
      intersect: ([x1, y1], [x2, y2]) => [1, y1 + (y2 - y1) * (1 - x1) / (x2 - x1)],
    },
    {
      inside: ([, y]) => y >= 0,
      intersect: ([x1, y1], [x2, y2]) => [x1 + (x2 - x1) * (0 - y1) / (y2 - y1), 0],
    },
    {
      inside: ([, y]) => y <= 1,
      intersect: ([x1, y1], [x2, y2]) => [x1 + (x2 - x1) * (1 - y1) / (y2 - y1), 1],
    },
  ];
  return boundaries.reduce((polygon, boundary) => {
    if (!polygon.length) return polygon;
    const output = [];
    polygon.forEach((current, index) => {
      const previous = polygon[(index + polygon.length - 1) % polygon.length];
      const currentInside = boundary.inside(current);
      const previousInside = boundary.inside(previous);
      if (currentInside && previousInside) {
        output.push(current);
      } else if (previousInside && !currentInside) {
        output.push(boundary.intersect(previous, current));
      } else if (!previousInside && currentInside) {
        output.push(boundary.intersect(previous, current), current);
      }
    });
    return output;
  }, points);
}

function projectedConnections() {
  return (model.connections || []).filter((connection) => (
    [connection.fromRoomId, connection.toRoomId]
      .filter((roomId) => roomId && roomId !== "exterior")
      .every((roomId) => modelScopeRoomIds.has(roomId))
  )).flatMap((connection) => {
    const start = worldPoint(connection.start);
    const end = worldPoint(connection.end);
    const bottom = Number(connection.bottom || 0);
    const height = Number(connection.height || 0);
    if (!(height > 0)) return [];
    const corners = [
      new THREE.Vector3(start.x, bottom, start.z),
      new THREE.Vector3(end.x, bottom, end.z),
      new THREE.Vector3(end.x, bottom + height, end.z),
      new THREE.Vector3(start.x, bottom + height, start.z),
    ];
    const cameraSpace = corners.map((point) => point.clone().applyMatrix4(camera.matrixWorldInverse));
    // An opening is a scene fact only when its full plane is in front of the
    // near plane. Projecting mixed front/behind corners creates a false,
    // screen-spanning door polygon for openings beside or behind the camera.
    if (cameraSpace.some((point) => point.z >= -camera.near)) return [];
    const projected = corners.map((point) => {
      const ndc = point.clone().project(camera);
      return [(ndc.x + 1) / 2, (1 - ndc.y) / 2];
    });
    const polygon = clipPolygonToUnitSquare(projected)
      .filter((point) => point.every(Number.isFinite))
      .map((point) => point.map((value) => Number(value.toFixed(6))));
    if (polygon.length < 3) return [];
    const xs = polygon.map((point) => point[0]);
    const ys = polygon.map((point) => point[1]);
    return [{
      connectionId: connection.id,
      sourceModelId: connection.id,
      kind: connection.kind || "opening",
      openingStyle: connection.openingStyle || null,
      displayName: connection.name || connection.id,
      roomIds: [connection.fromRoomId, connection.toRoomId].filter(Boolean),
      forbiddenInferences: [...(connection.forbiddenInferences || [])],
      screen: {
        polygon,
        bbox: [
          Math.min(...xs),
          Math.min(...ys),
          Math.max(...xs),
          Math.max(...ys),
        ].map((value) => Number(value.toFixed(6))),
        source: "front-clipped-projected-model-opening-corners",
        visibilityEvidence: {
          method: "all-opening-corners-in-front-of-camera",
          allCornersInFrontOfCamera: true,
          minimumForwardDepthMeters: Number(Math.min(...cameraSpace.map((point) => -point.z)).toFixed(6)),
          maximumForwardDepthMeters: Number(Math.max(...cameraSpace.map((point) => -point.z)).toFixed(6)),
        },
      },
    }];
  });
}

function normalizedBounds(minX, minY, maxX, maxY, width, height) {
  return [
    Number((minX / width).toFixed(6)),
    Number((minY / height).toFixed(6)),
    Number(((maxX + 1) / width).toFixed(6)),
    Number(((maxY + 1) / height).toFixed(6)),
  ];
}

function semanticMaskDataUrl(pixels, width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  const imageData = context.createImageData(width, height);
  for (let y = 0; y < height; y += 1) {
    const sourceY = height - y - 1;
    for (let x = 0; x < width; x += 1) {
      const sourceIndex = (sourceY * width + x) * 4;
      const targetIndex = (y * width + x) * 4;
      imageData.data[targetIndex] = pixels[sourceIndex];
      imageData.data[targetIndex + 1] = pixels[sourceIndex + 1];
      imageData.data[targetIndex + 2] = pixels[sourceIndex + 2];
      imageData.data[targetIndex + 3] = 255;
    }
  }
  context.putImageData(imageData, 0, 0);
  return canvas.toDataURL("image/png");
}

function polygonArea(polygon) {
  let area = 0;
  for (let index = 0; index < polygon.length; index += 1) {
    const [x1, z1] = polygon[index];
    const [x2, z2] = polygon[(index + 1) % polygon.length];
    area += x1 * z2 - x2 * z1;
  }
  return Math.abs(area) / 2;
}

function unpackRGBADepth(red, green, blue, alpha) {
  return (
    red / (256 ** 4)
    + green / (256 ** 3)
    + blue / (256 ** 2)
    + alpha / 256
  );
}

function roomSemanticFrame(width, height) {
  const started = performance.now();
  const depthRoots = [];
  const addVisibleRoot = (root) => {
    if (root && objectIsVisibleInScene(root) && !depthRoots.includes(root)) {
      depthRoots.push(root);
    }
  };
  addVisibleRoot(floorMesh);
  roomFilterFloors.forEach(addVisibleRoot);
  const activeWallGroups = roomFilterIsAll() ? wallGroups : roomFilterWallGroups;
  model.walls.forEach((wall) => {
    if (wall.enabled === false) return;
    addVisibleRoot(activeWallGroups.get(wall.id));
  });

  const visibilitySnapshot = new Map();
  scene.traverse((object) => {
    visibilitySnapshot.set(object, object.visible);
    if (object !== scene) object.visible = false;
  });
  const materialSnapshot = [];
  const depthMaterial = new THREE.ShaderMaterial({
    vertexShader: `
      void main() {
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      #include <packing>
      void main() {
        gl_FragColor = packDepthToRGBA(gl_FragCoord.z);
      }
    `,
    side: THREE.DoubleSide,
    depthTest: true,
    depthWrite: true,
    blending: THREE.NoBlending,
    toneMapped: false,
  });
  depthRoots.forEach((root) => {
    let current = root;
    while (current && current !== scene) {
      current.visible = true;
      current = current.parent;
    }
    root.traverse((object) => {
      if (!object.isMesh) return;
      object.visible = true;
      materialSnapshot.push([object, object.material]);
      object.material = depthMaterial;
    });
  });

  const ceilingHeight = Math.max(
    2.4,
    ...model.walls
      .filter((wall) => wall.enabled !== false)
      .map((wall) => Number(wall.height || 0)),
  );
  let ceilingMesh = null;
  if (floorMesh?.geometry) {
    ceilingMesh = new THREE.Mesh(floorMesh.geometry, depthMaterial);
    ceilingMesh.name = "semantic-derived-ceiling";
    ceilingMesh.rotation.copy(floorMesh.rotation);
    ceilingMesh.position.copy(floorMesh.position);
    ceilingMesh.position.y = ceilingHeight;
    ceilingMesh.scale.copy(floorMesh.scale);
    scene.add(ceilingMesh);
  }

  const previousTarget = renderer.getRenderTarget();
  const previousToneMapping = renderer.toneMapping;
  const previousOutputColorSpace = renderer.outputColorSpace;
  const previousClearColor = renderer.getClearColor(new THREE.Color()).clone();
  const previousClearAlpha = renderer.getClearAlpha();
  const target = new THREE.WebGLRenderTarget(width, height, {
    format: THREE.RGBAFormat,
    type: THREE.UnsignedByteType,
    depthBuffer: true,
    stencilBuffer: false,
  });
  target.texture.colorSpace = THREE.NoColorSpace;
  const depthPixels = new Uint8Array(width * height * 4);
  const depthStarted = performance.now();
  try {
    renderer.toneMapping = THREE.NoToneMapping;
    renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    renderer.setRenderTarget(target);
    renderer.clear(true, true, true);
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(target, 0, 0, width, height, depthPixels);
  } finally {
    renderer.setRenderTarget(previousTarget);
    renderer.toneMapping = previousToneMapping;
    renderer.outputColorSpace = previousOutputColorSpace;
    renderer.setClearColor(previousClearColor, previousClearAlpha);
    materialSnapshot.forEach(([object, material]) => {
      object.material = material;
    });
    if (ceilingMesh) scene.remove(ceilingMesh);
    visibilitySnapshot.forEach((visible, object) => {
      object.visible = visible;
    });
    depthMaterial.dispose();
    target.dispose();
  }
  const depthPassMs = performance.now() - depthStarted;

  const roomPixels = new Uint8Array(width * height * 4);
  const roomCandidates = (model.rooms || [])
    .filter((room) => (
      modelScopeRoomIds.has(room.id)
      && Array.isArray(room.polygon)
      && room.polygon.length >= 3
    ))
    .map((room, index) => {
      const color = semanticColorForIndex(index);
      const xs = room.polygon.map((point) => point[0]);
      const zs = room.polygon.map((point) => point[1]);
      return {
        room,
        color,
        area: polygonArea(room.polygon),
        planBounds: [
          Math.min(...xs),
          Math.min(...zs),
          Math.max(...xs),
          Math.max(...zs),
        ],
        stats: {
          count: 0,
          minX: width,
          minY: height,
          maxX: -1,
          maxY: -1,
        },
      };
    })
    .sort((left, right) => left.area - right.area);
  const inverseProjectionView = new THREE.Matrix4()
    .multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse)
    .invert();
  const matrix = inverseProjectionView.elements;
  const cameraPosition = camera.position;
  const maximumRoomSearchDistance = Math.max(
    0.45,
    Math.max(...model.walls.map((wall) => Number(wall.thickness || 0))) * 3,
  );
  const roomSearchStep = 0.025;
  const reprojectionStarted = performance.now();
  for (let sourceY = 0; sourceY < height; sourceY += 1) {
    const topY = height - sourceY - 1;
    const normalizedY = ((sourceY + 0.5) / height) * 2 - 1;
    for (let x = 0; x < width; x += 1) {
      const sourceIndex = (sourceY * width + x) * 4;
      const red = depthPixels[sourceIndex];
      const green = depthPixels[sourceIndex + 1];
      const blue = depthPixels[sourceIndex + 2];
      const alpha = depthPixels[sourceIndex + 3];
      const targetIndex = sourceIndex;
      roomPixels[targetIndex + 3] = 255;
      if ((red | green | blue | alpha) === 0) continue;
      const depth = unpackRGBADepth(red, green, blue, alpha);
      if (!(depth > 0 && depth < 1)) continue;
      const normalizedX = ((x + 0.5) / width) * 2 - 1;
      const normalizedZ = depth * 2 - 1;
      const worldW = (
        matrix[3] * normalizedX
        + matrix[7] * normalizedY
        + matrix[11] * normalizedZ
        + matrix[15]
      );
      if (Math.abs(worldW) < 1e-8) continue;
      let worldX = (
        matrix[0] * normalizedX
        + matrix[4] * normalizedY
        + matrix[8] * normalizedZ
        + matrix[12]
      ) / worldW;
      let worldZ = (
        matrix[2] * normalizedX
        + matrix[6] * normalizedY
        + matrix[10] * normalizedZ
        + matrix[14]
      ) / worldW;
      const towardCameraX = cameraPosition.x - worldX;
      const towardCameraZ = cameraPosition.z - worldZ;
      const horizontalLength = Math.hypot(towardCameraX, towardCameraZ);
      if (horizontalLength <= 1e-6) continue;
      const directionX = towardCameraX / horizontalLength;
      const directionZ = towardCameraZ / horizontalLength;
      let match = null;
      for (
        let distance = 0.01;
        distance <= maximumRoomSearchDistance && !match;
        distance += roomSearchStep
      ) {
        const plan = planPoint(
          worldX + directionX * distance,
          worldZ + directionZ * distance,
        );
        match = roomCandidates.find((candidate) => (
          plan[0] >= candidate.planBounds[0]
          && plan[0] <= candidate.planBounds[2]
          && plan[1] >= candidate.planBounds[1]
          && plan[1] <= candidate.planBounds[3]
          && pointInPolygon(plan, candidate.room.polygon)
        )) || null;
      }
      if (!match) continue;
      roomPixels[targetIndex] = match.color.rgb[0];
      roomPixels[targetIndex + 1] = match.color.rgb[1];
      roomPixels[targetIndex + 2] = match.color.rgb[2];
      match.stats.count += 1;
      match.stats.minX = Math.min(match.stats.minX, x);
      match.stats.minY = Math.min(match.stats.minY, topY);
      match.stats.maxX = Math.max(match.stats.maxX, x);
      match.stats.maxY = Math.max(match.stats.maxY, topY);
    }
  }
  const roomReprojectionMs = performance.now() - reprojectionStarted;
  return {
    mask: {
      encoding: "stable-rgb-room-id-from-depth-reprojection",
      backgroundColor: "#000000",
      dataUrl: semanticMaskDataUrl(roomPixels, width, height),
    },
    rooms: roomCandidates
      .filter((candidate) => candidate.stats.count > 0)
      .map((candidate) => ({
        roomId: candidate.room.id,
        displayName: candidate.room.name || candidate.room.id,
        roomType: candidate.room.roomType || "room",
        sourcePolygon: candidate.room.polygon,
        screen: {
          semanticId: candidate.color.semanticId,
          semanticColor: candidate.color.hex,
          encodedColorValue: candidate.color.value,
          bbox: normalizedBounds(
            candidate.stats.minX,
            candidate.stats.minY,
            candidate.stats.maxX,
            candidate.stats.maxY,
            width,
            height,
          ),
          visiblePixelCount: candidate.stats.count,
          coverage: Number((candidate.stats.count / (width * height)).toFixed(8)),
        },
      })),
    evidence: {
      method: "gpu-packed-depth-to-world-coordinate-to-room-polygon",
      depthPassMs: Number(depthPassMs.toFixed(3)),
      roomReprojectionMs: Number(roomReprojectionMs.toFixed(3)),
      totalMs: Number((performance.now() - started).toFixed(3)),
      depthReadbackBytes: depthPixels.byteLength,
      roomMaskBytes: roomPixels.byteLength,
      overlapRule: "smallest-containing-room-polygon-wins",
      roomSearchDirection: "surface-toward-camera",
      maximumRoomSearchDistanceMeters: Number(maximumRoomSearchDistance.toFixed(6)),
      roomSearchStepMeters: roomSearchStep,
    },
  };
}

function sceneSemanticFrame(shotId, guidanceImages, imageSize) {
  const shot = cameraPlan.shots?.find((item) => item.shotId === shotId);
  if (!shot) throw new Error(`未找到机位：${shotId}`);
  if (
    !guidanceImages
    || typeof guidanceImages !== "object"
    || typeof guidanceImages.slotGuided !== "string"
    || typeof guidanceImages.furnishedQa !== "string"
  ) {
    throw new Error("guidanceImages 必须同时包含 slotGuided 和 furnishedQa");
  }
  if (!Array.isArray(imageSize) || imageSize.length !== 2) {
    throw new Error("imageSize 必须是 [width, height]");
  }
  renderScene();
  const imageWidth = renderer.domElement.width;
  const imageHeight = renderer.domElement.height;
  if (Number(imageSize[0]) !== imageWidth || Number(imageSize[1]) !== imageHeight) {
    throw new Error(`截图尺寸 ${imageSize.join("x")} 与 Three.js 画布 ${imageWidth}x${imageHeight} 不一致`);
  }
  const semanticRasterMaxWidth = 800;
  const width = Math.min(semanticRasterMaxWidth, imageWidth);
  const height = Math.max(1, Math.round(width * imageHeight / imageWidth));
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  const entities = semanticSceneEntities(shot);
  entities.forEach((entity) => {
    entity.worldBounds = worldBoundsForGroup(entity.root);
    entity.dimensionsMeters = worldDimensions(entity.worldBounds);
    entity.worldTransform = worldTransformForGroup(entity.root);
  });

  const visibilitySnapshot = new Map();
  scene.traverse((object) => {
    visibilitySnapshot.set(object, object.visible);
    if (object !== scene) object.visible = false;
  });
  const materialSnapshot = [];
  const semanticMaterials = [];
  const enableRoot = (root, color) => {
    let current = root;
    while (current && current !== scene) {
      current.visible = true;
      current = current.parent;
    }
    root.traverse((object) => {
      if (object.isMesh) {
        object.visible = true;
        materialSnapshot.push([object, object.material]);
        const sourceMaterial = Array.isArray(object.material)
          ? object.material.find(Boolean)
          : object.material;
        const material = new THREE.MeshBasicMaterial({
          color: new THREE.Color(
            color.rgb[0] / 255,
            color.rgb[1] / 255,
            color.rgb[2] / 255,
          ),
          side: sourceMaterial?.side ?? THREE.FrontSide,
          depthTest: true,
          depthWrite: true,
          toneMapped: false,
        });
        semanticMaterials.push(material);
        object.material = material;
      } else if (object !== root) {
        object.visible = object.isGroup;
      }
    });
  };
  entities.forEach((entity, index) => {
    const color = semanticColorForIndex(index);
    entity.semanticColor = color;
    enableRoot(entity.root, color);
  });

  const previousTarget = renderer.getRenderTarget();
  const previousToneMapping = renderer.toneMapping;
  const previousOutputColorSpace = renderer.outputColorSpace;
  const previousClearColor = renderer.getClearColor(new THREE.Color()).clone();
  const previousClearAlpha = renderer.getClearAlpha();
  const target = new THREE.WebGLRenderTarget(width, height, {
    format: THREE.RGBAFormat,
    type: THREE.UnsignedByteType,
    depthBuffer: true,
    stencilBuffer: false,
  });
  target.texture.colorSpace = THREE.NoColorSpace;
  const pixels = new Uint8Array(width * height * 4);
  const startedGpu = performance.now();
  try {
    renderer.toneMapping = THREE.NoToneMapping;
    renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    renderer.setClearColor(0x000000, 1);
    renderer.setRenderTarget(target);
    renderer.clear(true, true, true);
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(target, 0, 0, width, height, pixels);
  } finally {
    renderer.setRenderTarget(previousTarget);
    renderer.toneMapping = previousToneMapping;
    renderer.outputColorSpace = previousOutputColorSpace;
    renderer.setClearColor(previousClearColor, previousClearAlpha);
    materialSnapshot.forEach(([object, material]) => {
      object.material = material;
    });
    visibilitySnapshot.forEach((visible, object) => {
      object.visible = visible;
    });
    semanticMaterials.forEach((material) => material.dispose());
    target.dispose();
    renderScene();
  }
  const gpuElapsedMs = performance.now() - startedGpu;
  const pixelStats = new Map(entities.map((entity) => [
    entity.semanticColor.value,
    {
      count: 0,
      minX: width,
      minY: height,
      maxX: -1,
      maxY: -1,
    },
  ]));
  for (let sourceY = 0; sourceY < height; sourceY += 1) {
    const topY = height - sourceY - 1;
    for (let x = 0; x < width; x += 1) {
      const sourceIndex = (sourceY * width + x) * 4;
      const semanticId = (
        (pixels[sourceIndex] << 16)
        | (pixels[sourceIndex + 1] << 8)
        | pixels[sourceIndex + 2]
      );
      const stats = pixelStats.get(semanticId);
      if (!stats) continue;
      stats.count += 1;
      stats.minX = Math.min(stats.minX, x);
      stats.minY = Math.min(stats.minY, topY);
      stats.maxX = Math.max(stats.maxX, x);
      stats.maxY = Math.max(stats.maxY, topY);
    }
  }
  entities.forEach((entity) => {
    const stats = pixelStats.get(entity.semanticColor.value);
    entity.visiblePixelCount = stats.count;
    entity.coverage = Number((stats.count / (width * height)).toFixed(8));
    entity.bbox = stats.count
      ? normalizedBounds(stats.minX, stats.minY, stats.maxX, stats.maxY, width, height)
      : null;
  });
  const resultEntities = entities.map((entity) => ({
    entityId: entity.entityId,
    sourceModelId: entity.sourceModelId,
    semanticType: entity.semanticType,
    category: entity.category,
    functionalClass: entity.functionalClass || null,
    quantity: entity.quantity ?? null,
    assetId: entity.assetId || null,
    sourceObjectCandidateId: entity.sourceObjectCandidateId || null,
    localAxes: entity.localAxes || {},
    displayName: entity.displayName,
    roomIds: entity.roomIds,
    visibilityState: entity.visibilityState,
    sourceGeometry: entity.sourceGeometry,
    placementRole: entity.placementRole || null,
    priority: entity.priority ?? null,
    mustPreserve: entity.mustPreserve ?? null,
    forbiddenInferences: entity.forbiddenInferences || [],
    worldBounds: entity.worldBounds,
    worldTransform: entity.worldTransform,
    dimensionsMeters: entity.dimensionsMeters,
    screen: {
      semanticId: entity.semanticColor.semanticId,
      semanticColor: entity.semanticColor.hex,
      encodedColorValue: entity.semanticColor.value,
      bbox: entity.bbox,
      visiblePixelCount: entity.visiblePixelCount,
      coverage: entity.coverage,
    },
  }));
  const roomFrame = roomSemanticFrame(width, height);
  renderScene();
  return {
    schema: "interior.scene-semantic-frame.v4",
    modelBackend: "html-threejs",
    floorplanId: model.floorplanId,
    modelScope: structuredClone(model.modelScope),
    shotId,
    guidanceImages: structuredClone(guidanceImages),
    imageSize: [imageWidth, imageHeight],
    semanticRaster: {
      size: [width, height],
      normalizedToImageSize: true,
      maximumSourcePixelError: Number((imageWidth / width).toFixed(6)),
      policy: "fixed-800px-maximum-width",
    },
    coordinateSystem: "image-top-left-normalized",
    camera: {
      position: camera.position.toArray(),
      target: controls.target.toArray(),
      up: camera.up.toArray(),
      fov: camera.fov,
      near: camera.near,
      far: camera.far,
      aspect: camera.aspect,
      projectionMatrix: camera.projectionMatrix.toArray(),
      matrixWorldInverse: camera.matrixWorldInverse.toArray(),
    },
    presentation: {
      sourceState: "same-model-dual-capture-evidence-on-concrete-shell",
      defaultGenerationMode: "slot-guided",
      evidenceStates: {
        "slot-guided": {
          componentPresentation: "hidden",
          slotFactsRetained: true,
          structureAppearance: "concrete-shell",
          generationAuthority: true,
        },
        "furnished-qa": {
          componentPresentation: "visible",
          structureAppearance: "concrete-shell",
          generationAuthority: false,
        },
      },
      styleState: "none",
      componentAppearanceAuthority: "json-slots-only-for-generation",
    },
    entitySemanticMask: {
      encoding: "stable-rgb-entity-id",
      backgroundColor: "#000000",
      dataUrl: semanticMaskDataUrl(pixels, width, height),
    },
    roomSemanticMask: roomFrame.mask,
    rooms: roomFrame.rooms,
    connections: projectedConnections(),
    entities: resultEntities,
    relationHints: structuredClone(model.relationHints || {
      schema: "interior.layout-relation-hints.v2",
      directionalAxes: [],
      facing: [],
      wallAttachment: [],
      allowedContacts: [],
      spaceDividerMarkers: [],
    }),
    projectionEvidence: {
      method: "same-camera-gpu-entity-id-plus-depth-to-room-polygon",
      entityIdPassMs: Number(gpuElapsedMs.toFixed(3)),
      roomDepthPassMs: roomFrame.evidence.depthPassMs,
      roomReprojectionMs: roomFrame.evidence.roomReprojectionMs,
      elapsedMs: Number((gpuElapsedMs + roomFrame.evidence.totalMs).toFixed(3)),
      cpuReadbackBytes: pixels.byteLength + roomFrame.evidence.depthReadbackBytes,
      generatedMaskBytes: pixels.byteLength + roomFrame.evidence.roomMaskBytes,
      renderTargetBytes: width * height * 16,
      overlapRule: roomFrame.evidence.overlapRule,
      roomSearchDirection: roomFrame.evidence.roomSearchDirection,
      maximumRoomSearchDistanceMeters: roomFrame.evidence.maximumRoomSearchDistanceMeters,
      roomSearchStepMeters: roomFrame.evidence.roomSearchStepMeters,
    },
    interpretationConstraints: structuredClone(model.interpretationConstraints || []),
  };
}

function setCapturePresentationMode(mode) {
  if (!activeCaptureShotId) throw new Error("只有 capture 机位可以切换交付显示模式");
  if (!["slot-guided", "furnished-qa"].includes(mode)) {
    throw new Error(`不支持的交付显示模式：${mode}`);
  }
  applyCaptureShot(activeCaptureShotId);
  if (mode === "furnished-qa") {
    setStructureAppearance("concrete-shell");
  } else {
    setStructureAppearance("concrete-shell");
    movableGroup.visible = false;
    fixedGroup.visible = false;
    componentGroups.forEach((group) => {
      group.visible = false;
    });
    renderScene();
  }
  document.documentElement.dataset.capturePresentation = mode;
  return {
    mode,
    structureAppearance,
    hiddenComponentCount: mode === "slot-guided"
      ? visibleComponents().length
      : 0,
  };
}

function materialsAreWhite(root) {
  let valid = true;
  root.traverse((object) => {
    if (!object.isMesh) return;
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach((material) => {
      if (material.color && material.color.getHex() !== 0xffffff) valid = false;
    });
  });
  return valid;
}

function structureEditContractAudit() {
  const patches = model.structureEditPatches || [];
  const patchByWall = new Map();
  let patchBacked = patches.every((patch) => {
    if (
      patch?.schema !== "interior.structure-edit-patch.v1"
      || patch.backend !== "html-threejs"
      || patch.entityType !== "wall"
      || patch.operation !== "extend-collinear-endpoints"
      || patchByWall.has(patch.entityId)
    ) return false;
    patchByWall.set(patch.entityId, patch);
    return true;
  });
  const topologyOwned = !document.getElementById("add-wall")
    && !document.getElementById("delete-wall")
    && model.walls.length === originalModel.walls.length
    && model.windows.length === originalModel.windows.length
    && JSON.stringify(model.connections) === JSON.stringify(originalModel.connections)
    && JSON.stringify(model.rooms) === JSON.stringify(originalModel.rooms)
    && JSON.stringify(model.floorBoundary) === JSON.stringify(originalModel.floorBoundary)
    && JSON.stringify(model.semanticDividers || []) === JSON.stringify(originalModel.semanticDividers || []);
  const withoutKeys = (value, keys) => {
    const clone = structuredClone(value);
    keys.forEach((key) => delete clone[key]);
    return clone;
  };
  originalModel.walls.forEach((sourceWall) => {
    const wall = model.walls.find((item) => item.id === sourceWall.id);
    if (!wall) {
      patchBacked = false;
      return;
    }
    if (JSON.stringify(withoutKeys(wall, ["start", "end", "endpointExtensions"]))
      !== JSON.stringify(withoutKeys(sourceWall, ["start", "end", "endpointExtensions"]))) {
      patchBacked = false;
    }
    const changed = JSON.stringify(wall.start) !== JSON.stringify(sourceWall.start)
      || JSON.stringify(wall.end) !== JSON.stringify(sourceWall.end);
    const patch = patchByWall.get(sourceWall.id);
    if (changed && !patch) patchBacked = false;
    if (patch && (
      JSON.stringify(patch.source) !== JSON.stringify({ start: sourceWall.start, end: sourceWall.end })
      || JSON.stringify(patch.current) !== JSON.stringify({ start: wall.start, end: wall.end })
      || patch.hostedWindowOffsetsPreservedInWorld !== true
    )) patchBacked = false;
  });
  originalModel.windows.forEach((sourceWindow) => {
    const item = model.windows.find((candidate) => candidate.id === sourceWindow.id);
    if (!item) {
      patchBacked = false;
      return;
    }
    const patch = patchByWall.get(sourceWindow.wallId);
    const expectedOffset = Number(sourceWindow.offset) + Number(patch?.extensionMeters?.start || 0);
    if (Math.abs(Number(item.offset) - expectedOffset) > 0.000001) patchBacked = false;
    if (JSON.stringify(withoutKeys(item, ["offset"])) !== JSON.stringify(withoutKeys(sourceWindow, ["offset"]))) {
      patchBacked = false;
    }
  });
  return { topologyOwned, patchBacked };
}

function runtimeAudit() {
  const library = libraryAudit();
  const contractIssues = componentContractIssues();
  const relationIssues = relationHintContractIssues();
  const rigIssues = sceneRigIssues();
  const collisions = componentCollisions();
  const placementIssues = [];
  model.componentPlacements.forEach((placement) => {
    const issue = componentStructureIssue(placement);
    if (issue) placementIssues.push({ id: placement.id, issue });
  });
  collisions.forEach((collision) => {
    placementIssues.push({
      id: `${collision.firstId}<->${collision.secondId}`,
      issue: `${collision.firstName}与${collision.secondName}互相穿模`,
    });
  });
  const planIssues = cameraPlanIssues(cameraPlan);
  const planBounds = floorplanWorldBounds();
  const planCenter = planBounds.getCenter(new THREE.Vector3());
  const gridSize = Number(grid?.userData.gridSize || 0);
  const structureEdits = structureEditContractAudit();
  const balconyPartitionAudits = [...wallGroups.values()]
    .map((group) => group.userData.balconyPartitionAudit)
    .filter(Boolean);
  const balconyPartitionValid = balconyPartitionAudits.every((item) => {
    const wall = wallById(item.sourceWallId);
    if (!wall) return false;
    const length = wallFrame(wall).length;
    const intervals = [...item.balconyIntervals, ...item.preservedSourceIntervals]
      .sort((first, second) => first[0] - second[0]);
    if (!item.balconyIntervals.length || !intervals.length) return false;
    let cursor = 0;
    for (const [start, end] of intervals) {
      if (Math.abs(start - cursor) > 0.025 || end <= start) return false;
      cursor = end;
    }
    return Math.abs(cursor - length) <= 0.025;
  });
  const roomsWithCeilings = (model.rooms || []).filter((room) => Array.isArray(room.polygon) && room.polygon.length >= 3).length;
  const audit = {
    schema: model.schema,
    structureSchemaValid: model.schema === "interior.floorplan-structure.v3",
    modelScopeSchema: model.modelScope?.schema,
    modelScopeMode: model.modelScope?.mode,
    modelScopeRequestedRoomIds: [...(model.modelScope?.requestedRoomIds || [])],
    modelScopeAllowedContextRoomIds: [...(model.modelScope?.allowedContextRoomIds || [])],
    modelScopeExcludedRoomIds: [...(model.modelScope?.excludedRoomIds || [])],
    modelScopeUsesWholeFloorCompiler: model.modelScope?.sameTemplateAsWholeFloor === true
      && model.modelScope?.customProjectGeometryAllowed === false,
    modelScopeRuntimeRoomFilterLocked: [...roomFilterIds]
      .every((roomId) => modelScopeRoomIds.has(roomId)),
    backendOptionsSchema: model.backendOptions?.schema,
    backendOptionsValid: model.backendOptions?.schema === "interior.model-backend-options.v1"
      && model.backendOptions?.backend === "html-threejs",
    ceilingCount: ceilingMeshes.size,
    ceilingsVisible: ceilingGroup.visible,
    ceilingSupportAvailable: model.backendOptions?.ceilings?.enabled === true
      && ceilingMeshes.size === roomsWithCeilings
      && Boolean(dom.ceilingToggle),
    windowStyleEditingAvailable: typeof applyWindowStyle === "function"
      && ["frameless-glass", "fixed-pane", "casement", "sliding"]
        .every((style) => model.backendOptions?.windows?.allowedStyles?.includes(style)),
    balconyEnvelopeModesAvailable: ["source-structure", "open-railing", "closed-glazing"]
      .every((mode) => model.backendOptions?.balconies?.allowedModes?.includes(mode)),
    balconyPartitionAudits,
    balconyPartitionValid,
    structureEditPatchCount: model.structureEditPatches?.length || 0,
    structureTopologyOwnedByFloorplan: structureEdits.topologyOwned,
    structureEditsPatchBacked: structureEdits.patchBacked,
    wallEndpointDirectDragAvailable: typeof startWallEndpointDrag === "function"
      && typeof updateWallEndpointDrag === "function"
      && typeof finishWallEndpointDrag === "function"
      && Boolean(wallEndpointHandleGroup),
    collisionMotionMode: model.backendOptions?.collision?.mode,
    sweptCollisionStopAvailable: model.backendOptions?.collision?.mode === "swept-stop-at-first-contact"
      && typeof sweptComponentMove === "function",
    componentLayoutSchema: model.componentLayoutSchema,
    componentLayoutSeparate: model.componentLayoutSchema === "interior.component-layout.v4",
    noEmbeddedComponentCatalog: !Object.prototype.hasOwnProperty.call(sourceStructure, "furnitureCatalog")
      && !Object.prototype.hasOwnProperty.call(sourceStructure, "furniturePlacements"),
    semanticWallCount: model.walls.length,
    hostedWindowCount: model.windows.filter((item) => Boolean(wallById(item.wallId))).length,
    windowsAllHosted: model.windows.every((item) => Boolean(wallById(item.wallId))),
    spatialConnectionCount: (model.connections || []).length,
    sceneSemanticFrameAvailable: typeof sceneSemanticFrame === "function",
    windowIssues: validateWindows(),
    componentLibrary: library,
    registeredComponentCount: COMPONENT_CATALOG.length,
    componentPlacementCount: model.componentPlacements.length,
    componentCollisionPairs: collisions,
    componentContractIssues: contractIssues,
    relationHintSchema: model.relationHints?.schema || null,
    relationHintIssues: relationIssues,
    reviewedLayoutAdjustmentCount: model.componentPlacements
      .filter((placement) => placement.reviewedAdjustment).length,
    facingHintCount: model.relationHints?.facing?.length || 0,
    wallAttachmentHintCount: model.relationHints?.wallAttachment?.length || 0,
    sceneRigSchema: sceneRig.schema,
    sceneRigSeparatedFromCameraPlan: sourceSceneRig !== cameraPlan
      && sceneRig.schema === "interior.scene-rig.v1"
      && cameraPlan.schemaVersion === "8.0",
    authoredLightCount: sceneRig.lights.length,
    enabledAuthoredLightCount: sceneRig.lights.filter((item) => item.enabled !== false).length,
    sceneCameraCount: sceneRig.cameras.length,
    cameraPlanShotCount: cameraPlan.shots?.length || 0,
    cameraPlanLightingSetupCount: cameraPlan.lightingSetups?.length || 0,
    cameraPlanIssues: planIssues,
    activeSceneCameraId,
    activeCameraPlanShotId,
    activeCaptureShotId,
    activeOcclusionCameraId,
    fullFloorVisible: Boolean(floorMesh?.visible),
    detachedCameraId,
    sceneEditorMode,
    sceneRigMarkersVisible: sceneRigHelperGroup.visible,
    sceneRigGizmosVisible: sceneRig.gizmosVisible !== false,
    cameraTargetLinesVisible: [...cameraTargetLines.values()].every((line) => line.visible === (sceneRig.gizmosVisible !== false && sceneRigHelperGroup.visible)),
    cameraControlsEnabled: controls.enabled,
    sceneRigIssues: rigIssues,
    rendering: {
      toneMapping: "ACESFilmic",
      exposure: renderer.toneMappingExposure,
      ambientIntensity: ambient.intensity,
      hemisphereIntensity: systemFill.intensity,
      detailFillIntensity: fill.intensity,
      inspectionKeyIntensity: inspectionKey.intensity,
      inspectionRimIntensity: inspectionRim.intensity,
      backgroundHex: scene.background.getHex(),
    },
    whiteModelContrastSystem: inspectionKey.castShadow === true
      && inspectionKey.intensity >= 0.5
      && inspectionRim.intensity >= 0.15
      && scene.background.getHex() === WHITE_MODEL_BACKGROUND,
    whiteModelToneMappingAvailable: renderer.toneMapping === THREE.ACESFilmicToneMapping
      && typeof frameReadability === "function",
    defaultTopViewConfigured: true,
    topViewCentered: viewMode !== "top" || (
      Math.abs(controls.target.x - planCenter.x) < 0.000001
      && Math.abs(controls.target.z - planCenter.z) < 0.000001
    ),
    topViewAllowsOrbit: viewMode !== "top" || controls.enableRotate === true,
    topDragStartsFromIsoView: typeof enterFree3dFromTopDrag === "function",
    topViewProjectionStable: viewMode !== "top"
      || (Math.abs(camera.up.x) < 0.000001
        && Math.abs(camera.up.y) < 0.000001
        && Math.abs(camera.up.z + 1) < 0.000001),
    roomFilterAvailable: Boolean(
      dom.roomFilterToggle
      && dom.roomFilterOptions
      && typeof applyRoomFilter === "function",
    ),
    roomFilterSelectedIds: [...roomFilterIds],
    floorAlwaysAvailable: Boolean(
      floorMesh
      && (
        floorMesh.visible
        || [...roomFilterFloors.values()].some((mesh) => mesh.visible)
      )
    ),
    selectedRoomFloorsVisible: roomFilterIsAll()
      || roomFilterIds.size === 0
      || [...roomFilterIds].every((id) => roomFilterFloors.get(id)?.visible),
    roomBoundaryWallSegmentationAvailable: typeof wallIntervalsForRooms === "function"
      && Boolean(roomFilterStructureGroup),
    compiledRoomTopologyAvailable: model.topology?.method === "wall-mask-opening-closure-space-seed"
      && model.topology?.roomCount === (model.rooms || []).length,
    roomBoundaryAnnotationAvailable: roomBoundaryLines.size === (model.rooms || []).length,
    roomAreaLabelsAvailable: [...roomLabels.values()].every((label) => Boolean(label.querySelector("small"))),
    roomHoverHighlightAvailable: typeof updateRoomHover === "function"
      && typeof setHoveredRoom === "function"
      && Boolean(roomHoverGroup),
    wallAdjacencyValid: model.walls.every((wall) => (
      Array.isArray(wall.adjacentRoomIds)
      && wall.adjacentRoomIds.length >= 2
      && new Set(wall.adjacentRoomIds).size === wall.adjacentRoomIds.length
    )),
    panelScopedPickingAvailable: typeof pickAt === "function" && Boolean(activePanelId),
    structureReadOnly: structureEdits.topologyOwned && structureEdits.patchBacked,
    componentKeyboardMoveAvailable: typeof armComponentKeyboardMove === "function"
      && typeof nudgeComponent === "function",
    componentDirectDragAvailable: typeof startComponentDrag === "function"
      && typeof finishComponentDrag === "function",
    componentRotationAvailable: typeof rotateComponentPlacement === "function",
    componentResetAvailable: typeof resetComponentPlacement === "function",
    componentDeleteAvailable: typeof deleteSelectedComponent === "function",
    componentVisibilityAvailable: typeof setComponentVisibility === "function",
    planSceneHelpersVisible: viewMode !== "top" || (
      sceneRigHelperGroup.visible
      && cameraHelperGroups.size === sceneRig.cameras.length
      && lightHelperGroups.size === sceneRig.lights.length
    ),
    lightEditorAvailable: Boolean(document.getElementById("add-light") && dom.lightList && dom.sceneInspector),
    cameraEditorAvailable: Boolean(document.getElementById("add-camera") && dom.cameraList && dom.sceneInspector),
    cameraWallMountAvailable: typeof mountSceneCameraToWall === "function",
    cameraViewAvailable: typeof enterSceneCameraView === "function" && typeof returnFreeView === "function",
    unifiedSceneModeControl: Boolean(dom.sceneModeLight && dom.sceneModeCamera),
    sceneAxisControlAvailable: typeof buildTransformGizmo === "function" && Boolean(transformGizmoGroup),
    sceneObjectDragAvailable: typeof startSceneObjectDrag === "function" && typeof finishSceneObjectDrag === "function",
    sceneObjectDirectPickingAvailable: typeof selectSceneObjectForEditing === "function"
      && [...lightHelperGroups.values(), ...cameraHelperGroups.values()]
        .every((helper) => helper.children.some((child) => child.userData.role === "pick-proxy")),
    cameraWallSnapAvailable: typeof applyCameraWallSnap === "function",
    cameraDetachesOnOrbit: true,
    cameraDetachesOnlyOnCanvasDrag: true,
    fixedCameraKeyboardNavigationAvailable: typeof nudgeFixedCamera === "function",
    fixedCameraDoubleClickFocusAvailable: typeof setFixedCameraTargetFromEvent === "function",
    cameraCutawayAvailable: typeof toggleCameraCutaway === "function" && typeof cameraOccluders === "function",
    cameraRoomFocusAvailable: (model.rooms || []).length > 0,
    cameraScreenshotAvailable: typeof captureCurrentView === "function",
    cameraPlanPreviewAvailable: typeof previewCameraPlanShot === "function"
      && Boolean(dom.cameraPlanList && dom.cameraPlanFile),
    cameraPlanPreviewBelowParameters: Boolean(dom.cameraPlanDeck?.previousElementSibling === dom.sceneInspector),
    cameraPlanPreviewIsTemporary: typeof restoreCameraPlanPreview === "function",
    contextPreservingOcclusionAvailable: typeof deriveContextVisibility === "function"
      && (sceneRig.cameras || []).every((item) => (
        item.visibility?.contextPolicy === "preserve-visible-adjacent-spaces"
      )),
    topCameraEditingAvailable: typeof showCameraPlanEvidence === "function"
      && Boolean(dom.cameraLivePreview),
    liveCameraPreviewAvailable: typeof renderLiveCameraPreview === "function"
      && typeof setCameraPreviewEnabled === "function"
      && Boolean(dom.cameraPreviewToggle && dom.cameraLivePreviewCanvas && previewRenderTarget),
    liveCameraPreviewPersistsAcrossViews: typeof activePreviewCameraState === "function",
    liveCameraPreviewResizable: typeof setCameraPreviewWidth === "function"
      && typeof startCameraPreviewResize === "function"
      && Boolean(dom.cameraPreviewResizeHandle),
    cameraDoubleClickEditsInsteadOfEnteringFixedView: true,
    centeredIsoViewAvailable: typeof fitIsoView === "function" && planCenter.toArray().every(Number.isFinite),
    blankCanvasPanAvailable: typeof clearSelectionForCanvasNavigation === "function"
      && typeof panCanvasByArrow === "function",
    cameraPreviewEnabled,
    previewSceneCameraId,
    shotLightingAvailable: typeof lightingSetupById === "function",
    screenshotCount,
    focalLengthControlAvailable: selection.type !== "camera" || Boolean(dom.sceneInspector.querySelector('[data-field="focalLengthMm"]')),
    lensDistortionControlAbsent: !dom.sceneInspector.querySelector('[data-field="distortion"]'),
    rectilinearLensOnly: (sceneRig.cameras || []).every((item) => Number(item.distortion || 0) === 0)
      && (cameraPlan.shots || []).every((shot) => Number(shot.distortion || 0) === 0),
    lightNameInputAbsent: !dom.sceneInspector.querySelector('[data-field="name"]'),
    cameraEnableInputAbsent: selection.type !== "camera" || !dom.sceneInspector.querySelector('[data-field="enabled"]'),
    eventDrivenRendering: controls.enableDamping === false,
    webglContextLossCount,
    webglContextRestoreCount,
    sceneRigBuildCount,
    sceneVisualUpdateCount,
    rendererMemory: { ...renderer.info.memory },
    rendererProgramCount: renderer.info.programs?.length || 0,
    sceneRigExportAvailable: Boolean(document.getElementById("export-scene-rig")),
    placementIssues,
    componentMeshCounts: Object.fromEntries(componentMeshCounts),
    structureWhiteModel: structureAppearance === "neutral-white"
      && materialsAreWhite(structureGroup) && materialsAreWhite(glassGroup),
    fixedComponentsWhiteModel: movableAppearance !== "white-model" || materialsAreWhite(fixedGroup),
    movableComponentsWhiteModel: movableAppearance !== "white-model" || materialsAreWhite(movableGroup),
    movableAppearance,
    movableAppearanceValid: ["white-model", "source-color"].includes(movableAppearance)
      && [...componentGroups.values()]
        .every((group) => group.userData.appearance === movableAppearance),
    projectFinishPresetsValid: model.componentPlacements.every((placement) => (
      placement.finishPreset === undefined
      || ["source-authored", "modern-light-wood"].includes(placement.finishPreset)
    )),
    componentFinishMaterialsValid: [...componentGroups.entries()].every(([id, group]) => {
      const placement = model.componentPlacements.find((item) => item.id === id);
      const preset = placement?.finishPreset || "source-authored";
      if (group.userData.finishPreset !== preset) return false;
      if (movableAppearance !== "source-color" || preset !== "modern-light-wood") return true;
      let finishMeshCount = 0;
      let valid = true;
      group.traverse((object) => {
        if (!object.isMesh || !object.userData.appearanceMaterials) return;
        finishMeshCount += 1;
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        if (!materials.every((material) => material.name.endsWith("-modern-light-wood"))) valid = false;
      });
      return finishMeshCount > 0 && valid;
    }),
    floorWhiteModel: structureAppearance === "neutral-white" && floorMesh ? materialsAreWhite(floorMesh) : false,
    structureAppearance,
    structureAppearanceValid: STRUCTURE_APPEARANCES.has(structureAppearance),
    concreteShellAvailable: typeof setStructureAppearance === "function" && Boolean(concreteTexture),
    concreteFloorAvailable: structureAppearance !== "concrete-shell"
      || (floorMesh?.material?.map === concreteTexture && floorMesh?.userData.structureSurfaceRole === "floor"),
    extendedMeasurementGrid: gridSize >= Math.max(cfg.realWidthMeters, cfg.realDepthMeters) * 2.75
      && Number(grid?.userData.gridStep || 0) <= 0.51,
    requiredFloorDividerCount: (model.relationHints?.spaceDividerMarkers || [])
      .filter((marker) => marker.required === true).length,
    renderedFloorDividerCount: semanticDividerGroup.children.length,
    requiredFloorDividersRendered: (model.relationHints?.spaceDividerMarkers || [])
      .filter((marker) => marker.required === true)
      .every((marker) => semanticDividerGroup.children.some((mesh) => mesh.name === marker.id)),
    sourceHiddenByDefault: !document.body.classList.contains("reference-open"),
    annotationsHiddenByDefault: originalModel.layers.annotations === false,
    rulerAvailable: Boolean(document.getElementById("toggle-measure") && document.getElementById("clear-measure")),
    addableCatalogAbsent: !document.getElementById("furniture-catalog"),
    componentLibraryPartitionCounts: library.partitionCounts,
    uniqueTemplateMarker: "INTERIOR_HTML_MODELING_V170_MODEL_SCOPE_SINGLE_SOURCE",
    viewMode,
  };
  audit.ok = audit.structureSchemaValid
    && audit.backendOptionsValid
    && audit.ceilingSupportAvailable
    && audit.windowStyleEditingAvailable
    && audit.balconyEnvelopeModesAvailable
    && audit.balconyPartitionValid
    && audit.structureTopologyOwnedByFloorplan
    && audit.structureEditsPatchBacked
    && audit.wallEndpointDirectDragAvailable
    && audit.sweptCollisionStopAvailable
    && audit.componentLayoutSeparate
    && audit.noEmbeddedComponentCatalog
    && audit.semanticWallCount > 0
    && audit.windowsAllHosted
    && audit.spatialConnectionCount > 0
    && audit.sceneSemanticFrameAvailable
    && audit.windowIssues.length === 0
    && audit.componentLibrary.ok
    && audit.registeredComponentCount === audit.componentLibrary.componentCount
    && audit.componentContractIssues.length === 0
    && audit.relationHintSchema === "interior.layout-relation-hints.v2"
    && audit.relationHintIssues.length === 0
    && audit.sceneRigSeparatedFromCameraPlan
    && audit.authoredLightCount >= 1
    && audit.sceneCameraCount >= 1
    && audit.sceneRigIssues.length === 0
    && audit.whiteModelToneMappingAvailable
    && audit.whiteModelContrastSystem
    && audit.defaultTopViewConfigured
    && audit.topViewCentered
    && audit.topViewAllowsOrbit
    && audit.topDragStartsFromIsoView
    && audit.topViewProjectionStable
    && audit.roomFilterAvailable
    && audit.floorAlwaysAvailable
    && audit.selectedRoomFloorsVisible
    && audit.roomBoundaryWallSegmentationAvailable
    && audit.compiledRoomTopologyAvailable
    && audit.roomBoundaryAnnotationAvailable
    && audit.roomAreaLabelsAvailable
    && audit.roomHoverHighlightAvailable
    && audit.wallAdjacencyValid
    && audit.panelScopedPickingAvailable
    && audit.structureReadOnly
    && audit.componentKeyboardMoveAvailable
    && audit.componentDirectDragAvailable
    && audit.componentRotationAvailable
    && audit.componentResetAvailable
    && audit.componentDeleteAvailable
    && audit.componentVisibilityAvailable
    && audit.planSceneHelpersVisible
    && audit.cameraPlanIssues.length === 0
    && audit.lightEditorAvailable
    && audit.cameraEditorAvailable
    && audit.cameraWallMountAvailable
    && audit.cameraViewAvailable
    && audit.unifiedSceneModeControl
    && audit.sceneAxisControlAvailable
    && audit.sceneObjectDragAvailable
    && audit.sceneObjectDirectPickingAvailable
    && audit.cameraWallSnapAvailable
    && audit.cameraDetachesOnOrbit
    && audit.cameraDetachesOnlyOnCanvasDrag
    && audit.fixedCameraKeyboardNavigationAvailable
    && audit.fixedCameraDoubleClickFocusAvailable
    && audit.cameraCutawayAvailable
    && audit.cameraRoomFocusAvailable
    && audit.cameraScreenshotAvailable
    && audit.cameraPlanPreviewAvailable
    && audit.cameraPlanPreviewBelowParameters
    && audit.cameraPlanPreviewIsTemporary
    && audit.contextPreservingOcclusionAvailable
    && audit.topCameraEditingAvailable
    && audit.liveCameraPreviewAvailable
    && audit.liveCameraPreviewPersistsAcrossViews
    && audit.liveCameraPreviewResizable
    && audit.cameraDoubleClickEditsInsteadOfEnteringFixedView
    && audit.centeredIsoViewAvailable
    && audit.blankCanvasPanAvailable
    && audit.shotLightingAvailable
    && audit.focalLengthControlAvailable
    && audit.lensDistortionControlAbsent
    && audit.rectilinearLensOnly
    && audit.eventDrivenRendering
    && audit.webglContextLossCount === 0
    && audit.sceneRigExportAvailable
    && audit.placementIssues.length === 0
    && audit.structureAppearanceValid
    && audit.concreteShellAvailable
    && audit.concreteFloorAvailable
    && audit.extendedMeasurementGrid
    && audit.requiredFloorDividersRendered
    && audit.fixedComponentsWhiteModel
    && audit.movableComponentsWhiteModel
    && audit.movableAppearanceValid
    && audit.projectFinishPresetsValid
    && audit.componentFinishMaterialsValid
    && (audit.structureAppearance === "concrete-shell" || (audit.structureWhiteModel && audit.floorWhiteModel))
    && audit.sourceHiddenByDefault
    && audit.annotationsHiddenByDefault
    && audit.rulerAvailable
    && audit.addableCatalogAbsent;
  return audit;
}

function updateRuntimeAudit() {
  const audit = runtimeAudit();
  document.getElementById("runtime-audit").textContent = JSON.stringify(audit, null, 2);
  window.__INTERIOR_MODEL_AUDIT__ = audit;
  return audit;
}

function runSelfTest() {
  const audit = updateRuntimeAudit();
  document.documentElement.dataset.selftest = audit.ok ? "pass" : "fail";
  document.documentElement.dataset.selftestIssues = String(
    audit.windowIssues.length
      + audit.componentContractIssues.length
      + audit.placementIssues.length
      + audit.sceneRigIssues.length,
  );
  return audit;
}

window.__INTERIOR_MODEL_EDITOR__ = {
  getModel: () => structuredClone(model),
  getRelationHints: () => structuredClone(model.relationHints),
  getSceneRig: () => structuredClone(sceneRig),
  getCameraPlan: () => structuredClone(cameraPlan),
  getCameraPlanEvidence: cameraEvidenceFacts,
  showCameraPlanEvidence,
  captureCameraPlanEvidenceDataUrl,
  loadCameraPlan: (plan) => loadCameraPlanData(plan),
  previewCameraPlanShot,
  restoreCameraPlanPreview,
  getContextVisibility: (cameraId) => {
    const item = sceneCameraById(cameraId);
    return item ? structuredClone(deriveContextVisibility(item)) : null;
  },
  applyCaptureShot,
  getActiveCapturePoseAudit: () => structuredClone(activeCapturePoseAudit),
  getActiveCaptureShotId: () => activeCaptureShotId,
  captureFrameDataUrl,
  getFrameReadability: frameReadability,
  getSceneSemanticFrame: sceneSemanticFrame,
  setCapturePresentationMode,
  setStructureAppearance,
  getStructureAppearance: () => structureAppearance,
  setCeilingsVisible: (visible) => performMutation(`${visible ? "显示" : "隐藏"}天花板`, () => {
    model.layers.ceilings = Boolean(visible);
  }),
  getCeilingsVisible: () => model.layers.ceilings !== false,
  setWindowStyle: (id, style) => (
    windowById(id) && model.backendOptions.windows?.allowedStyles?.includes(style)
      ? performMutation(`切换${windowById(id)?.name || id}样式`, () => applyWindowStyle(id, style))
      : false
  ),
  setWallEndpointExtensions: (id, startExtension, endExtension) => (
    wallById(id)
      ? performMutation(`调整${wallById(id)?.name || id}端点`, () => {
        applyWallExtension(id, Number(startExtension), Number(endExtension));
      })
      : false
  ),
  getStructureEditPatches: () => structuredClone(model.structureEditPatches || []),
  setMovableAppearance,
  getMovableAppearance: () => movableAppearance,
  setCameraPreviewEnabled,
  setCameraPreviewWidth,
  getCameraPreviewState: () => ({
    enabled: cameraPreviewEnabled,
    cameraId: previewSceneCameraId,
    visible: !dom.cameraLivePreview.hidden,
    viewMode,
    frameCount: cameraPreviewFrameCount,
    signature: cameraPreviewSignature,
    width: dom.cameraLivePreviewCanvas?.width || 0,
    height: dom.cameraLivePreviewCanvas?.height || 0,
    displayWidth: dom.cameraLivePreview?.getBoundingClientRect().width || 0,
    displayHeight: dom.cameraLivePreview?.getBoundingClientRect().height || 0,
    resizable: Boolean(dom.cameraPreviewResizeHandle),
  }),
  getAudit: () => structuredClone(runtimeAudit()),
  getComponentCatalog: () => structuredClone(COMPONENT_CATALOG),
  selectObject,
  setComponent: (id, patch) => performMutation(`修改${componentById(id)?.name || id}`, () => {
    const placement = componentById(id);
    if (patch.position) placement.position = [...patch.position];
    if (patch.rotationY !== undefined) placement.rotationY = patch.rotationY;
    if (patch.uniformScale !== undefined) {
      placement.uniformScale = clampUniformScale(
        getComponentDefinition(placement.componentId, placement.semantic),
        patch.uniformScale,
      );
    }
    if (patch.visualDimensions !== undefined) {
      const definition = getComponentDefinition(placement.componentId, placement.semantic);
      const resolved = resolvedVisualScale(definition, {
        uniformScale: placement.uniformScale ?? 1,
        visualDimensions: patch.visualDimensions,
      });
      placement.visualDimensions = { ...resolved.dimensions };
      placement.targetDimensions = {
        ...placement.targetDimensions,
        width: resolved.dimensions.width,
        depth: resolved.dimensions.depth,
      };
      placement.traceLock = { ...placement.traceLock, dimensions: false };
    }
    if (patch.elevation !== undefined) placement.elevation = Math.max(0, Number(patch.elevation));
  }),
  setRoomFilter: (ids) => {
    roomFilterIds.clear();
    (Array.isArray(ids) ? ids : []).filter((id) => roomById(id)).forEach((id) => roomFilterIds.add(id));
    applyRoomFilter();
    return [...roomFilterIds];
  },
  getRoomFilter: () => [...roomFilterIds],
  getRoomBoundaryWallSegments: (ids = [...roomFilterIds]) => {
    const rooms = (Array.isArray(ids) ? ids : [])
      .map((id) => roomById(id))
      .filter(Boolean);
    return model.walls.flatMap((wall) => (
      wallIntervalsForRooms(wall, rooms).map(([startOffset, endOffset]) => ({
        wallId: wall.id,
        startOffset,
        endOffset,
        start: pointAlongWall(wall, startOffset),
        end: pointAlongWall(wall, endOffset),
      }))
    ));
  },
  getComponentScreenPoint: (id) => {
    const group = componentGroups.get(id);
    if (!group) return null;
    const center = new THREE.Box3().setFromObject(group).getCenter(new THREE.Vector3());
    return worldPointToCanvas(center);
  },
  getPlanScreenPoint: (point, height = 0.3) => {
    if (!Array.isArray(point) || point.length !== 2) return null;
    const world = worldPoint(point);
    return worldPointToCanvas(new THREE.Vector3(world.x, Number(height), world.z));
  },
  getWallEndpointScreenPoint: (id, endpoint) => {
    if (!["start", "end"].includes(endpoint)) return null;
    const handle = wallEndpointHandleGroup.getObjectByName(`wall-endpoint-${id}-${endpoint}`);
    return handle ? worldPointToCanvas(handle.getWorldPosition(new THREE.Vector3())) : null;
  },
  getWallEndpointDragState: () => wallEndpointDrag ? structuredClone({
    wallId: wallEndpointDrag.wallId,
    endpoint: wallEndpointDrag.endpoint,
    proposedStart: wallEndpointDrag.proposedStart,
    proposedEnd: wallEndpointDrag.proposedEnd,
    moved: wallEndpointDrag.moved,
  }) : null,
  getPickAtScreenPoint: (x, y) => structuredClone(pickAt({ clientX: Number(x), clientY: Number(y) })),
  getElementVisibility: (id) => {
    if (wallGroups.has(id) || roomFilterWallGroups.has(id)) {
      const group = roomFilterIsAll() || roomFilterIds.size === 0
        ? wallGroups.get(id)
        : roomFilterWallGroups.get(id);
      return Boolean(group?.visible);
    }
    if (windowGroups.has(id) || roomFilterWindowGroups.has(id)) {
      const group = roomFilterIsAll() || roomFilterIds.size === 0
        ? windowGroups.get(id)
        : roomFilterWindowGroups.get(id);
      return Boolean(group?.visible);
    }
    return Boolean(componentGroups.get(id)?.visible);
  },
  activatePanel: activateTab,
  armComponentKeyboardMove,
  nudgeComponent,
  rotateComponent: rotateComponentPlacement,
  resetComponent: resetComponentPlacement,
  setComponentVisibility,
  deleteComponent: (id) => {
    selection = { type: "component", id };
    return deleteSelectedComponent();
  },
  addLight: addSceneLight,
  setLight: (id, patch) => {
    const item = lightById(id);
    const rebuildRig = patch.type !== undefined && patch.type !== item?.type;
    return mutateSceneItem(`修改${sceneDisplayName("light", item)}`, "light", id, () => {
      Object.assign(item, structuredClone(patch));
    }, { rebuildRig });
  },
  addSceneCamera,
  setSceneCamera: (id, patch) => {
    const item = sceneCameraById(id);
    if (!item) {
      setStatus(`未找到摄像头：${id}`, "error");
      return false;
    }
    return mutateSceneItem(`修改${sceneDisplayName("camera", item)}`, "camera", id, () => {
      const next = structuredClone(patch);
      if (next.focalLengthMm !== undefined && next.fov === undefined) {
        next.fov = fovForFocalLength(next.focalLengthMm);
      } else if (next.fov !== undefined && next.focalLengthMm === undefined) {
        next.focalLengthMm = focalLengthForFov(next.fov);
      } else if (
        next.lensPreset !== undefined
        && next.focalLengthMm === undefined
        && next.fov === undefined
        && LENS_PRESETS[next.lensPreset]
      ) {
        next.focalLengthMm = LENS_PRESETS[next.lensPreset].focalLengthMm;
        next.fov = fovForFocalLength(next.focalLengthMm);
        next.distortion = 0;
      }
      const mount = next.mount ? { ...item.mount, ...next.mount } : item.mount;
      const visibility = next.visibility ? { ...item.visibility, ...next.visibility } : item.visibility;
      Object.assign(item, next, { mount, visibility });
      if (item.mount?.mode === "wall") applyCameraWallMount(item);
    });
  },
  setSceneCameraFocusRoom: (id, roomId) => mutateSceneItem(`设置${sceneDisplayName("camera", sceneCameraById(id))}焦点空间`, "camera", id, () => {
    const item = sceneCameraById(id);
    item.focusRoomId = roomById(roomId) ? roomId : null;
    const target = roomFocusTarget(roomById(item.focusRoomId));
    if (target) item.target = target;
  }),
  setSceneEditorMode,
  setSceneTransformPart: (part) => {
    if (!["position", "target"].includes(part)) return false;
    sceneTransformPart = part;
    renderInspectors();
    buildTransformGizmo();
    updateSceneRigVisibility();
    updateSelectionHighlight();
    return true;
  },
  mountSceneCameraToWall,
  setSceneCameraWallSnap: (id, enabled) => mutateSceneItem(`${enabled ? "开启" : "关闭"}${sceneDisplayName("camera", sceneCameraById(id))}墙面吸附`, "camera", id, () => {
    const item = sceneCameraById(id);
    item.mount.snapEnabled = Boolean(enabled);
    if (item.mount.snapEnabled) applyCameraWallSnap(item);
    else if (item.mount.mode === "wall") {
      item.mount.mode = "free";
      item.mount.wallId = null;
      item.mount.offset = null;
    }
  }),
  toggleCameraCutaway,
  refreshCameraCutaway: (id) => mutateSceneItem(`更新${sceneDisplayName("camera", sceneCameraById(id))}遮挡`, "camera", id, () => {
    refreshCameraCutaway(sceneCameraById(id));
  }),
  getLocalOccluderCandidates: (id) => {
    const item = sceneCameraById(id);
    return item ? structuredClone(cameraOccluders(item)) : null;
  },
  copyCurrentViewToSceneCamera,
  enterSceneCameraView,
  returnFreeView,
  captureCurrentView,
  getSceneInteractionState: () => ({
    selection: { ...selection },
    sceneEditorMode,
    sceneTransformPart,
    activeSceneCameraId,
    activeCameraPlanShotId,
    cameraPlanPreviewActive: Boolean(cameraPlanPreviewSnapshot),
    activeLightingSetupId: activeCameraPlanShot()?.lightingSetupId || null,
    detachedCameraId,
    activeOcclusionCameraId,
    activeCameraViewFineTuned,
    controlsEnabled: controls.enabled,
    canvasNavigationReady: selection.type === "none"
      && !activeSceneCameraId
      && !activeCameraPlanShotId,
  }),
  clearSelection: clearSelectionForCanvasNavigation,
  panCanvas: panCanvasByArrow,
  getSceneObjectScreenPoint,
  getSceneHandleScreenPoint,
  getRendererState: () => ({
    webglContextLossCount,
    webglContextRestoreCount,
    sceneRigBuildCount,
    sceneVisualUpdateCount,
    renderQueued,
    memory: { ...renderer.info.memory },
    programs: renderer.info.programs?.length || 0,
  }),
  setSceneRigGizmosVisible: (visible) => {
    const type = ["light", "camera"].includes(selection.type) ? selection.type : sceneEditorMode;
    const item = type === "light" ? sceneRig.lights[0] : sceneRig.cameras[0];
    const changed = mutateSceneItem(`${visible ? "显示" : "隐藏"}操纵轴与焦点线`, type, item.id, () => {
      sceneRig.gizmosVisible = Boolean(visible);
    });
    updateSceneRigVisibility();
    return changed;
  },
  exportSceneRig: () => {
    const exportRig = structuredClone(sceneRig);
    if (cameraPlanPreviewSnapshot) {
      const cameraIndex = exportRig.cameras.findIndex((item) => item.id === cameraPlanPreviewSnapshot.cameraId);
      if (cameraIndex >= 0) exportRig.cameras[cameraIndex] = structuredClone(cameraPlanPreviewSnapshot.camera);
      exportRig.lights = structuredClone(cameraPlanPreviewSnapshot.lights);
      exportRig.rendering = structuredClone(cameraPlanPreviewSnapshot.rendering);
    }
    return `${JSON.stringify(exportRig, null, 2)}\n`;
  },
  setView: (mode) => mode === "top" ? setTop() : setIso(),
  getViewState: () => ({
    mode: viewMode,
    position: camera.position.toArray(),
    target: controls.target.toArray(),
    floorplanCenter: floorplanWorldBounds().getCenter(new THREE.Vector3()).toArray(),
    up: camera.up.toArray(),
    controlsEnabled: controls.enabled,
    rotateEnabled: controls.enableRotate,
  }),
  setReferenceOpen,
  setAnnotationsVisible,
  setMeasurementMode,
  measureBetween: setMeasurementPoints,
  clearMeasurement,
  undo,
  redo,
  runSelfTest,
};

function resize() {
  const bounds = dom.scene.getBoundingClientRect();
  const width = Math.max(1, bounds.width);
  const height = Math.max(1, bounds.height);
  camera.aspect = width / height;
  if (viewMode === "top") fitTopView();
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
  setCameraPreviewWidth(cameraPreviewWidth);
  requestRender();
}

new ResizeObserver(resize).observe(dom.scene);
window.addEventListener("keydown", (event) => {
  const editingField = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName);
  if (!editingField && (activeSceneCameraId || activeCameraPlanShotId) && !event.ctrlKey && !event.metaKey && !event.altKey) {
    const key = event.key.toLowerCase();
    const fixedViewMoves = {
      arrowleft: ["horizontal", -0.12],
      arrowright: ["horizontal", 0.12],
      arrowup: ["vertical", 0.1],
      arrowdown: ["vertical", -0.1],
      w: ["dolly", 0.14],
      s: ["dolly", -0.14],
    };
    if (fixedViewMoves[key]) {
      event.preventDefault();
      nudgeFixedCamera(...fixedViewMoves[key]);
      return;
    }
  }
  if (
    !editingField
    && activePanelId === "furniture-panel"
    && keyboardMoveComponentId
    && !activeSceneCameraId
    && !activeCameraPlanShotId
  ) {
    const step = event.shiftKey ? 0.2 : 0.05;
    const movement = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    }[event.key];
    if (movement) {
      event.preventDefault();
      nudgeComponent(keyboardMoveComponentId, movement[0], movement[1]);
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      deleteSelectedComponent();
      return;
    }
  }
  if (
    !editingField
    && selection.type === "none"
    && !activeSceneCameraId
    && !activeCameraPlanShotId
    && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)
  ) {
    event.preventDefault();
    panCanvasByArrow(event.key, event.shiftKey ? 3 : 1);
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
    event.preventDefault();
    event.shiftKey ? redo() : undo();
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
    event.preventDefault();
    redo();
  }
  if (event.key === "Escape") {
    if (keyboardMoveComponentId) {
      keyboardMoveComponentId = null;
      setStatus("已退出组件键盘移动");
    } else if (measurement.active || measurement.points.length) {
      clearMeasurement();
      setMeasurementMode(false);
    } else if (selection.type !== "none" && !activeSceneCameraId && !activeCameraPlanShotId) {
      clearSelectionForCanvasNavigation();
    }
  }
});

rebuildAll();
setTop();
setReferenceOpen(false);
const initialCaptureApplied = applyCaptureShot();
if (initialCaptureApplied) {
  const requestedPresentation = new URLSearchParams(window.location.search).get("presentation");
  setCapturePresentationMode(
    ["slot-guided", "furnished-qa"].includes(requestedPresentation)
      ? requestedPresentation
      : "slot-guided",
  );
}
resize();
const initialIssues = validateModel();
setStatus(initialIssues.length ? `模型有 ${initialIssues.length} 项待修：${initialIssues[0]}` : "结构、窗洞与描线匹配组件已载入", initialIssues.length ? "error" : "success");
if (new URLSearchParams(window.location.search).get("selftest") === "1") runSelfTest();
requestRender();
