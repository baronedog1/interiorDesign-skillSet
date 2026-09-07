#!/usr/bin/env node
/** Export the real current Three.js scene for the sole Python camera solver. */

import { spawn } from "node:child_process";
import crypto from "node:crypto";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import { pathToFileURL } from "node:url";

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    if (key === "chrome-no-sandbox") result[key] = true;
    else result[key] = argv[++index];
  }
  return result;
}

function browserPath() {
  return [
    process.env.CHROME_BIN,
    "/home/agentops/agent-runtime/bin/render-chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
  ].filter(Boolean).find((candidate) => existsSync(candidate));
}

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function waitForJson(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
    } catch {
      // Chrome is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`timed out waiting for ${url}`);
}

async function openCdp(port) {
  const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" });
  if (!response.ok) throw new Error(`Chrome target creation failed: HTTP ${response.status}`);
  const target = await response.json();
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  let sequence = 0;
  const pending = new Map();
  const consoleErrors = [];
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const entry = pending.get(message.id);
      pending.delete(message.id);
      clearTimeout(entry.timer);
      if (message.error) entry.reject(new Error(message.error.message || JSON.stringify(message.error)));
      else entry.resolve(message.result || {});
      return;
    }
    if (message.method === "Runtime.exceptionThrown") {
      consoleErrors.push(message.params?.exceptionDetails?.text || "Runtime exception");
    }
  });
  const send = (method, params = {}, timeoutMs = 30000) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`${method} timed out`));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });
  return { socket, send, consoleErrors };
}

async function evaluate(send, expression, timeoutMs = 120000) {
  const response = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  }, timeoutMs);
  if (response.exceptionDetails) throw new Error(
    response.exceptionDetails.exception?.description
      || response.exceptionDetails.text
      || JSON.stringify(response.exceptionDetails)
      || "page evaluation failed",
  );
  return response.result?.value;
}

async function waitForEditor(send, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  let latest = null;
  while (Date.now() < deadline) {
    const state = await evaluate(send, `(() => ({
      ready: window.__INTERIOR_COAUTHORING_BOOT__?.ready === true,
      hasExport: Boolean(window.__INTERIOR_COAUTHORING_EDITOR__?.exportAlgorithmicScenePackage),
      error: window.__INTERIOR_COAUTHORING_BOOT__?.error || null,
      keys: Object.keys(window.__INTERIOR_COAUTHORING_EDITOR__ || {})
    }))()`);
    latest = state;
    if (state.error) throw new Error(`HTML boot failed: ${state.error}`);
    if (state.ready && state.hasExport) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`timed out waiting for coauthoring scene export bridge: ${JSON.stringify(latest)}`);
}

function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.html || !args["out-dir"]) {
    throw new Error("usage: export_html_camera_scene.mjs --html <current.html> --out-dir <dir>");
  }
  const htmlPath = path.resolve(args.html);
  const outDir = path.resolve(args["out-dir"]);
  const browser = browserPath();
  if (!browser) throw new Error("Chrome not found; set CHROME_BIN");
  await fs.mkdir(outDir, { recursive: true });
  const port = await freePort();
  const profile = path.join(outDir, ".chrome-profile-export");
  await fs.rm(profile, { recursive: true, force: true });
  const chromeArgs = [
    "--headless=new",
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    "--window-size=1280,800",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-webgl",
    "--enable-unsafe-swiftshader",
    "--allow-file-access-from-files",
    "--ignore-gpu-blocklist",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--disable-default-apps",
    "--disable-extensions",
    "--no-first-run",
    "--no-default-browser-check",
  ];
  if (args["chrome-no-sandbox"]) chromeArgs.push("--no-sandbox");
  chromeArgs.push("about:blank");
  const chrome = spawn(browser, chromeArgs, { stdio: ["ignore", "ignore", "pipe"], detached: true });
  let stderr = "";
  chrome.stderr.on("data", (chunk) => { stderr = `${stderr}${chunk}`.slice(-20000); });
  let cdp = null;
  try {
    await waitForJson(`http://127.0.0.1:${port}/json/version`, 45000);
    cdp = await openCdp(port);
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Page.navigate", { url: pathToFileURL(htmlPath).href });
    await waitForEditor(cdp.send);
    await evaluate(cdp.send, `(async()=>{const deadline=performance.now()+90000;while(performance.now()<deadline){const promise=window.__INTERIOR_MANAGED_COMPONENT_READY__;if(promise)await Promise.race([Promise.resolve(promise),new Promise(resolve=>setTimeout(resolve,5000))]);const state=window.__INTERIOR_MANAGED_COMPONENT_STATE__;if(state?.runtimeReady&&state?.settled){if(!state.ready||state.failed>0||state.unmatched>0)throw new Error('managed precise furniture did not load: '+JSON.stringify(state.errors||[]));return JSON.parse(JSON.stringify(state))}await new Promise(resolve=>setTimeout(resolve,100))}throw new Error('managed precise furniture did not settle within 90 seconds')})()`, 95000);
    const payload = await evaluate(
      cdp.send,
      "window.__INTERIOR_COAUTHORING_EDITOR__.exportAlgorithmicScenePackage()",
      180000,
    );
    if (!payload?.gltf || !payload?.nativeGeometry || !payload?.currentModel) throw new Error("HTML export bridge returned an incomplete package");
    const gltfText = `${JSON.stringify(payload.gltf)}\n`;
    const nativeText = `${JSON.stringify(payload.nativeGeometry, null, 2)}\n`;
    const gltfPath = path.join(outDir, "camera-semantic-scene.gltf");
    const nativePath = path.join(outDir, "native-scene-geometry.json");
    const modelPath = path.join(outDir, "current-model-export.json");
    await fs.writeFile(gltfPath, gltfText);
    await fs.writeFile(nativePath, nativeText);
    const modelText = `${JSON.stringify(payload.currentModel, null, 2)}\n`;
    await fs.writeFile(modelPath, modelText);
    const receipt = {
      schema: "interior.html-camera-scene-export-receipt.v1",
      status: "complete",
      downstreamReady: true,
      sourceHtml: htmlPath,
      scene: { path: gltfPath, sha256: sha256(gltfText), bytes: Buffer.byteLength(gltfText) },
      nativeGeometry: { path: nativePath, sha256: sha256(nativeText), bytes: Buffer.byteLength(nativeText) },
      currentModel: { path: modelPath, sha256: sha256(modelText), bytes: Buffer.byteLength(modelText) },
      modelMeta: payload.modelMeta || {},
      consoleErrors: cdp.consoleErrors,
      chromeStderrTail: stderr,
    };
    await fs.writeFile(path.join(outDir, "html-camera-scene-export-receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`);
    process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
  } finally {
    if (cdp) {
      await cdp.send("Browser.close").catch(() => {});
      cdp.socket.close();
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (chrome.exitCode === null) {
      try { process.kill(-chrome.pid, "SIGTERM"); } catch { /* already gone */ }
    }
    await fs.rm(profile, { recursive: true, force: true });
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
