# 基于当前模型图直接生成效果图 说明书（AI 读取版）

版本：25.0.0

## YAML 头

```yaml
---
name: interior-space-rendering
description: 当 Camera 已生成同名 PNG 与 interior.camera-image-facts.v3，需要保持当前户型、机位和家具布局生成写实效果图时使用。直接编译一次正式 ImageGen 请求；视觉评估只提示并始终交付已生成图片。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"camera_facts_schema":"interior.camera-image-facts.v3","render_plan_schema":"interior.model-image-render-plan.v13","render_context_schema":"interior.render-context.v9","version":"25.0.0"}
---
```

## 思路


## 调用场景

1. **从当前模型机位图直接生成并交付写实效果图**：用户需要的不是再跑一轮场景验收，而是把当前模型图快速变成可看的效果图。系统直接读取 Camera 同名 PNG 与 camera-image-facts.v3：PNG 锁定当前相机、墙门窗、家具排列和画面范围，JSON 锁定对象身份、类别、数量、世界位置、尺寸与朝向。编译器一次生成正式 ImageGen 请求，工具返回图片就立即交付。构图、材质、灯光、轻微软装或局部外观不理想时，用自然语言提示用户并进入公共算法改进清单，不能把当前图片扣住，也不能自动重复生成。只有输入文件损坏、身份冲突、工具没有图片或缺少高风险授权时才停止。 输入：同名 camera-image-facts.v3 与 PNG、风格、可选参考图 输出：render-plan.v13、context v9、request v5、正式图片和 render-delivery.v1

## 完整文件

当前文件数：22

- `ENVIRONMENT_CONTRACT.md`：说明共享源、Ubuntu 安装、Python 和 ImageGen 边界。
- `MANIFEST.json`：登记版本和全部活动文件。
- `SKILL.md`：定义直接 Camera v3 交接、非阻断质量策略和停止条件。
- `SKILL_MANUAL.pdf`：人类 A3 说明书。
- `agents/openai.yaml`：提供默认调用提示。
- `data_contract.md`：定义输入、plan、context、request 和 delivery。
- `local_runtime.md`：给出本地确定性命令。
- `playbook.md`：说明读取、生成、失败处理和交付。
- `references/architectural-styling-playbook.md`：指导结构表面与固定产品的风格化。
- `references/cabinet-and-decor-playbook.md`：指导柜体和非结构装饰。
- `references/ceiling-and-lighting-playbook.md`：指导天花和灯光。
- `references/design-intent-routing.md`：区分结构修改与保持布局渲染。
- `references/skill-flowchart.svg`：派生的矢量流程图。
- `references/skill-manual.json`：说明书唯一结构化事实源。
- `references/skill-manual.md`：派生的 AI 完整说明。
- `references/style-guides/maillard.md`：美拉德风格参考。
- `references/style-guides/mid-century.md`：中古风格参考。
- `references/style-guides/modern-minimal.md`：现代简约风格参考。
- `references/window-door-balcony-playbook.md`：指导门窗和阳台边界。
- `scripts/compile_render_request.py`：直接编译渲染计划、上下文、请求和批计划。
- `scripts/finalize_render_delivery.py`：绑定实际图片并写非阻断交付回执。
- `scripts_logic.md`：登记正式脚本职责。

## 具体逻辑解释


完整真实分支、回退路径和文件节点见根目录 `SKILL_MANUAL.pdf`。
