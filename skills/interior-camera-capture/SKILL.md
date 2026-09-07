---
name: interior-camera-capture
description: 当当前整屋 HTML、Blender 或 CAD 模型需要按空间自动求机位、截图并输出同名场景事实 JSON 时使用。唯一求解器优先选择目标房间内的自然正视镜头，并用目标房间墙体投影统一裁切左右和底部非目标区域。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"camera_plan_schema":"interior.algorithmic-camera-plan.v3","image_facts_schema":"interior.camera-image-facts.v3","backend_template_schema":"interior.camera-backend-template.v1","version":"47.0.1"}
---

# Interior Camera Capture

## 能力边界

本 Skill 从项目唯一当前 HTML 一次求出正式机位，并生成截图、Entity-ID、Depth 与代码场景事实。同一 revision 的 HTML、Blender、CAD 必须共用同一份冻结计划；后端差异只放在 `assets/backend-templates/` 的原生截图适配中。它不修改户型和家具，不用图片识别猜位置，也不允许 Blender/CAD 重新求机位。

客户任务只允许一个生产入口：`scripts/run_camera_pipeline.py`；其中只允许 `scripts/unified_camera_solver.py` 拥有相机决策权。其它脚本只能准备输入、渲染冻结计划、转换后端合同或做发版审计。效果图下游直接读取 Camera facts 与配对 PNG，不再生成第二份 scene-map 事实。

## 用户确认后的画面优先级

默认正式图按以下顺序处理：

1. 必拍主体完整进入画面；
2. 主体正面和真实背景墙关系正确；床、沙发、书桌等有方向主体先锁定自身正面轴，再比较镜头自然度；
3. 马桶、浴室柜、洗衣机和洗手盆等靠墙设备从最近房间边界求有符号正面，优先从设备正面侧拍摄；
4. 同一空间有多个必拍主体时，优先投影互不遮挡的严格正视墙族，避免前一件完全盖住后一件；
5. 尽量严格正视，并同时保留可理解的上方和下方空间；
6. 房内存在自然视野解时优先房内零隐藏；
7. 房内只有极端广角解时，沿同一墙法线后退并剖开真实交点墙；
8. 房内与后退镜头都按目标房间墙体/开口 Entity-ID 包络裁掉左右和底部非目标内容，顶部保持天花板不裁；
9. 对裁切后仍遮挡主体的非目标墙柱或家具做有限隐藏；
10. 主体完整、像素占比、上下空间、遮挡、FOV、移轴和边缘畸变只参与候选排序并写入质量提示，不阻断客户截图。

## 唯一生产流程

1. `run_camera_pipeline.py --backend html` 从项目唯一当前 HTML 与同 revision 结构生成临时 VTK 场景，并只在这里调用一次 `unified_camera_solver.py`。
2. 求解器先生成 provisional plan，再读取 HTML 原生射线事实完成一次同源收敛；有 `qualityPreferred=true` 候选时必须从该集合选择，只有全部候选都有提示时才交付最佳可用正视镜头。若用户已在当前任务书或平面证据中明确确认机位方向，正式入口可读取 `interior.user-camera-intent.v1`；该有向光轴优先于主体默认正面轴，并必须携带可追溯来源。
3. 冻结唯一 `interior.algorithmic-camera-plan.v3`。同一 revision 后续运行 `--backend blender|cad --camera-plan <该文件>`；后端模板只能消费，不能生成或修改计划。
4. Blender/CAD 若没有同户型冻结计划就明确停止，不以自身场景重新求解、不创建代理场景、不使用历史坐标。
5. 冻结唯一 `interior.algorithmic-camera-plan.v3`；HTML、Blender、CAD 原生截图器按原值应用 position、target、FOV、windowCenter、隐藏集合和 projectionCrop，不拥有重新取景权。
6. 每张正式 PNG 配同名 `interior.camera-image-facts.v3` JSON；需要效果图时把 `camera-image-facts.v3 + 同名 PNG` 直接交给 `interior-space-rendering`。
7. 客户任务始终交付已经生成的截图。发版审计只用于改进通用算法，不允许扣住客户图片或逐图手改坐标。

## 单图与多图

- 单图优先主体完整的严格正视主图。
- 多图第一张仍按单图规则；后续仍只从其它真实墙法线对应的严格正视解中选择，不允许斜视分支。
- 所有输出都由同一求解器选择；不存在备用求解器、旧候选器或按截图人工调参入口。

## 高频数据入口

- HTML：项目唯一 `current.html`/`current-model.json` 与同 revision `structure-data.json`。
- Blender：accepted `.blend`、同 revision 结构和 HTML 已冻结的 v3 camera plan。
- CAD：accepted 原生模型、`interior.native-model-manifest.v1`、同 revision 结构和同一冻结 plan。
- 后端模板：HTML 模板拥有唯一求解入口；Blender/CAD 模板只做冻结计划消费和原生渲染适配。
- 输出合同、目录和下游状态：读 [data_contract.md](data_contract.md)。

## 文档路由

- AI 可读的完整说明书：[references/skill-manual.md](references/skill-manual.md)
- 人类可读的 A3 图文说明书：[SKILL_MANUAL.pdf](SKILL_MANUAL.pdf)
- 同源流程总览：[references/skill-flowchart.svg](references/skill-flowchart.svg)
- 完整流程与失败处理：[playbook.md](playbook.md)
- 输入输出与下游交接：[data_contract.md](data_contract.md)
- 正式脚本白名单：[scripts_logic.md](scripts_logic.md)
- Ubuntu 本地命令与依赖：[local_runtime.md](local_runtime.md)
- 设备、运行时和同步关系：[ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)
- 统一算法公式：[references/algorithm.md](references/algorithm.md)

## 禁止事项

- 禁止恢复旧求解器、旧候选器、旧评分器、后端专属选机位脚本或第二套相机方法。
- 禁止为 Blender/CAD 再次运行统一求解器；同一 revision 只能存在一份正式 plan。
- 禁止渲染器新增隐藏对象、修正 FOV、移动相机、重算裁切框或重新选角度。
- 禁止从截图进行图片识别后回写相机或 JSON。
- 禁止因为 FOV、移轴、边缘形变或非阻断评估而扣住客户截图。
- 禁止把 `qualityPreferred` 或 `qualityAdvisories` 当作客户任务门禁；只有当前模型/结构缺失、身份冲突、真实网格缺失或截图技术失败可以停止。
- 禁止把 Depth NPY 等研发证据默认作为客户附件外发。
- 禁止恢复旧 `native-capture-result.v1 -> shot-scene-map.v10 -> Q1/Q2/Q3` 中转链。

## 最小验收

- 官方 Skill 结构校验通过；
- 只有 `unified_camera_solver.py` 命中相机决策函数；
- HTML 与 Blender 最终原生截图的 plan SHA-256 必须完全相同；
- 当前十空间 HTML 案例只求解一次，Blender 使用相同 plan SHA-256 完成全部空间原生截图；
- 至少三个未参与当前案例调参的异构模型各自一次求解并截图完成；
- HTML 最终截图真实应用计划中的 FOV、windowCenter 与 projectionCrop，裁切后 JSON 投影对应最终 PNG；
- GCP 共享基线与 Ubuntu 活动副本树摘要一致；
- 两套 Bridge 全程在线且不因 Skill 文件同步而重启。
