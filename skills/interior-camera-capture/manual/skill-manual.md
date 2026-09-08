# 机位截图 · 七类空间与真实成像 说明书

版本：3.1.0

~~~yaml
---
name: interior-camera-capture
description: 从当前完整 HTML 的真实模型寻找全屋及各空间机位，冻结相机并输出原生 WebGL 参考截图；逐图识图，不改家具或冒充效果图。
metadata: {version: "3.1.0", category: interior-design}
---
~~~

## 调用场景

### 机位：空间语义先行，候选求解后看真实图片

本页保留实际业务步骤；蓝色节点链接专题，回源节点明确返回位置。文件逐项列明用途。

输入：当前完整模型及用户视角意图
输出：机位 JSON、实际 PNG、观察记录

#### 机位：空间语义先行，候选求解后看真实图片
- a：当前完整 HTML / scene / 认可机位；不覆盖用户已指定的机位；保持同版文件
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
  - scripts/run.py：find/apply/capture 入口
- a → q：文件
- q → fix：否
- q → room：是
- room → search：本房约束

### 正面不等于主体清楚：摄影式镜头偏移

正视保持垂直线；投影端与浏览器用同一个偏移量，截图后恢复。

输入：当前源事实与用户需求
输出：可追溯的设计决定及实际交接

#### 正面不等于主体清楚：摄影式镜头偏移
- group：明确本空间主要功能组；餐桌含最外侧椅背；书房是工作面；开放区提供站位，不提供额外主体
  - ../interior-html-modeling/scripts/engine/python/cameras.py：_subjects / front_view
- project：求完整主体包络与水平投影；不强制把地板到天花加入主体；按投影上下范围求verticalShift；保留背景余量，不俯拍或退到门外
  - ../interior-html-modeling/scripts/engine/python/cameras.py：_evaluate / projected / foreground_ratio
- rank：按主体占幅与可见性选候选；正视目标宽度占比约0.68，只是排序参考；惩罚遮挡、过宽视角与离本功能区太远；实际图仍由Agent判断
  - ../interior-html-modeling/scripts/engine/python/cameras.py：前景射线也采用相同偏移
- capture：真实截图并恢复原相机；setViewOffset应用同一verticalShift；finally清除偏移，恢复原视图；不改变建筑或家具
  - ../interior-html-modeling/scripts/engine/runtime/app.js：captureFrame：偏移/成像/恢复
- select：交付选择：正视主图先行；primary先选；supplement按表达需要；layout-reference是平面/鸟瞰，不全量送原生渲染
  - playbook.md：逐空间选图与识图
- group → project
- project → rank
- rank → capture
- capture → select

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
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- candidate：按本房可站区域采样并排序；共用候选算法；不从床头墙外拍；床侧门板遮挡时改候选，不缩床
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- q：图里床头、床侧及门柜关系可读？；检查靠墙、朝向、裁切和门板遮挡
  - playbook.md：主体、空间差异及识图方法
- yes：是：卧室参考图 + 冻结机位；
  - scripts/run.py：find/apply/capture 入口
- no：否：区分床锚点错还是镜头错；床位置错回规划；取景错回候选；交付具体问题图，不改变家具掩盖
  - playbook.md：主体、空间差异及识图方法
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
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- tv：电视机位：从会客侧看电视组；目标包含电视柜和背景，保持真实比例；电视前景过大时改站位和目标，不缩电视
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- q：两张图共同说明客厅布局？；主体完整、正反方向、阳台与通路可理解
  - playbook.md：主体、空间差异及识图方法
- out：是：互补图组；
  - scripts/run.py：find/apply/capture 入口
- fix：否：回主体/站位；保留观察；不重摆家具
  - playbook.md：主体、空间差异及识图方法
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
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- q：图片读得清整桌椅与背景？；看椅背裁切、柜体夹窄、拉椅区；近大远小不能误当实际尺寸
  - playbook.md：主体、空间差异及识图方法
- out：结果与明确归因；是：交付全组图；否：裁切回相机，真实拥挤回布局；原方案与观察同时保留，不用图像变形掩盖
  - scripts/run.py：find/apply/capture 入口
- a → b：对象组
- b → c：投影输入
- c → q：真实图
- q → out：是：交付
- q → out：否：带问题交付

#### 厨房：沿操作面读懂台面、设备和通道
- a：本厨房台柜与设备；只取本房 kitchen/cabinet 等实体
  - playbook.md：主体、空间差异及识图方法
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- b：操作面决定观看方向，通道决定站位；保持烟灶/水槽/台面关系；不借隔壁房间站位；自然站位与柜体前沿分离，柜门开合区纳入观察
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- q：房内能容纳完整自然视角？；候选投影、遮挡和使用区一起判断
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- full：能：操作面全景；镜头留出柜体高度和通路；保持相机参数截图
  - scripts/run.py：find/apply/capture 入口
- local：不能：明确局部／另议剖切；不从墙后拍；当前程序不自动生成剖切；保留已有图和缺口，回源选择机位
  - playbook.md：主体、空间差异及识图方法
- out：看台面、门扇与设备遮挡；位置错回布局；遮挡错回镜头；不隐掉结构冒充通透
  - playbook.md：主体、空间差异及识图方法
- a → b：功能关系
- b → q：候选
- q → full：是
- q → local：否
- full → out：实际图

#### 卫浴：先分台盆、马桶、淋浴，再求小空间视角
- a：识别本房功能件及玻璃/门扇；台盆、马桶、淋浴位置不能互换；只从当前 room 选主体，不借邻房资产
  - playbook.md：主体、空间差异及识图方法
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- b：以可用站位看功能关系；保持真实墙与玻璃，不为完整强行穿墙；包络抽样只是候选提示，不是透明表面视觉结论
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- q：实际图能读清目标功能区？；看台盆/镜面、门扇、玻璃和淋浴遮挡
  - playbook.md：主体、空间差异及识图方法
- good：是：交付功能区图；同房图组共同交代空间；机位摘要保留
  - scripts/run.py：find/apply/capture 入口
- bad：否：保留局部并说明缺失视野；回主体或站位；需要剖切时明确约定
  - playbook.md：主体、空间差异及识图方法
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
  - playbook.md：主体、空间差异及识图方法
- ok：是：工作关系图；
  - scripts/run.py：find/apply/capture 入口
- no：否：修主体/机位，保留观察后回候选；
  - playbook.md：主体、空间差异及识图方法
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
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- subject：有主体：沿通路求朝向与站位；保留客厅/阳台连接，不让座椅挡住通行关系；同一采样与投影算法，真实截图逐图看
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
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
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- q：站位在真实连通域且不在实体内？；距主体≥.45m；房间多边形及有向包围盒
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- next：舍弃该站位，继续剩余候选；这是生成算法选位，不是事后移动家具
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- score：投影并排序有效候选；正视：主体占幅、遮挡、就近站位排序；补充图沿用视角/可见性排序；不混成一个公式；verticalShift完成水平正视的上下构图；仍输出review
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
- out：冻结 cameras.json；包括 review 候选；可见比<.55、前景>.35 标风险，不冒充像素验收；没有站位则保留带原因候选，明确不是自然全景
  - ../interior-html-modeling/scripts/engine/python/cameras.py：本房主体、候选、投影与评分
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
  - ../interior-html-modeling/scripts/engine/runtime/app.js：empty-slots 可见性快照/恢复
- out：PNG + renders.json + 视觉观察；同 sceneKey、cameraDigest；真实模式与摘要；按本房主体看图，错误回空间或机位源
  - ../interior-html-modeling/scripts/engine/python/render.py：原子保存 PNG 与模式
  - ../interior-html-modeling/scripts/engine/python/common.py：哈希与写文件
- runtime：页面实际截图调用链；已有完整 HTML 内嵌运行时，不重新编造截图
  - ../interior-html-modeling/scripts/engine/runtime/three-r164.js：WebGL 渲染引擎
  - ../interior-html-modeling/scripts/engine/runtime/controls.js：投影/相机数学
  - ../interior-html-modeling/scripts/engine/runtime/scene.js：当前建筑家具实例
  - ../interior-html-modeling/scripts/engine/runtime/app.js：冻结机位、绘制、还原状态
- a → q：选择
- q → empty：是
- q → full：否
- full → out：全场景
- empty → runtime：指定模式
- runtime → out：真实帧
