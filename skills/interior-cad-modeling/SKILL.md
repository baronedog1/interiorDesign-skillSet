---
name: interior-cad-modeling
description: 当用户明确要求用 Text2CAD、CAD、STEP、FreeCAD 或可编辑 B-rep 建立完整户型，要求交付 STEP/STP，或要求从 CAD 原生模型找机位和截图时使用；直接消费 interior-floorplan-planning 已验收的 floorplan-handoff，在独立 CAD 模板中物化墙窗、门洞、空间、天花、灯具、阳台和 CAD 组件，并交付原生 STEP、同 B-rep 派生 GLB、可选 3MF/STL 审阅网格、原生模型清单与验收证据。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"floorplan_handoff_schema":"interior.floorplan-handoff.v3","asset_selection_schema":"interior.cad-asset-selection.v1","relation_hints_schema":"interior.layout-relation-hints.v2","layout_overrides_schema":"interior.native-layout-overrides.v1","native_model_manifest_schema":"interior.native-model-manifest.v1","version":"1.5.0"}
---

# Interior CAD Modeling

## 使用前准备

- 管理员预装固定 CAD Python runtime（build123d/OCP/cadpy）、CAD snapshot renderer 和版本化 CAD 资产仓；配置 `INTERIOR_CAD_ASSET_STORE` 与 `INTERIOR_CAD_SNAPSHOT_COMMAND`。
- 先读取 [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) 与 [local_runtime.md](local_runtime.md)，完成最小 STEP、entity index、资产选择和快照 preflight。
- 必须已有 accepted `floorplan-handoff`；runtime、资产、快照命令或 handoff 缺失时在构建前标记 `blocked`，禁止任务内安装包或改走 HTML/Blender 伪装 CAD 交付。

所有上游文件先按 [data_contract.md](data_contract.md) 的 `semantic-content-first-v1` 发现；推荐目录和文件名只用于排序，不能代替 schema、哈希和模型身份校验。

## 职责

本 Skill 是完整户型的 CAD/Text2CAD 原生后端，与 `interior-html-modeling`、`interior-blender-modeling` 平级。三个后端只共享同一份 accepted handoff，不读取彼此的回执、模型或截图。

本 Skill 负责：

1. 将 `floorplan-handoff.v3` 直接编译为可编辑 STEP B-rep；
2. 从 CAD 专属资产目录选择可编辑 STEP/FCStd 源模型，不生成方盒家具兜底；
3. 维护独立的建筑结构、门窗、地板、可选天花、灯具、阳台、组件和相机模板；
4. 输出 STEP、同 B-rep 派生 GLB、可选 3MF/STL 审阅网格、`native-model-manifest.v1` 和 CAD 原生截图证据；
5. 输出 accepted `native-model-manifest.v1` 后，先交给 `interior-circulation-planning`
   独立检查通路与布局关系；`correction-ready` 时自动应用唯一摘要绑定 override 并重建 STEP，
   不向用户确认；只有 accepted 结果才能进入机位。
6. 向 `interior-camera-capture` 暴露 STEP occurrence selector、显隐和原生截图适配器。CAD Snapshot 当前不输出逐像素深度/Entity-ID，因此清单必须如实标记为 `false`；正式 scene map 只能由同一 STEP 自动派生的 occurrence 拓扑在同一相机下执行 Z-buffer 后产出，不能截图识图、伪造通道或转到 HTML 代拍。

## 触发与路由

- “用 CAD/Text2CAD 建这个户型 / 给我 STEP / 用 FreeCAD”：使用本 Skill。
- “给户型建模”但未指定后端：默认使用 `interior-html-modeling`。
- “HTML、Blender、CAD 各做一版”：冻结一份 handoff，三个项目独立编译和验收。
- 只有户型图：先调用 `interior-floorplan-planning`。
- accepted 后的通路与摆放关系审计：调用 `interior-circulation-planning`。
- 动线 accepted 后找机位、四象限和渲染：调用同一个 `interior-camera-capture` 与 `interior-space-rendering`。
- 单个产品的精密 CAD 逆向建模：使用独立 `cad-object-modeling`，不进入本完整户型后端。

## 唯一事实源

| 事实 | 唯一位置 |
|---|---|
| 墙、门窗、空间、连接、源对象位置与方向 | 当前 `floorplan-handoff.v3` |
| CAD 资产源码、格式、轴、许可和哈希 | `assets/cad-component-library/residential-catalog-v3.json` 与 CAD 受管资产仓 |
| 当前项目资产选择 | `cad-asset-selection.json` |
| 通路、贴墙和面向关系 | `interior-circulation-planning` |
| 当前项目 B-rep、实体和选择器 | accepted STEP + `native-model-manifest.json` |
| 正式机位算法 | `interior-camera-capture` |

资产选择只写 `assetId`、具体 STEP 格式、轴适配、统一尺度和用途许可决定。位置、方向、尺寸、房间、对象 ID 只能从 handoff 读取。

## 标准流程

1. 验证 handoff schema、digest、artifact 哈希和 accepted 状态。
2. 用 `init_cad_model_project.py` 初始化独立 CAD 项目。
3. 按 handoff 的原子 `functionalClass` 建立 `cad-asset-selection.json`；每个 `quantity=1` 对象恰好选一个已验收 STEP 资产。名称、关键词、外形相似或风格均不能改写功能类别。
4. 用 `validate_asset_selection.py` 对比上游 `functionalClass` 与 catalog `supportedFunctionalClasses`，再验证一对一映射、文件哈希、本地正面轴、许可、可再编辑格式和无 placement 副本。精确功能类缺件时必须停止，不能跨类借用、临时建模或方盒代替。
5. 用 `build_cad_floorplan.py` 直接读取 handoff 建立墙、真实窗洞、地板、天花、门窗和组件 B-rep；不读取 HTML 回执或案例坐标。
6. 天花默认存在但检查视图隐藏；吊灯挂接到相应 room 天花，并检查净高。
7. 窗型可选 `frameless-glass|fixed-pane|casement|sliding`，阳台可选 `source|open-railing|closed-glazing`；样式不改变上游洞口边界。
8. 墙端点编辑导出沿原墙轴的 `structure-edit-patch.v1` 并回平面 Skill 形成新 handoff revision。组件移动用 STEP 原生 bounds 扫掠，停在首次接触。
9. 导出 STEP、同 B-rep 派生 GLB、可选 3MF/STL 审阅网格、结构/组件/碰撞/许可报告，并用 CAD viewer reopen。
10. 用 `export_native_model_manifest.py` 绑定 STEP、entity index 和由该 STEP 同次导出的 occurrence 拓扑 GLB，生成统一原生模型清单；后续彩色截图必须由 `capture_cad_views.py` 打开该 STEP，不转到 HTML/Blender。实体索引中的 selector 必须是 CAD Viewer 实际解析的顶层 `#o1.N` occurrence，语义拓扑节点必须保留同一 occurrence ID；只有顶层 selector 才能进入显隐操作。
11. 调用动线 Skill。本 Skill 不重算通道净宽、沙发/床贴墙、沙发朝向电视柜或餐椅朝向餐桌。

## 硬门禁

- STEP 不读取 HTML import receipt、旧 STEP、旧 `.blend` 或截图来补结构。
- 每个 accepted `sourceObjectCandidateId` 在 STEP assembly 中恰好对应一个根实体。
- 资产没有 STEP、哈希变化、许可不满足当前用途、轴未审阅或比例不合理时停止。
- 仓库 blanket 许可与资产内嵌许可冲突时，只能标记 `research-only` 并禁止平台上传、社区发布和模型再分发；商业/公开用途必须人工解决许可。
- 墙洞是真实 B-rep 开孔；玻璃不得穿实墙。
- 原生彩色截图、selector 显隐和语义拓扑必须绑定同一个 STEP 哈希；不存在的 CAD Depth/Entity-ID 能力必须写 `false`。需要槽位屏幕区域时，只能读取该 STEP 自动派生、带 occurrence 节点的隐藏 GLB，用同一相机做软件 Z-buffer；禁止逐对象截图颜色差分、截图后二次识图或人工填写区域。
- CAD 后端不持有第二套房间、墙、对象位置或相机算法。
- CAD entity index 只允许 `relationHints.v2` 的方向轴和显式目标引用；不得保存距离、点积、净空、房间归属或通过结论。

## 停止条件

- handoff 不完整、旧版或与本轮源图不一致；
- accepted 对象没有合法 STEP 资产；
- 构件数量、空间归属、世界变换或坐标往返与 handoff 不一致；
- STEP 无法 reopen、B-rep 无效、原生截图为空或 native manifest 哈希不一致。

## 高频数据入口

- [data_contract.md](data_contract.md)：handoff、资产选择、STEP entity 与原生清单。
- [playbook.md](playbook.md)：阶段、编辑、碰撞和失败恢复。
- [templates.md](templates.md)：CAD 模板与资产目录。
- [references/cad-architecture.md](references/cad-architecture.md)：B-rep 结构。
- [references/licensing-and-editability.md](references/licensing-and-editability.md)：研究用途与可编辑门禁。
- [scripts_logic.md](scripts_logic.md)、[local_runtime.md](local_runtime.md)：脚本和命令。
- [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)：运行环境与安装边界。

## 交付

- accepted STEP、由 `export_gltf` 登记派生的 GLB 与可选 3MF/STL 审阅网格；
- `cad-asset-selection.json`、`native-model-manifest.json`；
- 结构、组件、B-rep、碰撞、许可和原生截图报告。

项目创建、上传和社区发布只交给 `idk-canvas-ingest-agent`。
