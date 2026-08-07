# CAD B-rep 架构

完整户型 CAD 以一个 accepted STEP assembly 为唯一场景事实。建筑构件、组件和机位 sidecar 使用稳定 ID 关联，不用 STEP 层级顺序作业务 ID。

结构 B-rep 可由 build123d/OpenCascade 建立；组件必须导入已登记 STEP。所有缩放为统一比例，避免椅子、沙发和柜体被 X/Y 非等比拉坏。

CAD 原生截图使用 accepted STEP、真实 `#o...` occurrence selector 显隐和同一 camera plan。当前 CAD Snapshot 生成原生彩色图，但不导出逐像素 ID/depth；清单因此必须如实声明两项为 `false`。`cad_semantic_projection.py` 通过同一 STEP、同一相机逐 selector 隔离与像素差生成槽位和房间语义蒙版，不做截图识图。该适配器未产出或未验收时，允许完成机位候选与原生截图，但必须停止 scene map 和渲染交接。
