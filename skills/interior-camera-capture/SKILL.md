---
name: interior-camera-capture
description: 从当前完整 HTML 的真实模型寻找全屋及各空间机位，冻结相机并输出原生 WebGL 参考截图；逐图识图，不改家具或冒充效果图。
metadata: {version: "2.1.0", category: interior-design}
---
# 机位与模型截图

输入同版 scene.json/model.html 和用户主体意图；输出 cameras.json、逐张 PNG 与 renders.json。先读 [机位方法](playbook.md)，数据见 [共用合同](../interior-html-modeling/data_contract.md)。

入口 `python scripts/run.py find scene.json --out cameras.json`；截图 `python scripts/run.py capture scene.json cameras.json --out shots --mode pbr`，白模参考用 clay。可 `--shots ID1,ID2`；`apply` 创建机位审阅 HTML 副本，不覆盖源模型。

默认不移动家具、隐藏问题对象或镜像成品。唯一明确的渲染参照分支：用户要求白模/空白槽位时，capture 加 `--reference-mode empty-slots --white-model-requested`，暂时隐藏 placements 的家具/柜体图像，JSON 与机位不变，截后恢复；clay 单独使用只换灰材质，不等于空槽。空间算法先明确主体，再生成站位和朝向；几何评分只是候选排序，最终自己逐图看。搜索失败的候选也保留供识图诊断，不拿通过门禁代替实际图片。

截图交接原生绘图 Skill；查询参考或上传调用平台 Skill。浏览器依赖见 [运行说明](local_runtime.md)，人读 [PDF](SKILL_MANUAL.pdf)。
