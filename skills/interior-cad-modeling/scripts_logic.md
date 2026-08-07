# 脚本注册表

| 脚本 | 职责 |
|---|---|
| `scripts/common.py` | handoff、artifact、坐标和 JSON 公共实现 |
| `scripts/build_functional_class_catalog.py` | 从受管 CAD 资产清单确定性生成 v3 功能分类、方向轴和人工复核状态；不读取项目做临时标签 |
| `scripts/init_cad_model_project.py` | 验证 handoff 并初始化 CAD 项目 |
| `scripts/validate_asset_selection.py` | 精确对比源对象 `functionalClass` 与 STEP 资产 `supportedFunctionalClasses`，并验证原子数量、一对一覆盖、哈希、本地正面轴、用途许可和无 placement 副本 |
| `scripts/build_cad_floorplan.py` | 从 handoff 直接构建 STEP、同 B-rep 派生 GLB、可选 3MF/STL 审阅网格、entity index 和构建报告 |
| `scripts/apply_circulation_adjustment.py` | 校验 adjustment-plan.v2 摘要，把唯一可逆原生变换追加到 override ledger，不请求用户确认 |
| `scripts/export_native_model_manifest.py` | 从 accepted 构建报告生成统一原生模型清单 |
| `scripts/capture_cad_views.py` | 把 `camera-plan.v8` 编译为 CAD 原生 snapshot jobs；拒绝嵌套 selector，以同一水泥外观输出隐藏组件的 `slot-guided` 和保留组件的 `furnished-qa`，再调用语义投影；只有前者可供生成 |
| `scripts/cad_semantic_projection.py` | 用同一 STEP 派生 occurrence 拓扑、同一相机执行软件 Z-buffer，生成实体/房间蒙版与 `scene-semantic-frame.v4`，不做截图识图 |
| `scripts/validate_cad_model.py` | 检查 STEP reopen、B-rep、计数、碰撞和哈希 |
| `scripts/resolve_component_motion.py` | 以毫米制 native bounds 做不大于 20mm 的连续扫掠并停在首次接触 |

所有失败必须非零退出。CAD 墙端点 patch 统一交平面 Skill 验证并形成新 revision。

语义投影缺少任一隔离截图、STEP/结构哈希不一致、像素尺寸不同或主空间没有可见区域时，必须停止 scene map 和渲染交接。
