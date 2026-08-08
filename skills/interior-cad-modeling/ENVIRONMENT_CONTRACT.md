# 环境合同

## 多设备运行规则

- 下文 Ubuntu 路径只作示例；正式入口由 `CAD_PYTHON_BIN`、`INTERIOR_CAD_ASSET_STORE`、`INTERIOR_CAD_SNAPSHOT_COMMAND` 与设备 runtime manifest 决定。
- CAD runtime、snapshot renderer 和资产仓由管理员预装并固定版本；任务不得 `pip install` 或复制其它设备运行态。
- 只有目标账号完成最小 handoff→STEP→entity index→selection report→快照闭环后才为 `ready`；缺任一关键项时为 `blocked`。

- 权威 Skill：GCP Manager shared baseline 的 `interior-cad-modeling`。
- Ubuntu 安装：`/home/agentops/.codex/skills/interior-cad-modeling`。
- CAD 受管资产仓：`/home/agentops/agent-runtime/workspaces/interior-design-2/cad-asset-library`。
- 资产仓只归 CAD 后端；HTML、Blender Skill 不复制或修改。
- Skill 不保存 API Key、平台凭据或付费服务 token。
- 百亿、百万可共用同一 Skill 安装内容，但项目、Bridge、附件和交付目录隔离。
- CAD Python runtime 必须包含 `build123d` 与 `Pillow`；Pillow 仅用于同 STEP occurrence 隔离截图的确定性像素差和语义蒙版，不用于识图。
