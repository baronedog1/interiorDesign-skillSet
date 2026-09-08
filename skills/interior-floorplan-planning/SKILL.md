---
name: interior-floorplan-planning
description: 通过分轮需求访谈了解居住、功能、布局和风格偏好，将客户户型图与确认需求整理为米制布局JSON；规划墙门窗、家具锚点和动线，可用原生绘图探索方案。不交付平面HTML。
metadata: {version: "3.2.1", category: interior-design}
---
# 平面布局规划

输入原图、标注尺寸和用户意图；输出 `layout.json` 给 HTML 建模。按需生成原生平面方案图片，图片不是测量事实源。

空白/毛坯户型图、看不出偏好，或现有资料不能确定居住与布局意图时，先按[需求访谈](playbook/requirements-interview.md)分轮询问。先读已有对话，不重复索要答案；有家具的图也不等于用户认可其布局。把确认、待定、推测与用户授权自由发挥分开记录到 `requirements.json`；有实质冲突先讲清取舍，再规划受影响区域。用户暂未回复时可继续读结构和校准，不自行把假设写成已确认需求。

读 [规划方法](playbook.md)，字段唯一来源是 [布局合同](../interior-html-modeling/data_contract.md)。命令入口 [scripts/run.py](scripts/run.py)：`handoff INPUT --out layout.json`、`observe INPUT --out observations.json`；显式按宿主墙生成家具锚点用 `anchor INPUT --id ID --wall-id WALL --offset 米 --gap 米 --out layout.json`。共享确定性引擎由 HTML Skill 维护，不复制另一套几何字段。

访谈后 `handoff INPUT --requirements requirements.json --out layout.json` 同交付 `layout.requirements.json`；后续命令会发现输入布局旁的同名需求侧车。脚本只保留/核对交接数据，不替 Agent 提问、不按问卷填满率决定是否能设计。HTML建模先读该需求文件，把约束落实到房间、家具锚点与CMF；下游不另猜一套偏好。

床默认床头靠真实墙；沙发按房间和阳台关系确定靠墙或开放放置；不是随便找最近墙。动线在布局生成前考虑，观察结果不能代替源规则。保留带问题草稿并修正源头，不凭格式通过宣称设计正确。

资产查询或平台交付调用 `idk-canvas-ingest-agent`。不得把平台 Key 放到布局、HTML 或报告。

人读 [PDF](SKILL_MANUAL.pdf)，详细执行见 [运行说明](local_runtime.md)。

每一步必须记录开始、完成、耗时及状态，遵循[统一时间合同](../interior-html-modeling/playbook/timing.md)；正式命令自动记录，读图、识图、原生调用与交付等待随执行登记，不事后补时间。

规划大件时先建立“需求→功能→组件→真实位置”的理由；开放功能区不自动生成书架/屏风隔断。详见playbook的功能选型方法，交接前看全屋顶视和开放区关系。
