# CAD 模板与资产

## 模板

`assets/interior-cad-template/backend-options.json` 是完整户型 CAD 后端的唯一模板配置，维护天花、窗型、阳台、墙端点补丁、碰撞和双外观能力，不保存案例户型。

## 资产目录

`assets/cad-component-library/residential-catalog-v3.json` 是目录快照；原 STEP/FCStd 位于 `$INTERIOR_CAD_ASSET_STORE`。该目录只归 CAD 后端，HTML 和 Blender 不引用其中路径。

正式项目优先使用 STEP。FCStd 是可编辑源，但必须先在受管仓规范化为 STEP、登记对应哈希和许可再被项目选择。

资产可统一缩放、移动、旋转、隐藏和删除。可参数化柜体只在资产明确暴露参数时调整层数或模块；不能把整体 STEP 假装成可拆层。
