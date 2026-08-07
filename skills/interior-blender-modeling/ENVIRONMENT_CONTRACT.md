# 环境合同

- 共享基线：GCP Manager `skills/interior-blender-modeling`。
- Ubuntu 安装：`/home/agentops/.codex/skills/interior-blender-modeling`。
- Blender：`/home/agentops/agent-runtime/bin/blender`。
- MCP：`/home/agentops/agent-runtime/bin/blender-mcp-server`，仅 stdio/localhost。
- 资产仓：`INTERIOR_BLENDER_ASSET_STORE=/home/agentops/agent-runtime/shared-assets/blender-interior-research`。
- Skill 包不保存 API key、Cookie、平台凭据或多 GB 资产副本。
- 百亿与百万工作区可以使用同一安装 Skill，但项目、交付和 revision 隔离。
