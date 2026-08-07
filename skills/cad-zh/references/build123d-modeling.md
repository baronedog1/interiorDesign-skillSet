# build123d 建模模式

编写或修复 build123d Python 源码时读取本文件。

## 建模目标

创建可导出 STEP 的有效 B-Rep，而不是仅用于显示的网格。优先使用闭合实体、清晰标签和稳定的参数尺寸。定义 `gen_step()` 并返回可导出 STEP 的形状或带标签复合体；输出路径由 CLI 负责，参见 `step-generation.md`。

## 设计策略

写几何代码前先决定构造方式：

- **选择能让规格尺寸直接成为参数的构造。** 轮廓驱动形状用一个闭合草图配合 `extrude`、`revolve`、`sweep` 或 `loft`；块体加特征的零件用基础实体配合增材/减材。优先让用户控制尺寸成为具名参数，而不是复杂派生值。
- **建模前确定零件还是装配体。** 分别制造、购买或运动的实体应进入带标签装配体，参见 `positioning.md`；整体制造的对象应成为单一融合实体。避免无标签多实体复合体，否则检查和 Viewer 中会丢失每个实体的用途。
- **雕刻几何前，从功能基准选择原点和方向。** 优先把配合面、安装面或对称轴设为基准；不同零件类型的默认原点见 `positioning.md`。
- **让脆弱操作靠后，便于定位失败。** 基础实体 → 主要增材 → 减材特征 → 抽壳 → 穿壁孔 → 圆角/倒角。圆角最容易失败，所有布尔操作都会使选择器失效，因此把圆角放在最后。每个特征用独立函数或具名中间变量表达，让失败能定位到单一特征。
- **布尔工具要超出目标。** 切割工具应穿过入口和出口面；通切时两端通常各多出约 1 mm。工具面与目标面完全共面是几何内核常见失败原因。重复或阵列特征尽量合并为一次布尔切割。
- **生成前检查比例。** 把预期包围盒与真实物体比较，把壁厚与总尺寸比较，并检查特征到边缘和相邻特征的距离。数量级和碰撞错误可能通过几何有效性检查，却会在视觉复核中暴露。

## 拓扑层级

按以下顺序理解拓扑：

```text
Vertex → Edge → Wire → Face → Shell → Solid → Compound
顶点       边      线环     面      壳      实体     复合体
```

装配体统一使用以下术语：

- **Occurrence（实例节点）**：装配树中经过放置的节点，具有父节点、变换、路径和 `lid`、`m3_screw:front_left` 等用途标签。
- **Shape（形状/实体）**：实例节点内部导出的几何体。拓扑行归 Shape 所有；面和边属于 Shape，Shape 属于 Occurrence。
- **Face/Edge（面/边）**：归 Shape 所有的可选择拓扑。不要假设任意面/边具有持久意图标签；应通过实例、形状、序号、曲面/曲线类型和测量结果识别。

检查拓扑时遵循 `装配实例 → 形状/实体 → 面 → 边`。每一条面/边记录都应能通过 `occurrenceId` 和 `shapeId` 回溯。

普通 STEP 输出应返回以下之一：

- 有效 `Solid`
- 有效实体组成的 Compound
- 带标签的装配 Compound

除非用户明确要求，避免导出松散 Wire、开放 Face 或构造 Surface。

## 参数优先

把有意义的尺寸放进具名变量：

```python
width = 80.0
depth = 50.0
thickness = 6.0
hole_diameter = 4.5
hole_offset_x = 30.0
hole_offset_y = 17.5
```

不要把关键数字埋在几何调用内部。

## 坐标系

声明或注释坐标约定：

```text
原点：主体中心或选定配合基准
XY：主要基准/草图平面
+Z：向上或拉伸方向
```

有定位要求时有意识地使用 `Location`、`Plane` 和 `Axis`；装配关系读取 `positioning.md`。

## Builder 上下文

选择与几何对应的上下文：

```python
with BuildLine() as path:
    ...

with BuildSketch() as profile:
    ...

with BuildPart() as part:
    ...
```

常见流程：

```text
曲线/路径 → 草图/轮廓 → 实体/特征 → 标签 → STEP
```

## 选择器实践

尽量避免依赖不稳定的拓扑次序。优先按以下条件选择：

- 轴或法线
- 位置或包围盒极值
- 共面分组
- 特征意图
- 稳定构造面
- 下游验证中已检查的局部选择器

源码操作优先使用“按轴或位置找顶/底面”一类稳健选择，不要随意用列表索引。

## 装配与定位

本文件只描述 B-Rep 模式和标签。以下内容以 `positioning.md` 为唯一事实源：

- 零件局部坐标约定
- 何时使用 `cadpy.assembly.AssemblyHelper`、build123d Joint 或显式 `Location`
- `connect_to()` 行为
- CLI `inspect align` 的只读选择器对验证
- frame、measure 和定位报告要求

## 标签与装配

为每个导出零件和装配子项设置 build123d 原生标签。通过 `cadpy.assembly` 使用简洁意图标签：

```python
from cadpy.assembly import AssemblyHelper, label_shape

asm = AssemblyHelper("electronics_enclosure")
base = asm.add(make_base(), "base")
lid = asm.add(make_lid(), "lid")

boss = label_shape(Cylinder(radius=3.0, height=12.0), "m3_boss", "front_left")
```

不要用 `assembly`、`component`、`feature`、`datum`、`mate`、`hardware` 等拓扑类别给标签加前缀；装配树和拓扑检查已经表达这些类别。标签应描述拓扑不能可靠推断的内容：用途、位置、接口、重复序号和配合目的。

只有特征仍作为 Compound 子 Shape 导出时，特征标签最容易跨 STEP 保留。布尔减去或融合后的历史不应假设保留标签；其意图由源码参数、具名基准和验证选择器表达。

标签规则：

- 标记根装配体。
- 标记每个导出零件、子装配/模块和重复实例。
- 重复零件用实例标签表示用途和位置，如 `m3_screw:front_left`、`m3_screw:rear_right`。
- 有必要时给保留的导出 Shape 标记实体用途。
- 只有基准/特征几何仍作为子 Shape 导出时才依赖其标签。
- 用具名 mate datum 表达源码级定位，再验证导出 STEP 的拓扑和实例坐标系。

实例与 Shape 标签通过 STEP 名称导出，并在可用时由 `STEP_topology` 显示。Viewer 用实例标签生成装配树引用，用 Shape 标签生成形状引用。面和边通过 `occurrenceId`、`shapeId` 继承上下文；未经实测支持，不承诺面/边意图标签能持久保存。

重复零件必须显式记录实例标签、变换或 Joint 连接，并在生成后检查 frame/positioning。

## 常见失败

- 圆角半径超过局部边几何允许值。
- 开放草图无法生成有效面。
- 布尔或圆角后面选择器发生变化。
- 零件原点随意，导致后续对齐含糊。
- 把源码级 Joint 误认为导出 STEP 中会持续存在的约束，而不是一次性源码放置操作。
- Joint 标签缺失、重复或挂在错误的局部基准上。
- `.connect_to()` 固定/移动方向写反，移动了本应固定的零件。

生成或验证失败时读取 `repair-loop.md`。
