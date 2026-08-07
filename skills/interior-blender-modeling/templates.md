# 模板与资产索引

## 唯一空场景模板

`assets/blender-template/build_template_scene.py` 只创建 `STRUCTURE`、`OPENINGS`、`FLOORS`、`CEILINGS`、`FURNITURE`、`LIGHTS`、`CAMERAS`、`ANNOTATIONS` 集合和米制场景。它不含户型坐标或案例家具。

`assets/blender-template/backend-options.json` 是天花、窗型、阳台、墙端点编辑、连续碰撞和双外观的唯一后端选项。项目可覆盖具体窗 ID 和阳台 ID，但不能改变上游洞口边界。

## 组件资产

`assets/blender-component-library/catalog-policy.json` 维护来源许可、语义覆盖和轴审阅。`index_blender_asset_store.py` 读取 `$INTERIOR_BLENDER_ASSET_STORE` 生成运行目录；`.blend`/GLB 原文件不复制进其它 Skill。

组件仅由 `blender-asset-selection.json` 引用。目录中未 `accepted`、许可不在允许集合或哈希变化的资产不能进入模型。
