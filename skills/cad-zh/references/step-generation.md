# STEP 生成

从 build123d Python 源码生成/重新生成 STEP/STP，或直接处理 STEP/STP 时读取。

## 工具

入口位于 CAD Skill 目录：

```bash
python scripts/step [--kind {part|assembly}] targets... [flags]
```

只传入明确目标。目标路径从命令当前目录解析，绝不能依赖整目录生成。

普通 Python 目标默认写出同目录同名 `.step`。`-o`/`--output` 只可用于一个普通 Python 目标；多个目标需要使用 `SOURCE.py=OUTPUT.step` 位置参数对。成对输出路径也从命令当前目录解析，并且只能用于生成型 Python，不能用于直接 STEP/STP 输入。不要让 `gen_step()` 返回输出路径；输出由 CLI 控制。

## Python 生成器

从零设计或修改生成模型时，这是默认入口。生成型 build123d 源码必须定义：

```python
def gen_step():
    ...
    return step_ready_shape_or_labeled_compound
```

工具根据源码元数据和 `gen_step()` 返回值推断零件/装配类型：

```bash
python scripts/step path/to/part.py
python scripts/step path/to/part.py -o path/to/custom.step
python scripts/step path/to/a.py=out/a.step path/to/b.py=out/b.step
python scripts/step path/to/assembly.py
```

若把生成型装配的 `.step` 直接传入，工具会把它当原生导入 STEP，丢失源码级装配组合。必须传 `.py` 装配源码。生成装配体时优先在源码中使用 `cadpy.assembly.AssemblyHelper`，以便导出前保留原生标签、具名 mate frame 和源码关系，参见 `positioning.md`。

## 直接 STEP/STP

没有生成器（下载件、导入件），或用户明确指定 STEP/STP 为目标时使用：

```bash
python scripts/step --kind part path/to/imported.step
```

直接目标支持与生成器相同的网格旁车参数；STL/3MF/GLB 见 `supported-exports.md`。

## Viewer 产物

每次 `scripts/step` 运行都会生成相邻的隐藏 GLB/拓扑文件。它们支持 CAD Viewer、`$cad-viewer` 和 `scripts/inspect`，是 STEP 主流程必需产物。

## 生成后

- 确认命令成功，STEP 文件存在且非空。
- 按 `inspection-and-validation.md` 运行基线和规格检查：

```bash
python scripts/inspect refs path/to/model.step --facts --planes --positioning
```

