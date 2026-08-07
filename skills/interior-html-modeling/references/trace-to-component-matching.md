# 描线到公共组件路由

## 输入

每个 `interior.trace-components.v2` 对象必须包含唯一 `traceId`、accepted `sourceObjectCandidateId`、`movable-green|fixed-purple`、平台类型文字、`shapeClass`、米制宽深/中心/方向，以及同一来源轮廓和哈希。

## 路由

1. 先按 `semantic` 读取对应运行目录；不得跨目录取件。
2. 目录条目都来自同一 `public-assets.json`，运行分区不拥有第二套来源事实。
3. 在分区内先按功能类别、用途标签和安装方式排除错误类型，再按 `shapeClass`、人数和尺寸排序；风格证据最后参与排序。
4. 自动匹配时，普通公共模型只允许等比例缩放，目标宽深与原型比例差超过 25% 的候选直接排除。只有目录审核为 `axis-limited` 的直线柜体按各轴范围匹配。用户明确要求用通用成品替换来源净空条带时，可走带 accepted `visualFitReview` 的显式 authored-model-preserved 路由；模型仍保持等比，差异必须如实记录。
5. 同一原子 `functionalClass` 内存在多个合格候选时，按风格证据、尺寸拟合、文本证据和稳定资产 ID 排序后确定性选择第一名，不要求用户二次确认；只有该原子类别没有任何合格资产时才停止并报告缺口。
6. 显式 component ID 仍须满足分区、功能、形态、风格排除项和许可；超出自动比例阈值时必须满足上一条的复核证据，不能静默绕过。
7. 木色和名称含 Chinese 不能生成新中式标签；`old/vintage/antique/ornate/traditional` 条目不得自动进入新中式方案。`styleNeutral` 的通用柜体可由材质层表达方案风格。

## 两种几何事实

- 来源描线：唯一决定位置、方向和碰撞脚印，必须原样保留。
- 公共 GLB：唯一决定可见三维外形。默认只做等比例缩放；审核过的直线柜体可在 catalog 范围内分轴调整。

二者不能合并成“模型已按轮廓精确重塑”的假事实。`traceReshape.mode` 固定为 `proportional-authored-model-with-trace-footprint`，同时保存 width/depth 比例、实际 uniform scale 和比例差。

```json
{
  "matchMethod": "semantic-shape-proportional-source-score",
  "evidence": {
    "targetFootprintExact": true,
    "authoredGeometryScalePolicy": "uniform-only",
    "outlineBoundToCollisionFootprint": true,
    "proportionalScaleSpread": 0.08,
    "traceReshape": {
      "mode": "proportional-authored-model-with-trace-footprint",
      "builderUniformScale": 1.12
    }
  }
}
```

显式提示使用 `explicit-proportional-source-route`。

## 数量与禁止项

每个 accepted 对象对应一个 match 和一个来源 placement；数量、`traceId`、`sourceObjectCandidateId` 和轮廓哈希一一对应。用户明确补齐的功能件以 `user-explicit-addition` 单独登记，不进入来源数量等式，也不得伪造 trace。禁止 fallback、方盒、跨分区、历史复制、对象合并、为避碰移动来源 placement、未声明的非等比拉伸，以及用公共模型轮廓反向伪造来源描线。组合柜的上柜、下柜和设备必须是独立 placement 或真实节点，不能伪造可删除层。
