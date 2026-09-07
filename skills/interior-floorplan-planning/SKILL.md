---
name: interior-floorplan-planning
description: 将客户户型图、尺寸和需求整理为米制布局 JSON；规划墙门窗、功能区、家具锚点及动线，可用宿主原生绘图探索平面方案。不交付平面 HTML。
metadata: {version: "2.1.0", category: interior-design}
---
# 平面布局规划

输入原图、标注尺寸和用户意图；输出 `layout.json` 给 HTML 建模。按需生成原生平面方案图片，图片不是测量事实源。

读 [规划方法](playbook.md)，字段唯一来源是 [布局合同](../interior-html-modeling/data_contract.md)。命令入口 [scripts/run.py](scripts/run.py)：`handoff INPUT --out layout.json`、`observe INPUT --out observations.json`；显式按宿主墙生成家具锚点用 `anchor INPUT --id ID --wall-id WALL --offset 米 --gap 米 --out layout.json`。共享确定性引擎由 HTML Skill 维护，不复制另一套几何字段。

床默认床头靠真实墙；沙发按房间和阳台关系确定靠墙或开放放置；不是随便找最近墙。动线在布局生成前考虑，观察结果不能代替源规则。保留带问题草稿并修正源头，不凭格式通过宣称设计正确。

资产查询或平台交付调用 `idk-canvas-ingest-agent`。不得把平台 Key 放到布局、HTML 或报告。

人读 [PDF](SKILL_MANUAL.pdf)，详细执行见 [运行说明](local_runtime.md)。
