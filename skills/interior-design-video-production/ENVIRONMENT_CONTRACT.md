# Environment Contract

## 权威源与安装

- Ubuntu 权威源和安装：
  `/home/agentops/.codex/skills/interior-design-video-production`
- 工作区：
  `/home/agentops/agent-runtime/workspaces/interior-design` 或
  `/home/agentops/agent-runtime/workspaces/interior-design-2`
- Node：设备受管 Node 22。
- 媒体工具：受管 `ffmpeg`、`ffprobe`。

## Seedance / Ark

设备级唯一凭据文件：

`/home/agentops/agent-runtime/secrets/interior-design-video-production.env`

- 文件 owner 必须是 `agentops`，权限必须是 `0600`。
- 正式变量名是 `VOLCENGINE_ARK_API_KEY`。
- 为兼容历史受管凭据，读取器也接受 `ARK_API_KEY`、`SEEDANCE_API_KEY`，但会在
  进程内统一为 `VOLCENGINE_ARK_API_KEY`；不得复制出第二份文件。
- 只有真实执行和零费用鉴权检查读取该文件；dry-run 不访问它。
- 紧急轮换时可用 `SEEDANCE_VIDEO_SECRET_FILE` 指向另一份 `0600` 受管文件，完成
  验收后应恢复默认路径。

| 环境变量 | 必需性 | 用途 |
|---|---|---|
| `VOLCENGINE_ARK_API_KEY` | 仅真实生成必需 | Ark Bearer 密钥；dry-run 不读取 |
| `SEEDANCE_VIDEO_SECRET_FILE` | 可选 | 临时覆盖受管 secret 路径；默认使用设备级唯一文件 |
| `SEEDANCE_VIDEO_API_BASE_URL` | 可选 | 默认 `https://ark.cn-beijing.volces.com/api/v3` |
| `SEEDANCE20_VIDEO_MODEL_ID` | 可选 | 标准模型 ID |
| `SEEDANCE20_FAST_VIDEO_MODEL_ID` | 可选 | fast 模型 ID |
| `SEEDANCE_VIDEO_REQUEST_TIMEOUT_MS` | 可选 | 单次 HTTP 超时，默认 30000 |
| `SEEDANCE_VIDEO_POLL_INTERVAL_MS` | 可选 | 轮询间隔，默认 10000 |
| `SEEDANCE_VIDEO_MAX_POLLS` | 可选 | 最大轮询次数，默认 180 |
| `SEEDANCE_VIDEO_OUTPUT_DIR` | 可选 | 片段输出目录 |

工作区 `.env.local`、`.env` 不再是视频凭据来源。进程临时注入的 Key 优先于受管
文件，便于密钥轮换验收；任何 Key 值都不得写入计划、generation manifest、日志、
Skill、版本库或交付包。

## 视频参考库

优先使用本地受管数据库连接：

| 环境变量 | 用途 |
|---|---|
| `AI_NATIVE_DB_URL` 或 `DATA_KNOWLEDGE_DB_URL` | 本地只读 PostgreSQL 连接 |
| `AI_NATIVE_PSQL_BIN` | 自定义 `psql` 路径 |

没有本地连接时，查询脚本通过受管 SSH 入口执行只读查询：

| 环境变量 | 要求 |
|---|---|
| `AI_VIDEO_REFERENCE_QUERY_SSH_TARGET` | 远端查询时必填；公开 SkillSet 不保存设备地址 |
| `AI_VIDEO_REFERENCE_QUERY_REMOTE_CWD` | `/home/ecs-user/yeyiai/production/backend` |
| `AI_VIDEO_REFERENCE_QUERY_CONNECT_TIMEOUT` | `10` |

## 人物资产库

| 环境变量 | 默认值 |
|---|---|
| `SEEDANCE_ASSET_QUERY_SSH_TARGET` | 复用视频参考 SSH target |
| `SEEDANCE_ASSET_QUERY_REMOTE_CWD` | 复用视频参考 remote cwd |
| `SEEDANCE_ASSET_QUERY_CONNECT_TIMEOUT` | 复用视频参考 timeout |

远端数据库凭据只在远端受管 `.env` 中读取，不回传给本设备，不进入交付。

## 平台边界

百恩得项目创建、文件上传、预览和社区发布完全委托：

`/home/agentops/.codex/skills/idk-canvas-ingest-agent`

本 Skill 不读取 `IDK_API_KEY`，也不维护百恩得 API base URL。

## 安全

- 未确认付费时不得传 `--execute`。
- 真实执行前必须通过 `check_seedance_connectivity.mjs`；该检查只查询一个不存在的
  task ID，不创建任务、不扣费。
- 失败后不得自动重试。
- 不把签名 URL、密钥或数据库连接写入报告。
- 用户素材只用于本轮已授权的视频计划。
