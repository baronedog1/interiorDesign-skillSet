# 环境合同

- 权威 Skill：GCP Manager shared baseline 的 `interior-cad-modeling`。
- Ubuntu 安装：`/home/agentops/.codex/skills/interior-cad-modeling`。
- CAD 受管资产仓：`/home/agentops/agent-runtime/workspaces/interior-design-2/cad-asset-library`。
- 资产仓只归 CAD 后端；HTML、Blender Skill 不复制或修改。
- Skill 不保存 API Key、平台凭据或付费服务 token。
- 百亿、百万可共用同一 Skill 安装内容，但项目、Bridge、附件和交付目录隔离。
- CAD Python runtime 必须包含 `build123d` 与 `Pillow`；Pillow 仅用于同 STEP occurrence 隔离截图的确定性像素差和语义蒙版，不用于识图。
