# Script Logic

- `import_floorplan_handoff.mjs`：按摘要发现并只读导入当前 handoff；整屋和局部共用同一模板。
- `match_trace_components.mjs`：规范功能类别后在全受管库做同类确定性匹配，编辑语义与物理资产分区分离；所有对象必须落到真实 GLB，缺资产时返回精确缺口并在补库后重跑，绝不生成色块。
- `compile_coauthoring_model.mjs`：把结构、组件布局和 scene rig 合并为唯一 `coauthoring-model.json/js`，供室内户型人机共创模板直接加载；不生成第二套墙线或家具数据。
- `materialize_component_assets.mjs`：从受管资产仓复制当前项目实际使用的文件并锁摘要、许可。
- `validate_component_layout.mjs`：仅供 Skill 修改和发版回归，验证一一对应、来源 footprint、方向、关系、边界、项目 lock 和去重资产预算摘要；不进入客户生产路径。
- `audit_component_runtime_geometry.mjs`：发布前逐件读取中央库全部 GLB，以目录宽深高确定原生或 90 度归一框架，输出唯一运行时几何准入事实和完整审计记录。
- `validate_component_library.mjs` / `validate_public_asset_store.mjs`：验证中央目录、源码、运行 GLB、许可、哈希、双材质能力及几何准入与目录摘要的一致性。
- `build_standalone_html.py`：把当前项目模型同时写入 `#template-data` 与启动数据后再内联资产，保证用户保存的 HTML 自身就是完整当前状态；以 14 MiB 原始运行资产、29 MiB 最终 HTML 复核预算。
- `import_returned_html.py`：验证用户回传 HTML 的项目身份和 `documentRole`，从 `#template-data` 提取模型，用临时文件加原子替换覆盖工作区唯一当前 HTML/JSON，并写摘要回执。
- `collect_modeling_stage_timing.py`：读取任务起始时间及导入回执、组件布局、资产锁、自包含 HTML、原生清单五个正式产物，生成 `interior.html-modeling-stage-timing.v1`；只统计 HTML 建模，不把机位、截图或渲染混入建模耗时。
- `capture_html_views.mjs`：消费外部冻结机位并在当前 HTML 中生成原生视图；只执行截图，不拥有机位选择和资产替换权。
- `export_native_model_manifest.mjs`：登记唯一原生模型和输入绑定，并从当前 Skill 目录自动绑定、验证唯一测量适配器和截图适配器。
- `measure_html_camera_envelopes.mjs`：由 Camera Skill 正式入口调用同一 HTML 场景的 OBB 与可退距 API；不手填尺寸、不选机位。
- 模板 `__INTERIOR_COAUTHORING_EDITOR__`：向 Camera Skill 暴露稳定算法相机、最小遮挡和代码投影事实接口；旧私有编辑器 API 不再是正式依赖。
- `init_html_model_project.mjs`：从唯一模板创建项目并写入当前 handoff 身份。
- `validate_structure_data.py`：仅供 Skill 修改和发版回归验证 structure v4；生产导入默认不调用。
- `validate_template_ownership.py`：拒绝项目复制或替换正式模板代码。
- `build_functional_class_tags.mjs`：从 canonical catalog 编译功能类别、前向轴和安装标签。
- `validate_component_geometry.mjs`：仅供 Skill 修改和发版回归验证当前项目全部对象都有真实受管网格、来源 footprint 和可调尺寸；生产默认不调用。
- `validate_coauthoring_collisions.mjs`：仅供 Skill 修改和发版回归；在最终 standalone 与真实 Chrome 指针事件中验证六枚 SVG 结构工具、顶部组件删除、四角等比缩放、墙厚输入、天花/吊灯图层、固定构件归一化，以及家具、门窗、墙体的统一碰撞规则、垂直墙例外、控制台与 WebGL 状态，不进入客户生产路径。
- `placement_height_guard.mjs`：供发版回归复用的组件高度与宿主空间/墙体计算模块，不作为生产阻断入口。
- `trace_shape_contract.mjs`：提供源轮廓与资产形态匹配的共享几何函数。
- `node_component_loader.mjs`：提供 Node 侧受管 GLB/组件加载函数。
- `model_scope_contract.mjs`：验证整屋与用户明确局部建模的同一范围合同。
- `validate_scene_rig.mjs`：验证相机与灯光交互状态，不拥有正式机位选择。
- `import_custom_component_package.mjs`：仅导入已验收的项目级产品组件包。
- `build_component_gallery_standalone.py`：生成资产人工审核画廊，不参与项目匹配。

只有真实身份冲突、输入损坏、核心浏览器无法启动或不可逆操作未获授权才形成流程停止。资产缺失时先完成正式资产准入再继续生成，不允许用色块绕过；布局风险和时间不在本 Skill 形成门禁。
