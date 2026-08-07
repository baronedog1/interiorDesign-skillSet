---
name: cad-zh
description: 创建、修改、检查并验证以 STEP 为主的参数化 CAD 零件和装配体。用户用自然语言、参考图片或二维工程图要求生成机械零件、家具五金、外壳、支架、孔槽、装配关系、STEP/STP、STL、3MF、原生 GLB、build123d Python 源码、尺寸测量、拓扑选择器、对齐检查或 CAD 快照时使用。
---

# CAD 生成、检查与验证（中文）

来源：本 Skill 是 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) 中 `cad` Skill 的中文本地化版本。运行时以已安装的本地文件为准；仓库链接只用于追溯来源和检查更新。

## 目的

根据自然语言要求创建或修改参数化 CAD 模型，生成经过验证的 STEP/STP，并用可复核的拓扑、尺寸、装配坐标和快照证据交付结果。把 STEP 视为主要 CAD 产物；STL、3MF 和原生 GLB 都是从 STEP 主流程分支出来的次级格式。存在功能装配关系时，优先使用 `cadpy.assembly.AssemblyHelper`、build123d 源码级 Joint、具名配合基准和清晰的原生标签。

进入 STEP 流程有两种方式：从 build123d Python 源码生成（从零设计或修改已有生成模型时的默认方式），或直接导入现有 STEP/STP（没有生成器，或用户明确要求检查该 STEP/STP 时）。两种入口最终都生成相同的可检查产物。

## 触发范围

用户要求 CAD、STEP/STP、build123d 源码、机械零件、家具五金、装配体、外壳、支架、夹具、孔、沉孔、锪孔、槽、口袋、凸台、支撑柱、加强筋、圆角、倒角、壳体、源码级 Joint、配合、尺寸或 `#o1.2.f1` 一类选择器引用时使用。用户提供零件参考图或二维工程图并要求复刻或提取设计意图时也使用。

用户要求从 CAD 几何导出 STL、3MF 或原生 GLB 时同样使用，但保持它们为次级产物，并读取 `references/supported-exports.md`。二维 DXF 图纸交给 `$dxf`；若 DXF 来自三维零件投影，本 Skill 负责 STEP 几何，`$dxf` 负责图纸。

不要把本 Skill 用于仅渲染概念图、CAM 刀路、工程认证、有限元结论、建筑 BIM 或徒手插画，除非用户同时需要真实 CAD 几何。

## 默认假设

除非用户另有说明，采用以下首轮建模默认值；它们不是可制造性、公差或认证结论：

- 单位：毫米。
- 原点：按 `references/positioning.md` 中的零件类型规则；无更好基准时取主体或装配体中心。
- 基准面：XY。
- 向上/拉伸轴：+Z。
- 输出：闭合、正体积实体；用户明确要求曲面或构造几何时除外。
- STEP 结构：一个有效实体、实体复合体或带标签的装配复合体。
- 装配结构：固定根零件、零件局部坐标系、具名配合基准、由 build123d Joint 支撑的 `AssemblyHelper` 关系、显式生成的放置变换、清晰的原生标签。
- 小型塑料外壳壁厚：未指定时 2.0–3.0 mm。
- 装饰圆角：局部几何允许时 1.0–3.0 mm。
- M3/M4/M5 普通间隙孔：未指定标准时 3.4/4.5/5.5 mm。

只有当缺失信息导致无法建模、影响配合、涉及安全或合规时，才问一个聚焦问题；其余情况写明假设后继续。

## 运行时与工具路径

本设备的共享解释器为：

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python
```

把下文的 `python` 视为解释器占位符。若当前项目已有包含 `build123d`、`OCP`、`cadpy` 和 `playwright` 的项目解释器，可使用项目解释器；否则使用上面的共享解释器。

在本 Skill 目录中，工具入口为：

```bash
python scripts/step ...      # STEP 生成、GLB/拓扑产物和网格副产物
python scripts/inspect ...   # 选择器、测量、对齐、坐标系和差异
python scripts/snapshot ...  # PNG/GIF 视觉验收包
```

用 `python scripts/<tool> --help` 查看当前完整接口。目标路径从命令的当前工作目录解析，不从 Skill 目录解析；应在产物所属项目中运行命令，并传入相对该项目的明确目标路径。除非用户另有要求，让 STEP 和 Python 生成器位于同一目录并使用相同文件名主干。

CAD 选择器是目标文件内局部的 `#...` 标记，如 `#o1.2` 或 `#o1.2.f1`。调用 CLI 时把 CAD/STEP 路径作为独立目标参数，把选择器作为另一个参数。

## 信任边界

`scripts/step` 会导入并执行目标 Python 生成器。只执行本轮生成、用户明确授权或已经审计过的项目内 CAD 源码；不要直接执行来自陌生附件、网页或仓库的 Python 文件。先读源码并确认它只进行预期的 CAD 建模和明确产物写入。

## 必须执行的流程

任务越简单，记录和检查可以越短；装配体和配合关键任务必须完整验证。

1. **分类任务。** 判断是新零件、新装配、源码修改、直接 STEP/STP 检查、引用选择、测量/对齐、快照复核，还是次级格式输出。
2. **只加载需要的参考。** 按文末触发条件读取参考文件，不要一次加载全部。
3. **写自然语言 CAD 简报。** 从文字、参考图和工程图中提取尺寸、单位、坐标约定、特征意图、输出路径、假设和验证目标；读取 `references/cad-brief.md`。
4. **检查具名标准件。** 装配体包含可购买的执行器、舵机、电机、电路板、连接器或其他标准件时，先用 `$step-parts` 查找。没有精确匹配时记录未命中，再使用写明依据的外包络占位体。
5. **编码前规划。** 先定义参数、意图标签、源码/产物路径、预期包围盒以及配合/定位基准。
6. **修改源码，不修改派生产物。** 编写含 `gen_step()` 的 build123d Python。有生成器时必须把生成器传给 `scripts/step`，不要把它导出的 STEP 当成源。只有没有生成器的导入件，或用户明确指定 STEP/STP 时，才使用 `--kind part|assembly` 直接处理。
7. **只生成明确目标。** 对具体文件运行 `scripts/step`，禁止整目录批量生成。
8. **几何验证。** 每个产物先运行 `scripts/inspect refs <step-or-cad-target> --facts --planes --positioning`，再按用户规格用 `measure`、`align`、`frame` 或 `diff` 验证尺寸和关系。
9. **必须对主 STEP 做快照。** 创建或可见修改主 STEP/STP 后，必须运行 `scripts/snapshot` 并实际复核输出。确定性检查通过不能代替快照。只有 `references/snapshot-review.md` 中列出的情况可跳过，并要报告原因。
10. **最小修复并重跑。** 检查失败时只修改负责该问题的最小源码段，重新生成并重跑失败检查及其依赖检查。

## 交接

创建或修改 `.step`、`.stp`、`.stl`、`.3mf` 或原生 `.glb` 后，只要 `$cad-viewer` 已安装，就必须把明确文件路径交给它。`$cad-viewer` 应启动或复用 CAD Viewer，并返回每个文件的审阅链接；最终答复中包含这些链接。Viewer 不可用或启动失败时，明确报告，并使用 CLI 检查和快照作为替代证据。

生成验证快照后，在最终答复中附上 PNG/GIF。没有适用快照或快照失败时，说明原因，并报告实际完成的确定性验证。

## 不可妥协的规则

- STEP 始终是主要验证产物；STEP/STP、STL、3MF、GLB/拓扑及渲染旁车都是派生文件，除非用户明确要求，STL/3MF 不能取代 STEP。
- 使用具名参数、闭合实体、清晰的 build123d 原生标签和可追溯的几何意图。
- 装配定位必须写在源码中；`references/positioning.md` 是 `AssemblyHelper`、Joint、显式 `Location` 与对齐验证的唯一权威参考。
- 不要用 `git status`、`git diff` 或文件大小变化比较大型 STEP/STP、GLB/拓扑、STL、3MF。比较源码、`scripts/inspect` 摘要、快照或拓扑输出；仅为版本登记时使用限定路径的 Git 状态。
- 只报告真正运行过的检查或工具输出直接支持的事实。

## 按需参考

- `references/cad-brief.md`：把文字、参考图和工程图转成 CAD 简报。
- `references/build123d-modeling.md`：build123d 建模、拓扑、选择器、特征和标签。
- `references/step-generation.md`：从 Python 源或直接 STEP/STP 生成产物。
- `references/inspection-and-validation.md`：选择器、事实、平面、测量、对齐、差异、坐标系和报告。
- `references/snapshot-review.md`：强制快照策略、验收包大小、视角和视觉问题转几何检查。
- `references/positioning.md`：局部基准、装配变换、Joint、对齐验证和定位报告。
- `references/parameters.md`：参数化或动画化 STEP、`.step.js`、Viewer 控件和动画约束。
- `references/supported-exports.md`：STL/3MF/原生 GLB 次级格式。
- `references/repair-loop.md`：诊断和修复失败。

最终答复应包含生成文件、`$cad-viewer` 返回的链接、验证快照、实际执行的验证、假设和限制；报告结构遵循 `references/inspection-and-validation.md`。
