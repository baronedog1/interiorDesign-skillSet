# 定位逻辑、Joint 与配合

存在配合接口、重复特征、装配子件、轴、基准、运动或用户指定对齐时读取。本文件是装配定位、局部原点、build123d Joint、显式 `Location`、CLI `inspect align` 和定位报告的唯一权威参考。

## 核心规则

定位写在源码中，生成后再验证。禁止通过视觉拖拽或编辑导出的 STEP 定位零件。使用 build123d 参数、局部坐标系、`Location`、`Plane`/`Axis` 基准、`cadpy.assembly.AssemblyHelper` 关系、必要的源码级 `Joint` 和带标签装配子件。

## 术语

- **AssemblyHelper**：`cadpy.assembly` 中首选的生成脚本封装，记录 `face_to_face`、`coaxial`、`revolute`、`linear` 等语义关系，并通过原生 build123d Joint 实现。
- **build123d Joint**：挂在 `Solid`/`Compound` 上的源码对象，如 `RigidJoint`、`RevoluteJoint`、`LinearJoint`、`CylindricalJoint`、`BallJoint`；可通过 `connect_to()` 重新定位零件。
- **CLI `inspect align`**：选择器对验证工具，只读计算 STEP/CAD 中两个引用的平移差量。它不编辑源码、不修补 STEP，也不是已编写的 mate feature。其他文档都以此区分为前提。
- **配合意图**：贴合、居中、同轴、偏移、铰链、滑轨或其他基准驱动关系。

用 AssemblyHelper/Joint 编写并计算源码装配位置，再用 CLI 检查生成的 STEP。

## 推荐装配结构

优先用 mate/Joint，而不是随意变换：

```text
根组件
→ 零件局部坐标系
→ 具名基准 / Joint 位置
→ 由原生 build123d Joint 支撑的 AssemblyHelper 语义关系
→ 带清晰原生标签的 Compound 装配体
→ refs / measure / frame / align 验证
```

每个数值 `Location(...)` 通常应对应一个明确基准、偏移、间隙、螺钉轴、接触面或 Joint 关系。

把轴承、齿轮箱级、紧固件组等功能单元用 `asm.add_module(name, children)` 组成子装配节点，尤其当它作为整体定位、推理或重复使用时。这样 `#o1.12.1` 一类嵌套实例引用仍有意义。

## 零件局部定位

建模前定义每个零件的局部约定：

```text
- 原点：中心、底部基准、安装接口或功能轴。
- XY：主要草图/基准面，除非其他基准更关键。
- +Z：拉伸/向上方向。
- 具名尺寸：偏移、孔距、柱距、间隙。
- 基准特征：配合面、螺钉轴、中心线、定位舌、导轨。
```

良好默认值：

- 对称独立零件：主体中心。
- 板：平面中心，厚度沿 Z。
- 外壳：平面中心，底座/盖板配合面由 Z 参数控制。
- 轴、旋钮、回转件：旋转轴线上。
- 转接板：主要安装基准或螺栓阵列中心。

## 零件内部特征定位

使用具名参数和局部坐标：

```python
hole_offset_x = 30
hole_offset_y = 17.5
hole_positions = [
    (-hole_offset_x, -hole_offset_y),
    ( hole_offset_x, -hole_offset_y),
    (-hole_offset_x,  hole_offset_y),
    ( hole_offset_x,  hole_offset_y),
]

with Locations(*hole_positions):
    Hole(radius=hole_diameter / 2)
```

禁止在几何调用中埋入无法追溯的定位常数；所有有意义偏移都应参数化。

## AssemblyHelper 模式

生成装配脚本优先使用 `AssemblyHelper`。它让源码保持意图清晰，同时仍使用 build123d 标签、Joint 和 Compound：

```python
from build123d import *
from cadpy.assembly import AssemblyHelper

base_height = 30.0
lid_thickness = 3.0
gasket_gap = 0.5

asm = AssemblyHelper("enclosure")
base = asm.add(make_base(), "base")
lid = asm.add(make_lid(), "lid")

base_seat = asm.rigid_frame(
    base,
    "lid_seat",
    Location((0, 0, base_height / 2)),
)
lid_underside = asm.rigid_frame(
    lid,
    "underside",
    Location((0, 0, -lid_thickness / 2)),
)

asm.face_to_face(base_seat, lid_underside, offset=gasket_gap)

def gen_step():
    return asm.build()
```

固定目标写在前，移动目标写在后。示例中底座固定、盖板移动。Helper 记录源码关系并在内部调用 `connect_to()`；导出的 STEP 保存已经求解的静态位置和原生装配标签，不保存持续约束。

有意识地使用标签：

```python
standoff = asm.feature(Cylinder(radius=3.0, height=12.0), "m3_standoff", "front_left")
hinge_axis = asm.rigid_frame(lid, "hinge_axis", Location((0, -25, 0)))
```

Assembly 标签命名根实例；`asm.add()` 标记子组件实例及导出 Shape 上下文。重复五金/库件使用 `front_left`、`rear_right` 等用途/位置标签，确保导出后仍可追溯。

只有标签几何仍作为 Compound 子 Shape 时，特征标签最容易保留；布尔历史上的标签不可靠。

frame 方法必须匹配 build123d Joint 输入：`rigid_frame()`/`ball_frame()` 接受 `Location`；`revolute_frame()`、`linear_frame()`、`cylindrical_frame()` 接受 `Axis`，并可带原生范围/参考参数。

## 导入组件

购买或下载的零件（见 `$step-parts`）和自建零件一样导入装配：

```python
from build123d import import_step

servo = asm.add(import_step("models/parts/sg90_servo.step"), "servo")
```

导入几何的原点/方向不能假设。先运行 `refs --facts --planes --positioning` 和 `measure`，从实测面、轴和孔阵列定义 `asm.rigid_frame(...)`，再按同样标准验证配合。

## 何时使用 Joint

当装配意图比原始变换更适合表达为两个局部基准间关系时，使用 AssemblyHelper/build123d Joint：

- 盖板到底座、盖到框架、支架到导轨、法兰到管、销到孔、轴到轴承
- 铰链、滑块、螺旋、圆柱、球铰等运动定位装配
- 已暴露 Joint 的重复件或库件
- 某个尺寸变化后应自动重算放置的源码装配

简单静态阵列可用参数化且有说明的 `Location(...)`，如一排相同垫片或展示用爆炸图。

高级情况可直接用原生 Joint，但保持“固定端在前”的方向：在固定/根 Joint 上调用 `connect_to()`，传入移动零件 Joint。它是源码生成操作，不是 STEP 中持续存在的约束。

## Joint 类型

- `RigidJoint` / `asm.rigid_frame()`：固定放置、面对面、安装基准、接口已知的导入件。
- `RevoluteJoint` / `asm.revolute_frame()`：铰链/旋转姿态；用 `Axis` 定义，静态 STEP 姿态由角度参数驱动。
- `LinearJoint` / `asm.linear_frame()`：滑块、锁扣、伸缩件；用 `Axis` 定义，位置参数驱动。
- `CylindricalJoint` / `asm.cylindrical_frame()`：轴向平移 + 旋转，如螺旋或槽内销。
- `BallJoint` / `asm.ball_frame()`：万向/球面定向；用 `Location` 和角度范围。

只有最终静态位置重要且没有有意义 Joint 基准时，才用显式 `Location`，并进行验证。

## 装配定位流程

1. 选择固定/根组件。
2. 在放置子件前定义每个零件的局部 frame 和基准。
3. 识别配合面、螺钉轴、铰链轴、滑轨轴、定位舌、垫片偏移和接触平面。
4. 用 `asm.rigid_frame()`、`revolute_frame()`、`linear_frame()` 等为每个子件命名 Joint/mate datum。
5. AssemblyHelper 关系更清楚时使用关系方法，否则用参数化 `Location`。
6. 用 `asm.build()` 构造带标签 Compound。
7. 从 Python 源生成，禁止重新导入生成后的 STEP：

```bash
python scripts/step path/to/assembly.py
python scripts/inspect refs path/to/assembly.step --facts --planes --positioning
```

## CLI 对齐验证

生成后，从 `refs --positioning` 返回的局部选择器选择 moving/target 并计算差量：

```bash
python scripts/inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

共面贴合使用 `--mode flush`；中心线、平面中心或对称对齐在选择器支持时用 `--mode center`。差量超差时回源码修正，重新生成并复查。

## Frame 验证

```bash
python scripts/inspect frame path/to/assembly.step '#selector'
```

适用场景：子件方向错误、配合面世界坐标偏移、轴应与 X/Y/Z 对齐、重复件方向应一致、下游需要稳定坐标系。

## 测量验证

```bash
python scripts/inspect measure path/to/assembly.step \
  --from '#selector_a' \
  --to '#selector_b' \
  --axis z
```

示例：

- 盖板底面到底座顶面贴合应为 0 mm
- 两个螺钉轴的 X/Y 应一致
- 支架安装面距基准面应为指定距离
- 垫片高度应等于请求偏移

## 源码级修正

定位失败时只修正以下一项或最小组合：

- 子件 `Location` 平移/旋转
- AssemblyHelper 固定/移动顺序或 offset
- build123d Joint 位置或轴
- 零件局部原点约定
- 特征偏移参数
- 草图平面或工作平面
- 装配层级
- 对称放置符号

修正后重新生成，禁止直接补丁 STEP。

## 定位报告

只报告真正执行的检查：

```text
定位/Joint：
- 源码使用 RigidJoint lid_seat → underside
- 底座/盖板 Z 配合：flush，delta 0.00 mm
- 螺钉柱轴线：已在 XY 测量对齐
- 盖板实例 frame：+Z 向上，原点在装配中心线
```

没有定位敏感特征时写：

```text
定位：除居中的零件局部原点外不适用。
```

计划了配合/对齐但没有检查时写 `未检查`，不得暗示成功。
