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
