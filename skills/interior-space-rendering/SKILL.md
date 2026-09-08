---
name: interior-space-rendering
description: 以HTML粗模锁定结构、机位和家具位置尺度，按产品参考图或精细定样锁款，通过原生绘图重建精细家具与真实光影；不锁粗模造型，不把截图当最终效果图。
metadata: {version: "3.2.4", category: interior-design}
---
# 原生绘图效果图

输入同版 scene.json、cameras.json、renders.json、粗模截图及精细家具参考图；输出原生效果图、调用回执与问题说明。粗模只管建筑、机位、家具功能/位置/朝向/约略尺度，绝不把粗模的块体或软包轮廓当锁款。锁款依据绑定的产品图片，后续同空间沿用精细定样；按参考款式放入粗模对应位置，保留产品比例，不非均匀拉伸。没有参考时可按已知需求建立概念定样，但不能声称已锁定用户产品。光影重新计算，不复制粗模照明。

默认仍传带家具的完整粗模截图；仅用户明确要求白模/空白槽位时隐藏家具，原JSON保留。此Skill生成二维效果图，不会把参考照片自动变成可编辑3D家具或回写HTML。读 [执行方法](playbook.md)，字段见 [共用合同](../interior-html-modeling/data_contract.md)。

入口 `python scripts/run.py ai-request SCENE CAMERAS RENDERS --shot ID --out request.json`；`native-prepare request.json capabilities.json --out job.json` 只准备任务，随后必须由 Agent 实际调用可用的原生图像生成工具并附完整参考图。完成后 `native-result job.json image.png invocation.json review.json --out result.json`。

有精细家具图片时，`ai-request` 加 `--products references.json`，用 placementId 绑定图片及已知真实 sizeMetres；照片锁款不要求已有品牌SKU。实际附图顺序由job给出，必须全部附上，不能只写“参考图”却漏传。新版referencePolicy分离旧定样索引，旧粗模风格定样不自动沿用。

不得伪造工具可用性或真实回执。无宿主原生绘图时明确报告该能力缺失，不偷偷改走 WebGL、商业 API 或截图美化冒充完成。平台资产/推送调用独立平台 Skill。

人读 [PDF](SKILL_MANUAL.pdf)，工具条件见 [运行说明](local_runtime.md)。

每一步必须记录开始、完成、耗时及状态，遵循[统一时间合同](../interior-html-modeling/playbook/timing.md)；正式命令自动记录，读图、识图、原生调用与交付等待随执行登记，不事后补时间。

同空间/连通客餐厅、同风格：先生成并识图确认首张定样，再准备后续机位请求；后续附当前机位截图＋定样图＋指定产品图，不能各机位独立批量首发。ai-request 自动读取同输出目录 render-series.json，可用 --anchor-result 显式指定同系列结果。

调用链：native-prepare → native-start JOB --out invocation.json → 实际调用 job 的原生工具并原样附图/提示词 → native-complete invocation.json 工具输出图片 --out invocation-completed.json → 识图 → native-result。这些登记脚本不是绘图工具，不能自行生成成功回执或调用ID。

完整设计先查看平台风格模板，提炼设计意图并写design-brief.json；ai-request加--design-brief，实际附入风格图。锁建筑壳与洞口位置尺寸，不锁粗模门窗构件、天花饰面或灯光；按同一设计意图完善硬装与陈设，不无依据加大件隔断。详见playbook。
