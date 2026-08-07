import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  COMPONENT_CATALOG,
  COMPONENT_CATEGORIES,
  FIXED_PURPLE_COMPONENTS,
  MOVABLE_GREEN_COMPONENTS,
  createWhiteModelComponent,
  getComponentDefinition,
  libraryAudit,
  setComponentAppearance,
} from "@interior/component-library";

const viewer = document.getElementById("component-viewer");
const list = document.getElementById("component-list");
const search = document.getElementById("component-search");
const partitionFilter = document.getElementById("partition-filter");
const categoryFilter = document.getElementById("category-filter");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xdfe4e0);
const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.82;
viewer.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 1;
controls.maxDistance = 18;

scene.add(new THREE.HemisphereLight(0xffffff, 0x89928c, 1.05));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.45);
keyLight.position.set(-6, 9, 7);
keyLight.castShadow = true;
scene.add(keyLight);
const fillLight = new THREE.DirectionalLight(0xffffff, 0.55);
fillLight.position.set(5, 4, -5);
scene.add(fillLight);

const floorMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.96 });
const floor = new THREE.Mesh(new THREE.CircleGeometry(4.5, 64), floorMaterial);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -0.012;
floor.receiveShadow = true;
scene.add(floor);
const grid = new THREE.GridHelper(8, 16, 0x929a94, 0xc6cbc7);
grid.position.y = -0.006;
scene.add(grid);

let activeGroup = null;
let activeId = null;
let viewMode = "iso";
let componentAppearance = "white-model";

Object.entries(COMPONENT_CATEGORIES).forEach(([value, label]) => {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  categoryFilter.appendChild(option);
});

function formatDimensions(definition) {
  const { width, depth, height } = definition.defaultDimensions;
  return `${width.toFixed(2)} × ${depth.toFixed(2)} × ${height.toFixed(2)} m`;
}

function filteredCatalog() {
  const query = search.value.trim().toLowerCase();
  const partition = partitionFilter.value;
  const category = categoryFilter.value;
  return COMPONENT_CATALOG.filter((item) => {
    const partitionMatch = partition === "all" || item.placementClass === partition;
    const categoryMatch = category === "all" || item.category === category;
    const haystack = [item.id, item.name, item.categoryName, item.shapeClass, ...item.tags].join(" ").toLowerCase();
    return partitionMatch && categoryMatch && (!query || haystack.includes(query));
  });
}

function renderList() {
  const items = filteredCatalog();
  document.getElementById("result-count").textContent = `${items.length} 个组件`;
  list.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-result";
    empty.textContent = "没有匹配的原组件";
    list.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `component-item${item.id === activeId ? " active" : ""}`;
    button.dataset.componentId = item.id;
    button.innerHTML = `
      <i class="shape-mark ${item.shapeClass}" aria-hidden="true"></i>
      <span class="component-copy">
        <strong>${item.name}</strong>
        <small><i class="partition-chip ${item.placementClass}"></i>${item.categoryName} · ${item.shapeClass}</small>
      </span>
      <span class="component-size">${item.defaultDimensions.width.toFixed(2)}m</span>`;
    button.addEventListener("click", () => selectComponent(item.id));
    list.appendChild(button);
  });
}

function fitCamera(definition, mode = viewMode) {
  const d = definition.defaultDimensions;
  const extent = Math.max(d.width, d.depth, d.height, 0.7);
  controls.target.set(0, d.height * 0.42, 0);
  if (mode === "front") {
    camera.position.set(0, d.height * 0.52, extent * 3.3);
    camera.up.set(0, 1, 0);
    controls.enableRotate = true;
  } else if (mode === "top") {
    camera.position.set(0, extent * 3.7, 0.001);
    camera.up.set(0, 0, -1);
    controls.enableRotate = false;
  } else {
    camera.position.set(extent * 2.25, extent * 1.7, extent * 2.25);
    camera.up.set(0, 1, 0);
    controls.enableRotate = true;
  }
  camera.near = Math.max(0.01, extent / 100);
  camera.far = Math.max(100, extent * 30);
  camera.updateProjectionMatrix();
  controls.update();
}

function setView(mode) {
  viewMode = mode;
  document.querySelectorAll(".viewer-toolbar .segmented button").forEach((button) => {
    button.classList.toggle("active", button.id === `view-${mode}`);
  });
  const definition = getComponentDefinition(activeId);
  if (definition) fitCamera(definition, mode);
}

function renderDetails(definition) {
  document.getElementById("detail-name").textContent = definition.name;
  document.getElementById("detail-id").textContent = definition.id;
  document.getElementById("detail-class").textContent = definition.categoryName;
  document.getElementById("detail-dimensions").textContent = formatDimensions(definition);
  document.getElementById("detail-scale").textContent = `${definition.uniformScaleRange.min.toFixed(2)}–${definition.uniformScaleRange.max.toFixed(2)} 倍，等比例`;
  document.getElementById("detail-shape").textContent = definition.shapeClass;
  document.getElementById("detail-placement").textContent = definition.placementClass === "fixed-purple" ? "紫色固定构件" : "绿色活动家具";
  document.getElementById("detail-appearance").textContent = definition.appearanceVariants?.includes("source-color")
    ? "白模（默认） / 原色 PBR"
    : "白模";
  const source = document.getElementById("detail-source");
  source.replaceChildren();
  if (definition.sourceUrl) {
    const link = document.createElement("a");
    link.href = definition.sourceUrl;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = `${definition.sourceProvenance} · ${definition.sourceLicense}`;
    source.appendChild(link);
  } else {
    source.textContent = definition.sourceLicense;
  }
  const parameters = document.getElementById("detail-parameters");
  parameters.replaceChildren();
  Object.entries({
    mountType: definition.mountType,
    seatingCapacity: definition.seatingCapacity,
    researchOnly: definition.researchOnly,
    commercialReviewRequired: definition.commercialReviewRequired,
    ...definition.parameters,
  }).filter(([, value]) => value !== null && value !== undefined).forEach(([key, value]) => {
    const tag = document.createElement("span");
    tag.textContent = `${key}: ${value}`;
    parameters.appendChild(tag);
  });
  const tags = document.getElementById("detail-tags");
  tags.replaceChildren();
  definition.tags.forEach((value) => {
    const tag = document.createElement("span");
    tag.textContent = value;
    tags.appendChild(tag);
  });
}

function setAppearance(mode) {
  componentAppearance = mode;
  if (activeGroup) setComponentAppearance(activeGroup, componentAppearance);
  document.getElementById("appearance-white").classList.toggle("active", componentAppearance === "white-model");
  document.getElementById("appearance-color").classList.toggle("active", componentAppearance === "source-color");
  document.getElementById("appearance-color").disabled = false;
}

function selectComponent(componentId, updateHistory = true) {
  const definition = getComponentDefinition(componentId);
  if (!definition) return;
  delete viewer.dataset.error;
  if (activeGroup) scene.remove(activeGroup);
  activeId = componentId;
  activeGroup = createWhiteModelComponent(componentId, {
    semantic: definition.placementClass,
    appearance: componentAppearance,
  });
  scene.add(activeGroup);
  viewer.classList.toggle("loading", definition.builder === "external-gltf");
  activeGroup.userData.readyPromise?.then(() => {
    if (activeId !== componentId) return;
    viewer.classList.remove("loading");
    setAppearance(componentAppearance);
    fitCamera(definition);
  }).catch((error) => {
    viewer.classList.remove("loading");
    viewer.dataset.error = error.message;
  });
  renderDetails(definition);
  setAppearance(componentAppearance);
  renderList();
  fitCamera(definition);
  if (updateHistory) {
    const url = new URL(window.location.href);
    url.searchParams.set("component", componentId);
    url.searchParams.set("partition", definition.placementClass);
    window.history.replaceState({}, "", url);
  }
}

search.addEventListener("input", renderList);
partitionFilter.addEventListener("change", renderList);
categoryFilter.addEventListener("change", renderList);
document.getElementById("view-iso").addEventListener("click", () => setView("iso"));
document.getElementById("view-front").addEventListener("click", () => setView("front"));
document.getElementById("view-top").addEventListener("click", () => setView("top"));
document.getElementById("appearance-white").addEventListener("click", () => setAppearance("white-model"));
document.getElementById("appearance-color").addEventListener("click", () => setAppearance("source-color"));
document.getElementById("reset-view").addEventListener("click", () => {
  const definition = getComponentDefinition(activeId);
  if (definition) fitCamera(definition);
});

function resize() {
  const bounds = viewer.getBoundingClientRect();
  const width = Math.max(1, bounds.width);
  const height = Math.max(1, bounds.height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}

new ResizeObserver(resize).observe(viewer);
window.addEventListener("popstate", () => {
  const id = new URLSearchParams(window.location.search).get("component");
  if (getComponentDefinition(id)) selectComponent(id, false);
});

const audit = {
  ...libraryAudit(),
  standardAppearance: "dual-white-source-color",
  independentViewer: true,
  deepLinkSupported: true,
  physicalPartitionCounts: {
    "movable-green": MOVABLE_GREEN_COMPONENTS.length,
    "fixed-purple": FIXED_PURPLE_COMPONENTS.length,
  },
  uniformScalingOnly: COMPONENT_CATALOG.every((item) => item.lockAspectRatio),
  uniqueNames: new Set(COMPONENT_CATALOG.map((item) => item.name)).size,
};
audit.ok = audit.ok
  && audit.componentCount > 0
  && audit.uniqueNames === audit.componentCount
  && audit.externalAssetCount === audit.componentCount
  && audit.uniformScalingOnly;
document.getElementById("library-summary").textContent = `${audit.componentCount} 个公共源码组件 · ${audit.researchApprovedCount} 个可研究使用 · ${audit.commercialSafeCount} 个自动通过商业门禁 · ${audit.commercialReviewRequiredCount} 个需商业复核 · 白模 / 原色双状态`;
document.getElementById("library-audit").textContent = JSON.stringify(audit, null, 2);
window.__COMPONENT_EXPLORER_AUDIT__ = audit;

renderList();
const requested = new URLSearchParams(window.location.search).get("component");
const requestedPartition = new URLSearchParams(window.location.search).get("partition");
if (["movable-green", "fixed-purple"].includes(requestedPartition)) {
  partitionFilter.value = requestedPartition;
}
selectComponent(getComponentDefinition(requested)?.id || COMPONENT_CATALOG[0].id, false);
resize();

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();
