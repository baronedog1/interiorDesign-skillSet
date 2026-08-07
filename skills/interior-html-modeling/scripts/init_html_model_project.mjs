#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const outIndex = args.indexOf("--out");
if (!args.includes("--template-only") || outIndex < 0 || !args[outIndex + 1]) {
  throw new Error("usage: --template-only --out <directory>; formal projects must use import_floorplan_handoff.mjs");
}
const out = path.resolve(args[outIndex + 1]);
if (fs.existsSync(out) && fs.readdirSync(out).length) throw new Error(`target is not empty: ${out}`);
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
fs.mkdirSync(out, { recursive: true });
fs.cpSync(path.join(root, "assets", "base-floorplan-template"), out, { recursive: true });
fs.cpSync(path.join(root, "assets", "component-library"), path.join(out, "component-library"), { recursive: true });
console.log(JSON.stringify({
  out,
  purpose: "base-template-qa-only",
  template: "assets/base-floorplan-template",
  componentLibraries: {
    movableGreen: "assets/component-library/movable-green",
    fixedPurple: "assets/component-library/fixed-purple",
  },
  structureSchema: "interior.floorplan-structure.v3",
  traceComponentsSchema: "interior.trace-components.v2",
  componentLayoutSchema: "interior.component-layout.v4",
  sceneRigSchema: "interior.scene-rig.v1",
  backendOptionsSchema: "interior.model-backend-options.v1",
  cameraPlanSchema: "interior.camera-plan.v8",
  componentLibraryVersion: "5.0.0",
  embeddedComponents: 0,
}));
