import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const parseEnvLine = (line) => {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('#')) return null;
  const index = trimmed.indexOf('=');
  if (index < 1) return null;
  const key = trimmed.slice(0, index).trim();
  let value = trimmed.slice(index + 1).trim();
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1);
  }
  return { key, value };
};

const loadEnvFile = (filePath) => {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Managed Baiende credential file not found: ${filePath}`);
  }
  const content = fs.readFileSync(filePath, 'utf8');
  for (const line of content.split(/\r?\n/)) {
    const parsed = parseEnvLine(line);
    if (!parsed) continue;
    if (process.env[parsed.key] === undefined) {
      process.env[parsed.key] = parsed.value;
    }
  }
};

export const loadIdkEnv = () => {
  const managedEnvFile = process.env.IDK_ENV_FILE
    ? path.resolve(process.env.IDK_ENV_FILE)
    : path.join(os.homedir(), 'agent-runtime', 'secrets', 'baiende-platform.env');
  loadEnvFile(managedEnvFile);
  return managedEnvFile;
};

export const normalizeApiBaseUrl = (rawValue) => {
  const value = (rawValue || 'https://www.baiende.com/api/v1').trim();
  if (!value) return 'https://www.baiende.com/api/v1';

  const url = new URL(value);
  url.hash = '';
  url.search = '';

  const pathname = url.pathname.replace(/\/+$/, '') || '/';
  if (pathname === '/' || pathname === '/api') {
    url.pathname = '/api/v1';
  } else if (pathname === '/api/v1') {
    url.pathname = pathname;
  } else {
    throw new Error(`IDK_API_BASE_URL must end at /api/v1, received path: ${pathname}`);
  }

  return url.toString().replace(/\/+$/, '');
};

export const readConfig = () => {
  const managedEnvFile = loadIdkEnv();
  const apiBaseUrl = normalizeApiBaseUrl(process.env.IDK_API_BASE_URL);
  const apiKey = (process.env.IDK_API_KEY || '').trim();
  const toolName = (process.env.IDK_TOOL_NAME || 'idk-canvas-ingest-agent').trim() || 'idk-canvas-ingest-agent';
  const timeoutMs = Number.parseInt(process.env.IDK_REQUEST_TIMEOUT_MS || '600000', 10);
  const allowLocalApi = (process.env.IDK_ALLOW_LOCAL_API || 'NO').toUpperCase() === 'YES';

  if (!apiKey) {
    throw new Error(`Missing IDK_API_KEY in managed credential file: ${managedEnvFile}`);
  }

  const parsed = new URL(apiBaseUrl);
  const isHttps = parsed.protocol === 'https:';
  const isLocal =
    parsed.hostname === 'localhost' ||
    parsed.hostname === '127.0.0.1' ||
    parsed.hostname.endsWith('.local') ||
    parsed.hostname.startsWith('100.');

  if (!isHttps && !(allowLocalApi && isLocal)) {
    throw new Error('Refusing non-HTTPS API base. Set IDK_ALLOW_LOCAL_API=YES only for trusted localhost/Tailnet testing.');
  }

  return {
    apiBaseUrl,
    apiKey,
    toolName,
    timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 600000,
    managedEnvFile,
  };
};

export const idempotencyHeader = (operationKey) => (
  `idk-v1-${crypto.createHash('sha256').update(operationKey, 'utf8').digest('hex')}`
);

export const idkRequest = async ({ method = 'GET', path: requestPath, body }) => {
  const config = readConfig();
  const normalizedPath = requestPath.startsWith('/') ? requestPath : `/${requestPath}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.timeoutMs);
  const headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json; charset=utf-8',
    'X-IDK-API-Key': config.apiKey,
    'X-IDK-Tool-Name': config.toolName,
    'User-Agent': 'IDK-Canvas-Ingest-Agent-Skill/2.0.0',
  };
  const operationKey =
    body && typeof body === 'object' && typeof body.operationKey === 'string'
      ? body.operationKey.trim()
      : '';
  if (!['GET', 'HEAD'].includes(method.toUpperCase()) && operationKey) {
    headers['Idempotency-Key'] = idempotencyHeader(operationKey);
  }
  let requestBody = body;
  if (operationKey && body && typeof body === 'object' && !Array.isArray(body)) {
    requestBody = { ...body };
    delete requestBody.operationKey;
  }

  try {
    const response = await fetch(`${config.apiBaseUrl}${normalizedPath}`, {
      method,
      headers,
      body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
      signal: controller.signal,
    });
    const text = await response.text();
    let payload = text;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = text;
    }
    if (!response.ok) {
      const message = typeof payload === 'string' ? payload.slice(0, 300) : JSON.stringify(payload).slice(0, 300);
      throw new Error(`${method} ${normalizedPath} failed: HTTP ${response.status} ${message}`);
    }
    return payload;
  } finally {
    clearTimeout(timer);
  }
};
