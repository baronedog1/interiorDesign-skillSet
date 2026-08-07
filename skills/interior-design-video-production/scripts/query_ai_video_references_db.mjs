#!/usr/bin/env node
import { spawnSync } from "node:child_process";

function readArg(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function readRepeated(name) {
  const values = [];
  for (let index = 2; index < process.argv.length; index += 1) {
    if (process.argv[index] === name && process.argv[index + 1]) values.push(process.argv[index + 1]);
  }
  return values;
}

function clampLimit(value) {
  const raw = Number(value || 10);
  return Number.isFinite(raw) ? Math.min(Math.max(Math.trunc(raw), 1), 50) : 10;
}

function dollar(value) {
  const text = String(value ?? "");
  if (text.includes("$q$")) throw new Error("Unsupported value contains reserved dollar quote token");
  return `$q$${text}$q$`;
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

const filters = {
  domain: readArg("--domain") || undefined,
  useCase: readArg("--use-case") || undefined,
  q: readArg("--q") || undefined,
  aspectRatio: readArg("--aspect-ratio") || undefined,
  tags: readRepeated("--tag"),
  limit: clampLimit(readArg("--limit")),
};

const selectedColumns = `reference_key, title, summary, domain, use_case, tags, video_url, poster_url,
       primary_oss_object_key, duration_seconds, aspect_ratio, resolution, fps, model_support,
       prompt_template, storyboard, shot_count, image_count_min, image_count_max, ai_character_policy,
       motion_keywords, style_keywords, reference_notes, quality_score, visibility, metadata, updated_at`;

function runLocalPsqlQuery(dbUrl) {
  const sqlFilters = ["status = $$active$$", "visibility = ANY (ARRAY[$$public$$,$$controlled_external$$,$$internal$$,$$restricted$$])"];
  if (filters.domain) sqlFilters.push(`domain = ${dollar(filters.domain)}`);
  if (filters.useCase) sqlFilters.push(`use_case = ${dollar(filters.useCase)}`);
  if (filters.aspectRatio) sqlFilters.push(`aspect_ratio = ${dollar(filters.aspectRatio)}`);
  for (const tag of filters.tags) sqlFilters.push(`${dollar(tag)} = ANY(tags)`);
  if (filters.q) {
    const pattern = `%${filters.q}%`;
    sqlFilters.push(`(title ILIKE ${dollar(pattern)} OR COALESCE(summary, $$ $$) ILIKE ${dollar(pattern)} OR COALESCE(reference_notes, $$ $$) ILIKE ${dollar(pattern)})`);
  }

  const sql = `
WITH filtered AS (
  SELECT ${selectedColumns}
    FROM data_knowledge.ai_video_references
   WHERE ${sqlFilters.join(" AND ")}
   ORDER BY quality_score DESC, updated_at DESC
   LIMIT ${filters.limit}
)
SELECT COALESCE(json_agg(row_to_json(filtered)), $$[]$$::json) FROM filtered;
`;

  const psql = process.env.AI_NATIVE_PSQL_BIN || "psql";
  const result = spawnSync(psql, ["--dbname", dbUrl, "--tuples-only", "--no-align", "--quiet", "--command", sql], { encoding: "utf8" });
  if (result.error) {
    console.error(JSON.stringify({ ok: false, mode: "local-psql", error: result.error.message, hint: "Install psql or set AI_NATIVE_PSQL_BIN" }, null, 2));
    process.exit(3);
  }
  if (result.status !== 0) {
    console.error(JSON.stringify({ ok: false, mode: "local-psql", error: result.stderr.trim() || "psql query failed" }, null, 2));
    process.exit(result.status || 1);
  }
  return result.stdout.trim() || "[]";
}

const remoteSource = String.raw`
const fs = require("node:fs");
const dotenv = require("dotenv");
const { Pool } = require("pg");

const filters = JSON.parse(Buffer.from(process.env.AI_VIDEO_REF_QUERY_B64 || "e30", "base64url").toString("utf8"));
const parsed = dotenv.parse(fs.readFileSync(".env"));
const params = [];
const where = ["status = 'active'", "visibility = ANY($1::text[])"];
params.push(["public", "controlled_external", "internal", "restricted"]);
const add = (value) => {
  params.push(value);
  return "$" + params.length;
};
if (filters.domain) where.push("domain = " + add(filters.domain));
if (filters.useCase) where.push("use_case = " + add(filters.useCase));
if (filters.aspectRatio) where.push("aspect_ratio = " + add(filters.aspectRatio));
for (const tag of filters.tags || []) where.push(add(tag) + " = ANY(tags)");
if (filters.q) {
  const pattern = "%" + filters.q + "%";
  const token = add(pattern);
  where.push("(title ILIKE " + token + " OR COALESCE(summary, '') ILIKE " + token + " OR COALESCE(reference_notes, '') ILIKE " + token + ")");
}
params.push(Math.min(Math.max(Number.parseInt(String(filters.limit || 10), 10) || 10, 1), 50));
const limitToken = "$" + params.length;
const sql = "select reference_key, title, summary, domain, use_case, tags, video_url, poster_url, primary_oss_object_key, duration_seconds, aspect_ratio, resolution, fps, model_support, prompt_template, storyboard, shot_count, image_count_min, image_count_max, ai_character_policy, motion_keywords, style_keywords, reference_notes, quality_score, visibility, metadata, updated_at from data_knowledge.ai_video_references where " + where.join(" and ") + " order by quality_score desc, updated_at desc limit " + limitToken;
(async () => {
  const pool = new Pool({
    host: parsed.DB_HOST,
    port: Number.parseInt(parsed.DB_PORT || "5440", 10),
    database: parsed.DB_NAME,
    user: parsed.DB_USER,
    password: parsed.DB_PASSWORD,
    ssl: parsed.DB_SSL === "true" ? { rejectUnauthorized: false } : false,
  });
  const result = await pool.query(sql, params);
  await pool.end();
  console.log(JSON.stringify(result.rows));
})().catch((error) => {
  console.error(JSON.stringify({ ok: false, mode: "remote-ssh", error: error.message }));
  process.exit(1);
});
`;

function runRemoteSshQuery() {
  const target = process.env.AI_VIDEO_REFERENCE_QUERY_SSH_TARGET || "";
  if (!target) throw new Error("AI_VIDEO_REFERENCE_QUERY_SSH_TARGET is required for remote SSH query");
  const remoteCwd = process.env.AI_VIDEO_REFERENCE_QUERY_REMOTE_CWD || "/home/ecs-user/yeyiai/production/backend";
  const encoded = Buffer.from(JSON.stringify(filters), "utf8").toString("base64url");
  const remoteCommand = `cd ${shellQuote(remoteCwd)} && AI_VIDEO_REF_QUERY_B64=${shellQuote(encoded)} node -e ${shellQuote(remoteSource)}`;
  const sshArgs = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", `ConnectTimeout=${process.env.AI_VIDEO_REFERENCE_QUERY_CONNECT_TIMEOUT || "10"}`,
    target,
    remoteCommand,
  ];
  const result = spawnSync("ssh", sshArgs, { encoding: "utf8", maxBuffer: 20 * 1024 * 1024 });
  if (result.error) {
    console.error(JSON.stringify({ ok: false, mode: "remote-ssh", error: result.error.message }, null, 2));
    process.exit(4);
  }
  if (result.status !== 0) {
    console.error(JSON.stringify({ ok: false, mode: "remote-ssh", error: result.stderr.trim() || "remote query failed" }, null, 2));
    process.exit(result.status || 1);
  }
  return result.stdout.trim() || "[]";
}

const dbUrl = process.env.AI_NATIVE_DB_URL || process.env.DATA_KNOWLEDGE_DB_URL;
const text = dbUrl ? runLocalPsqlQuery(dbUrl) : runRemoteSshQuery();
try {
  JSON.parse(text);
  console.log(text);
} catch {
  console.log(JSON.stringify({ ok: true, raw: text }, null, 2));
}
