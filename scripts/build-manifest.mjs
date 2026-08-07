#!/usr/bin/env node

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const skillsRoot = path.join(repoRoot, 'skills');
const snapshotArg = process.argv.find((arg) => arg.startsWith('--snapshot='));
const snapshotIndex = process.argv.indexOf('--snapshot');
const snapshotAt = snapshotArg
  ? snapshotArg.slice('--snapshot='.length)
  : (snapshotIndex >= 0 && process.argv[snapshotIndex + 1] ? process.argv[snapshotIndex + 1] : new Date().toISOString());

function walkFiles(root) {
  const files = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const absolute = path.join(root, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`symbolic link is not allowed: ${absolute}`);
    if (entry.isDirectory()) files.push(...walkFiles(absolute));
    else if (entry.isFile()) files.push(absolute);
  }
  return files;
}

function sha256File(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function frontmatterValue(text, key) {
  const match = text.match(new RegExp(`^${key}:\\s*["']?([^\\n"']+)["']?\\s*$`, 'm'));
  return match ? match[1].trim() : '';
}

function skillVersion(text) {
  const jsonMetadata = text.match(/^metadata:\s*(\{[^\n]+\})\s*$/m);
  if (jsonMetadata) {
    try {
      const value = JSON.parse(jsonMetadata[1]);
      if (value.version) return String(value.version);
    } catch {
      // Fall through to YAML or body version fields.
    }
  }
  const yamlVersion = text.match(/^\s{2}version:\s*["'`]?([^\n"'`]+)["'`]?\s*$/m);
  if (yamlVersion) return yamlVersion[1].trim();
  const bodyVersion = text.match(/^版本[：:]\s*[`"]?([^\n`"]+)/m);
  return bodyVersion ? bodyVersion[1].trim() : 'unversioned';
}

const skillDirs = fs.readdirSync(skillsRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();
const fileRows = [];
const skills = [];

for (const skillId of skillDirs) {
  const skillRoot = path.join(skillsRoot, skillId);
  const skillEntry = path.join(skillRoot, 'SKILL.md');
  if (!fs.existsSync(skillEntry)) throw new Error(`missing SKILL.md: ${skillId}`);
  const skillText = fs.readFileSync(skillEntry, 'utf8');
  const declaredName = frontmatterValue(skillText, 'name');
  if (!declaredName) throw new Error(`missing name frontmatter: ${skillId}`);
  if (declaredName !== skillId) throw new Error(`skill name/path mismatch: ${skillId} != ${declaredName}`);

  const files = walkFiles(skillRoot);
  let totalBytes = 0;
  const digest = crypto.createHash('sha256');
  for (const absolute of files) {
    const relative = path.relative(repoRoot, absolute).split(path.sep).join('/');
    const stat = fs.statSync(absolute);
    const hash = sha256File(absolute);
    totalBytes += stat.size;
    digest.update(`${hash}  ${relative}\n`);
    fileRows.push(`${hash}  ${relative}`);
  }
  skills.push({
    id: skillId,
    path: `skills/${skillId}`,
    version: skillVersion(skillText),
    fileCount: files.length,
    bytes: totalBytes,
    sha256: digest.digest('hex'),
  });
}

const manifest = {
  schemaVersion: 1,
  snapshotAt,
  source: {
    deviceId: 'ubuntu-01-codex',
    skillRoot: '/home/agentops/.codex/skills',
    excluded: ['credentials', 'auth', 'sessions', 'history', 'tasks', 'logs', 'customer-data', 'node_modules', 'runtime-cache'],
  },
  skillCount: skills.length,
  fileCount: fileRows.length,
  skills,
};

fs.writeFileSync(path.join(repoRoot, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, { mode: 0o644 });
fs.writeFileSync(path.join(repoRoot, 'FILES.sha256'), `${fileRows.join('\n')}\n`, { mode: 0o644 });
