# 产品数据契约 / schemaVersion 1

唯一执行解释器：`assets/workbench/product-kernel.js`，Node和浏览器读取同一份代码，不执行用户表达式文本。

## 根对象

`format: "product-modeling"`、`schemaVersion: 1`、稳定 `id`（字母数字下划线或短横线）、`name`、`revision`、`mode: "parametric" | "mesh"`。`source` 保存图片/资料来源、尺度与假设；`overview`、`limits`、`assembly_steps` 用于说明书，不创造验证结论。

`parameters` 是键→描述：`type` 为number/enum/color，包含label/default/effect；number有min/max/step/unit；enum的options为字符串或{value,label}；color为#RRGGBB。`values` 只包含已定义参数的当前值。界面据此生成，不在HTML内硬编码产品参数。

`derived` 为有序 `{id,expr}`；每项只能引用已有参数或前序派生值。表达式是数值或数组：`["ref","width"]`、`["+",a,b]`、`["-",a,b]`、`["*",a,b]`、`["/",a,b]`、`["min",...]`、`["max",...]`。除零、未知引用、非有限数、未知参数和越界值报错。没有eval、Python表达式或任意脚本注入。

## 结构与装配

`assemblies` 是 `{id,label,parent?,explode:[x,y,z]}`；parent必须存在且不循环。explode是查看器分解方向/幅度（米），不是固定生产拆卸路径。

`parts` 至少有稳定id/label/assembly；`variants` 可指定当前 `values.variant` 下出现的部件。parametric还有primitive/material/size/position。size和position分别含三项表达式，单位毫米。box的size为宽高深；cylinder为顶直径、高、底直径；sphere使用size[0]为直径，其他两项保留一致值。当前不支持任意旋转表达式、布尔加工或任意CAD曲线，复杂部件走mesh。

mesh根含model相对GLB路径，parts含对应的mesh_name；可选mesh_source保存独立原始四边面文件。对应网格未带产品语义时，只能展示其原始名称，不能推断其制造结构。


`materials` 是ID→{label,color,roughness,metalness,colorParameter?,roughnessParameter?}。mesh纹理来自内嵌GLB。`interfaces` 记录连接与工艺说明，不自动生成精确孔槽；`geometry_status: metadata-only-not-machined` 不得解释为已经加工完成。

## 用户编辑

`edits` 是零件ID→{offset_mm:[x,y,z],hidden:boolean,color?:HEX,roughness?:0..1}。位移是世界坐标毫米，每轴不超过10000绝对值。联动操作会为所属实际零件分别保存对应编辑；颜色和粗糙度是实际材质因子修改。分解滑块是显示状态，默认不写入导出GLB，勾选“包含分解位移”才写入。

产品保存JSON用于重新加载参数/编辑，导出GLB保存当前可见已求值网格。parametric Python构建器能按编辑生成，mesh构建器拒绝复制未烘焙的编辑状态；必须先导出GLB并更新基线，见playbook/delivery.md。

## 静态GLB边界

支持GLB2、普通三角网格、节点变换、内嵌图像及基础PBR；受支持子集不是完整glTF实现。拒绝骨骼/动画、压缩扩展、稀疏accessor、外部资源和不支持的primitive，避免静默丢模型。OBJ保留四边面但不携带完整PBR；GLB负责材质交换，NPZ/OBJ负责曲面编辑源。

## 产物与身份

每产品输出原JSON、GLB、evaluated.json、PRODUCT_MANUAL.pdf、PRODUCT_MANIFEST.json；源网格及贴图按当前产品实际引用随包。产品手册写产品ID、修订和源摘要。技能级MANIFEST登记实际文件和版本但不自哈希，外层ZIP另做SHA256。包交付与安装/发布分别记录。

## 多视图还原数据

# 数据合同

| 对象 | 唯一职责 | 禁止内容 |
| --- | --- | --- |
| `interior.product-view-region-evidence.v1` | 冻结一个视图、注册、产品掩膜和逐组件可见区域 | 稀疏点、外包框、三维尺寸、手写平滑边 |
| `interior.product-multi-view-carving-plan.v1` | 组件、主视图、轴映射、缺失方向假设和遮挡层级 | 第二套轮廓、视图专属模型、自由顶点 |
| `interior.product-visual-hull-state.v1` | 逐组件占用体、确定性网格和唯一装配状态 | 与 evidence 脱钩的体块、材质反建结构 |
| projection report | 从 state 回投影后的逐组件/整件 XOR、precision、recall、IoU | Chamfer 宽限、人工 pass |
| `interior.product-browser-qa.v1` | 绑定 state 与 standalone 哈希，记录桌面/手机非空画布、错误、WebGL 与溢出事实 | 人工填写截图已看、未运行浏览器的 pass |
| `interior.custom-component-package.v3` | 绑定不可变 state、逐视图证据/源图、报告、standalone、browser QA 和同几何双外观合同，并派生 accepted/provisional | 平台凭据、第二份彩色几何、未通过候选冒充 accepted |

`interior.custom-component-package.v3` 是项目级交付，不是公共库写权限。公共库只能由
`interior-html-modeling` 的组件准入流程维护；本 Skill 不生成、修改或携带第二份 catalog。

组件包必须写入：

```json
{
  "placementClass": "movable-green",
  "appearance": {
    "defaultMode": "white-model",
    "supportedModes": ["white-model", "source-color"],
    "geometryStateSha256": "<visual-hull-state stateSha256>",
    "sourceColorAuthority": "visualHullState.components[].material"
  },
  "bindings": {
    "planCanonicalSha256": "<plan hash>",
    "stateCanonicalSha256": "<state hash>",
    "projectionReportCanonicalSha256": "<report hash>",
    "browserQaCanonicalSha256": "<browser QA hash>"
  },
  "evidence": [{
    "viewId": "front",
    "regionEvidence": {"path": "front.json", "sha256": "<file hash>"},
    "sourceImage": {"path": "front.png", "sha256": "<file hash>"}
  }]
}
```

白模和源色只能引用同一个 `visualHullState`。源色由各组件 `material` 保存；白模由 standalone 和
下游运行时确定性替换材质。二者不得拥有不同 mesh、尺寸、组件层级或碰撞体。

## 区域不变量

- 所有掩膜坐标使用源图左上角 `(0,0)`，按行 RLE 保存，不得把检查图坐标写回事实。
- `productMask` 是当前视图中产品可见区域；`components[].visibleMask` 的遮挡合成必须与其逐像素相等。
- 每个普通可见像素只有一个最前组件；隐藏组件可以在 carving plan 中推断，不能重复占有可见像素。
- 组件边界由代码在源图梯度/颜色证据上收敛。Agent 可给区域种子和语义，不可提交最终边界折线。
- 所有源、裁切、掩膜、RLE 和 canonical JSON 都必须有 SHA-256。

## 坐标与注册

每个正交视图登记 `uAxis`、`vAxis`、方向符号、源像素到共享网格的比例与偏移。例如俯视图为
`u=x, v=y, ray=z`，正视图为 `u=x, v=z, ray=y`。注册必须能将源掩膜无损放入共享整数网格；需要
重采样时先把所有视图映射到共同有理数网格并记录矩阵，禁止隐式拉伸。

## 雕刻不变量

对组件 `c`，先由主掩膜形成无限/有界棱柱，再与其它正交掩膜棱柱求交。最终占用体必须等于所有
登记证据约束的集合交；网格只是该占用体的确定性表面表示。缺视图方向只能使用 plan 中明确的
有界范围，状态写入 `inferenceFlags`。

## 状态分级

- `evidence-only`：区域仍待核验。
- state `candidate`：无缺失方向推断的不可变雕刻结果；仍需投影、结构和浏览器门禁。
- state `provisional`：唯一雕刻结果含尺寸或隐藏方向推断；即使已提供视图全通过也不能晋级 accepted 包。
- `rejected`：区域、注册、求交、投影或结构任一失败。
- package `accepted`：state 为无推断 candidate，所有提供视图零异或，结构成立，standalone 与桌面/手机
  browser QA 通过，并且包内 evidence、源图和全部 artifact 哈希闭合。accepted 只属于组件包，不回写 state。

## 公共库晋级合同

只有用户明确要求把 accepted 单品加入通用库时，才允许把组件包作为候选移交。候选必须有可复用的
来源许可、非纯方盒的设计几何、多角度结构证据、桌面与手机 standalone 验收，并由
`interior-html-modeling` 生成唯一 `componentId`。未晋级前只在当前项目使用；不得自动注册、静默替换
同名组件或把来源不明的网络模型写入公共库。
