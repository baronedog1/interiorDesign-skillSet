#!/usr/bin/env node
import { idkRequest } from './idk-env.mjs';

const args = process.argv.slice(2);

const readArg = (name, fallback = undefined) => {
  const index = args.indexOf(name);
  if (index === -1) return fallback;
  const value = args[index + 1];
  return value && !value.startsWith('--') ? value : fallback;
};

const hasFlag = (name) => args.includes(name);

const libraryId = readArg('--library');
const scope = readArg('--scope', 'all');
const type = readArg('--type');
const limitRaw = readArg('--limit', '8');
const limit = Math.max(1, Number.parseInt(limitRaw, 10) || 8);
const outputRaw = hasFlag('--json');
const summaryOnly = hasFlag('--summary') || !libraryId;

const query = new URLSearchParams();
if (scope) query.set('scope', scope);
if (type) query.set('type', type);

if (summaryOnly) {
  const payload = await idkRequest({ method: 'GET', path: `/library/summary?${query.toString()}` });
  if (outputRaw) {
    console.log(JSON.stringify(payload, null, 2));
  } else {
    const categories = Array.isArray(payload?.categories) ? payload.categories : [];
    console.log(JSON.stringify({
      categories: categories.map((category) => ({
        id: category.id,
        label: category.label,
        count: category.count,
        myCount: category.myCount,
        canUpload: category.id !== 'marketing_material',
      })),
    }, null, 2));
  }
  process.exit(0);
}

const payload = await idkRequest({ method: 'GET', path: `/library/${libraryId}/items?${query.toString()}` });
if (outputRaw) {
  console.log(JSON.stringify(payload, null, 2));
  process.exit(0);
}

const items = Array.isArray(payload?.items) ? payload.items.slice(0, limit) : [];
const simplified = items.map((item) => ({
  id: item.id,
  name: item.name,
  description: item.description ?? null,
  tags: item.tags ?? [],
  metadata: item.metadata ?? null,
  previewPath: item.previewPath ?? item.previewStoragePath ?? null,
  sourcePath: item.sourcePath ?? item.sourceStoragePath ?? null,
  slotUsage: item.slotUsage ?? null,
  visibility: item.visibility ?? null,
  inMyAssets: item.inMyAssets ?? null,
  isFavorite: item.isFavorite ?? null,
  canManage: item.canManage ?? null,
}));
console.log(JSON.stringify({ libraryId: payload?.libraryId ?? libraryId, scope, type: type ?? null, count: simplified.length, items: simplified }, null, 2));
