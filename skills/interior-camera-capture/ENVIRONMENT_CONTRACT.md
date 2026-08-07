# 环境合同

- 正式设备：`ubuntu-01`，运行用户 `agentops`。
- 正式安装目录：`/home/agentops/.codex/skills/interior-camera-capture`。
- 本 Skill 不保存建模模板、模型资产、HTML、`.blend`、STEP 或业务 API Key。
- HTML/Blender/CAD 原生截图适配器均由对应建模 Skill 维护，并通过 `native-model-manifest.v1` 暴露唯一入口。
- 真实截图唯一入口是本 Skill 的 `scripts/capture_model_views.py`；后端适配器拒绝绕过调度器的真实运行。
- 正式截图前后必须记录内存、swap、load、memory PSI、根盘及 `/tmp` 压力；整台设备最多同时运行 `2` 个截图作业，单作业内顺序复用一个 Chrome/Blender/CAD 进程。
- ImageGen 是远端作业编排，最高 `5` 路并发不适用于本机截图，也不能复用截图槽位。
- 找机位前必须提供由 `interior-circulation-planning` 生成、且绑定同一原生模型哈希的 `interior.circulation-result.v2`。
- `CHROME_BIN`、`BLENDER_BIN`、`INTERIOR_CAD_SNAPSHOT_COMMAND` 只作为设备运行时覆盖项。
- 输出只能写当前任务工作区或显式可写目录。
- 两个设计 Agent 共用同一安装内容，但各自使用独立工作区、模型清单、计划和截图目录。
- `camera-plan.v8` 必须与结构 v3、原生模型哈希和后端绑定。
- 本 Skill 不启动常驻服务、不修改模型、不删除交付文件、不读取平台凭据。
