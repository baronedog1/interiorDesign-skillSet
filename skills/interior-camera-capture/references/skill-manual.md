# 室内空间唯一机位生成与截图 说明书（AI 读取版）

版本：47.0.1

## YAML 头

```yaml
---
name: interior-camera-capture
description: 当当前整屋 HTML、Blender 或 CAD 模型需要按空间自动求机位、截图并输出同名场景事实 JSON 时使用。唯一求解器优先选择目标房间内的自然正视镜头，并用目标房间墙体投影统一裁切左右和底部非目标区域。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"camera_plan_schema":"interior.algorithmic-camera-plan.v3","image_facts_schema":"interior.camera-image-facts.v3","backend_template_schema":"interior.camera-backend-template.v1","version":"47.0.1"}
---
```

## 思路


## 调用场景

1. **从当前整屋模型自动生成每个空间的正式机位图**：当用户已经完成当前 HTML，并希望从 HTML、Blender 或 CAD 得到同角度截图时，就进入这一条流程。系统只允许 HTML 模板导出真实 Three.js 场景并调用唯一求解器；若用户已经明确确认机位方向，可附带带来源证据的有向光轴，求解器优先遵守该方向。未指定方向时，再从主体正面轴和房间边界自动求解。正式计划冻结后，Blender 和 CAD 必须携带同一个计划文件和摘要，只能转换坐标与渲染，不能再算一次。全部候选都有提示时仍交付最佳可用镜头，不用质量门禁扣图。 输入：项目唯一当前 HTML 或原生模型、同一 revision 的户型结构、需要拍摄的空间列表及可选用户机位意图 输出：冻结机位计划、每空间正式 PNG、同名场景事实 JSON、逐阶段计时和流水线完成回执

## 完整文件

当前文件数：26

- `ENVIRONMENT_CONTRACT.md`：说明权威源、Ubuntu 运行时和同步关系。
- `MANIFEST.json`：登记版本和全部正式文件。
- `SKILL.md`：定义调用场景、唯一生产流程和禁止恢复的旧做法。
- `SKILL_MANUAL.pdf`：人类 A3 图文说明书。
- `agents/openai.yaml`：提供 Codex 默认调用提示。
- `assets/backend-templates/blender.json`：声明 Blender 必须复用 HTML 冻结计划并执行原生截图。
- `assets/backend-templates/cad.json`：声明 CAD 必须复用同一计划、转换合同并执行截图。
- `assets/backend-templates/html.json`：声明 HTML 场景生成、原生探测和 Three.js 截图适配。
- `data_contract.md`：规定输入、计划、图片、事实 JSON 和下游交接。
- `local_runtime.md`：记录 Ubuntu 正式命令与依赖。
- `playbook.md`：说明从当前模型到正式交付的完整流程。
- `references/algorithm.md`：解释唯一场景与机位算法公式。
- `references/requirements.txt`：固定 Python 运行依赖。
- `references/skill-flowchart.svg`：唯一流程总览图。
- `references/skill-manual.json`：说明书唯一结构化事实源。
- `references/skill-manual.md`：AI 可读说明书。
- `scripts/audit_delivery.py`：审计真实流水线、旧文件和唯一决策入口。
- `scripts/capture_frozen_html_plan.mjs`：按冻结机位在 HTML 中截图，原样应用左右和底部墙体裁切，并把投影坐标映射到最终 PNG。
- `scripts/export_backend_camera_plan.py`：在后端合同需要时无损转换冻结计划，不能改选机位。
- `scripts/export_html_camera_scene.mjs`：从当前 HTML 导出真实模型和 GLTF。
- `scripts/generate_vtk_camera_scene.py`：生成唯一 VTK 场景包。
- `scripts/run_camera_pipeline.py`：唯一客户生产入口；HTML只求解一次，Blender/CAD只复用冻结计划并记录总耗时。
- `scripts/semantic_vtk_scene.py`：提供 VTK 实体、深度和射线事实。
- `scripts/unified_camera_solver.py`：唯一拥有主体、自然视野排序、后退站位、目标房间墙体裁切、显隐和最终选择权的求解器。
- `scripts_logic.md`：登记正式脚本和决策权。
- `tests/test_contracts.py`：回归版本、法线、唯一入口和无降级分支。

## 具体逻辑解释

### 三类原生模型到统一语义场景

这一页解释后端模板怎样把 HTML、Blender、CAD 原生事实统一成同一个求解输入，以及对象和网格怎样一一核对。

HTML 模板让当前页面自己导出运行时模型和 GLTF；Blender 与 CAD 模板读取对应建模 Skill 从当前原生模型导出的场景包。三个后端都统一提供稳定 Entity-ID、户型、结构版本、房间、语义、方向和真实网格包络，再送入同一个 VTK 求解层。模板不读取历史相机、不构造简化方盒，也不包含另一套 selector。任何缺失都会明确失败并指向当前模型或场景导出代码；修复后仍从同一个入口重跑。

- 输入：HTML、Blender 或 CAD 当前原生模型；同版结构数据
- 核心规则：后端模板生成或接收当前模型 GLTF；模型对象与原生网格一一对应；户型身份必须一致
- 失败处理：明确停止并修复当前模型或导出代码，不构造替代场景。
- 验收证据：场景生成回执、GLTF 摘要、对象与网格计数完全一致。

### 唯一严格正视机位求解器

这一页解释主体、墙法线、站位、FOV、移轴和真实像素如何在同一个求解器里完成。

求解器先按房间功能选择主体组，再从真实背景墙内法线生成严格正视候选。房内存在自然视野解时优先房内；否则沿同一法线后退。每个候选都计算主体大小、上下空间、遮挡、透视和墙体裁切，这些结果统一写入 qualityAdvisories 并参与排序，不再形成 质量硬门禁。只要存在几何上有效的严格正视候选，就选择排序最高的一张并交给截图器；没有达到理想质量时仍照常交付，同时把问题留给通用算法研发。只有模型、结构、墙体或真实网格事实缺失，导致连严格正视几何候选都不存在时，才停止并修输入。

- 输入：真实 VTK 场景；空间多边形；拍摄空间列表
- 核心规则：选择主体组和真实背景墙；只生成墙法线严格正视候选；求最小必要 FOV 与移轴；用实体和深度事实确认完整可见
- 失败处理：只有模型、结构、墙体或真实网格事实缺失，导致没有严格正视几何候选时才停止；质量提示不阻断截图。
- 验收证据：计划中的镜头来自唯一 strict-wall-frontal 候选族，qualityAdvisories 随图交付，deliveryBlockedByQuality=false。


完整真实分支、回退路径和文件节点见根目录 `SKILL_MANUAL.pdf`。
