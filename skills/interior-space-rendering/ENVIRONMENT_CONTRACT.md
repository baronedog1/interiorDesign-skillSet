# 环境合同

- 共享基线：GCP Manager `interior-space-rendering`。
- Ubuntu 活动副本：`/home/agentops/.codex/skills/interior-space-rendering`。
- 本地确定性依赖：Python 3.11+。
- 图像生成：当前 Codex 原生 ImageGen 或已登记的 `imagegen-batch-orchestrator` 执行环境。
- 本 Skill 不读取平台 secret，不维护浏览器、Blender、CAD 或 ImageGen provider 密钥。
- 项目截图、请求和效果图只放项目 run，不进入 Skill。
- Skill 同步不要求重启 Bridge；旧 TUI 若需重新加载新说明，应在无在途任务时换新会话。
