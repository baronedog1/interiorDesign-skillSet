# 数据合同

## 输入

- 当前模型：`meta.sourceFloorplanId`、`floorBoundary/walls/openings/rooms/furniture`。
- 结构补充：同版 `structure-data.json` 房间多边形和空间类型。
- 家具字段：`id/functionalClass/roomId/x/y/z/width/depth/height/rotationY/sourceTraceId`。
- Blender catalog：`interior.blender-component-catalog.v4`，支持同功能类多款、房间适用范围、风格标签、来源轴向和选型状态。
- 材料 catalog：`interior.blender-material-catalog.v1`，每个模板登记角色、来源、许可、物理宽度以及 Diffuse/Roughness/Normal 的路径与 SHA-256。
- 风格：`interior.blender-style-preset.v3`，包含家具选型、建筑材料引用、混色、凹凸、物理映射和 Eevee 参数。

HTML 的 `componentId/assetStatus/assetPath` 只作审计信息，不用于导入几何。

## 坐标与朝向

`[x,y,z] -> [x,-z,y]`，单位为米。组件输出登记 `sourceUpAxis/preRotationEulerDegrees/frontAxisLocal/orientationMode/preferredWallId/orientationTargetId/sourceRotationY/resolvedRotationRadians`，并保存 `assetSelection` 的候选数、请求标签、匹配标签和分数。家具最终包络严格匹配 JSON 宽、深、高；转向后的世界 X/Y 包络允许互换。

## 输出

- `interior.blender-model-project.v5`
- `interior.blender-build-report.v5`
- `interior.blender-scene-validation.v1`
- `interior.native-model-manifest.v1`
- `current.blend/current.glb`
- Blender PNG 与同名 `interior.camera-image-facts.v3`
- `interior.camera-delivery-index.v1`

构建报告绑定当前模型、结构、家具 catalog、材料 catalog、风格、原生模型、派生模型、贴图资源策略、逐家具选型和朝向记录。图片事实另记录 `BLENDER_EEVEE_NEXT`、16 samples、目标房间剪枝和实际资源耗时。硬要求未匹配和 primitive 均为 0，四套建筑材料必须存在。
