---
name: interior-space-rendering
description: 当用户要求把已建户型渲染成效果图、指定设计风格、保持空间与机位出图、生成每个机位的标准四象限，或同步完成模型与出图时使用；接收 HTML/Three.js、Blender 或 CAD/STEP 经 interior-camera-capture 生成的 accepted shot-scene-map.v9。默认槽位引导只提交纯水泥空结构 Q1 与精确场景 JSON；Q2 仅作人工审阅。按正视主图优先、共享空间串行继承、互不重叠空间并行的唯一依赖图生成。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"render_plan_schema":"interior.model-image-render-plan.v11","scene_map_schema":"interior.shot-scene-map.v9","render_media_context_schema":"interior.render-media-context.v7","prompt_manifest_schema":"interior.imagegen-prompt-manifest.v7","render_review_schema":"interior.render-agent-review.v4","platform_media_info_schema":"media_info.v1","version":"17.0.0"}
---

# Interior Space Rendering

所有上游文件先按 [data_contract.md](data_contract.md) 的 `semantic-content-first-v1` 发现；推荐目录和文件名只用于排序，不能代替 schema、哈希和模型身份校验。

## 使用前准备

- 本地需要 Python 3.11+、Pillow、可写批次目录，以及当前 Codex 会话可用的原生 `imagegen`；不读取外部图像 API Key。
- 先读取 [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) 与 [local_runtime.md](local_runtime.md)，确认 ImageGen 执行器、batch receipt 和图片输出路径可用。
- 必须已有同一模型/相机哈希的 accepted Q1、Q2、Q3、scene map 与用户风格要求；输入或生成能力缺失时在请求构建前标记 `blocked`，不得用未验截图、旧渲染或原生模型图冒充 Q4。

## 唯一职责

本 Skill 只负责从 accepted 机位事实生成风格效果图，并独占：

1. 每个 shot 的唯一槽位引导生成合同；
2. 墙顶门窗阳台柜体灯具配饰的表面处理方案；
3. 当前机位封闭世界 JSON 的确定性提示词编译；
4. 同空间多镜头的生成顺序、身份继承和并行边界；
5. Q1 纯水泥空结构、Q2 同机位家具 QA、Q3 平面相机、Q4 accepted render 的标准四象限；
6. 结构、相机、对象、空间身份和禁有对象终审。
7. 图像生成有限重试与真实 Q4 回执；原生模型截图不得作为 Q4 回退。

建模几何修改归上游建模 Skill；找机位和当前画面可见集合归 `interior-camera-capture`；平台上传归 `idk-canvas-ingest-agent`。

## 输入

- accepted `interior.shot-scene-map.v9`；
- 同一 scene map 内的 Q1 `slotGuidedConcreteImage`、Q2 `furnishedReferenceImage`、Q3 `planCameraImage`、Entity mask、过滤后的 Room mask；
- 用户指定风格；
- 已在上游模型 Q2、资产 ID 或目标风格 ID 中固化的产品与风格事实；用户在当前项目提供指定家具图片时，必须先编译成 `interior.user-product-reference-manifest.v1`，逐产品、逐槽位绑定后再提交，禁止仅靠自然语言或临时附件猜测；
- 多镜头时必须有 `spaceReferencePlan`。

只有 accepted 原生模型而没有 scene map 时，先执行 `interior-camera-capture`。未指定整屋后端时，上游默认 HTML；本 Skill 不改后端。

## 当前 Shot 的图像与 JSON 权威

- **Q1 纯水泥空结构图**：当前相机、裁切、墙体、开口、天花、地面和外部边界的唯一图像权威。图中隐藏活动家具和柜体，也不画槽位轮廓、色块或编号。
- **scene/context JSON**：功能对象类别、数量、所属空间、世界坐标、占地、朝向、朝向目标、贴墙关系、图像区域和禁有项的唯一布局权威。JSON 未登记的空间、门窗、结构、活动家具、柜体、家电和洁具禁止出现。
- **Q2 同机位家具图**：只用于四象限人工审阅和验证 JSON 是否来自同一模型；任何情况下都不得提交给图像模型，也不得成为形状权威。

Q1、Q2 和 JSON 必须来自同一 `shotId/sourceModelSha256/camera`。先前 accepted 效果图只能约束共享家具、材料和空间身份，永远不能覆盖当前 Q1 的结构和当前 JSON 的布局。

每个 scene map 必须打包正式 `camera-plan.v8`、Q1 和 Q3 camera JSON。渲染前验证器逐字段核对 `position/target/fov/focalLengthMm`，并要求主图仍为 `deterministic-wall-normal-camera-v7` 的 `one-point-frontal`；HTML 的 Q3 还必须声明 `runtimeCameraPlanSource=external-formal-camera-plan-v8`。手写机位、内嵌旧机位、近似复刻水泥截图视角或事后改 render plan 均在 ImageGen 请求前拒绝。

## 唯一生成模式 `slot-guided`

默认模式。请求只提交无组件、无槽位覆盖的 Q1、scene/context JSON，以及当前槽位明确绑定的产品或已接受身份参考。scene map 锁定类别、数量、房间、位置、占地、方向、关系、净空和图像区域；已绑定用户产品的槽位必须使用该产品，未绑定槽位才可按风格优化。不得提交 Q2、Entity mask 或 Room mask 来替代 JSON。

## 当前画面的封闭世界

`shot-scene-map.v9.visibleFrame/closedWorldView` 是提示词可消费的完整集合：

- 只包含当前相机原生证据证明可见的空间、连接、结构和槽位；相机后方、画外、被遮挡或仅剩不可读边缘碎片的空间不得进入 prompt。
- 结构归属、槽位归属、连接端点、`visibleFrame` 与 closed-world 集合必须逐 ID 闭合；任何 `included=false` 诊断项或画外房间 ID 出现在 prompt-facing scene map 时，在生成前直接拒绝。
- `visibilityAudit` 只用于 QA 文件哈希核验，禁止进入 attachment manifest、prompt manifest 和 imagegen request。
- required 项必须出现；未列出的房间、门窗通道、墙体、家具、柜体、家电和洁具禁止出现。
- 入户等 exterior 边界只能使用 scene map 的有限表现，不得延伸成第三个室内空间。
- 只有非结构饰品、挂画、灯饰、非结构吊顶细节和软装配饰可以按 allowlist 新增。
- 渲染不得增删、平移或缩放墙体、开口、房间边界、天花体积和阳台围护。

## 多镜头空间身份

`render-plan.v11.spaceReferencePlan` 是唯一调度事实：

1. 每个 primary room 的第一张必须是经 scene map 证明的 `frontal-master`；
2. 后续 `relation` 镜头必须依赖此前所有与它共享可见房间或槽位的 accepted 镜头；
3. 同一执行批次中的镜头不得共享任何可见房间或槽位；只有完全不相交的空间可并行；
4. 当前 Q1 始终控制当前镜头结构，当前 JSON 控制对象布局；依赖图片只控制共享对象和表面身份；
5. 任一依赖未 accepted，后续镜头不得进入 candidate 或 accepted 状态。

不能把“首图参考”写成普通 `style-guide`，也不能让多个客餐厅镜头各自独立生成。被拒绝、未完成、无 accepted review/receipt 哈希链的候选图禁止以任何角色回流请求；只有依赖计划自动注入的 `accepted-space-identity-reference` 可以继承先前画面。

## 标准流程

1. 验证所有 scene map v9、模型哈希、accepted 状态和标准四象限源合同。
2. 在 `render-plan.v11` 登记每个 shot 的 `primaryRoomId/role/visibleRoomIds/visibleSlotIds/dependsOnAcceptedShotIds` 及执行批次。
3. 每个空间先排正视主图；根据可见集合计算重叠依赖，只有不重叠空间并行。
4. 为每个 shot 写 `architecturalTreatment`，结构策略固定 `preserve-current-model`。
   `projectionLock` 必须由 `build_projection_lock.py` 从 scene map 全量区域编译，禁止人工估算。
5. 运行 `build_scene_prompt_context.py` 生成 context v7，再运行 `build_prompt_manifest.py` 生成 prompt manifest v7；禁止手写 `finalPrompt`。提示词必须小于 32KB，完整事实留在 JSON，不重复转写成长段自然语言。
6. 运行 `build_imagegen_request.py` 编译请求 v4。默认槽位引导只携带 Q1、scene/context JSON、逐槽位产品参考和计划内 accepted 身份参考；Q2 与 masks 保留为 QA 证据但不得提交。
7. 运行 `build_imagegen_batch_plan.py` 生成批任务 DAG，再交给 `imagegen-batch-orchestrator`。每张图有独立 job、请求哈希、状态、回执和输出哈希；同批独立 job 默认最多 `5` 路真并发，完成即落盘，单张失败只重试该 job。共享房间、槽位或身份参考的 job 必须按依赖串行，不能为了凑五路并发拆散。
8. 每个 `frontal-master` 最多尝试 `3` 个候选。第三个仍未通过时停止，不放宽结构合同，也不用原生 Three.js/Blender/CAD 截图顶替 Q4。
9. 成功后记录 imagegen receipt v4。使用独立 invocation 生成 review v4；验证器按 scene map 复算完整 required/forbidden 集合及最大误差，不重复执行已经通过的结构编译或机位算法。
10. accepted 后运行 `build_four_quadrant_delivery.py`，只从同一 scene map、request、receipt、review 生成标准四象限与 evidence JSON。
11. 编排器只释放依赖已经 accepted 的下一批关系图；已成功 job 不因兄弟任务失败而重做。
12. 全部 shot/style 完成后，运行 `validate_render_plan.py render-plan.v11.json --require-complete`。只有该命令返回 `complete=true` 才能报告“渲染完成”或发送完整四象限交付。

## 四象限唯一格式

每个 shot 单独一张四象限：

1. Q1：纯水泥墙地面与结构，无活动家具、柜体或可见槽位覆盖；
2. Q2：同一水泥墙地面、同一原生模型、同一机位的活动家具和柜体；
3. Q3：同一相机在平面图中的位置、方向和视锥；
4. Q4：该 shot 通过独立终审的最终渲染。

禁止用“四张渲染图”“四张平面机位图”或跨 shot 图片冒充。四象限必须由脚本编译，不允许任务现场手工拼版。

## 必过门禁

- scene map 只接受 v9；context v7、prompt v7、request v4、imagegen receipt v4、review v4；
- scene map 的 Q1、Q3 camera JSON 与打包 camera plan 必须哈希有效且机位逐字段一致；主图必须保持正式墙法向正视，禁止用效果图阶段另选角度。
- 唯一槽位引导请求必须有 Q1 与 scene/context JSON，且任何情况下不得提交 Q2、Entity mask、Room mask 或视觉槽位覆盖；
- `spaceReferencePlan` 必须覆盖全部 shot，重叠关系和执行批次由验证器重算；
- 当前 Q1/Q2 哈希必须与 scene map 完全一致；Q2 固定为 QA-only 且永不提交；
- accepted 参考图片必须来自同风格、较早批次并有输出哈希；
- prompt/request 图片角色只允许当前 Q1、计划内 accepted 身份参考，以及经 `user-product-reference-manifest.v1` 验证并逐槽位绑定的 `user-product-reference`；Q2、QA masks、未绑定产品图、被拒绝候选或其它临时图直接拒绝；
- 墙、门窗、空间、槽位 required/forbidden 集合必须贯穿 scene/context/request/review；
- 所有可见槽位、结构、连接必须完整枚举且源区域等于 scene map；任何对象中心误差 `>2%`、对象区域边误差 `>2.5%`、结构或开口区域边误差 `>2%`、对象朝向误差 `>3°` 即拒绝；
- 相机关键点采用最大误差 `<=2%`，主要墙线最大角度误差 `<=1°`；禁止删掉超差对应点后重新取中位数；
- Q4 必须等于已验收 producer receipt 中的 accepted output；
- 每个计划必须使用唯一 `renderExecutionPolicy.v2`：正视主图最多三次 imagegen，失败后停止且不交付 Q4，禁止放宽门禁和原生场景回退；
- Q4 必须具有 `interior.imagegen-receipt.v4`；Three.js、Blender、CAD 等原生截图只能作为 Q1/Q2/Q3 证据，不能冒充渲染图；
- `architecturalTreatment.projectionLock` 必须逐字等于 scene map 推导结果；
- 四象限图固定 `1920x1200` 并有同 shot evidence。
- ImageGen 并发只由依赖图决定，`1..5`；它与本机截图最多 `2` 路的设备资源门完全独立。
- 最终交付必须通过 `validate_render_plan.py ... --require-complete`；任一输出仍为 `planned/candidate/rejected`、缺少 Q4，或缺少 `fourQuadrantEvidence` 路径与哈希时都不得宣称完成。

## 高频数据入口

- [data_contract.md](data_contract.md)：v11/v9/v7/v4 数据合同。
- [playbook.md](playbook.md)：执行、依赖和返工。
- [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)：图像生成环境、凭据与运行边界。
- [references/architectural-styling-playbook.md](references/architectural-styling-playbook.md)：建筑处理。
- [references/ceiling-and-lighting-playbook.md](references/ceiling-and-lighting-playbook.md)：天花与灯光。
- [references/window-door-balcony-playbook.md](references/window-door-balcony-playbook.md)：窗门阳台。
- [references/cabinet-and-decor-playbook.md](references/cabinet-and-decor-playbook.md)：柜体和配饰。
- [scripts_logic.md](scripts_logic.md)、[local_runtime.md](local_runtime.md)：脚本和命令。

## 交付

- `render-plan.v11`、可选的用户产品参考 manifest v1、context v7、prompt v7、request v4、imagegen batch plan/receipt v1、imagegen receipt v4、review v4；
- 每个 shot 的 accepted 效果图；
- 每个 shot 的标准四象限 PNG 与 evidence JSON；
- 后端、模型、相机、可见集合、依赖和输入参考的完整哈希链。

确定性编译、依赖调度、重试顺序和门禁失败修正无需逐次向用户确认。只有图像生成涉及尚未授权的付费、输入事实真正缺失或冲突、用户设计取舍、公开发布或其它不可逆操作时，才集中询问一次；已授权范围内的规范修正直接执行。
