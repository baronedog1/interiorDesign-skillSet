# Script Logic

| 脚本 | 唯一职责 | 主要输出 |
|---|---|---|
| `model_scope_contract.mjs` | 从整屋/单空间请求确定性编译主空间、允许上下文和排除空间；禁止项目专用几何路径 | `model-scope.json` |
| `import_floorplan_handoff.mjs` | 验证并只读导入当前 handoff；整屋与单空间共用同一模板和组件链 | 项目模板、`model-scope.json` 与导入 receipt |
| `init_html_model_project.mjs` | 仅初始化空模板 QA 项目；正式项目不能绕过 handoff | 空白模板测试目录 |
| `build_functional_class_tags.mjs` | 从 canonical catalog 确定性生成每件资产允许承接的原子 `functionalClass` 与目录 digest；不读取项目做临时分类 | `functional-class-tags.v1.json` |
| `match_trace_components.mjs` | 先撤销模板/旧布局，按完全相等的原子 `functionalClass` 过滤，再按尺寸和明确风格证据择一；随后调用物化器，全部成功才原子提交资产锁与布局，禁止跨类别 fallback | `component-layout.json`、`component-assets.lock.json` |
| `materialize_component_assets.mjs` | 匹配器内部的资产落盘原语；从受管资产仓取当前 placement 使用的 GLB，并执行研究/商业/发布许可门禁，不作为可跳过的独立生产阶段 | `component-assets.lock.json` |
| `validate_component_library.mjs` | 校验成员清单、排除清单、canonical catalog、运行目录、标签、平台分类、沙发人数、实用椅例外和双外观 | JSON 审计 |
| `validate_public_asset_store.mjs` | 校验完整源码树、运行 GLB、逐文件哈希、inventory、未完成分片和失败数 | JSON 审计 |
| `validate_component_geometry.mjs` | 校验全部条目为外部真实网格、路径与来源唯一；分别核对来源描线脚印和用户明确新增组件 | JSON 审计 |
| `validate_component_layout.mjs` | 校验来源锁或用户复核调整、原子类别、数量、资产 ID、组件尺度策略、墙高、placement、边界、墙、开口和碰撞；只验证关系声明与引用，不重复计算贴墙、朝向或动线 | JSON 审计 |
| `apply_circulation_adjustment.mjs` | 复算 adjustment-plan.v2 与选中操作摘要，只写一个确定性 HTML active transform 和闭合证据，不覆盖用户显式修正 | 新 `component-layout.v4` 与零确认 receipt |
| `trace_shape_contract.mjs` | 从上游轮廓生成脚印哈希与度量 | 来源脚印事实 |
| `import_custom_component_package.mjs` | 导入已验收的项目单品 v3 包 | `custom-components/registry.json` |
| `validate_structure_data.py` | 核对 handoff 身份、结构和拓扑 | JSON 审计 |
| `validate_scene_rig.mjs` | 校验灯光与编辑相机合同 | JSON 审计 |
| `build_standalone_html.py` | 仅内联当前项目使用且满足 webStandalone 预算的 GLB 与项目数据；单资产、总资产和最终 HTML 超限时在写文件前退出 | 单文件 HTML，不超过 29MB |
| `build_component_gallery_standalone.py` | 构建明确 ID 或类别抽样展厅，不打包全库 | 抽样单文件 HTML |
| `export_native_model_manifest.mjs` | 将 accepted standalone HTML、model scope、哈希、能力、坐标变换和唯一截图适配器登记为跨后端清单 | `native-model-manifest.json` |
| `capture_html_views.mjs` | 仅作为正式机位调度器调用的后端适配器；在页面脚本前冻结外部 accepted camera plan v8，按 model scope 驱动同一 HTML 原生相机，验证最终矩阵并输出双模式、二维机位、Entity/Room ID、Depth、semantic frame 与统一 capture result；拒绝直接真实执行 | 原生截图证据 |
| `node_component_loader.mjs` | 为 Node 校验器提供与浏览器一致的组件模块解析 | 确定性模块加载 |
| `validate_template_ownership.py` | 确认唯一模板标记只属于本 Skill | JSON 审计 |

## 退出规则

- canonical catalog 与两个运行目录 ID 不完全一致：退出。
- 任一条目缺源码、许可、功能标签、平台分类、双外观或明确尺度策略：退出。
- 资产仓模型失败、任一源码依赖缺失、哈希漂移、存在未完成分片或 inventory 不完整：退出。
- `--commercial/--publish` 遇到 `commercialUseAllowed!=true`：退出；当前包括全部待许可复核的 ABO 条目。
- 自动匹配的普通组件宽深比例差超过 25% 时排除该候选；只有目录声明 `axis-limited` 的直线柜体可按各轴范围匹配。用户明确要求通用成品替换时，只有带 `authored-model-preserved` 视觉复核证据的显式路由可以保留 authored 比例。同一 `functionalClass` 内有多个合格资产时，按风格、尺寸、文本分数和稳定资产 ID 确定性择一，不询问用户；只有不存在同类合格资产时才报告具体缺口，整屋建模过程不得临时重建单品。
- placement 偏离 `sourcePosition/sourceRotationY` 但缺少闭合的用户权威或动线算法权威
  `interior.reviewed-layout-adjustment.v1`，摘要不一致，或存在两份 active transform 时退出。
- `relationHints` 缺少浏览器审阅方向轴、引用不存在的目标/墙体，或含任何距离、点积、净空、房间归属与通过结论时退出；贴墙、朝向、对象净距和通道是否合格只由后续 `interior-circulation-planning` 独立复算并放行。
- 普通组件碰撞一律退出；只有逐对登记且不超过深度上限的 `chair-tucked-under-table` 可以作为允许接触。
- `relationHints.spaceDividerMarkers[].required=true` 未引用真实 semantic divider、浏览器未生成对应地面标志，或项目因此改写 handoff 结构哈希时退出；不得用假墙代替。
- standalone 缺少 materialized GLB、单资产超过 `8MB`、当前项目原始资产合计超过 `18MB` 或最终 HTML 超过 `29MB`：退出；不得联网补取、内联全库或用方盒替代。
- `backend-options.json` 的天花、窗型、阳台围护、墙补丁或连续碰撞设置未真实物化，或 HTML 清单哈希与 standalone 不一致：退出。
- 预览缩略图缺失：记录 warning，不影响已经通过源码和 GLB 校验的资产。
