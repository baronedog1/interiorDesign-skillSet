#!/usr/bin/env node
import fs from "node:fs";

const file = process.argv[2];
if (!file) {
  console.error("usage: validate_scene_rig.mjs <scene-rig.json>");
  process.exit(2);
}

const data = JSON.parse(fs.readFileSync(file, "utf8"));
const issues = [];
const ids = new Set();
const vector3 = (value) => Array.isArray(value)
  && value.length === 3
  && value.every((item) => Number.isFinite(Number(item)));

if (data.schema !== "interior.scene-rig.v1") issues.push("invalid scene rig schema");
if (data.coordinateSystem !== "threejs-world-y-up-meters") issues.push("invalid coordinate system");
if (typeof data.gizmosVisible !== "boolean") issues.push("gizmosVisible must be boolean");
if (data.rendering?.toneMapping !== "ACESFilmic") issues.push("toneMapping must be ACESFilmic");
if (!(Number(data.rendering?.exposure) >= 0.3 && Number(data.rendering?.exposure) <= 1.5)) {
  issues.push("rendering exposure must be between 0.3 and 1.5");
}
if (!(Number(data.rendering?.ambientIntensity) >= 0 && Number(data.rendering?.ambientIntensity) <= 2)) {
  issues.push("invalid ambientIntensity");
}
if (!(Number(data.rendering?.hemisphereIntensity) >= 0 && Number(data.rendering?.hemisphereIntensity) <= 2)) {
  issues.push("invalid hemisphereIntensity");
}
if (!(Number(data.rendering?.detailFillIntensity) >= 0 && Number(data.rendering?.detailFillIntensity) <= 2)) {
  issues.push("invalid detailFillIntensity");
}
if (!Array.isArray(data.lights) || data.lights.length < 1) issues.push("at least one authored light is required");
if (!Array.isArray(data.cameras) || data.cameras.length < 1) issues.push("at least one scene camera is required");

for (const light of data.lights || []) {
  if (!light.id || ids.has(light.id)) issues.push(`duplicate or missing id: ${light.id || "empty"}`);
  ids.add(light.id);
  if (!["directional", "point", "spot"].includes(light.type)) issues.push(`${light.id}: invalid light type`);
  if (!vector3(light.position) || !vector3(light.target)) issues.push(`${light.id}: invalid position or target`);
  if (!(Number(light.intensity) >= 0 && Number(light.intensity) <= 12)) issues.push(`${light.id}: invalid intensity`);
  if (!(Number(light.temperatureK) >= 2000 && Number(light.temperatureK) <= 10000)) issues.push(`${light.id}: invalid temperature`);
  if (!(Number(light.distance) >= 0 && Number(light.distance) <= 80)) issues.push(`${light.id}: invalid distance`);
  if (!(Number(light.decay) >= 0 && Number(light.decay) <= 4)) issues.push(`${light.id}: invalid decay`);
  if (!(Number(light.angle) >= 5 && Number(light.angle) <= 120)) issues.push(`${light.id}: invalid angle`);
  if (!(Number(light.penumbra) >= 0 && Number(light.penumbra) <= 1)) issues.push(`${light.id}: invalid penumbra`);
}

for (const camera of data.cameras || []) {
  if (!camera.id || ids.has(camera.id)) issues.push(`duplicate or missing id: ${camera.id || "empty"}`);
  ids.add(camera.id);
  if (!vector3(camera.position) || !vector3(camera.target)) issues.push(`${camera.id}: invalid position or target`);
  if (!(camera.focusRoomId === null
    || camera.focusRoomId === undefined
    || typeof camera.focusRoomId === "string")) {
    issues.push(`${camera.id}: invalid focus room id`);
  }
  if (!(Number(camera.fov) >= 16 && Number(camera.fov) <= 82)) issues.push(`${camera.id}: invalid fov`);
  if (!(Number(camera.focalLengthMm) >= 14 && Number(camera.focalLengthMm) <= 85)) {
    issues.push(`${camera.id}: invalid focal length`);
  }
  if (Number(camera.distortion) !== 0) issues.push(`${camera.id}: distortion must be 0`);
  if (!(Number(camera.near) > 0 && Number(camera.far) > Number(camera.near))) issues.push(`${camera.id}: invalid clipping range`);
  if (!["ultra-wide", "wide", "standard", "telephoto", "custom"].includes(camera.lensPreset)) {
    issues.push(`${camera.id}: invalid lens preset`);
  }
  if (!camera.mount || !["free", "wall"].includes(camera.mount.mode)) issues.push(`${camera.id}: invalid mount mode`);
  if (camera.mount?.mode === "wall" && !camera.mount.wallId) issues.push(`${camera.id}: wall mount requires wallId`);
  if (typeof camera.mount?.snapEnabled !== "boolean") issues.push(`${camera.id}: invalid wall snap state`);
  if (!camera.visibility || typeof camera.visibility.cutawayEnabled !== "boolean") {
    issues.push(`${camera.id}: invalid cutaway state`);
  }
  if (camera.visibility?.contextPolicy !== "preserve-visible-adjacent-spaces") {
    issues.push(`${camera.id}: contextPolicy must preserve visible adjacent spaces`);
  }
  if (!Array.isArray(camera.visibility?.hiddenWallIds)
    || !camera.visibility.hiddenWallIds.every((id) => typeof id === "string")) {
    issues.push(`${camera.id}: invalid hidden wall ids`);
  }
  if (!Array.isArray(camera.visibility?.hiddenComponentIds)
    || !camera.visibility.hiddenComponentIds.every((id) => typeof id === "string")) {
    issues.push(`${camera.id}: invalid hidden component ids`);
  }
  for (const field of ["hiddenElementIds", "preserveElementIds"]) {
    if (!Array.isArray(camera.visibility?.[field])
      || !camera.visibility[field].every((id) => typeof id === "string")) {
      issues.push(`${camera.id}: invalid ${field}`);
    }
  }
}

const result = {
  ok: issues.length === 0,
  schema: data.schema,
  rendering: data.rendering,
  authoredLightCount: data.lights?.length || 0,
  sceneCameraCount: data.cameras?.length || 0,
  issues,
};
console.log(JSON.stringify(result, null, 2));
if (issues.length) process.exit(1);
