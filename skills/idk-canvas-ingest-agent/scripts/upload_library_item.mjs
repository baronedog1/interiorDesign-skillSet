#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { idkRequest } from './idk-env.mjs';

const args = process.argv.slice(2);

const readArg = (name, fallback = undefined) => {
  const index = args.indexOf(name);
  if (index === -1) return fallback;
  const value = args[index + 1];
  return value && !value.startsWith('--') ? value : fallback;
};

const readRepeated = (name) => {
  const values = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] !== name) continue;
    const value = args[index + 1];
    if (value && !value.startsWith('--')) values.push(value);
  }
  return values;
};

const hasFlag = (name) => args.includes(name);

const inferMimeType = (filePath) => {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.webp') return 'image/webp';
  if (ext === '.gif') return 'image/gif';
  return 'application/octet-stream';
};

const sha256File = (filePath) => crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');

const libraryId = readArg('--library');
const name = readArg('--name');
const description = readArg('--description');
const prompt = readArg('--prompt');
const metadataFile = readArg('--metadata-file');
const imageFile = readArg('--image-file');
const imageRole = readArg('--image-role', 'main');
const slotUsageRaw = readArg('--slot-usage');
const tags = readRepeated('--tag');
const dryRun = hasFlag('--dry-run');

if (!libraryId || !name) {
  console.error('Usage: node scripts/upload_library_item.mjs --library <libraryId> --name <name> [--image-file file] [--metadata-file json] [--tag tag] [--dry-run]');
  process.exit(2);
}

let metadata;
if (metadataFile) {
  metadata = JSON.parse(fs.readFileSync(metadataFile, 'utf8'));
}

const body = {
  name,
  ...(description ? { description } : {}),
  ...(prompt ? { prompt } : {}),
  ...(tags.length ? { tags } : {}),
  ...(metadata ? { metadata } : {}),
  ...(slotUsageRaw ? { slotUsage: Number.parseInt(slotUsageRaw, 10) } : {}),
};

let fileHash = 'no-file';
if (imageFile) {
  const absolute = path.resolve(imageFile);
  const mimeType = inferMimeType(absolute);
  fileHash = sha256File(absolute);
  const image = {
    base64: fs.readFileSync(absolute).toString('base64'),
    mimeType,
    fileName: path.basename(absolute),
  };
  body.image = image;
  body.images = [{ role: imageRole, image }];
}

const operationKey = readArg('--operation-key', `library:${libraryId}:${name}:${fileHash}`);
body.operationKey = operationKey;

if (dryRun) {
  const redacted = JSON.parse(JSON.stringify(body));
  if (redacted.image?.base64) redacted.image.base64 = `<base64:${redacted.image.base64.length}>`;
  if (Array.isArray(redacted.images)) {
    for (const entry of redacted.images) {
      if (entry.image?.base64) entry.image.base64 = `<base64:${entry.image.base64.length}>`;
    }
  }
  console.log(JSON.stringify({ dryRun: true, libraryId, payload: redacted }, null, 2));
  process.exit(0);
}

const payload = await idkRequest({ method: 'POST', path: `/library/${libraryId}/items`, body });
console.log(JSON.stringify(payload, null, 2));
