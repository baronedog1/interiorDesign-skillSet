# HTML 布局事实到精细 Blender 整屋 说明书（AI 读取版）

版本：5.0.0

## YAML 头

```yaml
---
name: interior-blender-modeling
description: 当用户明确要求把当前可编辑 HTML 户型继续生成精细 Blender 整屋模型、交付 .blend/GLB，或让通用机位算法直接在 Blender 原生场景截图时使用。户型未指定后端时仍先由 interior-html-modeling 生成人机共创当前版。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"source_model_schema":"interior.coauthoring-current-model.v1","native_model_manifest_schema":"interior.native-model-manifest.v1","camera_scene_receipt_schema":"interior.camera-scene-generation-receipt.v1","version":"5.0.0"}
---
```

## 思路


## 调用场景

1. **把当前 HTML 布局编译成精细 Blender 并原生截图**：系统只拿 HTML 里的墙门窗、房间和家具 transform，不搬 HTML 模型。每件家具按 functionalClass、房间和风格标签从 Blender 原生多款资产中确定性选择；Y-up 等来源先按 catalog 预旋转归一，再按 JSON 尺寸和靠墙/关系语义放置。墙面、天花、干区木地板和湿区瓷砖分别使用受管 PBR 模板；模板包含真实贴图、物理映射尺寸、来源、许可和摘要，禁止运行时程序噪声或纯色回退。Camera 仍只在 HTML 当前版求解一次机位；Blender 每张图单独启动受管进程，在 Eevee 分配纹理前删掉非目标房间家具并清理孤儿数据，因此既保留真实 PBR、AgX、灯光和阴影，又不突破内存上限。缺资产或材质就先人工审查候选，不能自动搜索后入库，也不能回退白模。 输入：项目唯一 current-model、同版 structure、Blender 组件 catalog、PBR 材质 catalog、风格预设和冻结 Camera plan 输出：自包含 blend、派生 GLB、原生清单、十空间 PNG 与同名 JSON、批处理回执

## 完整文件

当前文件数：35

- `ENVIRONMENT_CONTRACT.md`：说明权威源、Ubuntu 运行时、资产仓、材质仓、渲染盒和同步关系。
- `MANIFEST.json`：登记版本和全部活动文件。
- `SKILL.md`：定义触发、事实源、精细资产、PBR 材质和禁止事项。
- `SKILL_MANUAL.pdf`：人类 A3 图文说明书。
- `agents/openai.yaml`：提供 Codex 默认调用提示。
- `assets/blender-component-library/acquisition-manifest.v1.json`：记录实际获取资产的来源、许可、大小和摘要。
- `assets/blender-component-library/catalog.json`：登记 Blender 同类多款精细资产、选型和朝向合同。
- `assets/blender-component-library/precision-asset-acquisition.v1.json`：登记人工审过的免费资产 ID。
- `assets/blender-material-library/acquisition-manifest.v1.json`：记录实际获取 PBR 材质的来源、许可、文件大小和摘要。
- `assets/blender-material-library/catalog.json`：登记墙面、天花、木地板和瓷砖 PBR 模板及物理映射。
- `assets/blender-material-library/material-acquisition.v1.json`：登记人工审定的 Poly Haven CC0 材质。
- `assets/blender-style-presets/warm-modern-neutral.json`：登记房间选型、结构 PBR 模板、Eevee 灯光和贴图预算。
- `assets/blender-template/backend-options.json`：固定后端、材质事实源与 Eevee 原生渲染选项。
- `data_contract.md`：规定输入、输出、选型、PBR 材质与朝向字段。
- `local_runtime.md`：记录 Ubuntu 正式命令。
- `playbook.md`：说明唯一执行流程。
- `references/architecture.md`：解释三层职责。
- `references/contracts.md`：列出交接合同。
- `references/skill-flowchart.svg`：流程总览。
- `references/skill-manual.json`：说明书唯一结构化事实源。
- `references/skill-manual.md`：AI 可读说明书。
- `scripts/acquire_blenderkit_assets.py`：获取审定免费资产并生成审计清单。
- `scripts/acquire_polyhaven_materials.py`：获取审定 CC0 PBR 材质并生成审计清单。
- `scripts/build_floorplan_scene.py`：唯一 Blender PBR 编译器。
- `scripts/capture_blender_batch.py`：逐图隔离截图批处理。
- `scripts/capture_blender_views.py`：目标房间剪枝与 Eevee 冻结机位适配器。
- `scripts/common.py`：JSON 与摘要函数。
- `scripts/export_camera_scene.py`：导出网格语义审计包。
- `scripts/export_native_model_manifest.py`：生成原生模型清单。
- `scripts/init_blender_model_project.py`：建立 v5 项目并绑定组件与材质 catalog。
- `scripts/resolve_component_motion.py`：连续首次接触计算。
- `scripts/test_mcp_connection.py`：连接和重开检查。
- `scripts/validate_blender_scene.py`：重开验证原生模型。
- `scripts_logic.md`：登记脚本职责。
- `templates.md`：说明唯一模板、组件资产与 PBR 材质。

## 具体逻辑解释


完整真实分支、回退路径和文件节点见根目录 `SKILL_MANUAL.pdf`。
