#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { validateCompiledModelScope } from "./model_scope_contract.mjs";

function args(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    if (!argv[index].startsWith("--")) continue;
    result[argv[index].slice(2)] = argv[index + 1];
    index += 1;
  }
  return result;
}

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, "utf8"));
}

async function sha256(file) {
  return crypto.createHash("sha256").update(await fs.readFile(file)).digest("hex");
}

async function main() {
  const input = args(process.argv.slice(2));
  const required = ["html", "handoff", "structure", "components", "model-scope", "backend-options", "capture-adapter", "out"];
  const missing = required.filter((key) => !input[key]);
  if (missing.length) throw new Error(`missing arguments: ${missing.join(", ")}`);
  const files = Object.fromEntries(Object.entries(input).map(([key, value]) => [key, path.resolve(value)]));
  const [handoff, structure, components, modelScope, backendOptions] = await Promise.all([
    readJson(files.handoff), readJson(files.structure), readJson(files.components), readJson(files["model-scope"]), readJson(files["backend-options"]),
  ]);
  if (
    handoff.schema !== "interior.floorplan-handoff.v3"
    || handoff.producer?.skill !== "interior-floorplan-planning"
    || !/^6\.[0-9]+\.[0-9]+$/.test(String(handoff.producer?.version || ""))
  ) {
    throw new Error("handoff must use interior.floorplan-handoff.v3 from a compatible floorplan 6.x producer");
  }
  if (structure.schema !== "interior.floorplan-structure.v3") throw new Error("structure schema mismatch");
  if (components.schema !== "interior.component-layout.v4") throw new Error("component layout schema mismatch");
  if (backendOptions.schema !== "interior.model-backend-options.v1") throw new Error("backend options schema mismatch");
  const structureDataSha256 = await sha256(files.structure);
  validateCompiledModelScope(modelScope, structure, {
    floorplanId: handoff.floorplanId,
    handoffDigestSha256: handoff.handoffDigestSha256,
    structureDataSha256,
  });
  const manifest = {
    schema: "interior.native-model-manifest.v1",
    modelBackend: "html-threejs",
    floorplanId: handoff.floorplanId,
    handoffDigestSha256: handoff.handoffDigestSha256,
    modelScope,
    nativeModel: { path: files.html, sha256: await sha256(files.html), format: "self-contained-html", runtimeVersion: "threejs-r165" },
    coordinateTransform: {
      source: { origin: "north-west", units: "m", axes: { x: "east", y: "south", z: "up" } },
      target: { origin: "floorplan-center", units: "m", axes: { x: "east", y: "up", z: "south" } },
      cameraCoordinateSystem: "interior-world-y-up.v1",
    },
    collections: ["structure", "openings", "floors", "ceilings", "movableFurniture", "fixedFixtures", "lights", "cameras"],
    counts: {
      rooms: structure.rooms?.length || 0,
      walls: structure.walls?.length || 0,
      windows: structure.windows?.length || 0,
      connections: structure.connections?.length || 0,
      components: components.placements?.length || 0,
      ceilings: structure.rooms?.length || 0,
    },
    capabilities: { raycast: true, depth: true, entityId: true, visibilityStates: true, nativeCameraRender: true },
    captureAdapter: { runtime: "node-chrome-cdp", script: files["capture-adapter"], interface: "interior.native-capture-adapter.v1" },
    validation: { accepted: true, primitiveFurnitureFallbackCount: 0 },
    sourceHashes: {
      structure: structureDataSha256,
      components: await sha256(files.components),
      modelScope: await sha256(files["model-scope"]),
      backendOptions: await sha256(files["backend-options"]),
    },
  };
  await fs.mkdir(path.dirname(files.out), { recursive: true });
  await fs.writeFile(files.out, `${JSON.stringify(manifest, null, 2)}\n`);
  process.stdout.write(`${files.out}\n`);
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
