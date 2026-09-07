---
name: interior-blender-modeling
description: 当用户明确要求把当前可编辑 HTML 户型继续生成精细 Blender 整屋模型、交付 .blend/GLB，或让通用机位算法直接在 Blender 原生场景截图时使用。户型未指定后端时仍先由 interior-html-modeling 生成人机共创当前版。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"source_model_schema":"interior.coauthoring-current-model.v1","native_model_manifest_schema":"interior.native-model-manifest.v1","camera_scene_receipt_schema":"interior.camera-scene-generation-receipt.v1","version":"5.0.0"}
---

# Interior Blender Modeling

## 定位

本 Skill 是 HTML 共创之后唯一的精细 Blender 后端。HTML 只提供事实，不提供 Blender 几何：

- 墙、门窗、房间多边形来自项目唯一 `current-model.json` 与同版 `structure-data.json`；
- 家具只读取 `functionalClass/roomId/x/y/z/width/depth/height/rotationY`；
- Blender 家具从 `assets/blender-component-library/catalog.json` 的原生 `.blend` 精确资产匹配；
- 墙、顶、木地板、湿区地砖、门框和玻璃从 Blender 风格预设生成；
- 禁止导入 HTML 的 GLB、资产锁、代理块、primitive 或跨类别替代。

只有用户明确要求 Blender、`.blend` 或 Blender 原生截图时使用。未指定后端时继续交付 HTML。

## 高频数据入口

1. 项目唯一 `current-model.json/coauthoring-model.json`；
2. 同一 `floorplanId` 的 `structure-data.json`；
3. `assets/blender-component-library/catalog.json`；
4. `assets/blender-style-presets/warm-modern-neutral.json`；
5. `assets/blender-material-library/catalog.json` 的墙、顶、干区地板和湿区地板 PBR 模板；
6. Camera 冻结的 `interior.algorithmic-camera-plan.v3`。

## 唯一流程

1. `init_blender_model_project.py` 绑定当前模型、结构、Blender 资产目录、风格预设和后端选项。
2. `build_floorplan_scene.py` 生成结构和分房间地面；按房间风格标签在同一 `functionalClass` 的多款资产中确定性选型，每个选中款只加载一次，其它实例共享不可变网格与材质数据。
3. 每件家具按 JSON 尺寸精确缩放。非 Z-up 来源先按 catalog 登记的轴向和预旋转归一；柜体、床、沙发、卫浴、电器按背面/床头面靠墙，餐椅朝餐桌、办公椅朝书桌、休闲椅朝空间锚点。
4. 建筑面不再使用随机 Noise/Brick 冒充材质；墙、天花、暖木地板和湿区陶瓷砖分别加载受管 CC0 1K Diffuse/Roughness/Normal 模板，以物理尺度 Box 投影并按风格做暖白混色与微凹凸。
5. 保存自包含 `.blend`、派生 GLB 和 `interior.blender-build-report.v5`，再重新打开验证四套 PBR 建筑模板；正式视觉只由逐空间 Eevee 图片和总览联系表表达。
6. Camera 只在 HTML 当前版运行一次公共求解器并冻结 `interior.algorithmic-camera-plan.v3`；Blender 不重新求角度。
7. `capture_blender_batch.py` 为每张冻结机位启动一个受管 Blender 进程；单图适配器在 Eevee 分配纹理前删除非目标房间家具并清理孤儿数据，再以 960×600、16 samples、AgX、房间顶光和相机补光输出真正的材质渲染。

## 硬合同

- 坐标唯一为 Three.js `[x,y,z] -> Blender [x,-z,y]`。
- 固定集合为 `STRUCTURE/OPENINGS/FLOORS/CEILINGS/FURNITURE/LIGHTS/CAMERAS/ANNOTATIONS`。
- 所有家具必须精确命中 Blender catalog，`unmatchedFurnitureCount=0`、`primitiveFurnitureFallbackCount=0`。
- catalog 每项必须登记 `functionalClasses/path/sha256/styleTags/frontAxis/orientationMode/scalePolicy`；非 Z-up 资产另登记 `sourceUpAxis/preRotationEulerDegrees`。本版只接受 `scalePolicy=exact-dimensions`。
- 组件根节点必须保存资产身份、房间、功能类、来源尺寸、前向轴、朝向模式、优先墙或关系目标及最终旋转。
- `.blend` 必须自包含可用贴图；不得依赖 HTML 项目目录或浏览器缓存。
- 建筑面必须精确命中 `interior.blender-material-catalog.v1`，Diffuse/Roughness/Normal 三图摘要必须一致；缺图即停止，禁止退回程序色块。
- 正式截图必须为 `BLENDER_EEVEE_NEXT`，不得退回 Workbench 白模；事实 JSON 必须记录目标房间裁剪策略、样本数和实际引擎。
- Camera plan SHA、position、target、FOV、windowCenter、显隐和裁切不得在 Blender 中改写。

## 停止条件

- 当前模型与结构项目身份冲突；
- Blender catalog 缺少功能类、文件或摘要变化；
- `.blend` 保存/重开失败，或原生截图技术失败；
- 需要付费下载、公开发布或其它不可逆动作但未授权。

构图提示和运行时间不阻断已有交付。失败修唯一编译器、资产登记或批处理适配器，不恢复 HTML GLB、方盒或降级分支。

## 文档路由

- [playbook.md](playbook.md)
- [data_contract.md](data_contract.md)
- [scripts_logic.md](scripts_logic.md)
- [local_runtime.md](local_runtime.md)
- [templates.md](templates.md)
- [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)
- [references/architecture.md](references/architecture.md)
- [references/contracts.md](references/contracts.md)
- [references/skill-manual.md](references/skill-manual.md)
- [references/skill-flowchart.svg](references/skill-flowchart.svg)
- [SKILL_MANUAL.pdf](SKILL_MANUAL.pdf)

平台创建、上传和公开发布仍只交给 `idk-canvas-ingest-agent`。
