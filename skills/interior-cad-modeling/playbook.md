# 执行 Playbook

## 1. 输入冻结

验证 handoff v3 和全部 artifact。三个后端并行时，三份项目必须记录同一个 handoff digest；禁止 CAD 从 HTML 或 Blender 反向取坐标。

## 2. 资产选择

每个 `atomicObject=true, quantity=1` 对象选择一个 STEP，且上游 `functionalClass` 必须精确出现在资产 `supportedFunctionalClasses` 中。名称、关键词、尺寸相似和风格不得改写功能类别。目录只有 FCStd 而没有 STEP 时，先在受管资产仓规范化为 STEP 并登记新哈希；项目构建器不临时打开 FCStd 猜对象。没有精确同类资产时停止，不跨类和不临时建模。

选择表只决定外形来源和统一尺度。位置、方向、房间及 footprint 始终引用 handoff。

## 3. 建筑编译

1. 地板按 room polygon 生成；
2. 墙按真实中心线、厚度和高度生成；
3. 窗在宿主墙做真实布尔切孔，再放独立玻璃/框；
4. 门洞和开放通道按 connection 保持真实通行；
5. 每空间生成可隐藏天花；
6. 开放阳台使用栏杆，封闭阳台使用真实洞口内的玻璃系统；
7. 灯具必须属于 room 并检查挂高。

## 4. 组件与碰撞

资产只统一缩放，不能分别拉伸 X/Y 以硬贴 footprint。若统一缩放无法合理匹配则换资产。移动前从 STEP entity index/B-rep 读取 bounds 和障碍物，交 `resolve_component_motion.py` 按不超过 `20 mm` 分段扫掠；第一次相交前的位置是最终合法位置。不得穿墙、穿组件、超房间或堵开口。

## 5. 编辑

墙端点只能沿原墙轴延长/缩短。CAD 先导出 `structure-edit-patch.v1`，再交 `interior-floorplan-planning/validate_structure_edit_patch.py`；通过后由平面链重编空间闭合、连接、墙自交和新 handoff，再重建 STEP。

## 6. 原生验收

1. STEP reopen；
2. B-rep valid；
3. 实体数量与 handoff 一致；
4. 坐标五点往返为零误差；
5. 组件无 primitive fallback；
6. 至少整体、正、侧、顶和一个 accepted 机位 CAD 原生截图；
7. 槽位引导图使用 CAD 原生 `rendered` 水泥显示并隐藏组件 occurrence；`furnished-qa` 使用同一相机、同一 STEP、同一水泥显示保留组件，只供人工核对，禁止提交绘图模型，也禁止为看清轮廓改用 HTML/Blender 代拍；
8. 原生模型清单哈希匹配。

失败返回对应阶段修复，不退回 HTML 或案例硬编码脚本。

## 7. 动线与后续链

native manifest accepted 后先交给 `interior-circulation-planning`。动线 Skill 唯一计算结构基线、家具新增阻塞、封门、失联、沙发/床贴墙、沙发朝向电视柜和餐椅朝向餐桌；CAD 后端只提供真实轮廓与方向轴。动线 accepted 后才交给机位 Skill。

返回 `correction-ready` 时，`apply_circulation_adjustment.py` 校验计划和操作摘要，每轮只把
一个目标中心/朝向写入 `native-layout-overrides.v1`；随后用同一 handoff、资产和
`--layout-overrides` 重建 STEP、entity index 和 manifest，再全量审计。确定性可逆修正
不询问用户；无安全解、事实冲突或用户显式变换冲突才合并询问一次。
