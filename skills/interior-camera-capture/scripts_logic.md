# Scripts Logic

所有正式确定性代码只位于本 Skill 的 `scripts/`。未列入下表的脚本不得作为生产入口。

| 脚本 | 职责 | 是否拥有机位决策权 |
|---|---|---|
| `run_camera_pipeline.py` | 唯一客户生产入口；HTML 模板只求解一次，Blender/CAD 强制复用同一 plan，再调用原生截图器并写逐阶段用时 | 否 |
| `generate_vtk_camera_scene.py` | 唯一场景生成入口；从当前 HTML 导出真实网格，同时记录源局部尺寸/方向和浏览器网格包络 | 否 |
| `export_html_camera_scene.mjs` | 等待全部精细 GLB 真正加载，再执行 Three.js GLTF 导出；不可独立替代正式入口 | 否 |
| `unified_camera_solver.py` | 唯一候选生成、主体正面轴、设备有符号正面、多主体投影避挡、居中净距、FOV/移轴、隐藏和最终选择入口 | **是，唯一** |
| `semantic_vtk_scene.py` | 导入语义 GLTF，提供 Entity-ID/Depth/RGB 与射线事实 | 否 |
| `capture_frozen_html_plan.mjs` | 等待精细资产真实加载后按冻结计划截图；房内和后退镜头都原样应用墙体 projectionCrop，并把 facts 投影重映射到最终 PNG | 否 |
| `export_backend_camera_plan.py` | 当某后端合同需要时，将冻结 v3 pose 无损转换为后端适配 plan；不得修改 pose | 否 |
| `audit_delivery.py` | 对真实生产回执、正式图片/JSON、唯一决策入口和旧文件执行发布审计 | 否 |

`assets/backend-templates/*.json` 是唯一后端差异入口。HTML 固定 `solve-once-from-current-html`；Blender/CAD 固定 `consume-frozen-v3`。只有 HTML 路径能触发统一求解器，后端模板不得声明第二个场景求解或 selector。

正式下游只使用同名 `camera-image-facts.v3 + PNG`。`native-capture-result.v1`、`shot-scene-map.v10` 和可见性中转脚本已经退出活动文件，不得恢复兼容分支。
