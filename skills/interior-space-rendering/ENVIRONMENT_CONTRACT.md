# 环境合同

## 多设备运行规则

- 无固定设备路径；Python、批次目录、图片输出目录和当前 Codex 的 `imagegen` 能力以设备 runtime inventory 与当前工作区为准。
- 本 Skill 不保存图像 API Key，不在任务中安装模型工具。
- 原生生成器 smoke 可独立登记，但正式 `ready` 还要求 accepted Q1/Q2/Q3 和 scene map；缺上游证据时为条件未满足，不得用旧图替代。

- 共享基线：GCP Manager 登记的 `interior-space-rendering`。
- Ubuntu 安装目录：`/home/agentops/.codex/skills/interior-space-rendering`，是共享基线的安装镜像，可按治理记录做设备定制。
- 渲染与复核不需要外部 API 配置或 `.env`。
- 可选平台入库依赖已安装的 `idk-canvas-ingest-agent`；本 Skill 不读取平台 secret，不维护 API 或 OSS/CDN 路线。
- 运行依赖只有 Python 3.11+、当前 Codex 原生图像编辑能力，以及项目或平台提供的只读资产索引。
- 项目截图、prompt、效果图和 PDF 放在项目 run，不进入 Skill。
- HTML、Blender、CAD 模板分别归三个建模 Skill；统一机位 JSON 只归 `interior-camera-capture`。
- 渲染只能消费正式截图调度器产生的 Q1/Q3 与 camera plan；不能调用后端截图适配器或在效果图阶段新建近似机位。
- ImageGen job 默认且最多 `5` 路依赖感知并发；本机截图最多 `2` 路，两种额度和进程模型完全独立。
- 项目绑定和发布回执放项目 run，不进入 Skill。
