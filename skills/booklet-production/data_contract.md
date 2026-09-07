# 输入合同

单个 UTF-8 JSON：`schema="interior.booklet/3"`；projectId、version、title、edition、status（阶段方案／完整方案／模板演示）；pages 数组。路径相对该 JSON 解析，仅本地 png/jpg/webp 图片；脚本不联网下载图片。最小可编辑结构见 [示例 brief](playbook/example-brief.json)，其中图片路径要换为当前项目真实文件。

每页：kind（cover/plan/story/full/gallery/materials/closing）、title、kicker、body（段落数组）、layoutReason、images（图对象数组）、swatches（可选 name/color）。图对象：path、caption、role（planning/render/reference/product/detail）、shotId（空间图）、source（作者／出处）、crop（默认 false；仅封面）、focus（可选 object-position，如 `50% 50%`）。需要对照时参照图和渲染图使用同一 shotId；不同机位作为 gallery 时各自准确标记。

纸张默认 A4 竖版；theme 可含 accent 六位 hex 色，品牌文字来自 brief，禁止自动写虚构客户／面积／联系方式。正文不会自动生成业务事实。没有输入图的 closing 或概念页可用文字；其它页面缺图时明确记录阶段缺项。

输出：booklet.html、booklet-sendable.html、booklet-highres.pdf、booklet-sendable.pdf、manifest.json（来源摘要、页数、尺寸、观察）、preview-highres/ 与 preview-sendable/、mobile-highres.png 与 mobile-sendable.png。重复运行请新 out 目录保留旧交付版本。所有输出只在来酷 C 盘，不入 Skill 安装目录。

空间图片新增 resultPath（相对 brief 的原生结果JSON）、schemeId（风格方案）、sceneKey。脚本核对结果与图片摘要及 shotId，并登记源图/内嵌分辨率和实际打印 DPI；低于150 DPI只是质量提示，不把它作为审美或交付门禁。默认交付 booklet-highres.pdf，发送版为补充。正式方案含选定全部机位图和自然语言讲解；不以文字PDF和散图ZIP代替。
