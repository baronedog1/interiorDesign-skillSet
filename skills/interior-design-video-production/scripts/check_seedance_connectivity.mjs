#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import {
  checkSeedanceConnectivity,
  prepareSeedanceCredential,
} from './seedance_runtime.mjs';

const args = process.argv.slice(2);
const argValue = (name, defaultValue = null) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : defaultValue;
};

const outPath = argValue('--out');
const secretFile = argValue('--secret-file') || undefined;
const timeoutMs = Number(argValue('--timeout-ms', '15000'));
if (!Number.isInteger(timeoutMs) || timeoutMs < 1000) {
  console.error(JSON.stringify({ ok: false, error: '--timeout-ms must be an integer >= 1000.' }));
  process.exit(2);
}

const writeResult = (result) => {
  if (outPath) {
    fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
  }
  console.log(JSON.stringify(result, null, 2));
};

const main = async () => {
  const credential = prepareSeedanceCredential({ secretFile });
  const result = await checkSeedanceConnectivity({ credential, timeoutMs });
  writeResult(result);
  if (!result.ok) process.exit(1);
};

main().catch((error) => {
  const result = {
    schema: 'interior.seedance-connectivity-check.v1',
    checkedAt: new Date().toISOString(),
    ok: false,
    status: 'authentication_or_connectivity_failed',
    error: error.name === 'AbortError' ? 'Seedance connectivity check timed out.' : error.message,
    createdTask: false,
    costIncurringRequest: false
  };
  writeResult(result);
  process.exit(1);
});
