#!/usr/bin/env node
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import net from "node:net";
import { pathToFileURL } from "node:url";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    if (["dry-run", "chrome-no-sandbox"].includes(key)) args[key] = true;
    else args[key] = argv[++index];
  }
  return args;
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

function baseUrl(raw) {
  if (/^https?:\/\//.test(raw) || raw.startsWith("file://")) return raw;
  return pathToFileURL(path.resolve(raw)).href;
}

function shotUrl(base, shotId) {
  const url = new URL(base);
  url.searchParams.set("capture", "1");
  url.searchParams.set("shot", shotId);
  return url.href;
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

function pngDimensions(buffer) {
  if (buffer.length < 24 || buffer.toString("ascii", 1, 4) !== "PNG") return { width: 0, height: 0 };
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
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

function modelRevision(sceneSource) {
  const stable = {
    floorplanId: sceneSource.floorplanId,
    entities: sceneSource.entities.map((item) => ({
      entityId: item.entityId,
      sourceModelId: item.sourceModelId,
      semanticType: item.semanticType,
      category: item.category,
      roomIds: item.roomIds,
      worldBounds: item.worldBounds,
      worldTransform: item.worldTransform,
      dimensionsMeters: item.dimensionsMeters,
    })),
  };
  const digest = crypto
    .createHash("sha256")
    .update(JSON.stringify(canonical(stable)))
    .digest("hex")
    .slice(0, 16);
  return `model-${digest}`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args["model-manifest"] || !args["shots-manifest"] || !args["out-dir"]) {
    throw new Error("usage: capture_html_views.mjs --model-manifest <native-model-manifest.json> --shots-manifest <camera-plan.json> --out-dir <dir>");
  }
  if (!args["dry-run"] && process.env.INTERIOR_FORMAL_CAPTURE_DISPATCH !== "1") {
    throw new Error(
      "real screenshots must be launched by interior-camera-capture/scripts/capture_model_views.py; direct adapter execution is forbidden",
    );
  }
  const viewport = String(args.viewport || "1600x1000").split("x").map(Number);
  if (viewport.length !== 2 || viewport.some((value) => !Number.isInteger(value) || value < 320)) {
    throw new Error("--viewport must look like 1600x1000");
  }
  const waitMs = Number(args["wait-ms"] || 700);
  const nativeManifestPath = path.resolve(args["model-manifest"]);
  const nativeManifest = JSON.parse(await fs.readFile(nativeManifestPath, "utf8"));
  if (nativeManifest.schema !== "interior.native-model-manifest.v1"
      || nativeManifest.modelBackend !== "html-threejs"
      || nativeManifest.validation?.accepted !== true) {
    throw new Error("model manifest must be an accepted html-threejs native-model-manifest.v1");
  }
  const htmlPath = path.resolve(nativeManifest.nativeModel.path);
  const htmlBuffer = await fs.readFile(htmlPath);
  const htmlSha256 = crypto.createHash("sha256").update(htmlBuffer).digest("hex");
  if (htmlSha256 !== nativeManifest.nativeModel.sha256) {
    throw new Error("native HTML hash differs from model manifest");
  }
  const planPath = path.resolve(args["shots-manifest"]);
  const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
  if (plan.schema !== "interior.camera-plan.v8" || plan.schemaVersion !== "8.0") {
    throw new Error("camera plan must use interior.camera-plan.v8");
  }
  if (plan.methodVersion !== "deterministic-wall-normal-camera-v7") {
    throw new Error("camera plan must use deterministic-wall-normal-camera-v7");
  }
  if (plan.modelBackend !== "html-threejs" || plan.sourceModelSha256 !== htmlSha256) {
    throw new Error("camera plan backend/model hash differs from native HTML");
  }
  const orderedShots = plan.shots
    .filter((shot) => shot.selectionStatus === "selected")
    .sort((left, right) => left.sequenceOrder - right.sequenceOrder);
  for (const shot of orderedShots) {
    if (shot.composition !== "one-point-frontal") continue;
    if (Math.abs(Number(shot.position?.[1]) - Number(shot.target?.[1])) > 0.001) {
      throw new Error(`${shot.shotId}: frontal target height must equal camera height`);
    }
    if (shot.frontalAlignment?.mode !== "reference-wall-normal"
      || shot.frontalAlignment?.rayHitsReferenceWall !== true
      || shot.frontalAlignment?.sensorPlaneParallelToWall !== true) {
      throw new Error(`${shot.shotId}: validated frontalAlignment is required before capture`);
    }
  }
  const requestedShotIds = args["shot-ids"]
    ? new Set(String(args["shot-ids"]).split(",").map((item) => item.trim()).filter(Boolean))
    : null;
  const shots = requestedShotIds
    ? orderedShots.filter((shot) => requestedShotIds.has(shot.shotId))
    : args["shot-id"]
      ? orderedShots.filter((shot) => shot.shotId === args["shot-id"])
    : orderedShots.slice(0, args.limit ? Number(args.limit) : orderedShots.length);
  if (!shots.length) throw new Error("No shots matched --shot-id/--limit");
  const base = baseUrl(htmlPath);
  const outDir = path.resolve(args["out-dir"]);
  await fs.mkdir(outDir, { recursive: true });
  const resources = args["dry-run"]
    ? { dryRun: true }
    : {
        ownership: "interior-camera-capture/scripts/capture_model_views.py",
        formalDispatcher: process.env.INTERIOR_FORMAL_CAPTURE_DISPATCH === "1",
        heldGlobalCaptureSlot: process.env.INTERIOR_CAPTURE_SLOT_HELD || null,
        globalScreenshotConcurrencyLimit: 2,
      };
  const captures = [];

  if (args["dry-run"]) {
    for (const shot of shots) {
      const stem = `${String(shot.sequenceOrder).padStart(2, "0")}-${shot.shotId}`;
      captures.push({
        shotId: shot.shotId,
        sequenceOrder: shot.sequenceOrder,
        url: shotUrl(base, shot.shotId),
        slotGuidedImage: path.join(outDir, `${stem}.slot-guided.png`),
        furnishedQaImage: path.join(outDir, `${stem}.furnished-qa.png`),
        semanticFrame: path.join(
          outDir,
          `${stem}.semantic-frame.json`,
        ),
        semanticEntityMask: path.join(
          outDir,
          `${stem}.semantic-entity-id.png`,
        ),
        semanticRoomMask: path.join(
          outDir,
          `${stem}.semantic-room-id.png`,
        ),
        cameraPlanEvidenceImage: path.join(
          outDir,
          `${stem}.camera-plan-evidence.png`,
        ),
        cameraPlanEvidenceJson: path.join(
          outDir,
          `${stem}.camera-plan-evidence.json`,
        ),
        ok: true,
      });
    }
  } else {
    const externalChrome = Boolean(args["debug-port"]);
    const port = externalChrome ? Number(args["debug-port"]) : await freePort();
    let profile = null;
    let chrome = null;
    let chromeStderr = "";
    if (!externalChrome) {
      const browser = findBrowser();
      if (!browser) throw new Error("No Chrome/Chromium found. Install one or set CHROME_BIN.");
      profile = path.join(outDir, ".chrome-profile");
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
      chrome = spawn(browser, chromeArgs, { stdio: ["ignore", "ignore", "pipe"], detached: true });
      chrome.stderr.on("data", (chunk) => {
        chromeStderr += chunk.toString();
        if (chromeStderr.length > 16000) chromeStderr = chromeStderr.slice(-16000);
      });
    }

    try {
      await waitForJson(`http://127.0.0.1:${port}/json/version`);
      for (const [shotIndex, shot] of shots.entries()) {
        process.stderr.write(`[capture ${shotIndex + 1}/${shots.length}] ${shot.shotId}\n`);
        const url = shotUrl(base, shot.shotId);
        const stem = `${String(shot.sequenceOrder).padStart(2, "0")}-${shot.shotId}`;
        const slotGuidedOutput = path.join(outDir, `${stem}.slot-guided.png`);
        const furnishedQaOutput = path.join(outDir, `${stem}.furnished-qa.png`);
        const cameraPlanEvidenceOutput = path.join(outDir, `${stem}.camera-plan-evidence.png`);
        const cameraPlanEvidenceJsonOutput = path.join(outDir, `${stem}.camera-plan-evidence.json`);
        const record = {
          shotId: shot.shotId,
          sequenceOrder: shot.sequenceOrder,
          url,
          slotGuidedImage: slotGuidedOutput,
          furnishedQaImage: furnishedQaOutput,
          cameraPlanEvidenceImage: cameraPlanEvidenceOutput,
          cameraPlanEvidenceJson: cameraPlanEvidenceJsonOutput,
          ok: false,
        };
        let target = null;
        let socket = null;
        try {
          const targetResponse = await fetch(
            `http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`,
            { method: "PUT" },
          );
          if (!targetResponse.ok) throw new Error(`Chrome target creation failed: HTTP ${targetResponse.status}`);
          target = await targetResponse.json();
          if (!target.webSocketDebuggerUrl) throw new Error("Chrome did not expose a page target");
          socket = new WebSocket(target.webSocketDebuggerUrl);
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
              if (message.error) entry.reject(new Error(message.error.message));
              else entry.resolve(message.result);
              return;
            }
            let error = null;
            if (message.method === "Runtime.exceptionThrown") {
              error = message.params.exceptionDetails?.exception?.description || message.params.exceptionDetails?.text;
            } else if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
              error = message.params.args.map((item) => item.value || item.description || "").join(" ");
            } else if (message.method === "Log.entryAdded" && message.params.entry?.level === "error") {
              error = message.params.entry.text;
            }
            if (error && !/favicon\.ico/i.test(error)) consoleErrors.push(error);
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
                // The target may still be creating its first execution context.
              }
              await new Promise((resolve) => setTimeout(resolve, 120));
            }
            throw new Error(`timed out waiting for ${expression}`);
          };

          await send("Page.enable");
          await send("Runtime.enable");
          await send("Log.enable");
          await send("Network.enable");
          await send("Network.setCacheDisabled", { cacheDisabled: true });
          const externalPlanSource = JSON.stringify(JSON.stringify(plan));
          await send("Page.addScriptToEvaluateOnNewDocument", {
            source: `(() => {
              const deepFreeze = (value) => {
                if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
                Object.values(value).forEach(deepFreeze);
                return Object.freeze(value);
              };
              const lockedPlan = deepFreeze(JSON.parse(${externalPlanSource}));
              Object.defineProperty(window, "__CAMERA_PLAN__", {
                configurable: false,
                enumerable: true,
                get() { return lockedPlan; },
                set() { /* Discard the standalone HTML's historical embedded plan. */ },
              });
              Object.defineProperty(window, "__CAMERA_PLAN_RUNTIME_SOURCE__", {
                configurable: false,
                enumerable: true,
                value: "external-formal-camera-plan-v8",
                writable: false,
              });
            })();`,
          });
          await send("Emulation.setDeviceMetricsOverride", {
            width: viewport[0],
            height: viewport[1],
            deviceScaleFactor: 1,
            mobile: false,
          });
          const navigationUrl = new URL(url);
          navigationUrl.searchParams.set("captureRun", `${Date.now()}-${shot.sequenceOrder}`);
          await send("Page.navigate", { url: navigationUrl.href }, 120000);
          await poll("document.readyState === 'complete'");
          await poll("Boolean(window.__INTERIOR_MODEL_EDITOR__) && document.body.classList.contains('capture')");
          await poll(`window.__INTERIOR_MODEL_EDITOR__.getActiveCaptureShotId() === ${JSON.stringify(shot.shotId)}`);
          const poseAudit = await evaluate(
            "window.__INTERIOR_MODEL_EDITOR__.getActiveCapturePoseAudit()",
          );
          const runtimePlanSource = await evaluate("window.__CAMERA_PLAN_RUNTIME_SOURCE__");
          if (runtimePlanSource !== "external-formal-camera-plan-v8") {
            throw new Error(`${shot.shotId}: external camera-plan override did not take effect`);
          }
          if (poseAudit?.schema !== "interior.html-capture-pose-audit.v1"
              || poseAudit.shotId !== shot.shotId
              || poseAudit.accepted !== true
              || Number(poseAudit.directionDot) < 0.999999
              || poseAudit.controlsUpdateAppliedAfterPose !== false) {
            throw new Error(`${shot.shotId}: HTML camera pose drifted from the accepted plan`);
          }
          const routeError = await evaluate("document.getElementById('action-status')?.classList.contains('error') ? document.getElementById('action-status').textContent : ''");
          if (routeError) throw new Error(routeError);
          await new Promise((resolve) => setTimeout(resolve, waitMs));
          await evaluate(
            "window.__INTERIOR_MODEL_EDITOR__.setCapturePresentationMode('furnished-qa')",
          );
          await evaluate(
            "window.__INTERIOR_MODEL_EDITOR__.setStructureAppearance('concrete-shell')",
          );
          const furnishedQaScreenshot = await send(
            "Page.captureScreenshot",
            { format: "png", fromSurface: true, captureBeyondViewport: false },
            120000,
          );
          const furnishedQaBuffer = Buffer.from(furnishedQaScreenshot.data, "base64");
          await fs.writeFile(furnishedQaOutput, furnishedQaBuffer);
          const furnishedQaDimensions = pngDimensions(furnishedQaBuffer);
          const semanticFramePath = path.join(outDir, `${stem}.semantic-frame.json`);
          const semanticEntityMaskPath = path.join(outDir, `${stem}.semantic-entity-id.png`);
          const semanticRoomMaskPath = path.join(outDir, `${stem}.semantic-room-id.png`);
          const semanticFrame = await evaluate(
            `window.__INTERIOR_MODEL_EDITOR__.getSceneSemanticFrame(${
              JSON.stringify(shot.shotId)
            }, ${
              JSON.stringify({
                slotGuided: path.basename(slotGuidedOutput),
                furnishedQa: path.basename(furnishedQaOutput),
              })
            }, [${
              furnishedQaDimensions.width
            }, ${
              furnishedQaDimensions.height
            }])`,
            120000,
          );
          if (semanticFrame?.schema !== "interior.scene-semantic-frame.v4") {
            throw new Error("HTML 模板未返回 scene-semantic-frame.v4");
          }
          semanticFrame.modelBackend = "html-threejs";
          semanticFrame.sourceModelSha256 = htmlSha256;
          const writeSemanticMask = async (field, outputPath, label) => {
            const dataUrl = semanticFrame[field]?.dataUrl;
            if (!String(dataUrl || "").startsWith("data:image/png;base64,")) {
              throw new Error(`HTML 模板未返回 ${label} PNG`);
            }
            const buffer = Buffer.from(
              dataUrl.slice("data:image/png;base64,".length),
              "base64",
            );
            const dimensions = pngDimensions(buffer);
            if (
              dimensions.width !== semanticFrame.semanticRaster?.size?.[0]
              || dimensions.height !== semanticFrame.semanticRaster?.size?.[1]
            ) {
              throw new Error(`${label} PNG 尺寸与 semanticRaster 不一致`);
            }
            await fs.writeFile(outputPath, buffer);
            delete semanticFrame[field].dataUrl;
            semanticFrame[field].image = path.basename(outputPath);
            semanticFrame[field].byteLength = buffer.length;
            return buffer;
          };
          const semanticEntityMaskBuffer = await writeSemanticMask(
            "entitySemanticMask",
            semanticEntityMaskPath,
            "实体语义 ID",
          );
          const semanticRoomMaskBuffer = await writeSemanticMask(
            "roomSemanticMask",
            semanticRoomMaskPath,
            "空间语义 ID",
          );
          semanticFrame.modelRevision = modelRevision(semanticFrame);
          await fs.writeFile(
            semanticFramePath,
            `${JSON.stringify(semanticFrame, null, 2)}\n`,
          );
          await evaluate(
            "window.__INTERIOR_MODEL_EDITOR__.setCapturePresentationMode('slot-guided')",
          );
          await new Promise((resolve) => setTimeout(resolve, 100));
          const readability = await evaluate(
            "window.__INTERIOR_MODEL_EDITOR__.getFrameReadability()",
            60000,
          );
          const screenshot = await send(
            "Page.captureScreenshot",
            { format: "png", fromSurface: true, captureBeyondViewport: false },
            120000,
          );
          const buffer = Buffer.from(screenshot.data, "base64");
          await fs.writeFile(slotGuidedOutput, buffer);
          const dimensions = pngDimensions(buffer);
          if (
            dimensions.width !== semanticFrame.imageSize[0]
            || dimensions.height !== semanticFrame.imageSize[1]
          ) {
            throw new Error("槽位引导图尺寸与语义 ID 帧尺寸不一致");
          }
          const cameraPlanEvidence = await evaluate(
            `window.__INTERIOR_MODEL_EDITOR__.captureCameraPlanEvidenceDataUrl(${JSON.stringify(shot.shotId)})`,
            120000,
          );
          if (
            cameraPlanEvidence?.facts?.schema !== "interior.camera-plan-evidence.v2"
            || cameraPlanEvidence?.facts?.source !== "same-native-model-camera-state"
          ) {
            throw new Error("HTML 模板未返回同源 camera-plan-evidence.v2");
          }
          if (!String(cameraPlanEvidence?.dataUrl || "").startsWith("data:image/png;base64,")) {
            throw new Error("HTML 模板未返回同源二维机位 PNG");
          }
          const cameraPlanEvidenceBuffer = Buffer.from(
            cameraPlanEvidence.dataUrl.slice("data:image/png;base64,".length),
            "base64",
          );
          const cameraPlanEvidenceDimensions = pngDimensions(cameraPlanEvidenceBuffer);
          if (cameraPlanEvidenceDimensions.width < 320 || cameraPlanEvidenceDimensions.height < 320) {
            throw new Error("同源二维机位证据尺寸异常");
          }
          const formalVisibility = structuredClone(shot.visibility || {});
          formalVisibility.mustShowElements = structuredClone(
            shot.mustShowElements || formalVisibility.mustShowElements || [],
          );
          const formalCameraPlanEvidence = {
            ...cameraPlanEvidence.facts,
            modelBackend: plan.modelBackend,
            sourceModelSha256: plan.sourceModelSha256,
            coordinateSystem: "interior-world-y-up.v1",
            visibility: formalVisibility,
            runtimeCameraPlanSource: runtimePlanSource,
          };
          await fs.writeFile(cameraPlanEvidenceOutput, cameraPlanEvidenceBuffer);
          await fs.writeFile(
            cameraPlanEvidenceJsonOutput,
            `${JSON.stringify(formalCameraPlanEvidence, null, 2)}\n`,
          );
          record.semanticFrame = semanticFramePath;
          record.semanticEntityMask = semanticEntityMaskPath;
          record.semanticRoomMask = semanticRoomMaskPath;
          record.semanticMaskBytes = {
            entity: semanticEntityMaskBuffer.length,
            room: semanticRoomMaskBuffer.length,
          };
          record.furnishedQaEvidence = {
            ...furnishedQaDimensions,
            byteLength: furnishedQaBuffer.length,
            obviouslyNonBlank: furnishedQaBuffer.length > 10000,
          };
          record.modelRevision = semanticFrame.modelRevision;
          record.capturePoseAudit = poseAudit;
          record.runtimeCameraPlanSource = runtimePlanSource;
          record.cameraPlanEvidence = {
            schema: formalCameraPlanEvidence.schema,
            source: formalCameraPlanEvidence.source,
            image: cameraPlanEvidenceOutput,
            json: cameraPlanEvidenceJsonOutput,
            ...cameraPlanEvidenceDimensions,
            byteLength: cameraPlanEvidenceBuffer.length,
            obviouslyNonBlank: cameraPlanEvidenceBuffer.length > 10000,
          };
          record.availableEvidenceStates = ["slot-guided", "furnished-qa"];
          record.defaultGenerationMode = "slot-guided";
          record.imageEvidence = {
            ...dimensions,
            byteLength: buffer.length,
            obviouslyNonBlank: buffer.length > 10000,
            readability,
          };
          record.consoleErrors = consoleErrors;
          record.ok = record.imageEvidence.obviouslyNonBlank
            && record.furnishedQaEvidence.obviouslyNonBlank
            && record.cameraPlanEvidence.obviouslyNonBlank
            && readability?.readable === true
            && record.consoleErrors.length === 0;
          if (!readability?.readable) {
            record.retakeReason = "槽位引导画面亮度或层次不可读，必须调整本 shot 的打光/曝光后重拍";
          }
          process.stderr.write(`[capture ${shotIndex + 1}/${shots.length}] ${record.ok ? "ok" : "failed"} ${buffer.length} bytes\n`);
        } catch (error) {
          record.ok = false;
          record.error = error.message;
          process.stderr.write(`[capture ${shotIndex + 1}/${shots.length}] failed: ${error.message}\n`);
        } finally {
          socket?.close();
          if (target?.id) {
            await fetch(`http://127.0.0.1:${port}/json/close/${target.id}`).catch(() => {});
          }
        }
        captures.push(record);
      }
    } finally {
      if (chrome) {
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
      }
      if (profile) {
        await fs.rm(profile, {
          recursive: true,
          force: true,
          maxRetries: 5,
          retryDelay: 200,
        });
      }
      if (captures.some((item) => !item.ok)) {
        captures.filter((item) => !item.ok).forEach((item) => {
          item.chromeStderrTail = chromeStderr.slice(-2000);
        });
      }
    }
  }

  const manifest = {
    schemaVersion: "9.0",
    schema: "interior.camera-capture-manifest.v9",
    modelBackend: "html-threejs",
    sourceModelSha256: htmlSha256,
    modelSchema: plan.modelSchema,
    floorplanId: plan.floorplanId,
    seriesId: plan.seriesId,
    purpose: plan.purpose,
    methodVersion: plan.methodVersion,
    planPhase: plan.planPhase,
    roomCoverage: plan.roomCoverage,
    lightingSetups: plan.lightingSetups,
    base,
    capturedAt: new Date().toISOString(),
    viewport: { width: viewport[0], height: viewport[1] },
    resourceEvidence: resources,
    chromeOwnership: args["debug-port"] ? "external-debug-port" : "script-managed",
    shots,
    captures,
    manualVisualReview: [],
    note: "Each shot emits one generation-authoritative concrete-shell slot-guided image, one same-camera furnished QA image, one same-native HTML 2D camera evidence frame, GPU semantic masks and exact model-derived JSON. Only slot-guided may be submitted to image generation.",
  };
  const manifestPath = path.join(outDir, "model-capture-manifest.json");
  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  const nativeResult = {
    schema: "interior.native-capture-result.v1",
    modelBackend: "html-threejs",
    sourceModelSha256: htmlSha256,
    coordinateSystem: "interior-world-y-up.v1",
    preparedOnly: Boolean(args["dry-run"]),
    accepted: !args["dry-run"] && captures.every((item) => item.ok),
    records: captures.map((item) => ({
      shotId: item.shotId,
      images: {
        "slot-guided": item.slotGuidedImage,
        "furnished-qa": item.furnishedQaImage,
      },
      semanticFrame: item.semanticFrame,
      entityIdPass: item.semanticEntityMask,
      roomIdPass: item.semanticRoomMask,
      cameraEvidenceImage: item.cameraPlanEvidenceImage,
      cameraEvidenceJson: item.cameraPlanEvidenceJson,
      capturePoseAudit: item.capturePoseAudit,
      nativeRaycastSource: "threejs-gpu-id-depth",
      ok: item.ok,
    })),
  };
  await fs.writeFile(
    path.join(outDir, "capture-result.json"),
    `${JSON.stringify(nativeResult, null, 2)}\n`,
  );
  const ok = captures.every((item) => item.ok);
  process.stdout.write(`${JSON.stringify({ manifest: manifestPath, ok, dryRun: Boolean(args["dry-run"]) })}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
