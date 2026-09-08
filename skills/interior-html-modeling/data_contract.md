# 五项设计链的数据合同

相机可选verticalShift是归一化投影纵向中心偏移，默认0；实际画面NDC.y=原投影NDC.y−verticalShift。截图端通过setViewOffset实现，保持水平镜头，完成后恢复；必须把该字段纳入原cameraDigest，不在截图后裁图替代。

客户偏好是规划Skill维护的 `interior.requirements/1` 独立JSON，不改几何schema；结构详见[访谈与需求交接](../interior-floorplan-planning/playbook/requirements-interview.md)。Agent先读同名 `.requirements.json`（或已明确交接路径），落实到当前layout/customStyle并向下游携带原记录。编译器不会自动推断自然语言需求，也不以缺少可选偏好阻止可独立的结构工作。

平面只生成 `interior.layout/1` JSON；HTML 编译生成 `interior.scene/1`；机位生成 `interior.cameras/1` 和 `interior.renders/1` 真实 WebGL 参考截图；效果图使用 `interior.ai-request/1`、`interior.native-image-job/1`、真实宿主调用回执及 `interior.ai-result/1`。平台另用 `baiende.project-binding.v1`，不污染布局。

schema 的唯一机器定义位于 `scripts/engine/schemas/`。米制，平面 [x,z]、三维 [x,y,z]，Y 向上，rotationY 用度，组件地面中心原点、正面 +Z。墙 a/b 为中心线，开口 offset 从 a 到起边；rooms 多边形计面积，openConnections 代表无墙开放连接。

placements 包含 id/componentId/roomId/position/size/rotationY，size=[宽,高,深]；rooms.subjectIds 指向本房真实主体。source 记原图、尺度和估算；不能省略来源再声称精准。

nativeAssets 内嵌静态 GLB，placement.nativeAssetId 绑定；forward/deform/size 描述实际正面与缩放能力。materialOverrides 按材质名保存。customStyle 是完整当前配方，其中 forms 固定当前造型，materials/materialRecipes 为可换 CMF。measurements 两点均在地面，measurementUnit 是 m/mm。

sceneKey/layoutHash/htmlSha256/cameraDigest 绑定实际文件内容。用户修改源布局或 HTML 后应重新导入编译与截图，不使用旧回执。哈希不是审美验收。

观察报告 errors/warnings 保留问题原貌，technicalErrors 只列不能计算的格式/引用/不支持表达；compilable 表示能生成草稿，ok 不等于客户认可。相机 ready/review/blocked 都可作为技术有效的截图候选，blocked 是搜索失败提示，不隐藏它；不能将候选当已验收作品。

原生生成回执必须来自实际宿主调用；prepared-not-generated 不代表生成完成。图片复核记录结构、门窗、家具、机位 pass/fail；有问题仍交付实际结果并说明，再修源输入，不通过自动重试藏问题。

原生参考模式 referenceMode 默认 furnished；只有明确的白模要求才为 empty-slots 并记录 whiteModelRequested=true。截图 row 记录 hiddenPlacementIds，必须对应原布局全部 placements；原 JSON 不删家具或柜体。请求 placementSlots 保留 id/componentId/roomId/position/size/rotationY；产品参考通过 placementId 绑定，sizeMetres 是真实产品尺寸，未知用 null，不从槽位伪造。requiredReview 增加 furnitureDetail/assetIdentity/assetScale。clay 是材质显示模式，不能代替 referenceMode。

渲染referencePolicy为shell-layout-design-v2并参与seriesKey：粗模只定义结构/机位/布局，锁款从精细参考图片取得。--products读JSON列表，每项{placementId,path,sizeMetres?}；sizeMetres仍是[宽,高,深]米，未知省略或null，不能以粗模尺寸代填。输出productReferences标记role=furniture-identity-reference、identitySource=reference-image-not-proxy。referenceGuide列实际附图顺序及职责，不引入第二套图片路径。产品参考与粗模截图完全同内容时报错，避免同一图冒充两种事实；图片里具体对象的识别仍由Agent负责。

sourceFrame记录源宽/高/比例，ai-result保存outputFrame与frameObservation.sameAspectRatio，画幅差异不阻断已生成图交付，也不自动拉伸。比例相同不证明几何保真。精细参考/定样决定款式但不提供新的建筑或镜头；没有款式参考时只能称概念首图。二维渲染不回写HTML网格，HTML现有编辑/CMF合同不变。

ai-request可通过--design-brief读取{common:{},spaces:{roomId:{}},styleReferences:[{path,assetId?,notes?}]}。common与当前空间条目合并为designIntent，真实图转为styleReferences并参与附图顺序及seriesKey。顺序为当前结构截图、同系列精细定样、placement绑定产品图、风格设计图；最后一种不提供户型或产品身份。metrics.deliveryRole为primary/supplement/layout-reference，只表达用途，不作为阻断生成的门禁。

productReferences保留逐placement绑定；native_image.references按(role,sha256)合并实际附件，每张图的placementIds列出全部绑定，referenceGuide与job顺序同源。不删除绑定，不设置虚构的统一图数上限。同开放空间各机位使用相同完整产品清单；清单变化代表选型变化，应重新建立定样。床头正视metrics.framing=bed-head-and-upper-bed，fullSubjectProjection始终单独记录全床，构图完整不等于全床入画。组件catalog的shape区分直排/贵妃位与座数，风格不会覆盖该结构。

## 图像内槽位交接

`placementSlots` 保留完整世界坐标；`cameraFrame` 保留实际冻结相机。`imageSlotAnchors` 只列当前连通空间中投影与画面相交的实例，以同一相机把旋转包络投影为左上原点的 0–1 范围；先裁近裁面，再执行透视或正交投影及镜头偏移。它是位置/约略尺度参考，不是可见遮罩、产品轮廓或缩放目标；不可将画外物体搬进画面或拉伸产品填框。

`productReferences` 是连通空间完整产品绑定，参与同系列身份计算；`frameProductReferences` 是投影与当前画面相交的绑定，仅后者进入当前提示词与实际附图。缺省该字段才兼容旧请求，显式空列表不能回退整套产品。产品未入本镜头不等于系列换款；投影不证明墙后可见性。

绘图提示词不混入世界 `position/rotationY`。由组件正面轴和当前相机基底计算 `cameraRelativeYawDegrees`：0为正面、±90侧面、180背面；床的正面是床尾看床头。世界字段仍完整保存在JSON。`imageBoundsUnclipped01` 传递裁切前范围，避免将被裁切家具重新收进画面；它依然只是包络，不是产品比例目标。

空槽截图现在同次生成主图与 `shotId.layout.png`。renders行的 `layoutReference` 保存同一sceneKey、cameraDigest、图片摘要和 `same-camera-layout-only` 职责；ai-request/native-prepare原样交接到 `layoutReferences`。这张辅助图只直观表达JSON中的家具数量、方向、前后遮挡和裁切，绝非款式/材质/光照来源。默认furnished仍单图；历史冻结请求不修改，后续空槽任务重新截图取得配对输入。复用截图时检查配对文件仍在且摘要一致，缺失则按同相机重截，不猜布局。
