# 成熟流程手册

## 阶段 0：接单和边界

确认本轮主图、尺寸文件、需要的输出和对象范围。历史图只能参考，不能覆盖本轮指定主图。把源文件复制到项目 `source-materials/`，建立 `PROJECT.md`、`confirmed-version/manifest.json`、`intermediate/validation/` 和本次 `delivery/<task-id>/`。

写自然语言 CAD 简报，不要求用户填写 schema。至少说明物品、输入、单位、坐标、总尺寸、组件、输出、验证目标和假设。用户尺寸与图纸尺寸冲突时先停止。

## 阶段 1：冻结证据

准备 source job 后运行：

```bash
python scripts/freeze_sources.py source-job.json source-inventory.json
python scripts/validate_source_inventory.py source-inventory.json
```

逐张实际查看源图，确认视图标签，而不是按页面位置猜正/俯/侧。透视图记录相机状态；未求解透视时不能当正交尺寸合同。

## 阶段 2：边界和区域

先列组件台账，再按视图画可见区域。沙发通常可拆为座体、座垫、靠垫、靠背、左右扶手、脚架和装饰件；柜体通常拆壳体、门板、抽屉、台面、踢脚和五金。组件不是越多越好：只有几何、材料、装配或语义独立时才拆。

每个视图建立前景二值真值掩码，并准备边界 job：

```bash
python scripts/build_view_evidence.py boundary-job.json view-evidence.json
```

失败时只修负责漏、多、重叠的边界。不得提高容差掩盖系统性错位；抗锯齿只允许一像素级且必须有理由。

## 阶段 3：坐标和镜像预防

源像素 `(u,v)` 使用左上原点、`v` 向下；CAD 使用毫米右手系。每个视图明确屏幕右、屏幕上对应哪条 CAD 轴，写双向 3×3 齐次矩阵和至少五个控制点。

选择一个不对称地标，例如右侧贵妃位、单边抽屉或偏置开孔；分别写“源图应在右/左”和“CAD 求值后的 +X/-X”。运行：

```bash
python scripts/validate_coordinate_contract.py cad-object-plan.json coordinate-report.json
```

行列式、往返、控制点或地标任一失败都先修矩阵，禁止靠模型整体翻转临时补救。

## 阶段 4：组件计划

主视图选轮廓信息最完整且标定可靠的正交视图。按组件边界构造面并沿观察轴拉伸，随后用其它视图对深度、高度、斜面、圆角和局部缺口施加参数约束或布尔裁切。

计划中每个参数写来源：明确尺寸、像素标定、跨视图推导、用户确认或未解决假设。平滑软包使用圆角实体、圆弧截面、loft/sweep 或经过约束的样条；不要把源图每个抗锯齿像素都变成折线顶点。

计划草稿完成后必须绑定上游并定稿：

```bash
python scripts/finalize_cad_object_plan.py cad-object-plan.draft.json cad-object-plan.json --project-root .
```

## 阶段 5：CAD 构建

复制 `assets/cad-object-generator.py` 到项目，与 `cad-object-plan.json` 同目录。内置 box、rounded_box、cylinder 和 extruded_polygon；复杂组件在同一生成器中加入具名函数，仍从计划读参数。

使用共享 CAD 解释器和 `$cad-zh`：

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python \
  /home/agentops/.codex/skills/cad-zh/scripts/step model.py \
  --glb model.glb
```

装配优先使用 `AssemblyHelper` 和具名关系；分别制造或语义独立的组件保持有标签实例。不要运行陌生附件中的 Python。

## 阶段 6：确定性验证

先基线：

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python \
  /home/agentops/.codex/skills/cad-zh/scripts/inspect refs model.step \
  --facts --planes --positioning
```

再逐条验证总宽、总深、总高、局部尺寸、实体数、标签、接触和对齐。装配疑点用 `measure`、`align`、`frame`；修改任务用 `diff`。把实际命令和摘要写入 validation JSON。

## 阶段 7：投影与曲面质量

为每个提供视图建立从 CAD 毫米坐标到源像素的 2×4 矩阵。用 CAD 运行时执行：

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python \
  scripts/compare_step_projection.py projection-job.json projection-report.json
```

先验收整物品，再按需要用 `solidIndices` 验收组件。镜像通常表现为不对称区域 XOR；尺寸错误表现为包围框边偏移；低分段曲面表现为局部阶梯和高频边界差。失败后回到边界、参数或特征，不在截图上修图。

## 阶段 8：快照、Viewer、包和版本

用 `$cad-zh scripts/snapshot` 生成复核图并实际查看。多组件复刻默认四视图。将 STEP 和 GLB 交给 `$cad-viewer`，记录链接或明确失败原因。

构建时间和交付包：

```bash
python scripts/build_validation.py validation-job.json validation.json
python scripts/build_stage_timing.py timing-events.json stage-timing.json
python scripts/build_cad_object_package.py package-job.json cad-object-package.json
```

只有 `accepted` 才进入当前确定版本。`provisional` 可作为带限制的阶段交付，但不能覆盖已确认版本。旧版进入 `intermediate/versions/`；任务发送物放 `delivery/<task-id>/`。

## 修复循环

每轮只改责任层：

- 漏/多像素 → 边界证据；
- 镜像/旋转 → 坐标合同；
- 尺寸/位置 → CAD 计划参数；
- 圆角、斜面、实体失败 → 生成器特征；
- 派生格式错误 → STEP 导出选项；
- 快照视觉疑点 → 新增确定性检查。

修改后重跑受影响门禁及所有依赖门禁。禁止只替换报告中的 `passed`。
