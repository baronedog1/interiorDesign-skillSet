# 结构基线差分方法

## 为什么不直接使用规范最小值

动线审计面对的是已经存在的户型。原卧室小、原走廊窄，不代表设计任务可以拒绝，也不代表 Agent 有权改墙。直接拿统一最小值做硬门禁，会把原户型责任错误归给当前布局。

## 两层比较

1. `structuralBaseline`：冻结红墙和真实开口、不放家具时的最大可通行能力。
2. `currentLayout`：加入当前落地家具和柜体后的能力。

目标值只用于评价布局是否浪费了原本可用空间：

```text
effective = min(target, baseline)
layout passes when current + tolerance >= effective
```

## 责任边界

- baseline 不足：披露事实，不阻断。
- current 比 effective 更差：调整布局。
- baseline 与 current 都不可计算：先查证据完整性；确认结构本来不可达后作为 source constraint。

## 不参与的指标

房间面积、房间长宽、原始厨房/卫生间尺度和原走廊绝对宽度不构成本 Skill 的硬拒绝项。无障碍或法规专项可由独立合规审查处理，不能偷偷改写本 Skill 的责任边界。
