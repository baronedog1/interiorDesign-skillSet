# source-intent-fixture-facing-frontal-camera-v6

## 1. 唯一决策顺序

```text
用户明确确认的有向光轴（若有）
→ 主体正面轴和真实背景墙
→ 主体完整
→ 居中与镜头净距
→ 严格正视
→ 上下空间同时成立
→ 房内自然视野优先
→ 必要时沿同一法线后退
→ 目标空间 Entity-ID 裁切
→ 遮挡、空白、移轴和透视排序
```

这不是多套算法串联，也不是先选错机位再靠广角补救。用户已明确确认方向时，`interior.user-camera-intent.v1` 的有向光轴优先，候选光轴与它的点积不得小于 `0.92`；未提供时，床、沙发和书桌等方向主体按自身正面轴求解。一个看起来整齐的侧面镜头不能因为 FOV 更小而胜出。

## 2. 主体投影

对主体关键点 `q_i`、相机位置 `p`、前向 `f`、右向 `r`、垂直视场角 `φ`、画幅比 `a`：

```text
z_i = (q_i - p) · f
u_i = ((q_i - p) · r) / (z_i tan(φ/2) a)
v_i = (q_i.y - p.y) / (z_i tan(φ/2))
```

加上镜头移轴 `(w_x,w_y)` 后，所有必拍主体关键点必须位于安全画幅内。

## 3. 正视约束

目标墙朝室内法线为 `n`：

```text
f = -n
yawError ≤ 0.25°
pitch = 0°
roll = 0°
```

方向主体还要求光轴与主体深度/正面轴的绝对点积不小于 `0.90`。卧室构图优先使用床头柜、边几和床头灯作为上下文，衣柜与书桌仅在没有床边上下文时扩大画幅。

### 3.1 靠墙设备的有符号正面

马桶、浴室柜、洗衣机、烘干机和洗手盆等设备不能只判断“轴平行”，还要区分正面和背面。对每件设备找到目标房间多边形中最近边界，取得向室内法线 `n`；设备正面朝 `n`，从正面拍摄的相机光轴应朝 `-n`。多个设备分别保留该方向，候选使用平均有符号点积排序；背面候选不能因 FOV 较小而胜出。

### 3.2 多主体投影避挡

对每两个必拍主体的原生 Entity-ID 投影框计算：

```text
overlap = intersectionArea / min(areaA, areaB)
centerSeparation = distance(centerA, centerB)
```

卫浴、阳台和洗衣空间若 `overlap > 0.34`，该候选写入非阻断提示并在同一严格墙法线候选池中降序；无重叠且设备正面正确的候选优先。

## 4. 居中、净距与站位

方向主体的站位先最小化横向偏移。相机到主体最近表面的距离低于 `1.10m` 时，房内镜头视为贴脸站位；若没有同时满足正面、居中和净距的房内位置，就沿同一法线后退。后退候选优先接近 `1.60m` 的主体表面净距，避免床尾板堵住画面，也避免退得过远让主体过小。没有明确方向的空间仍采用 `0.75m / 1.35m` 的通用净距。

## 5. 自然视野与后退

对每个房内合法机位从小到大枚举 FOV，只有同时满足：

- 主体完整；
- 顶部空间达到最小值；
- 底部空间达到最小值；
- 移轴在硬件范围内；

才把该 FOV 记为完整候选。房内存在 `FOV≤100°` 且 `perspectiveDepthRatio≤6` 的完整严格正视解时优先房内。房内只有更极端的超广角解时，沿同一墙法线后退，并从后退站位的完整候选中优先选择接近 `90°` 的镜头。这里是排序偏好，不是硬门禁。

## 6. 目标空间裁切

房内和后退站位都可能带入相邻房间或户型外区域。求解器从当前 VTK Entity-ID 帧取得属于目标房间的墙、开口与硬主体像素，计算左右和底部包络；顶部固定为 `0`，保留完整天花板。裁切边界向目标空间内部收边，同时保留主体安全余量：

```text
cropLeft  = min(targetRoomLeft + innerMargin, primaryLeft - subjectMargin)
cropRight = max(targetRoomRight - innerMargin, primaryRight + subjectMargin)
cropTop   = 0
cropBottom = max(primaryBottom + subjectMargin,
                 min(targetWallBottom + wallMargin, framingBottom + floorContextMargin))
```

裁切框完全由当前模型的原生墙体/开口实体 ID、主体 ID 与投影产生，`imageRecognitionUsed=false`。HTML 截图器只按冻结框裁图，并把墙门窗家具的投影坐标重新映射到最终 PNG；它不重新决定裁切。

## 7. 纵向空间包络

原生语义网格可用时使用 `ceilingRatio / floorRatio`；语义网格不稳定时，使用 framing 包围框上下的可用空间：

```text
effectiveCeilingRatio = max(ceilingRatio, topOpenRatio)
effectiveFloorRatio   = max(floorRatio, bottomOpenRatio)
```

正式图要求：

```text
effectiveCeilingRatio ≥ ceilingMinimumRatio
effectiveFloorRatio   ≥ floorMinimumRatio
```

纵向移轴不是固定值，而是解析求解同时满足主体完整与上下空间的可行区间。目标值偏向更多顶部空间。

## 8. 狭长空间通用适配

房间全局狭长程度：

```text
roomSlenderness = max(spanX, spanZ) / min(spanX, spanZ)
```

针对每面正视墙还计算：

```text
viewWidth  = polygon projected span on wall tangent
viewDepth  = polygon projected span on wall inward normal
viewSlenderness = viewDepth / viewWidth
combinedSlenderness = max(roomSlenderness, viewSlenderness)
```

使用 `combinedSlenderness` 调整：

- 退距搜索上限；
- 主体目标面积；
- FOV 代价；
- 主体最小像素阈值；
- 天花板/地板目标带。

因此不是只对某一个卧室写死特殊值，而是任意狭长厨房、卫浴、书房、走廊、衣帽间都走同一套几何逻辑。

## 9. 厨房主体

单图不再要求每个细小柜体模块都成为独立硬主体。算法先按柜体方向建立连续工作带，将水槽/灶台分配给最近的工作带，选择功能最强的一条作为硬主体；其他工作带和冰箱作为高优先级上下文。

## 10. 真实家具几何

场景生成器必须等待 `runtimeReady + settled + ready`，并拒绝任何 `failed/unmatched` 家具。相机站位碰撞使用模型记录的源局部宽、深、高和旋转；VTK 显隐评分继续使用浏览器真实网格包络。两者不能混用，否则旋转后的衣柜包络会被再旋转一次，或者隐藏 footprint 会被误读为 `1cm` 高家具。

## 11. 多图

多图模式仍只使用严格墙法线正视候选。请求数量超过现有不同候选时，交付已经求出的镜头并在合同中记录数量差异，不因为质量评分或候选数量不足扣住已有图片。
