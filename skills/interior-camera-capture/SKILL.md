---
name: interior-camera-capture
description: 当用户要求“找机位/选角度”“给户型模型截图”“拍白模或成品模型”“取景”“做机位四象限图”，或要求保持空间不变出图但尚无正式机位时使用；统一读取已通过动线规划的 HTML/Three.js、Blender 或 CAD/Text2CAD 原生模型，以确定性墙法向算法快速生成每空间正视主机位，并输出 camera-plan.v8、纯水泥空结构 Q1、同机位家具审阅图 Q2、平面机位 Q3、shot-scene-map.v9 与四象限交接。
metadata:
  version: 20.0.0
  camera_plan_schema: interior.camera-plan.v8
  scene_map_schema: interior.shot-scene-map.v9
  supported_backends: html-threejs,blender,cad-step
---

# Interior Camera Capture

## 使用前准备

- 管理员至少预装一种受支持后端：HTML 需非 Snap Chrome/Chromium + WebGL2，Blender 需固定 `BLENDER_BIN`，CAD 需 `INTERIOR_CAD_SNAPSHOT_COMMAND`；相机槽位和输出目录必须可写。
- 先读取 [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) 与 [local_runtime.md](local_runtime.md)，以目标服务账号运行对应后端的非空画布/图像 preflight。
- 必须已有同一哈希链的 accepted 原生模型清单、结构、动线结果和相机输入；任一后端前置缺失时只阻塞该后端，不得任务内安装浏览器、绕过设备压力门或用二维截图冒充原生机位。

所有上游文件先按 [data_contract.md](data_contract.md) 的 `semantic-content-first-v1` 发现；推荐目录和文件名只用于排序，不能代替 schema、哈希和模型身份校验。

## 唯一职责

本 Skill 是三种建模后端、整屋与单空间共用的唯一机位方法：

1. 验证 `interior.circulation-result.v2` 与当前原生模型哈希一致，且动线已接受。
2. 验证 `interior.native-model-manifest.v1`、原生模型哈希和能力。
3. 先运行 `solve_frontal_camera_seeds.py`，从冻结结构、动线场景、原生模型清单和真实墙段为本轮每个拍摄空间确定性生成唯一 `one-point-frontal` 主种子；同一输入必须得到同一 `frontalSeedId`、背景墙、锚定物、相机轴和参数。
4. 原生适配器一次导出全部空间的 OBB 和真实可后退区域，`compile_camera_candidates.py` 一次编译完整拍摄范围的固定焦段链。每个空间只先截图第一张满足几何约束的主候选；只有该原生投影未通过机器门禁时，才允许再截图一张带明确 `failureCodes` 的回退候选，不跨后端代拍，也不由 Agent 随机试角度。
5. 重新计算背景墙法向、射线命中、构图边距、近远尺度和遮挡，不相信计划内自报结论。
6. 用同一原生模型、同一 shot 输出纯水泥空结构 Q1、同机位家具审阅图 Q2、二维机位证据、实体/房间语义和 `shot-scene-map.v9`；只把当前相机前方且具备原生像素证据的空间、连接和对象编译为封闭世界合同。连接除四角前向投影外，还必须在归一化 Entity-ID 图中逐像素证明开口区域未被墙体遮挡。
7. 固定 Q1 纯水泥结构、Q2 同机位家具 QA、Q3 平面相机、Q4 accepted render 的四象限合同；默认槽位引导生成只提交 Q1 和 JSON，不提交 Q2 或语义遮罩。本 Skill 生成 Q1-Q3，渲染 Skill 确定性回填 Q4。
8. 所有真实截图只允许通过 `capture_model_views.py` 正式调度器执行。调度器在启动原生适配器前复验 camera plan 和设备内存、swap、load、PSI、根盘及 `/tmp` 余量，并在设备级最多同时放行 `2` 个截图作业；单个适配器内部按 shot 顺序复用同一原生进程，禁止用 `Promise.all` 批量启动 Chrome。

模型几何修改归对应建模 Skill；固定槽位生成合同和风格表现归 `interior-space-rendering`；平台上传归 `idk-canvas-ingest-agent`。

## 输入合同

必须同时存在：

- `interior.circulation-result.v2`：由 `interior-circulation-planning` 对当前模型完成结构基线与布局差分、开口拓扑和 Agent 视觉终审后生成；状态必须 accepted，`cameraWorkflowAllowed=true`。
- `interior.floorplan-structure.v3`：墙、开口、房间和连接的唯一结构事实。
- `interior.native-model-manifest.v1`：由且仅由当前建模后端导出。
- 清单内 `interior.model-scope.v1`：整屋覆盖全部房间；单空间必须把主空间、允许上下文和排除空间完整分区，并与 `camera-plan.captureScope` 一致。
- 清单内原生模型文件及一致 SHA-256。
- 清单声明 `visibilityStates/nativeCameraRender=true`。HTML 与 Blender 还必须声明 `raycast/depth/entityId=true`；CAD 必须声明 `projectionProfile=cad-same-brep-topology-zbuffer-v1` 和哈希锁定的 `semanticTopology`，不存在的 Snapshot 深度/Entity-ID 必须为 `false`，不能为了统一字段伪造能力。
- 清单声明的 `captureAdapter.interface=interior.native-capture-adapter.v1`。

后端路由固定为：

| `modelBackend` | 原生模型 | 原生截图 |
|---|---|---|
| `html-threejs` | self-contained HTML | 同一 HTML/Three.js 相机经 Chrome/CDP |
| `blender` | `.blend` | Blender Camera + depsgraph + Object Index/Depth |
| `cad-step` | STEP、真实 occurrence selector 索引与同 STEP 派生拓扑 | CAD 原生透视相机；槽位语义由 occurrence 拓扑在同一相机下 Z-buffer 生成 |

不得用某一后端导出的 GLB、截图或重新搭建的代理场景替另一后端拍摄。三后端只共享 `interior-world-y-up.v1` 相机坐标和本 Skill 的算法。

## 简单意图入口

- “找角度 / 截图 / 拍模型 / 做机位四象限”：直接触发本 Skill。
- “保持空间不变出效果图”：先执行本 Skill，再执行 `interior-space-rendering`。
- 只有户型图：先执行 `interior-floorplan-planning`，再根据用户指定后端执行 HTML、Blender 或 CAD 建模 Skill。
- 用户未指定整屋后端时，上游默认使用 HTML；本 Skill 不替用户切换已选后端。

## 高频数据入口

- `interior.floorplan-structure.v3`：墙、真实开口、空间连接和房间多边形。
- `interior.circulation-result.v2`：当前模型哈希对应的动线放行结果。
- `interior.native-model-manifest.v1`：当前 HTML、Blender 或 CAD 原生模型、哈希、坐标系与截图适配器。
- `assets/room-camera-algorithms.json`：八类空间的主角、参考面、目标入画率和候选策略。
- `assets/camera-frontal-seeds.example.json`：每个拍摄空间唯一正视主种子的结构示例。
- `assets/native-camera-envelope-measurements.example.json`：原生适配器一次导出的全空间 OBB 与可退距合同。
- `assets/camera-plan.example.json`：`interior.camera-plan.v8` 示例。
- `assets/closed-world-view-policy.v1.json`：本镜头可新增配饰与绝对禁止推断的唯一策略源。
- `assets/view-visibility-policy.v1.json`：当前相机可进入提示词的房间、连接与边缘片段唯一判定策略。
- `assets/shot-scene-map.example.json`：下游唯一可消费的 `interior.shot-scene-map.v9` 示例。

## 唯一机位算法

### 1. 先求解唯一正视种子

`solve_frontal_camera_seeds.py` 必须在任何候选截图前运行。它按固定优先级选择空间功能锚定物，优先读取已通过动线审计的贴墙关系，再从当前房间真实相邻墙中按距离、墙长和 ID 稳定排序选择唯一背景墙。种子光轴严格沿该墙法向，相机和目标等高，并绑定 `floorplanId/handoffDigest/sourceModelSha256/circulationResultDigest`。请求范围内每个空间恰好一个种子；不能手写、删除或用关系镜头替代。

### 2. 确定空间语义

先选择 `anchorEnvelope`、`referenceFacade`、`contextEnvelope`，再计算相机：

- `anchorEnvelope`：空间主角完整三维 OBB，例如沙发组、完整餐桌椅、床组、最长连续柜面。
- `referenceFacade`：主角背后的真实墙面、开口与必要立面组合。
- `contextEnvelope`：必须保留的相邻空间、通道尽端、采光关系和次要物件。

三个 envelope 都必须由原生模型全部 8 个 OBB 角点投影计算。禁止只取墙宽、组件中心或二维包围盒。

### 3. 计算画幅和距离

固定 36 × 22.5mm 传感器：

```text
Fw = max(
  Wa / oa,
  Wf / of,
  Wc / oc,
  Ha / ov * 36 / 22.5,
  Hf / ov * 36 / 22.5
)
D0 = Fw * focal / 36
D  = D0 * 1.05
```

`Wa/Ha` 为主角宽高，`Wf/Hf` 为参考立面宽高，`Wc` 为上下文宽度；`oa/of/oc/ov` 是各 envelope 的目标入画率。5% 安全量固定保留，不能在结果中删除。

### 4. 生成有界候选

- 正视主图：只能使用 `composition=one-point-frontal`，优先使用 `80%/96%` 主角候选。
- 关系图：使用 `60%/72%` 候选。
- 焦段链：`35 → 32 → 28 → 24 → 22 → 20mm`。
- `18mm` 只允许狭小空间专项审计后使用；`16mm` 永不自动使用。
- 候选按正视种子和固定顺序计算，但每组只实际渲染第一张可拟合主候选；主候选投影通过后立即停止。只有主候选被机器门禁拒绝时，才允许渲染下一张回退候选，因此每组原生预览只能是 `1` 或 `2` 张。
- 候选只改变合法退距、沿墙位置、焦段或构图占比，不改变模型。

### 5. 默认正视墙面法向门禁

本轮每个拍摄空间都必须至少有且只能有一张正对真实背景墙的主镜头；关系、入口、采光和细节图只能作为补充：

1. 从 `structure-data.walls[]` 选唯一 `referenceWallId`。
2. 用墙段 `start/end` 计算切向量和面向相机的法向量。
3. 相机中心射线与墙法向一致；传感器平面与墙平行。
4. `camera.up=[0,1,0]`，相机和目标高度一致。
5. 射线必须在前方命中该墙的有限线段，不能只命中无限延长线或相邻墙。
6. 固定门限：偏航 `≤1°`、俯仰 `≤0.25°`、横滚 `≤0.1°`、整体对齐残差 `≤0.25°`。
7. 四边安全边距均 `≥6%`，左右边距差 `≤3%`，前景遮挡占比 `≤8%`。
8. `mustShowElements` 必须包含 anchor、reference facade 和全部 `preserveElementIds`，且在原生 semantic frame 中逐 ID 可见；近端与远端同类对象投影尺度比 `≤1.18`。

`validate_camera_manifest.py` 必须从绑定的结构、动线场景和原生模型独立重跑 seed 算法，再从结构墙、相机向量和原生相机状态证据重新计算以上结果。手写自洽 seed、复用其它截图的相机证据都必须失败。只有明确标记为关系、入口、采光或细节的补充镜头可以偏离墙法向，它们不能替代任何空间的 `one-point-frontal` 主图。

### 6. 后退链

候选不合格时按固定顺序处理：

1. 在当前房间合法可站立区域后退。
2. 穿过真实开口进入连通空间后退，并把进入后的空间登记为 `cameraHostRoomId`；禁止只把可后退深度写大而不移动到真实连通空间。
3. 经原生 raycast 审核后只隐藏最近、真实阻断主角的局部墙段或对象。
4. 沿参考墙平移相机并保留正交光轴。
5. 将可选上下文移到第二张关系图。
6. 按焦段链逐级降低焦距。
7. 仍不合格则停止，不能用夸张俯仰、16mm 或整体隐藏房间强行通过。

## 空间算法

| 空间 | 主角 | 默认参考面 | 必检关系 |
|---|---|---|---|
| 客厅 | 完整沙发组或电视组 | 主背景墙 | 客餐厅、阳台开口、主要采光 |
| 餐厅 | 桌与全部餐椅 | 餐边柜墙或连续墙 | 餐椅朝桌、厨房/客厅关系 |
| 厨房 | 最长连续操作柜面 | 柜体后墙 | 台面、灶台、水槽、开口顺序 |
| 卧室 | 床、床头与床头柜 | 床头墙 | 床头贴墙、衣柜和通道 |
| 卫生间 | 台盆/坐便/淋浴组合 | 关键洁具墙 | 门、湿区和镜柜关系 |
| 书房 | 桌椅工作组 | 书桌或收纳墙 | 采光和通道 |
| 玄关/过道 | 通行轴与尽端开口 | 尽端墙或门 | 背景房间必须保留 |
| 阳台 | 功能尽端和长轴 | 尽端墙/栏杆 | 客厅分界与室内外关系 |

详细字段见 [references/room-algorithm-matrix.md](references/room-algorithm-matrix.md)。

## 遮挡规则

- 默认 `contextPolicy=preserve-visible-adjacent-spaces`。
- 默认 `occlusionPolicy=ray-blocking-local-elements-only`。
- 不隔离整间房，也不隐藏与射线无关的后方空间。
- 每个 `hiddenElementId` 都要有原生 raycast 证据、被挡锚定物和 Agent 截图复核。
- `preserveElementIds`、`preservedBackgroundRoomIds`、`mustShowElements` 不能与隐藏清单相交。

## 原生截图和双状态证据

每个 accepted shot 必须由同一原生模型、同一相机、同一帧状态输出：

- `*.slot-guided-concrete.png`：Q1。隐藏全部活动家具和柜体，只保留水泥墙、地面、真实门窗和结构光影；不得绘制槽位轮廓、半透明色块、编号或其它替代家具的视觉形状。它是默认图像生成唯一结构参考。
- `*.furnished-qa.png`：Q2。同一水泥墙地面、同一模型、同一相机显示资产库家具和柜体，仅用于人工四象限审阅；任何情况下都不得提交给图像模型或成为生成形状权威。
- `*.camera-plan-evidence.png/json`：同一原生相机的二维位置、方向、视锥、焦距和高度证据。
- Entity ID、Room ID、Depth 或 CAD 拓扑遮罩：按后端真实能力产生。CAD 没有 Snapshot Depth/Entity-ID 时不得写成已有；它必须用同 STEP 派生的 occurrence 拓扑和同一相机执行 Z-buffer 生成语义区域。
- `scene-semantic-frame.v4`：写入 `modelBackend` 与 `sourceModelSha256`。

本 Skill 只生成 Q1/Q2 两个证据状态；下游生成模式固定为 `slot-guided`，不再存在模式选择。

截图并发与 ImageGen 并发是两套资源模型：截图消耗本机 Chrome/Blender/CAD、GPU、RAM 和 `/tmp`，设备级硬上限为 `2`；ImageGen 是远端、逐 job 持久化调用，由渲染链按依赖决定，最高可为 `5`。不得把 ImageGen 的五路额度用于启动五个本机截图进程。

## 封闭世界视图合同

`shot-scene-map.v9.closedWorldView` 是当前镜头唯一、完整、封闭的可见事实：

- 房间只有在主空间可见、包含可见功能对象，或可见像素面积与宽高达到统一阈值时才进入提示词；相机后方、画外、被遮挡或仅剩不可读边缘碎片的空间必须排除。
- 门窗/通道必须同时满足：所有室内端点都已进入当前可见空间集合、洞口四角全部位于相机前方、存在完整前向投影。仅有拓扑相邻或混合前后角点投影不得进入 scene map。
- prompt-facing scene map 只保存 `included=true` 的房间与连接；结构 `roomIds` 必须裁切到当前可见房间，槽位必须归属唯一可见房间。完整 included/excluded 决策只写入 QA-only `visibility-audit.v1`，禁止进入图像模型。

- `required.roomIds/connectionIds/structureIds/placementSlotIds` 必须与同机位原生语义逐项完全相等；空数组表示该类对象在本镜头中一个也不允许出现。
- `placementSlots[]` 必须逐槽位保留类别、数量、所属空间、世界坐标、占地尺寸、朝向、局部轴和图像区域；`placementRelations[]` 必须保留朝向目标、贴墙、接触和组合关系。Q1 即使隐藏家具和柜体，JSON 也不得删除、合并或改写这些事实。
- `required.placementSlotInventory` 只作为封闭世界 ID/类别/数量/房间索引，不重复保存完整几何；完整位置与关系只以同文件的 `placementSlots[]/placementRelations[]` 为权威。
- `forbidden.inferenceClasses` 固定禁止未登记空间、门、窗、通道、结构、活动家具、柜体、家电和洁具；不能靠渲染模型自行补全。
- 凡连接到 `exterior` 的开口都必须生成 `boundaryTerminations`。入户门只能表现为“现有门扇关闭”或“现有门扇打开并通向室外”；绝不允许延伸成另一个室内空间。
- 可自由新增的类别只有策略列出的非结构饰品、挂画、灯饰、非结构吊顶细节和软装配饰。它们不能创建空间、开口或功能槽位，也不能堵塞开口与净空。

本合同由机位 Skill 从同帧原生证据单向编译。渲染 Skill 只能消费，不能重新识别、扩写或删减。

## 标准流程

1. 校验动线 result 与原生模型清单：

```bash
python3 scripts/validate_circulation_gate.py circulation-result.json native-model-manifest.json
```

2. 校验结构 v3、原生模型清单、model scope、模型哈希、捕获适配器和能力。单空间 `captureScope` 必须逐字继承模型的主空间、允许上下文和排除空间。
3. 运行 `solve_frontal_camera_seeds.py`，为 `captureScope` 中每个空间生成唯一正视种子；算法输出不向用户请求确认。
4. 原生适配器一次登记全部种子的三个 envelope、背景墙、可后退区域和 `mustShowElements`，输出 `native-camera-envelope-measurements.v1`。
5. 运行 `compile_camera_candidates.py` 一次生成全部空间固定排序的可拟合候选；可后退深度必须由宿主空间多边形和射线交点计算，不接受自报值。camera plan 必须绑定该 batch，禁止按空间手工重抄候选参数。
6. 用后端原生适配器先生成第一张候选预览并执行投影门禁。通过即选中并停止；失败时记录机器可读 `failureCodes`，只再生成下一张回退预览。`candidateAudit` 必须保留固定顺序、实际截图和首个通过者。
7. 写入同时绑定正视种子集与候选 batch 的 `camera-plan.v8`，运行：

```bash
python3 scripts/validate_camera_manifest.py camera-plan.json native-model-manifest.json structure-data.json
```

8. 调用统一入口：

```bash
python3 scripts/capture_model_views.py \
  --model-manifest native-model-manifest.json \
  --camera-plan camera-plan.json \
  --structure structure-data.json \
  --out captures
```

调度器在每次正式截图前和适配器返回后保存压力证据，并占用两个全局截图槽位之一。资源门拒绝时先清理已确认无活动任务关联的旧临时目录或等待设备恢复，不能绕过门禁、直接调用后端适配器或降低为手工截图。

9. 从原生 semantic frame 按 `view-visibility-policy.v1` 编译 `shot-scene-map.v9`。先过滤相机后方/画外/遮挡/边缘碎片空间，再过滤缺少完整前向投影的连接；将当前提示词可见结构、组件和 `relationHints` 逐 ID 写入 required sets、`placementSlots[]` 与 `placementRelations[]`。CAD 若只有彩色截图而缺同 STEP 拓扑 Z-buffer semantic frame，必须停在本步。
10. 从同帧原生语义遮罩复算全部 anchor 和 `mustShowElements`；任何必显对象缺失、anchor 裁切或边距 `<6%` 都必须按固定回退链自动重算，不向用户逐次确认。
11. 算法完成后只做一次并排终审：检查最终主候选、Q1/Q2、二维机位证据和语义遮罩，逐项确认房间、连接、结构和槽位。终审只能接受或把明确错误退回唯一责任源，禁止反复试角、补拍和用主观选片覆盖算法结果。
12. 写入 `scene-map-agent-review.v2`，其中四类 observed 必须精确相等、四类 unexpected 必须全空且 `closedWorldContractAccepted=true`，再运行 `validate_shot_scene_map.py ... --final`。
13. 生成固定 Q1-Q3 证据图；Q1 是无家具、无槽位覆盖的纯水泥结构图，Q2 是同水泥壳体的家具 QA 图，Q3 是平面相机图。由渲染 Skill 在同一 shot 通过终审后回填真正的图像生成 Q4，禁止把四张不同效果图或原生场景截图冒充四象限。

## 错误归因

- 结构墙、房间、开口错误：退回 `interior-floorplan-planning`。
- 原生模型实体、尺寸、组件或碰撞错误：退回当前建模后端 Skill。
- 相机公式、候选、墙法向或遮挡错误：在本 Skill 修正。
- 材质、吊顶、窗饰、柜体造型或风格错误：交给 `interior-space-rendering`，必要时先形成建模修订。

## 停止条件

- 原生模型清单缺失、哈希不一致或没有原生截图能力。
- HTML 清单没有有效 `model-scope.v1`，单空间 camera scope 与模型范围不同，或运行时暴露了排除空间。
- 正式截图绕过 `capture_model_views.py`、未保存设备压力证据、同机超过两个截图作业，或适配器内部并发启动多个浏览器/原生渲染进程。
- 动线 result 缺失、未接受，或其 `nativeModelSha256` 与当前模型不一致。
- 结构 v3 与模型不属于同一 `floorplanId/handoffDigest`。
- 候选不是当前后端原生截图；主候选通过后仍继续试拍；或在没有主候选失败证据时生成回退候选。
- 任一拍摄空间没有功能锚定物或唯一可验证背景墙。
- `captureScope` 中任一空间没有唯一正视种子、没有 `one-point-frontal` 主图，或种子与 camera plan 绑定不一致。
- 正视射线未命中背景墙、画面边距不足、尺度比过大或主角不完整。
- 槽位、房间、开口、实体 ID 或世界坐标无法由原生证据复算。
- `closedWorldView` 与当前 scene map 数组不完全一致、外部边界没有有限终止方案，或任何 `mustShowElements` 在原生帧中不可见。

禁止手填屏幕区域、从截图二次识别事实、复制其他后端的机位 JSON、随机试角度、让 Agent 从无界候选中主观选图，或自动切换出图模式。算法可证明的修正、重算和一次有界回退直接执行；只有上游证据缺失或冲突、用户设计取舍、不可逆/付费/公开操作才集中询问一次。

## 文档路由

- [data_contract.md](data_contract.md)：跨后端模型、机位、semantic frame 和 scene map 合同。
- [playbook.md](playbook.md)：执行、候选评分、退距和视觉复核。
- [references/camera-composition-method.md](references/camera-composition-method.md)：三 envelope 和完整 OBB 构图公式。
- [references/room-algorithm-matrix.md](references/room-algorithm-matrix.md)：逐空间算法。
- [references/shot-scene-map-method.md](references/shot-scene-map-method.md)：原生投影到 scene map。
- [references/capture-review-checklist.md](references/capture-review-checklist.md)：截图复核门禁。
- [scripts_logic.md](scripts_logic.md)：脚本职责。
- [local_runtime.md](local_runtime.md)：运行命令和后端环境。
- [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)：安装、运行时和外部资产边界。
