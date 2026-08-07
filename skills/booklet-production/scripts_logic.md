# Scripts Logic

## `scripts/validate_booklet_plan.py`

在排版前校验页面顺序、用户资产登记、空间页白模小图和版式多样性。

硬门槛：

- 正文不得包含四象限或描线过程图；
- 空间页默认包含与效果图相同 `shotId` 的白模小图，只有用户明确关闭时可省略；
- 白模小图占页面 `16%–28%`，不得与效果图等权；
- 先讲规划，再整理用户资产，随后按空间展示；
- 连续页面不得全部使用同一版式。

## `scripts/pdf_quality_check.py`

对导出的图册 PDF 检查页数、页面尺寸、加密、文件大小、图片颜色空间，并抽取关键页预览，输出 Markdown 与 JSON 报告。

## `scripts/make_sendable_pdf.py`

需要飞书/移动端版本时调用 Ghostscript 生成 RGB sendable 副本，再运行 PDF QA。高清原版不得被覆盖。

## 平台交接

本 Skill 不含平台脚本。封面/页面预览图交给
`idk-canvas-ingest-agent/publish_project_artifact.mjs`；社区 publication spec
交给其唯一入口 `publish_community_post.mjs`。
