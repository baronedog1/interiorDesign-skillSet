---
name: interior-space-rendering
description: 将同机位完整模型截图通过宿主原生绘图生成室内效果图，保留结构、家具、机位与材质意图，登记实际调用和逐图复核；不把 WebGL 截图当最终渲染。
metadata: {version: "3.0.0", category: interior-design}
---
# 原生绘图效果图

输入同版 scene.json、cameras.json、renders.json 和实际参考 PNG；输出真实原生绘图结果、调用回执与问题说明。默认传带全部家具和细节的完整截图；只有用户明确要求“白模/空白槽位渲染”才隐藏可见家具/柜体，原 JSON 位置、尺寸和朝向保留。锁住结构与机位，细化普通家具，指定资产不变形并参考真实尺寸。读 [执行方法](playbook.md)，字段见 [共用合同](../interior-html-modeling/data_contract.md)。

入口 `python scripts/run.py ai-request SCENE CAMERAS RENDERS --shot ID --out request.json`；`native-prepare request.json capabilities.json --out job.json` 只准备任务，随后必须由 Agent 实际调用可用的原生图像生成工具并附完整参考图。完成后 `native-result job.json image.png invocation.json review.json --out result.json`。

不得伪造工具可用性或真实回执。无宿主原生绘图时明确报告该能力缺失，不偷偷改走 WebGL、商业 API 或截图美化冒充完成。平台资产/推送调用独立平台 Skill。

人读 [PDF](SKILL_MANUAL.pdf)，工具条件见 [运行说明](local_runtime.md)。

每一步必须记录开始、完成、耗时及状态，遵循[统一时间合同](../interior-html-modeling/playbook/timing.md)；正式命令自动记录，读图、识图、原生调用与交付等待随执行登记，不事后补时间。

同空间/连通客餐厅、同风格：先生成并识图确认首张定样，再准备后续机位请求；后续附当前机位截图＋定样图＋指定产品图，不能各机位独立批量首发。ai-request 自动读取同输出目录 render-series.json，可用 --anchor-result 显式指定同系列结果。

调用链：native-prepare → native-start JOB --out invocation.json → 实际调用 job 的原生工具并原样附图/提示词 → native-complete invocation.json 工具输出图片 --out invocation-completed.json → 识图 → native-result。这些登记脚本不是绘图工具，不能自行生成成功回执或调用ID。
