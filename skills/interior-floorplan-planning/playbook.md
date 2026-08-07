# Playbook

## 1. 建立源证据

保存原图 SHA-256，先确定 `layoutAuthority`。原图已有完整布置时使用 `source-furnished`；空户型或用户要求先重新规划时，先锁原图结构，再调用原生绘图一次生成同画布二维布置图并验收，使用 `native-layout-furnished`。从唯一入户处开始，沿外墙内外两条边顺时针连续走完一圈，再描内部墙和真实开口。随后按源房名逐空间登记 furnishing authority 中全部清晰活动家具、柜体、洁具和设备；先冻结对象候选，再生成绿紫描线。每个斜切、外凸、凹口、对象曲线和方向变化分别保留真实角度及局部裁图；禁止用只支持水平/垂直的 helper 把异形边界矩形化。不读取历史项目、最终墙表或组件表，也不凭目测输入近似端点。

拍照图低对比、轻微透视、折痕或局部手写覆盖时，先确定性生成旋转、透视校正、
灰度、对比度增强和逐空间 `4x/8x` 裁图。辅助图只用于定位和视觉判断，必须保存
互逆 `3x3` 坐标变换并完成四角加中心五点往返，所有候选坐标最终回到原图。
确定性灰度/局部对比度归一化、Hough 和 OCR 都只是候选定位器，任何一种失败都不能
单独宣布整张图不可用。输入颜色、背景和对比度不设硬门禁；固定归一化结果只用于
校验 authored 输出是否对齐真实可见线，门禁失败必须修正候选坐标或语义决定。
Agent 对原图、局部裁图和候选叠图共同复核。能由当前证据唯一证明的候选漏画、偏移、
错误分类或错误归属直接修正并重编译，不询问用户；真正无法唯一判断时，以候选 ID
记录原图坐标、局部裁图、竞争解释和缺失证据。完成整张图检查后只集中询问一次，
不得逐候选确认。禁止生成式修复结构线。

先把候选路径原样回绘到源图：

```bash
python3 scripts/render_floorplan_quadrants.py \
  --evidence source-evidence.json \
  --source source-floorplan.png \
  --out-dir .
```

`native-layout-furnished` 模式在上述命令额外加入 `--native-layout native-layout.png`；
`source-furnished` 不创建也不传这张冗余图片。

Agent 必须先沿外轮廓顺时针核对每个方向变化，再核对内部墙、开口、虚线语义分界和每个空间的对象轮廓。对象按真实构成登记：主体外轮廓进入 `outline`，全部可见内部线及分离部件进入 `details`；餐桌周围每把可见椅子都要逐条登记，不能用整组外包框。未重合、异形轮廓被矩形化、对象候选圈到文字，或仍有清晰对象/细节未登记，就修正源证据，不能进入语义分类。

对象轮廓与门、移门或真实通道相交时，不能先假定对象该移走。先在同一局部源图中同时回绘红墙、橙色开口和绿紫对象：若开口线其实落在柜门分缝、地毯边或家具边，就把该开口判为 `not-opening`；若墙体中断和门扇证明确认开口真实，就按真实边界重描对象。只有二者不再穿过同一中央净开口，才允许进入下一阶段。

## 2. Agent 分类

逐墙候选判断墙、遮挡墙、非墙或未确定；逐开口先保存图形签名，再判断门、移门、源图可见通道、固定玻璃、窗、非开口或未确定。墙体中断、门扇弧、平行轨道、玻璃扇与宿主墙关系由脚本核对，推拉门与窗不能互相替代；玻璃材质随结构事实下传。逐对象候选判断活动家具、固定柜体设备、非对象或未确定，并绑定所属源房名。源房名锚点只记录文字在原图上的位置，语义决定绑定后不得为迁就拓扑移动。没有实体墨线但由两个源房名和两端结构锚点确定的功能分界，单独进入 `semanticDividerCandidates[]`，不能伪装成开口。accepted 分界必须同时判断 `traversal`：实际直接连通为 `open-passage`，仅划分功能区而不能直接穿行为 `boundary-only`。墙与柜体相邻时必须分别找证据；若柜体遮住一面墙，只能以连续可见墙面、门垛端点、与其它墙的结构交点或一致墙厚等至少两类源图事实登记 `occluded-wall`，并在候选 `occlusionEvidence[]` 逐项绑定，不能用“房间需要闭合”倒推墙。对象与 accepted 物理开口中央净开口相交时必须退回本阶段消解语义冲突；不确定即停。

## 3. 编译几何

```bash
python3 scripts/build_wall_geometry.py \
  --evidence source-evidence.json \
  --decisions semantic-decisions.json \
  --output wall-geometry.json
```

绿紫对象只能一对一引用 accepted `sourceObjectCandidateId` 建立最小
`trace-spec.json` 和 `trace-components.json`；描线的 `points/details` 必须与冻结
候选逐点完全一致，禁止只传外轮廓或在组件匹配前删掉餐椅、柜门分缝等源图细节。
authored spec 不包含任何墙、门、窗、通道或功能分界坐标；四象限和 finalizer
直接读取冻结证据。真实门窗连接只用 `sourceOpeningId`，功能区分界只用
`sourceDividerId`；只有其决定为 `open-passage` 时才同时登记连接，
`boundary-only` 不登记连接。

为每个真实空间放置一个带 `spaceType` 的独立 `spaceSeed`。卧室、卫生间、书房、独立衣帽间和储藏室使用 `enclosed`，且至少有一个真实门或移门；客厅和餐厅分别使用 `open-zone`；走廊使用 `circulation`；阳台使用 `attached`。源图分别标注的空间不得因无墙而合并；accepted 分界统一编译为 `semanticDivider`，只有 `open-passage` 同时生成连接，`boundary-only` 不生成连接，两者都不能画成墙。

## 4. 生成四象限

```bash
python3 scripts/render_floorplan_quadrants.py \
  --spec trace-spec.json \
  --source source-floorplan.png \
  --geometry wall-geometry.json \
  --source-evidence source-evidence.json \
  --decisions semantic-decisions.json \
  --out-dir outputs
```

`native-layout-furnished` 模式同样额外加入 `--native-layout native-layout.png`。

脚本先执行唯一空间拓扑编译。拓扑种子只选择房间内部连通区，并引用不可变源房名；
二者必须落在同一区域。空间种子合并、种子与源房名分离、无人认领区域、同空间假墙
或连接端点错误时停止。通过后，第二象限保留原图并显示空间块与虚线边界；第三象限
只显示红墙蓝窗；第四象限不显示空间块。

## 5. Agent 最终看图

按每个房间顺时针查看墙、窗、门、开放通道、外轮廓、柜体相邻线、空间边界和家具有效轮廓。先分别查看墙/开口、房名/分界、对象三组干净叠图及编号复核图，再逐项登记全部墙、真实开口、语义分界、空间、连接和对象 ID，并明确外凸、凹口和斜切是否逐段保留。每个源房名必须写一条 `objectCoverageReviews[]`，列出该空间 accepted 对象并明确是否还有台账外清晰对象。`enclosed` 空间有多个开口时，逐连接说明为什么成立。将六张分层候选叠图、最终叠加图、逐房间联系图、发现和未解决项写入 `agent-visual-review.json`。

## 6. 一次收口

运行 `finalize_floorplan_handoff.py --help` 查看完整参数。收口命令从当前 spec 编译空间和 `structure-data.json`，再只运行一次 `validate_source_model.py`；失败时回到源证据、空间种子、开口或语义判断修正，不增加例外状态，也不接收手写结构 JSON。

成功后只交 `floorplan-handoff.v3`。未指定后端时交 HTML；明确要求 `.blend` 或 CAD/STEP 时分别交 Blender 或 CAD；要求多个版本时三个后端读取同一 frozen handoff。确定性修正和重编译直接执行；只有仍未消解的源事实冲突、用户设计取舍、不可逆/付费/公开操作才集中询问一次。

建模后端中拖动墙端点时，先导出 `interior.structure-edit-patch-set.v1`，再运行 `validate_structure_edit_patch.py`。该校验只接受沿原墙轴的延长/缩短并保护宿主开口；通过后仍必须重新编译空间拓扑和 handoff。补丁不能原地改写已 accepted 的旧 handoff。
