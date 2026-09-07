#!/usr/bin/env node
/** Render a frozen v3 camera plan in the current coauthoring HTML. */

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

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function pngDimensions(buffer) {
  if (buffer.length < 24 || buffer.toString("ascii", 1, 4) !== "PNG") return { width: 0, height: 0 };
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

function safeStem(value) {
  return String(value || "shot").replace(/[^\p{L}\p{N}._-]+/gu, "-").replace(/^-+|-+$/g, "") || "shot";
}

function frameFactMap(frameFacts) {
  const contents = frameFacts?.contents || {};
  return new Map(
    ["furniture", "walls", "openings"]
      .flatMap((key) => contents[key] || [])
      .filter((item) => item?.id)
      .map((item) => [item.id, item]),
  );
}

function subjectFocusFacts(shot, frameFacts) {
  const facts = frameFactMap(frameFacts);
  const primaryIds = shot.primarySubjectElementIds || shot.anchorElementIds || [];
  const companionIds = shot.companionElementIds || [];
  const subjectClusterIds = new Set([...primaryIds, ...companionIds]);
  const rows = [...primaryIds, ...companionIds].map((id) => {
    const fact = facts.get(id);
    const bounds = fact?.projection?.normalizedBounds || null;
    const firstHit = fact?.centerRayFirstHit || null;
    return {
      id,
      role: primaryIds.includes(id) ? "primary" : "companion",
      inFrame: fact?.projection?.inFrame === true,
      renderVisible: fact?.renderVisible === true,
      normalizedBounds: bounds,
      centerRayFirstHit: firstHit,
      // A dining chair in front of its own table, or a cooktop on the same
      // kitchen run, is a valid subject relationship rather than an unrelated
      // blocker.  Keep the raw first-hit fact but only flag occlusion when the
      // hit falls outside the declared primary/companion cluster.
      centerOccluded: Boolean(firstHit?.id && firstHit.id !== id && !subjectClusterIds.has(firstHit.id)),
      croppedAtFrameEdge: Boolean(bounds && (bounds.left <= 0.004 || bounds.top <= 0.004
        || bounds.right >= 0.996 || bounds.bottom >= 0.996)),
    };
  });
  const primaryBounds = rows.filter((row) => row.role === "primary" && row.normalizedBounds)
    .map((row) => row.normalizedBounds);
  const union = primaryBounds.length ? {
    left: Math.min(...primaryBounds.map((item) => item.left)),
    top: Math.min(...primaryBounds.map((item) => item.top)),
    right: Math.max(...primaryBounds.map((item) => item.right)),
    bottom: Math.max(...primaryBounds.map((item) => item.bottom)),
  } : null;
  const coverage = union ? Math.max(0, union.right - union.left) * Math.max(0, union.bottom - union.top) : 0;
  const center = union ? { x: (union.left + union.right) / 2, y: (union.top + union.bottom) / 2 } : null;
  const issues = [];
  if (rows.some((row) => row.role === "primary" && !row.inFrame)) issues.push("primary-out-of-frame");
  if (rows.some((row) => row.role === "primary" && row.croppedAtFrameEdge)) issues.push("primary-cropped");
  if (rows.some((row) => row.role === "primary" && row.centerOccluded)) issues.push("primary-center-occluded");
  if (coverage > 0 && coverage < 0.045) issues.push("primary-too-small");
  if (coverage > 0.62) issues.push("primary-too-close");
  if (center && (Math.abs(center.x - 0.5) > 0.24 || Math.abs(center.y - 0.58) > 0.28)) issues.push("primary-off-balance");
  return {
    module: "code-derived-subject-focus-v2",
    primarySubjectIds: primaryIds,
    companionIds,
    subjects: rows,
    primaryUnionBounds: union,
    primaryCoverageRatio: Math.round(coverage * 100000) / 100000,
    primaryFrameCenter: center,
    advisoryIssues: issues,
    advisoryOnly: true,
  };
}

function normalizedProjectionCrop(shot) {
  const raw = shot?.targetSpacePolicy?.projectionCrop || shot?.projectionCrop;
  if (!raw) return null;
  const crop = {
    left: Math.max(0, Math.min(1, Number(raw.left))),
    top: Math.max(0, Math.min(1, Number(raw.top))),
    right: Math.max(0, Math.min(1, Number(raw.right))),
    bottom: Math.max(0, Math.min(1, Number(raw.bottom))),
    source: raw.source || "target-space-projection-crop",
    imageRecognitionUsed: false,
  };
  if (!(crop.right - crop.left >= 0.10 && crop.bottom - crop.top >= 0.10)) {
    throw new Error(`invalid target-space projection crop for ${shot.shotId}`);
  }
  return crop;
}

function remapBounds(bounds, crop) {
  if (!bounds || !crop) return bounds;
  const width = crop.right - crop.left;
  const height = crop.bottom - crop.top;
  const left = Math.max(0, Math.min(1, (Number(bounds.left) - crop.left) / width));
  const right = Math.max(0, Math.min(1, (Number(bounds.right) - crop.left) / width));
  const top = Math.max(0, Math.min(1, (Number(bounds.top) - crop.top) / height));
  const bottom = Math.max(0, Math.min(1, (Number(bounds.bottom) - crop.top) / height));
  return { left, top, right, bottom };
}

function remapFrameFacts(frameFacts, crop, sourceViewport, outputViewport) {
  if (!crop) return frameFacts;
  const output = structuredClone(frameFacts);
  const contents = output.contents || {};
  for (const key of ["furniture", "walls", "openings"]) {
    contents[key] = (contents[key] || []).filter((item) => {
      const bounds = item?.projection?.normalizedBounds;
      if (!bounds) return false;
      const intersects = Number(bounds.right) > crop.left
        && Number(bounds.left) < crop.right
        && Number(bounds.bottom) > crop.top
        && Number(bounds.top) < crop.bottom;
      if (!intersects) return false;
      item.projection.normalizedBounds = remapBounds(bounds, crop);
      item.projection.inFrame = true;
      return true;
    });
  }
  output.croppedOutRoomIds = (output.visibleRoomIds || []).filter((roomId) => roomId !== output.roomId);
  output.visibleRoomIds = [output.roomId];
  output.sourceViewport = sourceViewport;
  output.viewport = outputViewport;
  output.camera.projectionCrop = crop;
  output.evidence.projection = "native-threejs-frame-remapped-by-code-derived-target-space-crop";
  return output;
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
    if (message.method === "Runtime.consoleAPICalled" && message.params?.type === "error") {
      consoleErrors.push((message.params.args || []).map((item) => item.value || item.description || "").join(" "));
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
  return { target, socket, send, consoleErrors };
}

async function evaluate(send, expression, timeoutMs = 30000) {
  const response = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  }, timeoutMs);
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || "page evaluation failed");
  return response.result?.value;
}

async function waitForEditor(send, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const state = await evaluate(send, `(() => ({
      ready: window.__INTERIOR_COAUTHORING_BOOT__?.ready === true,
      hasEditor: Boolean(window.__INTERIOR_COAUTHORING_EDITOR__?.setAlgorithmicCamera),
      error: window.__INTERIOR_COAUTHORING_BOOT__?.error || null
    }))()`);
    if (state.error) throw new Error(`HTML boot failed: ${state.error}`);
    if (state.ready && state.hasEditor) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error("timed out waiting for coauthoring editor camera bridge");
}

async function waitForShotFacts(send, roomId, primaryIds, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let latest = null;
  while (Date.now() < deadline) {
    latest = await evaluate(send,
      `window.__INTERIOR_COAUTHORING_EDITOR__.getAlgorithmicFrameFacts(${JSON.stringify(roomId)})`);
    const facts = frameFactMap(latest);
    if (!primaryIds.length || primaryIds.every((id) => facts.get(id)?.renderVisible === true)) return latest;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return latest;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.html || !args.plan || !args["out-dir"]) {
    throw new Error("usage: capture_coauthoring_cameras.mjs --html <standalone.html> --plan <camera-plan.json> --out-dir <dir>");
  }
  const viewport = String(args.viewport || "1600x1000").split("x").map(Number);
  if (viewport.length !== 2 || viewport.some((value) => !Number.isInteger(value) || value < 480)) {
    throw new Error("--viewport must look like 1600x1000");
  }
  const waitMs = Number(args["wait-ms"] || 600);
  const htmlPath = path.resolve(args.html);
  const planPath = path.resolve(args.plan);
  const outDir = path.resolve(args["out-dir"]);
  const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
  if (plan.schema !== "interior.algorithmic-camera-plan.v3") throw new Error("unsupported camera plan schema");
  if (!Array.isArray(plan.shots) || plan.shots.length === 0) throw new Error("camera plan contains no shots");
  const htmlBuffer = await fs.readFile(htmlPath);
  const browser = browserPath();
  if (!browser) throw new Error("Chrome not found; set CHROME_BIN");
  await fs.mkdir(outDir, { recursive: true });
  const port = await freePort();
  const profile = path.join(outDir, ".chrome-profile");
  await fs.rm(profile, { recursive: true, force: true });
  const chromeArgs = [
    "--headless=new",
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    `--window-size=${viewport[0]},${viewport[1]}`,
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-webgl",
    "--enable-unsafe-swiftshader",
    "--allow-file-access-from-files",
    "--ignore-gpu-blocklist",
    "--hide-scrollbars",
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
  chrome.stderr.on("data", (chunk) => {
    stderr = `${stderr}${chunk}`.slice(-20000);
  });
  let cdp = null;
  const records = [];
  try {
    await waitForJson(`http://127.0.0.1:${port}/json/version`, 45000);
    cdp = await openCdp(port);
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: viewport[0], height: viewport[1], deviceScaleFactor: 1, mobile: false,
    });
    await cdp.send("Page.navigate", { url: pathToFileURL(htmlPath).href });
    await waitForEditor(cdp.send);
    await evaluate(cdp.send, `window.__INTERIOR_COAUTHORING_EDITOR__.setAlgorithmicCaptureMode(true)`);
    await evaluate(cdp.send, `(async()=>{const deadline=performance.now()+90000;while(performance.now()<deadline){const promise=window.__INTERIOR_MANAGED_COMPONENT_READY__;if(promise)await Promise.race([Promise.resolve(promise),new Promise(resolve=>setTimeout(resolve,5000))]);const state=window.__INTERIOR_MANAGED_COMPONENT_STATE__;if(state?.runtimeReady&&state?.settled){if(!state.ready||state.failed>0||state.unmatched>0)throw new Error('managed precise furniture did not load: '+JSON.stringify(state.errors||[]));return JSON.parse(JSON.stringify(state))}await new Promise(resolve=>setTimeout(resolve,100))}throw new Error('managed precise furniture did not settle within 90 seconds')})()`, 95000);
    for (const shot of [...plan.shots].sort((left, right) => left.sequenceOrder - right.sequenceOrder)) {
      const stem = `${String(shot.sequenceOrder).padStart(2, "0")}-${safeStem(shot.roomName || shot.roomId)}`;
      const imagePath = path.join(outDir, `${stem}.png`);
      const jsonPath = path.join(outDir, `${stem}.json`);
      const started = performance.now();
      const record = { shotId: shot.shotId, roomId: shot.roomId, roomName: shot.roomName, ok: false };
      try {
        const hiddenElementIds = new Set([
          ...(shot.hiddenWallIds || []),
          ...(shot.hiddenOpeningIds || []),
          ...(shot.hiddenElementIds || []),
        ]);
        // The renderer has no camera or hiding decision rights.  It applies the
        // exact frozen pose and exact hidden set selected by the sole solver.
        const captureShot = { ...shot, hiddenElementIds: [...hiddenElementIds] };
        await evaluate(cdp.send, `window.__INTERIOR_COAUTHORING_EDITOR__.setAlgorithmicCamera(${JSON.stringify(captureShot)})`);
        await new Promise((resolve) => setTimeout(resolve, waitMs));
        const fullFrameFacts = await waitForShotFacts(
          cdp.send,
          shot.roomId,
          shot.primarySubjectElementIds || shot.anchorElementIds || [],
        );
        const projectionCrop = normalizedProjectionCrop(captureShot);
        const clip = projectionCrop ? {
          x: Math.floor(projectionCrop.left * viewport[0]),
          y: Math.floor(projectionCrop.top * viewport[1]),
          width: Math.max(1, Math.ceil((projectionCrop.right - projectionCrop.left) * viewport[0])),
          height: Math.max(1, Math.ceil((projectionCrop.bottom - projectionCrop.top) * viewport[1])),
          scale: 1,
        } : null;
        const screenshot = await cdp.send("Page.captureScreenshot", {
          format: "png",
          fromSurface: true,
          captureBeyondViewport: false,
          ...(clip ? { clip } : {}),
        }, 60000);
        const png = Buffer.from(screenshot.data, "base64");
        const dimensions = pngDimensions(png);
        const frameFacts = remapFrameFacts(
          fullFrameFacts,
          projectionCrop,
          { width: viewport[0], height: viewport[1] },
          dimensions,
        );
        await fs.writeFile(imagePath, png);
        const paired = {
          schema: "interior.camera-image-facts.v3",
          schemaVersion: "3.0",
          generation: {
            method: "code-derived-from-native-threejs-scene",
            imageRecognitionUsed: false,
            generatedAt: new Date().toISOString(),
            htmlSha256: sha256(htmlBuffer),
            planDigestSha256: plan.planDigestSha256,
          },
          shot: captureShot,
          image: {
            filename: path.basename(imagePath),
            sha256: sha256(png),
            bytes: png.length,
            ...dimensions,
            projectionCrop,
          },
          visibleScene: frameFacts,
          subjectFocus: subjectFocusFacts(shot, frameFacts),
          semanticInventory: shot.semanticInventory || [],
          expectedRoomElementIds: shot.expectedRoomElementIds || [],
          evaluationPolicy: {
            advisoryOnly: true,
            deliveryBlocked: false,
            customerRunAction: "always-deliver-image-and-json",
            releaseRegressionAction: "improve-shared-algorithm-never-hand-tune-this-shot",
          },
        };
        await fs.writeFile(jsonPath, `${JSON.stringify(paired, null, 2)}\n`);
        Object.assign(record, {
          ok: true,
          image: imagePath,
          json: jsonPath,
          imageSha256: paired.image.sha256,
          frameFactsDigestSha256: sha256(Buffer.from(JSON.stringify(frameFacts))),
          durationMs: Math.round((performance.now() - started) * 100) / 100,
          hiddenElementIds: [...hiddenElementIds],
          projectionCrop,
          geometryOccluderPasses: 0,
          deliveredScreenshotCount: 1,
        });
      } catch (error) {
        record.error = String(error?.stack || error);
      }
      records.push(record);
      process.stderr.write(`[${records.length}/${plan.shots.length}] ${shot.roomName}: ${record.ok ? "ok" : "error"}\n`);
    }
    await evaluate(cdp.send, `window.__INTERIOR_COAUTHORING_EDITOR__.setAlgorithmicCaptureMode(false)`).catch(() => {});
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
  const index = {
    schema: "interior.camera-delivery-index.v1",
    schemaVersion: "1.0",
    producer: { skill: "interior-camera-capture", version: "47.0.1" },
    html: { path: htmlPath, sha256: sha256(htmlBuffer) },
    plan: { path: planPath, digestSha256: plan.planDigestSha256 },
    capture: {
      viewport: { width: viewport[0], height: viewport[1] },
      browser,
      sequentialSingleBrowser: true,
      oneSolvedPoseAndOneDeliveredScreenshotPerShot: true,
      consoleErrors: cdp?.consoleErrors || [],
      chromeStderrTail: stderr,
    },
    records,
    summary: {
      requested: plan.shots.length,
      delivered: records.filter((record) => record.ok).length,
      failed: records.filter((record) => !record.ok).length,
      deliveryBlocked: false,
    },
  };
  const indexPath = path.join(outDir, "camera-delivery-index.json");
  await fs.writeFile(indexPath, `${JSON.stringify(index, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({ index: indexPath, summary: index.summary }, null, 2)}\n`);
  if (index.summary.failed) process.exitCode = 2;
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
