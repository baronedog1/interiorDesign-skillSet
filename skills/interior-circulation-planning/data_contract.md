# 数据合同

## 推荐目录与语义发现

任务产物建议按阶段放置，便于人和 Agent 浏览，但目录与文件名只是**推荐位置**，绝不是有效性门禁：

| 目录 | 建议内容 |
|---|---|
| `source/` | 用户原图、附件和原始需求 |
| `planning/` | 平面 handoff、结构、描线和证据 |
| `model/<backend>/` | HTML、Blender 或 CAD 原生模型、布局及 manifest |
| `circulation/` | 动线 scene、audit、调整建议和 accepted result |
| `camera/` | camera plan、Q1/Q2/Q3、语义帧和 scene map |
| `rendering/` | render plan、请求、回执、终审和 Q4 |
| `delivery/` | 只放最终交付和验收摘要 |

读取上游产物必须遵循 `semantic-content-first-v1`：

1. 先用用户或 Bridge 明确提供的路径，再用上游 manifest 登记的相对路径。
2. 推荐路径不可用时，在当前任务工作区做有界搜索，按 schema、角色、`floorplanId`、模型 revision、内容哈希和 handoff digest 识别，而不是按文件名猜测。
3. 字段名或文件名缺少、增加或写错一个字符时，仅在内容结构有效且候选唯一时内存归一化；保留原文件并在 receipt 记录警告。
4. 多个候选内容哈希相同视为等价副本，优先推荐目录并记录其它路径；内容冲突时必须询问用户选择，不能自行挑路径。
5. 完全找不到时，先询问用户“是否已有该文件，请上传或提供路径”；用户确认没有后才能报告缺失。
6. 路径、目录名、文件名和 producer 的 patch 版本不能单独构成拒绝理由。Schema、身份哈希、空间/模型绑定、许可和内容冲突仍是硬门禁，不能因兼容发现而放宽。
7. 每次发现都输出 `artifactDiscovery`：推荐路径、实际路径、语义角色、内容哈希、归一化字段、等价副本和冲突状态。



## `interior.circulation-scene.v2`

三后端归一化后的当前布局事实。

必需字段：

- `floorplanId`
- `modelBackend`: `html-threejs | blender | cad-step`
- `bindings`: 原图、handoff、结构、描线、manifest、原生模型和布局状态路径及 SHA-256
- `backendAdapter`
- `components[]`
- `relationHints`
- `sceneDigestSha256`

每个组件必须包含：

- `id`
- `roomId`
- `sourceObjectCandidateId` 或 `designAdditionId`
- `assetId`
- `functionalClass`
- `quantity=1`
- `localAxes`
- `blockingClass`
- `footprint`: 当前模型坐标中的精确闭合多边形
- `activeTransform`
- `origin`

Blender/CAD 的 `activeTransform.planarScale` 必须由原生 `worldTransform.scale[x,z]` 编译；非等比缩放必须影响源描线轮廓，缺省缩放只能解释为 `[1,1,1]`。

`floor-obstacle` 才进入平面阻挡计算。设计新增组件没有 `planFootprint` 时拒绝。

`relationHints` 只能由各后端的 `interior.layout-relation-hints.v2` 编译而来：

- `facing[]` 只含 `sourceId/targetId/axisRole`；
- `wallAttachment[]` 只含 `sourceId/wallId/axisRole`；
- `allowedContacts[]` 只含 `firstId/secondId/kind=chair-tucked-under-table`，并且两个 ID 必须分别指向原子 `dining-chair` 与 `dining-table`；
- 不接受距离、点积、门限、房间归属、净空区或通过结论；
- 方向轴缺失时不能按文件名、类别或包围盒猜测，关系审计必须失败并退回资产审阅。

## `interior.circulation-audit.v2`

必需字段：

- `bindings`: 完整输入哈希
- `method`: 算法、分辨率、容差、`roomAreaGateCount=0`
- `topologyAudit`: 入口、连接、源/当前可达房间和每房间开口数
- `topologyAudit.connectionEndpointAudit`: 米制法向探测与上游源像素独立探测的逐连接交叉结果
- `layoutRelationshipAudit`: 本 Skill 独立重算的贴墙、朝向与射线命中结果
- `routes[]`
- `findings[]`
- `verdict`
- `auditDigestSha256`

每条路线至少包含：

```json
{
  "id": "entry-to-room::bedroom-1",
  "configuredTargetWidthMeters": 0.6,
  "structuralBaselineWidthMeters": 0.7,
  "effectiveRequiredWidthMeters": 0.6,
  "currentLayoutWidthMeters": 0.5,
  "layoutDeltaMeters": -0.2,
  "disposition": "layout-regression"
}
```

`verdict.status` 只能是：

- `accepted`
- `accepted-with-source-constraints`
- `needs-layout-adjustment`
- `blocked-input-integrity`

## `interior.circulation-adjustment-plan.v2`

这是当前审计状态唯一允许的确定性修正决定，不是修改结果。它必须声明：

- `automaticMutationPerformed=false`
- `mustNotChange` 包含红墙、门洞、窗、房间和源图证据
- `planDigestScope=bound-input-state-and-selected-operation-v1`
- `failureVector/failureScore` 与可选 `previousPlan`，只有严格改善才可继续
- 固定排序候选的 `targetFootprint`、`backendOperation`、操作摘要和受保护路线
- `automaticDecision.action=apply-without-user-confirmation` 及唯一 `selectedCandidateId`
- `confirmationPolicy.repeatConfirmationForbidden=true`
- `requiresBackendApplyAndFullReaudit=true`

任何输入哈希变化后，计划立即失效。当前后端只能执行摘要匹配的一个选中操作；写回后必须
生成新原生模型哈希并全量重审。无候选时为 `algorithm-blocked`，相同或更差失败向量为
`algorithm-stalled`；两者都不得靠随机移动或重复询问绕过。

## `interior.circulation-agent-review.v2`

必须绑定 audit、原图、handoff 和原生模型哈希，并包含四种真实文件证据角色：

- `source-floorplan`
- `floorplan-overlay`
- `native-model-top-view`
- `circulation-overlay`

终审不再接受一组由同一 Agent 自报的 `checks.*=true`。以下集合必须无重复且与 audit/scene
重算后的集合完全相等：

- `reviewedRoomIds`
- `reviewedConnectionIds`
- `reviewedAtomicObjectIds`
- `reviewedLayoutRelationshipKeys`，键格式为 `ruleId::sourceId::targetId::wallId`
- `reviewedRouteIds`

`findings` 必须是显式列表，`decision` 必须为 `accept`。少看一个房间、连接、对象、关系或
路线都会被拒绝。

## `interior.circulation-result.v2`

仅当 audit 为 accepted 类状态且布局错误、输入错误均为 0 时生成。它必须：

- 绑定 audit 与 Agent review 文件哈希。
- 保留原生模型 SHA-256。
- 声明 `roomAreaGateCount=0`。
- 声明 `structuralMutationPerformed=false`。
- 把同一模型交给 `interior-camera-capture`。

result 不能代替 audit 或视觉证据；它只是下游的完整性门票。
