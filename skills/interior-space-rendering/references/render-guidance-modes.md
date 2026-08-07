# 唯一槽位引导生成模式

## 槽位引导模式

这是默认模式。完整白模中的临时外形、材质和颜色可能误导绘图模型，所以发送同一机位的水泥毛坯结构图。活动家具和柜体在图片中隐藏，但仍以 placement slot 保留在 JSON。水泥皮肤让墙、地、开口和光影更容易阅读，但只是输入提示，最终必须替换为用户目标风格。

每个 slot 记录模型 ID、类别、房间、米制尺寸、世界变换和图片区域。图像模型可重做产品外观，但不能改变槽位的类别、数量、位置、尺寸或方向。

“隐藏”只发生在源图片像素中，不发生在数据合同中。`closedWorldView.required.placementSlotInventory` 必须保留当前镜头全部可见房间的每件活动家具、柜体、家电和洁具；少一个必须拒绝，多生成一个同样必须拒绝。

Q2 组件图只证明槽位 JSON 与原生模型同源，并用于四象限人工核对。它在任何情况下都不发送给图像模型；用户要求保留某一具体产品时，使用逐槽位绑定的产品参考图，不把整张白模提升为形状权威。

## MediaInfo 差量

Original Media 表示当前模式下的空间截图且无风格。Target Media 表示同一空间和机位的目标风格：

- `spaceLayout`、`hardDecoration` 永远不变；
- `softDecoration` 只能在锁定槽位中选择同类别造型；
- `style`、`lighting` 按用户目标变化。

`render-plan.v11`、context、prompt manifest 和 request 都只接受 `slot-guided`。请求只提交纯水泥 Q1、精确 JSON、已绑定产品参考和依赖图允许的 accepted 身份参考；Q2 与 masks 永远只用于 QA。
