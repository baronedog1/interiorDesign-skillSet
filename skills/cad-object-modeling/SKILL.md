---
name: cad-object-modeling
description: 基于产品照片、渲染图、尺寸图以及俯视、正视、侧视等单视图或多视图，为单个家具、设备、五金、外壳、定制物品或可拆组件建立可审计的 STEP 优先 CAD 模型，并交付 build123d 生成器、STEP、原生 GLB、投影比对、CAD 快照和物品包。用户说“物品建模”“用 Text2CAD/CAD 复刻这个产品”“根据三视图做 STEP”“把照片中的家具做成 CAD”或要求解决镜像、轮廓、尺寸、组件拼接问题时使用。完整户型、仅 Three.js/HTML 单品、纯效果图、BIM、CAM、有限元或工程认证不使用本 Skill。
---

# CAD 物品建模

版本：1.0.0

## 目标

把产品资料编译为一条可追溯的 CAD 事实链：冻结输入、逐视图分区、统一坐标、组件化参数计划、build123d/STEP 构建、确定性检查、逐视图投影验收、快照复核和交付打包。STEP/B-Rep 是唯一三维几何事实；GLB、截图和预览只能从同一 STEP 派生。

## 快速导航

- 数据对象、状态与哈希关系：读取 `data_contract.md`。
- 从接单到交付的逐阶段操作：读取 `playbook.md`。
- 本机 CAD、Viewer 和命令入口：读取 `local_runtime.md`。
- 脚本参数与失败码：读取 `scripts_logic.md`。
- 可复制的 CAD 生成器骨架：读取 `templates.md`，复制 `assets/cad-object-generator.py`。
- 输入等级：读取 `references/input-grading.md`。
- 坐标、镜像和相机规则：读取 `references/coordinate-contract.md`。
- 推断与停止条件：读取 `references/inference-policy.md`。
- 常用家具/产品构造策略：读取 `references/text2cad-recipes.md`。

## 核心思想

每个已提供视图都是模型投影必须满足的几何约束，不是气氛参考。先在源分辨率上把前景分成互不重叠的组件可见区域，再为每个组件建立同一右手坐标系中的参数化 B-Rep；主视图确定轮廓和主要拉伸，其余正交视图裁剪或约束深度、高度和局部特征。最后把生成后的 STEP 重新投影回每个提供视图，逐像素或按已声明公差验收。

不要把“自动描点”与“边界”混为一谈。事实对象是闭合边界和其覆盖的区域；采样点只是边界的编码。没有源像素、标注或用户确认支持的点不得进入边界，前景区域也不得无故缺失。

## 唯一事实流

```text
原始资料
→ interior.cad-object-source-inventory.v1
→ interior.cad-object-view-evidence.v1
→ interior.cad-object-plan.v1
→ build123d 生成器
→ 主 STEP/B-Rep
→ interior.cad-object-validation.v1
→ interior.cad-object-package.v1
```

同一物品不得并存第二套手写三维尺寸、第二份组件坐标或独立修改的 GLB/HTML 几何。任何修正都回到证据、计划或生成器，重生 STEP 后再派生其它格式。

## 标准流程

1. **锁定任务与项目。** 建立独立项目目录，保存用户原文件，不覆盖旧确定版本。写简短 CAD 简报；尺寸标注优先于像素比例，冲突时停止并指出冲突。
2. **冻结来源。** 为每个文件记录哈希、原始分辨率、视图类型、观察轴、投影类型、比例标定和尺寸事实。运行 `scripts/freeze_sources.py` 与 `scripts/validate_source_inventory.py`，得到 A/B/C 输入等级。
3. **逐视图分区。** 在每张源图原始像素坐标中，按真实组件画闭合边界并生成区域掩码。运行 `scripts/build_view_evidence.py`；默认要求前景零漏像素、零多像素、组件可见区域零重叠。遮挡只登记可见区域，禁止凭空补画被遮挡像素。
4. **建立坐标合同。** 固定 `+X=右、+Y=后、+Z=上` 的毫米右手坐标；每个检查图登记可逆变换、至少五个往返控制点和不对称地标方向。运行 `scripts/validate_coordinate_contract.py`，先消灭旋转、翻转和镜像错误。
5. **组件化 CAD 计划。** 每个可制造、可装配或语义独立部件拥有稳定 `componentId`、证据 ID、参数来源、局部原点、构造方式、放置关系和推断状态。按主视图轮廓构造，再用其余视图约束或裁切；运行 `scripts/finalize_cad_object_plan.py` 绑定全部上游并写入 `planHash`。不要先写一坨不可维护网格。
6. **生成 STEP。** 读取 `$cad-zh` 的 `cad-brief.md`、`build123d-modeling.md`、`step-generation.md`；复制并按需扩展 `assets/cad-object-generator.py`。只执行本轮已审计的生成器。通过 `$cad-zh` 的 `scripts/step` 生成主 STEP，并在同一次运行中按需派生原生 GLB。
7. **确定性检查。** 对主 STEP 运行 `$cad-zh scripts/inspect refs ... --facts --planes --positioning`，再按每个尺寸、接触、对齐、实体数和标签使用 `measure`、`align`、`frame` 或 `diff`。几何修改只能回到生成器。
8. **投影门禁。** 从主 STEP 按坐标合同生成正交投影，运行 `scripts/compare_step_projection.py` 对每个已提供视图和组件证据比较。任何镜像、轮廓错位、遗漏、锯齿近似或超公差都退回第 3–7 步。
9. **视觉复核。** 按 `$cad-zh` 的 `snapshot-review.md` 为主 STEP 生成至少一张快照；多组件或复刻任务默认生成轴测、反向轴测、俯视和正视。实际查看每张图，将视觉疑点转为确定性检查。
10. **Viewer 与打包。** 将 STEP/GLB 交给 `$cad-viewer`；记录成功链接或不可用原因。依次运行 `scripts/build_validation.py`、`scripts/build_stage_timing.py` 和 `scripts/build_cad_object_package.py`。最终报告列出文件、Viewer、快照、检查、假设、限制和逐阶段耗时。

## 输入等级与交付状态

- A 级：三个互相正交且已标定的视图，并有 X/Y/Z 明确尺寸。完成全部门禁且没有未解决推断时，包可为 `accepted`。
- B 级：至少一个已标定正交视图和一个明确尺寸。可以建模，但未观察侧面、背面或内部必须标为推断，包为 `provisional`，除非用户补证据或确认。
- C 级：只有未标定透视图或无法确定相机/尺度。先求解相机、获取一个尺度或向用户提一个聚焦问题；不得声称严格复刻。

详见 `references/input-grading.md` 和 `references/inference-policy.md`。输入等级描述证据充分度，不代表模型质量。

## 不可妥协的门禁

- 源文件、尺寸、边界、计划、生成器、STEP 与验证报告必须以 SHA-256 相互绑定。
- 源图坐标是唯一二维事实；裁切、放大、旋转图仅供检查，必须有可逆矩阵和控制点。
- 提供哪个面，就必须验收哪个面；不得用漂亮轴测图代替正交投影比对。
- 组件在每个视图的可见区域必须一对一消费；不得为通过碰撞或投影而删、缩、移源组件。
- 不对称地标、坐标行列式和投影结果三重检查镜像。
- 曲线边界使用圆弧、样条、圆角、loft 或 sweep 等 CAD 特征；禁止用低分段折线冒充平滑曲面。圆角半径和曲线采样必须参数化并在快照中检查。
- STEP 是主产物。STL、3MF、GLB、PNG 和 HTML Viewer 都不能反向成为几何事实。
- 所有尺寸、接口和定位结论只报告实际运行过的检查；不声称结构安全、制造公差、认证或材料性能。

## 停止条件

遇到以下任一情况，不得生成 `accepted` 包：尺寸来源冲突；源图不完整且缺失处影响配合/安全；正交视图互相矛盾；坐标往返或不对称检查失败；区域存在未解释的漏/多像素；STEP 无有效正体积实体；组件标签或数量不符；任一必需投影失败；快照未实际查看；验证文件与 STEP 哈希不一致。

## 交付边界

本 Skill 只交付单个物品的项目级 CAD 包，不直接改写既有活动家具 HTML Skill，不写入通用组件库，也不处理完整户型、空间渲染、视频或社区发布。需要交互审阅时调用 `$cad-viewer`；需要平台上传时把已验收产物交给相应发布 Skill。
