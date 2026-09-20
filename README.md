# Ubuntu design Skills · 2026.09.20

独立发布 `ubuntu-design-2026.09.20`，来源 Ubuntu 百亿设计工作流；同步 Ubuntu、Lecoo、Genmachine。旧分支及旧标签保持原样。本分支仅包含六项室内设计 Skill；单产品与 Blender 能力不属于此次发布。

| Skill | Version |
|---|---|
| interior-floorplan-planning | 3.5.0 |
| interior-html-modeling | 5.0.0 |
| interior-camera-capture | 3.3.0 |
| interior-space-rendering | 3.4.0 |
| booklet-production | 4.2.0 |
| idk-canvas-ingest-agent | 3.1.1 |

新增方法：图纸上下层投影识别、真实完成面对齐、柜体板件/分格/转角盲区、桌柜关系、台面实开孔、吊顶与封板语义、真实室内构图、已确认节点继承与方案说明。客户固定尺寸、审美和个人偏好留在各项目/用户记忆，不提升为通用默认。

HTML 5.0.0：共享参数化构造核、固定板厚重建、柜段生成、真实台面孔洞与水槽、桌下抽屉、柜体盲区与内缩踢脚、平台床/卡座、独立吊顶构件、完成面锚点与连排台面联动。参数编辑支持撤销/重做及完整 HTML 保存重开。

这些是制作方法与可配置参数，不增加设计强校验、审美门禁或审批流程。几何测试只用于本次软件维护，不作为客户设计交付门禁。

安装：把 `skills/` 的六个目录替换至设备唯一活动 Skill 根；保留该设备已有私有 `.runtime`，不要跨设备复制凭据。Python/Chrome/字体路径按各设备运行配置提供。各 Skill 的 `SKILL.md`、playbook、当前 PDF 为同一版本。`manifest.json` 和 `FILES.sha256` 用于发布文件溯源。

验证：参数化部件测试、已有 Python 测试、真实 Chrome 编辑与完整保存往返。原生效果图及私有平台网络业务不在本次软件发布测试范围。
