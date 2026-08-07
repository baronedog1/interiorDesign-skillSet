# Data Contract

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
4. 多个候选内容哈希相同视为等价副本，优先推荐目录并记录其它路径；只有内容不同且项目身份同样成立、无法由 manifest 或上下游哈希链消歧时，才把冲突与其它未决项合并成一次用户选择。
5. 完全找不到时，先完成 manifest、工作区有界搜索和等价字段归一化，再把所有缺失产物合并询问用户是否已有文件或可提供路径；用户确认没有后才能报告缺失。
6. 路径、目录名、文件名和 producer 的 patch 版本不能单独构成拒绝理由。Schema、身份哈希、空间/模型绑定、许可和内容冲突仍是硬门禁，不能因兼容发现而放宽。
7. 每次发现都输出 `artifactDiscovery`：推荐路径、实际路径、语义角色、内容哈希、归一化字段、等价副本和冲突状态。



## 源事实

### `source-evidence.json`

```json
{
  "schema": "interior.floorplan-source-evidence.v4",
  "sourceSha256": "<source image sha256>",
  "sourceNormalization": {
    "method": "grayscale-local-contrast-union-v1",
    "coordinateBinding": "original-source-image-pixels"
  },
  "sourceCoordinateFrame": {
    "width": 817,
    "height": 850,
    "origin": "top-left",
    "xAxis": "right",
    "yAxis": "down"
  },
  "layoutAuthority": {
    "schema": "interior.floorplan-layout-authority.v1",
    "mode": "source-furnished",
    "structureAuthority": "source-floorplan",
    "furnishingAuthority": "source-floorplan",
    "nativeLayoutSha256": null,
    "coordinateBinding": "same-canvas-identity",
    "structureLock": {"walls": true, "openings": true, "spaceBoundaries": true},
    "nativeGeneration": null
  },
  "inspectionViews": [{
    "id": "natural-reading-view",
    "path": "source-natural-view.png",
    "size": [850, 817],
    "sourceToView": [[0, 1, 0], [-1, 0, 816], [0, 0, 1]],
    "viewToSource": [[0, -1, 816], [1, 0, 0], [0, 0, 1]],
    "roundTripControlPoints": [
      {"source": [0, 0], "view": [0, 816]},
      {"source": [816, 0], "view": [0, 0]},
      {"source": [0, 849], "view": [849, 816]},
      {"source": [816, 849], "view": [849, 0]},
      {"source": [408, 424], "view": [424, 408]}
    ]
  }],
  "candidateOverlayPath": "source-evidence-overlay.png",
  "candidateOverlayPaths": {
    "wallsOpenings": "walls-openings-overlay.png",
    "wallsOpeningsReview": "walls-openings-overlay-review.png",
    "roomLabelsDividers": "room-labels-dividers-overlay.png",
    "roomLabelsDividersReview": "room-labels-dividers-overlay-review.png",
    "objects": "objects-overlay.png",
    "objectsReview": "objects-overlay-review.png"
  },
  "wallCandidates": [{
    "id": "candidate-wall-001",
    "faceA": [[10, 10], [100, 10]],
    "faceB": [[10, 22], [100, 22]],
    "sourceCrop": "evidence-crops/candidate-wall-001.png",
    "discovery": "deterministic-source-pixel-trace"
  }],
  "openingCandidates": [{
    "id": "candidate-entry-main",
    "segment": [[10, 200], [60, 200]],
    "discovery": "deterministic-source-pixel-trace",
    "symbolEvidence": {
      "signature": "single-leaf-swing",
      "primitiveTypes": ["wall-gap", "swing-arc"],
      "panelMaterial": "opaque"
    }
  }],
  "spaceLabelCandidates": [{
    "id": "label-living",
    "text": "客厅",
    "point": [180, 180],
    "discovery": "source-plan-text-position-agent-confirmed"
  }, {
    "id": "label-dining",
    "text": "餐厅",
    "point": [250, 260],
    "discovery": "source-plan-text-position-agent-confirmed"
  }],
  "objectCandidates": [{
    "id": "candidate-object-living-sofa",
    "outline": [[120, 120], [220, 120], [220, 165], [120, 165]],
    "details": [[[135, 142], [205, 142]]],
    "discovery": "deterministic-source-object-contour"
  }],
  "semanticDividerCandidates": [{
    "id": "candidate-divider-living-dining",
    "segment": [[120, 240], [300, 240]],
    "sourceLabelIds": ["label-living", "label-dining"],
    "anchorWallCandidateIds": ["candidate-wall-010", "candidate-wall-021"],
    "discovery": "deterministic-space-label-partition"
  }]
}
```

该文件先于任何最终墙体、门窗或空间连接生成，只描述源图证据。
输入不设颜色、饱和度、背景或对比度门禁。校验器先用固定的
`grayscale-local-contrast-union-v1` 将可读源图确定性归一化为黑白墨线证据；该结果只
用于检查 authored 输出是否回投到真实可见线，不替代原图、不改变坐标系，也不自动
决定墙、门窗、房间或对象语义。项目数据不得自定义阈值或掩膜来让偏离源线的候选通过。
`faceA/faceB` 与 `openingCandidates[].segment` 必须由代码辅助的归一化线证据定位并
回投原始源像素产生，
不能由 Agent 目测填入近似直线。`candidateOverlayPath` 必须是
`render_floorplan_quadrants.py --evidence` 用同一组坐标生成的原图叠加图。
外轮廓按内外双边顺时针连续拆段，斜切、外凸、凹口和方向变化不得轴对齐简化。

`layoutAuthority` 明确结构与布置分别来自哪里。结构始终只认用户源图。原图已有完整
家具时使用 `source-furnished`；空户型或用户要求先重新布置时，先以原图锁结构，用原生
绘图生成一张同尺寸、同坐标的二维布局，验收后使用 `native-layout-furnished`。后者必须
记录 native layout 哈希、原生绘图提示词哈希和 accepted 状态；`source-furnished` 的
`nativeLayoutSha256` 必须为 `null`，不重复制造第二张图片。对象候选的 `discovery`
固定为 `deterministic-native-layout-object-contour`。验证器同时检查 native layout 与原图
墙线是否重合，禁止把生成图中的结构漂移带入建模。无论哪种模式，墙、门窗、房名和空间
边界都只从原图读取。

每个开口候选必须保存结构化 `symbolEvidence`，语义映射固定如下：

| 分类 | `signature` | 必须出现的 `primitiveTypes` |
|---|---|---|
| 平开门 | `single-leaf-swing` | `wall-gap`, `swing-arc` |
| 玻璃/普通推拉门 | `sliding-panel` | `wall-gap`, `parallel-tracks`；玻璃时再含 `glass-panels` |
| 开放通道 | `open-gap` | `wall-gap`, `no-swing-or-track` |
| 固定玻璃 | `fixed-glazing` | `host-wall`, `glass-panels` |
| 窗 | `window-frame` | `host-wall`, `parallel-frame-lines` |

`sliding-door/glazing/window` 还必须记录 `panelMaterial=glass|opaque|mixed|unknown`，其中固定
玻璃和窗必须为 `glass`。该证据随连接或窗对象进入结构 handoff，后端不能再把玻璃推拉门
退化成普通窗。厨房至餐厅、客厅至阳台等位置不能只按“蓝线”判断；是否可通行由墙体
中断、轨道、玻璃扇和门扇符号共同确定。`window/glazing` 不进入通行图，`sliding-door`
必须进入通行图。

`sourceCoordinateFrame` 是唯一正式坐标系，固定为原图左上角原点、x 向右、y 向下。
旋转、增强、放大或裁切查看图只能登记在 `inspectionViews[]`；每个查看图必须保存
互逆的 `3x3` 变换和至少五个覆盖四角与中心的往返控制点。所有候选最后都写回原图
坐标，禁止把查看图坐标直接混入候选台账。

`candidateOverlayPath` 是脚本生成的全量机器绑定图。Agent 视觉复核必须另外查看
`candidateOverlayPaths` 的三组干净叠图及对应编号图：墙与开口、房名与非墙分界、
对象。六张图都由正式渲染脚本从同一候选台账生成；禁止用一张拥挤叠图代替逐层复核。

`spaceLabelCandidates[]` 记录源图上 Agent 已确认的房名文字和源像素锚点，不是
OCR 猜测结果，也不能从最终 `spaces[]` 倒推。每个 ID 必须唯一，并在候选叠图中
回绘位置。房名锚点一旦进入已绑定的语义决定便不可移动；拓扑失败只能修墙、开口、
非墙分界或独立拓扑种子，禁止移动房名锚点来改变区域归属。

`objectCandidates[]` 在任何绿紫描线之前，按每个空间登记 furnishing authority 中清晰可见的
活动家具、柜体、洁具和设备。`outline` 必须沿该 authority 的像素轮廓描点并由候选叠图回绘；
`details[]` 必须显式存在，并保存全部可见非文字内部线及与主体分离但属于同一对象
组合的轮廓。例如餐桌和每把餐椅分别建立独立候选；餐桌腿线属于餐桌 `details[]`，
椅背线属于对应椅子 `details[]`。衣柜门缝、沙发坐垫分缝、洁具内部轮廓也只进入所属
对象的 `details[]`。禁止用一只覆盖整组对象的
外包矩形代替真实轮廓。`outline` 与每条 `details[]` 都必须通过统一归一化墨线证据的
逐线输出对齐门禁；绿紫描线的 `points/details` 必须与冻结候选逐点完全一致。候选不能从最终
绿紫图、组件表或碰撞结果倒推，也不能因为组件库没有合适原型、对象靠近门洞或下游
校验失败而省略。

accepted 对象的 `outline` 不得穿过 accepted 门、移门或源图可见通道的中央净开口。
校验器沿物理开口中段 `76%` 检查对象占用，排除两端门垛后仍有交叉即失败。失败时
只能回到源证据重描对象或重新判断开口；不得在绿紫描线、组件匹配或任一建模后端移动、
缩小、删除对象，也不得把冲突开口改写为无源图依据的语义分界。

`semanticDividerCandidates[]` 只表示源图没有实体墙墨线、但存在两个独立房名的
功能区边界。`segment` 由两个已登记房名锚点和两个墙候选端点确定性求得；
`sourceLabelIds` 必须恰好引用两个已登记房名，`anchorWallCandidateIds` 必须恰好引用
两个已登记墙候选。两个房名锚点必须位于分界线两侧，分界线的两个端点必须分别
落在这两条墙候选上，允许的源像素误差不超过 `3px`。它不接受 `deterministic-source-pixel-trace`，
也不进入物理开口或墙体台账。

### `semantic-decisions.json`

```json
{
  "schema": "interior.floorplan-semantic-decisions.v1",
  "evidenceSha256": "<source-evidence sha256>",
  "candidates": [{
    "candidateId": "candidate-wall-001",
    "classification": "wall",
    "reason": "连续双边线构成房间边界",
    "evidenceTypes": ["visible-double-edge", "room-boundary"]
  }],
  "openings": [{
    "candidateId": "candidate-entry-main",
    "classification": "door",
    "reason": "外墙中断与门扇符号共同确定入户门",
    "evidenceTypes": ["wall-gap", "door-symbol"]
  }],
  "objects": [{
    "candidateId": "candidate-object-living-sofa",
    "classification": "movable-furniture",
    "name": "客厅沙发",
    "sourceLabelId": "label-living",
    "reason": "独立外轮廓与坐垫内部线清晰可见",
    "evidenceTypes": ["closed-object-contour", "visible-furniture-details"]
  }],
  "dividers": [{
    "candidateId": "candidate-divider-living-dining",
    "classification": "semantic-divider",
    "traversal": "open-passage",
    "reason": "两个独立房名与两侧结构端点共同确定开放功能分界",
    "evidenceTypes": ["source-room-label-pair", "open-zone-anchor-pair"]
  }]
}
```

`classification` 只允许 `wall|occluded-wall|not-wall|unresolved`。`occluded-wall`
用于墙的一侧被固定柜体等对象遮住、但源图仍给出可追溯结构连续性的情况。对应墙候选
必须在 `occlusionEvidence[]` 逐项记录至少两种不同的源图证据，例如连续可见墙面、
门垛端点、与另一面墙的结构交点或一致墙厚；每项 `type` 必须同时出现在决定的
`evidenceTypes[]`，引用其它候选时使用 `referenceCandidateIds[]`。仅因空间需要闭合、
住宅通常有墙或柜体靠墙，不构成独立证据。带 `occlusionEvidence[]` 的候选只能判为
`occluded-wall`；存在 `unresolved` 时停止。

`openings[].classification` 只允许
`door|sliding-door|open-passage|glazing|window|not-opening|unresolved`。
每个开口候选必须有且仅有一个判断，并写明理由和证据类型；存在 `unresolved`
时停止。墙与开口的语义判断分开登记，但都只引用同一个源证据台账。

`dividers[].classification` 只允许
`semantic-divider|not-divider|unresolved`，且至少引用房名和结构端点两类证据。
accepted 分界必须额外包含唯一 `traversal`：
`open-passage|boundary-only`。`open-passage` 表示两个空间沿该分界可以直接穿行；
`boundary-only` 表示该线只划分空间、面积和标注区域，实际被柜侧、设备或其它
非墙构造阻隔，不生成通行连接。非 accepted 分界禁止携带 `traversal`。
语义分界与真实门窗分别登记，禁止把没有源墨线的空间边界写进 `openings[]`。

`objects[].classification` 只允许
`movable-furniture|fixed-cabinet-equipment|not-object|unresolved`。accepted 对象必须
有名称并绑定一个已登记 `sourceLabelId`；还必须写
`functionalClass/quantity=1/atomicObject=true`。`functionalClass` 使用小写连字符的
单一功能类别，例如 `sofa|bed|dining-table|dining-chair|tv-console|toilet|washbasin`；
`dining-set|bedroom-set|furniture-group` 等组合类别禁止进入正式数据。餐桌和六把椅子
必须登记为七个候选对象，父级组合关系只能通过可选 `assemblyId` 表达，不能吞掉子对象。
存在 `unresolved` 时停止。每个
`objectCandidates[]` 必须恰有一个决定。空间拓扑编译后，同一个 accepted 对象的
源图轮廓必须至少占有其声明空间的像素，且占入其它已编译空间的像素数必须为 `0`。
活动家具的轮廓质心还必须落在声明空间内；固定柜体可压住宿主墙像素，但不得穿到
另一空间。失败时只能修正源空间分界或对象所属空间判断，禁止下游移动对象。

### `wall-geometry.json`

只由 `build_wall_geometry.py` 生成，墙点固定为 `[faceA 起点, faceA 终点, faceB 终点, faceB 起点]`。禁止手改端点或为了闭合空间新增墙。

## `trace-spec.json`

`interior.floorplan-trace.v3` 是同一源像素坐标系中的派生模型，只保留渲染和建模需要的事实：

- `floorplanId`、`sourceImage`、`planBounds`、`knownSizeMm`。
- `layers.movableFurniture/fixedFixtures/other`。
- `cleanStructure.windows/connections/removedNoise`；其中窗和连接只登记语义绑定，
  不登记第二套像素几何。
- 每个窗的 `hostWallTraceId` 必须在第一 Skill 内完成宿主校验：窗源线须与宿主墙
  平行，且窗线两端沿墙方向的投影都落在该墙段范围内。绑定到相邻墙、交叉墙或
  墙段之外时立即失败；下游建模后端不得移动、裁切或改绑窗来补救。
- `spaceSeeds[]`：每个真实空间唯一的
  `id/name/spaceType/topologyClass/sourceLabelId/point`；`sourceLabelId` 引用
  `spaceLabelCandidates[]`，并把房名事实绑定到最终空间。`point` 是独立的室内
  拓扑种子，不是房名文字坐标的副本，也不能反向改写房名。编译后该种子和其引用的
  原图房名锚点必须落在同一个连通区域；若二者分离，说明中间墙、开口或功能分界有误，
  必须修源边界，禁止移动房名或把门改接到其它空间。
- `semanticDividers[]`：所有 accepted 功能区之间的非墙分界；通行属性只从
  对应语义决定编译。
- `floorBoundary`、`spaces[]`、`compiledTopology`：只由 `topology_compiler.py` 生成；finalizer 在正式 `structure-data.json` 中规范化为 `floorBoundary`、`rooms[]`、`topology`。
- `floorBoundary` 与贴外墙房间的 `polygon` 必须共享同一条边和同一顶点。轮廓简化
  造成的最大 `2px` 表示偏差由编译器投影回同一边并插入共享顶点；超过该由两次
  `1px` 简化产生的上限即失败，禁止由案例放宽阈值、缩小房间或在建模后端补形。

禁止在 authored spec 中出现 `layers.walls/windows/doors`、`cleanStructure.walls`、
房间多边形、面积、墙邻接、`passed`、墙召回声明或第二套面积基准。
`layers.movableFurniture/fixedFixtures` 只可引用 accepted
`sourceObjectCandidateId`；其 `points` 和 `details` 分别逐点复制冻结候选的
`outline` 和 `details`，不得重新概括、删减或改成组件包络。
拓扑编译器只从冻结的 `wall-geometry.json` 注入墙层，并从
`source-evidence.json + semantic-decisions.json` 注入门窗层、开口类别和开口线段；
finalizer 输出的编译后 spec 才包含这些派生字段。

`layers.movableFurniture[]` 和 `layers.fixedFixtures[]` 的每个对象必须包含唯一
`sourceObjectCandidateId/sourceLabelId/traceId`。`points` 必须与该源对象候选的
`outline` 完全一致，名称、`functionalClass` 和 `quantity=1` 必须与语义决定一致。
所有 accepted 对象必须被恰好消费一次，
其它候选不得进入绿紫层。`trace-components.json` 必须再次引用同一个
`sourceObjectCandidateId + traceId + roomId`；它只表达如何把已冻结轮廓编译为
后端原生组件几何，不拥有另一套对象事实。`roomId` 不只核对文本引用：唯一源模型校验器直接把
候选轮廓栅格与本轮拓扑 `assignment` 比较，拒绝进入其它空间的对象。

`spaceType` 只允许 `living/dining/kitchen/bedroom/bathroom/study/balcony/entrance/corridor/closet/storage/utility/multipurpose/other`。其中 `bedroom/bathroom/study/closet/storage` 必须使用 `enclosed`，不能通过把卧室或书房写成开放区来绕过门洞规则。

`topologyClass` 只允许：

- `enclosed`：卧室、卫生间、书房等由实体边界围合的私密空间；
- `open-zone`：客厅、餐厅等开放公共功能区；
- `circulation`：走廊、过厅、玄关等通行空间；
- `attached`：阳台、生活阳台等依附空间。

编译器先按墙和有证据的外部入口得到净室内，再临时闭合内部开口和开放分界形成连通区域。每个区域必须恰有一个空间种子。两个种子进入同一区域表示漏墙或漏分界；区域没有种子表示漏空间；墙两侧仍属于同一空间表示把地毯、柜体或家具边误当墙。

authored `cleanStructure.connections[]` 是可通行空间端点关系的唯一平面事实，每项只写
真实开口连接使用
`id/fromRoomId/toRoomId/sourceOpeningId/bottom/height`；开放功能分界连接使用
`id/fromRoomId/toRoomId/sourceDividerId/bottom/height`。二者必须且只能出现一个。
编译器再从对应证据注入 `kind/segment` 和来源 ID。其中：

- `sourceOpeningId` 必须引用一个已分类的源开口候选；
- `segment` 只来自该候选的源图像素坐标，`kind` 只来自该候选的语义决定；
- 连接中的 `sourceDividerId` 必须引用一个 accepted 且 `traversal=open-passage`
  的语义分界候选，只能编译为 `open-passage`，不得生成门线或墙；
- `traversal=boundary-only` 的语义分界禁止进入 `connections[]`；
- 使用 `sourceDividerId` 的连接不得连接 `exterior`，两端空间种子的
  `sourceLabelId` 集合必须与候选的两个 `sourceLabelIds` 完全一致；
- `exterior` 是唯一允许的非房间端点；
- 每个门描线必须被一条连接消费一次，每个房间必须沿连接图到达有证据的外部入口；
- 每个空间至少有一个可通行连接；`enclosed` 空间至少包含一个 `door` 或 `sliding-door`，超过一个可通行连接时必须登记逐连接视觉复核；
- 连接不是根据家具、空间名称或“住宅通常如此”推测出来的。

authored `semanticDividers[]` 必须逐项消费每个 accepted 分界候选，每项只允许
`id/kind=open-zone-boundary/sourceDividerId/reason`；仅当对应决定为
`open-passage` 时再写同源 `connectionId`，`boundary-only` 禁止写
`connectionId`。编译器从 `sourceDividerId` 唯一注入 `segment/traversal/roomIds`。
它只生成空间边界与面积，不生成墙；通行图只读取 `connections[]`。

完整示例见 [source-evidence.example.json](assets/source-evidence.example.json)、
[semantic-decisions.example.json](assets/semantic-decisions.example.json)、
[trace-spec.example.json](assets/trace-spec.example.json) 与
[wall-geometry.example.json](assets/wall-geometry.example.json)。

## `agent-visual-review.json`

```json
{
  "schema": "interior.floorplan-agent-visual-review.v2",
  "geometrySha256": "<wall geometry sha256>",
  "status": "passed",
  "reviewedWallIds": ["wall-001"],
  "reviewedSpaceLabelIds": ["label-living", "label-dining"],
  "reviewedOpeningIds": ["candidate-entry-main"],
  "reviewedDividerIds": ["candidate-divider-living-dining"],
  "reviewedObjectIds": ["candidate-object-living-sofa"],
  "reviewedRoomIds": ["living"],
  "reviewedConnectionIds": ["entry-living"],
  "objectCoverageReviews": [{
    "sourceLabelId": "label-living",
    "sourceObjectCandidateIds": ["candidate-object-living-sofa"],
    "observedFunctionalCounts": {"sofa": 1},
    "finding": "客厅清晰可见沙发已登记；未发现台账外清晰对象。"
  }],
  "extraAccessReviews": [],
  "reviewedEvidenceOverlayPaths": [
    "walls-openings-overlay.png",
    "walls-openings-overlay-review.png",
    "room-labels-dividers-overlay.png",
    "room-labels-dividers-overlay-review.png",
    "objects-overlay.png",
    "objects-overlay-review.png"
  ],
  "sourceEvidenceOverlay": "source-evidence-overlay.png",
  "overlayImage": "reviews/source-wall-overlay.png",
  "roomContactSheet": "reviews/room-contact-sheet.png",
  "findings": ["外轮廓凹凸和斜切逐段保留；入口保持开放。"],
  "unresolved": []
}
```

该文件必须由 Agent 查看当前三组干净候选叠图、三组编号复核图和最终实际图片后写入，
不能由案例生成脚本预填。`reviewedEvidenceOverlayPaths` 必须与当前源证据声明的六张
分层叠图完全一致。每个空间的 `observedFunctionalCounts` 必须与 accepted 原子对象
按 `functionalClass` 重算后的数量完全一致；该字段不能写总数或组合家具数量。对象 ID、
功能分类计数与房间集合的逐项枚举是正式证据，不再接受
`noUnregisteredVisibleObject=true` 一类无法独立复算的全局自证布尔值。

## `floorplan-handoff.v3`

唯一正式出口：

```json
{
  "schema": "interior.floorplan-handoff.v3",
  "floorplanId": "project-001",
  "producer": {"skill": "interior-floorplan-planning", "version": "6.4.0"},
  "layoutAuthority": {"schema": "interior.floorplan-layout-authority.v1"},
  "artifacts": {},
  "reports": {
    "sourceModelValidation": {
      "path": "reports/source-model-validation.json",
      "sha256": "<64 hex>",
      "bytes": 1
    }
  },
  "sourceTraceRegistry": {
    "structureTraceIds": [],
    "componentTraceIds": [],
    "sourceObjectCandidateIds": []
  },
  "validation": {
    "sourceModel": true,
    "agentVisualReview": true
  },
  "handoffDigestSha256": "<canonical manifest sha256>"
}
```

每个 artifact 都保存相对路径、SHA-256 和字节数。下游只核对该 manifest、唯一报告和来源注册表，不重复运行图像分析。

正式 artifact 集合固定包含：源图、源证据 JSON、全量候选叠图、六张分层候选叠图、
语义判断、墙体几何、Agent 视觉复核、最终对照图、逐房间联系表、四象限图、结构图、
分类叠图、纯描线组合、正式布局、描线组件、已编译 trace spec 和 structure data。
六张分层候选叠图的 manifest key 固定为
`evidenceOverlay_wallsOpenings`、`evidenceOverlay_wallsOpeningsReview`、
`evidenceOverlay_roomLabelsDividers`、`evidenceOverlay_roomLabelsDividersReview`、
`evidenceOverlay_objects`、`evidenceOverlay_objectsReview`；下游不得忽略或另起别名。

米制注册由 `planBounds + knownSizeMm` 确定性完成；墙中心、厚度、窗沿墙位置和连接开口段都必须从源像素换算，不能手填第二套比例。

`structure-data.json` 不是输入。`finalize_floorplan_handoff.py` 只从已编译的
`trace-spec.json` 生成它，并为每面墙写入 `adjacentRoomIds`，为每个空间写入
`spaceType/topologyClass/areaM2/polygon`，同时把编译期 `compiledTopology` 规范化复制为正式字段 `topology`。下游按语义发现该字段，不绑定编译期键名。
