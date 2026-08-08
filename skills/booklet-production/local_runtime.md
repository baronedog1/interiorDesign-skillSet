# Local Runtime

设备路径以 `CHROME_BIN`、`XDG_RUNTIME_DIR` 和 runtime inventory 为准；任何 `/home/agentops/...` 都只是 Ubuntu 示例。管理员预装依赖，任务只做 preflight。

本 skill 的本地 runtime 包括 PDF 质检和 mobile-safe 转换。

- Python：`scripts/pdf_quality_check.py`、`scripts/make_sendable_pdf.py`。
- `__pycache__`、临时 PDF 预览、导出缓存不属于正式 skill 文件图谱。

平台项目入库或社区 HTML snapshot 交给 `/home/agentops/.codex/skills/idk-canvas-ingest-agent`；本 Skill 只准备 accepted 预览图或 snapshot spec。
