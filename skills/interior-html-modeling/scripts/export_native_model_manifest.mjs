#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
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
  const required = ["html", "handoff", "structure", "components", "model-scope", "backend-options", "out"];
  const missing = required.filter((key) => !input[key]);
  if (missing.length) throw new Error(`missing arguments: ${missing.join(", ")}`);
  const files = Object.fromEntries(Object.entries(input).map(([key, value]) => [key, path.resolve(value)]));
  const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
  const measurementAdapterPath = path.join(scriptDirectory, "measure_html_camera_envelopes.mjs");
  const captureAdapterPath = path.join(scriptDirectory, "capture_html_views.mjs");
  await Promise.all([
    fs.access(measurementAdapterPath),
    fs.access(captureAdapterPath),
  ]);
  const [handoff, structure, components, modelScope, backendOptions] = await Promise.all([
    readJson(files.handoff), readJson(files.structure), readJson(files.components), readJson(files["model-scope"]), readJson(files["backend-options"]),
  ]);
  if (
    handoff.schema !== "interior.floorplan-handoff.v3"
    || handoff.producer?.skill !== "interior-floorplan-planning"
    || !/^(6|7|8|9)\.[0-9]+\.[0-9]+$/.test(String(handoff.producer?.version || ""))
  ) {
    throw new Error("handoff must use interior.floorplan-handoff.v3 from a compatible floorplan 6.x through 9.x producer");
  }
  if (!["interior.floorplan-structure.v3", "interior.floorplan-structure.v4"].includes(structure.schema)) throw new Error("structure schema mismatch");
  if (components.schema !== "interior.component-layout.v5") throw new Error("component layout schema mismatch");
  if (backendOptions.schema !== "interior.model-backend-options.v1") throw new Error("backend options schema mismatch");
  const structureDataSha256 = await sha256(files.structure);
  const traceEntry = handoff.artifacts?.traceComponents;
  if (!traceEntry?.path || !traceEntry?.sha256) throw new Error("handoff traceComponents artifact is missing");
  const traceComponentsPath = path.resolve(path.dirname(files.handoff), traceEntry.path);
  const traceComponentsSha256 = await sha256(traceComponentsPath);
  if (traceComponentsSha256 !== traceEntry.sha256) throw new Error("handoff traceComponents artifact is stale");
  const traceComponents = await readJson(traceComponentsPath);
  if (traceComponents.schema !== "interior.trace-components.v2") throw new Error("traceComponents schema mismatch");
  if (components.source?.traceComponentsSha256 !== traceComponentsSha256) {
    throw new Error("component layout was compiled from a different traceComponents revision");
  }
  const canonicalTraceRows = (traceComponents.objects || []).map((row) => ({
    traceId: row.traceId,
    sourceObjectCandidateId: row.sourceObjectCandidateId,
    semantic: row.semantic,
    functionalClass: row.functionalClass,
  })).sort((left, right) => left.traceId.localeCompare(right.traceId));
  const canonicalMatchRows = (components.matches || []).map((row) => ({
    traceId: row.sourceTraceId,
    sourceObjectCandidateId: row.sourceObjectCandidateId,
    semantic: row.semantic,
    functionalClass: row.functionalClass,
  })).sort((left, right) => left.traceId.localeCompare(right.traceId));
  if (JSON.stringify(canonicalTraceRows) !== JSON.stringify(canonicalMatchRows)) {
    throw new Error("component layout does not exactly represent the handoff traceComponents artifact");
  }
  const componentLayoutSha256 = await sha256(files.components);
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
    measurementAdapter: { runtime: "node-chrome-cdp", script: measurementAdapterPath, interface: "interior.native-camera-measurement-adapter.v1" },
    captureAdapter: { runtime: "node-chrome-cdp", script: captureAdapterPath, interface: "interior.native-capture-adapter.v1" },
    validation: { accepted: true, primitiveFurnitureFallbackCount: 0 },
    sourceArtifacts: {
      traceComponents: {
        path: traceComponentsPath,
        sha256: traceComponentsSha256,
      },
      componentLayout: {
        path: files.components,
        sha256: componentLayoutSha256,
      },
    },
    sourceHashes: {
      structure: structureDataSha256,
      componentLayout: componentLayoutSha256,
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
