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

## 拍摄范围

- 默认不声明 `captureScope` 时，`roomCoverage` 覆盖结构中的全部空间。
- 用户只要求部分空间时，声明 `captureScope.mode=requested-room-subset`；`requestedRoomIds` 是本轮必须生成正视主图的空间，`allowedContextRoomIds` 只能列出模型 scope 允许且源拓扑连通、可能真实进入画面的相邻空间，`excludedRoomIds` 列出其余空间，并记录非空 `reason`。
- 三组 ID 必须无重叠地覆盖全部结构空间，并与 `native-model-manifest.modelScope` 完全一致。子集拍摄不删除、不改写未拍空间，只约束同模板运行时可见范围。验证器仍拒绝未知空间、遗漏目标空间、排除空间曝光及目标范围外的偷偷加拍。



## `interior.circulation-result.v2`

找机位前必须读取由 `interior-circulation-planning` 生成的结果。固定要求：

- `floorplanId` 与原生模型清单一致。
- `modelBackend` 与原生模型清单一致。
- `verdict.accepted=true`。
- `verdict.cameraWorkflowAllowed=true`。
- `verdict.structuralMutationPerformed=false`。
- `classification.layoutRegressionCount=0`。
- `classification.inputIntegrityErrorCount=0`。
- `bindings.nativeModelSha256` 与清单及磁盘原生模型完全一致。
- `bindings.handoffDigestSha256` 与清单一致。
- `resultDigestSha256` canonical 校验通过。

模型或布局状态变化后必须重新执行动线 Skill，不能更新 result 字段冒充重审。

## `interior.native-model-manifest.v1`

三个建模 Skill 都必须导出同一外层合同：

```json
{
  "schema": "interior.native-model-manifest.v1",
  "modelBackend": "html-threejs | blender | cad-step",
  "floorplanId": "example-home",
  "handoffDigestSha256": "...",
  "modelScope": {
    "schema": "interior.model-scope.v1",
    "mode": "room-subset",
    "requestedRoomIds": ["living"],
    "allowedContextRoomIds": ["dining"],
    "excludedRoomIds": ["bedroom"],
    "sameTemplateAsWholeFloor": true,
    "customProjectGeometryAllowed": false,
    "bindings": {"floorplanId": "example-home", "handoffDigestSha256": "...", "structureDataSha256": "..."},
    "scopeDigestSha256": "..."
  },
  "nativeModel": {"path": "...", "sha256": "...", "format": "..."},
  "coordinateTransform": {"cameraCoordinateSystem": "interior-world-y-up.v1"},
  "capabilities": {
    "raycast": true,
    "depth": true,
    "entityId": true,
    "visibilityStates": true,
    "nativeCameraRender": true
  },
  "captureAdapter": {
    "script": "...",
    "interface": "interior.native-capture-adapter.v1"
  },
  "validation": {"accepted": true, "primitiveFurnitureFallbackCount": 0}
}
```

HTML 后端必须提供有效 `modelScope`。`whole-floor` 覆盖全部房间；`room-subset` 必须证明与整屋共用模板和编译链，且其 digest、handoff 与 structure 绑定有效。Blender/CAD 在升级到该合同前可按完整整屋处理，但不得伪造局部模型范围。

`nativeModel.sha256` 是后续 plan、capture、semantic frame 和 scene map 的共同版本键。派生 GLB 不可取代 `.blend` 或 STEP 的原生模型身份。

能力按后端分型：HTML/Blender 必须有 `raycast/depth/entityId/visibilityStates/nativeCameraRender=true`；CAD 必须有 `visibilityStates/nativeCameraRender=true`、`projectionProfile=cad-same-brep-topology-zbuffer-v1` 和哈希锁定的 `semanticTopology`。CAD Snapshot 未输出的 `depth/entityId` 必须为 `false`。CAD 的 semantic frame 只有在同一 STEP 自动派生的 occurrence 拓扑、同一相机和同一显隐基线上执行 Z-buffer 并通过遮罩验收后才成立。

## `interior.camera-frontal-seed-set.v1`

任何原生候选截图前必须由 `solve_frontal_camera_seeds.py` 生成。输入固定为结构 v3、当前动线 scene/result v2 和当前原生模型 manifest；输出必须绑定 `floorplanId`、handoff digest、`sourceModelSha256` 与 circulation result digest。

```json
{
  "schema": "interior.camera-frontal-seed-set.v1",
  "methodVersion": "deterministic-wall-normal-camera-v7",
  "captureScope": {"mode": "requested-room-subset", "requestedRoomIds": ["living"]},
  "seeds": [
    {
      "frontalSeedId": "frontal::living",
      "roomId": "living",
      "composition": "one-point-frontal",
      "anchorElementIds": ["sofa-01"],
      "referenceWallId": "wall-north",
      "position": [0, 1.25, 1.72],
      "target": [0, 1.25, -3]
    }
  ],
  "seedSetDigestSha256": "..."
}
```

`captureScope` 中每个空间恰好一个 seed；多一个、少一个、手写种子、关系镜头替代正视种子，或任何身份绑定不一致都必须拒绝。算法使用功能类别优先级、已接受的贴墙关系、真实相邻墙距离、墙长和 ID 进行稳定排序。同一输入重复运行必须产生相同 canonical digest，不需要用户确认。

## `interior.native-camera-envelope-measurements.v1`

原生后端一次读取每个 seed 的锚定物、参考立面和上下文 OBB 八角点包围盒，并沿参考墙法向计算可后退深度。一个空间只能有一条与当前 seed 精确绑定的 measurement；元素 ID、模型哈希或 seed digest 不一致时停止。该文件只保存原生测量事实，不允许手工填写候选相机。

## `interior.camera-candidate-batch.v1`

`compile_camera_candidates.py` 一次消费完整 seed set 和原生测量，按固定占画比与焦段顺序生成所有空间的正视候选。每个空间固定先用第一条可容纳候选，只有其原生投影失败时才允许查看下一条回退候选。`camera-plan.v8.candidateCompilation` 必须绑定该批次文件、文件哈希和 canonical digest；最终验证器会用原 seed 和 measurement 重新执行编译并逐字段比对，不能修改批次 JSON 冒充算法结果。

## `interior.camera-plan.v8`

顶层固定字段：

```json
{
  "schemaVersion": "8.0",
  "schema": "interior.camera-plan.v8",
  "methodVersion": "deterministic-wall-normal-camera-v7",
  "coordinateSystem": "interior-world-y-up.v1",
  "modelBackend": "blender",
  "sourceModelSha256": "...",
  "floorplanId": "example-home",
  "planPhase": "final-selection",
  "frontalSeedSet": {
    "path": "camera-frontal-seeds.json",
    "sha256": "...",
    "seedSetDigestSha256": "..."
  },
  "candidateCompilation": {
    "path": "camera-candidate-batch.json",
    "sha256": "...",
    "batchDigestSha256": "..."
  }
}
```

每个 selected shot 必须重复 `modelBackend/sourceModelSha256`，并包含：

- 扁平 `position/target/focalLengthMm/fov`，供三种适配器共同读取。
- 显式 `cameraHostRoomId`；验证器必须确认相机平面坐标落在该空间多边形内，且该空间与被摄空间在冻结连接图中连通。
- `framing.envelopes.anchor/referenceFacade/context`。
- `measurementBasis=native-model-obb-eight-corners`。
- `availableDepthMeters` 必须由 `cameraHostRoomId` 的冻结多边形与目标到相机射线重算，禁止 Agent 手填或借用其它空间深度。
- 固定 5% 距离安全量。
- `projectionAudit.frameMargins/depthScaleRatio/foregroundBlockerShare/mustShowComplete`。
- 主图固定 `role=primary`、`composition=one-point-frontal`，并通过 `frontalSeedId` 绑定当前空间唯一 seed。
- 主图的 `frontalAlignment`。
- 只隐藏局部射线遮挡物的 `visibility`。

每个 `candidateGroup` 必须从对应正视 seed 确定性派生并保存固定候选顺序，以及 `1` 张主候选或“主候选失败 + `1` 张回退候选”的当前后端原生预览。主候选投影通过后禁止继续试拍：

```json
{
  "candidateAudit": {
    "modelBackend": "blender",
    "sourceModelSha256": "...",
    "selectionMethod": "deterministic-first-fitting-with-one-bounded-fallback",
    "orderedFittingCandidateIds": ["living-o80-f35", "living-o80-f32"],
    "selectedCandidateId": "living-o80-f35",
    "nativePreviewEvidence": [
      {
        "candidateId": "living-o80-f35",
        "imagePath": "...",
        "imageSha256": "...",
        "cameraEvidencePath": "...camera-plan-evidence.json",
        "cameraEvidenceSha256": "...",
        "projectionAccepted": true,
        "failureCodes": [],
        "modelBackend": "blender",
        "sourceModelSha256": "..."
      }
    ]
  }
}
```

每条候选截图必须绑定同一次原生截图产生的 `interior.camera-plan-evidence.v2`。最终门禁会回读该文件，并把 `shotId`、后端、原生模型哈希、相机位置、目标点和焦段与 selected shot 逐项比对；只给图片或复用其它机位的证据不能通过。

### 正视硬门限

`frontalAlignment.tolerances` 必须原样为：

```json
{
  "yawErrorDeg": 1.0,
  "pitchAbsDeg": 0.25,
  "rollAbsDeg": 0.1,
  "alignmentResidualDeg": 0.25
}
```

其它固定门限：四边边距 `≥0.06`、左右边距差 `≤0.03`、前景遮挡 `≤0.08`、`depthScaleRatio≤1.18`、`mustShowComplete=true`。

## `interior.native-capture-result.v1`

统一调度器调用原生适配器后产出：

```json
{
  "schema": "interior.native-capture-result.v1",
  "modelBackend": "cad-step",
  "sourceModelSha256": "...",
  "coordinateSystem": "interior-world-y-up.v1",
  "accepted": true,
  "records": [],
  "formalCaptureDispatcher": {
    "cameraPlanValidated": true,
    "resourceGateApplied": true,
    "globalScreenshotConcurrencyLimit": 2,
    "slot": {"slot": 1, "pid": 1234}
  },
  "dispatcherResourceEvidence": {
    "beforeAdapter": {},
    "afterAdapter": {}
  }
}
```

正式结果必须由 `capture_model_views.py` 回填 dispatcher 和压力证据。真实截图直接来自后端适配器、并发上限不是 `2`、缺前后设备压力，或同一 HTML 作业启动多个 Chrome，都不是 accepted 正式截图。

Blender 和 CAD 在自身 `Z-up` 坐标中截图，但记录必须同时保留 canonical/native camera；HTML 直接使用 canonical camera。所有转换必须由各后端适配器唯一实现。

## `interior.scene-semantic-frame.v4`

由所选后端原生截图链直接导出：

```json
{
  "schema": "interior.scene-semantic-frame.v4",
  "modelBackend": "html-threejs",
  "sourceModelSha256": "...",
  "floorplanId": "example-home",
  "shotId": "living-frontal",
  "coordinateSystem": "image-top-left-normalized",
  "guidanceImages": {
    "slotGuided": "living.slot-guided.png",
    "furnishedQa": "living.furnished-qa.png"
  }
}
```

允许的投影事实源只有：

- HTML：`same-camera-gpu-entity-id-plus-depth-to-room-polygon`
- Blender：`blender-native-object-index-plus-depth-to-room-polygon`，由 Blender 原生 `IndexOB`、同机位 Depth 和冻结空间多边形组成；同一实体的全部可渲染子物体共享 `pass_index`，不做截图后二次识图。
- CAD：`cad-same-brep-topology-zbuffer-to-room-polygon`；每个语义像素来自同 STEP occurrence 拓扑在同相机下的最近可见三角形，不做截图颜色差分或二次识别

`entities[]`、`rooms[]`、`connections[]` 必须由当前原生 ID/Depth 与冻结模型事实生成，不做截图二次识别。`connections[].screen` 先要求 `source=front-clipped-projected-model-opening-corners` 和 `visibilityEvidence.allCornersInFrontOfCamera=true`；任一洞口角点不在相机前方时，该连接不得进入当前帧。随后必须把归一化洞口多边形映射到当前原生 Entity-ID 图，记录语义图尺寸、栅格多边形、采样像素数、墙体遮挡像素数和比例。采样少于 `64px` 或墙体遮挡率超过 `15%` 时，该连接必须从当前画面排除。

## `interior.shot-scene-map.v9`

由 `build_shot_scene_map.py` 从 semantic frame 单向编译：

```json
{
  "schema": "interior.shot-scene-map.v9",
  "modelBackend": "html-threejs",
  "sourceModelSha256": "...",
  "guidance": {
    "defaultMode": "slot-guided",
    "availableModes": ["slot-guided"],
    "selectionOwner": "interior-space-rendering/render-plan.v11"
  }
}
```

scene map 不含 `sendToImageModel`，也不选择模式。`cameraPlanEvidence` 只做机位证据，不发送给图像模型；其 JSON 固定为 `interior.camera-plan-evidence.v2`、`source=same-native-model-camera-state`。

`visibleFrame` 由 `assets/view-visibility-policy.v1.json` 唯一计算。主空间、包含可见功能对象的空间以及达到统一可读像素阈值的空间可以进入；相机后方、画外、遮挡和不可读边缘碎片必须排除。连接只有在所有室内端点均已进入可见空间集合、具备完整前向投影证据且通过 Entity-ID 开口遮挡审计时才能进入。Room mask 必须同步滤除 excluded room 颜色。

`visibleFrame.decisions` 只能保留 `included=true` 的提示词事实；结构 `roomIds` 必须是源归属与 `visibleRoomIds` 的非空交集，槽位必须归属唯一可见房间。完整 included/excluded 决策和开口像素审计写入运行时 `interior.shot-visibility-audit.v1`，其 asset role 固定为 `qa-only-never-submit-to-image-model`。该 QA 文件不得进入 render context、prompt manifest、image attachment 或 JSON prompt block。

`guidance.fourQuadrantContract` 固定为 Q1 无组件、无槽位覆盖的纯水泥结构图，Q2 同一水泥墙地面且同模型同机位的家具柜体 QA 图，Q3 平面相机与视锥，Q4 accepted image-generated render。默认槽位引导只把 Q1 与 scene/context JSON 提交给图像模型；Q2 和 masks 不提交。四张图必须绑定同一 `shotId/sourceModelSha256/camera`；禁止用四张效果图、四张机位图或原生三维截图代替 Q4。

scene map 必须同时打包当前 `camera-plan.v8`，并写入 `nativeProjectionAudit`。生成器从原生 semantic frame 逐一查找 `framing.envelopes.anchor.elementIds` 和 `mustShowElements`；任一必显对象缺失、anchor 被裁切或任一边距小于 `6%` 时停止。验证器必须回读已打包 plan 和同帧 semantic frame 重新计算，不能采信 plan 中自报的 `mustShowComplete`。

### `closedWorldView`

该对象把当前镜头定义为封闭集合：

```json
{
  "schema": "interior.closed-world-view.v1",
  "required": {
    "roomIds": ["living"],
    "connectionIds": ["connection-entry-exterior"],
    "structureIds": ["wall-north", "window-west"],
    "placementSlotIds": ["sofa-01", "dining-table-01"],
    "placementSlotInventory": [
      {"slotId": "sofa-01", "functionalClass": "sofa", "quantity": 1, "roomId": "living"}
    ]
  },
  "boundaryTerminations": [
    {
      "connectionId": "connection-entry-exterior",
      "farSide": "exterior",
      "allowedDepictions": ["closed-existing-door-leaf", "open-existing-door-to-exterior"]
    }
  ]
}
```

- 四个 required 集合必须与 scene map 的房间、连接、结构和槽位数组完全相等；空集合具有明确的“一个也没有”语义。
- Q1 隐藏组件且不画槽位轮廓；`placementSlots[]` 仍逐件保存世界位置、占地、朝向、局部轴和图像区域，`placementRelations[]` 保存朝向目标、贴墙、接触和组合关系。`placementSlotInventory` 只保存封闭世界索引，不允许合并餐桌椅或遗漏相邻可见空间的家具。
- 未列出的房间、结构、门窗通道、家具柜体、家电洁具全部禁止出现。
- 与 `exterior` 相连的连接必须具有有限终止表现，禁止画成另一个室内房间。
- 可新增类别仅从 `assets/closed-world-view-policy.v1.json` 读取；策略只允许非结构饰品、挂画、灯饰、非结构吊顶细节和软装配饰。

### 槽位锁定范围

`slot-guided` 下，所有家具/柜体槽位都锁定位置、占地、方向、类别和通行净距。柜体白模造型不是默认形状权威：

```json
{
  "slotLock": {
    "position": true,
    "footprint": true,
    "orientation": true,
    "category": true,
    "clearance": true
  }
}
```

唯一生成模式为 `slot-guided`。Q1 隐藏组件且不画槽位覆盖，完整布局只由 JSON 表达；Q2 家具图只用于 QA，不能提交给图像模型。指定产品通过逐槽位产品参考绑定，不把整张白模提升为形状权威。本链不接受其它模式、别名或自动切换。

## 最终 review

`validate_shot_scene_map.py ... --final` 要求 `scene-map-agent-review.v2` 精确枚举全部 observed 房间、连接、结构和槽位，四类 unexpected 列表为空，并明确写入 `closedWorldContractAccepted=true`。复核 invocation 必须与源截图 invocation 不同。
