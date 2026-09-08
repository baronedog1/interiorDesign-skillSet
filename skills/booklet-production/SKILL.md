---
name: booklet-production
description: 将同一室内设计方案的布局、空间图片、材料与用户产品整理成杂志式 HTML 和 PDF 方案册；用户只要图片时不调用。不负责重新建模或生成效果图。
metadata: {"version":"4.1.1","source_authority":"lecoo-windows-device","category":"interior-design"}
---

# 室内设计方案册

用户要求完整方案、设计图册或 PDF 时调用。读取当前项目资料，按设计故事组织页面，运行 `scripts/run.py brief.json --out <任务目录>`，得到高清 PDF、发送版 PDF、可离线 HTML 和逐页预览。输入字段见 [数据合同](data_contract.md)，方法与版式选择见 [制作方法](playbook.md)。

高频数据入口：当前 `C:\AgentWorkspaces\InteriorDesign\projects\<projectId>` 中的同版布局 JSON、模型、机位、实际渲染图片及回执；临时项目则读取用户当前隔离目录。按 projectId、version、shotId 定位，不取其它项目的漂亮图片填空。客户资料缺失先回查当前任务产物；仍缺则说明缺口并标阶段方案。首次使用先按 [运行环境](local_runtime.md) 确认 Python、Chrome 和字体可用。

先完成户型规划 → HTML 建模 → 机位 → 用户风格 CMF／必要选型 → 更新后的同机位截图 → 原生绘图，再入册；已有同版成果按需复用，不重复执行全链。完整方案不代表施工图、工程预算或工程可实施承诺。

普通客户册用最终效果图讲空间，布局说明使用真实布局图。截图不得冒充原生渲染；缺效果图可以明确交付“阶段方案”，不伪造完成。白模不是必需输入：默认不加机位小图；用户需要对照时可加入同 shotId 的完整模型或显式空槽参照。

保留真实图的结构、比例和用户资产身份，不为了版面拉伸图片；平面图完整呈现。主图、图文、双图、材料页按内容选择，不固定每空间一套版式或固定页数。客户信息与素材只存在来酷项目目录；本 Skill 不读 API Key。需要平台素材或上传时调用 `idk-canvas-ingest-agent`，本机 PDF 不自动公开。

运行环境见 [local_runtime.md](local_runtime.md)，脚本说明见 [scripts/scripts.md](scripts/scripts.md)，[流程说明书](SKILL_MANUAL.pdf)，[视觉样册及适用边界](expected_outcome/expected_outcome.md)。

每一步必须记录开始、完成、耗时及状态，遵循[统一时间合同](../interior-html-modeling/playbook/timing.md)；正式命令自动记录，读图、识图、原生调用与交付等待随执行登记，不事后补时间。

用户说“交付方案”但未明确格式，默认交付带文字说明的 booklet-highres.pdf；只有明确仅要图片才省略 PDF。每张 render 图片关联 resultPath、shotId、schemeId；同一空间多机位一起讲清布局与材料，源图低分辨率不能靠放大宣称高清。
