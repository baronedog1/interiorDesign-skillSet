# 机位截图 · 七类空间与真实成像 说明书

版本：3.2.1

~~~yaml
---
name: interior-camera-capture
description: 从当前完整 HTML 的真实模型寻找全屋及各空间机位，冻结相机并输出原生 WebGL 参考截图；逐图识图，不改家具或冒充效果图。
metadata: {version: "3.2.1", category: interior-design}
---
~~~

## 调用场景

### 机位：空间语义先行，候选求解后看真实图片

本页保留实际业务步骤；蓝色节点链接专题，回源节点明确返回位置。文件逐项列明用途。

输入：当前完整模型及用户视角意图
输出：机位 JSON、实际 PNG、观察记录

#### 机位：空间语义先行，候选求解后看真实图片
- a：当前完整 HTML / scene / 认可机位；不覆盖用户已指定的机位；保持同版文件（详见 whole-bed）
  - scripts/run.py：find/apply/capture 入口
- q：场景、机位引用同版？；sceneKey/layoutHash/HTML 摘要一致
  - ../interior-html-modeling/scripts/engine/python/render.py：load_scene 与真实页面检查
  - ../interior-html-modeling/scripts/engine/schemas/cameras.schema.json：相机数据字段
- fix：引用错误：更新当前源模型；回本页输入，不拿旧图冒充新结果；随步骤记录开始、完成、耗时；代码与绘图等待分开。
  - ../interior-html-modeling/scripts/engine/python/common.py：JSON 与文件摘要
  - ../interior-html-modeling/scripts/engine/python/model.py：重新编译当前布局
  - ../interior-html-modeling/playbook/timing.md：计时口径
  - ../interior-html-modeling/scripts/engine/python/timing.py：正式命令自动计时
- room：明确本房主体和表达关系；卧室/客厅/餐厅/厨房/卫浴/书房/阳台（详见 rooms）
  - playbook.md：主体、空间差异及识图方法
- search：求解候选 → 冻结参数 → 真实截图；候选质量为观察，不用分数拦截整套图；看图不合格，定位空间语义或机位计算的源头（详见 search）
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- a → q：文件
- q → fix：否
- q → room：是
- room → search：本房约束

### 完整主图：先解可见地面与天花，再成像

把空间身份和构图放到生成源头；看图后修源规则，不增加事后阻断器。

输入：本轮源事实与用户完整空间表达要求
输出：可运行规则、可追溯镜头与空间关系

#### 完整主图：先解可见地面与天花，再成像
- intent：本房功能面 + 构图意图；balanced / floor / ceiling / table；正视是水平朝向正；餐桌可小幅俯视
  - ../interior-html-modeling/scripts/engine/schemas/layout.schema.json：cameraComposition
  - playbook.md：七类空间的差异
- backdrop：投射到真实房间背景边界；以背景层高和横向范围求初始视角；不用近处床脚角点把天花挤出画面
  - ../interior-html-modeling/scripts/engine/python/cameras.py：_evaluate：背景平面与视角
- solve：源头同时求站位、画幅与上下构图；有限候选中计算能看见的地面/天花；结合主体遮挡、距离及镜头自然度排序；不是生成后裁图、挪物或审美门禁
  - ../interior-html-modeling/scripts/engine/python/openings.py：门型与开合一次编译；输出共享墙局部门扇姿态
- capture：真实HTML按同一相机截图；同一verticalShift；保留门窗源状态；采集实际表面与开口证据，finally恢复状态
  - ../interior-html-modeling/scripts/engine/runtime/app.js：captureFrame / frameSpaceContext
  - ../interior-html-modeling/scripts/engine/python/render.py：逐张落盘与计时
- review：实际构图符合本次表达？；看上下边界、主体与门后空间；不是机械判分
- out：主图 + 空间事实交接；否：保留问题，回对应源输入/算法；是：primary先行，斜视/特写按需补
- intent → backdrop
- backdrop → solve
- solve → capture
- capture → review
- review → out：是
- review → intent：否：回源

## 完整文件地图
- MANIFEST.json：发布版本与完整文件清单
- SKILL.md：调用范围、输入输出与关键规则
- SKILL_MANUAL.pdf：面向人的算法说明书
- local_runtime.md：Chrome 与软件 WebGL 配置
- manual/skill-flowchart.svg：同源说明书内容与图形
- manual/skill-manual.json：同源说明书内容与图形
- manual/skill-manual.md：同源说明书内容与图形
- playbook.md：主体、空间差异及识图方法
- scripts/run.py：find/apply/capture 入口

## 具体逻辑解释

### 逐空间关系与机位

按实际输入、计算、分支和文件消费者展开。

#### 卧室：从床头墙确定床尾视线
- bed：床与床头柜属于本卧室；床头为 -Z；先确认其宿主墙；wardrobe、door 是关系对象，不借邻房床
  - playbook.md：主体、空间差异及识图方法
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- axis：以床朝向求正视方向；从床尾朝床头；frontWallId优先；斜角应同时交代床、衣柜和门
- candidate：按本房可站区域采样并排序；共用候选算法；不从床头墙外拍；床侧门板遮挡时改候选，不缩床
- q：图里床头、床侧及门柜关系可读？；检查靠墙、朝向、裁切和门板遮挡
- yes：是：卧室参考图 + 冻结机位；
  - scripts/run.py：find/apply/capture 入口
- no：否：区分床锚点错还是镜头错；床位置错回规划；取景错回候选；交付具体问题图，不改变家具掩盖
- bed → axis：床轴
- axis → candidate：视线
- candidate → q：实际截图
- q → yes：是
- q → no：否

#### 客厅：会客关系和电视方向必须互补
- a：锁定客厅自己的沙发、茶几、电视和阳台通路；洗衣机/台盆/坐凳按真实正面分别正视，长轴纵深仅作补充；各空间主图先输出，不把诊断或局部当合格主图
  - playbook.md：主体、空间差异及识图方法
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- sofa：会客机位：朝沙发正面；第一张以沙发有符号正面轴求水平正视；电视以自身正面另求正视；斜图只是补充
- tv：电视机位：从会客侧看电视组；目标包含电视柜和背景，保持真实比例；电视前景过大时改站位和目标，不缩电视
- q：两张图共同说明客厅布局？；主体完整、正反方向、阳台与通路可理解
- out：是：互补图组；
  - scripts/run.py：find/apply/capture 入口
- fix：否：回主体/站位；保留观察；不重摆家具
- a → sofa：会客关系
- a → tv：电视关系
- sofa → q：候选A
- tv → q：候选B
- q → out：是
- q → fix：否

#### 餐厅：先包含最外椅背，再决定画幅
- a：餐桌＋本组全部椅子；不只取桌面中心；确认属于餐厅
  - playbook.md：主体、空间差异及识图方法
- b：变换每个组件八角点求联合包络；size/position/rotationY → 世界坐标；最外椅背决定完整画幅；保留拉椅使用区
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- c：包络投影 → FOV → 候选排序；保持房内站位；吊灯与背景柜作空间关系；视场不足留风险，不缩小餐桌
- q：图片读得清整桌椅与背景？；看椅背裁切、柜体夹窄、拉椅区；近大远小不能误当实际尺寸
- out：结果与明确归因；是：交付全组图；否：裁切回相机，真实拥挤回布局；原方案与观察同时保留，不用图像变形掩盖
  - scripts/run.py：find/apply/capture 入口
- a → b：对象组
- b → c：投影输入
- c → q：真实图
- q → out：是：交付
- q → out：否：带问题交付

#### 厨房：沿操作面读懂台面、设备和通道
- a：本厨房台柜与设备；首图：水槽工作面 / 台盆正面；不同朝向功能面不强塞同一包络；其他功能关系另作补充
  - playbook.md：主体、空间差异及识图方法
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- b：操作面决定观看方向，通道决定站位；保持烟灶/水槽/台面关系；不借隔壁房间站位；自然站位与柜体前沿分离，柜门开合区纳入观察
- q：房内能容纳完整自然视角？；候选投影、遮挡和使用区一起判断
- full：能：操作面全景；镜头留出柜体高度和通路；保持相机参数截图
  - scripts/run.py：find/apply/capture 入口
- local：不能：明确局部／另议剖切；不从墙后拍；当前程序不自动生成剖切；保留已有图和缺口，回源选择机位
- out：看台面、门扇与设备遮挡；位置错回布局；遮挡错回镜头；不隐掉结构冒充通透
- a → b：功能关系
- b → q：候选
- q → full：是
- q → local：否
- full → out：实际图

#### 卫浴：先分台盆、马桶、淋浴，再求小空间视角
- a：识别本房功能件及玻璃/门扇；首图：水槽工作面 / 台盆正面；不同朝向功能面不强塞同一包络；其他功能关系另作补充
  - playbook.md：主体、空间差异及识图方法
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- b：以可用站位看功能关系；保持真实墙与玻璃，不为完整强行穿墙；包络抽样只是候选提示，不是透明表面视觉结论
- q：实际图能读清目标功能区？；看台盆/镜面、门扇、玻璃和淋浴遮挡
- good：是：交付功能区图；同房图组共同交代空间；机位摘要保留
  - scripts/run.py：find/apply/capture 入口
- bad：否：保留局部并说明缺失视野；回主体或站位；需要剖切时明确约定
- a → b：功能件
- b → q：实际截图
- q → good：是
- q → bad：否

#### 书房：主体工作面与座椅、收纳共同入镜
- a：本房书桌、座椅、收纳；以书桌工作面和座椅为主体；收纳只作有需求的背景，不并入整片客餐厅
  - playbook.md：主体、空间差异及识图方法
- b：取工作面正向与斜向候选；首图沿书桌+Z正面；镜头水平；就近站位、主体占幅与镜头偏移；斜向只是补充；不从远处门洞后拍
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- q：工作面与通行关系可理解？；逐图看桌前/椅后使用空间和门遮挡
- ok：是：工作关系图；
  - scripts/run.py：find/apply/capture 入口
- no：否：修主体/机位，保留观察后回候选；
- a → b：主体
- b → q：看真实图
- q → ok：是
- q → no：否

#### 阳台：休闲主体不能遮掉出入口与栏杆关系
- a：原图用途与本房对象；休闲座椅/绿植或无家具空间；不把相邻客厅家具当作阳台主体
  - playbook.md：主体、空间差异及识图方法
- q：本房有明确主体？；优先 subjectIds；缺失保持缺失，不造摆件
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- empty：无主体：空间预设图；看栏杆、墙、门和出入口；注明无家具主体
- subject：有主体：沿通路求朝向与站位；保留客厅/阳台连接，不让座椅挡住通行关系；同一采样与投影算法，真实截图逐图看
- out：明确输出：本阳台图与问题说明；洗衣机/台盆/坐凳按真实正面分别正视，长轴纵深仅作补充；各空间主图先输出，不把诊断或局部当合格主图
  - scripts/run.py：find/apply/capture 入口
- a → q：主体事实
- q → subject：是
- q → empty：否
- empty → out：空间图
- subject → out：主体图

### 候选计算与实际截图

按实际输入、计算、分支和文件消费者展开。

#### 候选求解：采样、投影、评分，最后才是截图
- a：构造本房主体与遮挡包络；subjectIds 只取本房；否则按 room.type 推断；墙段先扣洞口，门扇/窗帘/家具参与近似遮挡
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
  - ../interior-html-modeling/scripts/engine/schemas/layout.schema.json：房间、墙门窗、placements 数据
- b：普通与正视两类站位；普通 7×7×高1.40/1.25/1.55m；正视沿宿主墙内法向35档、横移0/±.18m
- q：站位在真实连通域且不在实体内？；距主体≥.45m；房间多边形及有向包围盒
- next：舍弃该站位，继续剩余候选；这是生成算法选位，不是事后移动家具
- score：投影并排序有效候选；正视：主体占幅、遮挡、就近站位排序；补充图沿用视角/可见性排序；不混成一个公式；verticalShift完成水平正视的上下构图；仍输出review
- out：冻结 cameras.json；包括 review 候选；可见比<.55、前景>.35 标风险，不冒充像素验收；没有站位则保留带原因候选，明确不是自然全景
  - ../interior-html-modeling/scripts/engine/python/common.py：保存机位与摘要
- a → b：本房事实
- b → q：候选
- q → next：否
- q → score：是：计算投影
- score → out：参数与风险

#### 真实截图与两种渲染参照：输出后恢复原模型
- a：打开当前完整 HTML；独立 Windows Headless / SwiftShader；实际页面 ready 或明确错误，不用空白页预检阻断
  - scripts/run.py：find/apply/capture 入口
  - ../interior-html-modeling/scripts/engine/python/render.py：浏览器打开/截图/回执
  - ../interior-html-modeling/scripts/engine/python/bootstrap.py：Windows Python 入口
  - local_runtime.md：Chrome 与软件 WebGL 配置
- q：明确要求空白槽位？；默认 furnished；不是自动切白模
  - playbook.md：主体、空间差异及识图方法
- full：否：带全部家具和细节；clay 仅换灰材质，不等于空房
  - ../interior-html-modeling/scripts/engine/runtime/app.js：captureFrame 默认完整场景
- empty：是：暂隐家具/柜体实例；仅 placements；JSON槽位和建筑不变；记录 hiddenPlacementIds；截图后恢复
- out：PNG + renders.json + 视觉观察；同 sceneKey、cameraDigest；真实模式与摘要；按本房主体看图，错误回空间或机位源
  - ../interior-html-modeling/scripts/engine/python/common.py：哈希与写文件
- runtime：页面实际截图调用链；已有完整 HTML 内嵌运行时，不重新编造截图
  - ../interior-html-modeling/scripts/engine/runtime/three-r164.js：WebGL 渲染引擎
  - ../interior-html-modeling/scripts/engine/runtime/controls.js：投影/相机数学
  - ../interior-html-modeling/scripts/engine/runtime/scene.js：当前建筑家具实例
- a → q：选择
- q → empty：是
- q → full：否
- full → out：全场景
- empty → runtime：指定模式
- runtime → out：真实帧

### 完整床体的候选求解

由已实现代码展开，真实模型不变；虚拟取景须明示。

#### 完整主体优先：同源取景与交接
- a：完整床体与建筑共同投影；床头/床尾/两侧/床脚八角点与建筑上下边界；不是只拟合背景墙；沿床自身正面轴
  - ../interior-html-modeling/scripts/engine/python/cameras.py：完整床体、自然候选与虚拟后退求解
- b：先求真实房内候选；房界精确远端与35档站位；共同算FOV/移轴；完整床FOV≤100°，不是拉长焦距
  - ../interior-html-modeling/scripts/engine/schemas/cameras.schema.json：视角、移轴、near冻结参数
- q：有床完整、眼高≥1米的房内候选？；投影maxAbsNDC≤0.965；FOV≤100°
- normal：保留房内完整正视；主体完整优先，同时照顾地面天花；不缩床、不移墙、不后裁图
- retreat：生成虚拟后退候选；退0.5/0.8/1.2/1.6m；眼高1.2/1.4/1.6m；near=退距+邻墙半厚+0.03m；不得切到床；裁切代价3000×max(0,NDC−.965)，连续排序
  - ../interior-html-modeling/scripts/engine/python/cameras.py：同源近裁切遮挡计算
- out：冻结整床镜头后真实识图；记录near/退距；保持床正面；不是房内可站摄影位置；模型数据不变
  - ../interior-html-modeling/scripts/engine/python/render.py：保存PNG、请求与实际提示词
- a → b：同版输入
- b → q：判断
- q → normal：是：房内
- normal → out：继续
- q → retreat：否：后退
- retreat → out：同一交接
