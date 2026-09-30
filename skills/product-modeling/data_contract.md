# 生成器与工作台接口

配置模块导出 `create(parameters)`、`parameters`、`reference`（内联 data 图片）、`referenceSize:[width,height]`、`finish` 和 `spec`。所有外部纹理在构建前嵌入；产品生成器留在任务目录。

## 几何与单位

`create` 返回 `{root,parts,anchors}`；root 是 THREE.Object3D，parts 是独立 Mesh，anchors 是同坐标的真实几何点。BoxGeometry 等仅是几何，需包成 Mesh。工作台世界坐标用米，Y 向上、Z 向前；原数据为毫米/厘米时，生成器统一换算几何、锚点、相机距离和目标高度，不能只缩放模型。无实测尺寸时记录 `dimensionStatus:inferred`，米制是估计显示尺度，不是厂家尺寸。不得把自动包围盒取景当作已校准相机。

网格 name/part_id 稳定且唯一；每件使用单一材质，多材质网格先拆分。类别在 `mesh.userData.category`，木纹轴在 grainAxis。部件关系和参数必须实际驱动几何；geometryParameters 与 parameters 默认值合并后，再由 spec.values 覆盖可编辑参数。

## 产品定义

spec：`format:product-modeling`、`schemaVersion:1`、`mode:mesh`、英数短横线 id、`generator:embedded-product-v1`。parts 包含 id、mesh_name、label、assembly；assemblies 包含组 id。parameters 的字段支持 number（min/max/default/step）、color、enum（options），以及 label/unit/effect；values 存当前值，geometryParameters 存几何和相机参数。内部导入还支持模板已有 parametric 表达式产品与 GLB 网格，不把简单体示例当照片复建结果。

## 相机、表面与保存

`scripts/core.mjs` 提供 cameraFor：az/el 角度、distance/targetY 米、fov 角度、shiftX/shiftY 图像比例。缺字段使用明确的临时默认值；非有限数、非法视角/距离报具体错误，绝不静默重置拟合相机。保存全部实际使用参数。多视角评估由任务脚本逐图调用；当前工作台以选定主参考图展示，不声称有内置多图切换器。

finish 由 surfaces 方法定义。JSON 保存产品参数、部件编辑、相机浏览状态、白模、叠图、曝光、阴影、分解、选件及隔离；在原产品 HTML 中重开。同名生成器不匹配时报错。编辑位移后该部件暂退回局部 UV；最终重新拟合应回生成器重建深度和照片投影。

GLB 导出当前可见网格、基础材质与统一 UV 变换；支持选择是否包括分解位移。照片投影是 HTML shader，未自动烘焙到 GLB；不同材质贴图采用不同 UV 变换时先烘焙，再导出。不能声称两种载体材质完全一致。导出的 GLB 与 JSON 以实际重新载入核对为准。

## 报告

源图摘要/宽高/裁剪、语义对应来源、单位与推定、实际拟合目标/权重、参数边界、最终点误差与关键特征偏差、浏览器实测和未完成项均可追溯。源程序没有执行的损失项或观察不能写成已实现功能；源图没提供的未知项与误差为0是两回事。
