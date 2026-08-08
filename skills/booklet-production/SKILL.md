---
name: booklet-production
description: 当用户说“做方案册/设计说明书”“整理成 PDF”“做设计图册、作品集、汇报材料或社区图文”时使用；只读取当前 confirmed-version 中已验收的干净平面规划、用户产品资产、同 shotId 白模机位小图和最终效果图，先讲规划与资产，再按空间编排客户可读的 HTML/CSS 和 PDF，执行全页、字体、图片、移动端 RGB 与 sendable QA。技术描线过程默认不入册，户型/渲染不在本 Skill 重做；平台项目上传和社区公开统一交给 idk-canvas-ingest-agent。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"ubuntu-01-device-source","version":"3.3.0","booklet_schema":"interior.design-booklet.v2"}
---

# 室内设计方案册

## 使用前准备

- 管理员预装 Python 3、可用的非 Snap Chrome/Chromium、Poppler（`pdfinfo`、`pdfimages`、`pdftoppm`）、Ghostscript 和中文字体；需要结构修复或压缩时再启用 qpdf / ImageMagick。
- 先读取 [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) 与 [local_runtime.md](local_runtime.md)，确认浏览器、字体、PDF 工具和当前任务输出目录均可用。
- 必须已有同一确认版本的规划图、白模机位、渲染图与来源清单；缺任何必需输入时在排版前标记 `blocked`，不得运行中安装软件或从历史目录猜资料。

## 唯一职责

- 输入：当前确认版本的规划图、用户资产、正式白模机位、最终渲染、空间说明和来源清单。
- 输出：结构化页面计划、HTML/CSS 权威排版、高清/可发送 PDF、预览总览和可选平台链接。
- 不处理：四象限描线、墙窗建模、产品建模、机位计算或效果图生成。
- 对客户展示设计结果和依据，不展示内部纠错过程。

## 简单意图入口

- “把结果做成 PDF / 方案册 / 图册 / 汇报材料”：使用本 Skill。
- “做粉笔/涂鸦风格的方案说明页”：使用本 Skill；以 accepted 干净规划图为不可变
  背景，只增加圈注、箭头、编号和说明，禁止让图像模型重画户型。
- 如果用户同时要求“从户型图做到方案册”，先由渲染 Skill 的 `direct-output` 完成
  规划、模型、机位和效果图，再由本 Skill 编排；不在图册阶段补做上游事实。
- “上传到平台”不是排版意图，交给 `idk-canvas-ingest-agent`；如需平台社区图文，
  本 Skill 只准备已验收的 `baiende.community-publication-spec.v1` 内容字段。

## 高频数据入口

| 需要的信息 | 入口 |
|---|---|
| 图册 brief、资产登记和页面字段 | [data_contract.md](data_contract.md) |
| 从资产盘点到 PDF QA 的完整流程 | [playbook.md](playbook.md) |
| 页面计划和 PDF 脚本 | [scripts_logic.md](scripts_logic.md) |
| 版式规则 | [references/layout-rules.md](references/layout-rules.md) |
| 本地 PDF 和浏览器依赖 | [local_runtime.md](local_runtime.md) |
| 设备、字体和凭据边界 | [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) |

## 正式内容顺序

1. 封面与项目摘要。
2. **平面布局规划讲解**：使用干净规划图和空间/动线/功能说明。
3. **用户资产**：产品照片、品牌/SKU、尺寸、材质偏好和本案使用位置。
4. **分空间内容**：每个空间按“最终效果图 + 设计说明 + 可选产品细节 + 默认白模机位小图”组织。
5. 材质、灯光、收纳或重点细节。
6. 总结与交付信息。

第一阶段的源图描线、四象限、红墙蓝窗框架和校验叠加图属于中间证据，默认禁止进入客户 PDF。只有用户明确要求审计附件时，才放在独立附录。

粉笔/涂鸦说明页是 presentation layer：必须使用 accepted 干净规划图本身作为背景，
通过 HTML/CSS/SVG 叠加说明；不能生成一张“看起来相似”的新户型图。这样保留说明
能力，但墙窗、房间和家具事实仍只有平面 Skill 一份。

## 白模机位小图

- 默认 `enabled=true`，用户明确要求不带时关闭。
- 作为“空间原图/机位依据”小图，不与效果图等大。
- 推荐放在右上角、右下角或侧栏，占页面宽度 16%–28%。
- 必须与当前效果图使用同一 `shotId`、裁切和空间；不能放相似但不同机位。
- 小图保留清晰轮廓，不带编辑侧栏、轴、标签或网格。

## 页面多样性

- 超过 8 页至少使用 4 种版式；同一版式不得连续超过 2 页。
- 允许：满版主图、右上白模 inset、左图右文、左文右图、主图加细节条、双图对照、产品资产板、材料节点页。
- 页面变化服务内容，不随机换版。重点空间给大图，次要空间用紧凑组合，产品资产页强调比例和来源。
- 不使用卡片堆叠、重复粗边框、装饰性渐变或一页塞满制作说明。

## 来源与版本门

1. 只读取项目 `confirmed-version/manifest.json` 中 current 且 QA passed 的资产。
2. 每张效果图绑定 `renderId/shotId/sourceImage/sourceSceneMap`。
3. 每个白模 inset 绑定同一 `shotId`。
4. 每个用户产品图绑定第五个 Skill 的 `productId/customPackageId`。
5. rejected、retake、旧版本和中间过程图不得入册。

## 工作流

1. 建 `booklet-brief.json`，确认受众、比例、语言、页数、交付形式和是否显示白模 inset。
2. 建 `asset-register.json`，按 planning、user-product、white-model-shot、final-render、detail 分类。
3. 建 `page-specs.json`，严格按正式内容顺序排页，并为每页写版式理由。
4. 先完成 HTML/CSS 权威排版，再用浏览器逐页截图检查。
5. 导出 PDF 后运行 `pdf_quality_check.py`；超过飞书阈值时生成 sendable 版本。
6. 用户要求写入平台项目时，将封面或页面预览图以 `booklet_preview` 交给 `idk-canvas-ingest-agent`；PDF 仍按飞书/云盘交付。
7. 用户要求社区在线阅读时，把 `baiende.community-publication-spec.v1` 交给同一
   平台 Skill；公开发布必须明确确认。

## 硬门槛

- PDF 前部出现四象限或描线过程而用户未要求：失败。
- 缺少干净平面规划图或规划讲解：失败。
- 用户资产未单独登记，或产品图与空间使用位置不明：失败。
- 空间效果图有正式 white-model shot 却未放 inset，且用户没有明确关闭：失败。
- inset 与效果图 `shotId` 不一致：失败。
- 全册空间页使用同一版式：失败。
- 旧图、rejected 图或未绑定来源图进入正式册：失败。
- PDF 未做全页预览、字体、裁切、色彩空间和移动端检查：失败。
- 本 Skill 读取平台凭据或直接调用平台 API：失败。

## 平台交接

- 项目资产只上传封面或页面预览图，`assetKind=booklet_preview`，默认目录 `booklet`。
- PDF、页面计划、资产登记和 QA 报告不作为项目媒体上传。
- 社区 HTML snapshot 由 `idk-canvas-ingest-agent` 的唯一
  `publish_community_post.mjs` 执行；预览不公开，真实公开必须再次确认。

## 维护

- 唯一权威源：Ubuntu `/home/agentops/.codex/skills/booklet-production`。
- 两个设计师 Agent 共用同一安装内容。
- GCP Manager 只登记治理摘要，不保留第二份源码。
- `.env.local`、`__pycache__`、任务图片和历史图册不得进入 Skill 正式文件图谱。
