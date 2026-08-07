#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { idkRequest, readConfig } from './idk-env.mjs';

const args = process.argv.slice(2);
const value = (name) => {
  const index = args.indexOf(`--${name}`);
  if (index < 0) return null;
  const result = args[index + 1];
  return result && !result.startsWith('--') ? result : null;
};
const flag = (name) => args.includes(`--${name}`);
const fail = (message) => {
  throw new Error(message);
};

const usage = [
  'Usage:',
  '  node scripts/publish_project_artifact.mjs',
  '    --file <accepted-file>',
  '    --asset-kind <kind>',
  '    --external-tool <skill-id>',
  '    [--project-name <name> | --project-id <uuid>]',
  '    [--binding-file <project>/baiende-project.json]',
  '    [--folder-id <folder>] [--caption <text>] [--title <text>]',
  '    [--external-run-id <run>] [--room-name <room>]',
  '    [--manifest-file <json>] [--source-project-asset-id <uuid>]',
  '    [--source-node-id <id>] [--receipt <json>] [--dry-run]',
].join('\n');

if (flag('help')) {
  process.stdout.write(`${usage}\n`);
  process.exit(0);
}

const inputFile = value('file');
const assetKind = value('asset-kind');
const externalTool = value('external-tool');
const projectName = value('project-name');
const explicitProjectId = value('project-id');
const bindingFile = path.resolve(value('binding-file') || 'baiende-project.json');
const receiptFile = value('receipt') ? path.resolve(value('receipt')) : null;
const dryRun = flag('dry-run');

if (!inputFile || !assetKind || !externalTool) fail(usage);

const absoluteFile = path.resolve(inputFile);
if (!fs.existsSync(absoluteFile) || !fs.statSync(absoluteFile).isFile()) {
  fail(`Accepted artifact not found: ${absoluteFile}`);
}

const mimeTypes = new Map([
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.webp', 'image/webp'],
  ['.mp4', 'video/mp4'],
  ['.webm', 'video/webm'],
  ['.mov', 'video/quicktime'],
  ['.html', 'text/html'],
  ['.htm', 'text/html'],
]);
const extension = path.extname(absoluteFile).toLowerCase();
const mimeType = mimeTypes.get(extension);
if (!mimeType) {
  fail('Project assets support PNG/JPEG/WEBP/MP4/WEBM/MOV, while standalone HTML must use asset-kind=preview3d_html');
}
const assetKinds = new Map([
  ['floorplan_source', 'image'],
  ['layout_plan', 'image'],
  ['layout_annotation', 'image'],
  ['camera_shot', 'image'],
  ['render_image', 'image'],
  ['product_reference', 'image'],
  ['component_preview', 'image'],
  ['booklet_preview', 'image'],
  ['storyboard_image', 'image'],
  ['design_video', 'video'],
  ['preview3d_html', 'html'],
]);
const sourceSkills = new Set([
  'interior-floorplan-planning',
  'interior-html-modeling',
  'interior-camera-capture',
  'interior-space-rendering',
  'movable-furniture-modeling',
  'booklet-production',
  'interior-design-video-production',
]);
if (!sourceSkills.has(externalTool)) {
  fail(`Unsupported external-tool: ${externalTool}`);
}
const expectedMedia = assetKinds.get(assetKind);
if (!expectedMedia) {
  fail(`Unsupported project asset kind: ${assetKind}`);
}
const actualMedia = mimeType === 'text/html'
  ? 'html'
  : mimeType.startsWith('image/')
    ? 'image'
    : 'video';
if (actualMedia !== expectedMedia) {
  fail(`asset-kind=${assetKind} requires ${expectedMedia}, but ${extension} is ${actualMedia}`);
}

const bytes = fs.readFileSync(absoluteFile);
const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
const artifactName = value('name') || path.basename(absoluteFile);
const roomName = value('room-name');
const defaultFolders = new Map([
  ['floorplan_source', 'plan'],
  ['layout_plan', 'plan'],
  ['layout_annotation', 'plan'],
  ['camera_shot', 'shots'],
  ['render_image', roomName || 'renders'],
  ['product_reference', 'products'],
  ['component_preview', 'products'],
  ['booklet_preview', 'booklet'],
  ['storyboard_image', 'storyboard'],
  ['design_video', 'video'],
  ['preview3d_html', '3d'],
]);
const folderId = value('folder-id') || defaultFolders.get(assetKind);
const externalRunId = value('external-run-id') || sha256.slice(0, 20);
const caption = value('caption');
const title = value('title') || artifactName.replace(/\.[^.]+$/, '');
const manifestFile = value('manifest-file');
const sourceProjectAssetId = value('source-project-asset-id');
const sourceNodeId = value('source-node-id');
const artifactBindingKey = `${folderId}/${artifactName}`;

let manifest;
if (manifestFile) {
  const absoluteManifest = path.resolve(manifestFile);
  if (!fs.existsSync(absoluteManifest)) fail(`Manifest not found: ${absoluteManifest}`);
  manifest = JSON.parse(fs.readFileSync(absoluteManifest, 'utf8'));
}

const readBinding = () => {
  if (!fs.existsSync(bindingFile)) return null;
  const binding = JSON.parse(fs.readFileSync(bindingFile, 'utf8'));
  if (binding?.schema !== 'baiende.project-binding.v1' || !binding?.projectId) {
    fail(`Invalid Baiende project binding: ${bindingFile}`);
  }
  return binding;
};

const initialBinding = readBinding();
if (explicitProjectId && initialBinding && explicitProjectId !== initialBinding.projectId) {
  fail('--project-id conflicts with the existing baiende-project.json binding');
}
if (projectName && initialBinding?.projectName && projectName !== initialBinding.projectName) {
  fail('--project-name conflicts with the existing baiende-project.json binding');
}
if (!explicitProjectId && !initialBinding && !projectName) {
  fail('First publication requires --project-name or --project-id; later publications reuse baiende-project.json');
}

const projectUrl = (projectId) => (
  String(projectId).startsWith('<')
    ? '<available-after-project-create>'
    : `https://www.baiende.com/projects/${encodeURIComponent(projectId)}`
);
const projectsFrom = (payload) => (
  Array.isArray(payload) ? payload
    : Array.isArray(payload?.projects) ? payload.projects
      : Array.isArray(payload?.data?.projects) ? payload.data.projects
        : []
);
const projectFrom = (payload) => payload?.project || payload?.data?.project || payload;
const projectIdFrom = (payload) => {
  const project = projectFrom(payload);
  return project?.id || payload?.projectId || payload?.data?.projectId || null;
};
const projectLabel = (project) => String(project?.title || project?.name || '').trim();
const assetsFrom = (payload) => (
  Array.isArray(payload) ? payload
    : Array.isArray(payload?.assets) ? payload.assets
      : Array.isArray(payload?.data?.assets) ? payload.data.assets
        : []
);

const resolveProject = async () => {
  if (dryRun) {
    const projectId = explicitProjectId || initialBinding?.projectId || '<created-project-id>';
    return {
      projectId,
      projectName: projectName || initialBinding?.projectName || '<new-project>',
      created: !explicitProjectId && !initialBinding,
      project: null,
    };
  }

  await idkRequest({ method: 'GET', path: '/auth/profile' });

  const boundProjectId = explicitProjectId || initialBinding?.projectId;
  if (boundProjectId) {
    const listed = projectsFrom(await idkRequest({ method: 'GET', path: '/projects' }));
    const matches = listed.filter((project) => project?.id === boundProjectId);
    if (matches.length !== 1) {
      fail(`Bound project ${boundProjectId} is not uniquely visible to the managed platform account`);
    }
    const project = matches[0];
    return {
      projectId: boundProjectId,
      projectName: projectLabel(project) || projectName || initialBinding?.projectName,
      created: false,
      project,
    };
  }

  const listed = projectsFrom(await idkRequest({ method: 'GET', path: '/projects' }));
  const exact = listed.filter((project) => projectLabel(project) === projectName);
  if (exact.length > 1) {
    fail(`More than one project is named "${projectName}"; rerun with --project-id`);
  }
  if (exact.length === 1) {
    return {
      projectId: exact[0].id,
      projectName,
      created: false,
      project: exact[0],
    };
  }

  const createOperationKey = `project:${externalTool}:${crypto
    .createHash('sha256')
    .update(projectName)
    .digest('hex')
    .slice(0, 24)}`;
  const createdPayload = await idkRequest({
    method: 'POST',
    path: '/projects',
    body: {
      operationKey: createOperationKey,
      title: projectName,
      name: projectName,
      stage: '设计方案',
      requirements: '接收已验收的外部室内设计产物。',
      sourceType: 'external_upload',
      externalTool,
      externalRunId,
    },
  });
  const createdProjectId = projectIdFrom(createdPayload);
  if (!createdProjectId) fail('Project creation response did not contain a project id');
  return {
    projectId: createdProjectId,
    projectName,
    created: true,
    project: projectFrom(createdPayload),
  };
};

const ensureStandaloneHtml = (html) => {
  if (!/<html[\s>]/i.test(html) || !/<\/html>/i.test(html)) {
    fail('preview3d_html must be a complete HTML document');
  }
  const forbidden = [
    ['file URL', /file:\/\//i],
    ['localhost dependency', /https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?/i],
    ['absolute local path', /(?:src|href)=["']\/home\//i],
    ['relative script dependency', /<script[^>]+src=["'](?!https?:|data:|blob:)[^"']+/i],
    ['relative stylesheet dependency', /<link[^>]+href=["'](?!https?:|data:)[^"']+/i],
  ];
  for (const [label, pattern] of forbidden) {
    if (pattern.test(html)) fail(`Standalone HTML rejected: ${label}`);
  }
};

const writeBinding = (resolvedProject, publication) => {
  const config = readConfig();
  const artifacts = { ...(initialBinding?.artifacts || {}) };
  if (publication?.assetId) {
    artifacts[artifactBindingKey] = {
      assetId: publication.assetId,
      assetKind,
      folderId,
      name: artifactName,
      mimeType,
      sha256,
      bytes: bytes.length,
      externalTool,
      externalRunId,
      publishedAt: publication.skipped
        ? artifacts[artifactBindingKey]?.publishedAt || null
        : new Date().toISOString(),
    };
  }
  const binding = {
    schema: 'baiende.project-binding.v1',
    projectId: resolvedProject.projectId,
    projectName: resolvedProject.projectName,
    projectUrl: projectUrl(resolvedProject.projectId),
    apiBaseUrl: config.apiBaseUrl,
    artifacts,
    boundAt: new Date().toISOString(),
  };
  fs.mkdirSync(path.dirname(bindingFile), { recursive: true });
  fs.writeFileSync(bindingFile, `${JSON.stringify(binding, null, 2)}\n`, { mode: 0o600 });
  return binding;
};

const recordedPublication = async (projectId) => {
  const recorded = initialBinding?.artifacts?.[artifactBindingKey];
  if (!recorded) return null;
  if (recorded.sha256 !== sha256) {
    fail(`Project binding collision at ${artifactBindingKey}; use a versioned --name for changed content`);
  }
  const remote = assetsFrom(await idkRequest({
    method: 'GET',
    path: `/projects/${encodeURIComponent(projectId)}/assets`,
  })).find((asset) => asset?.id === recorded.assetId);
  if (!remote) {
    fail(`Bound project asset ${recorded.assetId} is missing; reconcile the project before publishing again`);
  }
  return {
    endpoint: assetKind === 'preview3d_html'
      ? `/projects/${projectId}/preview3d`
      : `/projects/${projectId}/assets`,
    operationKey: null,
    skipped: true,
    reason: 'same project binding key and SHA-256 already published',
    assetId: recorded.assetId,
  };
};

const publishPreview = async (projectId) => {
  if (!dryRun) {
    const recorded = await recordedPublication(projectId);
    if (recorded) return recorded;
  }
  const html = bytes.toString('utf8');
  ensureStandaloneHtml(html);
  const operationKey = value('operation-key') || `preview3d:${projectId}:${externalTool}:${sha256}`;
  const payload = {
    operationKey,
    name: artifactName,
    title,
    html,
    folderId,
    externalTool,
    externalRunId,
    roomName: roomName || undefined,
    caption: caption || undefined,
    sourceProjectAssetId: sourceProjectAssetId || undefined,
    sourceNodeId: sourceNodeId || undefined,
    manifest,
    manifestName: manifestFile ? path.basename(manifestFile) : undefined,
  };
  if (dryRun) {
    return {
      endpoint: `/projects/${projectId}/preview3d`,
      operationKey,
      htmlBytes: bytes.length,
      payload: { ...payload, html: `<html:${bytes.length} bytes>` },
    };
  }
  const response = await idkRequest({
    method: 'POST',
    path: `/projects/${encodeURIComponent(projectId)}/preview3d`,
    body: payload,
  });
  const htmlAsset = response?.preview3d?.htmlAsset || response?.data?.preview3d?.htmlAsset;
  return {
    endpoint: `/projects/${projectId}/preview3d`,
    operationKey,
    assetId: htmlAsset?.id || response?.asset?.id || null,
    nodeId: response?.preview3d?.node?.id || response?.data?.preview3d?.node?.id || null,
    response,
  };
};

const publishMedia = async (projectId) => {
  if (!dryRun) {
    const recorded = await recordedPublication(projectId);
    if (recorded) return recorded;
  }
  const operationKey = value('operation-key') || `project-asset:${projectId}:${folderId}:${artifactName}:${sha256}`;
  const source = {
    externalTool,
    externalRunId,
    assetKind,
    origin: 'uploaded',
    sourceType: 'external_upload',
    roomName: roomName || undefined,
    caption: caption || undefined,
    sourceProjectAssetId: sourceProjectAssetId || undefined,
    sourceNodeId: sourceNodeId || undefined,
  };
  const uploadPayload = {
    operationKey,
    folderId,
    ...source,
    materials: [{
      folderId,
      name: artifactName,
      mimeType,
      base64: bytes.toString('base64'),
      ...source,
    }],
  };

  if (dryRun) {
    return {
      endpoint: `/projects/${projectId}/assets`,
      operationKey,
      upload: {
        ...uploadPayload,
        materials: [{ ...uploadPayload.materials[0], base64: `<base64:${uploadPayload.materials[0].base64.length}>` }],
      },
    };
  }

  const existing = assetsFrom(await idkRequest({
    method: 'GET',
    path: `/projects/${encodeURIComponent(projectId)}/assets`,
  })).find((asset) => (
    String(asset?.folderId || '').toLowerCase() === folderId.toLowerCase()
    && String(asset?.name || '').toLowerCase() === artifactName.toLowerCase()
  ));
  if (existing) {
    fail(`Unbound project asset already exists at ${artifactBindingKey}; reconcile it before publishing`);
  }

  const uploaded = await idkRequest({
    method: 'POST',
    path: `/projects/${encodeURIComponent(projectId)}/assets`,
    body: uploadPayload,
  });
  const asset = assetsFrom(uploaded)[0];
  if (!asset?.id) fail('Project asset upload response did not contain an asset id');

  return {
    endpoint: `/projects/${projectId}/assets`,
    operationKey,
    assetId: asset.id,
    uploaded,
  };
};

const resolvedProject = await resolveProject();
const publication = assetKind === 'preview3d_html'
  ? await publishPreview(resolvedProject.projectId)
  : await publishMedia(resolvedProject.projectId);

if (!dryRun) {
  const verifiedAssets = assetsFrom(await idkRequest({
    method: 'GET',
    path: `/projects/${encodeURIComponent(resolvedProject.projectId)}/assets`,
  }));
  if (publication.assetId && !verifiedAssets.some((asset) => asset?.id === publication.assetId)) {
    fail(`Published asset ${publication.assetId} was not found during read-back verification`);
  }
}

const binding = dryRun
  ? {
      schema: 'baiende.project-binding.v1',
      projectId: resolvedProject.projectId,
      projectName: resolvedProject.projectName,
      projectUrl: projectUrl(resolvedProject.projectId),
      bindingFile,
    }
  : writeBinding(resolvedProject, publication);

const receipt = {
  schema: 'baiende.project-publication-receipt.v1',
  dryRun,
  project: {
    id: resolvedProject.projectId,
    name: resolvedProject.projectName,
    url: projectUrl(resolvedProject.projectId),
    created: resolvedProject.created,
    bindingFile,
  },
  artifact: {
    file: absoluteFile,
    name: artifactName,
    mimeType,
    assetKind,
    folderId,
    sha256,
    bytes: bytes.length,
    externalTool,
    externalRunId,
  },
  publication,
  publishedAt: dryRun ? null : new Date().toISOString(),
};

if (receiptFile) {
  fs.mkdirSync(path.dirname(receiptFile), { recursive: true });
  fs.writeFileSync(receiptFile, `${JSON.stringify(receipt, null, 2)}\n`);
}
process.stdout.write(`${JSON.stringify({ ...receipt, binding }, null, 2)}\n`);
