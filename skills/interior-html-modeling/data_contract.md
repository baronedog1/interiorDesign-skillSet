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



## 上游唯一入口

正式项目必须先导入 `interior.floorplan-handoff.v3`。下表是推荐位置；实际文件可位于任务工作区其它目录，由语义发现记录真实路径：

| 文件 | 作用 |
|---|---|
| `floorplan-handoff/floorplan-handoff.json` | 第一 Skill 的完整自包含事实包及逐文件哈希 |
| `floorplan-import-receipt.json` | 本 Skill 导入器记录的 handoff 摘要、结构/组件哈希和 importer 版本 |

根目录 `structure-data.json`、`trace-components.json` 是上述 handoff 的运行时物化副本，不是新的事实源，必须与 manifest 哈希相同。组件匹配以后产生的 `component-layout.json` 是本 Skill 的下游派生事实。

禁止直接提交裸结构 JSON，也禁止以文件名、项目目录名、`confirmed-version` 或人工布尔值代替 handoff 复验。
导入器必须接收第一 Skill 正式 manifest 语义上完整的 artifact 集合，包括墙与开口、房名与
非墙分界、对象三组干净叠图及三组编号复核图。角色名有唯一的一字符笔误可归一化，额外产物允许保留；真正缺少必需语义或出现内容冲突时才停止并询问用户。

## `interior.model-scope-request.v1` 与 `interior.model-scope.v1`

整屋和单空间使用同一 handoff 与同一 HTML 编译器。整屋调用不需要 request，importer 自动生成 `mode=whole-floor` 的 scope。单空间调用只允许提交：

```json
{
  "schema": "interior.model-scope-request.v1",
  "mode": "room-subset",
  "requestedRoomIds": ["living"],
  "allowedContextRoomIds": ["dining"],
  "reason": "只交付客厅，餐厅是该机位真实可见的相邻空间"
}
```

importer 将其编译为 `interior.model-scope.v1`，并确定性补齐 `excludedRoomIds`、handoff/structure 绑定和 digest。`requestedRoomIds` 是需要建模、动线和正视主机位的空间；`allowedContextRoomIds` 只能是源拓扑真实连通且可能进入画面的相邻空间；三组 ID 必须无重叠地覆盖来源结构全部房间。

`sameTemplateAsWholeFloor=true`、`customProjectGeometryAllowed=false` 是硬合同。单空间运行时只显示主空间与允许上下文，但仍调用同一 `base-floorplan-template`、组件匹配器、资产库、碰撞、场景和截图适配器；禁止项目脚本、临时 primitive、手写墙体或第二份局部结构事实。

## 五个项目文件

| 文件 | Schema | 唯一职责 |
|---|---|---|
| `structure-data.json` | `interior.floorplan-structure.v3` | 墙、窗、房间、可通行连接、非墙空间分界、有效边界、尺寸和图层 |
| `trace-components.json` | `interior.trace-components.v2` | 上游每个绿色/紫色对象的位置、尺寸、方向与归一化轮廓事实 |
| `component-layout.json` | `interior.component-layout.v4` | 分库匹配结果、轮廓哈希、尺度策略、形态参数和项目 placement |
| `scene-rig.json` | `interior.scene-rig.v1` | HTML 内可编辑光源、场景摄像头及辅助标记状态 |
| `model-scope.json` | `interior.model-scope.v1` | 整屋或单空间的主空间、允许上下文、排除空间及唯一编译器绑定 |

`structure-data.json` 禁止包含 `furnitureCatalog` 或 `furniturePlacements`。组件定义只存在于 Skill 的两个物理分库。`model-scope.json` 只控制同一结构的运行范围，不能携带墙、门窗、连接或组件副本。

## 结构合同

```json
{
  "schema": "interior.floorplan-structure.v3",
  "floorplanId": "floorplan-project-001",
  "name": "项目白模",
  "source": {
    "kind": "compiled-floorplan-handoff",
    "image": "structure-source.png",
    "traceSpec": "trace-spec.json"
  },
  "coordinateSystem": {
    "units": "m",
    "origin": "north-west",
    "realWidthMeters": 8,
    "realDepthMeters": 6,
    "defaultWallHeightMeters": 2.8
  },
  "dimensionAnnotations": {
    "widthMeters": 8,
    "depthMeters": 6,
    "widthLabel": "总宽",
    "depthLabel": "总深"
  },
  "floorBoundary": [[0, 0], [8, 0], [8, 6], [0, 6]],
  "rooms": [
    {
      "id": "living",
      "name": "客厅",
      "spaceType": "living",
      "topologyClass": "open-zone",
      "polygon": [[0, 0], [4, 0], [4, 3], [0, 3]],
      "labelPosition": [2, 1.5],
      "areaM2": 12
    },
    {
      "id": "balcony",
      "name": "阳台",
      "spaceType": "balcony",
      "topologyClass": "attached",
      "polygon": [[0, 3], [4, 3], [4, 6], [0, 6]],
      "labelPosition": [2, 4.5],
      "areaM2": 12
    }
  ],
  "walls": [
    {
      "id": "wall-north",
      "name": "北侧外墙",
      "start": [0, 0],
      "end": [8, 0],
      "thickness": 0.24,
      "height": 2.8,
      "type": "external",
      "adjacentRoomIds": ["exterior", "living"],
      "sourceTraceIds": ["red-north"]
    }
  ],
  "windows": [
    {
      "id": "window-living",
      "name": "客厅窗",
      "wallId": "wall-north",
      "offset": 2,
      "width": 2.2,
      "sill": 0.72,
      "openingHeight": 1.65,
      "kind": "standard",
      "frameDepth": 0.08,
      "sourceTraceIds": ["blue-living"]
    }
  ],
  "connections": [
    {
      "id": "opening-living-balcony",
      "fromRoomId": "living",
      "toRoomId": "balcony",
      "kind": "open-passage",
      "start": [1.2, 3],
      "end": [3.6, 3],
      "bottom": 0,
      "height": 2.55,
      "sourceTraceIds": [],
      "sourceDividerIds": ["candidate-divider-living-balcony"]
    }
  ],
  "topology": {
    "method": "wall-mask-opening-closure-space-seed",
    "interiorPixels": 120000,
    "assignedInteriorPixels": 120000,
    "spaceSeedCount": 2,
    "roomCount": 2,
    "mergedSeedGroups": [],
    "unassignedRegionCount": 0,
    "orphanWallIds": [],
    "openingEndpointMismatches": []
  },
  "layers": {
    "walls": true,
    "windows": true,
    "fixedFixtures": true,
    "movableFurniture": true,
    "grid": true,
    "annotations": false
  }
}
```

### 结构约束

- 单位为米，原点在西北角，`x` 向东、`z` 向南。
- `structure-data.json` 只能由第一 Skill 的 finalizer 生成；本 Skill 不接收或维护手写结构副本。
- 墙使用中心线 `start/end`、真实 `thickness` 和 `height`。
- 每面墙和窗保留非空 `sourceTraceIds`。
- 每面墙的 `adjacentRoomIds` 由上游拓扑编译器产生，至少包含两个不同的已知房间/`exterior`，且至少一侧是实际房间；同一房间位于墙两侧即为假墙。
- 每个窗绑定已存在 `wallId`；洞口不越墙、不重叠。
- 每条 `connections[]` 绑定两个真实空间或一个空间与 `exterior`。物理门窗通道保留非空 `sourceTraceIds`；无实体墨线的开放功能连接保留非空 `sourceDividerIds`。二者必须且只能有一个；`start/end/bottom/height` 是后续相邻空间投影的唯一连接体。
- `semanticDividers[]` 逐项保存上游编译的 `sourceDividerId/roomIds/traversal/start/end`。`traversal=open-passage` 必须绑定同源连接；`boundary-only` 禁止绑定连接。两类分界都影响房间 polygon、面积和标注边界，但都不生成墙或门。本 Skill 不得在该只读数组增加显示字段。
- 带 `sourceDividerIds` 的连接只能是 `open-passage`；`boundary-only` 永远不进入 `connections[]`。
- 多房间模型中的每个房间必须沿 `connections[]` 到达有证据的外部入口；HTML 和机位 Skill 禁止根据家具、房名或像素空白补关系。
- `bedroom/bathroom/study/closet/storage` 固定属于 `enclosed`，且至少有一个 `door` 或 `sliding-door`；`open-passage` 不能替代封闭空间的门。
- `floorBoundary` 只含有效室内地面，不含户型外留空。
- `rooms[].polygon` 是房间地板、面积、标注高亮和边界墙段归属的唯一空间几何；`spaceType` 使用上游受控空间类型，`topologyClass` 只允许 `enclosed/open-zone/circulation/attached`，`areaM2` 来自上游净地面像素。贴外墙房间与 `floorBoundary` 使用上游编译出的共享边和共享顶点；共享边上的点属于户型内部，本 Skill 不缩小、平移或重新拟合房间边界。
- `topology` 必须与 handoff 唯一源模型报告完全相等；室内像素全部分配，空间种子数等于房间数，合并种子、无人认领区域、同空间假墙和错误开口端点均为空。
- 标注模式只读取 `rooms[].polygon/name/areaM2` 绘制虚线边界、文字和悬停高亮，不进行截图识别，也不维护第二套房间坐标。

## 描线对象合同

```json
{
  "schema": "interior.trace-components.v2",
  "floorplanId": "floorplan-project-001",
  "coordinateSystem": "plan-meters-north-west",
  "objects": [
    {
      "traceId": "green-living-sofa",
      "sourceObjectCandidateId": "candidate-object-living-sofa",
      "name": "三人位沙发",
      "semantic": "movable-green",
      "shapeClass": "rectilinear",
      "bbox": {"width": 2.22, "depth": 0.94},
      "center": [2.2, 2.1],
      "rotationY": 0,
      "roomId": "living",
      "typeHint": "三人位沙发",
      "categoryHint": "沙发与躺卧",
      "keywords": ["沙发", "三人"],
      "componentHint": "sofa-three-seat",
      "shapeEvidence": {
        "coordinateSpace": "bbox-normalized",
        "outlineSource": "classified-green-code-trace",
        "outline": [[0, 0], [1, 0], [1, 1], [0, 1]],
        "curveEdgeRatio": 0,
        "handedness": "none"
      }
    }
  ]
}
```

约束：

- `traceId` 与 `sourceObjectCandidateId` 都唯一稳定；后者必须属于 handoff
  `sourceTraceRegistry.sourceObjectCandidateIds`，且与第一 Skill accepted 对象一对一。
- `semantic` 只能是 `movable-green` 或 `fixed-purple`。
- `shapeClass` 使用组件库已有形态，但不能独立作为形状证据。
- `bbox`、`center` 和 `rotationY` 是米制描线事实。
- `shapeEvidence.outline` 必须是从同一绿色/紫色代码描线提取的包围盒归一化闭合轮廓；禁止用组件库轮廓反向伪造来源。
- `shapeEvidence.outlineSource` 必须指向本轮代码描线来源，`coordinateSpace` 固定为 `bbox-normalized`。
- `curveEdgeRatio` 记录曲线边占比；`handedness` 记录 L 形等非对称对象的左右手性。
- 圆形、曲面和有机形轮廓至少 12 个采样点且 `curveEdgeRatio >= 0.35`；L/U 形必须保留凹角，L 形必须保留手性。
- `componentHint` 仅在原型已确认时填写；它仍受颜色分库、形态和缩放约束。
- 类型不确定时保留未解决，不写默认组件。

## 两个组件分库合同

```text
movable-green -> assets/component-library/movable-green/catalog.js
fixed-purple  -> assets/component-library/fixed-purple/catalog.js
```

每个组件定义包含：

```json
{
  "id": "sofa-three-seat",
  "name": "三人位沙发",
  "category": "sofa",
  "placementClass": "movable-green",
  "shapeClass": "rectilinear",
  "builder": "external-gltf",
  "variant": "sofa_04",
  "defaultDimensions": {"width": 2.08, "depth": 0.96, "height": 0.90},
  "uniformScaleRange": {"min": 0.72, "max": 1.35},
  "lockAspectRatio": true,
  "appearance": "dual-white-source-color",
  "appearanceVariants": ["white-model", "source-color"],
  "sourceLicense": "CC0-1.0",
  "sourceUrl": "https://polyhaven.com/a/sofa_04",
  "licenseEvidence": {"status": "provider-direct-confirmed"},
  "researchOnly": false,
  "commercialUseAllowed": true,
  "commercialReviewRequired": false,
  "seatingCapacity": 3,
  "mountType": "floor",
  "styleCompatibility": ["现代"],
  "useCaseTags": ["客厅", "三人位"],
  "tags": ["沙发", "sofa_multi", "现代", "客厅", "三人位"],
  "editorCapabilities": {"scaleMode": "uniform-only"}
}
```

加载后由分库合同补充：

```json
{
  "libraryPartition": "movable-green",
  "libraryDirectory": "movable-green"
}
```

两个运行目录必须与 `catalog/public-assets.json` 的 ID 集合完全一致。全部条目必须满足 `builder=external-gltf`、`geometryProfile=authored-gltf-pbr-v2`、`primitiveBoxOnly=false`、明确尺度策略和白模/源色双状态。默认 `uniform-only`；只有经审核的直线柜体可声明 `axis-limited` 及宽深高范围。二进制 SHA-256 只在受管 asset-store receipt/inventory 与项目 `component-assets.lock.json` 中维护；catalog 不保存第二份可漂移下载状态。

## 组件布局合同

```json
{
  "schema": "interior.component-layout.v4",
  "libraryVersion": "5.0.0",
  "source": {
    "traceSpec": "trace-components.json",
    "sourceObjectCandidateIds": ["candidate-object-living-sofa"],
    "movableGreenCount": 1,
    "fixedPurpleCount": 0,
    "removedSourceTraceIds": [],
    "libraryPartitions": {
      "movable-green": "component-library/movable-green",
      "fixed-purple": "component-library/fixed-purple"
    }
  },
  "matches": [
    {
      "sourceTraceId": "green-living-sofa",
      "sourceObjectCandidateId": "candidate-object-living-sofa",
      "sourceName": "三人位沙发",
      "semantic": "movable-green",
      "sourceShapeClass": "rectilinear",
      "componentId": "sofa-three-seat",
      "componentName": "三人位沙发",
      "libraryPartition": "movable-green",
      "libraryDirectory": "movable-green",
      "matchMethod": "explicit-proportional-source-route",
      "score": 18,
      "uniformScale": 1,
      "evidence": {
        "shapeClassExact": true,
        "semanticExact": true,
        "targetFootprintExact": true,
        "authoredGeometryScalePolicy": "uniform-only",
        "proportionalScaleSpread": 0.08,
        "targetWidth": 2.22,
        "targetDepth": 0.94,
        "outlineBoundToCollisionFootprint": true,
        "sourceOutlineHash": "<sha256>",
        "sourceOutlinePointCount": 4,
        "outlineSource": "classified-green-code-trace",
        "sourceShapeMetrics": {
          "area": 1,
          "perimeter": 4,
          "circularity": 0.785398,
          "concavityCount": 0,
          "curveEdgeRatio": 0,
          "handedness": "none"
        },
        "traceReshape": {
          "mode": "proportional-authored-model-with-trace-footprint",
          "widthScaleFromPrototype": 1,
          "depthScaleFromPrototype": 1,
          "rawUniformScale": 1,
          "builderUniformScale": 1
        }
      }
    }
  ],
  "placements": [
    {
      "id": "component-green-living-sofa",
      "name": "三人位沙发",
      "componentId": "sofa-three-seat",
      "sourceTraceId": "green-living-sofa",
      "sourceObjectCandidateId": "candidate-object-living-sofa",
      "semantic": "movable-green",
      "libraryPartition": "movable-green",
      "libraryDirectory": "movable-green",
      "roomId": "living",
      "position": [2.2, 2.1],
      "rotationY": 0,
      "uniformScale": 1,
      "targetDimensions": {"width": 2.22, "depth": 0.94},
      "sourcePosition": [2.2, 2.1],
      "sourceRotationY": 0,
      "sourceDimensions": {"width": 2.22, "depth": 0.94},
      "sourceShapeEvidence": {
        "coordinateSpace": "bbox-normalized",
        "outlineSource": "classified-green-code-trace",
        "outline": [[0, 0], [1, 0], [1, 1], [0, 1]],
        "curveEdgeRatio": 0,
        "handedness": "none"
      },
      "sourceShapeMetrics": {
        "outlineHash": "<sha256>",
        "area": 1,
        "perimeter": 4,
        "circularity": 0.785398,
        "concavityCount": 0,
        "curveEdgeRatio": 0,
        "handedness": "none"
      },
      "shapeAdjustments": {
        "curveRatio": 0,
        "arcRadians": 0,
        "concavityCount": 0,
        "handedness": "none"
      },
      "traceReshape": {
        "mode": "proportional-authored-model-with-trace-footprint",
        "widthScaleFromPrototype": 1,
        "depthScaleFromPrototype": 1,
        "rawUniformScale": 1,
        "builderUniformScale": 1
      },
      "traceLock": {
        "position": true,
        "dimensions": true,
        "rotation": true,
        "outline": true,
        "source": "classified-second-quadrant"
      },
      "collisionTolerance": 0.006
    }
  ],
  "relationHints": {
    "schema": "interior.layout-relation-hints.v2",
    "directionalAxes": [
      {
        "assetId": "dining-chair",
        "role": "front",
        "localAxis": "+Z",
        "evidence": "browser-reviewed-authored-model"
      }
    ],
    "facing": [],
    "wallAttachment": [],
    "allowedContacts": [],
    "spaceDividerMarkers": []
  }
}
```

### 数量与路由等式

```text
movableGreenCount + fixedPurpleCount
= matches.length
= source placements.length + removedSourceTraceIds.length
= unique sourceTraceId count
= unique sourceObjectCandidateId count
```

初始编译时 `removedSourceTraceIds` 必须为空。用户在组件页显式删除对象后，保留原
match，并把其 `sourceTraceId` 移入该数组；不得改写上游绿色/紫色来源数量或
`sourceObjectCandidateIds`。每个 match 和 placement 必须保留完全相同的
`sourceObjectCandidateId`；每个活跃 placement 必须满足：

```text
semantic
= libraryPartition
= component.placementClass
```

`libraryDirectory` 必须与该语义的物理目录一致。任何 match 出现 `fallback` 字段即失败。允许的匹配方法只有 `explicit-proportional-source-route` 和 `semantic-shape-proportional-source-score`。

用户明确要求补齐、且原图没有清晰描线证据的功能对象，使用
`placementOrigin=user-explicit-addition`，并必须提供唯一 `designAdditionId`、
`userInstructionRef` 和 `roomId`。这类 placement 不进入上述来源数量等式，不得携带
`sourceTraceId` 或 `sourceObjectCandidateId`，也不得反向补写上游描线。它仍须通过目录、
尺度、层高、房间边界、墙体、开口和组件碰撞门禁。

### 用户复核后的唯一布局事实

初始 placement 继续与 `source*` 完全相等。用户明确纠正，或动线算法产生摘要绑定的唯一
可逆修正时，禁止覆盖来源证据，也禁止另建一份“修正版 placement”。同一 placement
直接保存当前唯一 active transform，并增加 `reviewedAdjustment`。

```json
{
  "position": [7.38, 4.52],
  "rotationY": 0,
  "sourcePosition": [7.56, 4.88],
  "sourceRotationY": 1.5707963268,
  "traceLock": {
    "position": false,
    "dimensions": true,
    "rotation": false,
    "outline": true,
    "source": "classified-second-quadrant"
  },
  "reviewedAdjustment": {
    "schema": "interior.reviewed-layout-adjustment.v1",
    "authority": "user-explicit-layout-correction",
    "userInstructionRef": "feishu-task-20260802061347",
    "reasonCode": "headboard-wall-and-clearance-correction",
    "reason": "用户要求床头贴墙并与衣柜保持可通行净距",
    "reviewedAt": "2026-08-02T06:13:47+08:00",
    "changedFields": ["position", "rotationY"],
    "previous": {"position": [7.56, 4.88], "rotationY": 1.5707963268},
    "active": {"position": [7.38, 4.52], "rotationY": 0}
  }
}
```

- `changedFields` 只允许 `position|rotationY`，并必须与对应 `traceLock` 的 `false` 精确一致。
- `previous` 必须等于不可变 `sourcePosition/sourceRotationY`；`active` 必须等于当前 `position/rotationY`。
- 当前 `position/rotationY` 是渲染、碰撞和关系验收的唯一执行事实；`source*` 只用于溯源，不再参与 active 选择。
- `authority=user-explicit-layout-correction` 必须有用户指令、原因、时间和前后值闭合。
- `authority=circulation-deterministic-correction` 必须有
  `sourceAuditDigestSha256/adjustmentPlanDigestSha256/candidateId/operationDigestSha256`，
  且 `apply_circulation_adjustment.mjs` 重新计算摘要后才可写入；它不需要用户确认。
- 不属于这两种权威的任何来源偏移都必须拒绝。

### 布局关系提示合同

`relationHints` 与 placements 位于同一个 `component-layout.json`，不建立第二份布局 JSON：

- `directionalAxes[]`：记录真实 authored GLB 经浏览器审阅后的局部 `front|back|headboard` 轴，只允许 `+X|-X|+Z|-Z`。同一 `assetId + role` 只能有一条。
- `facing[]`：只允许 `sourceId/targetId/axisRole`，用于存在多个同类目标时消歧；点积、射线和门限由动线 policy 统一计算。
- `wallAttachment[]`：只允许 `sourceId/wallId/axisRole`；间距及是否贴墙由动线 Skill 计算。
- `allowedContacts[]`：只允许 `firstId/secondId/kind=chair-tucked-under-table`，且对象必须分别是原子 `dining-chair` 与 `dining-table`；不得携带伪造的深度门限，其它碰撞不得用白名单跳过。
- `spaceDividerMarkers[]`：只保存 `id/semanticDividerId/visible/required/kind/width/height/color/roughness/metalness/label`，其中 `semanticDividerId` 必须引用上游已存在 divider；起终点和房间关系继续只读上游，不在这里复制。标志只参与展示，不参与墙、门、碰撞或拓扑。

合同顶层只允许 `schema/directionalAxes/facing/wallAttachment/allowedContacts/spaceDividerMarkers`。任何 v1 旧关系对象、房间归属提示、对象净距、净空区和所有门限字段均直接拒绝，不提供兼容别名。所有提示不含 `passed`、实测距离或算法结果。模型轴不确定时先在浏览器单独审阅组件；禁止根据包围盒长边、文件名或“椅子通常朝哪边”猜轴。正式结果只存在于同一模型哈希的 `circulation-audit.v2/result.v2`。

### 描线尺寸与白模

- `uniformScale` 仍须位于组件合理范围，用于原组件整体尺度。
- 项目平面宽深固定读取 `targetDimensions`，且初始值必须逐项等于 `sourceDimensions` 和上游描线 `bbox`；不能用原组件标准包围盒替代。
- `targetDimensions + shapeAdjustments` 始终只决定来源碰撞脚印。普通组件的可见 GLB 只使用等比例缩放；自动匹配遇到宽深比例差超过 25% 时必须拒绝。用户明确要求用通用成品替换、且来源描线只是位置/净空条带时，可以用 `explicit-proportional-source-route` 保留 authored GLB 比例，但必须同时记录 `sourceFootprintAuthority=source-trace-collision`、`visualFootprintAuthority=authored-model-preserved` 和 accepted 的 `visualFitReview`；不得把差异伪装成精确贴合。
- `axis-limited` 只允许用于目录审核过的直线柜体；placement 可增加 `visualDimensions`，三个轴分别受 `editorCapabilities.axisScaleRange` 限制。曲面洁具、软包、灯具和饰品不得声明该模式。
- 落地组件满足 `elevation + visualHeight <= wallHeight - 0.05m`；吊柜必须有正数 `elevation` 且同样受墙高门禁。灶台等台面设备作为独立 placement 记录离地高度。
- 多层组合由地柜、吊柜、高柜、台面设备等独立 placement 组成；上层删除只删除对应模块。只有 catalog 明确列出的真实 glTF 节点可做节点级显隐。
- `finishPreset` 可省略；省略时有色状态使用来源 PBR。正式值只允许 `source-authored|modern-light-wood`，其中木饰面只用于经审核的通用柜体材质角色，不改变 mesh、组件类别、位置、尺寸或风格标签，也不形成第三种外观模式。
- `position`、`rotationY` 初始必须分别等于 `sourcePosition`、`sourceRotationY`。只有上述
  两种完整 `reviewedAdjustment` 才能改变当前值；普通碰撞不能触发自动移动。
- `traceLock.position/dimensions/rotation/outline` 初始全部为 `true`。合法修正只释放声明字段，
  永远不得反向篡改 `source*` 证据。
- 匹配器必须重新计算轮廓面积、周长、圆度、凹角数、曲线占比、手性和 SHA-256；`matches[].evidence`、`placements[].sourceShapeMetrics` 与来源轮廓必须逐项一致。
- `shapeAdjustments` 只由来源轮廓确定，用来驱动曲率、弧长、凹角和手性；不能用它改变中心、宽深、方向或绕过碰撞。
- 曲面、圆形、有机形、L/U 形必须选择同类 authored GLB；`shapeAdjustments` 只绑定来源碰撞脚印，不再驱动第二套程序化 builder。
- placement 不得写任意基础色；只能引用上述受管饰面预设。风格、材质、颜色和用途分字段维护。木色不能自动产生“新中式”标签，古旧/仿古/繁复资产不能匹配新中式意图。
- 用户项目上色不能回写两个标准分库。

### 组件碰撞合同

- 每个 placement 的碰撞脚印由来源轮廓、`targetDimensions.width/depth`、`position` 和 `rotationY` 确定；不允许回退到原组件矩形包围盒。
- 初始来源锁定状态定义为 `position == sourcePosition`、`rotationY == sourceRotationY`、`targetDimensions == sourceDimensions`。该状态的空间归属、跨房间和跨开口合法性只由第一 Skill 的编译空间像素报告负责；本 Skill 不使用第二套碰撞近似重新解释源图中地毯承托、组件贴合、连续组合或贴墙关系。
- 任一变换偏离 `source*` 必须是 HTML 用户编辑形成的用户权威记录，或摘要验证通过的动线算法
  权威记录。离线校验器和浏览器必须导入同一 `shared/placement-geometry.js`，用当前唯一
  active transform 和精确轮廓检查 `floorBoundary`、墙带、真实开口中心线和其它组件；
  `relationHints` 只做引用完整性检查。布局关系和动线只由下游统一算法计算。
- 编辑态以下情况失败：越出 `floorBoundary`、穿过墙带、跨越 `door|sliding-door|open-passage` 的开口中心线、与其它非地毯组件相交。`variant=rug` 是地面覆盖层，不参与组件互撞阻挡，但仍受来源、房间和边界合同约束。
- 只有两个 `fixed-purple` placement 的非空 `joinGroup` 完全相同时，才可把它们视为同一连续柜组的编辑态设计连接；`joinGroup` 不能用于活动家具，也不能作为普通碰撞豁免。
- 浏览器拖动、旋转或缩放产生非法位置时必须回滚到提交前 placement。

### `component-assets.lock.json`

```json
{
  "schema": "interior.project-component-assets.v1",
  "catalogDigestSha256": "<sha256>",
  "policy": "research",
  "assetCount": 1,
  "assets": [{
    "id": "ph-sofa-04",
    "provider": "poly-haven",
    "sourceLicense": "CC0-1.0",
    "licenseEvidence": {"status": "provider-direct-confirmed"},
    "researchOnly": false,
    "commercialUseAllowed": true,
    "commercialReviewRequired": false,
    "runtimeSha256": "<sha256>",
    "runtimeBytes": 123456,
    "targetPath": "component-library/models/poly-haven/ph-sofa-04.glb",
    "materialization": "hardlink"
  }]
}
```

lock 的 ID 集合必须等于当前 placement 所用公共组件集合；自定义单品不进入该集合。`policy=commercial|publish` 时任何 `commercialUseAllowed!=true` 都必须在物化前失败。
每条 lock 记录还必须保存 `sourceUrl/sourceAuthors/sourceLicense/licenseEvidence/commercialUseAllowed/commercialReviewRequired/attributionRequired/modificationNotice`。CC BY 资产的署名和官方登记冲突不能只留在全局 catalog。

`component-layout.json.source.assetMaterialization` 必须同时绑定本项目资产锁：

```json
{
  "status": "complete",
  "policy": "research",
  "lockFile": "component-assets.lock.json",
  "lockSha256": "<sha256>",
  "distinctAssetCount": 1,
  "placementCount": 1
}
```

该对象只由匹配器在资产全部物化并复核后写入；不存在 `deferred` 或手工补写状态。布局、锁、实际 GLB 任一摘要不一致时，项目不是可消费模型。

## 场景与机位合同

### `scene-rig.json`

```json
{
  "schema": "interior.scene-rig.v1",
  "coordinateSystem": "threejs-world-y-up-meters",
  "gizmosVisible": true,
  "rendering": {
    "toneMapping": "ACESFilmic",
    "exposure": 1.12,
    "ambientIntensity": 0.48,
    "hemisphereIntensity": 1.05,
    "detailFillIntensity": 0.38
  },
  "lights": [
    {
      "id": "light-day-key",
      "name": "日光主灯",
      "type": "directional",
      "enabled": true,
      "position": [-7, 13, 9],
      "target": [0, 0.8, 0],
      "intensity": 0.78,
      "temperatureK": 6500,
      "distance": 18,
      "decay": 2,
      "angle": 45,
      "penumbra": 0.2,
      "castShadow": true
    }
  ],
  "cameras": [
    {
      "id": "camera-overview",
      "name": "默认可编辑机位",
      "enabled": true,
      "position": [-3.2, 1.25, 1.5],
      "target": [-1.8, 0.65, -0.9],
      "focusRoomId": "living",
      "focalLengthMm": 28,
      "fov": 46.397,
      "lensPreset": "wide",
      "distortion": 0,
      "near": 0.01,
      "far": 120,
      "mount": {
        "mode": "free",
        "wallId": null,
        "offset": null,
        "height": 1.55,
        "side": 1,
        "clearance": 0.12,
        "snapEnabled": false
      },
      "visibility": {
        "cutawayEnabled": false,
        "contextPolicy": "preserve-visible-adjacent-spaces",
        "hiddenElementIds": [],
        "preserveElementIds": [],
        "hiddenWallIds": [],
        "hiddenComponentIds": []
      }
    }
  ]
}
```

#### 光源字段

- `type`：`directional`、`point` 或 `spot`。
- `position` / `target`：Three.js 世界坐标，单位米；点光源不使用 `target`，但仍保留合法三元组。
- `intensity`：模板归一化亮度，范围 0 到 12；运行时按类型换算为 Three.js 光强。
- `temperatureK`：2000 到 10000 K。
- `distance` / `decay`：点光源和聚光灯的照射距离与距离衰减。
- `angle` / `penumbra`：仅聚光灯使用，分别为 5 到 120 度、0 到 1。
- `castShadow`：是否投射阴影；默认主灯为 `true`，新增灯默认为 `false`。

#### 渲染字段

- `toneMapping`：白模正式预览固定为 `ACESFilmic`，用于压缩强高光并保留墙体、家具和柜体层次。
- `exposure`：渲染器曝光，范围 `0.30`–`1.50`；默认编辑值 `1.12`。
- `ambientIntensity`：中性环境底光，范围 `0`–`2`；保证浏览器预览和 capture 暗部均有最低可读层次，不承担方向塑形。
- `hemisphereIntensity`：天空/地面半球补光，范围 `0`–`2`；只负责保留空间层次，不可打平全部阴影。
- `detailFillIntensity`：中性细节补光，范围 `0`–`2`；默认低于环境补光。
- 正式机位可临时覆盖五项设置，退出机位后必须恢复项目值；交互预览和 `?capture=1&shot=` 必须应用同一套字段。

#### 场景摄像头字段

- `position` / `target`：Three.js 世界坐标三元组。
- `focusRoomId`：`structure-data.json.rooms[].id` 或 `null`；非空时 `target` 取该空间多边形中心与标准视线高度。
- `focalLengthMm`：全画幅等效焦距，14 到 85mm。模板用 24mm 传感器高度将其换算为垂直 `fov`。
- `fov`：16 到 82 度；焦距或 FOV 任一字段变化时必须更新另一字段。
- `lensPreset`：`ultra-wide`、`wide`、`standard`、`telephoto` 或 `custom`，快捷值分别为 16、24、35、50mm。
- `distortion`：正式必填值固定为 `0`。广角通过真实焦距与相机后退空间获得，不叠加鱼眼、桶形或弧边后处理。
- `mount.mode`：`free` 为自由坐标；`wall` 为挂载到语义墙。
- `mount.wallId`：挂载墙 ID，仅墙面模式必填。
- `mount.offset`：从宿主墙起点沿墙方向的米制距离。
- `mount.height`：离地高度；墙面挂载时必须位于 `0.20m` 至“宿主墙高减 `0.15m`”之间。
- `mount.side`：墙的 A/B 两侧，取 `1` 或 `-1`。
- `mount.clearance`：摄像头离墙中心线距离。
- `mount.snapEnabled`：是否开启提交式墙面吸附；开启后仅在松手或字段提交时检查一次，距离最近启用墙不超过 `0.70m` 时切为 `wall`。
- `visibility.cutawayEnabled`：是否应用当前 shot 的显式局部隐藏清单；它不表示整房隔离。
- `visibility.contextPolicy`：固定为 `preserve-visible-adjacent-spaces`。
- `visibility.hiddenElementIds`：第三个 Skill 已逐项复核的局部遮挡实体；HTML 不自动扩大清单。
- `visibility.preserveElementIds`：必须显示的主体、开口和背景元素；优先级高于隐藏清单。
- `visibility.hiddenWallIds` / `hiddenComponentIds`：由显式 ID 按真实实体类型派生，只控制临时可见性，不删除模型事实。

每个场景对象 ID 唯一。基础模板至少保留一盏可编辑光源和一个场景摄像头。浏览器编辑后可导出完整 `scene-rig.json`。

平面显示直接读取同一数组，不建立 `planLights` 或 `planCameras`：

- 平面相机目标始终为 `floorBoundary` 的世界中心；取景半径以该中心对称扩展，直到户型、所有光源/目标和摄像头/目标都位于视口内，因此户型不会被场景对象拖偏；
- 用户显式进入三维时，Orbit target 的 X/Z 必须等于同一 `floorBoundary` 世界中心，Y 为结构包围盒中高；相机距离由户型宽、深、最高构件、FOV 和画布比例联合计算，禁止使用与户型尺寸无关的固定位置。用户后续平移焦点时不自动回正。
- 三维 `position/target` 在平面中只把 Y 压到编辑辅助层，X/Z 不变；拖动写回原对象 X/Z，真实高度保持不变；
- 平面相机、灯光和连线不受当前右栏页限制，capture 或进入正式相机视角时统一隐藏；
- `cameraPreviewEnabled` 默认 `false`。用户点击“预览”后，左上角 16:9 `camera-live-preview-canvas` 使用同一场景、同一 `scene-rig` 相机和独立离屏 render target 输出实时画面；开启调用返回前必须完成第一帧，不能等下一次拖动才出现。不得用主画布 scissor 假装预览，也不得创建第二个 WebGL context。
- 预览右下角提供唯一 resize handle。拖动边界只改变 CSS 显示宽度并锁定 16:9，桌面范围 `240–720px` 且不得超出主画布，移动端最小 `210px`；双击手柄恢复 `320px`。离屏 render target 始终保持 `320×180`，调整窗口大小不得重建 renderer、相机或场景。
- 预览开关独立于 `top|iso|free-3d` 视图和右栏页签，切换平面、三维、组件或场景时不得自动关闭。相机位置、目标、焦距、对象显隐或灯光变化都必须增加 frame count 并改变可测像素签名。

场景检查器的 X/Y/Z 滑杆和数字输入必须写回同一 `position` 或 `target` 数组。滑杆 `input` 和画布 `pointermove` 只更新现有可视对象；吸附、遮挡、完整校验和撤销记录只在提交时执行。

`gizmosVisible=false` 只隐藏位置/焦点三轴和焦点连线；光源、摄像头本体标记仍保持可选。

场景对象与固定视角交互合同：

- 场景辅助对象拥有独立于可见网格的拾取代理。场景页内单击相机或光源本体立即选中并显示操纵轴；按住本体或 XYZ 轴拖动必须写回同一 `scene-rig` 对象。二维和自由三维使用同一套拾取与拖动实现。
- 双击相机或光源复用上述选中逻辑，只额外明确进入位置编辑；双击相机同时开启实时预览，但不得自动进入固定视角。方向光的实际 Y 可高于户型，三维编辑标记允许投影到墙顶以上的辅助高度，字段仍显示并写回真实 Y。
- 固定摄像头视角只能由检查器中的显式“进入视角”命令或已保存 shot 触发；进入后显示“已切换为固定视角”。
- 固定状态内方向键改变相机与目标的水平位置，`W/S` 或滚轮沿当前视线前后移动，双击空白画布改变目标点；焦距和 FOV 变化写回当前摄像头，`distortion` 始终为 `0`。
- 只有在画布空白处按下并拖动 Orbit 才脱离固定视角；脱离后的自由视角不写回固定摄像头，左上角预览仍保持开启。
- 非固定视角中，单击空白画布必须把选择设为 `none`。此时方向键沿当前屏幕平面同步平移主相机与 Orbit target，保持两者距离、方向和 FOV 不变；`Shift` 加速。对象被选中时，方向键继续服从对象或固定机位的既有语义，不得同时移动画布。

### 与 `camera-plan.json` 的边界

`scene-rig.json` 保存建模 HTML 中由用户直接编辑的场景灯光和摄像头。`camera-plan.json` 由 `interior-camera-capture` 负责，保存已经完成空间主角分析的正式机位组合与逐机位打光。两者不得合并。

正式机位文件至少包含：

```json
{
  "schemaVersion": "8.0",
  "schema": "interior.camera-plan.v8",
  "modelBackend": "html-threejs",
  "sourceModelSha256": "...",
  "floorplanId": "floorplan-project-001",
  "seriesId": "whole-home-review-001",
  "modelPath": "./index.html",
  "lightingSetups": [],
  "shots": []
}
```

`floorplanId` 必须与 `structure-data.json.floorplanId` 一致。基础模板只保存 `lightingSetups: []`、`shots: []` 的空适配文件；正式坐标、空间聚焦策略和打光方案不在本 Skill 维护。

HTML 的“已保存机位”必须位于当前摄像头参数之后。点击某个 shot 时，把以下组合临时套入当前摄像头和场景：

- `position`、`target`、`roomId`；
- `focalLengthMm`、`fov`、固定为 0 的 `distortion`；
- `framing` 中经量尺计算的主体宽高、墙宽、可用后退距离、所需距离和画幅占比；
- `visibility.mode=all-spaces`、`contextPolicy=preserve-visible-adjacent-spaces`；
- `visibility.hiddenElementIds`、`hiddenElementEvidence` 和由 `mustShowElements` 派生的主体保护集合；
- `lightingSetupId` 引用的整组灯光，或 `null` 表示沿用当前场景光。
- `rendering`：该 shot 的 `toneMapping`、`exposure`、`hemisphereIntensity` 和 `detailFillIntensity`。

临时套用时，下方焦点、位置和镜头字段必须反映该 shot 参数；不得创建第二个摄像头、写入撤销历史或改写导出的 `scene-rig.json`。再次点击同一 shot 时，必须完整恢复切换前的摄像头、灯光、选择状态和视图。切换到其它 shot 时始终以同一份切换前快照为基线，禁止叠加上一个 shot 的参数。

HTML 继续支持确定性截图路由：

```text
?capture=1&shot=<shotId>
```

该路由必须使用与右栏预览相同的机位、空间聚焦、逐机位打光和曝光设置，并公开帧可读性像素证据。正式 shot 与 `lightingSetups` 的完整字段只在 `interior-camera-capture/data_contract.md` 维护。

## `interior.scene-semantic-frame.v4`

连接/门窗洞口的 `screen` 只能由完整位于相机近裁面前方的四个洞口角点生成，并必须写入 `visibilityEvidence.method=all-opening-corners-in-front-of-camera`、`allCornersInFrontOfCamera=true` 及正向最小/最大深度。任一角点位于相机后方或跨越近裁面时，该连接不得进入当前 semantic frame；禁止把前后混合角点裁成横跨画面的假门洞。

截图页面必须在实际截图相机下调用：

```javascript
window.__INTERIOR_MODEL_EDITOR__.getSceneSemanticFrame(
  shotId,
  {
    slotGuided: slotGuidedImageFile,
    furnishedQa: furnishedQaImageFile
  },
  [sourceWidth, sourceHeight]
)
```

返回值是第三 Skill 构建机位 JSON 的唯一模型侧输入，至少包含：

- `camera`、`imageSize` 和 `semanticRaster`；
- `guidanceImages.slotGuided` 与 `guidanceImages.furnishedQa`；
- `presentation.defaultGenerationMode=slot-guided`，以及槽位生成证据和家具核对证据的组件显隐、结构皮肤与生成权限；
- `entities[]`：原始 `sourceModelId`、类别、房间、世界尺寸、世界包围、位置、四元数、缩放、Y 轴旋转角及 GPU 可见像素；
- `rooms[]`：房间原始 ID、模型多边形和同帧可见像素；
- `openings[]`：门洞/通道的模型几何投影；
- `entityIdMask` 和 `roomIdMask`；
- 分阶段耗时和工作内存字节数。

生成算法固定为：

1. 使用实际 Three.js 网格，以稳定 RGB ID 材质离屏渲染；WebGL 深度测试决定每个像素最前方的真实对象，并写入 `modelBackend=html-threejs` 与 standalone HTML SHA-256。
2. 使用同一相机渲染结构深度，将语义像素反投影到世界坐标，再用 `structure-data.json.rooms[].polygon` 判断空间归属。
3. 将 `connections[]` 的真实开口几何直接投影到画面并裁切到单位画幅。
4. 语义栅格最长边固定不超过 `800px`，坐标统一归一化到原始截图；源图为 `1200px` 宽时最大量化误差不超过 `1.5px`，`1600px` 宽时不超过 `2px`。

禁止：

- 从最终 PNG 做 OCR、分割、目标检测或视觉识别来生成正式数据；
- 用对象 AABB、投影凸包或无遮挡角点代替可见像素；
- 根据名称后缀重命名 `roomId`、`sourceModelId` 或对象类别；
- 由旧 scene map 倒推本帧数据。

本 Skill 只提供两种同机位证据状态：

- `slot-guided`：隐藏活动家具和定制柜，墙体与 `floorBoundary` 地板统一显示 `concrete-shell` 水泥毛坯皮肤，但保留精确 placement slot 数据；
- `furnished-qa`：显示已经从资产库物化的活动家具和定制柜，墙体与 `floorBoundary` 地板继续显示同一 `concrete-shell` 水泥毛坯皮肤；只用于人工核对，不具备绘图模型输入权限。

两种状态共用位于户型下方的米制网格。网格宽深至少为户型最大边的 `2.8` 倍并覆盖场景辅助对象，
不得裁到房间内部，也不得随水泥皮肤切换而消失。

二维机位证据不由第三个 Skill 重画。唯一公开入口为：

```javascript
window.__INTERIOR_MODEL_EDITOR__.captureCameraPlanEvidenceDataUrl(shotId)
```

返回 `interior.camera-plan-evidence.v2` JSON 与同一 WebGL 场景 PNG；证据写入 `source=same-native-model-camera-state`、HTML 后端和原生模型哈希。摄影机、目标、视锥和左上角离屏实时预览都读取当前 HTML 相机状态，不能各自维护位置或镜头副本。

正式截图只能由 `interior-camera-capture/scripts/capture_model_views.py` 调度。调度器先验证 accepted `camera-plan.v8`、模型范围和设备压力，再取得全设备最多两个截图槽位，最后调用 `capture_html_views.mjs`。适配器必须在 standalone 业务脚本执行前冻结该计划，丢弃页面内嵌历史计划的赋值，并验证 `runtimeCameraPlanSource=external-formal-camera-plan-v8`。第三象限 JSON 由适配器直接绑定同一计划的 `modelBackend`、`sourceModelSha256`、坐标系、`visibility` 与 `mustShowElements`；不允许项目脚本直接启动 Chrome 或在截图后补写这些字段。

## `interior.native-model-manifest.v1`

standalone HTML 完成浏览器验收后，`export_native_model_manifest.mjs` 必须导出：

- `modelBackend=html-threejs`；
- HTML 路径、SHA-256 和 Three.js runtime；
- `cameraCoordinateSystem=interior-world-y-up.v1`；
- 结构、开口、地面、天花、组件、灯光和相机集合；
- raycast、depth、entity ID、visibility 和 native camera render 能力；
- 唯一正式调度器 `interior-camera-capture/scripts/capture_model_views.py`，HTML 后端适配器为 `scripts/capture_html_views.mjs`。

机位 Skill 只读取该清单，不再从目录名猜测 HTML 身份或直接持有 HTML 截图脚本。

它不保存任务最终选择。生成合同只有 `slot-guided`：渲染 Skill 只能提交水泥 Q1 和闭合槽位 JSON。Q2 家具图只供人工核对，本 Skill 不根据模型质量、用户历史或出图失败切换输入。

## 项目级外部组件

`custom-components/registry.json`：

```json
{
  "schema": "interior.custom-component-registry.v3",
  "packages": [
    {
      "packageId": "custom-sofa-001-v3",
      "placementClass": "movable-green",
      "manifestPath": "custom-components/custom-sofa-001-v3/custom-component-package.json",
      "standaloneHtmlPath": "custom-components/custom-sofa-001-v3/product-standalone.html",
      "manifestSha256": "<64 hex>",
      "packageSha256": "<64 hex>",
      "geometryStateSha256": "<64 hex>",
      "evidenceViewIds": ["front", "side", "top"],
      "scope": "current-project",
      "enabled": true,
      "defaultAppearanceMode": "white-model",
      "supportedAppearanceModes": ["white-model", "source-color"]
    }
  ]
}
```

引用外部产品的 placement 使用 `customPackageId`，通用组件使用 `componentId`；
两者必须且只能填写一个。导入器只复制 manifest 明确列出的 plan、逐视图 evidence/源图、唯一 state、
零异或报告、standalone 和 browser QA，不复制整个来源目录。所有 artifact 文件哈希、四条 canonical 绑定、
双外观 state 哈希及 accepted 状态必须一致。外部包仍必须通过既有边界、碰撞、方向和数量校验；registry
中的 `standaloneHtmlPath` 必须指向同一 v3 包内已验收的单产品 HTML。
