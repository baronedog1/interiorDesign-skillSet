---
name: movable-furniture-modeling
description: 当用户要求根据照片、尺寸图、顶/正/侧视图或渲染图，对单个活动家具、定制柜、设备或异形产品做可审计 Three.js 建模时使用；唯一方法是把每个已提供视图在源分辨率上分割为逐组件可见区域，以主视图区域沿视线拉伸，再依次与其余正交视图区域形成的体积求交，最后用逐组件、逐视图零异或投影门禁验收。每个产品只保存一份三维几何，同时交付默认 white-model 与 source-color 两个外观状态。本 Skill 只交付项目级单品 HTML 与组件包，不直接写入通用组件库；户型墙窗、空间效果图、视频和平台发布不触发本 Skill。
metadata:
  version: 10.2.0
  schema: interior.custom-component-package.v3
---

# 活动家具多视图区域雕刻建模

## 快速导航

- [data_contract.md](data_contract.md)：唯一 evidence、carving plan、state、browser QA 与组件包合同。
- [playbook.md](playbook.md)：从源图冻结到 accepted/provisional 交付的唯一执行顺序。
- [local_runtime.md](local_runtime.md)：本地命令、依赖与真实浏览器验收入口。
- [scripts_logic.md](scripts_logic.md)：所有确定性脚本及其唯一职责。
- [templates.md](templates.md)：单产品 self-contained HTML 的唯一模板入口。

## 高频数据入口

1. 先读 `view-region-evidence.v1`，确认每个源视图、组件区域、遮挡归属和源文件哈希。
2. 再读 `multi-view-carving-plan.v1`，确认同一组件如何沿各视线求交。
3. 只把 `visual-hull-state.v1` 作为三维几何事实；白模与源色只能引用这一份 state。
4. 最终状态只读 `custom-component-package.v3.status`，并核对绑定的零异或报告和 `product-browser-qa.v1`。

## 核心思想

模型不是先猜一组方盒再回头调图，而是直接由用户给出的视图区域生成：先在顶、正、侧或其它已登记
视图上得到产品和组件的完整可见区域，再把主视图区域沿视线拉伸成初始体，随后用其它正交视图逐向
切掉不属于对应区域的体素。每个组件独立雕刻，最后只在同一坐标系中拼装。

唯一几何公式为：

`component volume = extrusion(primary mask) ∩ extrusion(front mask) ∩ extrusion(side mask) ∩ ...`

没有第二套自由体量、pathId 拟合、类别模板或逐视图独立调参逻辑。

## 事实定义

- `区域` 是源分辨率上的二维像素集合；`边界` 是区域与非区域相邻处的源像素边缘，不是稀疏点、
  外包框或手写平滑曲线。
- 代码负责源图裁切、背景/产品分离、基于图像梯度的区域分割、掩膜 RLE、哈希、覆盖和投影比较。
- Agent 只负责组件命名、组件种子、遮挡归属、主视图选择和物理层级；不得手写最终边界坐标。
- 每张正交图必须登记世界轴映射和可逆像素注册；裁切、缩放或旋转检查图不能成为几何事实源。
- 隐藏区域必须标记 `inferred`。推断可以补足三维实体，不能改动任何已提供视图的可见掩膜。

## 唯一事实流

`冻结源图 -> view-region-evidence.v1 -> 区域分件与覆盖门禁 -> multi-view-carving-plan.v1 -> 主视图逐组件拉伸 -> 其余正交视图依次求交 -> 不可变 visual-hull-state.v1 -> 零异或回投影 -> 单产品 HTML -> 桌面/手机 browser-qa.v1 -> custom-component-package.v3`

## 标准流程

1. 冻结每个源文件的 SHA-256、原始尺寸、视图类型、裁切和源图往返矩阵；优先读清晰尺寸。
2. 对每个视图运行 `scripts/extract_view_regions.py`。Agent 提供粗种子和语义，代码在原始图梯度上完成
   区域分割并输出产品掩膜、逐组件掩膜、叠图和 canonical evidence。
3. 运行 `scripts/validate_view_regions.py`。可见组件掩膜必须完整覆盖产品掩膜；普通区域不得重叠，
   遮挡重叠必须有唯一前后归属；区域边界不得落到已登记的纯背景排除区。
4. 选择信息最强的正交主视图。存在可用俯视图时默认以俯视图为主；否则依次选正视图、侧视图，
   透视图只能在相机已求解时使用。
5. 每个组件把主视图掩膜沿主轴完整拉伸。不要先造方盒、圆角盒或类别模板。
6. 对同一组件，把每个其它已提供正交掩膜沿其视线拉伸并与当前体积求交。顺序只影响计算效率，
   不得影响最终占用体。
7. 只对缺失视图方向补充有界深度、厚度或支撑假设，并在 state 中逐项标记 `inferred`；至少一个
   已提供视图必须完全来自证据，不能被推断覆盖。
8. 用 `scripts/compare_view_projection.py` 从最终占用体按同一注册反投影。先检查每个组件，再检查
   整件可见遮挡合成，不得只比外包框。
9. 结构门禁通过后才生成材质与 self-contained HTML。同一 state 网格必须提供默认
   `white-model` 与 `source-color` 两个外观状态；切换只替换材质，不得切换几何。渲染圆角或
   法线平滑不得改变逻辑占用体和任何已提供视图的投影掩膜。
10. 用桌面与手机 Chrome 验收同一个 HTML，browser QA 必须绑定 state 与 HTML 哈希。无推断的
    `candidate` 在零异或与 browser QA 均通过后由组件包确定为 `accepted`；含缺失方向推断的
    `provisional` 仍只能打为 provisional。不得回写第二份“accepted state”。

## 视图匹配硬门禁

- 每个用户提供的正交视图都必须满足：`xorPixels = 0`、`precision = 1.0`、`recall = 1.0`、
  `IoU = 1.0`。不得以 Chamfer 容差、包围盒或 0.92 阈值替代。
- 若多视图证据彼此不相容，保留冲突并停止为 `rejected`；不得移动某张图的边界让它通过。
- 只有一个视图时，该视图仍必须零异或匹配；沿缺失轴的厚度、背面和隐藏结构标记为
  `single-view-inferred`，不能宣称其它视图为实测。
- 透视渲染图仅用于相机校准、遮挡与外观复核；未求解相机时不得拿透视轮廓切正交体。
- 低分辨率、JPEG 模糊或无尺寸只降低米制尺寸和隐藏结构的确定性，不降低已接受区域的投影门禁。

## 结构硬门禁

- 每个可见组件至少有一个 source-backed region；产品掩膜中的每个可见像素必须被消费一次。
- 组件占用体非空、具有正厚度，接触/支撑关系成立；禁止悬空、无意穿插、自交或非流形表面。
- 所有视图共享一个世界坐标和一份组件状态；不存在 `topModel`、`frontModel` 等视图专属模型。
- 模型网格必须由 state 的占用体确定性生成。自由移动顶点、事后截图描边和人工填写 pass 均禁止。
- 组件包 `appearance.geometryStateSha256` 必须等于唯一 state 哈希；`defaultMode` 固定为
  `white-model`，`supportedModes` 固定为 `white-model/source-color`，不得保存第二份彩色几何。
- state 只保存雕刻结果及其 `candidate/provisional` 证据状态；最终是否 accepted 只由绑定零异或报告、
  desktop/mobile browser QA 和全部 artifact SHA 的 `custom-component-package.v3.status` 表达。

## 停止条件

源哈希不一致、组件区域漏分/多分、背景排除区违规、注册不可逆、主视图未完整拉伸、辅助视图未
实际参与求交、零异或门禁失败、结构门禁失败或浏览器 QA 未完成时，不得称为完成品。

## 交付

正式交付包含 `view-region-evidence.v1`、分区叠图、`multi-view-carving-plan.v1`、唯一
`visual-hull-state.v1`、逐组件逐视图投影报告、浏览器 QA、self-contained HTML 和
带双外观合同的 `interior.custom-component-package.v3`。包内必须逐视图列出 evidence 与原始源图、四条
canonical 绑定、standalone 及 browser QA 的文件哈希。证据不足的隐藏结构可交付 provisional，但已提供视图仍
必须零异或通过，且 provisional 不得导入正式户型项目或晋级通用库。

## 通用组件库边界

- 本 Skill 的 accepted 输出仍然只是当前项目的 `interior.custom-component-package.v3`，不得自动追加到公共活动家具库，也不得在本 Skill 内维护第二份 catalog。
- 公共活动家具库的唯一事实源归 `interior-html-modeling`。只有用户明确要求“加入通用库”时，才把 accepted 组件包作为候选交给该 Skill 的准入流程。
- 候选必须同时满足：来源可追溯且许可允许复用、非纯方盒、多视角结构 QA 通过、单产品 HTML 通过桌面与手机浏览器验收，并且同一 state 同时提供默认白模与源色材质。公共库自己的 `qualityTier/geometryProfile/componentId` 只由 `interior-html-modeling` 准入流程生成。
- 来源不明的网络模型、仅由原始方盒堆砌的模型、重复造型、未记录许可的资产和只在单张截图看似正确的模型一律不得进入通用库。
- 进入公共库后只保留公共 `componentId`、可编辑源码模型、运行时 GLB、来源许可收据和唯一目录记录；项目证据、原图、平台凭据和客户文件不得复制到库内。
