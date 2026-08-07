# 原生 Scene Map 方法

## 唯一链路

```text
native model + accepted camera-plan.v8
  -> native RGB / Entity ID / Room ID / Depth
  -> scene-semantic-frame.v4
  -> exact visible rooms / connections / structures / placement slots
  -> closedWorldView required + forbidden + exterior terminations
  -> view-visibility-policy.v1
  -> shot-scene-map.v9
```

HTML 使用 GPU Entity ID 与深度；Blender 使用 Object Index 与 Z pass；CAD 使用实体 ID 与深度。三者都在同一原生相机帧内把冻结房间多边形和开口投影到画面。

## 禁止替代

- 不从 RGB 截图识别家具、房间或开口。
- 不用另一后端导出的代理模型生成语义。
- 不手填 bbox、房间或组件类别。
- 不在 scene map 中选择渲染模式。
- 不把“图中没登记的对象”留给下游猜测。required 中未列出的空间、开口、结构和功能对象一律视为不存在。
- 不因槽位引导图隐藏组件而删除 JSON 槽位；相邻空间中只要在原生语义帧可见，就必须逐件进入 placement slots。

## 反向验证

`validate_shot_scene_map.py` 回读 semantic frame、所有图像哈希、相机证据、实体和槽位，并从 scene map 数组重新计算 `closedWorldView`。任何后端/模型哈希、区域、类别、世界变换、数量、封闭集合或外部边界终止差异都会拒绝交接。
