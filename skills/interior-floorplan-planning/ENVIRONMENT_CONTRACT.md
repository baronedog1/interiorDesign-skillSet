# Environment Contract

## 多设备运行规则

- 下文共享基线与 Ubuntu 路径只作来源/安装示例；运行解释器由设备 runtime inventory 指定。
- Python、Pillow、NumPy、OpenCV 由管理员预装并固定；任务不得临时 `pip install`。
- 只有目标账号完成模块导入、标准 fixture、四象限与 handoff schema/hash 验收后才为 `ready`；缺 OpenCV 时必须为 `blocked`。

- 推荐共享基线：`/home/baronedog111/gcp-manager/skills/interior-floorplan-planning`。
- Ubuntu 安装副本：`/home/agentops/.codex/skills/interior-floorplan-planning`。
- 同步是显式复制，不自动覆盖设备定制。
- 本 Skill 不需要 secret、账号或外部 API；可选平台入库依赖已安装的 `idk-canvas-ingest-agent`，凭据由其受管环境独占。
- 原生绘图由 Codex 系统 image generation 能力执行；该能力不作为本 Skill 的本地脚本。
