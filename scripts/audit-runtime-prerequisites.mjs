#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outArg = process.argv.find((value) => value.startsWith('--out-dir='));
const outIndex = process.argv.indexOf('--out-dir');
const outDir = path.resolve(outArg
  ? outArg.slice('--out-dir='.length)
  : (outIndex >= 0 && process.argv[outIndex + 1] ? process.argv[outIndex + 1] : path.join(repoRoot, 'runtime-audit')));

function findExecutable(name) {
  if (!name) return null;
  if (name.includes('/')) {
    try {
      fs.accessSync(name, fs.constants.X_OK);
      // Preserve the configured entry path. Resolving a venv's `bin/python`
      // to the system interpreter disables the venv's site-packages.
      return path.resolve(name);
    } catch {
      return null;
    }
  }
  for (const directory of String(process.env.PATH || '').split(path.delimiter)) {
    if (!directory) continue;
    const candidate = path.join(directory, name);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return path.resolve(candidate);
    } catch {
      // Continue searching PATH.
    }
  }
  return null;
}

function firstExecutable(values) {
  for (const value of values) {
    const found = findExecutable(value);
    if (found) return found;
  }
  return null;
}

function commandVersion(command, args = ['--version']) {
  if (!command) return null;
  try {
    return execFileSync(command, args, { encoding: 'utf8', timeout: 15_000, stdio: ['ignore', 'pipe', 'pipe'] })
      .trim().split(/\r?\n/)[0].slice(0, 240);
  } catch {
    return null;
  }
}

function pathFact(value, type = 'any') {
  const input = String(value || '').trim();
  if (!input) return { configured: false, exists: false, path: null };
  try {
    const absolute = path.resolve(input);
    const stat = fs.statSync(absolute);
    const matchesType = type === 'directory' ? stat.isDirectory() : (type === 'file' ? stat.isFile() : true);
    return {
      configured: true,
      exists: matchesType,
      path: absolute,
      type: stat.isDirectory() ? 'directory' : (stat.isFile() ? 'file' : 'other'),
      readable: (() => { try { fs.accessSync(absolute, fs.constants.R_OK); return true; } catch { return false; } })(),
    };
  } catch {
    return { configured: true, exists: false, path: path.resolve(input) };
  }
}

function pythonImports(python, modules) {
  if (!python) return Object.fromEntries(modules.map((moduleName) => [moduleName, false]));
  const script = modules.map((moduleName) => `import ${moduleName}`).join('; ');
  try {
    execFileSync(python, ['-c', script], { timeout: 20_000, stdio: 'ignore' });
    return Object.fromEntries(modules.map((moduleName) => [moduleName, true]));
  } catch {
    const result = {};
    for (const moduleName of modules) {
      try {
        execFileSync(python, ['-c', `import ${moduleName}`], { timeout: 10_000, stdio: 'ignore' });
        result[moduleName] = true;
      } catch {
        result[moduleName] = false;
      }
    }
    return result;
  }
}

function all(...values) {
  return values.every(Boolean);
}

function readiness(localReady, options = {}) {
  if (!localReady) return { status: 'blocked', reason: options.blockedReason || 'missing-required-local-runtime' };
  if (options.conditional) return { status: 'conditional', reason: options.conditionalReason || 'requires-accepted-upstream-input' };
  if (options.degraded) return { status: 'degraded', reason: options.degradedReason || 'optional-external-integration-not-configured' };
  return { status: 'ready', reason: 'local-runtime-preflight-passed' };
}

const python = firstExecutable([process.env.DESIGN_PYTHON_BIN, 'python3']);
const node = firstExecutable([
  process.env.DESIGN_NODE_BIN,
  '/home/agentops/agent-runtime/bin/node',
  'node',
]);
const browser = firstExecutable([
  process.env.CHROME_BIN,
  process.env.CAD_BROWSER_BIN,
  'google-chrome-stable',
  'google-chrome',
  'chromium',
  'chromium-browser',
]);
const browserIsSnap = Boolean(browser && (browser.startsWith('/snap/') || browser.includes('/snap/')));
const blender = firstExecutable([process.env.BLENDER_BIN, '/home/agentops/agent-runtime/bin/blender', 'blender']);
const cadPython = firstExecutable([
  process.env.CAD_PYTHON_BIN,
  '/home/agentops/.local/share/codex-cad-runtime/bin/python',
]);
const pythonModules = pythonImports(python, ['PIL', 'numpy', 'cv2', 'jsonschema']);
const cadModules = pythonImports(cadPython, ['build123d', 'OCP', 'cadpy', 'PIL']);
const commands = Object.fromEntries([
  'ffmpeg', 'ffprobe', 'pdfinfo', 'pdfimages', 'pdftoppm', 'gs', 'qpdf', 'convert',
].map((name) => [name, findExecutable(name)]));

const componentStore = pathFact(
  process.env.INTERIOR_COMPONENT_ASSET_STORE || '/home/agentops/agent-runtime/shared-assets/interior-component-library-v5',
  'directory',
);
const blenderStore = pathFact(
  process.env.INTERIOR_BLENDER_ASSET_STORE || '/home/agentops/agent-runtime/shared-assets/blender-interior-research',
  'directory',
);
const cadStore = pathFact(
  process.env.INTERIOR_CAD_ASSET_STORE || '/home/agentops/agent-runtime/workspaces/interior-design-2/cad-asset-library',
  'directory',
);
const idkSecret = pathFact(process.env.IDK_ENV_FILE || '', 'file');
const videoSecret = pathFact(process.env.SEEDANCE_VIDEO_SECRET_FILE || '', 'file');
const cadSnapshotConfigured = Boolean(String(process.env.INTERIOR_CAD_SNAPSHOT_COMMAND || '').trim());
const imagegenDeclared = /^(1|true|yes)$/i.test(String(process.env.CODEX_IMAGEGEN_AVAILABLE || ''));

const facts = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  host: { hostname: os.hostname(), platform: os.platform(), arch: os.arch(), user: os.userInfo().username },
  executables: {
    python: { path: python, version: commandVersion(python, ['--version']) },
    node: { path: node, version: commandVersion(node, ['--version']) },
    browser: { path: browser, version: commandVersion(browser, ['--version']), nonSnap: Boolean(browser && !browserIsSnap) },
    blender: { path: blender, version: commandVersion(blender, ['--version']) },
    cadPython: { path: cadPython, version: commandVersion(cadPython, ['--version']) },
    ...Object.fromEntries(Object.entries(commands).map(([name, command]) => [name, { path: command, version: commandVersion(command) }])),
  },
  pythonModules,
  cadModules,
  assets: { componentStore, blenderStore, cadStore },
  integrations: {
    idk: { configured: Boolean(idkSecret.exists), secretPathExists: Boolean(idkSecret.exists) },
    seedance: { configured: Boolean(videoSecret.exists || process.env.VOLCENGINE_ARK_API_KEY), secretPathExists: Boolean(videoSecret.exists) },
    videoReferenceQuery: { configured: Boolean(process.env.AI_NATIVE_DB_URL || process.env.DATA_KNOWLEDGE_DB_URL || process.env.AI_VIDEO_REFERENCE_QUERY_SSH_TARGET) },
    cadSnapshot: { configured: cadSnapshotConfigured },
    codexImagegen: { declaredAvailable: imagegenDeclared },
  },
};

const browserReady = Boolean(browser && !browserIsSnap);
const pythonImageReady = all(python, pythonModules.PIL, pythonModules.numpy, pythonModules.cv2, pythonModules.jsonschema);
const cadReady = all(cadPython, cadModules.build123d, cadModules.OCP, cadModules.cadpy, cadModules.PIL, browserReady);
const pdfReady = all(python, browserReady, commands.pdfinfo, commands.pdfimages, commands.pdftoppm, commands.gs);
const videoLocalReady = all(node, commands.ffmpeg, commands.ffprobe);
const blenderReady = all(blender, blenderStore.exists);
const htmlReady = all(node, python, browserReady, componentStore.exists);

const skillReadiness = {
  schemaVersion: 1,
  generatedAt: facts.generatedAt,
  host: facts.host,
  skills: {
    'booklet-production': readiness(pdfReady, { blockedReason: 'browser-or-core-pdf-tools-missing' }),
    cad: readiness(cadReady, { blockedReason: 'cad-runtime-or-non-snap-browser-missing' }),
    'cad-object-modeling': readiness(all(cadReady, pythonModules.PIL, pythonModules.numpy, pythonModules.jsonschema), { blockedReason: 'cad-runtime-viewer-or-python-modules-missing' }),
    'cad-viewer': readiness(all(node, browserReady), { blockedReason: 'node-or-non-snap-browser-missing' }),
    'cad-zh': readiness(cadReady, { blockedReason: 'cad-runtime-or-non-snap-browser-missing' }),
    'idk-canvas-ingest-agent': readiness(Boolean(node), { degraded: !idkSecret.exists, degradedReason: 'dry-run-only-idk-credential-not-configured' }),
    'imagegen-batch-orchestrator': readiness(Boolean(python), { conditional: !imagegenDeclared, conditionalReason: 'requires-codex-imagegen-session-capability' }),
    'interior-blender-modeling': readiness(blenderReady, { blockedReason: 'fixed-blender-or-asset-store-missing', conditional: blenderReady, conditionalReason: 'requires-accepted-floorplan-handoff' }),
    'interior-cad-modeling': readiness(all(cadReady, cadStore.exists, cadSnapshotConfigured), { blockedReason: 'cad-runtime-asset-store-or-snapshot-command-missing', conditional: true, conditionalReason: 'requires-accepted-floorplan-handoff' }),
    'interior-camera-capture': readiness(Boolean(browserReady || blenderReady || (cadReady && cadSnapshotConfigured)), { blockedReason: 'no-supported-capture-backend-ready', degraded: !(browserReady && blenderReady && cadReady && cadSnapshotConfigured), degradedReason: 'only-subset-of-html-blender-cad-backends-ready' }),
    'interior-circulation-planning': readiness(Boolean(python), { conditional: true, conditionalReason: 'requires-accepted-model-and-circulation-inputs' }),
    'interior-design-video-production': readiness(videoLocalReady, { blockedReason: 'node-or-ffmpeg-tools-missing', degraded: !(facts.integrations.seedance.configured && facts.integrations.videoReferenceQuery.configured), degradedReason: 'local-video-ready-external-generation-or-reference-query-unconfigured' }),
    'interior-floorplan-planning': readiness(pythonImageReady, { blockedReason: 'pillow-numpy-opencv-or-jsonschema-missing' }),
    'interior-html-modeling': readiness(htmlReady, { blockedReason: 'node-python-browser-or-component-store-missing', conditional: true, conditionalReason: 'requires-accepted-floorplan-handoff' }),
    'interior-space-rendering': readiness(all(python, pythonModules.PIL), { conditional: true, conditionalReason: imagegenDeclared ? 'requires-accepted-q1-q2-q3-and-scene-map' : 'requires-codex-imagegen-and-accepted-q1-q2-q3' }),
    'movable-furniture-modeling': readiness(all(pythonImageReady, node, browserReady), { blockedReason: 'python-image-modules-node-or-non-snap-browser-missing', conditional: true, conditionalReason: 'requires-sufficient-multiview-product-evidence' }),
  },
};

fs.mkdirSync(outDir, { recursive: true, mode: 0o700 });
fs.writeFileSync(path.join(outDir, 'runtime-inventory.json'), `${JSON.stringify(facts, null, 2)}\n`, { mode: 0o600 });
fs.writeFileSync(path.join(outDir, 'skill-readiness.json'), `${JSON.stringify(skillReadiness, null, 2)}\n`, { mode: 0o600 });

const counts = Object.values(skillReadiness.skills).reduce((acc, item) => {
  acc[item.status] = (acc[item.status] || 0) + 1;
  return acc;
}, {});
process.stdout.write(`${JSON.stringify({ ok: true, outDir, counts })}\n`);
