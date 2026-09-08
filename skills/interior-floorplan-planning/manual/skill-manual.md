# 平面规划 · 尺度、拓扑与锚点 说明书

版本：3.2.0

~~~yaml
---
name: interior-floorplan-planning
description: 通过分轮需求访谈了解居住、功能、布局和风格偏好，将客户户型图与确认需求整理为米制布局JSON；规划墙门窗、家具锚点和动线，可用原生绘图探索方案。不交付平面HTML。
metadata: {version: "3.2.0", category: interior-design}
---
~~~

## 调用场景

### 从客户原图生成可追溯的布局 JSON

本页保留实际业务步骤；蓝色节点链接专题，回源节点明确返回位置。文件逐项列明用途。

输入：户型原图、已有对话、尺寸；用户需求可以尚未明确
输出：布局JSON＋需求侧车，按需原生平面方案图

#### 先理解居住需求，再进入下一页的几何规划
- source：原图＋已有对话；空白图提供建筑事实，不提供客户画像；已有家具和颜色也不自动代表偏好
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- missing：有影响本次设计的偏好缺口或冲突？；看居住人数/功能/习惯/取舍；未知≠否定；不重复询问已有答案
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- interview：分轮需求访谈；先功能和生活习惯，再相关空间、预算和风格；问题随回答调整；不设置固定轮数（详见 interview）
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- brief：复述需求及空间影响；区分必须满足、偏好、待定、授权自由发挥；关键歧义补问；明确答案不再逐条审批
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- waiting：尚未答复：保留提问；可做尺度与不变结构；不替用户决定房间用途；等待与实际工作分别计时
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
  - ../interior-html-modeling/playbook/timing.md：记录提问、答复与等待
- next：进入几何规划与需求交接；下一页：墙门窗→功能区→锚点→layout；已知约束落实；未知保留，不伪称用户确认
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
  - scripts/run.py：handoff携带需求，不替Agent提问
- source → missing：先读已有信息
- missing → interview：是
- missing → brief：否：直接沿用
- interview → brief：收到明确答复/授权
- interview → waiting：仍在等待
- brief → next：按需求规划
- waiting → next：仅独立结构/授权探索

#### 从客户原图生成可追溯的布局 JSON
- input：P1 原图与本轮已梳理的需求；先读访谈记录，不把样板家具当用户偏好
  - playbook.md：读图、尺度、空间功能和动线方法
- scale：尺度和方向可信？；像素只用于读图；以标注距离定标（详见 facts）
  - playbook.md：读图、尺度、空间功能和动线方法
- uncertain：估算与疑问随稿保留；标注估算来源；不能称精准施工数据；随步骤记录开始、完成、耗时；代码与绘图等待分开。
  - playbook.md：读图、尺度、空间功能和动线方法
  - ../interior-html-modeling/playbook/timing.md：计时口径
  - ../interior-html-modeling/scripts/engine/python/timing.py：正式命令自动计时
- topology：P2 建立全屋唯一拓扑；共享墙一次；门窗绑定宿主；客餐厅按原图区分
  - playbook.md：读图、尺度、空间功能和动线方法
- anchor：P3 先算家具锚点与使用区；床头/沙发背靠指定墙；保留开门、柜门、拉椅及通路（详见 anchors）
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- out：layout.json 交给 HTML 建模；layout.json＋layout.requirements.json；需求revision与疑问一起交接（详见 brief-handoff）
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- native：用户要多方案：原生平面绘图；附原图探索方案 → 识图选定 → 回 P2 整理事实；图片不是测量值；不生成平面 HTML
  - playbook.md：读图、尺度、空间功能和动线方法
- input → scale：读尺度
- input → native：明确要多方案
- scale → uncertain：否
- scale → topology：是
- uncertain → topology：保留估算后
- topology → anchor：本房与宿主
- anchor → out：生成，不补丁摆放

### 先决定为什么需要，再决定摆什么

功能区域不自动产生隔断；从需求与真实可用位置形成组件选择。

输入：当前源事实与用户需求
输出：可追溯的设计决定及实际交接

#### 先决定为什么需要，再决定摆什么
- need：需求：工作 / 收纳 / 就餐；区分客户已确认与设计假设；开放书房不是新增房间
  - playbook.md：功能→组件→位置规则
- q：这件大件有独立必要功能？；已有物件能承担？是否只是为了画区域边界？
  - playbook/requirements-interview.md：读取需求与授权状态
- revise：否：回需求解释与选型；不沿开放区边界自动排书架；不等渲染再隐藏问题家具
  - playbook.md：源头取舍与全屋识图
- place：是：选择真实可用位置；沿墙或围绕功能中心；先考虑开合与通路；再选类别、尺寸、正面和风格
  - scripts/run.py：明确宿主的anchor/handoff入口
- out：全屋顶视 / 开放区轴测 → 解释大件位置；不合理回原需求或选型；合理则交接布局与需求；不新增一个事后移动家具的修补器
  - ../interior-html-modeling/data_contract.md：沿用布局与需求侧车
- need → q
- q → revise：否
- q → place：是
- revise → out
- place → out

## 完整文件地图
- MANIFEST.json：发布版本与完整文件清单
- SKILL.md：调用范围、输入输出与关键规则
- SKILL_MANUAL.pdf：面向人的算法说明书
- local_runtime.md：运行工具、路径与凭据边界
- manual/skill-flowchart.svg：同源说明书内容与图形
- manual/skill-manual.json：同源说明书内容与图形
- manual/skill-manual.md：同源说明书内容与图形
- playbook.md：读图、尺度、空间功能和动线方法
- playbook/requirements-interview.md：分轮访谈、生活情境问题、确认/待定/授权状态及需求JSON交接
- scripts/run.py：handoff/observe/anchor 三条实际命令

## 具体逻辑解释

### 按生活情境逐轮追问，不使用整套固定问卷

Agent通过实际对话提问；没有自动访谈脚本。图中“收到答复”是对话事件，不是轮询等待进程。

#### 缺口→选问题→实际答复→需求状态
- topics：按本次任务选择高影响主题；谁住/床位与功能→使用习惯与保留物；按回答深入办公、聚餐、洗烘、储物等；再问投入范围、风格喜恶与参考图
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- ask：一次问少量相关问题；说明为何影响布局；吸收一句话中的多个答案；不懂风格：用颜色/材料/感觉对比；可拒答、待定或授权推荐，不代答
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- reply：收到答复或明确委托了吗？；无答复不等于默认同意；真实askedAt/answeredAt随执行记录
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- hold：保留待定项和本轮问题；只推进不依赖答案的读图/尺度/结构；缺颜色可先布局；缺关键用途不擅自决定
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- update：理解答案并记录影响；confirmed / tentative / unknown / delegated；冲突说明取舍；不暗中删需求；按新答案再次判断实质缺口，必要时下一轮
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- result：本轮需求记录＋待定事项；items存主题/值/状态/来源/优先级/影响；rounds存实际问答时间；已有信息足够或用户授权时转规划；否则带着新缺口返回主页访谈判断
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- topics → ask：跳过已知与不相关项
- ask → reply：发给用户
- reply → hold：否
- reply → update：是
- hold → result：未完成状态
- update → result：新增需求/下一轮缺口

### 尺度与拓扑算法

按实际输入、计算、分支和文件消费者展开。

#### 尺度与拓扑：从原图信息到统一坐标
- a：选取可对应的标注墙段；记录真实长度 L、像素距离 d、方向和原点
  - playbook.md：读图、尺度、空间功能和动线方法
- b：计算比例与唯一坐标变换；米/像素 = L/d；图像 Y 向下只在入口翻转；所有墙、洞口、房间、家具共用同一变换
  - playbook.md：读图、尺度、空间功能和动线方法
- c：其它尺寸相符？；交叉核对可见标注；不可从截图编尺寸
  - playbook.md：读图、尺度、空间功能和动线方法
- d：有矛盾：记录原图事实冲突；定位标注/识图错误 → 回比例输入；保留估算稿，不镜像输出掩盖错误
  - playbook.md：读图、尺度、空间功能和动线方法
- e：形成房间、墙和开口连接；共享墙去重；门窗引用真实 wallId；房间多边形与开放连接保持原图
  - ../interior-html-modeling/scripts/engine/schemas/layout.schema.json：布局字段、单位和引用结构
  - ../interior-html-modeling/scripts/engine/python/common.py：JSON 读取与规范摘要
- f：JSON 可计算？；ID/宿主存在；有限数值；有效房间多边形
  - ../interior-html-modeling/scripts/engine/python/validate.py：区分 technicalErrors 与设计观察
- g：技术成立：输出布局及观察；handoff 不生成 HTML；留原图来源和假设
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- h：字段错误；明确字段；回本页输入
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- a → b：定标事实
- b → c：交叉比对
- c → d：否
- c → e：是
- e → f：结构数据
- f → g：是
- f → h：否

### 家具锚点计算

按实际输入、计算、分支和文件消费者展开。

#### 家具靠墙：墙基向量、尺寸与房间约束
- a：输入指定墙、房间及家具；墙 a/b、厚度；家具宽/高/深；offset 与 gap
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- b：选定墙段容纳组件？；长度>0；offset/gap有限且≥0；offset+宽≤墙长
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- c：计算切向 t 与朝房间的法向 n；t=(b−a)/|b−a|；n=(-tz,tx)；房间内部点决定 n 的正负
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- d：一次求中心与正面；中心=a+t×(offset+宽/2)+n×(墙厚/2+深/2+gap)；朝向=atan2(nx,nz)；正面 +Z；背/床头 -Z
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- e：中心在指定房间内？；按真实多边形；不借邻房空间
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- f：写新布局与观察报告；房间/门扇/拉椅净空继续按规划方法看；该锚点计算不是全屋无碰撞证明
  - scripts/run.py：handoff/observe/anchor 三条实际命令
  - ../interior-html-modeling/scripts/engine/python/validate.py：保留真实几何观察
  - ../interior-html-modeling/scripts/engine/python/common.py：原子写布局和 observations
  - playbook.md：读图、尺度、空间功能和动线方法
- bad：无解：改源墙段/组件，回输入；
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- a → b：尺寸
- b → c：是
- b → bad：否
- c → d：内法向
- d → e：锚点
- e → f：是
- e → bad：否：回源

### 需求侧车随布局交接，技术一致性不等于问卷门禁

同项目与结构检查保护资料不串用；不会要求items填满或所有状态confirmed。

#### handoff / anchor 的需求保留路径
- input：布局与可选需求文件；显式--requirements优先，否则找输入同名侧车；observe只观察，不改需求
  - scripts/run.py：handoff携带需求，不替Agent提问
  - playbook/requirements-interview.md：访谈分轮、主题、状态与交接合同
- exists：发现需求文件或显式指定？；显式路径缺失是文件错误，不当作没有偏好
  - scripts/run.py：handoff携带需求，不替Agent提问
- valid：schema/项目/条目结构一致？；projectId=layout.id；revision整数；items数组；条目ID唯一，值/来源/主题/四种状态明确
  - scripts/run.py：handoff携带需求，不替Agent提问
- old：无输入需求但目标已有旧侧车？；防止新布局误配上一份需求
  - scripts/run.py：handoff携带需求，不替Agent提问
- error：报告具体资料不一致；修正项目绑定/JSON或选择新输出；不覆盖为通过；不以偏好完成率阻断设计
  - scripts/run.py：handoff携带需求，不替Agent提问
- plain：历史或纯描图兼容输出；没有侧车时仍输出layout与observations；Agent不能以省参数绕过必要访谈
  - scripts/run.py：handoff携带需求，不替Agent提问
- copy：同交付需求JSON与摘要；保留未知/委托/所有答复；不修改几何schema；HTML Agent先读，落实到功能、锚点、CMF
  - scripts/run.py：handoff携带需求，不替Agent提问
  - ../interior-html-modeling/scripts/engine/python/common.py：原子JSON写入与摘要
- input → exists：解析输入
- exists → valid：是
- exists → old：否
- valid → error：否
- valid → copy：是
- old → error：是
- old → plain：否
