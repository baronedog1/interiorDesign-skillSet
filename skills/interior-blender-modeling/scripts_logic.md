# 脚本注册表

| 脚本 | 职责 |
|---|---|
| `scripts/common.py` | handoff/artifact 哈希、唯一对象索引和坐标矩阵公共实现 |
| `scripts/index_blender_asset_store.py` | 从 Blender 专属受管资产仓确定性生成目录，不复制二进制到 Skill |
| `scripts/init_blender_model_project.py` | 验证 handoff 并初始化 Blender 项目 |
| `scripts/validate_asset_selection.py` | 由上游语义与目录元数据重算类别相容性，并验证一对一资产选择、哈希、轴和禁止重复 placement |
| `scripts/build_floorplan_scene.py` | Blender 后台原生场景构建、GLB/预览/报告 |
| `scripts/apply_circulation_adjustment.py` | 校验 adjustment-plan.v2 摘要，把唯一选中原生变换追加到可追溯 override ledger；不请求用户确认 |
| `scripts/validate_blender_scene.py` | 重开 `.blend` 后验证集合、实体标签、资产相机/灯污染、计数和模型哈希 |
| `scripts/export_native_model_manifest.py` | 从构建报告生成后端无关原生模型清单 |
| `scripts/render_blender_camera_candidates.py` | 从同一 accepted `.blend` 按 `camera-plan.v8` 生成一张确定性主候选；仅当主候选投影失败时再生成一张回退候选；不得重建几何或改写相机事实 |
| `scripts/capture_blender_views.py` | 从 accepted `.blend` 和 `camera-plan.v8` 原生渲染双状态截图、深度 EXR、RGB8 实体 ID 图及映射 |
| `scripts/blender_semantic_projection.py` | 以同一 `.blend`、同一相机、Cycles Object Index 与深度通道投影房间、结构和槽位，生成 `scene-semantic-frame.v4`；禁止截图后二次识图 |
| `scripts/resolve_component_motion.py` | 以米制原生 bounds 做不大于 0.02m 的连续扫掠并停在首次接触 |
| `scripts/test_mcp_connection.py` | MCP 初始化、工具发现和 `.blend` reopen 验收 |
| `assets/blender-template/build_template_scene.py` | 生成空 Blender 模板集合和材质 |

脚本失败必须非零退出。墙补丁由 Blender 编辑器导出后，统一交平面 Skill 的 `validate_structure_edit_patch.py` 形成新 revision。
