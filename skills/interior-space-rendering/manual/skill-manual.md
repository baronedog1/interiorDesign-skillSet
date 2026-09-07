# 原生绘图 · 完整场景与空白槽位 说明书

版本：3.0.0

~~~yaml
---
name: interior-space-rendering
description: 将同机位完整模型截图通过宿主原生绘图生成室内效果图，保留结构、家具、机位与材质意图，登记实际调用和逐图复核；不把 WebGL 截图当最终渲染。
metadata: {version: "3.0.0", category: interior-design}
---
~~~

## 调用场景

### 原生绘图：默认完整模型，白模仅明确要求时使用

本页保留实际业务步骤；蓝色节点链接专题，回源节点明确返回位置。文件逐项列明用途。

输入：模型图、CMF、产品参考、实际工具
输出：原生图片、调用回执、逐图问题

#### 原生绘图：默认完整模型，白模仅明确要求时使用
- a：同版模型图、JSON、机位与指定资产；先看图和用户要求；不把配置当工具可用证明
  - scripts/run.py：ai-request/native-prepare/native-result 入口
- q：用户明确要求白模／空白槽位？；默认 furnished；不因效果差自动切模式（详见 modes）
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- full：否：完整家具与细节截图；普通简化家具精细化，类别/数量/尺寸范围不变；随步骤记录开始、完成、耗时；代码与绘图等待分开。；同空间先定样，再准备其它机位；见SERIES。（详见 consistency）
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
  - ../interior-html-modeling/playbook/timing.md：计时口径
  - ../interior-html-modeling/scripts/engine/python/timing.py：正式命令自动计时
- empty：是：建筑截图＋原 JSON 槽位；家具/柜体暂隐；位置、尺寸、朝向仍固定
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- prompt：生成真实提示词与资产约束；锁房型、墙门窗和同机位；指定资产不变形（详见 assets）
  - ../interior-html-modeling/scripts/engine/python/render.py：两种模式、槽位、产品尺寸进入 prompt
- call：真实宿主调用 → 看图 → 交付；没有工具或图片就如实报告；不拿截图冒充（详见 native）
  - ../interior-html-modeling/scripts/engine/python/native_image.py：工具准备、实际调用回执和结果绑定
- a → q：模式
- q → empty：是
- q → full：否：默认
- full → prompt：完整图
- empty → prompt：空槽图与 JSON
- prompt → call：附图调用

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

### 结构锁定与资产尺度

按实际输入、计算、分支和文件消费者展开。

#### 精细家具与指定资产：细化普通件，锁定指定件
- a：提示词的结构底线始终不变；不改房型、墙门窗、空间尺度；机位位置、朝向、投影、FOV和裁切同图；普通家具细化细节，不重布局；指定资产身份优先于风格变化
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
  - ../interior-html-modeling/scripts/engine/python/render.py：实际拼装不可变约束与 slots
- q：用户提供指定产品参考？；产品图与 placementId 一一对应
  - ../interior-html-modeling/scripts/engine/python/render.py：读取 products 文件与绑定校验
- normal：否：细化现有简化家具；保持类别、数量、位置、朝向、宽高深范围；提高材质、纹理尺度、接触阴影和细节
  - ../interior-html-modeling/scripts/engine/catalog/styles.json：当前风格/渲染意图
- asset：是：读取真实产品尺寸并保留身份；sizeMetres=[宽,高,深]；未知标 null，补查；不将槽位尺寸当产品实测，不拉伸或压扁；部件、颜色纹理、形体和比例不被风格改写
  - ../interior-html-modeling/scripts/engine/python/render.py：真实尺寸检查、来源与 prompt
  - ../interior-html-modeling/scripts/engine/python/common.py：参考图 SHA 与 JSON读取
  - ../idk-canvas-ingest-agent/SKILL.md：需要平台资产时调用独立平台能力
- conflict：尺寸冲突：回布局／选型或请用户确定；不靠扭曲资产塞进槽位；记录未确定尺寸；结果复核必须看资产身份、比例与尺度
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- a → q：资产条件
- q → normal：否
- q → asset：是
- asset → conflict：比较产品与槽位

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
- review：图像与结构、机位、资产相符？；structure/openings/layout/camera；furnitureDetail/assetIdentity/assetScale
  - playbook.md：两模式、锁结构机位、家具细化与资产不变形
- out：保留真实图片并如实交付；是：记录符合；否：指出位置并修源再生成；不能以提示词/检测通过保证绝无变形
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
- input：当前机位截图与空间系列；同布局、风格、模式、开放连接分组；先生成正视主图，不同系列可独立执行
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- has：已有本系列识图确认的首图？；读取 render-series.json；是：附定样；否：先做首图
  - ../interior-html-modeling/scripts/engine/python/render.py：系列索引查找
- first：首张：当前截图＋精确产品参考；粗模型只约束位置尺寸朝向；原生绘图精细化；墙门窗镜头不变
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- save：真实返回、逐图识图、登记定样；native-start / complete记录调用跨度；native-result保留观察；accepted登记首图
  - scripts/run.py：ai-request/native-*入口
  - ../interior-html-modeling/scripts/engine/python/render.py：连通空间系列与定样引用
  - ../interior-html-modeling/scripts/engine/python/native_image.py：实际调用计时与结果登记
- next：后续：新截图＋首张定样＋指定产品；新截图锁当前镜头，定样锁家具CMF；校核所有附图摘要，保留每次实际提示词
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
