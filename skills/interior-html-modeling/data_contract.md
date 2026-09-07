# 五项设计链的数据合同

客户偏好是规划Skill维护的 `interior.requirements/1` 独立JSON，不改几何schema；结构详见[访谈与需求交接](../interior-floorplan-planning/playbook/requirements-interview.md)。Agent先读同名 `.requirements.json`（或已明确交接路径），落实到当前layout/customStyle并向下游携带原记录。编译器不会自动推断自然语言需求，也不以缺少可选偏好阻止可独立的结构工作。

平面只生成 `interior.layout/1` JSON；HTML 编译生成 `interior.scene/1`；机位生成 `interior.cameras/1` 和 `interior.renders/1` 真实 WebGL 参考截图；效果图使用 `interior.ai-request/1`、`interior.native-image-job/1`、真实宿主调用回执及 `interior.ai-result/1`。平台另用 `baiende.project-binding.v1`，不污染布局。

schema 的唯一机器定义位于 `scripts/engine/schemas/`。米制，平面 [x,z]、三维 [x,y,z]，Y 向上，rotationY 用度，组件地面中心原点、正面 +Z。墙 a/b 为中心线，开口 offset 从 a 到起边；rooms 多边形计面积，openConnections 代表无墙开放连接。

placements 包含 id/componentId/roomId/position/size/rotationY，size=[宽,高,深]；rooms.subjectIds 指向本房真实主体。source 记原图、尺度和估算；不能省略来源再声称精准。

nativeAssets 内嵌静态 GLB，placement.nativeAssetId 绑定；forward/deform/size 描述实际正面与缩放能力。materialOverrides 按材质名保存。customStyle 是完整当前配方，其中 forms 固定当前造型，materials/materialRecipes 为可换 CMF。measurements 两点均在地面，measurementUnit 是 m/mm。

sceneKey/layoutHash/htmlSha256/cameraDigest 绑定实际文件内容。用户修改源布局或 HTML 后应重新导入编译与截图，不使用旧回执。哈希不是审美验收。

观察报告 errors/warnings 保留问题原貌，technicalErrors 只列不能计算的格式/引用/不支持表达；compilable 表示能生成草稿，ok 不等于客户认可。相机 ready/review/blocked 都可作为技术有效的截图候选，blocked 是搜索失败提示，不隐藏它；不能将候选当已验收作品。

原生生成回执必须来自实际宿主调用；prepared-not-generated 不代表生成完成。图片复核记录结构、门窗、家具、机位 pass/fail；有问题仍交付实际结果并说明，再修源输入，不通过自动重试藏问题。

原生参考模式 referenceMode 默认 furnished；只有明确的白模要求才为 empty-slots 并记录 whiteModelRequested=true。截图 row 记录 hiddenPlacementIds，必须对应原布局全部 placements；原 JSON 不删家具或柜体。请求 placementSlots 保留 id/componentId/roomId/position/size/rotationY；产品参考通过 placementId 绑定，sizeMetres 是真实产品尺寸，未知用 null，不从槽位伪造。requiredReview 增加 furnitureDetail/assetIdentity/assetScale。clay 是材质显示模式，不能代替 referenceMode。
