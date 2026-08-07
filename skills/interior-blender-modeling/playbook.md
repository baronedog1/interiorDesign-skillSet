# 执行 Playbook

## 阶段 1：冻结输入

验证 handoff 与全部 artifact。输出 `input-lock.json`。结构错误退回平面 Skill，不在 Blender 中补墙。

## 阶段 2：资产选择

先按上游原子 `functionalClass` 查询 Blender 专属 catalog，只保留明确支持同一功能类的资产，再比较尺度、风格和安装方式。优先真实 `.blend`，其次有完整 PBR 的 GLB。检查审阅方向轴、原点、单位和许可。没有同类资产时标记 `blocked-asset-gap`，不得跨类别凑用。

## 阶段 3：结构物化

先生成地面、墙与真实洞口，再生成窗/门/栏杆。每一源 wall/opening ID 只出现一次。窗框、玻璃和门扇是洞口子对象，不得成为第二套结构坐标。

## 阶段 4：天花与灯具

按 room polygon 生成独立天花。天花事实默认存在、检查视图默认隐藏，可一键显示；正式相机渲染按镜头需要显示。吊灯根节点吸附 ceiling root；高度变化同时检查最低点净高。没有吊顶设计要求时使用平整天花，不自动堆造型。

## 阶段 5：组件

从资产仓 link/append 实际模型。先测量全部可渲染子物体的世界包围盒，按目标宽、深、高三轴中最严格比例统一缩放；再应用轴适配和 handoff 旋转，最后按旋转后真实包围盒重新居中并接地。不能依赖下载模型的原点，也不能为了塞进槽位而做 X/Y/Z 非等比缩放。白模与源色是同一网格的两套 material override；白模覆盖每个 `component-part`，槽位引导隐藏根节点及全部子物体。

## 阶段 6：编辑和碰撞

- 墙端点只允许沿原切向延长/缩短；Blender 生成 patch 后交 `interior-floorplan-planning/validate_structure_edit_patch.py`，通过新 handoff revision 重新构建，不改旧结构事实。
- 组件拖动先从 Blender depsgraph 取 world bounds 和障碍物，交 `resolve_component_motion.py` 做连续扫掠；找到首次碰撞参数并停在接触前的 epsilon。
- Blender operator 只提交通过检查的 transform；失败恢复上个 accepted revision。

## 阶段 7：原生验收

重新打开 `.blend` 并运行 `validate_blender_scene.py`，检查集合、ID、原子功能类、数量、资产相机/灯污染、坐标和哈希。逐组件检查中心误差 `<=2mm`、接地误差 `<=2mm`、高度不越界。导出 manifest 后先执行统一动线审计；只有通过后才生成机位预览，并分别实际查看同机位槽位引导图与白模图。机位截图必须直接由 Blender camera/render 产生。

动线返回 `correction-ready` 时，脚本验证计划、候选和操作摘要后更新
`native-layout-overrides.v1`，每轮只应用一个目标中心/朝向并重建原生场景。来源 handoff
不变；新实体携带 `circulation-deterministic-correction`，新模型哈希必须从头审计。
确定性修正不询问用户；算法无解、事实冲突或用户显式变换冲突才合并询问一次。

## 错误归属

- 墙窗/空间错：上游证据或 handoff。
- 对象位置/方向错：handoff object facts 或显式项目 revision。
- 可见外形错：Blender 资产选择/轴/尺度。
- 穿模：碰撞或编辑提交逻辑。
- 截图错：机位 Skill 或 Blender capture adapter。
