# Local Runtime

Skill 入口以当前 `$CODEX_HOME/skills/idk-canvas-ingest-agent` 为准，真实凭据只从 `IDK_ENV_FILE` 注入；下文 `/home/agentops/...` 只作 Ubuntu 示例。

运行依赖：Node.js 22+，无需 npm 安装。

首次创建项目并上传平面图：

```bash
node /home/agentops/.codex/skills/idk-canvas-ingest-agent/scripts/publish_project_artifact.mjs \
  --file <project>/layout-plan.png \
  --asset-kind layout_plan \
  --external-tool interior-floorplan-planning \
  --external-run-id <task-id> \
  --project-name <project-name> \
  --binding-file <project>/baiende-project.json \
  --folder-id plan \
  --receipt <project>/platform-publications/layout-plan.json
```

复用项目上传 HTML：

```bash
node /home/agentops/.codex/skills/idk-canvas-ingest-agent/scripts/publish_project_artifact.mjs \
  --file <project>/model-standalone.html \
  --asset-kind preview3d_html \
  --external-tool interior-html-modeling \
  --external-run-id <task-id> \
  --binding-file <project>/baiende-project.json \
  --folder-id 3d \
  --receipt <project>/platform-publications/model-html.json
```

所有命令均可先加 `--dry-run`。dry-run 不读取凭据、不写平台、不写绑定。

社区本地合同检查：

```bash
node /home/agentops/.codex/skills/idk-canvas-ingest-agent/scripts/publish_community_post.mjs \
  <project>/community-publication-spec.json \
  --binding-file <project>/baiende-project.json \
  --out <project>/platform-publications/community-dry-run.json \
  --dry-run
```

去掉 `--dry-run` 后生成平台预览，但仍不公开。用户本轮明确确认后才执行：

```bash
node /home/agentops/.codex/skills/idk-canvas-ingest-agent/scripts/publish_community_post.mjs \
  <project>/community-publication-spec.json \
  --binding-file <project>/baiende-project.json \
  --out <project>/platform-publications/community-publication.json \
  --execute \
  --confirm-public
```
