---
name: interior-floorplan-planning
description: 当用户说“规划这个户型”“做平面布局/户型规划”“描户型图”“把墙窗、门洞、空间和家具画准”，或用户要求户型建模但只有原始户型图、CAD 截图、扫描图或草图而没有本轮有效 handoff 时使用；直接从当前源图像素建立不可倒推的证据与语义决定，确定性生成红色双边墙、蓝窗、开放门洞、完整空间、绿紫对象、四象限和平面规划，逐房间视觉复核后输出 HTML、Blender、CAD 三个户型建模后端共同读取的 floorplan-handoff.v3。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"source_evidence_schema":"interior.floorplan-source-evidence.v4","handoff_schema":"interior.floorplan-handoff.v3","version":"6.4.0"}
---

# Interior Floorplan Planning

所有上游文件先按 [data_contract.md](data_contract.md) 的 `semantic-content-first-v1` 发现；推荐目录和文件名只用于排序，不能代替 schema、哈希和项目身份校验。

## 职责

本 Skill 只负责把源户型图变成可追溯的平面事实：

1. 红色双边墙、蓝色窗、门和开放通道。
2. 每个真实空间的种子、拓扑类别、边界、面积与连接关系。
3. 绿色活动家具、紫色柜体设备及其真实轮廓。
4. 四象限图、正式平面规划和 `floorplan-handoff.v3`。

HTML/Three.js、Blender、CAD 建模、机位截图和效果渲染属于后续 Skills。

## 简单意图入口

- “请规划这个户型 / 做平面布局 / 把户型描好”：直接使用本 Skill。
- “给户型做技术叠加 / 四象限 / 房间墙窗说明图”：使用本 Skill，并只从同一
  accepted 证据路径确定性生成，不调用图像模型重画户型。
- “请对这个户型建模”，但输入只有原始户型图：先使用本 Skill 生成并验收
  `floorplan-handoff.v3`。未指定后端时交给 `interior-html-modeling`；明确要求 `.blend`
  时交给 `interior-blender-modeling`；明确要求 CAD/STEP/Text2CAD 时交给
  `interior-cad-modeling`；用户要求多个版本时，三个后端分别读取同一个 frozen handoff。
- “请对这个沙发 / 柜子 / 单个东西建模”：不使用本 Skill，交给
  `movable-furniture-modeling`。
- 已存在 handoff 时，只有其源图 SHA-256、`floorplanId` 和用户本轮附件一致才可复用；
  不一致即从本轮源图重新规划，禁止借用旧项目。

## 高频数据入口

- 源图事实、语义判断、编译几何、空间和 handoff 对象：[data_contract.md](data_contract.md)。
- 四象限、示例资产和交接模板索引：[templates.md](templates.md)。
- 四个确定性脚本与本地命令：[scripts_logic.md](scripts_logic.md)、[local_runtime.md](local_runtime.md)。
- 共享基线、设备安装和同步边界：[ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)。

## 根方法

### 1. 先取证，再判断

先确定唯一布局事实模式。原图已有完整家具时使用 `source-furnished`；用户给的是空户型
或明确要求重新规划时，必须先锁定原图墙、门窗和空间边界，再调用原生绘图一次生成同
画布二维布局，验收后使用 `native-layout-furnished`。建模只消费这张已确认布局，不得跳过
平面规划直接在三维里试摆。两种模式都写入 `layoutAuthority`，结构事实始终来自原图，
家具事实只能来自所声明的 furnishing authority。

`source-evidence.json` 记录从本轮源图像素直接描出的双边墙线、真实开口、源房名锚点、逐空间对象轮廓和局部证据，并冻结源图 SHA-256 与唯一原图坐标系。外轮廓必须从入户处开始，沿内外两条墙边顺时针连续走完；每个凹口、外凸、斜切和方向变化都拆成真实角度的候选段，禁止用水平/垂直矩形包络简化。候选坐标必须来自代码辅助的源像素描点，禁止 Agent 凭目测手填近似端点。对象候选必须在写绿紫描线前逐空间登记；床、桌椅、沙发、柜体、洁具和设备等清晰对象不能因后续碰撞或净空校验而不进入台账。语义判断前，`render_floorplan_quadrants.py --evidence` 必须从同一台账生成全量机器绑定图，以及墙/开口、房名/分界、对象三组干净叠图和编号复核图；Agent 看完六张分层叠图并确认逐项重合后才允许分类。

每个对象候选以真实主体轮廓为 `outline`，以 `details[]` 只登记该对象自身的非文字
内部线。对象台账必须原子化：餐桌和每把餐椅分别是 `quantity=1` 的独立候选，马桶、
洗手台、灶具和柜体也分别登记；禁止 `dining-set`、`bedroom-set` 或“柜体含全部设备”
一类聚合对象。每个 accepted 对象必须有小写 kebab-case `functionalClass`、
`atomicObject=true` 和 `quantity=1`，并以同一值贯穿描线、`trace-components` 和三个
建模后端。柜门分缝、坐垫分缝等仍属于本对象 `details[]`。文字框、空白框和组合外包
矩形不是对象证据。对象主体和每条细节都必须通过固定源像素门禁。

`semantic-decisions.json` 由 Agent 对每条墙、开口、空间分界和对象候选做语义判断。开口
必须先记录图形签名：墙中断加门扇弧线为平开门，墙中断加平行轨道为推拉门，宿主墙内
的平行框线为窗，宿主墙内玻璃扇且无通行缺口为固定玻璃。可确认的墙进入编译；可确认
对象只分为绿色活动家具或紫色柜体设备，并绑定一个源空间标签。不确定项必须停下，不以
“住宅通常如此”为理由补线或删对象。柜后墙只能判为 `occluded-wall`：候选必须记录至少
两种不同且可追溯的源图结构证据，例如连续可见墙面、门垛端点、结构交点或一致墙厚；
“拓扑需要闭合”不能作为证据。

### 询问与自动修正规则

- 推荐目录、文件名、轻微字段拼写和等价副本不是身份门禁；按 schema、项目身份和内容哈希自动发现、内存归一化并记录 receipt，不要求用户搬文件或重复确认。
- 候选漏画、坐标偏移、错误分类、错误空间归属、开口端点或拓扑编译问题，只要当前源图证据能唯一证明正确结果，就直接修正源证据并重新编译，不先询问用户。
- 只有在完成可逆增强、局部放大、分层回绘和候选级对照后，同一位置仍有两个以上同等合理且会改变结构/对象事实的解释，才进入 `unresolved`。
- 一轮内全部 `unresolved` 必须合并成一次问题，列明候选 ID、竞争解释和所缺证据；不得逐墙、逐门或每次失败都向用户确认。
- 用户设计取舍、不可逆、付费和公开操作仍需明确授权；确定性校验和可逆规范修正不需要授权。

### 输入无颜色门禁，输出必须可追溯

任何颜色、对比度、扫描底色、轻微透视、折痕或局部手写覆盖的源图都允许进入流程，
不得因为墙线不是黑色、固定阈值未命中或一次候选提取失败而拒绝输入。正式验证器先对
原图执行固定的 `grayscale-local-contrast-union-v1` 灰度、局部对比度和彩色线联合
归一化；该黑白掩膜只用于验证输出候选确实贴合可见源线，不替代原图，也不决定语义。
可继续生成旋转、透视校正、灰度、对比度增强及逐空间 `4x/8x` 裁图供 Agent 查看，
但每张辅助图必须记录从原图到辅助图的互逆 `3x3` 变换，并用四角和中心至少五点完成
往返验证。最终候选坐标必须反算回原图左上角坐标，不能在处理图上另建事实或混用
两个坐标系。

Agent 必须把原图、归一化黑白掩膜、局部裁图和候选回绘叠图一起看，使用可见双边墙、连续墙厚、
门扇弧线、门垛端点、结构交点、房名锚点和图上尺寸判断语义。只有在完成局部放大
和候选回绘后，某个具体候选仍有两种以上无法排除的解释，才登记为 `unresolved`；
记录必须包含候选 ID、原图坐标、局部裁图、竞争解释和缺失证据。禁止用“颜色不对”、
“阈值失败”或一句“图片不清晰”代替候选级台账，也禁止用生成式修复图片创造结构证据。
门禁只约束候选回投、结构拓扑、对象消费和最终输出质量，不约束输入图的颜色格式。

### 2. 几何只编译一次

`build_wall_geometry.py` 只把已确认候选的 `faceA/faceB` 编译为红色墙带。墙坐标不能由案例脚本、空间闭合或下游模型再次填写。

authored `trace-spec.json` 禁止包含 `layers.walls/windows/doors` 或
`cleanStructure.walls`。四象限、拓扑和 finalizer 都直接读取同一份
`wall-geometry.json`，并从同一源开口候选注入窗、门、移门、开放通道和玻璃开口，
避免任何结构坐标复制后分叉。Agent 只为每个真实空间登记一个带 `spaceType`
的独立 `spaceSeed`，并引用不可变的源房名 ID。房名锚点证明原图文字在哪里，
`spaceSeed.point` 只负责选择同一空间的可行走连通区域；二者可以不是同一点，但
编译后必须落在同一个区域。拓扑失败不得反向移动房名锚点或改门端点，必须修正
墙、开口、非墙分界或独立种子。真实门窗和源图可见通道只引用已分类的
`sourceOpeningId`；没有实体墨线、仅由两个房名和开放区结构端点确定的功能分界只引用
`sourceDividerId`。二者互斥，禁止让语义分界冒充源图门洞。
`topology_compiler.py` 从墙、开口闭合线和空间种子一次生成 `floorBoundary`、
`spaces[]`、面积、墙两侧空间和连接端点；并沿每个真实开口法向在两侧独立探测空间，
编译期生成 `compiledTopology.connectionEndpointAudit`，finalizer 在正式结构中输出为 `topology.connectionEndpointAudit`。声明的 `fromRoomId/toRoomId` 与几何两侧
不完全一致时直接拒绝，不能用声明字段自证。房间多边形和开口线段都禁止手写。

客厅、餐厅、阳台、厨房等相邻区域没有实体墙墨线但确实属于不同功能空间时，
登记由两个源房名和两端结构锚点确定的 `semanticDividerCandidate`。Agent 必须在
同一语义决定中写唯一 `traversal`：实际可以直接穿行写 `open-passage`，被柜侧、
设备或其它非墙构造阻隔、只用于面积和标注分区时写 `boundary-only`。两者都编译为
同一条非墙 `semanticDivider`，只有 `open-passage` 进入空间连接图；
`boundary-only` 禁止生成连接。该线不得进入红墙或门层。每个真实门、开放通道、
移门或玻璃开口必须明确写出连接的两个空间；后续阶段不得再从家具或截图猜空间关系。

### 3. 一次代码检查，一次 Agent 看图

`validate_source_model.py` 只执行一次，检查：

- 哈希链和候选分类是否完整。
- 唯一原图坐标系、确定性灰度/局部对比度归一化、辅助查看图的双向变换和五点往返是否成立；全量及六张分层候选叠图是否由当前源图和当前候选路径确定性生成。
- 每条墙的两条边是否逐像素贴合源图，而不是只达到宽松平均值。
- 每条 `occluded-wall` 是否在源证据中记录至少两类不同结构证据，且没有把“需要闭合”当成证据。
- 最终墙是否与候选确定性一致。
- 每个空间种子是否被墙或开放分界分开，且与其不可变源房名锚点处于同一编译区域；两个种子落入同一区域即判漏墙或漏边界，房名与种子分离即判边界错误。
- 每个可用区域是否恰有一个空间种子；无人认领区域即判漏空间。
- 每面墙两侧是否属于不同空间或空间与室外；同一空间两侧的墙即判地毯、柜体或家具边误分类。
- 每个真实开口与语义分界候选是否各自只有一个分类；每个 accepted 分界是否恰好编译一次，并且只有声明为 `open-passage` 的分界进入空间连接图；所有房间是否沿真实连接图到达外部入口。
- 每条连接声明的两个端点空间是否与开口法向两侧独立探测结果完全相同；连接对象不能只凭 ID 或相邻线段通过。
- 每个源图对象候选的主体及每条细节是否有源像素支持、唯一分类和所属空间，accepted 对象是否被绿紫描线及 `trace-components` 各消费一次，且 `points/details` 与冻结候选逐点完全一致；对象轮廓不得占入其它已编译空间，活动家具质心必须落在声明空间，固定柜体只允许压住宿主墙像素。
- 每个 accepted 对象是否为 `atomicObject=true + quantity=1 + functionalClass`，逐房间 `observedFunctionalCounts` 是否与原子台账精确一致；餐桌椅、洁具和厨电不能合并计数。
- accepted 对象是否穿过真实门、移门或通道的中央净开口；存在交叉必须退回源证据重描对象或重新判断开口，禁止下游挪动避让。
- 卧室、卫生间、书房、独立衣帽间和储藏室是否声明为 `enclosed`，且至少有一个真实门或移门；超过一个可通行连接时是否有逐连接视觉复核。
- Agent 最终复核是否绑定当前几何和实际叠加图。

不再生成独立的对齐报告、流水线报告和消费者复验报告。

Agent 最后直接看原图、六张分层候选叠图、分类叠加图、红墙蓝窗图和逐房间联系图，判断漏墙、假墙、误封门洞、错误空间边界和对象漏描。每个源空间都必须形成一条对象覆盖结论，明确该空间已登记的对象 ID，并确认没有清晰对象留在台账之外。代码不能替代语义判断，Agent 也不能手改代码量尺。

## 四象限

1. 原图。
2. 原图不擦除，叠加红墙、蓝窗、门、绿紫对象、半透明黄色空间块和黄色虚线边界。
3. 仅红色双边墙带和蓝窗。
4. 墙窗、门、绿色活动家具和紫色柜体的纯描线；不显示空间名或黄色区域。

墙始终为红色双边线，窗始终为蓝色。家具和柜体只描轮廓与有效内部线，禁止实心色块或矩形包络替代曲线、L/U 形和有机形。

## 标准流程

1. 读取完整源图和尺寸，登记唯一原图坐标系并确定 `layoutAuthority`。原图已有完整布置时使用 `source-furnished`；空户型或用户要求重新规划时，先锁定原图结构，再用原生绘图生成并确认同画布二维布置图，使用 `native-layout-furnished`。先确定性生成黑白线证据掩膜，方向、对比度或局部线条不清时再生成
   带互逆 `3x3` 变换和五点往返记录的旋转/增强/逐空间裁图，再把候选回绘到原图
   复核。只有形成候选级
   `unresolved` 台账后才把全部真正冲突合并成一次用户问题；颜色、底色和单次候选提取漏检不能整体停止。
2. 从入户开始顺时针连续走查外轮廓，再描内部墙和真实开口；开口候选必须保存墙体中断、门扇弧、平行轨道、玻璃扇和宿主墙图形签名。随后按每个源房名逐空间登记 furnishing authority 中所有清晰活动家具、柜体、洁具和设备轮廓。用代码辅助的权威图像素描点建立 `source-evidence.json`。异形转角和对象曲线按真实形状分段，候选不得来自米制模型、旧墙表、轴对齐包络或目测近似坐标。
3. 运行 `render_floorplan_quadrants.py --evidence --source <source> [--native-layout <layout>]`；`--native-layout` 只在 `native-layout-furnished` 模式提供。从同一候选路径生成全量机器绑定图和六张分层叠图；Agent 分别对照原图核墙/开口与房名/分界，对照 furnishing authority 核对象。
4. Agent 写 `semantic-decisions.json`；墙、开口、分界或对象存在带候选 ID、原图
   坐标、局部裁图、竞争解释和缺失证据的 `unresolved` 时停止。
5. 运行 `build_wall_geometry.py`。
6. 从同一对象证据一对一生成绿紫轮廓和 `trace-components`，并为每个真实空间登记唯一的 `spaceType + spaceSeed + sourceLabelId`。房名锚点保持原图文字位置，拓扑种子只选同一空间内部点；二者不得互相改写。每条绿紫描线只能引用一个 accepted `sourceObjectCandidateId`，`points/details` 必须逐点复制候选的 `outline/details`；组件只能引用同一个对象 ID 和描线 ID。拓扑编译后直接用像素 assignment 核对对象所属空间，任何对象进入其它空间都退回本步骤修正分界或归属。真实门窗连接绑定 `sourceOpeningId`；无实体线的功能分区绑定独立 `sourceDividerId`。只有语义决定为 `open-passage` 的分界同时登记连接；`boundary-only` 只登记分界。authored spec 不写墙、门窗、通道或分界的第二套坐标。
7. 运行 `render_floorplan_quadrants.py --spec trace-spec.json --source <source> [--native-layout <layout>] --geometry wall-geometry.json --source-evidence source-evidence.json --decisions semantic-decisions.json`；`--native-layout` 仍只用于空户型生成布置模式。脚本从唯一墙和开口证据注入结构层并编译真实空间拓扑，任何合并种子、漏空间、假墙或错误开口都直接停止。
8. Agent 逐房间顺时针查看候选叠图、原图、最终叠加图和空间联系图，逐项登记全部墙、空间、连接和对象 ID；每个源房名都写一条对象覆盖结论，禁止用全局一句 `passed` 代替。
9. 运行 `finalize_floorplan_handoff.py`；它从已编译空间唯一生成 `structure-data.json`，再调用一次 `validate_source_model.py` 并封装 handoff。禁止另交手写结构 JSON。
10. 用户要求上传平台时，只把已验收的原始户型图、干净规划图或四象限图交给 `idk-canvas-ingest-agent`；首次创建项目，后续复用项目根目录的 `baiende-project.json`。

## 不可破坏规则

- 红墙只能来自源图证据；源图留白、门洞和通道上禁止造线。
- 每面墙必须有两条真实边，不能用中心线或线宽模拟厚度。
- 外轮廓闭合不能成为造墙理由；入口数量由当前图纸事实决定。外凸、凹口、飘窗和斜切转角必须按源图真实角度保留，禁止矩形化。
- 柜体线、家具线、尺寸线和文字不能作为墙体证据。
- 一个真实空间对应一个带受控 `spaceType` 的独立种子；卧室、卫生间、书房、独立衣帽间和储藏室固定属于 `enclosed`；`floorBoundary`、空间多边形、面积和墙邻接全部由编译器生成，Agent 不得手填。
- 两个空间种子不能落入同一连通区；每个净地面区域必须有且仅有一个种子。
- 每个拓扑种子必须与其引用的不可变源房名锚点落在同一编译区域；禁止为通过拓扑而移动房名证据。
- 墙的两侧必须是不同空间，或一个空间与室外；同一空间内部出现墙体必须退回重新分类。
- 固定柜遮挡墙面时，只有连续可见墙面、门垛/墙体交点和一致墙厚等至少两类源图证据共同成立，才可登记 `occluded-wall`；柜体边本身不能单独证明墙。
- 空间必须位于墙内净地面；空间并集覆盖全部净地面，不能跨墙、漏分区或实质重叠。
- 窗必须绑定宿主墙和源开口候选；门洞、源图可见开放通道、移门和玻璃必须绑定两个空间及同一 `sourceOpeningId`。只有无实体墨线的功能区分界使用 `sourceDividerId`；两种 ID 不能混用。
- `enclosed` 空间至少有一个真实门或移门；开放通道不能替代门。多个可通行连接不是自动失败，但必须由 Agent 逐连接复核并说明。
- 每个 accepted `semanticDivider` 必须唯一选择 `open-passage` 或 `boundary-only`。前者同时生成可通行连接，后者只用于面积、边界和交互标注；禁止自动互换，也不得伪造成墙。
- 家具、地垫、脚凳等源图中独立可见的轮廓分别保留；没有证据时不虚构。
- 对象候选台账必须先于绿紫描线冻结并进入哈希链。accepted 对象与绿紫描线、`trace-components` 必须一对一；下游碰撞、门洞净空或组件匹配失败只能修正真实轮廓、语义分类或净空解释，禁止删除、平移或缩小源对象来通过。
- accepted 对象的源轮廓不得进入其它已编译空间；活动家具质心必须在声明空间，固定柜体可以压住宿主墙但不能穿入邻室。
- accepted 对象轮廓不得穿过 accepted 物理开口的中央净开口；冲突说明对象或开口至少有一项语义错误，必须在第一阶段解决。
- 曲线必须保留曲率；L/U 形必须保留凹口；所有有效非文字内部线都要表达。
- 像素坐标先确定，毫米尺寸后换算；禁止从米制模型反投影生成描线。
- 任何不确定结构都先回到源图完成可逆增强、局部回绘和候选级消歧；只有仍存在同等合理解释时才纳入一次合并提问。不复制旧 JSON、不引入备用模板。
- 本 Skill 不读取平台凭据、不调用平台 API、不维护上传脚本；项目创建和入库只由 `idk-canvas-ingest-agent` 执行。

## 停止条件

- 完成确定性黑白归一化、可逆旋转/增强、逐空间局部放大和候选回绘后，仍有具体候选因源图缺边、
  分辨率不足或批注遮挡关键结构而无法唯一解释，并已登记候选 ID、原图坐标、
  竞争解释和缺失证据。颜色、底色、单次候选提取或线段检测失败不构成停止条件；
  输出候选无法贴合归一化后的真实可见线时，必须回到候选坐标修正。
- 同一位置存在两种同等合理的墙/柜/门解释。
- 已知尺寸与像素比例明显冲突。
- Agent 视觉复核发现漏墙、假墙、误封开口或空间越墙。
- 任一源空间未完成对象覆盖复核、存在未登记的清晰对象，或对象候选与绿紫描线/组件不能一对一。
- accepted 对象穿过真实门、移门或通道的中央净开口。
- 空间种子合并、种子与源房名锚点分离、净地面无人认领、墙两侧属于同一空间、连接端点与实际两侧不一致。
- `enclosed` 空间没有通行开口，或多个开口未完成逐连接视觉复核。
- `finalize_floorplan_handoff.py` 未成功。

## 文档路由

- [data_contract.md](data_contract.md)：源证据、语义判断、模型 spec 和 handoff。
- [playbook.md](playbook.md)：实际执行。
- [references/source-model-method.md](references/source-model-method.md)：代码与 Agent 的责任边界。
- [references/quadrant-contract.md](references/quadrant-contract.md)：四象限。
- [references/trace-classification.md](references/trace-classification.md)：线条分类。
- [references/modeling-handoff.md](references/modeling-handoff.md)：下游交接。
- [scripts_logic.md](scripts_logic.md)：六个正式脚本，包括三后端统一回传的结构编辑补丁验证器。
- [templates.md](templates.md)：模板与参考资产索引。
- [local_runtime.md](local_runtime.md)：本地确定性命令。
- [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)：共享基线与设备安装关系。
- [MANIFEST.json](MANIFEST.json)：唯一正式文件清单。

## 平台交接

- `floorplan_source`：原始户型图。
- `layout_plan`：已确认的干净平面规划图。
- `layout_annotation`：四象限或用户要求的说明图。

这些都是项目图片资产，默认目录为 `plan`。源证据 JSON、handoff、校验报告和中间叠加图不上传为项目媒体。
