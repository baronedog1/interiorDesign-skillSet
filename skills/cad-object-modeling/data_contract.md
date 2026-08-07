# 数据合同

本 Skill 只有一条几何事实链。每个 JSON 必须通过 `schema`、稳定 ID、相对项目路径和 SHA-256 指向上游，禁止靠文件名相似或目录搜索猜测关联。

## 1. 来源清单

`interior.cad-object-source-inventory.v1` 冻结：

- `objectId`、单位和项目根；
- 每个源文件的 `sourceId`、路径、字节数、SHA-256、原始像素尺寸；
- `viewId`、`projection`、`normalAxis`、画面横/纵轴；
- 比例标定及明确尺寸事实；
- A/B/C `inputGrade` 与严格交付资格。

该对象只能由 `scripts/freeze_sources.py` 生成，并由 `scripts/validate_source_inventory.py` 重验原文件。

## 2. 逐视图证据

`interior.cad-object-view-evidence.v1` 以源分辨率保存每个视图的：

- 前景真值掩码及哈希；
- 每个 `componentId` 的闭合边界环、孔洞、可见区域掩码、像素数和包围框；
- 组件区域的漏像素、多像素和互相重叠计数；
- 明确的像素公差与理由。

边界环是区域的编码，区域才是比较事实。被遮挡部分不得伪造成可见像素；同一可见像素默认只能属于一个组件。

## 3. CAD 计划

`interior.cad-object-plan.v1` 是唯一参数与组件坐标事实，至少包含：

- 固定毫米右手坐标：`+X=right`、`+Y=back`、`+Z=up`；
- 每个视图的 `sourceToPlane` / `planeToSource` 可逆矩阵、控制点和方向检查；
- 总尺寸及每个参数的证据来源；
- 逐组件 `componentId`、标签、角色、构造类型、局部变换、证据 ID；
- 接触、包含、对齐、Joint 或装配关系；
- 每个未观察事实的假设、状态和影响；
- 各视图投影目标与公差。

`planHash` 为移除自身字段后的规范 JSON SHA-256。生成器读取这份计划；不得在源码中再维护一份冲突尺寸。

## 4. 主几何与派生物

主几何是 `.step`/`.stp`。build123d Python 是可编辑生成源；STEP 是验证对象。原生 `.glb`、隐藏 Viewer GLB、STL、3MF 和图片全部从同次 STEP 流程派生。

每个产物记录相对项目路径、SHA-256、字节数和生成命令。禁止手工编辑派生 GLB 后继续沿用旧 STEP 的验证结论。

## 5. 验证报告

`interior.cad-object-validation.v1` 必须绑定 `sourceInventorySha256`、`planSha256`、`generatorSha256` 和 `stepSha256`，并逐项记录：

- 来源、坐标合同；
- STEP 生成和有效正体积实体；
- 包围盒与全部明确尺寸；
- 组件数量、标签和装配关系；
- 每个提供视图的投影结果；
- 快照已生成且已人工查看；
- Viewer 交接状态；
- 实际命令、事实摘要、限制。

`overallStatus=passed` 只有在所有必需门禁为 `true` 时成立。

## 6. 阶段耗时

`interior.cad-object-stage-timing.v1` 记录阶段起止、活动和毫秒耗时。`totalDurationMs` 必须等于各阶段 `durationMs` 之和；墙钟跨度和未归属间隙单独记录，不能混入阶段总和。

## 7. 交付包

`interior.cad-object-package.v1` 是唯一交付入口，绑定上述对象和全部文件事实：

- `accepted`：A 级输入、无未解决假设、全部门禁通过；
- `provisional`：几何检查通过，但输入不足或仍有明确推断；
- `rejected` 不可作为正式交付，由构建脚本直接失败并保留验证证据。

包内只引用项目根内文件。`accepted` 与 `provisional` 都不能隐藏限制；后者必须明确列出还需用户确认或补充的证据。
