# Environment Contract

## 多设备运行规则

- 下文 Ubuntu 路径只作示例；其它设备必须通过 `IDK_ENV_FILE` 指向自己的受管凭据文件，并使用本机 `$CODEX_HOME/skills/idk-canvas-ingest-agent`。
- Node 由管理员预装；任务不得复制其它设备 secret 或在 Skill 目录创建 `.env`。
- 无获批凭据时状态为 `degraded/dry-run-only`，不能把源码安装或 dry-run 通过登记成真实上传 `ready`。

## 权威源与安装

- 项目源码：`/home/ecs-user/idk-ai-native-skills/repo/skills/idk-canvas-ingest-agent`
- Ubuntu 安装：`/home/agentops/.codex/skills/idk-canvas-ingest-agent`
- 设备设计 Skills 通过该安装入口发布，不复制脚本。

## 受管凭据

- Ubuntu 唯一凭据文件：`/home/agentops/agent-runtime/secrets/baiende-platform.env`
- 权限：`0600`，所有者 `agentops`。
- 其它设备可通过进程环境 `IDK_ENV_FILE` 指向其受管 secret。
- 文件内正式变量：`IDK_API_BASE_URL`、`IDK_API_KEY`、`IDK_TOOL_NAME`、`IDK_REQUEST_TIMEOUT_MS`、`IDK_ALLOW_LOCAL_API`。

Skill 目录、工作区、项目、交付包、日志和回执均不得含 API Key。发布脚本禁止读取 cwd 或 Skill 根目录的 `.env/.env.local`。

## API 边界

- 生产根：`https://www.baiende.com/api/v1`
- 仅允许 HTTPS；受控 localhost/Tailnet 测试必须显式 `IDK_ALLOW_LOCAL_API=YES`。
- 本 Skill 不提供无凭据匿名上传、生成、扣费或删除；社区公开必须由用户明确确认。
