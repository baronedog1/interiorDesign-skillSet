# 小酷设计编排与杂志式方案册 说明书

版本：4.1.1

~~~yaml
---
name: booklet-production
description: 将同一室内设计方案的布局、空间图片、材料与用户产品整理成杂志式 HTML 和 PDF 方案册；用户只要图片时不调用。不负责重新建模或生成效果图。
metadata: {"version":"4.1.1","source_authority":"lecoo-windows-device","category":"interior-design"}
---
~~~

## 调用场景

### 完整设计及按目标交付

先生成准确户型，再用机位看空间；风格落入模型后刷新正式截图，渲染与交付各归对应 Skill。

输入：客户户型图、偏好与交付要求
输出：对应图片、模型或完整方案 PDF

#### 从客户户型，到对应的交付物
- a：客户原图 + 偏好 + 交付目标；先区分完整方案、图片或单一步骤任务。；已有同版可靠成果按需复用，不强制重跑。
  - SKILL.md：方案册调用边界
- b：规划 JSON → 代码生成整户型；规划：尺寸、拓扑、门窗、通路与家具锚点。；HTML：严格按代码生成；错在源头就改源头。；不把漂亮风格参考图当成客户户型。；随步骤记录开始、完成、耗时；代码与绘图等待分开。
  - playbook.md：接收上游事实，不另造布局
  - ../interior-html-modeling/playbook/timing.md：计时口径
  - ../interior-html-modeling/scripts/engine/python/timing.py：正式命令自动计时
- c：初始机位看布局 → 用户风格入模；先看真实空间关系，再按用户偏好应用 CMF。；平台资产按需获取，指定家具保持尺寸比例。；改风格不默认改户型或家具摆放。
- d：保存风格版 → 正式机位与截图；只改 CMF 可复用机位几何，但刷新同版截图。；改结构或家具包络，重新求解受影响视角。；旧截图不能配新模型。
- f：原生绘图：同机位、同结构；默认带完整活动家具与细节。；用户明确要求才使用白模／空白槽位。；精细化普通家具；指定资产不变形、不失真。
- q：交付目标是完整方案册？；是：编排 PDF；否：按指定格式交付。
  - SKILL.md：触发判断
- g：否：发送图片／HTML／JSON；用户要图片就发图片，不强塞 PDF。；实际发送成功才算交付。
- h：是：第六项 booklet-production；同版布局、风格、效果、材料组成方案册。；缺实际渲染只能标阶段方案。
  - playbook.md：杂志式内容编排
  - data_contract.md：brief 输入与来源
- i：发送完整方案 PDF；平台上传按需调用平台 Skill。；方案册不自动等于施工图、报价或采购承诺。；方案默认高清PDF＋讲解；记录原生结果与有效DPI。
- a → b
- b → c
- c → d
- d → f
- f → q
- q → g：否
- q → h：是
- h → i

### 制作有内容差异的设计杂志

每页按内容选择布局。宋体标题、清晰正文、大幅照片和细线页码形成统一气质，而不是统一框图。

输入：当前同版布局、图片、材料与文字
输出：离线 HTML、高清 PDF、发送版 PDF

#### 内容决定版式，而不是把每页套成同样的框
- a：同版资料 → 方案叙事；原图／布局、最终效果图、指定产品、CMF。；标清参考照片、模型截图和真实渲染。
  - data_contract.md：来源、shotId、状态
  - playbook.md：内容与叙事
  - playbook/example-brief.json：可编辑的封面与平面输入例子
- b：按内容选择页面；封面引入 → 平面说明 → 空间故事。；图组、材料与收束按实际需要插入。；无固定页数、无强制白模插图比例。
  - assets/magazine.css：七类响应式杂志版式
- c：中文宋体 + 清晰正文 + 大图；暖白纸感、低饱和点缀、细线页码。；空间图保持原比例，封面裁切须显式允许。；材料色板不冒充实物样板。
  - expected_outcome/expected_outcome.md：样册来源与适用边界
  - expected_outcome/demo.pdf：实际排版样例，不是客户渲染
- d：本机 Chrome 实际排版；图片内嵌，文字作为数据转义。；生成高清／发送两份 PDF 与离线 HTML。；字体、长文分页详见蓝色逻辑页。（详见 pagination）
  - scripts/run.py：document / picture / build
  - local_runtime.md：Windows Python 与 Chrome
- q：逐页看图，是否符合本次内容？；图片未变形，文字不溢出。；信息来源真实、版式服务于本页叙事。
- z：是：发送所需文件；不是只保存路径；检查实际发送回执。；客户要方案发 PDF，模板包另行提供。
- r：否：改对应源头，再排版；资料错改 brief；版式错改 CSS／分页逻辑。；不盖住错误、不缩到看不清、不伪造图片。
- a → b
- b → c
- c → d
- d → q
- q → z：是
- q → r：否
- r → d

## 完整文件地图
- MANIFEST.json：Windows 分支、版本与文件摘要
- SKILL.md：调用入口、范围与交付边界
- SKILL_MANUAL.pdf：编排、排版与分页算法说明书
- assets/magazine.css：七类页面的字体、图片、色板、分页与移动布局
- data_contract.md：方案册 JSON 与图片来源字段
- expected_outcome/demo.pdf：实际 Windows 生成的六页杂志排版演示
- expected_outcome/expected_outcome.md：视觉样册来源、参考维度与非客户成果边界
- local_runtime.md：Windows 运行环境和依赖
- manual/skill-flowchart.svg：完整设计编排总览
- manual/skill-manual.json：各场景与算法流程图的可维护源数据
- manual/skill-manual.md：说明书自然语言源
- playbook.md：杂志式编排、来源语义和源头修正
- playbook/example-brief.json：可编辑的封面与平面页输入示例，图片替换为当前项目
- scripts/run.py：本地生成、文字分页、PDF 双版本与回读
- scripts/scripts.md：标准调用与错误说明

## 具体逻辑解释

### 分页、图片与 PDF 回读

排版规则作用于页面，不改变空间和家具。技术检查与逐页识图共同定位源头，不能以报告替代看图。

#### 文字分页与独立 PDF 回读：真实算法
- a：读取本地资料并安全生成 HTML；转义标题、正文与图片说明；无效输入报真实技术错误。；透明资产先合成白底再转RGB；EXIF方向校正，原文件不改。
  - scripts/run.py：document / picture
  - data_contract.md：brief 的字段
- b：等待字体与图片加载 → 测量末段；按 A4 打印尺寸测量正文末段与页脚。；不是凭字数猜页数，也不把文字截掉。
  - scripts/run.py：build / PAGINATE
  - assets/magazine.css：正文、图框和页脚尺寸
- q：正文末段侵入页脚区域？；是：末段移到续页，再测量。；否：保持当前页，进入 PDF 输出。
- r：建立同标题续页，移动末段；不重复铺图，不缩字，不修改源图。；循环至段落放下；无法排版报技术原因。
  - scripts/run.py：PAGINATE
- p：打印两份 PDF → 独立引擎回读；PyMuPDF 按每页真实内容生成预览。；记录页数、尺寸、字体嵌入、RGB 与摘要。；方案默认高清PDF＋讲解；记录原生结果与有效DPI。
  - scripts/run.py：inspect_pdf
  - local_runtime.md：固定依赖
- v：回读／浏览器／视觉发现问题？；字体、溢出、图像比例与来源均需查看。；这些检查不移动家具、不改空间设计。
- f：是：定位资料／版式／运行环境；保留报告，修改最早源头后重建。；缺图说明缺口，可交付标注阶段的版本。
- z：否：保存与交付；manifest 保留来源摘要、观察与输出结果。；新输出目录保留前版，可追溯。
  - scripts/scripts.md：调用方法与技术错误
- a → b
- b → q
- q → r：是
- r → b
- q → p：否
- p → v
- v → f：是
- v → z：否
