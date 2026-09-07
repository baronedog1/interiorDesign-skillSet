#!/usr/bin/env node
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import net from "node:net";
import { pathToFileURL } from "node:url";

const DETERMINISTIC_CAMERA_METHOD_PATTERN = /^deterministic-room-first-camera-v[0-9]+(?:\.[0-9]+)?$/;

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    if (key === "chrome-no-sandbox") args[key] = true;
    else args[key] = argv[++index];
  }
  return args;
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonical(item)]),
    );
  }
  return value;
}

function canonicalSha256(value) {
  return crypto.createHash("sha256").update(JSON.stringify(canonical(value))).digest("hex");
}

function findBrowser() {
  const candidates = [
    process.env.CHROME_BIN,
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  return candidates.find((candidate) => existsSync(candidate)) || null;
}

async function fileSha256(file) {
  return crypto.createHash("sha256").update(await fs.readFile(file)).digest("hex");
}

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function waitForJson(url, timeoutMs = 20000) {
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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const required = ["model-manifest", "frontal-seeds", "out"];
  const missing = required.filter((key) => !args[key]);
  if (missing.length) {
    throw new Error(`missing arguments: ${missing.join(", ")}`);
  }
  if (process.env.INTERIOR_FORMAL_CAMERA_MEASUREMENT !== "1") {
    throw new Error(
      "native camera measurements must be launched by interior-camera-capture/scripts/measure_native_camera_envelopes.py",
    );
  }

  const manifestPath = path.resolve(args["model-manifest"]);
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  if (manifest.schema !== "interior.native-model-manifest.v1"
      || manifest.modelBackend !== "html-threejs"
      || manifest.validation?.accepted !== true) {
    throw new Error("model manifest must be an accepted HTML native-model-manifest.v1");
  }
  const htmlPath = path.resolve(manifest.nativeModel.path);
  const htmlSha256 = await fileSha256(htmlPath);
  if (htmlSha256 !== manifest.nativeModel.sha256) {
    throw new Error("native HTML hash differs from model manifest");
  }
  const seedPath = path.resolve(args["frontal-seeds"]);
  const seeds = JSON.parse(await fs.readFile(seedPath, "utf8"));
  if (seeds.schema !== "interior.camera-frontal-seed-set.v1"
      || !DETERMINISTIC_CAMERA_METHOD_PATTERN.test(seeds.methodVersion || "")
      || seeds.sourceModelSha256 !== htmlSha256) {
    throw new Error("frontal seeds do not belong to the accepted HTML model");
  }

  const outPath = path.resolve(args.out);
  await fs.mkdir(path.dirname(outPath), { recursive: true });
  const profile = `${outPath}.chrome-profile`;
  await fs.rm(profile, { recursive: true, force: true });
  const browser = findBrowser();
  if (!browser) throw new Error("No Chrome/Chromium found. Install one or set CHROME_BIN.");
  const port = await freePort();
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
  let chromeStderr = "";
  chrome.stderr.on("data", (chunk) => {
    chromeStderr = `${chromeStderr}${chunk.toString()}`.slice(-12000);
  });

  let target = null;
  let socket = null;
  try {
    await waitForJson(`http://127.0.0.1:${port}/json/version`);
    const response = await fetch(
      `http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`,
      { method: "PUT" },
    );
    if (!response.ok) throw new Error(`Chrome target creation failed: HTTP ${response.status}`);
    target = await response.json();
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });
    let sequence = 0;
    const pending = new Map();
    const runtimeErrors = [];
    const networkErrors = [];
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && pending.has(message.id)) {
        const entry = pending.get(message.id);
        pending.delete(message.id);
        clearTimeout(entry.timer);
        if (message.error) entry.reject(new Error(message.error.message));
        else entry.resolve(message.result);
        return;
      }
      if (message.method === "Runtime.exceptionThrown") {
        runtimeErrors.push(
          message.params.exceptionDetails?.exception?.description
          || message.params.exceptionDetails?.text
          || "runtime exception",
        );
      }
      if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
        runtimeErrors.push(
          (message.params.args || []).map((arg) => arg.value || arg.description || "").join(" ")
          || "console error",
        );
      }
      if (message.method === "Log.entryAdded" && message.params.entry?.level === "error") {
        runtimeErrors.push(message.params.entry.text || "browser log error");
      }
      if (message.method === "Network.loadingFailed") {
        networkErrors.push(
          `${message.params.errorText || "network load failed"} ${message.params.blockedReason || ""}`.trim(),
        );
      }
    });
    const send = (method, params = {}, timeoutMs = 15000) => {
      const id = ++sequence;
      socket.send(JSON.stringify({ id, method, params }));
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new Error(`${method} timed out after ${timeoutMs}ms`));
        }, timeoutMs);
        pending.set(id, { resolve, reject, timer });
      });
    };
    const evaluate = async (expression, timeoutMs = 15000) => {
      const result = await send(
        "Runtime.evaluate",
        { expression, awaitPromise: true, returnByValue: true },
        timeoutMs,
      );
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result.value;
    };
    const poll = async (expression, timeoutMs = 120000) => {
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline) {
        try {
          if (await evaluate(expression)) return;
        } catch {
          // The page may still be creating its first execution context.
        }
        await new Promise((resolve) => setTimeout(resolve, 120));
      }
      throw new Error(`timed out waiting for ${expression}`);
    };

    await send("Page.enable");
    await send("Runtime.enable");
    await send("Log.enable");
    await send("Network.enable");
    const url = new URL(pathToFileURL(htmlPath).href);
    url.searchParams.set("nativeMeasurement", "1");
    await send("Page.navigate", { url: url.href }, 120000);
    await poll("document.readyState === 'complete'");
    await poll("Boolean(window.__INTERIOR_MODEL_EDITOR__?.getNativeCameraEnvelopeMeasurements)");
    const requiredComponentIds = [...new Set(
      seeds.seeds.flatMap((seed) => [
        ...(seed.anchorElementIds || []),
        ...(seed.contextElementIds || []),
      ]).filter((id) => String(id).startsWith("component-")),
    )];
    const modelComponentIds = await evaluate(
      "window.__INTERIOR_MODEL_EDITOR__.getModel().componentPlacements.map((item) => item.id)",
    );
    const missingModelIds = requiredComponentIds.filter((id) => !modelComponentIds.includes(id));
    if (missingModelIds.length) {
      throw new Error(`camera seeds reference components absent from the native model: ${missingModelIds.join(",")}`);
    }
    if (requiredComponentIds.length) {
      const requiredPayload = JSON.stringify(JSON.stringify(requiredComponentIds));
      const readinessExpression = `(() => {
        const required = JSON.parse(${requiredPayload});
        const counts = window.__INTERIOR_MODEL_AUDIT__?.componentMeshCounts || {};
        return required.every((id) => Number(counts[id] || 0) > 0);
      })()`;
      try {
        await poll(readinessExpression, 20000);
      } catch {
        const state = await evaluate(`({
          status: document.getElementById("action-status")?.textContent || "",
          audit: window.__INTERIOR_MODEL_AUDIT__ || null,
          placements: window.__INTERIOR_MODEL_EDITOR__.getModel().componentPlacements.map((item) => item.id),
        })`);
        throw new Error(
          `native component meshes did not become ready: ${JSON.stringify({
            ...state,
            runtimeErrors,
            networkErrors,
          })}`,
        );
      }
    }
    if (runtimeErrors.length) {
      throw new Error(`HTML runtime errors before native measurement: ${runtimeErrors.join(" | ")}`);
    }
    const seedPayload = JSON.stringify(JSON.stringify(seeds));
    const measurements = await evaluate(
      `window.__INTERIOR_MODEL_EDITOR__.getNativeCameraEnvelopeMeasurements(JSON.parse(${seedPayload}))`,
      120000,
    );
    if (!Array.isArray(measurements) || measurements.length !== seeds.seeds.length) {
      throw new Error("native HTML model did not return one measurement per frontal seed");
    }
    if (runtimeErrors.length) {
      throw new Error(`HTML runtime errors during native measurement: ${runtimeErrors.join(" | ")}`);
    }
    const document = {
      schema: "interior.native-camera-envelope-measurements.v1",
      producer: { skill: "interior-html-modeling", version: "24.2.0" },
      measurementSource: "same-native-html-scene-obb",
      seedSetDigestSha256: seeds.seedSetDigestSha256,
      sourceModelSha256: htmlSha256,
      measurements,
      supplementalMeasurements: [],
    };
    document.measurementDigestSha256 = canonicalSha256(document);
    await fs.writeFile(outPath, `${JSON.stringify(document, null, 2)}\n`);
    process.stdout.write(`${outPath}\n`);
  } catch (error) {
    error.message = `${error.message}${chromeStderr ? `\nChrome stderr:\n${chromeStderr}` : ""}`;
    throw error;
  } finally {
    socket?.close();
    if (target?.id) {
      await fetch(`http://127.0.0.1:${port}/json/close/${target.id}`).catch(() => {});
    }
    chrome.kill("SIGTERM");
    await new Promise((resolve) => {
      const timer = setTimeout(() => {
        chrome.kill("SIGKILL");
        resolve();
      }, 3000);
      chrome.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
    await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
