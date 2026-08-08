# Environment Contract

## 多设备运行规则

- 下文 Ubuntu 路径只是已验收示例，不是唯一入口。其它设备通过 `CHROME_BIN`、`XDG_RUNTIME_DIR` 和设备 runtime inventory 解析本机浏览器与可写目录。
- 浏览器、PDF 工具和字体必须由管理员预装；任务只做 preflight，不执行 apt/npm/pip 下载。
- 只有目标执行账号真实完成 HTML→PDF、逐页栅格与字体/颜色检查后才能登记 `ready`；缺浏览器时为 `blocked`，缺可选压缩工具时为 `degraded`。

## 运行环境

- 主设备：`ubuntu-01-codex`
- Skill 根目录：`/home/agentops/.codex/skills/booklet-production`
- 建议工作区：`/home/agentops/agent-runtime/workspaces/interior-design` 或任务专属目录

## 必需工具

- `python3`：运行本 skill 内 `scripts/`。
- `pdfinfo`：检查 PDF 元数据。
- `pdfimages`：检查图片颜色空间。
- `pdftoppm`：抽页预览。
- 浏览器或 PDF 导出工具：根据任务项目选择。

## 可选能力

- Codex 原生绘图：生成细节图、封面图或补充视觉页。
- Ghostscript `gs`：当需要生成 sRGB/DeviceRGB mobile-safe sendable PDF 时，由 `scripts/make_sendable_pdf.py` 调用。
- ImageMagick / qpdf：只有在具体任务需要压缩、抽图或结构修复时使用，使用前确认命令和风险。

## 安全边界

- 不读取 secret。
- 不把未授权客户素材加入公开模板库。
- 不伪造真实品牌、获奖、署名或客户信息。
- 不把高分辨率客户资料作为飞书附件外发，除非用户明确授权。

## 验收边界

- `SKILL.md` 和文档结构合规。
- PDF 交付必须运行 `scripts/pdf_quality_check.py`，保留 `pdf-qa-report.md`、`pdf-qa-report.json` 和至少关键页预览检查记录。
- 移动端/飞书发送版如果由脚本转换，必须保留高清原版、sendable 版和 `qa-sendable/` 报告。
- 飞书发送版需说明页数、大小和是否 mobile-safe。

## 平台依赖

- 可选项目入库和社区 HTML snapshot 依赖已安装的 `idk-canvas-ingest-agent`。
- 本 Skill 不读取平台 secret，不保存项目 API helper。
