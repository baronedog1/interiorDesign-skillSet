---
name: interior-blender-modeling
description: 当用户明确要求用 Blender、交付可编辑 .blend、使用 Blender 原生资产库或在 Blender 中建立完整户型时使用；直接消费 interior-floorplan-planning 已验收的 floorplan-handoff，在独立 Blender 模板中物化墙窗、门洞、空间、天花、灯具、阳台和组件，并交付原生 .blend、GLB、原生场景清单与验收证据。户型建模未指定后端时由 interior-html-modeling 作为默认后端。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"floorplan_handoff_schema":"interior.floorplan-handoff.v3","asset_selection_schema":"interior.blender-asset-selection.v1","relation_hints_schema":"interior.layout-relation-hints.v2","layout_overrides_schema":"interior.native-layout-overrides.v1","native_model_manifest_schema":"interior.native-model-manifest.v1","version":"1.5.0"}
---

# Interior Blender Modeling

所有上游文件先按 [data_contract.md](data_contract.md) 的 `semantic-content-first-v1` 发现；推荐目录和文件名只用于排序，不能代替 schema、哈希和模型身份校验。

## 职责

本 Skill 是完整户型的 Blender 原生后端。它与 `interior-html-modeling`、`interior-cad-modeling` 平级，三者只共享同一份上游 handoff，不互相导入模型或回执。

本 Skill 负责：

1. 把 accepted `floorplan-handoff.v3` 直接编译为可编辑 `.blend`。
2. 从 Blender 专属资产目录选择并链接真实 `.blend`/GLB 组件；不生成方盒家具兜底。
3. 在独立集合中维护墙、洞口、地面、可选天花、灯具、阳台、组件和相机。
4. 输出 `.blend`、GLB、`native-model-manifest.v1`、预览和 Blender/MCP 验收。
5. 向 `interior-camera-capture` 暴露 Blender 原生射线、显隐和截图入口。

## 触发与路由

- “用 Blender 建这个户型 / 给我 .blend / Blender 原生截图”：使用本 Skill。
- “给这个户型建模”且未指定后端：使用 `interior-html-modeling`，不并行运行三个后端。
- “分别给我 HTML、Blender、CAD 三个版本”：冻结一份 handoff，三个后端分别建立项目并独立验收。
- 只有源户型图时：先调用 `interior-floorplan-planning`。
- 找机位、四象限和渲染：模型 accepted 后先调用 `interior-circulation-planning`；只有同一 `.blend` 哈希的动线结果放行后，才依次调用 `interior-camera-capture`、`interior-space-rendering`。

## 唯一事实源

| 事实 | 唯一位置 |
|---|---|
| 墙、门窗、空间、连接、源对象位置与方向 | 当前 `floorplan-handoff.v3` |
| Blender 资产成员、标签、许可、轴与文件哈希 | `assets/blender-component-library/catalog.json` 及受管资产仓 |
| 当前项目资产选择 | `blender-asset-selection.json` |
| 资产方向轴及显式对象/墙目标提示 | 实体索引 `relationHints` |
| 贴墙、朝向、连接、净距和动线是否通过 | `interior-circulation-planning` |
| 当前 Blender 场景对象、集合、坐标和能力 | `.blend` + `native-model-manifest.json` |
| 正式机位算法与 accepted camera plan | `interior-camera-capture` |

资产选择只允许写 `assetId`、材质状态、允许的等比尺度和资产轴适配；位置、尺寸、方向、房间和源对象 ID 必须从 handoff 引用，禁止再手写一套 placement。

## 标准流程

1. 验证 handoff schema、digest、全部 artifact 哈希和 accepted 状态。
2. 运行 `init_blender_model_project.py` 建立空项目并复制 Blender 模板配置。
3. 运行 `index_blender_asset_store.py`，只索引本 Skill 所属的 Blender 受管资产仓；每个目录项必须先有人工接受的 `supportedFunctionalClasses` 和 `directionalAxes`。每个 accepted `sourceObjectCandidateId` 恰好选择一个资产；没有合格资产时停止，不用 primitive 替代。
4. 运行 `validate_asset_selection.py`。上游每个对象必须为 `quantity=1/atomicObject=true`，资产必须明确支持完全相等的 `functionalClass`；之后再验证路径、哈希、许可、审阅方向轴和尺度策略。禁止从名称或关键词临时猜类别，也禁止用其它类别或 primitive 顶替。
5. 用 Blender 后台模式运行 `build_floorplan_scene.py`。结构与 placement 只从 handoff 读取；资产选择只负责可见外形。导入资产必须先按全部可渲染子物体的世界包围盒测量，再用目标宽、深、高三轴中最严格的一项做统一缩放；随后按缩放和旋转后的真实包围盒重新对齐 handoff 中心并接地。禁止只按宽深缩放、信任资产原点，或用非等比缩放把高柜、椅子和灯具拉坏。
6. 默认生成每空间地面和 `CEILINGS` 集合。天花可一键显示/隐藏；吊灯必须挂到对应天花面并保留离地净高。
7. 窗型从 `windowStyle` 选择 `frameless-glass`、`casement`、`sliding` 或 `fixed-pane`；洞口位置和尺寸仍由上游决定。阳台用 `enclosureMode=open-railing|closed-glazing` 表达，不能把栏杆伪造成墙。
8. 用户编辑墙端点时导出 `structure-edit-patch.v1` 并回平面 Skill 生成新 handoff revision；组件或灯具移动留在当前项目 revision，并以原生 bounds 连续扫掠到首次接触。
9. 运行 `validate_blender_scene.py`、MCP reopen、GLB 导出、整体预览和至少一个正式机位预览。
10. 生成 `native-model-manifest.v1`；把 handoff、当前实体索引、原生 `.blend` 和审阅方向轴
    交给 `interior-circulation-planning`。若返回 `adjustment-plan.v2/correction-ready`，
    运行 `apply_circulation_adjustment.py` 追加摘要绑定 override，不询问用户；用
    `build_floorplan_scene.py --layout-overrides` 重建新 `.blend`、导出新哈希并全量重审。
11. 后续机位截图必须由 `capture_blender_views.py` 直接打开该 `.blend`，且 camera plan 必须绑定 accepted `circulation-result.v2`；不能转到 HTML 后截图。

## 硬门禁

- `.blend` 不读取 HTML、HTML import receipt、旧 `.blend` 或截图来补结构。
- `STRUCTURE`、`OPENINGS`、`FLOORS`、`CEILINGS`、`FURNITURE`、`LIGHTS`、`CAMERAS` 集合必须存在且对象 ID 稳定。
- 墙洞必须真实切开；玻璃不能穿过实墙。
- accepted 源对象一对一物化；缺资产、哈希变化、许可门禁失败或轴未审阅时停止。
- 餐桌不能映射茶几，马桶不能映射洗手台；目录没有同一 `functionalClass` 时必须停止并报告资产缺口。
- 每个组件缩放后的世界中心与 handoff 中心平面误差不得超过 `2mm`，最低点接地误差不得超过 `2mm`，最高点不得超过 handoff 高度；任一失败都拒绝场景。
- 槽位引导状态必须同时隐藏组件根节点和全部 `component-part` 子物体；白模状态必须覆盖全部 `component-part` 材质并在截图后恢复原材质。只改父空节点、仍露出源色子网格属于失败。
- 组件移动使用连续碰撞检测并停在首次接触位置；不得穿墙、堵真实开口或穿入其它组件。
- 天花显示状态只影响检查视图，不删除天花事实；正式渲染是否显示由镜头和渲染计划决定。
- Blender 机位截图、Entity ID、深度和射线证据必须来自同一个 `.blend` 哈希。
- 本 Skill 不计算沙发背贴墙、床头贴墙、沙发朝电视柜、餐椅朝餐桌或通道净宽；这些结论只能来自同一 `.blend` 哈希的 circulation audit。
- 只允许 `user-explicit-layout-correction` 或摘要闭合的
  `circulation-deterministic-correction` 改变 active transform；后者是确定性可逆修正，
  必须自动应用，不得重复询问用户。
- 实体索引只允许 `relationHints.v2`；不得携带距离、点积、净空、房间归属或通过结论，也不得接受旧关系字段。

## 停止条件

- handoff 不完整或与本轮附件不一致。
- accepted 对象没有合格 Blender 资产，或资产许可/哈希/轴不明确。
- 墙洞、空间、对象数量或坐标转换与 handoff 不一致。
- `.blend` 无法 reopen、原生截图为空、MCP 连接不成立或 native manifest 与文件哈希不一致。

## 高频数据入口

- 输入、资产选择、原生场景和编辑补丁字段：[data_contract.md](data_contract.md)
- 阶段流程、碰撞、天花与失败恢复：[playbook.md](playbook.md)
- 模板和 Blender 资产目录：[templates.md](templates.md)
- Blender 原生集合、坐标和资产加载架构：[references/architecture.md](references/architecture.md)
- 确定性脚本：[scripts_logic.md](scripts_logic.md)
- Blender/MCP 命令：[local_runtime.md](local_runtime.md)
- 共享基线、设备安装和受管资产仓：[ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)

## 交付

- accepted `.blend` 与派生 GLB；
- `blender-asset-selection.json`、`native-model-manifest.json`；
- 结构/组件/天花/灯具计数、碰撞与许可验收 JSON；
- MCP reopen 结果、整体预览和原生机位预览。

平台创建、上传和社区发布只交给 `idk-canvas-ingest-agent`。
