---
name: interior-space-rendering
description: 当 Camera 已生成同名 PNG 与 interior.camera-image-facts.v3，需要保持当前户型、机位和家具布局生成写实效果图时使用。直接编译一次正式 ImageGen 请求；视觉评估只提示并始终交付已生成图片。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"camera_facts_schema":"interior.camera-image-facts.v3","render_plan_schema":"interior.model-image-render-plan.v13","render_context_schema":"interior.render-context.v9","version":"25.0.0"}
---

# Interior Space Rendering

## 能力边界

本 Skill 把 Camera 已交付的当前模型截图和同名代码事实直接编译成写实效果图请求。它不再要求 `shot-scene-map`、Q1/Q2/Q3、mask、accepted review 或其它中转门禁，也不重新求机位、改户型或移动家具。

图片只生成一次正式结果。结果构图、材质、装饰或局部表现不理想时，照常把图片和自然语言提示交给用户；这些问题用于下一次 Skill 发版改进通用算法，不能扣住当前客户任务，也不能在冻结版本里逐图手改后冒充一次成功。

## 输入

- `interior.camera-image-facts.v3` 与同目录同名 PNG；
- 一个或多个用户要求的风格；
- 可选用户家具、产品或风格参考图。

Camera facts 必须来自原生场景代码且 `imageRecognitionUsed=false`。PNG 是当前相机、结构、开口、布局和家具排列的直观事实；JSON 是对象身份、类别、数量、世界位置、尺寸、朝向与关系的代码事实。

## 唯一流程

1. 运行 `scripts/compile_render_request.py`，直接读取 Camera v3 facts 与配对 PNG。
2. 编译 `render-plan.v13`、`render-context.v9`、每图 `imagegen-request.v5` 和可选 `imagegen.batch-plan.v1`。
3. 每个 shot/style 只调用一次正式 ImageGen。多图可交给 `imagegen-batch-orchestrator`，但质量不触发自动重试。
4. 工具返回图片后运行 `scripts/finalize_render_delivery.py`，绑定请求、图片摘要和质量提示。
5. 把图片、同名交付回执和质量提示一起发给用户。发现问题继续改公共算法，不撤回已生成图。

## 质量与停止条件

以下只形成 `qualityAdvisories`，永不阻断交付：构图不理想、材质偏差、灯光层次、轻微透视、软装差异、局部家具外观差异、动线风险、对象投影贴边、机位 FOV、执行耗时和视觉评分。

只有四类真实技术问题可以停止当前调用：

1. Camera facts 或配对 PNG 不存在、不可读或摘要损坏；
2. 项目、shot 或模型身份互相冲突，无法判断该用哪一份事实；
3. ImageGen 工具真实失败，没有返回可读图片；
4. 当前动作涉及付费、公开发布、删除、覆盖生产数据或批量外发且尚未获得授权。

技术问题不能用旧 schema、历史图片、手写 scene map、白模替代或质量降级绕过；应修复事实源或工具后，从当前 Camera facts 继续。

## 高频数据入口

- 当前机位事实：项目 `camera/**/delivery/*.json`，schema 为 `interior.camera-image-facts.v3`。
- 配对模型截图：JSON 的 `image.filename` 指向同目录 PNG，摘要必须一致。
- 详细数据和产物合同：[data_contract.md](data_contract.md)。
- 风格和结构处理参考：[references/design-intent-routing.md](references/design-intent-routing.md) 及本 Skill 其它风格 playbook。

## 文档路由

- 执行、失败处理和交付：[playbook.md](playbook.md)
- 数据对象与目录：[data_contract.md](data_contract.md)
- 两个正式脚本：[scripts_logic.md](scripts_logic.md)
- Ubuntu 命令：[local_runtime.md](local_runtime.md)
- 运行环境：[ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)
- AI 完整说明：[references/skill-manual.md](references/skill-manual.md)
- 人类说明：[SKILL_MANUAL.pdf](SKILL_MANUAL.pdf)
- 流程总览：[references/skill-flowchart.svg](references/skill-flowchart.svg)

## 禁止事项

- 禁止恢复 `shot-scene-map.v10`、camera plan v9、`native-capture-result.v1` 或 Q1/Q2/Q3 中转链。
- 禁止把视觉复核、质量分、动线、FOV、耗时或 accepted 字段变成客户交付门禁。
- 禁止因为质量提示自动重复 ImageGen。
- 禁止用历史效果图、代码绘图或原生模型截图冒充本次 ImageGen 结果。
- 禁止输出 secret，或在未授权时执行付费、发布、删除和批量外发。

## 最小验收

- 真实 `camera-image-facts.v3 + PNG` 能一次编译出请求与 batch plan；
- `imagegen-batch-orchestrator` 能初始化 batch plan；
- 带任意质量提示的可读输出图仍生成 `status=delivered` 回执；
- 旧 scene-map、Q1/Q2/Q3、accepted/rejected 和 `--require-complete` 正式入口负向扫描为零；
- GCP 与 Ubuntu Skill 树摘要一致，Bridge 不因 Skill 同步重启。
