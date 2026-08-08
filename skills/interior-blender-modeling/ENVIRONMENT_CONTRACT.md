# 环境合同

## 多设备运行规则

- 下文 Ubuntu 路径只作已验收示例；正式入口由 `BLENDER_BIN`、`INTERIOR_BLENDER_ASSET_STORE` 和设备 runtime manifest 决定。
- Blender、MCP 与资产仓由管理员安装/同步并登记版本和 SHA-256；任务不得临时下载或借用其它设备路径。
- 只有实际执行账号完成版本检查、最小 `.blend`、GLB/manifest 与指定机位非空图后才为 `ready`；MCP 未配置但后台建模可用时可标为 `degraded`。

- 共享基线：GCP Manager `skills/interior-blender-modeling`。
- Ubuntu 安装：`/home/agentops/.codex/skills/interior-blender-modeling`。
- Blender：`/home/agentops/agent-runtime/bin/blender`。
- MCP：`/home/agentops/agent-runtime/bin/blender-mcp-server`，仅 stdio/localhost。
- 资产仓：`INTERIOR_BLENDER_ASSET_STORE=/home/agentops/agent-runtime/shared-assets/blender-interior-research`。
- Skill 包不保存 API key、Cookie、平台凭据或多 GB 资产副本。
- 百亿与百万工作区可以使用同一安装 Skill，但项目、交付和 revision 隔离。
