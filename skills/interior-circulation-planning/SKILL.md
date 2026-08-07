---
name: interior-circulation-planning
description: 当用户要求检查“动线/空间规划/布局是否合理”、家具或柜体是否挡路、门口是否被堵、房间能否进出、通道净宽是否被摆放压缩，或整屋建模完成后需要在找机位前复核布局时使用；读取原始户型证据、冻结的红墙/门洞/房间拓扑和当前 HTML、Blender、CAD/Text2CAD 原生模型，以结构基线与当前摆放的差分区分原户型限制、布局新增问题和证据链错误，并生成可复核的组件调整闭环。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"relation_hints_schema":"interior.layout-relation-hints.v2","scene_schema":"interior.circulation-scene.v2","audit_schema":"interior.circulation-audit.v2","adjustment_plan_schema":"interior.circulation-adjustment-plan.v2","result_schema":"interior.circulation-result.v2","version":"3.1.0"}
---

# 动线规划

所有上游文件先按 [data_contract.md](data_contract.md) 的 `semantic-content-first-v1` 发现；推荐目录和文件名只用于排序。门洞法向探针只把真实房间或户外算作空间，墙厚带和浅层未归属采样不能构成第二空间。

版本：`3.1.0`

## 唯一职责

本 Skill 位于“平面规划 + 一个整屋建模后端”之后、“找机位”之前。它只回答三件事：

1. 原始红墙、真实门洞和空间连接本来允许怎样通行。
2. 当前活动家具、落地柜体和设备是否让这种通行能力变差。
3. 如果变差，确定性选择哪一个可逆组件变换，并让当前原生建模后端直接执行。

它不拥有第二套墙、门、窗、房间或家具事实，也不直接写原生文件；它拥有修正候选的搜索、排序和唯一自动决定，当前建模后端只负责按该决定写回并导出新 revision。机位、效果图或施工规范审查不属于本 Skill。

## 三类结论

所有发现必须且只能归入下列一类：

| 类别 | 示例 | 处理 |
|---|---|---|
| `source-structure` | 原过道本来只有 0.7m；原图中房间本来没有可识别入口 | 提示并继续，不拒绝布局，不擅自改红墙 |
| `current-layout` | 原过道 1.5m，家具摆入后只剩 0.5m；柜体封住原门洞 | 必须调整当前家具/柜体，并重新全量审计 |
| `input-integrity` | 原图、handoff、结构、原生模型或布局状态哈希不一致 | 停止，退回事实源修正，禁止继续计算 |

有效要求固定为：

```text
effectiveRequiredWidth = min(configuredTargetWidth, structuralBaselineWidth)
```

因此：

- 原通道 1.5m、目标 0.9m、摆放后 0.8m：布局问题。
- 原通道 0.7m、目标 0.9m、摆放后仍为 0.7m：原户型限制，只提示。
- 原通道 0.7m、摆放后 0.5m：布局问题，因为当前摆放继续压缩了基线。
- 卧室、厨房或卫生间面积小：不是本 Skill 的拒绝条件。

`assets/circulation-policy.v2.json` 是唯一数值策略；禁止在报告、后端适配器或提示词里维护第二份门限。

## 高频数据入口

必须同时提供：

- 原始户型图片，且哈希与 `interior.floorplan-handoff.v3` 一致。
- `interior.floorplan-handoff.v3`、`interior.floorplan-structure.v3`、`interior.trace-components.v2`。
- 当前后端的 `interior.native-model-manifest.v1` 及哈希一致的原生模型。
- 当前布局状态：
  - HTML：`interior.component-layout.v4`
  - Blender：`interior.blender-entity-index.v2`
  - CAD/Text2CAD：`interior.cad-entity-index.v1`

三种后端只通过适配器归一化“当前组件精确平面轮廓”，不会互相读取或改写模型。源图对象必须沿用冻结描线轮廓；设计新增物件必须提供 `planFootprint`，不接受中心点加猜测包围盒。
每个组件还必须携带上游唯一 `functionalClass`、`quantity=1`、`assetId` 和当前变换；
资产的 `front|back|headboard` 局部轴只能来自 HTML/Blender/CAD 对真实资产的原生预览审阅。
后端只通过 `relationHints.v2` 提供这些轴及显式对象/墙目标，不得夹带距离、点积、
净空、房间归属或通过结论；本 Skill 对旧关系对象直接拒绝。
餐椅收进餐桌只允许登记原子椅/桌 ID 对，不允许登记未经计算的“最大穿入深度”；
其它接触或碰撞不得使用白名单绕过当前模型与动线审计。

## 简单意图入口

- “检查这个布局合不合理 / 看下动线 / 家具有没有挡路”：执行本 Skill。
- “户型建好后找机位”：若没有同一模型哈希的 accepted 动线结果，先执行本 Skill。
- “原户型太小怎么办”：可以说明限制，但不能用本 Skill 改户型。
- “改墙、改门洞、改空间边界”：退回 `interior-floorplan-planning`，不在本 Skill 内完成。

## 唯一算法

### 1. 冻结结构基线

只从 `structure-data.v3` 栅格化：

- 红墙及真实厚度；
- `connections[]` 中的真实开口；
- 房间多边形和外部入口；
- 原始楼板边界。

这一层不放任何家具。它表示“该户型本来最多能做到什么”，不是合规户型模板。

### 2. 编译当前布局

在完全相同的网格上加入当前落地障碍：活动家具、落地柜体和落地设备。地毯、挂画、镜子、窗帘、吊灯和离地组件不作为平面阻挡物。

禁止靠物件名称猜位置；位置、方向、平面缩放和轮廓必须来自当前原生模型状态。

### 3. 生成拓扑与路线

必须检查：

- 每个真实门洞两侧能否互通；
- 每个源拓扑可达房间能否从外部入口到达内部服务锚点；
- 一个房间有多个开口时，各开口之间能否穿行；
- 每个房间的结构开口数和当前可用开口数；
- 源拓扑可达、但当前布局不可达的“进得去/出不来”问题。

路径使用最大瓶颈宽度算法，不用一条手绘中心线冒充完整可行域。正反方向共享同一静态自由空间图，因此 accepted 边必须双向成立。
入口到房间的可达目标是“该房间任一可站立内部自由区域”，不是房间多边形质心；质心落在柜体、床或非通行功能区时不能把本来可进入的房间误判为失联。

每条连接还要做两次相互独立的端点检查：上游拓扑编译器在源像素空间沿开口法向探测，
本 Skill 在米制空间重新探测。两次结果都必须与声明的两个空间完全一致；不能复用
`fromRoomId/toRoomId` 作为计算输入再宣称验证通过。

### 4. 做基线差分

同一路线分别计算：

- `structuralBaselineWidthMeters`
- `currentLayoutWidthMeters`
- `effectiveRequiredWidthMeters`
- `layoutDeltaMeters`

只要当前布局低于“目标与结构基线中的较小者”，就是 `layout-regression`。结构本身不可达或不足，只记 `source-constraint`。

### 5. 归因组件

对失败路径附近的组件逐一做“临时移除”反事实测试：

- 单独移除即可恢复者是 `provenSingleCulpritIds`。
- 移除后改善但未完全恢复者是 `contributorIds`。
- 无法证明时不得指定唯一罪因，交给 Agent 联合检查。

### 6. 计算布局关系

本 Skill 是布局关系几何的唯一计算者，按 `circulation-policy.v2` 逐项计算：

- 沙发 `back` 到真实墙面的间距不超过 `0.08m`，且背轴朝墙。
- 床的 `headboard` 到真实墙面的间距不超过 `0.05m`，且床头轴朝墙。
- 同房间存在电视柜时，沙发 `front` 射线必须命中电视柜，占向点积至少 `0.95`。
- 每把 `dining-chair` 的 `front` 射线必须命中唯一餐桌，占向点积至少 `0.95`。

存在多个同类目标且没有显式目标提示时，算法按“同房间、兼容功能类、当前几何距离、稳定 ID”
唯一选择最近目标；显式目标提示只改变候选集合，不携带通过结论。点积、射线、贴墙距离和
通过结论仍由本 Skill 重算。HTML、Blender、CAD 不得另存第二套通过数值。

### 7. 形成唯一可回滚调整

`plan_layout_adjustments.py` 按固定顺序搜索同一房间内、无碰撞、不穿墙、不压住受保护路径的
平移、贴墙和面向候选，以失败向量、移动量、旋转量和稳定 ID 排序，每轮只选择一个候选。
它输出带摘要的 `apply-without-user-confirmation` 原生后端操作，不写回模型。

调整固定由当前后端执行：

| 后端 | 调整 Skill |
|---|---|
| HTML/Three.js | `interior-html-modeling` |
| Blender | `interior-blender-modeling` |
| CAD/Text2CAD | `interior-cad-modeling` |

当前后端必须自动应用该可逆操作，不得询问用户。应用后旧审计立即失效，必须重新导出模型、
编译 scene 并全量审计；失败向量没有严格改善即输出 `algorithm-stalled` 并停止，不能只复查
一条失败路径或反复试同一修正。只有无安全变换、源证据冲突、用户硬性设计意图缺失，或涉及
不可逆、付费、公开操作时才允许把全部阻塞合并为一次问题。

## 标准流程

1. 校验原图、handoff、结构、描线、原生模型和当前布局状态的 ID 与 SHA-256。
2. 编译统一 scene：

```bash
python3 scripts/build_circulation_scene.py \
  --handoff floorplan-handoff.json \
  --structure structure-data.json \
  --traces trace-components.json \
  --manifest native-model-manifest.json \
  --layout-state current-layout-state.json \
  --source-image source-floorplan.png \
  --out circulation-scene.json
```

3. 执行结构基线和当前布局差分：

```bash
python3 scripts/audit_circulation.py \
  --structure structure-data.json \
  --scene circulation-scene.json \
  --policy assets/circulation-policy.v2.json \
  --out circulation-audit.json \
  --svg-out circulation-overlay.svg
```

4. 若状态为 `needs-layout-adjustment`，生成候选：

```bash
python3 scripts/plan_layout_adjustments.py \
  --structure structure-data.json \
  --scene circulation-scene.json \
  --audit circulation-audit.json \
  --policy assets/circulation-policy.v2.json \
  --out circulation-adjustment-plan.json
```

5. `workflowStatus=correction-ready` 时，当前建模后端立即应用
   `automaticDecision.selectedCandidateId`，不向用户确认；导出新模型后把本计划作为
   `--previous-plan` 重新从第 1 步运行。每轮只允许一个操作，且失败向量必须严格改善。
6. 审计进入 accepted 类状态后，Agent 对照原图、平面叠图、原生模型顶视图和动线叠图；
   使用 `interior.circulation-agent-review.v2` 逐项列出已查看的房间、原子对象、连接、
   布局关系和路线。验证器必须把五个集合与 audit/scene 重算结果完全比对。
7. 只有审计为 `accepted` 或 `accepted-with-source-constraints` 时，才能生成 `interior.circulation-result.v2`：

```bash
python3 scripts/finalize_circulation_delivery.py \
  --audit circulation-audit.json \
  --agent-review circulation-agent-review.json \
  --out circulation-result.json
```

8. 将结果和同一原生模型交给 `interior-camera-capture`。

## Agent 视觉复核

代码负责几何和拓扑，Agent 必须负责图像语义。四份证据缺一不可：

1. 原始户型图。
2. 平面规划红墙、蓝窗、真实门洞和组件描线叠图。
3. 当前原生模型正交顶视图。
4. 动线 SVG，包括结构基线路径、当前路径和阻挡组件。

必须确认：源图与平面结构一致、平面结构与模型一致、组件位置/方向/轮廓一致、开口数量与连接一致、原始限制没有被误报成布局错误。不能只看 JSON 数值。

## 禁止规则

- 禁止用卧室、厨房、卫生间面积或原始走廊宽度直接拒绝布局。
- 禁止把目标净宽写回红墙，或为了通过检查增删墙门窗。
- 禁止把原图中本来存在的问题伪装成当前设计师造成的问题。
- 禁止把当前家具造成的压缩降级成“户型没办法”。
- 禁止未绑定 audit/plan 摘要的临时移动、随机试位、删除源图对象、缩小物件或跨房间挪动；
  `adjustment-plan.v2` 唯一授权的同房间可逆修正必须自动执行。
- 禁止只靠物件中心、AABB 或截图二次识别代替精确平面轮廓。
- 禁止复用输入哈希已变化的旧 audit、adjustment plan 或 result。
- 禁止后端用自报关系结果绕过本 Skill；`layoutRelationshipAudit` 是唯一正式通过事实。

## 停止条件

- 任一事实文件、原图、布局状态或原生模型哈希不一致。
- 三后端输入不属于同一 `floorplanId/handoffDigest`。
- 当前组件缺精确平面轮廓、房间归属或原生变换。
- 当前组件缺精确 `functionalClass/quantity=1/assetId` 或真实资产方向轴。
- 视觉复核发现原图、平面规划和当前模型结构不一致。
- 仍有 `current-layout`、`input-integrity` 或布局关系错误。
- 确定性搜索无安全变换或失败向量不再改善；此时一次性报告全部阻塞，不重复询问同一问题。

原户型限制本身不是停止条件。

## 文档路由

- [playbook.md](playbook.md)：完整执行与调整闭环。
- [data_contract.md](data_contract.md)：scene、audit、adjustment、review 和 result 合同。
- [references/baseline-differential-method.md](references/baseline-differential-method.md)：基线差分原则。
- [references/topology-and-clearance-method.md](references/topology-and-clearance-method.md)：开口、可达性和最大瓶颈路径。
- [references/backend-adapters.md](references/backend-adapters.md)：三后端适配边界。
- [scripts_logic.md](scripts_logic.md)：脚本职责与退出规则。
- [local_runtime.md](local_runtime.md)：本地运行命令。
- [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)：运行时、外部事实和安全边界。
