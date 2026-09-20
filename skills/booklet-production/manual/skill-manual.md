# 设计图文方案册

版本：4.2.0

用户给当前方案图文资料 → 确定设计故事与交付范围 → 组织同版主图和节点说明 → 通过正式版式生成图文页面 → 制作高清文档与可读预览 → 用户获得图文方案册


## SKILL.md

---
name: booklet-production
description: 将同一室内设计方案的布局、空间图片、材料与用户产品整理成杂志式 HTML 和 PDF 方案册；用户只要图片时不调用。不负责重新建模或生成效果图。
metadata: {"version":"4.1.1","source_authority":"lecoo-windows-device","category":"interior-design"}
---

# 室内设计方案册

用户要求完整方案、设计图册或 PDF 时调用。读取当前项目资料，按设计故事组织页面，运行 `scripts/run.py brief.json --out <任务目录>`，得到高清 PDF、发送版 PDF、可离线 HTML 和逐页预览。输入字段见 [数据合同](data_contract.md)，方法与版式选择见 [制作方法](playbook.md)。

高频数据入口：当前 `C:\AgentWorkspaces\InteriorDesign\projects\<projectId>` 中的同版布局 JSON、模型、机位、实际渲染图片及回执；临时项目则读取用户当前隔离目录。按 projectId、version、shotId 定位，不取其它项目的漂亮图片填空。客户资料缺失先回查当前任务产物；仍缺则说明缺口并标阶段方案。首次使用先按 [运行环境](local_runtime.md) 确认 Python、Chrome 和字体可用。

先完成户型规划 → HTML 建模 → 机位 → 用户风格 CMF／必要选型 → 更新后的同机位截图 → 原生绘图，再入册；已有同版成果按需复用，不重复执行全链。完整方案不代表施工图、工程预算或工程可实施承诺。

普通客户册用最终效果图讲空间，布局说明使用真实布局图。截图不得冒充原生渲染；缺效果图可以明确交付“阶段方案”，不伪造完成。白模不是必需输入：默认不加机位小图；用户需要对照时可加入同 shotId 的完整模型或显式空槽参照。

保留真实图的结构、比例和用户资产身份，不为了版面拉伸图片；平面图完整呈现。主图、图文、双图、材料页按内容选择，不固定每空间一套版式或固定页数。客户信息与素材只存在来酷项目目录；本 Skill 不读 API Key。需要平台素材或上传时调用 `idk-canvas-ingest-agent`，本机 PDF 不自动公开。

运行环境见 [local_runtime.md](local_runtime.md)，脚本说明见 [scripts/scripts.md](scripts/scripts.md)，[流程说明书](SKILL_MANUAL.pdf)，[视觉样册及适用边界](expected_outcome/expected_outcome.md)。

每一步必须记录开始、完成、耗时及状态，遵循[统一时间合同](../interior-html-modeling/playbook/timing.md)；正式命令自动记录，读图、识图、原生调用与交付等待随执行登记，不事后补时间。

用户说“交付方案”但未明确格式，默认交付带文字说明的 booklet-highres.pdf；只有明确仅要图片才省略 PDF。每张 render 图片关联 resultPath、shotId、schemeId；同一空间多机位一起讲清布局与材料，源图低分辨率不能靠放大宣称高清。


## 当前设计方法

先按任务读取 [当前设计事实与图文表达](playbook/design-facts.md)。通用方法与用户参数分开，选择及覆盖见 [规则归属](../interior-html-modeling/playbook/rule-selection.md)。这些是生成方法，不新增强校验、门禁或审批。


## playbook.md

# 杂志式方案册制作方法

## 资料和叙事

从当前项目明确版本的 layout.json、scene.json、cameras.json、最终图片和用户资产取材。记录 projectId、version、每张图的角色、来源、shotId；不要扫描历史目录猜最新版。原生图和参照图成对展示时必须同 shotId；普通情绪参考明确标“风格参考”，不能冒充本户型效果。

完整设计的合理叙事：主题封面 → 居住需求与真实布局 → 风格／用户资产 → 主要空间和次要空间 → 材料及细节 → 交付说明。根据实际资料取舍，不空造资产页、装饰图、面积、品牌或预算。用户只要图片直接交付图片，不调用本 Skill。已有渲染只做图册时不重建上游。

## 版式不是固定业务模板

承接 Ubuntu 3.3 的中文优先、大主图、错落图文和真实素材思路，删除强制 confirmed-version、必带白模 inset、固定版式数量和旧平台入口。

模板提供页面构件，Agent 按内容选择：cover 聚焦主题；plan 完整展示布局和关键说明；story 以图文叙述单空间；full 保留大图视觉；gallery 比较两个空间或两个同源机位；materials 展示色板和真实材料／产品；closing 写实际交付。不是每册每种都必须使用。空间主图默认 contain，封面只有明确 crop=true 才允许装饰性裁切，不改变长宽比；不能截掉关键门窗后声称完整空间。

视觉语言：象牙纸底、炭黑文字、克制橄榄色或用户风格强调色；中文宋体大标题配黑体正文，英文只作小型编辑标签，细分隔线、页码和舒展页边距。图片是主角，不堆圆角卡片、阴影、渐变和大段制作过程。Do：真实主图、短而具体的设计说明、统一基线；Don't：拉伸照片、伪造细节、连续机械换标题。

## 生成与看图

先为页面写 layoutReason；脚本安全读取 JSON 和本地栅格图，校正EXIF方向，将透明区域合成到白色画布后再以RGB内嵌，避免产品透明底变黑；原始资产不改写。随后生成 HTML/CSS，Chrome 加载全部图和字体后出 PDF。网页长正文按实际可用高度续页，不能缩成小字或截断。查看所有页面：主图是否足够大、关键结构是否完整、图文比例是否合适、文字是否溢出、中文是否缺字、版面节奏是否服务故事。问题回到 page kind、内容或 CSS 源再生成，不在成品 PDF 上盖补丁。

高清版保留；发送版从同份文字和图片生成，降低图片像素和 JPEG 质量而不改页序、文字或几何。两份 PDF 由 PyMuPDF 独立重开并生成全部页预览、字体和图像色彩清单。质量观察记录具体页，不把版式数量当门禁；损坏图片、无实际文件等真实技术故障如实指出。

## 交付

发用户指定的 PDF 和必要图片。报告实际页数、字节数、阶段／完整状态；附来源但不把内部路径、Key、测试日志写入客户册。上传平台只通过平台 Skill；PDF 走飞书文件／云盘，平台媒体仅传其支持的封面／页面图片。模板演示使用授权公开图并标“非客户方案”，不列为正式生成效果。


## playbook/design-facts.md

# 方案册沿用当前设计事实

从当前revision的模型、正式机位、效果图和需求侧车组织图文。按空间主图及必要节点图讲清柜桌、柜顶、厨房、阳台等设计选择；局部图不冒充全貌。通用方法无需整套抄入客户方案册，只解释本案适用关系。

区分图纸标注、用户确认、概念估算、未选设备和实际完成内容。尺寸图里的模型值不是复尺生产值；说明书里的规则已记录不代表旧项目已修改。用户只要模型或单图不强制生成方案册；无需新增设计门禁或强校验。


## data_contract.md

# 输入合同

单个 UTF-8 JSON：`schema="interior.booklet/3"`；projectId、version、title、edition、status（阶段方案／完整方案／模板演示）；pages 数组。路径相对该 JSON 解析，仅本地 png/jpg/webp 图片；脚本不联网下载图片。最小可编辑结构见 [示例 brief](playbook/example-brief.json)，其中图片路径要换为当前项目真实文件。

每页：kind（cover/plan/story/full/gallery/materials/closing）、title、kicker、body（段落数组）、layoutReason、images（图对象数组）、swatches（可选 name/color）。图对象：path、caption、role（planning/render/reference/product/detail）、shotId（空间图）、source（作者／出处）、crop（默认 false；仅封面）、focus（可选 object-position，如 `50% 50%`）。需要对照时参照图和渲染图使用同一 shotId；不同机位作为 gallery 时各自准确标记。

纸张默认 A4 竖版；theme 可含 accent 六位 hex 色，品牌文字来自 brief，禁止自动写虚构客户／面积／联系方式。正文不会自动生成业务事实。没有输入图的 closing 或概念页可用文字；其它页面缺图时明确记录阶段缺项。

输出：booklet.html、booklet-sendable.html、booklet-highres.pdf、booklet-sendable.pdf、manifest.json（来源摘要、页数、尺寸、观察）、preview-highres/ 与 preview-sendable/、mobile-highres.png 与 mobile-sendable.png。重复运行请新 out 目录保留旧交付版本。所有输出只在来酷 C 盘，不入 Skill 安装目录。

空间图片新增 resultPath（相对 brief 的原生结果JSON）、schemeId（风格方案）、sceneKey。脚本核对结果与图片摘要及 shotId，并登记源图/内嵌分辨率和实际打印 DPI；低于150 DPI只是质量提示，不把它作为审美或交付门禁。默认交付 booklet-highres.pdf，发送版为补充。正式方案含选定全部机位图和自然语言讲解；不以文字PDF和散图ZIP代替。


## local_runtime.md

# 设备外置运行配置

本包在 Ubuntu、Windows 来酷和 Genmachine 使用同一份业务代码。Python 3.10+、Node、Chrome/Edge、中文字体及依赖由本机设计 runtime 配置提供；优先用设备登记的 interior-python 包装入口。普通任务不临时安装软件。所有输入和交付保存在当前设备当前工作区。

HTML 和截图共享 interior-html-modeling/scripts/engine。纯 HTML 离线打开不需要 Python；编译依赖 jsonschema、shapely、numpy，截图使用 Playwright 和 INTERIOR_CHROMIUM 指定的浏览器。资源盒由本机包装器沿用，任务结束只关闭本次浏览器。依赖列表见正式 scripts 中的 requirements 文件。

平台凭据通过设备既有 IDK_ENV_FILE 或私有 .runtime 链接提供，分发包不包含凭据；不得跨设备复制登录态。原生绘图使用当前宿主实际提供的绘图工具，准备文件不等于生成图片。

方案册使用 scripts/run.py 及 assets/magazine.css 正式版式，按本机运行说明提供 Playwright、Pillow 与中文字体；具体入口见SKILL.md。
