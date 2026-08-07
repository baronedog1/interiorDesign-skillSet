# 分空间机位 Reference

每个文件都是一种空间的“自然语言预期 + 可测量算法 + 视觉验收”模板。案例没有可复制坐标；所有长度、朝向和可后退深度必须从当前 accepted HTML、Blender 或 CAD 原生模型读取。

| 空间 | Reference |
|---|---|
| 客厅 | [living-room.md](living-room.md) |
| 餐厅 | [dining-room.md](dining-room.md) |
| 厨房 | [kitchen.md](kitchen.md) |
| 卧室 | [bedroom.md](bedroom.md) |
| 玄关/过道 | [entry-corridor.md](entry-corridor.md) |
| 阳台 | [balcony.md](balcony.md) |
| 卫生间 | [bathroom.md](bathroom.md) |
| 书房/多功能 | [study-multifunction.md](study-multifunction.md) |

## 共同模板

1. 从对象语义和几何中确定锚定物、锚定物正面、参考墙/功能立面、必须出现对象和合法相机区域。
2. 先写预期成片：第一视觉中心、前中后景、左右留白、真实连通空间和光向。
3. 数值参数统一读取 [../../assets/room-camera-algorithms.json](../../assets/room-camera-algorithms.json)，公式解释只读 [../room-algorithm-matrix.md](../room-algorithm-matrix.md)，本目录不复制第二份数值事实。
4. 正式 `distortion=0`，任何空间都不能用鱼眼或弧边换取画幅。
5. 每个拍摄空间先由 `solve_frontal_camera_seeds.py` 生成唯一 `one-point-frontal` 主种子，只截图首个可拟合候选；机器门禁失败时最多再截图一张回退候选。Agent 只验收，不从无界候选中主观选图。
6. 真实连通空间只要不遮挡就保留；仅隐藏明确挡住锚定物的最少对象。
7. 相机、焦点、焦距、显隐或光源改变后，公式、投影、遮挡和光向全部重验。

机器参数只在 `assets/room-camera-algorithms.json` 维护；本目录文件只解释空间主角、上下文和视觉淘汰条件。
