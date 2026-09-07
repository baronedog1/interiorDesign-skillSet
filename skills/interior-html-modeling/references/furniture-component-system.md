# Public Component System

## 一套目录，两种语义

组件库版本为 `6.1.1`。`public-assets.json` 是唯一目录，`movable-green` 和 `fixed-purple` 只是上游描线路由：

- `movable-green`：可自由移动的沙发、桌、椅、床、地毯和饰品。
- `fixed-purple`：柜体、吊灯、挂画、镜子、设备等固定或安装类对象。

两种分区都必须来自公共源码模型，都支持默认白模和源色/PBR。不存在“绿色有真实模型、紫色继续用旧程序化方盒”的例外。

## 来源层

- Poly Haven：官方 API、CC0，可商业和发布。
- Amazon Berkeley Objects：原始 GLB。数据集官网与桶内许可正文写 CC BY 4.0，但 AWS Registry 仍显示 CC BY-NC 4.0。研究模式允许；自动商业和社区发布阻塞到人工复核。任何后续放行仍必须署名 Amazon.com、数据集建设者、来源和许可，并说明运行时转换、等比缩放或白模材质替换。

Poly Haven 只收逐项审阅的室内资产白名单。ABO 候选必须同时满足产品标题类别与官方 `product_type` 类别一致；下载、几何或轴向审计失败即进入唯一排除表。不得为了达到数量配额使用宽泛关键词补入工具、游戏设备、户外路灯等错类模型。

每项资产保存 provider、source ID、来源页/API、许可、作者、源码格式、运行路径、尺寸、网格信息、颜色/材质、安装方式和用途。`public-asset-selection.json` 是精确成员清单，`source-asset-exclusions.json` 是唯一排除清单；缓存状态不得隐式增删目录成员。二进制和完整源码树哈希在 Ubuntu asset-store inventory/receipt 中维护，不复制回 catalog 形成第二份状态。

## 标签层

平台标签优先使用平台现有枚举：软装 category/subcategory、硬装 type/subcategory、other subcategory 与 `现代/极简/轻奢/意式/北欧/新中式/工业/other`。本地扩展只允许：

- `seatingCapacity`
- `mountType`
- `useCaseTags`
- `researchOnly`
- `sourceLicense`
- `stylePolicy`

风格必须有来源名称或产品类型证据。塑料一体椅等通用品不写风格，改写“简易、大排档、户外、易清洁”等用途。沙发必须填写人数。

## 几何与材质

- `builder=external-gltf`
- `geometryProfile=authored-gltf-pbr-v2`
- `primitiveBoxOnly=false`
- `lockAspectRatio=true`
- `appearanceVariants=[white-model, source-color]`

白模材质在加载后从同一 mesh 派生；有色状态默认保留 glTF PBR。项目可在 placement 上声明唯一 `finishPreset`，对通用柜体使用经审核的材质角色映射，例如 `modern-light-wood`；它只替换同一几何的材质引用，不生成风格标签或第三种显示模式。公共模型保留真实网格并允许按当前对象宽、深、高确定性调整；交互四角手柄默认维持等比例，地毯允许平面两轴独立适配且保持薄层高度。来源描线只作为位置和碰撞脚印，不能被渲染成色块家具。

编辑器双击组件时使用四角等比例手柄，宽、深、高共用同一倍率。柜体仍受天花高度上限；固定柜、冰箱、洗手盆和洗衣机在加载时先解除边界、墙和固定构件之间的面积穿透。灶台等表面设备按竖向承托关系放到柜顶，不把正常叠放误判为同层穿模。加载纠偏只做最小位移，不因活动家具的源布局把固定柜推离墙面。

## 取用与扩展

目录不把全量模型复制进项目。`match_trace_components.mjs` 在提交布局前调用物化器，只取当前用到的 GLB，并生成项目 lock。精确类别不存在时列出真实资产缺口，并在本次建模任务内完成来源、许可、网格、尺寸和浏览器准入后再重跑匹配。不得临时添加色块、方盒、不明网络模型或跨类资产掩盖缺口。品牌/SKU 专用资产仍交由 `movable-furniture-modeling` 建设并验收入库。

全库浏览通过 Ubuntu HTTP + asset store；飞书交付只制作明确抽样展厅，避免单文件内联数百个模型。
