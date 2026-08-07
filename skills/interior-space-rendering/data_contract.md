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



## 上游 `interior.shot-scene-map.v9`

必须 accepted，且包含：

- `visibleFrame`：按当前相机原生像素和前向深度筛选后的房间/连接集合；
- `visibleFrame.decisions` 只能包含 `included=true` 的当前镜头事实；结构、槽位和连接的房间归属必须是 `visibleRoomIds` 的子集；
- `assets.visibilityAudit` 必须存在且 role 为 `qa-only-never-submit-to-image-model`，只校验文件与哈希，不能进入任何生成输入；
- `closedWorldView`：与 `rooms/connections/structures/placementSlots` 精确相等；
- `shotContract.wallNormalFrontal`：正视主图必须为 `true`；
- Q1 `slotGuidedConcreteImage` 必须是无组件、无槽位覆盖的纯水泥结构图；Q2 `furnishedReferenceImage` 是 QA 图；Q3 `planCameraImage` 是平面机位图；
- `placementSlots[]` 保存完整位置、尺寸、朝向和图像区域，`placementRelations[]` 保存朝向目标、贴墙、接触和组合关系；
- `guidance.selectionOwner=interior-space-rendering/render-plan.v11`；
- 同一 `shotId/sourceModelSha256/camera`。
- `assets.cameraPlan` 与 `assets.planCameraJson` 必须存在且哈希有效。计划必须为 `camera-plan.v8` / `deterministic-wall-normal-camera-v7`；scene map、Q3 camera JSON 与 selected shot 的 `position/target/fov/focalLengthMm` 逐字段相同。HTML Q3 固定来自 `external-formal-camera-plan-v8`。主 shot 必须为 `one-point-frontal` 且命中登记背景墙。

## `interior.model-image-render-plan.v11`

核心字段：

```json
{
  "schema": "interior.model-image-render-plan.v11",
  "schemaVersion": "11.0",
  "floorplanId": "example-home",
  "modeSelectionOwner": "render-plan.v11",
  "modeSwitchingPolicy": "forbidden",
  "renderExecutionPolicy": {
    "schema": "interior.render-execution-policy.v2",
    "primaryProducer": "imagegen-closed-world",
    "maximumImagegenCandidatesPerFrontalMaster": 3,
    "onImagegenExhaustion": "stop-without-q4-delivery",
    "q4ProducerRequirement": "imagegen-receipt-only",
    "thresholdRelaxation": "forbidden",
    "nativeSceneFallback": "forbidden"
  },
  "userProductReferenceManifest": {
    "path": "user-products.json",
    "sha256": "...",
    "required": true
  },
  "requestedStyles": ["modern-minimal"],
  "selectedShots": [],
  "spaceReferencePlan": {
    "schema": "interior.space-reference-plan.v1",
    "shots": [
      {
        "shotId": "living-frontal",
        "primaryRoomId": "living",
        "role": "frontal-master",
        "visibleRoomIds": ["living", "dining"],
        "visibleSlotIds": ["sofa-01", "table-01"],
        "dependsOnAcceptedShotIds": []
      }
    ],
    "executionBatches": [["living-frontal"]]
  },
  "outputs": [
    {
      "shotId": "living-frontal",
      "styleId": "modern-minimal",
      "status": "accepted",
      "fourQuadrantEvidence": {
        "path": "living-frontal-four-quadrant.evidence.json",
        "sha256": "..."
      }
    }
  ]
}
```

约束：

- 每个 primary room 的首个 shot 必须是 `frontal-master`；
- 正式生成模式只有 `selectedShots[].guidance.mode=slot-guided`，不存在全局默认模式或模式切换字段；
- `visibleRoomIds/visibleSlotIds` 必须等于 scene map；
- 两个 shot 共享房间或槽位即视为重叠；同批禁止重叠；
- 后续 shot 的依赖必须精确等于所有较早批次中与它重叠的 shot；
- 依赖未 accepted 时，后续输出不得进入 candidate/accepted。
- `architecturalTreatment.projectionLock` 必须由 scene map 的全部房间、结构、连接和槽位区域确定性生成；禁止手写近似区域。
- 每个 `frontal-master` 最多生成 3 个 imagegen 候选；连续拒绝后必须停止且不交付 Q4，不能再次抽样、无限抽样、放宽误差或用原生模型截图回退。
- `validate_render_plan.py` 的普通模式只验证可继续执行的计划状态；最终交付必须使用 `--require-complete`。此时每个 shot/style 都必须 `status=accepted`，并用 `fourQuadrantEvidence.path/sha256` 绑定同一 `shotId/renderId/sourceModelSha256` 的有效 evidence。

## `interior.user-product-reference-manifest.v1`

当用户提供指定家具图片时必须生成。`references[]` 保存原图路径、哈希及图中每个产品的 `productId/functionalClass/sourceRegionNormalized`；`slotBindings[]` 将产品逐一绑定到 scene map 的 `slotId`。参考图只拥有产品身份和外观权，不拥有相机、建筑、房间拓扑或槽位位置/占地/朝向权。`required=true` 时，所选镜头内每个可见槽位都必须恰好绑定一次。

## `interior.render-media-context.v7`

每个 shot/style 一个 context：

- `guidanceSelection.mode` 固定为 `slot-guided`，`sourceImageRoles` 只包含 Q1；Q2 永远是 QA-only；
- `spaceIdentityReferences[]` 逐项绑定较早 accepted 输出哈希、共享房间与槽位；
- `userProductReferences[]` 逐项绑定当前可见槽位、产品 ID、参考图 ID、图中区域和图片哈希；
- 先前参考只能是 `appearance-and-object-identity-only`，不得控制当前相机、裁切、墙和开口；
- `spaceLayout` 从 scene map 单向引用 visible rooms、connections、structures、完整 placement slots 和 placement relations；
- `attachmentManifest` 可以登记 Q2 与 masks 为 QA-only，但默认槽位引导的 submitted inputs 只能列 Q1、scene/context JSON、计划内身份参考和已绑定用户产品图。

## `interior.imagegen-prompt-manifest.v7`

只能由 `build_prompt_manifest.py` 生成：

- `promptCompiler=closed-world-scene-v2`；
- 禁止 `finalPrompt`；
- 必须发送 Q1 与 scene/context JSON，禁止发送 Q2、Entity mask、Room mask 或任何可见槽位覆盖；
- `accepted-space-identity-reference` 可多张，以 `referenceId` 唯一；
- `user-product-reference` 只能来自已验证的产品 manifest，且 `coveredSlotIds` 必须与 context 逐项一致；
- 图片附件只允许当前 Q1、context 声明的 accepted 身份参考和已绑定用户产品图；禁止手工追加 Q2、QA masks、`style-guide`、未绑定产品图、被拒绝候选或无 accepted 回执链图片；
- 原始 projection evidence 仅 QA，不发送。

## `interior.imagegen-request.v4`

由 `build_imagegen_request.py` 编译。请求提示词包含精简 scene facts v4 和 render context facts v4；完整场景事实保留在 JSON，提示词 UTF-8 长度不得超过 32KB。任何人工前后缀都会改变 digest 并被拒绝。槽位引导附件只包含 Q1 和计划声明的身份/产品参考。

## `interior.imagegen-batch-plan.v1`

由 `build_imagegen_batch_plan.py` 从 render plan 与各 shot request 编译。每个 job 保存 `jobId/shotId/requestPath/requestSha256/dependsOnJobIds/outputFile/maxAttempts`；独立 shot 进入同一 batch，共享空间或槽位的 shot 依赖已 accepted 主图。依赖 job 可在上游成功后再用编排器 `bind-request` 固定最终请求。`maxConcurrency` 只允许 `1..5`，默认 `5`；它控制远端 ImageGen job，不控制本机 Chrome/Blender/CAD 截图。

## `interior.imagegen-receipt.v4`

绑定 request digest、generation invocation、供应商 request ID、全部附件 `(role, referenceId, sha256)` 和唯一输出图片。

## `imagegen.batch-receipt.v1`

由 `imagegen-batch-orchestrator` 完成。每个 job 独立持久化 queued/running/succeeded/failed 状态、尝试次数、开始结束时间、提供方请求 ID 和输出 SHA-256；批次使用 all-settled 语义，兄弟 job 失败不得删除已成功输出。

## `interior.render-agent-review.v4`

必须由不同 invocation 完成，逐项枚举房间、连接、结构、槽位、边界、允许新增项和禁有项。每个槽位都要确认与 scene map JSON 的身份、位置和朝向一致；Q2 只用于辅助人工比对，不是默认生成输入。

`measuredProjectionAudit` 必须使用 `complete-scene-map-region-correspondence-v1`，并完整提供：

- 每个 `placementSlot` 的 `objectCenterPairs` 与 `objectRegionPairs`；
- 每个覆盖率不低于 `1%` 且锁定朝向槽位的 `orientationLinePairs`；
- 每个 `structure` 的 `structureRegionPairs`；
- 每个 `connection` 的 `connectionRegionPairs`；
- scene map 全量对象、结构、开口数量以及 source/render 可见房间集合；
- 由上述完整集合重算的五项最大误差。

源区域必须与 scene map 完全一致，ID 不得遗漏、重复或删除失败项。对象中心最大误差 `<=0.02`，对象区域任一边最大误差 `<=0.025`，对象朝向最大误差 `<=3°`，结构和连接区域任一边最大误差 `<=0.02`。

`cameraComparison` 至少提供四组 source/render 归一化关键点，并为 scene map 中覆盖率不低于 `2%` 的每个主要结构提供一条绑定 `structureId` 的墙线。验证器采用关键点最大误差而非中位数；要求最大位置误差 `<=0.02`、墙线最大角度误差 `<=1°`。

## `interior.render-four-quadrant-evidence.v1`

由 `build_four_quadrant_delivery.py` 在 review accepted 后生成：

1. `q1-pure-concrete-structure-camera`；
2. `q2-furnished-same-camera-reference`；
3. `q3-plan-camera-frustum`；
4. `q4-accepted-render`。

evidence 绑定 scene/request/receipt/review、render producer 及每个象限的路径和哈希；输出固定 `1920x1200`。Q4 必须等于 receipt 输出。

`planned`、`candidate`、`rejected`、只有 Q1-Q3、只有效果图而没有 evidence，或只有原生模型截图的状态都不是完成状态。任何文案或 Agent 自报都不能替代 `--require-complete` 的成功结果。

## 唯一链路

```text
shot-scene-map.v9
  -> render-plan.v11 + space-reference-plan.v1
  -> render-media-context.v7
  -> imagegen-prompt-manifest.v7
  -> imagegen-request.v4
  -> imagegen-batch-plan.v1 -> imagegen-batch-orchestrator
  -> imagegen-receipt.v4 + imagegen.batch-receipt.v1
  -> render-agent-review.v4
  -> render-four-quadrant-evidence.v1
```
