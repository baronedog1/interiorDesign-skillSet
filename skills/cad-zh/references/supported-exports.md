# 支持的次级导出

用户要求从 CAD 几何导出 STL、3MF 或原生 GLB 时读取。二维 DXF 使用 `$dxf`；DXF 有独立的 `gen_dxf()` 源码合同。

## 规则

STL、3MF 和原生 GLB 是网格旁车，不是 STEP 的替代品。先生成和验证 STEP，再从同一次 `scripts/step` 运行中导出所需格式。旁车渲染不能当 CAD 验证；仍需按标准流程检查和快照主 STEP。

原生 GLB 是供外部工具使用的普通 glTF 2.0 二进制：Y 向上、米制缩放、不包含 CAD Viewer 的 `STEP_topology` 扩展。不要把它与隐藏的 `.<name>.step.glb` Viewer 拓扑文件混淆。

## 工具

对 Python 生成器运行：

```bash
python scripts/step path/to/model.py \
  --stl meshes/model.stl \
  --3mf meshes/model.3mf \
  --glb meshes/model.glb
```

有生成器时必须使用生成器。只有生成器不可用或用户明确指定 STEP/STP 时，才直接处理：

```bash
python scripts/step --kind part path/to/model.step \
  --stl meshes/model.stl \
  --3mf meshes/model.3mf \
  --glb meshes/model.glb
```

旁车路径必须是相对路径，后缀分别为 `.stl`、`.3mf`、`.glb`，并相对 STEP 输出目录解析。

## 网格公差

默认线性偏差 `0.02`，角度偏差 `0.05`。

需要调整网格密度时使用：

```bash
--mesh-tolerance FLOAT
--mesh-angular-tolerance FLOAT
```

小型曲面零件或高视觉保真使用更小公差；大型简单几何且文件大小更重要时可放宽。

## 流程

1. 从 `gen_step()` 生成 STEP，并带所需旁车参数。
2. 对 STEP 运行 facts/planes/positioning。
3. 报告 STEP 和用户要求的旁车文件。

示例：

```bash
python scripts/step models/bracket.py \
  --stl meshes/bracket.stl \
  --glb meshes/bracket.glb \
  --mesh-tolerance 0.2 \
  --mesh-angular-tolerance 0.2

python scripts/inspect refs models/bracket.step --facts --planes --positioning
```

## 报告

```text
文件：
- STEP: /absolute/project/models/bracket.step
- STL: /absolute/project/models/meshes/bracket.stl
- GLB: /absolute/project/models/meshes/bracket.glb

验证：
- STEP 几何已验证；STL/3MF/原生 GLB 是按要求生成的旁车。
- 主 STEP/STP 快照验收：已运行，或写明跳过原因。
```

