# 三后端适配

## 共同规则

三个后端读取同一个 handoff，但当前布局必须来自各自原生模型。适配器只统一平面轮廓，不转换资产、不代理渲染，也不修改后端文件。

## HTML / Three.js

读取 `interior.component-layout.v5`。源图对象由冻结 `bbox-normalized` 轮廓、当前尺寸、平面中心和 `rotationY` 计算；正式轮廓以组件中心为原点且坐标范围为 `-0.5…0.5`。方向读取 `layout-relation-hints.v3` 与 placement 的 `worldOrientation`。设计新增对象必须给绝对 `planFootprint`。

## Blender

读取 `interior.blender-entity-index.v2`。`worldTransform.position[x,z]` 按 `interior-world-y-up.v1` 转到左上角平面坐标；源描线轮廓还必须应用当前 `worldTransform.scale[x,z]`，非等比缩放不能漏算。设计新增物使用绝对精确 footprint，不能用 AABB 或渲染截图反推。

## CAD / Text2CAD

读取 `interior.cad-entity-index.v1`。使用原生 occurrence 的当前 placement、平面缩放和同一坐标合同；STEP 三角网格或屏幕包围框不能替代源轮廓。

## 调整

候选只描述目标平面变换。真正写回由相应建模 Skill 完成，并导出新 manifest、原生模型哈希和布局状态。三种后端均须从新状态重新审计。
