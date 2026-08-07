# 脚本逻辑

所有脚本均为确定性编译或校验工具，不替 Agent 决定物品语义。命令失败必须修上游事实，禁止直接改输出 JSON。

## `freeze_sources.py`

输入 source job，输出 `interior.cad-object-source-inventory.v1`。解析相对项目根的文件，计算哈希、字节数、图像尺寸、正交轴和比例标定，按规则计算 A/B/C 等级。源文件越界、重复 ID、尺寸无效或哈希读取失败返回非零。

## `validate_source_inventory.py`

重新读取所有源文件，重算哈希、像素尺寸、等级和 inventory hash。适合在进入下一阶段和最终打包前运行。

## `build_view_evidence.py`

把闭合边界环确定性栅格化为逐组件二值掩码，并与已冻结的前景真值掩码比较。默认 `maxMissingPixels=0`、`maxExtraPixels=0`、`maxOverlapPixels=0`。边界越界、自交、缺少组件、掩码尺寸不符或门禁失败返回非零，但仍写报告便于定位。

## `validate_coordinate_contract.py`

验证固定右手轴、双向 3×3 变换互逆、至少五个控制点、源像素往返误差、平面误差和不对称地标。失败报告指出具体 `viewId` 和误差。

## `finalize_cad_object_plan.py`

绑定来源清单与逐视图证据文件，检查 ID、关系和视图引用唯一性，写入规范 `planHash` 并按 schema 验证。生成器只能读取该 finalizer 输出，不能读取未签名草稿。

## `compare_step_projection.py`

必须用 CAD 解释器运行。它通过 build123d 导入主 STEP、三角化 B-Rep、按 2×4 `cadToSource` 矩阵栅格化整物品或指定 `solidIndices`，再与二值证据掩码计算 XOR、IoU、包围框和质心。写出实际投影掩码与叠图；任一必需目标超公差时返回非零。

## `build_stage_timing.py`

解析带时区 ISO-8601 阶段事件，计算每阶段毫秒、阶段合计、墙钟跨度和未归属间隙。阶段合计严格等于输出总耗时；重叠或结束早于开始直接失败。

## `build_validation.py`

绑定来源、区域、坐标报告、生成器、STEP、CAD inspect 原始事实、逐尺寸/标签/关系检查、STEP 投影、已查看快照和 Viewer 交接；门禁由输入证据计算，失败仍输出 `overallStatus=failed` 报告。

## `build_cad_object_package.py`

读取 package job，重验 inventory、plan、generator、STEP、validation、evidence、GLB、快照和 timing 的路径与 SHA-256。验证门禁失败时不生成正式包；A 级且无未解决假设生成 `accepted`，否则只有 job 明确 `allowProvisional=true` 才生成 `provisional`。

## `validate_skill.py`

校验 Skill frontmatter、UI 元数据、MANIFEST 精确文件图、JSON Schema、Python 语法、唯一工作流关键字和禁用占位符。它验证 Skill 包本身，不验证某个产品包。

## 退出约定

- `0`：脚本完成且相应门禁通过；
- `1`：输入、合同、几何或门禁失败；
- `2`：命令参数错误，由 argparse 返回。

所有失败脚本尽量先写结构化报告再退出 1，便于审计和最小修复。
