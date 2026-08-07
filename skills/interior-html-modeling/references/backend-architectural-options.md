# HTML 建筑表现与编辑选项

## 唯一选项文件

项目的 HTML 后端表现只写入 `backend-options.json`，schema 为
`interior.model-backend-options.v1`。它不能重写 handoff 中的墙、洞口、空间或源对象。

## 天花与灯具

- 每个房间从同一 `rooms[].polygon` 生成一块稳定 ID 的天花面，默认隐藏，工具栏“顶”
  和图层页共用同一 `layers.ceilings` 状态。
- 显示/隐藏只改变可见性，不删除天花实体；正式截图的语义清单必须登记当前可见天花。
- 吊灯、吸顶灯和射灯是资产组件或 `scene-rig` 灯具。吊装点必须落在所属房间天花投影内，
  组件底部净高和灯光目标均要通过验收。

## 窗型

窗洞 `wallId/offset/width/sill/openingHeight` 永远来自 handoff。后端只能在同一洞口内选择：

- `frameless-glass`：极细边框，无中梃；
- `fixed-pane`：四边框，无中梃；
- `casement`：四边框和一条开启分格；
- `sliding`：四边框和中部搭接分格。

窗帘属于可选软装，不能遮掉窗事实。改变洞口尺寸必须回到平面 Skill 形成新 handoff，
不能借渲染或后端样式偷偷缩窗。

## 阳台

`source-structure` 原样物化上游结构；`open-railing` 只在已确认的外边界生成栏杆；
`closed-glazing` 只在已确认的外边界生成玻璃围护。开放/封闭状态没有证据时停止确认，
不能把栏杆写成墙，也不能把玻璃围护写成新房间。

## 墙端点编辑

HTML 允许沿原墙轴延长或缩短起点、终点。每次合法修改只产生
`interior.structure-edit-patch.v1`：保存原始端点、当前端点、来源 trace 和延长量；宿主窗
同步调整沿墙 offset 以保持世界位置。修改不得出户型边界、压住组件、破坏窗洞或产生零长墙。
补丁不是新上游事实；需要跨后端复用时，必须交回 `interior-floorplan-planning` 审阅并生成
新的 handoff。

## 连续碰撞

组件拖动按不大于 `0.02m` 的路径步长逐点检查房间、墙、门洞和其它组件。首次非法点前的
最后合法位置即为停止位置，禁止只检查鼠标抬起点或用瞬移跨过薄墙。
