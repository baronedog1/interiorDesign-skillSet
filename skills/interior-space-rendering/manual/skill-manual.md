# 原生绘图 · 粗模定位，参考图锁款 说明书

版本：3.2.1

~~~yaml
---
name: interior-space-rendering
description: 以HTML粗模锁定结构、机位和家具位置尺度，按产品参考图或精细定样锁款，通过原生绘图重建精细家具与真实光影；不锁粗模造型，不把截图当最终效果图。
metadata: {version: "3.2.1", category: interior-design}
---
~~~

## 调用场景

### 粗模定位 → 参考图片锁款 → 真实光影

HTML不必先变高精模；建筑与位置依据粗模，款式依据精细参考图，二维生成不回写3D网格。

输入：同版HTML粗模截图、场景/机位/槽位、精细家具参考图片及用户意图
输出：原生图片、调用回执、逐图问题

#### 粗模定位 → 参考图片锁款 → 真实光影
- a：同版模型图、JSON、机位与指定资产；先看图和用户要求；不把配置当工具可用证明
  - scripts/run.py：ai-request/native-prepare/native-result 入口
- q：用户明确要求白模／空白槽位？；默认 furnished；不因效果差自动切模式（详见 modes）
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- full：默认：完整粗模截图，只管布局；不照抄粗模造型和照明；按精细参考重建家具（详见 consistency）
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
  - ../interior-html-modeling/playbook/timing.md：计时口径
  - ../interior-html-modeling/scripts/engine/python/timing.py：正式命令自动计时
- empty：是：建筑截图＋原 JSON 槽位；家具/柜体暂隐；位置、尺寸、朝向仍固定
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- prompt：粗模定位＋精细参考图锁款；产品图优先；精细定样其次；不锁粗模身份（详见 assets）
  - ../interior-html-modeling/scripts/engine/python/render.py：两种模式、槽位、产品尺寸进入 prompt
- call：真实宿主调用 → 看图 → 交付；没有工具或图片就如实报告；不拿截图冒充（详见 native）
  - ../interior-html-modeling/scripts/engine/python/native_image.py：工具准备、实际调用回执和结果绑定
- a → q：模式
- q → empty：是
- q → full：否：默认
- full → prompt：完整图
- empty → prompt：空槽图与 JSON
- prompt → call：附图调用

### 建筑不变，设计内容不再锁死

风格图提供设计语言，产品图提供款式，当前机位图才提供结构。

输入：当前源事实与用户需求
输出：可追溯的设计决定及实际交接

#### 建筑不变，设计内容不再锁死
- style：实际查看平台风格模板与产品图；提炼墙/顶/灯/窗、材料、陈设密度；按本空间用途组织，不只提取木色
  - playbook.md：设计意图与参考职责
- brief：design-brief.json → --design-brief；common：全屋共用；spaces：按roomId差异；styleReferences：真实path、assetId及说明；实际图片加入job，不只写风格名称
  - ../interior-html-modeling/scripts/engine/python/render.py：ai_request合并意图与真实附图
- shell：不可变事实；建筑壳与洞口位置尺寸、机位；主要家具功能、位置与通行关系；产品身份来自绑定参考图
  - ../interior-html-modeling/data_contract.md：壳体与设计提案的边界
- design：可设计内容；原层高内天花饰面、灯具与光影；洞口内门窗框扇/五金、帘、玻璃；挂画、器物、绿植及意向窗外景观
  - ../interior-html-modeling/scripts/engine/python/native_image.py：结构图/定样/产品/风格图完整传入
- review：是否改变了不可变事实？；改墙/开口/主布局：回对应源头；新增合理陈设不是结构错误
  - playbook.md：分开审查事实与设计完成度
- yes：是：修源头；保留实际图与问题
- no：否：审视设计品质；看光影、材质、构图与一致性
- style → brief
- style → shell
- brief → design
- shell → review
- design → review
- review → yes：是
- review → no：否

## 完整文件地图
- MANIFEST.json：发布版本与完整文件清单
- SKILL.md：调用范围、输入输出与关键规则
- SKILL_MANUAL.pdf：面向人的算法说明书
- local_runtime.md：原生工具运行与权限边界
- manual/skill-flowchart.svg：同源说明书内容与图形
- manual/skill-manual.json：同源说明书内容与图形
- manual/skill-manual.md：同源说明书内容与图形
- playbook.md：两模式、锁结构机位、家具细化与资产不变形
- scripts/run.py：ai-request/native-prepare/native-result 入口

## 具体逻辑解释

### 两种参照模式

按实际输入、计算、分支和文件消费者展开。

#### 两模式的源数据：显示可变，布局和机位不变
- source：保存原布局与相机；placements：id/roomId/position/size/rotationY；size=[宽,高,深]米；不删除 Ubuntu 原数据
  - ../interior-html-modeling/scripts/engine/python/render.py：load_scene、模式和同版校验
  - ../interior-html-modeling/scripts/engine/schemas/layout.schema.json：原始布局结构
  - ../interior-html-modeling/data_contract.md：两模式与槽位数据合同
- default：已在主图明确选择空槽模式；仅用户明确要求：empty-slots + 请求记录；固定相机，保存材质和每个实例的可见性
  - ../interior-camera-capture/scripts/run.py：捕获参数入口
  - ../interior-html-modeling/scripts/engine/runtime/app.js：captureFrame 保存当前状态
- explicit：finally：恢复捕获前场景；成功或异常都恢复材质、可见性和机位；显示暂变；JSON、家具尺寸和布局不改
  - ../interior-html-modeling/scripts/engine/runtime/app.js：finally 恢复原场景状态
- empty：空槽帧：仅隐藏家具和柜体实例；冻结机位 → 保存可见性 → 隐藏 placements；绘制 PNG → 记录全部隐藏ID → finally 恢复；建筑不删；JSON 槽位列表仍交给生成工具
  - ../interior-camera-capture/scripts/run.py：--reference-mode/--white-model-requested
  - ../interior-html-modeling/scripts/engine/runtime/app.js：临时隐藏/恢复及返回模式
  - ../interior-html-modeling/scripts/engine/python/render.py：截图摘要、hiddenPlacementIds 和请求槽位
- out：交付给提示词的是明确模式、同版图片和完整槽位；默认不带空槽开关；空槽请求与普通截图不匹配则重拍同版参照
  - ../interior-html-modeling/scripts/engine/python/common.py：文件摘要与原子保存
  - ../interior-html-modeling/scripts/engine/python/cli.py：请求参数显式选择
- source → default：原数据不变
- default → empty：临时显示层
- empty → explicit：捕获后或异常
- explicit → out：恢复后保留真实记录

### 谁决定家具款式与尺寸

粗模不拥有精细款式解释权；产品图优先，定样只管已出现的家具。

#### 款式来源：参考图锁款，不锁粗模
- source：当前粗模与参考图片；粗模：建筑/机位/位置/约略尺度；参考图片：精细产品的造型与比例
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
  - playbook.md：按参考图锁款、重建光影、尺寸与质量处理
- product：该家具绑定了精细产品图？；--products：placementId/path；真实尺寸可未知，不要求品牌SKU
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
- locked：是：按图锁定该款家具；保留参考图款式、部件、比例与CMF；丢弃粗模不同的扶手、底座和软包；产品图不改变房间、镜头与摆放
  - playbook.md：按参考图锁款、重建光影、尺寸与质量处理
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
- anchor：已有可见该家具的精细定样？；同系列/同策略，参考身份真实；不能从旧粗模图继承款式
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
  - playbook.md：按参考图锁款、重建光影、尺寸与质量处理
- reuse：是：沿用精细定样款式；当前粗模仍锁建筑与机位；按新视角重算反射、阴影
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
  - ../interior-html-modeling/scripts/engine/python/native_image.py：真实附图顺序、原生调用与回收计时
- concept：否：获取参考或建立概念首图；按需求选精细参考，平台取图走平台Skill；无参考时原生设计可信精细家具；明确概念选型，不假称已锁用户产品
  - playbook.md：按参考图锁款、重建光影、尺寸与质量处理
  - ../idk-canvas-ingest-agent/SKILL.md：按需获取平台家具图片
- out：按对应位置与合理大小放入；重新计算真实光影；尺寸不符回选型/布局，不拉伸产品；不新增结构；首张定样后再扩展同空间，不复制粗模廉价几何
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
- source → product
- product → locked：是
- product → anchor：否
- anchor → reuse：是
- anchor → concept：否
- locked → out：具体产品优先
- reuse → out
- concept → out

#### 图片与尺寸交接：技术条件不等于审美门禁
- input：逐条读取产品参考绑定；placementId、path、sizeMetres?；size=[宽,高,深]米；未知为null
  - ../interior-html-modeling/scripts/engine/python/cli.py：--products读取JSON列表
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
- binding：实例存在且图片文件可读？；placementId必须来自原布局；文件不能缺失
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
- same：是否拿同内容粗模冒充产品图？；图片摘要与粗模截图相同？
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
  - ../interior-html-modeling/scripts/engine/python/common.py：文件SHA与读取
- err：报告具体输入错误，修正该参考后重新准备；不伪造产品身份；不改客户布局绕过问题
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
- size：已给尺寸是否合法？；null合法；已给则为3个正有限数值；未知不代填粗模数值
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
- emit：真实绑定进入prompt与原生附图；完整绑定表跨机位复用；同图按职责+SHA合并；一张产品图可对应多个placementIds；顺序：粗模→精细定样→产品→风格；不虚构5张上限
  - ../interior-html-modeling/scripts/engine/python/render.py：粗模/参考图片分权、尺寸来源、附图编号与系列策略
  - ../interior-html-modeling/scripts/engine/python/native_image.py：真实附图顺序、原生调用与回收计时
  - ../interior-html-modeling/data_contract.md：参考角色、sourceFrame/outputFrame合同
- input → binding
- binding → same：是
- binding → err：否
- same → err：是：输入误绑
- same → size：否
- size → err：否
- size → emit：是

### 真实原生调用与识图

按实际输入、计算、分支和文件消费者展开。

#### 真实出图链：准备不是调用，提示词不是保真证明
- a：校对参照和实际工具清单；sceneKey/cameraDigest/图像SHA同版；产品图摘要和尺寸来源随请求携带
  - scripts/run.py：ai-request/native-prepare/native-result 入口
  - ../interior-html-modeling/scripts/engine/python/render.py：ai_request 生成完整实际 prompt
  - ../interior-html-modeling/scripts/engine/python/cli.py：三个命令与参数分派
- q：当前宿主有原生绘图工具？；实际 toolName；无工具不能假写 available
  - ../interior-html-modeling/scripts/engine/python/native_image.py：prepare 只生成 ready-for-host-call/unavailable
  - local_runtime.md：原生工具运行与权限边界
- missing：否：报告能力缺失；不能换成 WebGL 或付费 API 冒充
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- call：是：附完整/空槽图及产品图调用；宿主原生工具实际返回后保存图片；不伪造 providerRequestId 或调用成功
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际 invocation 与 jobDigest/outputSHA 关联
- review：图像与结构、机位、资产相符？；结构/开口/布局/机位＋参考款式和真实比例；furnitureDetail/assetIdentity/assetScale
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- out：保留真实图片并如实交付；真实图片＋画幅差异提示；不拉伸、不藏问题；记录调用返回时间，不冒充供应商纯计算
  - ../interior-html-modeling/scripts/engine/python/render.py：ai_result 校验图片与复核字段
  - ../interior-html-modeling/scripts/engine/python/common.py：摘要与原子保存
  - ../idk-canvas-ingest-agent/SKILL.md：需要私有上传时交给平台 Skill
- a → q：工具
- q → missing：否
- q → call：是
- call → review：自己看输出
- review → out：是
- review → out：否：带观察交付

### 先定样，再衍生同空间机位

结构只由当前机位截图控制；首张图控制家具与CMF，不复制首张镜头。

#### 同空间多机位的真实参考链与计时
- input：当前机位截图与空间系列；同布局/风格/模式/参考策略，开放空间同组；旧策略首图不自动沿用，不能篡改系列摘要
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- has：已有本系列识图确认的首图？；读取 render-series.json；是：附定样；否：先做首图
  - ../interior-html-modeling/scripts/engine/python/render.py：系列索引查找
- first：首张：当前截图＋精确产品参考；产品参考决定精细款式；粗模只管建筑/位置；无参考时建概念定样，不冒称用户指定产品
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- save：真实返回、逐图识图、登记定样；native-start / complete记录调用跨度；native-result保留观察；accepted登记首图
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- next：后续：新截图＋首张定样＋指定产品；粗模锁镜头与位置，精细图锁款式和CMF；referencePolicy隔离旧定样；原顺序附全部图片
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- output：同空间一致的多机位图与完成时间；逐图复核结构、家具、镜头及crossViewConsistency；方案交方案册；图片任务直接交付，质量问题如实说明
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- input → has
- has → first：否
- has → next：是
- first → save
- save → next：后续机位准备时读取
- next → output
