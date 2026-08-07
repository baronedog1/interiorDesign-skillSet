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
  const raw = Number(value || 8);
  return Number.isFinite(raw) ? Math.min(Math.max(Math.trunc(raw), 1), 30) : 8;
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

const filters = {
  gender: readArg("--gender") || undefined,
  q: readArg("--q") || undefined,
  ageMin: readArg("--age-min") || undefined,
  ageMax: readArg("--age-max") || undefined,
  tags: readRepeated("--tag"),
  exclude: readRepeated("--exclude-asset-id"),
  limit: clampLimit(readArg("--limit")),
};

const remoteSource = String.raw`
const fs = require("node:fs");
const dotenv = require("dotenv");
const { Pool } = require("pg");

const filters = JSON.parse(Buffer.from(process.env.SEEDANCE_ASSET_QUERY_B64 || "e30", "base64url").toString("utf8"));
const parsed = dotenv.parse(fs.readFileSync(".env"));
const params = [];
const where = ["status = 'active'"];
const add = (value) => {
  params.push(value);
  return "$" + params.length;
};
if (filters.gender) where.push("gender = " + add(filters.gender));
if (filters.ageMin) where.push("age >= " + add(Number.parseInt(String(filters.ageMin), 10)));
if (filters.ageMax) where.push("age <= " + add(Number.parseInt(String(filters.ageMax), 10)));
for (const assetId of filters.exclude || []) where.push("asset_id <> " + add(assetId));
const searchExpr = "COALESCE(search_text,'') || ' ' || COALESCE(display_label,'') || ' ' || COALESCE(user_label,'') || ' ' || COALESCE(appearance_summary,'') || ' ' || COALESCE(clothing_summary,'') || ' ' || COALESCE(usage_notes,'')";
if (filters.q) where.push("(" + searchExpr + ") ILIKE " + add("%" + filters.q + "%"));
for (const tag of filters.tags || []) where.push("(" + searchExpr + ") ILIKE " + add("%" + tag + "%"));
params.push(Math.min(Math.max(Number.parseInt(String(filters.limit || 8), 10) || 8, 1), 30));
const limitToken = "$" + params.length;
const sql = [
  "select",
  "  asset_id,",
  "  asset_uri,",
  "  display_label,",
  "  gender,",
  "  age,",
  "  country_or_region,",
  "  occupation,",
  "  appearance_summary,",
  "  clothing_summary,",
  "  usage_notes,",
  "  user_label,",
  "  user_label_preference,",
  "  user_label_notes,",
  "  user_label_assigned_role,",
  "  appearance_tags,",
  "  profile_tags,",
  "  updated_at,",
  "  (",
  "    case when user_label_preference = 'selected' then 40 else 0 end +",
  "    case when COALESCE(user_label,'') ~ '美女|帅哥|大美女|小美女|颜值|路人偏上' then 30 else 0 end +",
  "    case when COALESCE(occupation,'') ~ '模特|主播|网红|歌手|设计|主持|演员' then 10 else 0 end",
  "  ) as match_score",
  "from public.seedance_virtual_human_assets",
  "where " + where.join(" and "),
  "order by match_score desc, updated_at desc",
  "limit " + limitToken
].join("\n");
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
  const target = process.env.SEEDANCE_ASSET_QUERY_SSH_TARGET || process.env.AI_VIDEO_REFERENCE_QUERY_SSH_TARGET || "";
  if (!target) throw new Error("SEEDANCE_ASSET_QUERY_SSH_TARGET or AI_VIDEO_REFERENCE_QUERY_SSH_TARGET is required for remote SSH query");
  const remoteCwd = process.env.SEEDANCE_ASSET_QUERY_REMOTE_CWD || process.env.AI_VIDEO_REFERENCE_QUERY_REMOTE_CWD || "/home/ecs-user/yeyiai/production/backend";
  const encoded = Buffer.from(JSON.stringify(filters), "utf8").toString("base64url");
  const remoteCommand = `cd ${shellQuote(remoteCwd)} && SEEDANCE_ASSET_QUERY_B64=${shellQuote(encoded)} node -e ${shellQuote(remoteSource)}`;
  const sshArgs = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", `ConnectTimeout=${process.env.SEEDANCE_ASSET_QUERY_CONNECT_TIMEOUT || process.env.AI_VIDEO_REFERENCE_QUERY_CONNECT_TIMEOUT || "10"}`,
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

const text = runRemoteSshQuery();
try {
  JSON.parse(text);
  console.log(text);
} catch {
  console.log(JSON.stringify({ ok: true, raw: text }, null, 2));
}
