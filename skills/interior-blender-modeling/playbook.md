# 执行 Playbook

## 1. 冻结布局事实

读取项目唯一 `current-model.json/coauthoring-model.json` 与同一 `floorplanId` 的 `structure-data.json`。HTML 只负责结构与家具 transform；不得读取 HTML GLB、资产锁或旧 `.blend` 作为 Blender 几何。

## 2. 解析精细资产与朝向

按 `functionalClass + room style tags` 在 Blender catalog 中选择原生 `.blend`。普通卫生间、主卫、厨房和阳台可使用同类不同款；未通过轴向/组合审查的下载资产标记 `research-only`，不能进入生产。按 JSON 宽深高精确缩放，位置保持不变；非 Z-up 资产先归一轴向。每项记录候选数、匹配标签、来源 yaw、前向轴、优先墙、关系目标和最终 yaw。

## 3. 编译与材质

结构、洞口、房间地面和天花由代码生成；建筑表面从材料 catalog 读取受管 PBR 三图。墙使用暖白细灰泥，天花使用低凹凸白灰泥，干区使用暖木板，厨房、卫生间、主卫和阳台使用室内陶瓷砖。无 UV 程序几何统一使用三轴 Box 投影和登记物理尺度；缺图或摘要变化立即停止。家具与建筑贴图随后一起打包进自包含 `.blend`。

## 4. 原生验收

重开 `.blend` 检查八个集合、组件根、实体标签、资产摘要、朝向字段、家具数量、零未匹配和零 primitive。失败只修 catalog、编译器或输入事实。

## 5. 冻结机位原生截图

Camera 先在 HTML 当前版求解一次 v3 计划。Blender 只执行相同 plan。Ubuntu 使用 `capture_blender_batch.py` 每张图单独启动受管 Blender；单图适配器在 Eevee 加载纹理前移除非目标房间家具与地面并清理孤儿数据，只保留结构及当前空间精细资产，然后应用冻结坐标、FOV、windowCenter、显隐和 projectionCrop。

## 完成标准

`.blend` 可重开、贴图自包含、全部家具由精确资产组成；十张截图与同名 JSON 绑定同一 `.blend` 和同一 plan，批处理回执 `requested=delivered`、`failed=0`。
