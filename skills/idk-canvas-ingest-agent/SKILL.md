---
name: idk-canvas-ingest-agent
description: 设计链访问百恩得资产库、绑定同一私有项目、下载选定资产并上传图片或完整 HTML 时使用；独占受管 Key、API 和真实回读，不负责生成或美学验收。
metadata: {version: "3.1.0", category: interior-design}
---
# 百恩得资产与私有项目交付

其他五项 Skill 需要找平台资产或推送成果时调用本入口，不复制 Key 和上传脚本。

先读 [平台方法](playbook.md) 和 [运行说明](local_runtime.md)。`python scripts/run.py profile`；`library [--library ID]`；`bind --binding FILE --project-id ID`；`download --library ID --asset-id ID --out FILE`；`publish FILE --binding FILE --kind preview3d_html|render_image|camera_shot --run-id ID --receipt FILE --apply`。

真实上传有对应用户授权才加 --apply，不带时仅预览。内部 Key 从 `.runtime/baiende-platform.env` 或显式 IDK_ENV_FILE 读取，不能进 Git/PDF/HTML/回执。没有 Key 或服务失败如实报错，不改用匿名上传绕过。

本版实现资产库读取/下载及私有项目上传，不提供社区公开发布、付费生成、删除或批量覆盖；需要公开发布另行明确需求与授权，不能把私有上传当公开。

人读 [PDF](SKILL_MANUAL.pdf)。

每一步必须记录开始、完成、耗时及状态，遵循[统一时间合同](../interior-html-modeling/playbook/timing.md)；正式命令自动记录，读图、识图、原生调用与交付等待随执行登记，不事后补时间。
