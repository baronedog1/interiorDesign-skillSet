import { pathToFileURL } from "node:url";
import path from "node:path";

const skillRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const templateRoot = path.join(skillRoot, "assets", "interior-coauthoring-template");
const componentRoot = path.join(skillRoot, "assets", "component-library");
const aliases = new Map([
  ["three", path.join(templateRoot, "vendor", "three.module.js")],
  ["three/addons/loaders/GLTFLoader.js", path.join(templateRoot, "vendor", "loaders", "GLTFLoader.js")],
  ["three/addons/utils/BufferGeometryUtils.js", path.join(templateRoot, "vendor", "utils", "BufferGeometryUtils.js")],
  ["@interior/library-contract", path.join(componentRoot, "shared", "library-contract.js")],
  ["@interior/movable-green-catalog", path.join(componentRoot, "movable-green", "catalog.js")],
  ["@interior/fixed-purple-catalog", path.join(componentRoot, "fixed-purple", "catalog.js")],
  ["@interior/component-catalog", path.join(componentRoot, "index.js")],
  ["@interior/component-library", path.join(componentRoot, "component-library.js")],
  ["@interior/placement-geometry", path.join(componentRoot, "shared", "placement-geometry.js")],
]);

export async function resolve(specifier, context, nextResolve) {
  const target = aliases.get(specifier);
  if (target) return { url: pathToFileURL(target).href, shortCircuit: true };
  return nextResolve(specifier, context);
}
