#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import {
  checkSeedanceConnectivity,
  prepareSeedanceCredential,
  seedanceEndpointBase
} from './seedance_runtime.mjs';

const args = process.argv.slice(2);

const usage = () => {
  console.error([
    'Usage:',
    '  node scripts/generate_seedance_video_from_storyboard.mjs <video-storyboard-plan.json> --out <manifest.json> [--dry-run]',
    '  node scripts/generate_seedance_video_from_storyboard.mjs <video-storyboard-plan.json> --out <manifest.json> --execute --confirm-paid-generation',
    '  node scripts/generate_seedance_video_from_storyboard.mjs <video-storyboard-plan.json> --out <manifest.json> --execute --confirm-paid-generation --chain-extend',
    '',
    'Default mode is dry-run. Real Seedance calls require both --execute and --confirm-paid-generation.'
  ].join('\n'));
};

const argValue = (name, defaultValue = null) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : defaultValue;
};

const hasFlag = (name) => args.includes(name);

const planPath = args.find((value) => !value.startsWith('--'));
const outPath = argValue('--out', 'seedance-video-generation-manifest.json');
const execute = hasFlag('--execute');
const confirmedPaid = hasFlag('--confirm-paid-generation');
const dryRun = hasFlag('--dry-run') || !execute;
const chainExtend = hasFlag('--chain-extend') || hasFlag('--sequential-extension');
const maxShotsRaw = argValue('--max-shots', null);
const maxShots = maxShotsRaw === null ? null : Number.parseInt(maxShotsRaw, 10);
if (maxShotsRaw !== null && (!Number.isInteger(maxShots) || maxShots < 1)) {
  console.error('--max-shots must be a positive integer.');
  process.exit(2);
}

if (!planPath) {
  usage();
  process.exit(2);
}

if (execute && !confirmedPaid) {
  console.error('Refusing real Seedance call: --confirm-paid-generation is required with --execute.');
  process.exit(2);
}

const readJson = (filePath) => JSON.parse(fs.readFileSync(filePath, 'utf8'));

const endpointBase = () => seedanceEndpointBase();

const positiveIntegerEnv = (name, defaultValue) => {
  const raw = process.env[name];
  if (!raw) return defaultValue;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${name} must be a positive integer.`);
  }
  return value;
};

const modelId = (policy = {}) => {
  const requested = String(policy.model || policy.modelName || 'seedance 2.0').trim().toLowerCase();
  if (requested.includes('fast')) {
    return (process.env.SEEDANCE20_FAST_VIDEO_MODEL_ID || 'doubao-seedance-2-0-fast-260128').trim();
  }
  return (process.env.SEEDANCE20_VIDEO_MODEL_ID || 'doubao-seedance-2-0-260128').trim();
};

const normalizeRatio = (value) => {
  const ratio = String(value || '16:9').trim();
  if (!['16:9', '9:16', '1:1', '4:3', '3:4'].includes(ratio)) {
    throw new Error(`Unsupported Seedance ratio: ${ratio}`);
  }
  return ratio;
};

const seedance2Duration = (seconds) => {
  const numeric = Number(seconds);
  const requested = Number.isFinite(numeric) && numeric > 0 ? numeric : 8;
  return Math.min(15, Math.max(5, Math.ceil(requested)));
};

const estimatedCostCny = (plan, shot) => {
  if (Number.isFinite(Number(shot.estimatedCostCny)) && Number(shot.estimatedCostCny) >= 0) {
    return Number(shot.estimatedCostCny);
  }
  const rate = Number(plan.pricing?.estimatedCnyPerSecond);
  return Number.isFinite(rate) && rate >= 0
    ? Number((seedance2Duration(shot.durationSec) * rate).toFixed(2))
    : null;
};

const isHttpUrl = (value) => /^https?:\/\//i.test(String(value || '').trim());
const hasChineseText = (value) => /[\u4e00-\u9fff]/.test(String(value || ''));
const storyboardUrlFrom = (storyboard) => {
  const value = String(storyboard?.imageUrl || storyboard?.cdnUrl || storyboard?.url || '').trim();
  return isHttpUrl(value) ? value : '';
};

const imageMap = (plan) => {
  const map = new Map();
  for (const image of plan.images || []) {
    if (image && image.id) map.set(String(image.id), image);
  }
  return map;
};

const urlsFromReferenceItems = (items = []) => {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => (typeof item === 'string' ? item : item?.url || item?.video_url))
    .filter(isHttpUrl);
};

const validateGlobalReferenceVideos = (plan) => {
  const refs = Array.isArray(plan.globalReferenceVideos) ? plan.globalReferenceVideos : [];
  if ((plan.shots || []).some((shot) => Array.isArray(shot.referenceVideos) && shot.referenceVideos.length)) {
    throw new Error('Use globalReferenceVideos[] only. Shot-level referenceVideos are forbidden by the current design-video planning rule.');
  }
  const totalDuration = refs.reduce((sum, item) => sum + Number(item.durationSeconds || item.duration || 0), 0);
  if (totalDuration > 15) {
    throw new Error(`Seedance reference videos total duration must be <= 15 seconds; current total is ${totalDuration}.`);
  }
  const aspectToKey = new Map();
  for (const item of refs) {
    const uses = Array.isArray(item.referenceUse) ? item.referenceUse : [item.referenceUse].filter(Boolean);
    for (const use of uses) {
      const key = String(use).trim();
      if (!key) continue;
      if (aspectToKey.has(key)) {
        throw new Error(`Only one reference video may own each reference aspect. Duplicate aspect: ${key}`);
      }
      aspectToKey.set(key, item.key || item.title || item.url || item.video_url || 'reference');
    }
  }
  return refs;
};


const validateStoryboardPlanning = (plan) => {
  const storyboard = plan.storyboardSketch || plan.storyboard || null;
  const storyboardUrl = storyboardUrlFrom(storyboard);
  if (!storyboard || !storyboardUrl) {
    throw new Error('storyboardSketch.imageUrl/cdnUrl must be an https CDN URL before Seedance dry-run or execution. Local/relative paths are forbidden.');
  }
  const panels = Array.isArray(plan.storyboardPanels) ? plan.storyboardPanels : (Array.isArray(storyboard.panels) ? storyboard.panels : []);
  if (!panels.length) {
    throw new Error('storyboardPanels[] are required before Seedance dry-run.');
  }
  for (const panel of panels) {
    const panelText = [panel.timeRange, panel.shotId, panel.roughVisual || panel.visual, panel.cameraCue || panel.camera, panel.transitionCue || panel.transition].join(' ');
    if (!hasChineseText(panelText)) {
      throw new Error('Storyboard panels must use Simplified Chinese labels and descriptions. Regenerate the Codex native storyboard sketch if it uses English labels.');
    }
  }
  const forbiddenOpenings = ['本案', '本空间', '本设计'];
  for (const shot of plan.shots || []) {
    const lines = shot.dialogueLines || (shot.voiceover?.text ? [shot.voiceover] : []);
    if (!lines.length) throw new Error(`Shot ${shot.id || shot.title || ''} is missing dialogueLines[].`);
    for (const line of lines) {
      const text = String(line.text || '');
      if (!text.trim()) throw new Error(`Shot ${shot.id || shot.title || ''} has an empty dialogue line.`);
      if (forbiddenOpenings.some((word) => text.trim().startsWith(word))) {
        throw new Error(`Dialogue should use a friendly guided-tour opening instead of stiff phrasing: ${word}`);
      }
    }
    const beats = shot.microBeats || [];
    if (!beats.length) throw new Error(`Shot ${shot.id || shot.title || ''} is missing microBeats[].`);
    for (const beat of beats) {
      const required = ['cameraPath', 'framing', 'movement', 'transitionIn', 'transitionOut', 'focusObject', 'detailCue', 'bgmCue', 'sfxCue', 'lightingCue'];
      for (const key of required) {
        if (!String(beat[key] || '').trim()) {
          throw new Error(`Shot ${shot.id || shot.title || ''} microBeat ${beat.start ?? ''}-${beat.end ?? ''} is missing ${key}.`);
        }
      }
    }
  }
};

const normalizeText = (value) => String(value || '').trim();

const formatDialogueLines = (shot) => {
  const lines = shot.dialogueLines || (shot.voiceover?.text ? [shot.voiceover] : []);
  return lines.map((line, index) => {
    const start = line.start ?? line.speechStartSec ?? shot.startSec ?? 0;
    const end = line.end ?? line.speechEndSec ?? (Number(start) + Number(shot.durationSec || 0));
    const cps = line.charsPerSecond ? `，语速 ${line.charsPerSecond} 字/秒` : '';
    return `${index + 1}. ${line.speakerName || '虚拟设计顾问'} ${start}-${end}s${cps}：${line.text || ''}`;
  }).join('\n');
};

const formatMicroBeats = (shot) => {
  const beats = shot.microBeats || [];
  return beats.map((beat, index) => [
    `分镜 ${index + 1}: ${beat.start ?? ''}-${beat.end ?? ''}s`,
    beat.shotSize ? `景别=${beat.shotSize}` : '',
    beat.camera ? `机位=${beat.camera}` : '',
    beat.cameraPath ? `镜头路径=${beat.cameraPath}` : '',
    beat.framing ? `构图=${beat.framing}` : '',
    beat.movement ? `运动=${beat.movement}` : '',
    beat.transitionIn ? `入场=${beat.transitionIn}` : '',
    beat.transitionOut ? `出场=${beat.transitionOut}` : '',
    beat.focusObject ? `焦点=${beat.focusObject}` : '',
    beat.detailCue ? `细节=${beat.detailCue}` : '',
    beat.dialogue ? `对应台词=${beat.dialogue}` : '',
    beat.bgmCue ? `BGM=${beat.bgmCue}` : '',
    beat.sfxCue ? `音效=${beat.sfxCue}` : '',
    beat.lightingCue ? `灯光=${beat.lightingCue}` : ''
  ].filter(Boolean).join('；')).join('\n');
};

const virtualHumanInfo = (plan) => {
  const character = plan.aiCharacter || {};
  if (!character.enabled) return null;
  const assetId = String(character.assetId || character.asset_id || '').trim();
  const assetUri = String(character.assetUri || character.asset_uri || '').trim();
  const library = String(character.library || character.matchingSource || '').trim();
  if (!assetId || !assetUri || !library) {
    throw new Error('aiCharacter.enabled=true requires library, assetId and assetUri from the Seedance virtual human library.');
  }
  const sssid = String(character.sssid || character.seedanceSssid || assetId).trim();
  const seedanceAssetUri = String(character.seedanceAssetUri || character.seedance_asset_uri || assetUri).trim();
  if (!sssid || !seedanceAssetUri) {
    throw new Error('aiCharacter.enabled=true requires sssid and seedanceAssetUri for Seedance role binding.');
  }
  return {
    library,
    assetId,
    assetUri,
    sssid,
    seedanceAssetUri,
    displayLabel: character.displayLabel || character.display_label || '',
    description: character.description || '',
    roleName: character.roleName || character.speakerName || '虚拟设计顾问',
    appearancePrompt: character.appearancePrompt || character.appearance || character.description || '',
    wardrobeNote: character.wardrobeNote || character.clothingDetail || character.outfitDetail || '米白或浅咖现代中式轻奢套装，干净利落，适合家居设计顾问带看。',
    voiceStyle: character.voiceStyle || '亲切、专业、像导购带客户看样板间，中文自然口播。',
    selectionRationale: character.selectionRationale || ''
  };
};

const buildPrompt = (plan, shot, virtualHuman, options = {}) => {
  const images = imageMap(plan);
  const shotImages = (shot.imageIds || [])
    .map((id) => images.get(String(id)))
    .filter(Boolean)
    .map((image) => `${image.title || image.id}: ${image.url}`)
    .join('\n');
  const referenceSummary = (options.referenceItems || [])
    .map((item) => `${item.title || item.key || '参考视频'}：只参考${Array.isArray(item.referenceUse) ? item.referenceUse.join('、') : item.referenceUse || '镜头语言'}；${item.referenceNotes || item.summary || ''}`)
    .join('\n');
  const extensionText = options.extensionMode
    ? [
        '生成模式：本片段必须基于上一段 provider 视频做连续延长。',
        `上一段镜头：${options.previousShotId || 'previous-shot'}。`,
        '必须从上一段最后一帧自然继续，不重新开场，不重复上一段入场，不再采纳全局参考视频，不出现第二个无关开头。',
        '除上一段 provider 视频和官方人物 asset 外，不得引入新的外部参考视频或外部空间。'
      ].join('\n')
    : [
        '生成模式：第一段原生生成。允许使用全局参考视频学习运镜、镜头质感和空间节奏。',
        '全局参考视频只作为镜头语言参考，不借用其中的空间、家具、人物或装饰。'
      ].join('\n');
  const characterText = virtualHuman
    ? [
        `人物角色：${virtualHuman.roleName}。`,
        `必须使用 Seedance 官方/可信人像资产：sssid=${virtualHuman.sssid}，seedanceAssetUri=${virtualHuman.seedanceAssetUri}，assetId=${virtualHuman.assetId}，assetUri=${virtualHuman.assetUri}。`,
        `形象设定：${virtualHuman.displayLabel || ''}。${virtualHuman.appearancePrompt || virtualHuman.description || ''}`,
        `穿着与衣服细节：${virtualHuman.wardrobeNote}`,
        `口播气质：${virtualHuman.voiceStyle}`,
        '人物脸型、五官和身份一致性以官方 asset 为准，不得随机生成其它模特。'
      ].join('\n')
    : '本片段不添加 AI 人物。';
  const dialogue = formatDialogueLines(shot);
  const microBeats = formatMicroBeats(shot);
  const hardBoundary = [
    '硬性空间限制：只能展示当前方案图中已经出现的客餐厅/客厅空间。',
    '严禁生成图片里没有呈现的房间、走廊、卧室、厨房、卫生间、阳台、窗外景观或其它项目空间。',
    '只允许在当前图片范围内前推、横移、轻微环绕、拉近、特写和焦点转移；不得改户型、不得替换家具、不得新增大型家具。',
    '局部细节必须来自当前图中的圆桌、餐椅、吊灯、木饰面、石材电视墙、沙发或收纳，不得使用外部风格图/家具图。'
  ].join('\n');
  const parts = [
    extensionText,
    characterText,
    `镜头标题：${shot.title || shot.id || ''}`,
    shot.prompt ? `完整场景提示词：${shot.prompt}` : '',
    shot.cameraMove ? `总体运镜：${shot.cameraMove}` : '',
    shot.notes ? `备注：${shot.notes}` : '',
    dialogue ? `完整台词，必须按文本口播，不得改成泛泛介绍：\n${dialogue}` : '',
    microBeats ? `逐秒分镜和导演要求：\n${microBeats}` : '',
    shotImages ? `当前方案图证据：\n${shotImages}` : '',
    referenceSummary && !options.extensionMode ? `全局参考视频用法：\n${referenceSummary}` : '',
    plan.referenceNotes && !options.extensionMode ? `参考说明：${plan.referenceNotes}` : '',
    hardBoundary,
    '输出要求：中文口播清晰，画面自然，人物与空间比例真实，镜头语言按分镜执行。'
  ].filter(Boolean);
  const prompt = parts.join('\n\n');
  if (!prompt.trim()) throw new Error(`Shot ${shot.id || shot.title || ''} is missing prompt text.`);
  return prompt;
};

const PREVIOUS_PROVIDER_VIDEO_PLACEHOLDER = 'https://previous-provider-video.invalid/previous-scene.mp4';

const buildTaskPayloads = (plan) => {
  const images = imageMap(plan);
  const virtualHuman = virtualHumanInfo(plan);
  let shots = Array.isArray(plan.shots) && plan.shots.length ? plan.shots : [];
  if (!shots.length) throw new Error('video-storyboard-plan.json must contain shots[].');
  if (maxShots !== null) shots = shots.slice(0, maxShots);
  validateStoryboardPlanning(plan);
  const globalReferenceItems = validateGlobalReferenceVideos(plan);
  const globalReferenceVideos = urlsFromReferenceItems(globalReferenceItems)
    .filter((url, urlIndex, urls) => urls.indexOf(url) === urlIndex);
  const selectedReferenceImages = Array.isArray(plan.referenceImageUrls)
    ? plan.referenceImageUrls.filter(isHttpUrl)
    : [];

  const storyboard = plan.storyboardSketch || plan.storyboard || null;
  const storyboardImageUrl = storyboardUrlFrom(storyboard);
  const sequentialExtension = chainExtend || shots.length > 1 || String(plan.videoGenerationMode || plan.generationMode || '').includes('extension');
  return shots.map((shot, index) => {
    if (Number(shot.durationSec) > 15) {
      throw new Error(`Shot ${shot.id || shot.title || index + 1} durationSec exceeds Seedance 2.0 single-video limit of 15 seconds. Split or extend serially.`);
    }
    const extensionMode = sequentialExtension && index > 0;
    const previousShotId = extensionMode ? String(shots[index - 1]?.id || `shot-${index}`) : null;
    const shotImages = (shot.imageIds || [])
      .map((id) => images.get(String(id)))
      .filter(Boolean)
      .map((image) => image.url)
      .filter(isHttpUrl)
      .slice(0, 4);
    const selectedReferenceVideos = extensionMode ? [] : globalReferenceVideos;
    const firstFrame = shotImages[0] || null;
    const prompt = buildPrompt(plan, shot, virtualHuman, {
      extensionMode,
      previousShotId,
      referenceItems: globalReferenceItems
    });
    const content = [
      { type: 'text', text: `${prompt}\n\n分镜参考图用途：只控制镜头站位、运镜节奏、人物位置、焦点细节和转场，不替代最终空间效果。` },
      ...(virtualHuman ? [{ type: 'image_url', image_url: { url: virtualHuman.seedanceAssetUri }, role: 'reference_image' }] : []),
      ...(extensionMode
        ? [{ type: 'video_url', video_url: { url: PREVIOUS_PROVIDER_VIDEO_PLACEHOLDER }, role: 'reference_video' }]
        : [
            { type: 'image_url', image_url: { url: storyboardImageUrl }, role: 'reference_image' },
            ...(firstFrame ? [{ type: 'image_url', image_url: { url: firstFrame }, role: 'reference_image' }] : []),
            ...shotImages.slice(1).map((url) => ({ type: 'image_url', image_url: { url }, role: 'reference_image' })),
            ...selectedReferenceImages.slice(0, 4).map((url) => ({ type: 'image_url', image_url: { url }, role: 'reference_image' })),
            ...selectedReferenceVideos.slice(0, 3).map((url) => ({ type: 'video_url', video_url: { url }, role: 'reference_video' }))
          ])
    ];
    return {
      localShotId: String(shot.id || `shot-${index + 1}`),
      title: shot.title || `镜头 ${index + 1}`,
      endpoint: `${endpointBase()}/contents/generations/tasks`,
      virtualHuman,
      extensionMode,
      dependsOnPreviousShotId: previousShotId,
      referenceVideoUrls: selectedReferenceVideos.slice(0, 3),
      continuityReferenceVideoUrl: extensionMode ? PREVIOUS_PROVIDER_VIDEO_PLACEHOLDER : null,
      storyboardImageUrl: extensionMode ? null : storyboardImageUrl,
      estimatedCostCny: estimatedCostCny(plan, shot),
      body: {
        model: modelId(plan.seedancePromptPolicy || {}),
        content,
        resolution: String(plan.seedancePromptPolicy?.resolution || '720p'),
        ratio: normalizeRatio(shot.aspectRatio || plan.aspectRatio),
        duration: seedance2Duration(shot.durationSec),
        generate_audio: plan.seedancePromptPolicy?.generateAudio !== false,
        watermark: false,
        character: virtualHuman ? {
          sssid: virtualHuman.sssid,
          seedance_asset_uri: virtualHuman.seedanceAssetUri,
          asset_id: virtualHuman.assetId,
          asset_uri: virtualHuman.assetUri,
          wardrobe_note: virtualHuman.wardrobeNote,
          role_name: virtualHuman.roleName
        } : undefined
      }
    };
  });
};

const materializeTaskBody = (task, previousResult = null) => {
  const body = JSON.parse(JSON.stringify(task.body));
  if (!task.extensionMode) return body;
  const previousVideoUrl = String(previousResult?.videoUrl || '').trim();
  if (!isHttpUrl(previousVideoUrl)) {
    throw new Error(`Shot ${task.localShotId} requires previous provider video URL from ${task.dependsOnPreviousShotId}, but none was available.`);
  }
  for (const item of body.content || []) {
    if (item?.type === 'video_url' && item.video_url?.url === PREVIOUS_PROVIDER_VIDEO_PLACEHOLDER) {
      item.video_url.url = previousVideoUrl;
    }
  }
  return body;
};

const parseResponseJson = async (response) => {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Provider returned non-JSON response: HTTP ${response.status}`);
  }
};

const seedanceRequest = async (pathSuffix, method, apiKey, body = undefined) => {
  const controller = new AbortController();
  const timeout = positiveIntegerEnv('SEEDANCE_VIDEO_REQUEST_TIMEOUT_MS', 30000);
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${endpointBase()}${pathSuffix}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal
    });
    const json = await parseResponseJson(response);
    if (!response.ok) {
      const message = json?.error?.message || json?.message || json?.msg || response.statusText || `HTTP ${response.status}`;
      throw new Error(`Seedance API request failed: ${message}`);
    }
    return json;
  } finally {
    clearTimeout(timer);
  }
};

const taskIdFrom = (response) => String(response?.id || response?.task_id || response?.taskId || response?.data?.id || response?.output?.task_id || '').trim();
const statusFrom = (response) => String(response?.status || response?.data?.status || response?.output?.task_status || response?.task_status || '').trim().toLowerCase();
const videoUrlFrom = (response) => {
  const candidates = [
    response?.content?.video_url,
    response?.data?.content?.video_url,
    response?.output?.video_url,
    response?.data?.output?.video_url,
    response?.content?.file_url,
    response?.data?.content?.file_url,
    Array.isArray(response?.output?.urls) ? response.output.urls[0] : null,
    Array.isArray(response?.data?.output?.urls) ? response.data.output.urls[0] : null
  ];
  return candidates.map((item) => (typeof item === 'string' ? item.trim() : '')).find(Boolean) || null;
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const downloadVideo = async (url, outputPath) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Video download failed: HTTP ${response.status}`);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  const buffer = Buffer.from(await response.arrayBuffer());
  fs.writeFileSync(outputPath, buffer);
  return { path: outputPath, bytes: buffer.length };
};

const runTask = async (task, apiKey, outputDir, previousResult = null) => {
  const body = materializeTaskBody(task, previousResult);
  const created = await seedanceRequest('/contents/generations/tasks', 'POST', apiKey, body);
  const taskId = taskIdFrom(created);
  if (!taskId) throw new Error('Seedance API did not return a task id.');
  const pollInterval = positiveIntegerEnv('SEEDANCE_VIDEO_POLL_INTERVAL_MS', 10000);
  const maxPolls = positiveIntegerEnv('SEEDANCE_VIDEO_MAX_POLLS', 180);
  let latest = created;
  let status = statusFrom(latest);
  for (let attempt = 0; attempt <= maxPolls; attempt += 1) {
    if (['succeeded', 'success', 'completed', 'done'].includes(status)) {
      const url = videoUrlFrom(latest);
      if (!url) throw new Error(`Seedance task ${taskId} succeeded without a video URL.`);
      const safeId = task.localShotId.replace(/[^A-Za-z0-9_.-]/g, '_');
      const downloaded = await downloadVideo(url, path.join(outputDir, `${safeId}.mp4`));
      return { ...task, body, providerTaskId: taskId, status, videoUrl: url, downloaded };
    }
    if (['failed', 'failure', 'error', 'cancelled', 'canceled', 'expired'].includes(status)) {
      throw new Error(`Seedance task ${taskId} failed: ${JSON.stringify(latest)}`);
    }
    await sleep(pollInterval);
    latest = await seedanceRequest(`/contents/generations/tasks/${encodeURIComponent(taskId)}`, 'GET', apiKey);
    status = statusFrom(latest);
  }
  throw new Error(`Seedance polling timed out: ${taskId}`);
};

const main = async () => {
  const credential = dryRun ? null : prepareSeedanceCredential();
  const credentialPreflight = dryRun
    ? null
    : await checkSeedanceConnectivity({
        credential,
        timeoutMs: positiveIntegerEnv('SEEDANCE_VIDEO_REQUEST_TIMEOUT_MS', 30000)
      });
  if (credentialPreflight && !credentialPreflight.ok) {
    throw new Error(
      `Seedance credential preflight failed with HTTP ${credentialPreflight.httpStatus}; ` +
      'no paid task was created.'
    );
  }
  const plan = readJson(planPath);
  const tasks = buildTaskPayloads(plan);
  const apiKey = credential?.apiKey || null;
  if (!dryRun && tasks.some((task) => task.estimatedCostCny === null)) {
    throw new Error('Real generation requires pricing.estimatedCnyPerSecond or estimatedCostCny on every shot so the confirmed cost is explicit.');
  }
  const outputDir = argValue('--output-dir', process.env.SEEDANCE_VIDEO_OUTPUT_DIR || 'outputs/seedance-video');

  const manifest = {
    schema: 'interior.design-video-generation.v3',
    generatedAt: new Date().toISOString(),
    mode: dryRun ? 'dry-run' : 'execute',
    sourcePlanPath: planPath,
    provider: 'seedance',
    apiKey: dryRun ? 'not-required-in-dry-run' : credential.source,
    credentialPreflight,
    endpointBase: endpointBase(),
    outputDir,
    taskCount: tasks.length,
    generationPolicy: {
      serialOnly: true,
      sequentialExtension: true,
      noBatchSubmit: true,
      maxSingleVideoSeconds: 15,
      retryRequiresUserConfirmation: true,
      firstShotUsesGlobalReferenceVideos: true,
      laterShotsUsePreviousProviderVideoOnly: true,
      selectedShotIds: tasks.map((task) => task.localShotId),
      costEstimateComplete: tasks.every((task) => task.estimatedCostCny !== null),
      estimatedCostCny: tasks.every((task) => task.estimatedCostCny !== null)
        ? Number(tasks.reduce((sum, task) => sum + task.estimatedCostCny, 0).toFixed(2))
        : null
    },
    tasks: dryRun
      ? tasks.map((task) => ({
          localShotId: task.localShotId,
          title: task.title,
          endpoint: task.endpoint,
          virtualHuman: task.virtualHuman,
          extensionMode: task.extensionMode,
          dependsOnPreviousShotId: task.dependsOnPreviousShotId,
          referenceVideoUrls: task.referenceVideoUrls,
          continuityReferenceVideoUrl: task.continuityReferenceVideoUrl,
          storyboardImageUrl: task.storyboardImageUrl,
          estimatedCostCny: task.estimatedCostCny,
          body: task.body
        }))
      : []
  };

  if (!dryRun) {
    manifest.tasks = [];
    let previousResult = null;
    for (const task of tasks) {
      try {
        const result = await runTask(task, apiKey, outputDir, previousResult);
        previousResult = result;
        manifest.tasks.push({ ...result, estimatedCostCny: task.estimatedCostCny });
        fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
        fs.writeFileSync(outPath, JSON.stringify(manifest, null, 2));
      } catch (error) {
        manifest.ok = false;
        manifest.failedAt = new Date().toISOString();
        manifest.error = error.message;
        manifest.tasks.push({
          localShotId: task.localShotId,
          title: task.title,
          status: 'failed',
          estimatedCostCny: task.estimatedCostCny,
          error: error.message
        });
        fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
        fs.writeFileSync(outPath, JSON.stringify(manifest, null, 2));
        throw error;
      }
    }
  }

  fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(manifest, null, 2));
  console.log(JSON.stringify({
    ok: true,
    mode: manifest.mode,
    out: outPath,
    taskCount: manifest.taskCount,
    provider: manifest.provider,
    endpointBase: manifest.endpointBase,
    apiKeyLoaded: !dryRun
  }, null, 2));
};

main().catch((error) => {
  try {
    if (outPath) {
      const failure = {
        schema: 'interior.design-video-generation-error.v1',
        generatedAt: new Date().toISOString(),
        mode: dryRun ? 'dry-run' : 'execute',
        sourcePlanPath: planPath,
        ok: false,
        error: error.message
      };
      if (!fs.existsSync(outPath)) {
        fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
        fs.writeFileSync(outPath, JSON.stringify(failure, null, 2));
      }
    }
  } catch {}
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
