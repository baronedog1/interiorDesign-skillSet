# 平面规划 · 尺度、拓扑与锚点 说明书

版本：2.1.0

~~~yaml
---
name: interior-floorplan-planning
description: 将客户户型图、尺寸和需求整理为米制布局 JSON；规划墙门窗、功能区、家具锚点及动线，可用宿主原生绘图探索平面方案。不交付平面 HTML。
metadata: {version: "2.1.0", category: interior-design}
---
~~~

## 调用场景

### 从客户原图生成可追溯的布局 JSON

本页保留实际业务步骤；蓝色节点链接专题，回源节点明确返回位置。文件逐项列明用途。

输入：原图、尺寸、客户需求
输出：布局 JSON；可选原生平面图

#### 从客户原图生成可追溯的布局 JSON
- input：P1 原图、尺寸、需求；先读墙门窗、阳台与房间用途
  - playbook.md：读图、尺度、空间功能和动线方法
- scale：尺度和方向可信？；像素只用于读图；以标注距离定标（详见 facts）
  - playbook.md：读图、尺度、空间功能和动线方法
- uncertain：估算与疑问随稿保留；标注估算来源；不能称精准施工数据
  - playbook.md：读图、尺度、空间功能和动线方法
- topology：P2 建立全屋唯一拓扑；共享墙一次；门窗绑定宿主；客餐厅按原图区分
  - playbook.md：读图、尺度、空间功能和动线方法
- anchor：P3 先算家具锚点与使用区；床头/沙发背靠指定墙；保留开门、柜门、拉椅及通路（详见 anchors）
  - scripts/run.py：handoff/observe/anchor 三条实际命令
- out：layout.json 交给 HTML 建模；只生成 JSON；疑问与观察同交付
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

## 完整文件地图
- MANIFEST.json：发布版本与完整文件清单
- SKILL.md：调用范围、输入输出与关键规则
- SKILL_MANUAL.pdf：面向人的算法说明书
- local_runtime.md：运行工具、路径与凭据边界
- manual/skill-flowchart.svg：同源说明书内容与图形
- manual/skill-manual.json：同源说明书内容与图形
- manual/skill-manual.md：同源说明书内容与图形
- playbook.md：读图、尺度、空间功能和动线方法
- scripts/run.py：handoff/observe/anchor 三条实际命令

## 具体逻辑解释

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
