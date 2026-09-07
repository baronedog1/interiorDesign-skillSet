# 环境合同

- GCP 共享基线：`/home/baronedog111/gcp-manager/skills/interior-blender-modeling`。
- Ubuntu 活动副本：`/home/agentops/.codex/skills/interior-blender-modeling`。
- Blender 唯一入口：`/home/agentops/agent-runtime/bin/blender`，强制进入 `blender-heavy` 渲染盒。
- 精确资产来源：设备受管 `/home/agentops/agent-runtime/shared-assets/blender-interior-research/precision-v2/`；Skill catalog 固定文件摘要、来源许可、选型状态、来源轴、前向轴和朝向合同。HTML 几何不得进入 Blender。
- 建筑材料来源：设备受管 `/home/agentops/agent-runtime/shared-assets/blender-interior-research/materials-v1/`；只允许 catalog 登记的 Poly Haven CC0 1K Diffuse/Roughness/Normal 三图和固定物理尺度。
- 外部资产：只通过受管 BlenderKit Client 获取显式审过的免费资产，不读取浏览器 Cookie 或个人登录态；`royalty_free` 来源模型不得从 Skill 包二次分发。
- 外部材料：只通过 Poly Haven 官方 API 获取显式审过的 CC0 ID；下载图不放进 Skill 包，正式 `.blend` 使用时自包含打包。
- 原生截图：Eevee Next 960×600/16 samples/AgX；每张冻结机位使用一个独立 `blender-heavy` 进程，并在纹理分配前剪除非目标房间资产，受 `6G/7500M/1G swap` 限制。
- Camera 公共求解器：`/home/agentops/.codex/skills/interior-camera-capture`。
- MCP：`/home/agentops/agent-runtime/bin/blender-mcp-server`，仅用于 stdio/localhost 只读重开和有界编辑。
- Skill 包不保存客户模型、密钥、Cookie、会话或大型二进制资产。
- 百亿与百万共用活动 Skill，但项目目录、当前 HTML、`.blend`、截图和 revision 隔离。
