# Local Runtime

Node、ffmpeg、ffprobe 和 Skill 根目录以设备 runtime inventory / 当前 `$CODEX_HOME` 为准；下文 `/home/agentops/...` 只作 Ubuntu 示例。外部 secret 未授权时只运行 dry-run。

## 入口

- Node：`/home/agentops/agent-runtime/bin/node`
- 视频检查和合片：设备受管 `ffprobe`、`ffmpeg`
- Skill：`/home/agentops/.codex/skills/interior-design-video-production`

## 推荐执行顺序

```bash
node scripts/query_ai_video_references_db.mjs \
  --domain interior_design \
  --use-case room_story \
  --limit 6
```

需要人物时：

```bash
node scripts/query_seedance_virtual_human_assets_db.mjs \
  --q 现代家居设计顾问 \
  --limit 6
```

生成审阅页：

```bash
node scripts/render_design_video_storyboard_html.mjs \
  video-storyboard-plan.json \
  --out video-storyboard-preview.html
```

离线 dry-run：

```bash
node scripts/generate_seedance_video_from_storyboard.mjs \
  video-storyboard-plan.json \
  --out seedance-dry-run.json \
  --dry-run
```

零费用检查设备凭据与 Ark 连通性：

```bash
node scripts/check_seedance_connectivity.mjs \
  --out seedance-connectivity-check.json
```

预期状态为 `reachable_auth_ok_no_task_created`；该命令只发送 `GET`，不会创建
生成任务。

确认付费后的真实生成：

```bash
node scripts/generate_seedance_video_from_storyboard.mjs \
  video-storyboard-plan.json \
  --out seedance-video-generation-manifest.json \
  --output-dir outputs/seedance-video \
  --execute \
  --confirm-paid-generation
```

平台项目上传和社区发布使用已安装的 `idk-canvas-ingest-agent`，不从本 runtime
复制实现。
