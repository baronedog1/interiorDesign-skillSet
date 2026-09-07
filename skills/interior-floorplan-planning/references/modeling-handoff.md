# 户型建模交接

## 目标

把当前源模型事实整理成 `interior.floorplan-handoff.v3`。HTML、Blender、CAD 三个建模阶段都不重新识别原图，也不接受包外的裸结构数据。

## 边界

- 本文定义如何从证据链编译 `structure-data.json` 和 `trace-components.json`；真正的交付只能由 `finalize_floorplan_handoff.py` 完成，且不接受外部手写 `structure-data.json`。
- `sourceTraceIds/sourceDividerIds` 不是自由文本。墙来源于唯一墙几何，窗与物理空间连接来源于同包源开口候选；无实体墨线的功能边界来源于同包语义分界候选，且只有 `traversal=open-passage` 才进入连接图。compiled spec 的 `layers.doors/windows` 只由物理开口编译器派生，语义分界不得进入门层。全部 ID 必须进入同包来源注册表。绿紫对象 ID 必须存在于同包对应 layers。
- 旧项目、旧 confirmed-version、人工修补 JSON 和手写 `passed` 不得混入。需要复用时也必须从当前源图重新生成完整 handoff。

## 墙

1. finalizer 先把唯一 `wall-geometry.json` 注入 compiled `cleanStructure.walls`，再按尺寸比例将墙带主轴和真实厚度换算为米；authored spec 不维护墙副本。
2. 连续构造形成一个稳定 `wallId`；门洞/通道处拆成两侧墙段。
3. 有物理证据的 `cleanStructure.connections[]` 只绑定一个 `sourceOpeningId`；编译器取得该候选的源像素开口段和分类。无实体墨线且可直接穿行的功能连接只绑定一个 `traversal=open-passage` 的 `sourceDividerId`；`boundary-only` 分界不进入连接表。二者互斥，再按同一比例换算为 `structure-data.connections[].start/end`；两端空间、类型、底高不得在建模阶段修改。
4. `spaceSeeds[]`、实体墙、物理开口闭合线和全部 accepted `semanticDividers[]` 经 `topology_compiler.py` 生成房间多边形、面积和墙两侧空间；空间可达性只由真实连接计算。
5. 保存对应红色或开口 `traceId` 到 `sourceTraceIds`。
6. 蓝窗所在墙带也必须先形成完整宿主墙。

像素掩膜可以证明描线覆盖，但不能作为任一建模后端的可编辑对象。不得输出逐像素、逐扫描行或数百个碎矩形墙块。

## 窗

1. 用窗线与墙主轴的投影确定 `wallId`、沿墙 `offset` 和 `width`。
2. 普通/高/近落地窗依据原图、立面、空间功能或用户确认填写。
3. 无法唯一确定宿主或高度时，写入 `unresolved` 并停止建模交接。

## 家具

1. 绿色映射 `movable-green`，紫色映射 `fixed-purple`。
2. reviewed source model 顶层唯一 `orientationAngleUnit=degrees`；先把源度数转换一次为弧度，再逆旋转世界轮廓得到真实本地 `width/depth`，accepted `rotationY` 只保存该弧度，中心进入 `position`。禁止无单位输入、数值大小推断或后端二次换算。
3. 类型必须细化到可匹配的 `functionalClass`。电视柜不得只写 cabinet，需写 `tv-console`；连续橱柜按可见柜段拆为 `base-cabinet`、`corner-base-cabinet`、`sink-base-cabinet`、`cooktop` 等原子成员，并用一个 `assemblyId` 表达整组关系，禁止把整套橱柜写成一个 `kitchen-run` 巨型单件。
4. 用户已明确授权近似匹配或直接修正时，将授权作为可追溯输入继续执行，不重复确认。只有来源证据真正冲突、空间归属无法唯一确定，或资产库不存在同用途原子组件时才停止；禁止 generic block。

## 最小复核

- 墙段端点与第三象限门洞留白一致。
- 每个窗能指出宿主墙。
- 户型边界不包含图外空白或设备井。
- 每面墙具有编译器生成的 `adjacentRoomIds`；同一空间不能同时位于墙两侧。
- 每个实际空间有独立边界、面积和至少一条通行连接；开放分界保留在空间数据中但不生成墙。
- 绿/紫对象的中心和旋转后脚印在对应空间内。
- `interior.floorplan-structure.v3` 不包含 `rectangles[]`。
- 三份数据使用同一 `floorplanId`，正式收口命令成功；消费者核对 handoff 哈希、唯一源模型报告和来源注册表。
