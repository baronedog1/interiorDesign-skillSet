# 脚本注册表

| 脚本 | 唯一职责 |
|---|---|
| `init_blender_model_project.py` | 绑定当前模型、结构、Blender catalog、风格和后端选项 |
| `acquire_blenderkit_assets.py` | 按人工审过的免费资产 ID 获取受管 1K `.blend` 并生成来源/许可/摘要清单 |
| `acquire_polyhaven_materials.py` | 按人工审过的 Poly Haven ID 获取 CC0 1K PBR 三图并生成摘要清单 |
| `build_floorplan_scene.py` | 唯一把 HTML 事实编译为 Blender 原生结构、材质和精确资产 |
| `validate_blender_scene.py` | 重开 `.blend` 验证集合、资产、朝向与零兜底 |
| `export_native_model_manifest.py` | 生成后端中立原生模型清单 |
| `export_camera_scene.py` | 从 `.blend` 导出真实网格和语义审计包 |
| `capture_blender_batch.py` | 每张冻结机位启动一个受管 Blender 进程并合并回执 |
| `capture_blender_views.py` | 单进程剪除非目标房间资产并用 Eevee 执行一张冻结机位材质渲染 |
| `resolve_component_motion.py` | 组件编辑时连续首次接触位移 |
| `test_mcp_connection.py` | Blender 连接与文件重开只读检查 |
| `common.py` | JSON 与 SHA-256 公共函数 |

只有 `build_floorplan_scene.py` 拥有 Blender 编译权；只有 Camera Skill 公共求解器拥有机位决策权。资产和材料获取脚本只接受显式审过的免费/CC0 ID，不搜索后自动入库。不存在 HTML GLB 导入器、程序材质回退、primitive fallback、Workbench 正式截图或第二机位求解器。
