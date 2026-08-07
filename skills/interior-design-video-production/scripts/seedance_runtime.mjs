import fs from 'fs';

export const DEFAULT_SEEDANCE_SECRET_FILE =
  '/home/agentops/agent-runtime/secrets/interior-design-video-production.env';

const KEY_ALIASES = [
  'VOLCENGINE_ARK_API_KEY',
  'ARK_API_KEY',
  'SEEDANCE_API_KEY'
];

const parseDotEnv = (content) => {
  const values = {};
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) continue;
    const [, key, rawValue] = match;
    values[key] = rawValue.replace(/^['"]|['"]$/g, '');
  }
  return values;
};

const findApiKey = (env) => {
  for (const alias of KEY_ALIASES) {
    const value = String(env[alias] || '').trim();
    if (value && value !== 'placeholder_api_key') {
      return { value, alias };
    }
  }
  return null;
};

export const prepareSeedanceCredential = ({
  env = process.env,
  secretFile = String(env.SEEDANCE_VIDEO_SECRET_FILE || '').trim() || DEFAULT_SEEDANCE_SECRET_FILE
} = {}) => {
  const injected = findApiKey(env);
  if (injected) {
    env.VOLCENGINE_ARK_API_KEY = injected.value;
    return {
      apiKey: injected.value,
      source: `process-env:${injected.alias}`,
      secretFile: null
    };
  }

  if (!fs.existsSync(secretFile)) {
    throw new Error(
      `Seedance managed secret is missing: ${secretFile}. ` +
      'Provision the device secret before real generation.'
    );
  }

  const stat = fs.lstatSync(secretFile);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error(`Seedance managed secret must be a regular file: ${secretFile}`);
  }
  if ((stat.mode & 0o077) !== 0) {
    throw new Error(`Seedance managed secret must use mode 0600: ${secretFile}`);
  }
  if (typeof process.getuid === 'function' && stat.uid !== process.getuid()) {
    throw new Error(`Seedance managed secret must be owned by the current runtime user: ${secretFile}`);
  }

  const values = parseDotEnv(fs.readFileSync(secretFile, 'utf8'));
  for (const [key, value] of Object.entries(values)) {
    if (env[key] === undefined) env[key] = value;
  }
  const managed = findApiKey(env);
  if (!managed) {
    throw new Error(
      `Seedance managed secret does not contain one of ${KEY_ALIASES.join(', ')}: ${secretFile}`
    );
  }
  env.VOLCENGINE_ARK_API_KEY = managed.value;
  return {
    apiKey: managed.value,
    source: `managed-secret:${managed.alias}`,
    secretFile
  };
};

export const seedanceEndpointBase = (env = process.env) => {
  const raw = String(
    env.SEEDANCE_VIDEO_API_BASE_URL || 'https://ark.cn-beijing.volces.com/api/v3'
  ).trim();
  if (!/^https:\/\/[A-Za-z0-9.-]+(\/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?$/.test(raw)) {
    throw new Error('SEEDANCE_VIDEO_API_BASE_URL must be an https URL.');
  }
  return raw.replace(/\/+$/, '');
};

const providerErrorCode = (json) => String(
  json?.error?.code || json?.code || json?.error_code || json?.data?.error_code || ''
).trim() || null;

export const checkSeedanceConnectivity = async ({
  credential,
  env = process.env,
  timeoutMs = 15000
}) => {
  if (!credential?.apiKey) {
    throw new Error('Seedance connectivity check requires a prepared credential.');
  }
  const endpointBase = seedanceEndpointBase(env);
  const probeId = `codex-auth-probe-${Date.now()}-not-a-real-task`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  let json = {};
  try {
    response = await fetch(
      `${endpointBase}/contents/generations/tasks/${encodeURIComponent(probeId)}`,
      {
        method: 'GET',
        headers: { Authorization: `Bearer ${credential.apiKey}` },
        signal: controller.signal
      }
    );
    const body = await response.text();
    if (body) {
      try { json = JSON.parse(body); } catch { json = {}; }
    }
  } finally {
    clearTimeout(timer);
  }

  const authRejected = response.status === 401 || response.status === 403;
  const expectedProbeResponse =
    (response.status >= 200 && response.status < 300) ||
    [400, 404, 422].includes(response.status);
  const ok = expectedProbeResponse && !authRejected;
  return {
    schema: 'interior.seedance-connectivity-check.v1',
    checkedAt: new Date().toISOString(),
    ok,
    status: ok ? 'reachable_auth_ok_no_task_created' : 'authentication_or_connectivity_failed',
    endpointBase,
    method: 'GET',
    httpStatus: response.status,
    providerErrorCode: providerErrorCode(json),
    credentialSource: credential.source,
    createdTask: false,
    costIncurringRequest: false
  };
};
