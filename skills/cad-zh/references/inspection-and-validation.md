# 检查与验证

每个生成的 STEP 都必须读取本文件。用户要求几何事实、选择器、尺寸、配合、差异或坐标系检查时也读取。

## 原则

确定性几何检查决定通过或失败；强制快照复核（见 `snapshot-review.md`）负责发现未被检查条件编码的语义错误。检查深度按用户规格缩放：用户明确给出的每个尺寸、间隙和关系——包括工程图尺寸——都必须用 `measure`、`align` 或 `frame` 验证。无论规格多简单，每个产物都必须运行 facts/planes/positioning 基线。

## 工具

入口位于 CAD Skill 目录：

```bash
python scripts/inspect {refs|diff|frame|measure|align|worker|batch} ...
```

目标从命令当前工作目录解析，传入相对该目录的路径。常用数据输出参数：`--format json|text`（默认为机器可读）、`--quiet`、`--verbose`。

支持的目标形式：

```text
path/to/entry
path/to/entry.step
```

选择器只在本次传入的 STEP/CAD 目标内有效，不含文件路径：

```text
#o1.2
#o1.2.f1
#f1
```

把 STEP/CAD 路径作为目标参数，把 `#...` 选择器作为另一个参数。

## 验证顺序

1. 确认生成成功，STEP/STP 存在且非空。
2. `refs --facts --planes --positioning` 确认尺度、标签、主要平面和可用于定位的引用；每个产物都必须执行。
3. 规格驱动检查：每个用户尺寸、偏移或间隙用 `measure`；应贴合或居中的接口用 `align`；实例放置与朝向用 `frame`；修改可能影响其他几何时用 `diff`。
4. 按 `snapshot-review.md` 对主 STEP/STP 做快照；视觉疑点必须转成确定性几何检查，才能成为验证结论。

## 引用发现

紧凑事实、平面和定位：

```bash
python scripts/inspect refs path/to/model.step \
  --facts --planes --positioning
```

详细检查选择器：

```bash
python scripts/inspect refs path/to/model.step '#selector' \
  --detail --positioning
```

只在必要时枚举拓扑：

```bash
python scripts/inspect refs path/to/model.step --topology
```

平面选项：

```bash
--plane-coordinate-tolerance FLOAT
--plane-min-area-ratio FLOAT
--plane-limit INT
```

普通验证使用较低 plane limit 和紧凑 facts。只有在发现选择器、调试复杂几何，或无法通过 facts/planes/measure 验证特征时才枚举全拓扑；大型模型的完整枚举开销很高。

## 测量

`measure` 用于包围距离、间隙、偏移、零件间距、板厚、孔到面距离和对齐核验：

```bash
python scripts/inspect measure path/to/model.step \
  --from '#selector_a' \
  --to '#selector_b' \
  --axis x
```

工具可在部分情况推断轴，但确定性检查应明确指定 `x`、`y` 或 `z`。

## 对齐

两个 STEP 引用应贴合或居中时使用 `align`。它返回选中引用之间需要的平移差量；任何修正都必须回到 build123d 源码（见 `positioning.md`），然后重新生成和检查。

```bash
python scripts/inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

## 坐标系检查

`frame` 用于验证实例变换和选中引用的世界坐标系：

```bash
python scripts/inspect frame path/to/model.step '#selector'
```

适用于装配体、局部到世界坐标转换和定位调试。

## 差异检查

修改任务比较前后产物：

```bash
python scripts/inspect diff path/to/before.step path/to/after.step --planes
```

修复、增加特征或修改源码可能波及其他几何时必须使用。

## 验证报告

只报告实际执行或工具输出直接支持的检查。若检查了重要选择器，在对应 CAD Viewer 链接旁返回该局部选择器。

使用以下结构：

```text
验证：
- STEP 生成：通过/部分通过/失败
- 实体/装配：<数量和标签>
- 包围盒：<尺寸与单位>
- 主要平面/引用：<摘要>
- 定位：<相关的 frame/measure/align 结果>
- 特征：<孔、开口、凸台等>
- 视觉复核：<$cad-viewer 链接；CAD scripts/snapshot PNG/GIF，或跳过原因；视觉疑点对应的几何复查>
```

除非真正执行了对应分析或有制造数据，禁止声称：

- 结构安全
- 工艺认证
- 公差合规
- 超出几何合理性的可制造性
