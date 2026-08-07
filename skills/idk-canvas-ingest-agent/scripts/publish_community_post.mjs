#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { idkRequest } from './idk-env.mjs';

const args = process.argv.slice(2);
const usage = 'Usage: node scripts/publish_community_post.mjs <community-publication-spec.json> [--binding-file <baiende-project.json>] [--out result.json] [--dry-run | --execute --confirm-public]';
if (!args.length || args.includes('--help')) {
  process.stdout.write(`${usage}\n`);
  process.exit(args.includes('--help') ? 0 : 2);
}

const argument = (name) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 ? args[index + 1] || null : null;
};
const execute = args.includes('--execute');
const confirmPublic = args.includes('--confirm-public');
const dryRun = args.includes('--dry-run');
if (execute && !confirmPublic) {
  throw new Error('Community publication requires --execute --confirm-public');
}
if (execute && dryRun) {
  throw new Error('--dry-run and --execute are mutually exclusive');
}

const specPath = path.resolve(args[0]);
const specRoot = path.dirname(specPath);
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const allowedSourceSkills = new Set([
  'interior-floorplan-planning',
  'interior-html-modeling',
  'interior-camera-capture',
  'interior-space-rendering',
  'movable-furniture-modeling',
  'booklet-production',
  'interior-design-video-production',
]);
const bindingPath = argument('binding-file')
  ? path.resolve(argument('binding-file'))
  : spec.bindingFile
    ? path.resolve(specRoot, spec.bindingFile)
    : null;
const binding = bindingPath ? JSON.parse(fs.readFileSync(bindingPath, 'utf8')) : null;
const projectId = spec.projectId || binding?.projectId;
if (spec.schema !== 'baiende.community-publication-spec.v1') {
  throw new Error('Community spec must use schema baiende.community-publication-spec.v1');
}
if (!projectId || !spec.title || !spec.htmlPath || !spec.sourceSkill) {
  throw new Error('Community spec requires title, htmlPath, sourceSkill and either projectId or a valid project binding');
}
if (!allowedSourceSkills.has(spec.sourceSkill)) {
  throw new Error(`Unsupported sourceSkill: ${spec.sourceSkill}`);
}

const bannedKeys = ['templateId', 'themeId', 'renderMode', 'templateDraft', 'layoutSnapshot', 'blocks', 'pages'];
const presentBanned = bannedKeys.filter((key) => Object.prototype.hasOwnProperty.call(spec, key));
if (presentBanned.length) {
  throw new Error(`Snapshot spec contains platform-layout fields: ${presentBanned.join(', ')}`);
}

const resolveSpecPath = (filePath) => path.resolve(specRoot, filePath);
const html = fs.readFileSync(resolveSpecPath(spec.htmlPath), 'utf8');
const css = (spec.cssPaths || []).map((cssPath) => ({
  path: cssPath,
  content: fs.readFileSync(resolveSpecPath(cssPath), 'utf8'),
}));
const imageAssetMap = spec.imageAssetMapPath
  ? JSON.parse(fs.readFileSync(resolveSpecPath(spec.imageAssetMapPath), 'utf8'))
  : spec.imageAssetMap;
if (!imageAssetMap || !Object.keys(imageAssetMap).length) {
  throw new Error('Every snapshot image must be mapped to an HTTPS platform/CDN URL');
}
for (const [localRef, publicUrl] of Object.entries(imageAssetMap)) {
  if (typeof publicUrl !== 'string' || !/^https:\/\//i.test(publicUrl)) {
    throw new Error(`imageAssetMap[${localRef}] must be an HTTPS URL`);
  }
}

const payload = {
  projectId,
  title: spec.title,
  summary: spec.summary || '',
  tags: spec.tags || [],
  shareMode: 'html_snapshot',
  html,
  css,
  imageAssetMap,
  coverSourceAssetId: spec.coverSourceAssetId || null,
  sourceReference: spec.sourceReferencePath
    ? JSON.parse(fs.readFileSync(resolveSpecPath(spec.sourceReferencePath), 'utf8'))
    : null,
  metadata: {
    source: spec.sourceSkill,
    sourceRunId: spec.sourceRunId || null,
    projectBindingSchema: binding?.schema || null,
  },
};

const outPath = path.resolve(argument('out') || 'community-publication.json');
if (dryRun) {
  const result = {
    schema: 'baiende.community-publication-receipt.v1',
    mode: 'dry-run',
    projectId,
    sourceSkill: spec.sourceSkill,
    htmlLength: html.length,
    cssFileCount: css.length,
    imageCount: Object.keys(imageAssetMap).length,
    publicConfirmationRequired: true,
    generatedAt: new Date().toISOString(),
  };
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, `${JSON.stringify(result, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({ ok: true, outPath, mode: result.mode }, null, 2)}\n`);
  process.exit(0);
}

const preview = await idkRequest({
  method: 'POST',
  path: '/community/html-snapshots/preview',
  body: {
    operationKey: `community-preview:${projectId}:${crypto.createHash('sha256').update(html).digest('hex')}`,
    ...payload,
  },
});
const result = {
  schema: 'baiende.community-publication-receipt.v1',
  mode: execute ? 'published' : 'preview_only',
  projectId,
  preview: {
    htmlLength: typeof preview?.html === 'string' ? preview.html.length : 0,
    diagnostics: preview?.diagnostics || null,
  },
  communityPostPayload: preview?.communityPostPayload || null,
  generatedAt: new Date().toISOString(),
};

if (execute) {
  if (!preview?.communityPostPayload) {
    throw new Error('Preview response did not contain communityPostPayload');
  }
  const published = await idkRequest({
    method: 'POST',
    path: '/community/posts',
    body: {
      operationKey: `community-publication:${projectId}:${crypto
        .createHash('sha256')
        .update(JSON.stringify(preview.communityPostPayload))
        .digest('hex')}`,
      ...preview.communityPostPayload,
    },
  });
  result.publish = {
    id: published?.id || null,
    sharePath: published?.sharePath || null,
    shareUrl: published?.shareUrl || null,
  };
}

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, `${JSON.stringify(result, null, 2)}\n`);
process.stdout.write(`${JSON.stringify({ ok: true, outPath, mode: result.mode, shareUrl: result.publish?.shareUrl || null }, null, 2)}\n`);
