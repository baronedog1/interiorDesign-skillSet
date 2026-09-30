# 当前户型到精细整屋模型

版本：5.1.1

```yaml
---
name: interior-blender-modeling
description: 当用户明确要求把当前可编辑 HTML 户型继续生成精细 Blender 整屋模型、交付 .blend/GLB，或让通用机位算法直接在 Blender 原生场景截图时使用。户型未指定后端时仍先由 interior-html-modeling 生成人机共创当前版。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"source_model_schema":"interior.coauthoring-current-model.v1","native_model_manifest_schema":"interior.native-model-manifest.v1","camera_scene_receipt_schema":"interior.camera-scene-generation-receipt.v1","version":"5.1.1"}
---
```

总分结构：1 张总图；0 张来自主节点的展开。

## 1. 总图 · 从当前户型制作精细模型并交付

触发：用户确认 HTML 布局后明确要求 Blender 精细模型或 Blender 原生机位图时调用。；输入：用户提供当前户型事实并要求 Blender 整屋工程或原生机位图片；输出：自包含模型、派生文件、原生清单、按请求制作的图片及真实限制
布局：semantic-grid；选择理由：先横向核对并制作模型，再按是否需要图片分支，回到同一交付；避免把全部步骤排成长条。

### input · 用户给当前户型并要求精细整屋模型
明确要求 Blender 工程或原生机位图时调用；默认由当前代理完成。
- [入口] `SKILL.md`：定义触发、事实源、精细资产、PBR 材质和禁止事项。
- [配置] `agents/openai.yaml`：提供 Codex 默认调用提示。

### prepare · 核对布局、审定资产和本机条件
读取同项目、同版本的墙门窗、房间与家具尺寸位置。
缺素材时仅获取已审定的免费或 CC0 资源；付费或受限资源按已有授权处理。
身份冲突、文件缺失、摘要变化或本机依赖受阻时，记录具体原因及可用文件。
补充说明：输入为 current-model/coauthoring-model 与同版 structure；HTML 几何不导入 Blender。
- [方法] `data_contract.md`：规定输入、输出、选型、PBR 材质与朝向字段。
- [方法] `local_runtime.md`：记录 Ubuntu 正式命令。
- [方法] `ENVIRONMENT_CONTRACT.md`：说明权威源、Ubuntu 运行时、资产仓、材质仓、渲染盒和同步关系。
- [方法] `templates.md`：说明唯一模板、组件资产与 PBR 材质。
- [方法] `references/architecture.md`：解释三层职责。
- [方法] `references/contracts.md`：列出交接合同。
- [数据] `assets/blender-component-library/catalog.json`：登记 Blender 同类多款精细资产、选型和朝向合同。
- [数据] `assets/blender-component-library/precision-asset-acquisition.v1.json`：登记人工审过的免费资产 ID。
- [数据] `assets/blender-component-library/acquisition-manifest.v1.json`：记录实际获取资产的来源、许可、大小和摘要。
- [数据] `assets/blender-material-library/catalog.json`：登记墙面、天花、木地板和瓷砖 PBR 模板及物理映射。
- [数据] `assets/blender-material-library/material-acquisition.v1.json`：登记人工审定的 Poly Haven CC0 材质。
- [数据] `assets/blender-material-library/acquisition-manifest.v1.json`：记录实际获取 PBR 材质的来源、许可、文件大小和摘要。
- [执行] `scripts/acquire_blenderkit_assets.py`：获取审定免费资产并生成审计清单。
- [执行] `scripts/acquire_polyhaven_materials.py`：获取审定 CC0 PBR 材质并生成审计清单。
- [执行] `scripts/init_blender_model_project.py`：建立 v5 项目并绑定组件与材质 catalog。

### build · 按房间选款并制作精细模型
同功能类按房间风格选款，先统一来源轴，再按确认尺寸和朝向装配。
墙、顶、干湿区地面读取登记贴图，按真实尺度映射；素材缺失不以方盒或色块补位。
编辑时用连续首次接触计算位移；客户当前布局和修改留在本项目。
补充说明：坐标转换 [x,y,z] → [x,-z,y]；贴图为 Diffuse/Roughness/Normal；模型保存为自包含 .blend 和派生 GLB。
- [方法] `playbook.md`：说明唯一执行流程。
- [方法] `scripts_logic.md`：登记脚本职责。
- [执行] `scripts/build_floorplan_scene.py`：唯一 Blender PBR 编译器。
- [模块] `scripts/common.py`：JSON 与摘要函数。
- [执行] `scripts/resolve_component_motion.py`：连续首次接触计算。
- [数据] `assets/blender-style-presets/warm-modern-neutral.json`：登记房间选型、结构 PBR 模板、Eevee 灯光和贴图预算。
- [配置] `assets/blender-template/backend-options.json`：固定后端、材质事实源与 Eevee 原生渲染选项。

### verify · 重新打开模型并核对真实结果
核对集合、组件身份、素材摘要、朝向和贴图打包，登记未匹配项及技术失败。
生成原生模型清单和真实网格审计数据；失败只修对应输入、登记或编译器。
- [验证] `scripts/validate_blender_scene.py`：重开验证原生模型。
- [验证] `scripts/test_mcp_connection.py`：连接和重开检查。
- [执行] `scripts/export_native_model_manifest.py`：生成原生模型清单。
- [执行] `scripts/export_camera_scene.py`：导出网格语义审计包。

### want · 用户是否需要原生机位图片？
按用户要求选择交付范围；受阻模型只整理已有结果和原因。
- [入口] `SKILL.md`：定义触发、事实源、精细资产、PBR 材质和禁止事项。
- [方法] `playbook.md`：说明唯一执行流程。

### capture · 用同版机位逐张拍摄房间
读取 Camera 已冻结机位，逐图使用独立进程并清理非目标房间资产。
记录请求、成功和失败数量；实际图片及回执与本次模型绑定。
补充说明：固定 plan 的 position/target/FOV/windowCenter/显隐与裁切；Eevee 960×600、16 samples、AgX；遵守现有渲染盒限额。
- [执行] `scripts/capture_blender_batch.py`：逐图隔离截图批处理。
- [执行] `scripts/capture_blender_views.py`：目标房间剪枝与 Eevee 冻结机位适配器。
- [方法] `local_runtime.md`：记录 Ubuntu 正式命令。

### organize · 整理交付范围、使用说明与登记
普通任务整理可交付模型、图片与真实限制；模型受阻时说明原因和已有成果。
只有修改本 Skill 规则、代码或目录时，更新版本、文件登记和同源说明书；不增加建模前置检查。
- [登记] `MANIFEST.json`：登记版本和全部活动文件。
- [图源] `manual/skill-manual.json`：说明书唯一结构化事实源。
- [交付] `manual/skill-manual.md`：AI 可读说明书。
- [交付] `manual/skill-flowchart.svg`：流程总览。
- [交付] `manual/skill-manual.html`：提供可放大、按文件定位和跳转的同源使用说明

### deliver · 用户拿到精细模型和所需图片
交付可重开的模型、原生清单、请求的机位图与回执；未完成项单独说明。
平台上传仍沿用已有授权与平台 Skill。
- [入口] `SKILL.md`：定义触发、事实源、精细资产、PBR 材质和禁止事项。
- [交付] `SKILL_MANUAL.pdf`：提供从用户输入到交付的中文流程图和使用说明

连线：
- input → prepare
- prepare → build
- build → verify
- verify → want
- want → capture：需要图片且模型可用
- want → organize：只要模型或本次受阻
- capture → organize：图片与实际回执
- organize → deliver

## 文件索引（全部用途已在节点内说明）
- `ENVIRONMENT_CONTRACT.md`：说明权威源、Ubuntu 运行时、资产仓、材质仓、渲染盒和同步关系。；对应 main/prepare
- `MANIFEST.json`：登记版本和全部活动文件。；对应 main/organize
- `SKILL.md`：定义触发、事实源、精细资产、PBR 材质和禁止事项。；对应 main/input、main/want、main/deliver
- `SKILL_MANUAL.pdf`：提供从用户输入到交付的中文流程图和使用说明；对应 main/deliver
- `agents/openai.yaml`：提供 Codex 默认调用提示。；对应 main/input
- `assets/blender-component-library/acquisition-manifest.v1.json`：记录实际获取资产的来源、许可、大小和摘要。；对应 main/prepare
- `assets/blender-component-library/catalog.json`：登记 Blender 同类多款精细资产、选型和朝向合同。；对应 main/prepare
- `assets/blender-component-library/precision-asset-acquisition.v1.json`：登记人工审过的免费资产 ID。；对应 main/prepare
- `assets/blender-material-library/acquisition-manifest.v1.json`：记录实际获取 PBR 材质的来源、许可、文件大小和摘要。；对应 main/prepare
- `assets/blender-material-library/catalog.json`：登记墙面、天花、木地板和瓷砖 PBR 模板及物理映射。；对应 main/prepare
- `assets/blender-material-library/material-acquisition.v1.json`：登记人工审定的 Poly Haven CC0 材质。；对应 main/prepare
- `assets/blender-style-presets/warm-modern-neutral.json`：登记房间选型、结构 PBR 模板、Eevee 灯光和贴图预算。；对应 main/build
- `assets/blender-template/backend-options.json`：固定后端、材质事实源与 Eevee 原生渲染选项。；对应 main/build
- `data_contract.md`：规定输入、输出、选型、PBR 材质与朝向字段。；对应 main/prepare
- `local_runtime.md`：记录 Ubuntu 正式命令。；对应 main/prepare、main/capture
- `manual/skill-flowchart.svg`：流程总览。；对应 main/organize
- `manual/skill-manual.html`：提供可放大、按文件定位和跳转的同源使用说明；对应 main/organize
- `manual/skill-manual.json`：说明书唯一结构化事实源。；对应 main/organize
- `manual/skill-manual.md`：AI 可读说明书。；对应 main/organize
- `playbook.md`：说明唯一执行流程。；对应 main/build、main/want
- `references/architecture.md`：解释三层职责。；对应 main/prepare
- `references/contracts.md`：列出交接合同。；对应 main/prepare
- `scripts/acquire_blenderkit_assets.py`：获取审定免费资产并生成审计清单。；对应 main/prepare
- `scripts/acquire_polyhaven_materials.py`：获取审定 CC0 PBR 材质并生成审计清单。；对应 main/prepare
- `scripts/build_floorplan_scene.py`：唯一 Blender PBR 编译器。；对应 main/build
- `scripts/capture_blender_batch.py`：逐图隔离截图批处理。；对应 main/capture
- `scripts/capture_blender_views.py`：目标房间剪枝与 Eevee 冻结机位适配器。；对应 main/capture
- `scripts/common.py`：JSON 与摘要函数。；对应 main/build
- `scripts/export_camera_scene.py`：导出网格语义审计包。；对应 main/verify
- `scripts/export_native_model_manifest.py`：生成原生模型清单。；对应 main/verify
- `scripts/init_blender_model_project.py`：建立 v5 项目并绑定组件与材质 catalog。；对应 main/prepare
- `scripts/resolve_component_motion.py`：连续首次接触计算。；对应 main/build
- `scripts/test_mcp_connection.py`：连接和重开检查。；对应 main/verify
- `scripts/validate_blender_scene.py`：重开验证原生模型。；对应 main/verify
- `scripts_logic.md`：登记脚本职责。；对应 main/build
- `templates.md`：说明唯一模板、组件资产与 PBR 材质。；对应 main/prepare
