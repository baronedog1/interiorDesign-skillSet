# 原组件摆放方法

## 来源

原图对象不得由项目自行补造；每个来源 placement 必须来自 `component-layout.json` 中已确认 match。用户本轮明确要求补齐、且原图没有清晰对象证据的功能件，可作为 `user-explicit-addition` 独立登记，并从初始状态执行空间、墙、开口、碰撞和层高门禁。

- `movable-green`：活动家具、可移动灯饰、绿植等绿色对象。
- `fixed-purple`：柜体、厨卫设备、悬挂灯具、固定饰面等紫色对象。

两类对象分别来自 `component-library/movable-green/` 与 `component-library/fixed-purple/`。placement 必须保留对应 `libraryPartition` 和 `libraryDirectory`，运行时按该语义直接读取组件。

## 位置和方向

- `sourcePosition` 是描线包围盒中心，初始 `position` 必须与其逐项相等，单位米。
- `sourceRotationY` 取描线主方向，弧形对象取朝向而不是包围盒最长边；初始 `rotationY` 必须相等。用户明确指出布局或方向错误时，current transform 只能通过同一 placement 的 `reviewedAdjustment` 改变，`source*` 保持不可变。
- `roomId` 取第四象限空间归属。
- 不使用模板默认中心、自动网格寻找或历史 placement。

## 尺寸

- 描线宽深写入 `sourceDimensions` 和 `targetDimensions`，初始值必须完全相等。
- 来源描线只决定 `targetDimensions` 碰撞脚印；公共 GLB 决定可见三维外形。
- `uniformScale` 等比例作用于公共 GLB，不能分别改变宽、深或高。
- `traceReshape` 记录描线脚印相对公共模型的两个轴向比例和实际 uniform scale，不代表模型被重建或非等比拉伸。
- 自动匹配宽深比例差超过 25% 时，只能换更接近的已登记公共模型。用户明确要求通用成品替换来源净空条带时，可以保留 authored 模型比例并记录 accepted `visualFitReview`；禁止在整屋建模过程中临时重建单品、使用方盒、非等比拉伸、假称精确贴合或平移来源位置兜底。

## 来源锁定与编辑边界

初始 placement 只允许精确复制上游 `source*`。第一 Skill 已经用真实编译空间像素确认：

1. 每个对象在声明空间内至少有一个像素；
2. 对象在任何其它空间内的像素为零；
3. 活动家具中心位于声明空间；
4. 固定柜可与墙带接触，但不能越入其它空间；
5. 对象轮廓不跨越真实开口中心线。

因此第二 Skill 不用固定深度的门洞净空矩形、不把地毯承托或紧邻家具视为初始错误，也不借碰撞检查移动来源对象。上游任一空间指标失败时停止导入并回到第一 Skill。

用户在 HTML 编辑，或摘要绑定的动线 adjustment-plan.v2 通过
`apply_circulation_adjustment.mjs` 使 placement 偏离 `source*` 时，运行时对当前唯一
active transform 和精确轮廓执行：

1. 脚印必须位于 `floorBoundary`；
2. 不得穿过任一墙带或真实开口中心线；
3. 不得与其它非地毯 placement 相交；
4. `variant=rug` 只作为地面覆盖层，不阻挡其它组件；
5. 只有同属一个明确连续柜组的两个紫色 placement，才可使用相同非空 `joinGroup` 声明编辑态连接；
6. 失败时恢复上一合法位置，并说明具体墙、开口或冲突组件。
7. 餐椅正面、床头端和柜门方向按浏览器审阅 authored 轴验证；同时检查贴墙、房间完整包含、对象净距和显式过道净空。

离线 `validate_component_layout.mjs` 与浏览器必须导入同一
`shared/placement-geometry.js`，避免一个判定通过、另一个运行时穿模。

## 形态

- `rectilinear`、`linear`：保持方正或线性主轮廓；
- `round`：使用圆柱、圆盘或圆桌类；
- `curved`：使用真实曲背、弧形壳体或曲面主体；
- `l-shaped`、`u-shaped`：保持转角方向；
- `organic`：使用有机叶片、茎干或自由曲面；
- `wall-mounted`、`suspended`：保留墙面/顶部安装语义。

形态不一致不是“稍微不准”，而是匹配失败。

## 编辑

项目侧允许：

- 单击后用方向键平移，或在画布直接拖动；
- 使用列表方形图标顺时针旋转 `90°`；
- 合理范围内等比例缩放；
- 恢复上游匹配位置。

直接拖动只增量更新当前组件；每个候选位置都必须先通过同一旋转脚印碰撞检查。旋转命令同样先检查完整旋转脚印，越界、穿墙或互撞时不写入。列表中的逐件复位图标恢复初始 placement 的位置、方向、缩放和 `roomId`，不能把全部家具一起复位。

项目侧不允许：

- 添加未描线组件；
- 无来源记录地删除描线对象；显式删除必须把 `sourceTraceId` 写入 `removedSourceTraceIds` 并保留 match；
- 临时替换 `componentId`；
- 用户手工或编译器非等比例拉伸公共模型；
- 修改标准组件颜色事实。

需要改变数量或类型时，先更新上游描线对象并重新生成 `component-layout.json`。
