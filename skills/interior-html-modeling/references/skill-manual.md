# 室内户型人机共创 HTML 建模 说明书（AI 读取版）

版本：34.0.0

## YAML 头

```yaml
---
name: interior-html-modeling
description: 当用户要求把已编译户型快速生成可编辑 HTML/Three.js 整屋模型，或在 AI 初稿上直接调整墙、门窗、精细家具、摄像机与灯光时使用。未明确要求 Blender/CAD 时，本 Skill 是默认建模后端。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"model_backend":"html-threejs","floorplan_handoff_schema":"interior.floorplan-handoff.v3","structure_schema":"interior.floorplan-structure.v4","component_layout_schema":"interior.component-layout.v5","native_model_manifest_schema":"interior.native-model-manifest.v1","version":"34.0.0"}
---
```

## 思路


## 调用场景

1. **把已编译户型生成只有真实资产的可编辑整屋 HTML**：当用户提供已经编译好的户型结构，或者把自己修改后的当前 HTML 发回来时，就进入这一条流程。系统先确认项目身份和当前版本，再删除模板自带的示例模型，避免把其它户型家具混进来。每件家具都按规范化后的同功能类别从受管库选择真实 GLB，绿色或紫色只表示编辑方式，不再阻止同功能资产匹配。地毯、台灯、书桌等必须显示真实网格并可调整尺寸和方向；找不到资产时先补入正式资产再继续，绝不交付色块。模型编译后生成一个自包含 HTML，用户可直接修改墙门窗和家具，保存后把新 HTML 发回，系统原子覆盖项目唯一当前版。 输入：同一户型版本的 floorplan-handoff.v3，或由唯一模板保存并回传的当前 HTML 输出：真实资产 component-layout、当前 coauthoring model、自包含可编辑 HTML、原生模型清单和回传接收回执

## 完整文件

当前文件数：73

- `ENVIRONMENT_CONTRACT.md`：说明共享源、Ubuntu 运行副本、资产仓和浏览器环境。
- `MANIFEST.json`：登记版本、正式文件和摘要。
- `SKILL.md`：定义触发条件、唯一 HTML 产品、精确资产和交付边界。
- `SKILL_MANUAL.pdf`：给普通人阅读的 A3 图文说明书。
- `agents/openai.yaml`：提供 Codex 默认调用提示。
- `assets/component-library/catalog/directional-axis-tags.v1.json`：登记有方向资产的局部轴。
- `assets/component-library/catalog/functional-class-tags.v1.json`：登记每件资产支持的功能类别。
- `assets/component-library/catalog/platform-taxonomy.json`：保存组件平台分类枚举。
- `assets/component-library/catalog/public-asset-selection.json`：保存公共资产精确成员清单。
- `assets/component-library/catalog/public-assets.json`：作为公共资产目录唯一事实源。
- `assets/component-library/catalog/runtime-geometry-admission.v1.js`：登记已准入和排除的运行几何。
- `assets/component-library/catalog/source-asset-exclusions.json`：保存明确排除的来源资产。
- `assets/component-library/component-library.js`：加载真实 GLB、调整尺寸并切换外观。
- `assets/component-library/fixed-purple/catalog.js`：提供固定和安装类资产目录。
- `assets/component-library/fixtures/match-fixture.json`：提供匹配算法的离线测试样本。
- `assets/component-library/gallery/explorer.js`：实现组件展厅浏览交互。
- `assets/component-library/gallery/index.html`：提供组件展厅页面。
- `assets/component-library/gallery/styles.css`：提供组件展厅样式。
- `assets/component-library/index.js`：汇总公共组件目录出口。
- `assets/component-library/movable-green/catalog.js`：提供活动家具资产目录。
- `assets/component-library/shared/library-contract.js`：声明组件库共同字段合同。
- `assets/component-library/shared/placement-geometry.js`：提供家具放置和碰撞几何函数。
- `assets/interior-coauthoring-template/coauthoring-model.js`：提供唯一模板直接打开时的无色块示例模型。
- `assets/interior-coauthoring-template/coauthoring-model.json`：保存同一示例模型的结构化数据。
- `assets/interior-coauthoring-template/index.html`：实现唯一室内户型人机共创编辑器。
- `assets/interior-coauthoring-template/vendor/exporters/GLTFExporter.global.js`：提供离线 GLTF 场景导出。
- `assets/interior-coauthoring-template/vendor/loaders/GLTFLoader.js`：提供离线 GLB 加载。
- `assets/interior-coauthoring-template/vendor/three.module.js`：提供离线 Three.js 运行库。
- `assets/interior-coauthoring-template/vendor/utils/BufferGeometryUtils.js`：提供离线几何合并工具。
- `data_contract.md`：规定户型、组件布局、当前 HTML 和回传覆盖对象。
- `local_runtime.md`：列出 Ubuntu 唯一正式命令。
- `playbook.md`：说明从户型导入到用户回传的连续工作方法。
- `references/annotation-and-measurement-method.md`：解释标注与测量显示方法。
- `references/backend-architectural-options.md`：说明 HTML 与其它建模后端的职责边界。
- `references/furniture-component-system.md`：规定公共精细家具来源、网格和尺寸能力。
- `references/furniture-placement-method.md`：规定家具方向、位置和碰撞关系。
- `references/scene-light-camera-method.md`：说明编辑器灯光、相机与正式机位桥。
- `references/sidebar-function-contract.md`：规定结构、组件和场景侧栏交互。
- `references/skill-flowchart.svg`：提供同源流程总览图。
- `references/skill-manual.json`：作为说明书唯一结构化事实源。
- `references/skill-manual.md`：给 AI 阅读的同源说明书。
- `references/structure-and-window-method.md`：规定墙、门窗和二维三维编辑行为。
- `references/trace-to-component-matching.md`：解释描线对象怎样匹配真实资产。
- `references/white-model-contrast-system.md`：说明白模与源色外观切换。
- `scripts/audit_component_runtime_geometry.mjs`：审计全部公共 GLB 的真实运行几何。
- `scripts/build_component_gallery_standalone.py`：生成组件库浏览展厅。
- `scripts/build_functional_class_tags.mjs`：生成资产功能类别标签。
- `scripts/build_standalone_html.py`：内联当前模型和实际使用资产，生成单文件 HTML。
- `scripts/capture_html_views.mjs`：按外部冻结计划截取 HTML 原生视图。
- `scripts/collect_modeling_stage_timing.py`：汇总 HTML 建模各阶段用时。
- `scripts/compile_coauthoring_model.mjs`：编译当前项目唯一 Three.js 模型。
- `scripts/export_native_model_manifest.mjs`：登记当前原生模型和适配器摘要。
- `scripts/import_custom_component_package.mjs`：导入通过准入的定制组件包。
- `scripts/import_floorplan_handoff.mjs`：导入户型并清除模板示例模型。
- `scripts/import_returned_html.py`：接收用户修改后的 HTML 并原子覆盖当前版。
- `scripts/init_html_model_project.mjs`：创建只使用唯一模板的新项目。
- `scripts/match_trace_components.mjs`：规范类别、选择真实 GLB、校准尺寸方向并物化资产。
- `scripts/materialize_component_assets.mjs`：只复制当前项目实际使用的资产。
- `scripts/measure_html_camera_envelopes.mjs`：向机位 Skill 暴露当前模型包络。
- `scripts/model_scope_contract.mjs`：编译整屋或明确局部建模范围。
- `scripts/node_component_loader.mjs`：让 Node 校验器读取组件库模块。
- `scripts/placement_height_guard.mjs`：限制柜体和固定构件垂直位置。
- `scripts/trace_shape_contract.mjs`：规范来源家具轮廓与碰撞脚印。
- `scripts/validate_coauthoring_collisions.mjs`：在真实浏览器回归碰撞与直接编辑。
- `scripts/validate_component_geometry.mjs`：验证全部 placement 都有真实网格和来源脚印。
- `scripts/validate_component_layout.mjs`：验证匹配、尺寸、方向、预算和关系。
- `scripts/validate_component_library.mjs`：验证公共组件目录与几何合同。
- `scripts/validate_public_asset_store.mjs`：验证 Ubuntu 资产仓文件与摘要。
- `scripts/validate_scene_rig.mjs`：验证灯光和场景相机数据。
- `scripts/validate_structure_data.py`：在发版回归中验证户型结构。
- `scripts/validate_template_ownership.py`：确认只有一个活动 HTML 模板。
- `scripts_logic.md`：登记所有确定性脚本的职责。
- `templates.md`：索引唯一模板和组件库。

## 具体逻辑解释

### 描线对象怎样只匹配真实资产

这一页解释为什么绿色紫色不再切断同功能资产，以及地毯、书桌和台灯怎样避免变成色块。

匹配器先规范功能类别，只把 area-rug、floor-rug 和 carpet 合并为同一个 rug；其它类别保持严格一致。然后在全受管库查找同功能资产，绿色或紫色只继续控制对象是否可移动和安装，不再限制物理资产来自哪个目录。缺少方向标签的普通书桌仍使用来源旋转，不会被错误排除。所有胜出对象都必须具有 componentId、真实 GLB、尺寸和资产锁；没有候选时输出精确缺口并补库后重跑，页面没有任何色块渲染通路。

- 输入：家具描线对象；公共资产目录；Ubuntu 资产仓
- 核心规则：规范登记过的功能同义词；全库只选同功能真实资产；编辑语义与物理分区分离；尺寸方向和资产摘要一并锁定
- 失败处理：没有真实同类资产时列出缺口并补库后重跑，禁止生成色块。
- 验收证据：component-layout 中 matched 数等于 placement 总数，unmatched 为零且每件 componentId 都能加载真实网格。

### 唯一编辑器怎样保持真实资产可编辑

这一页解释真实 GLB 加载、尺寸方向调整、碰撞和用户保存回传怎样共用同一模型。

编辑器只渲染真实 GLB，隐藏的来源 footprint 仅参与碰撞，不能作为资产加载完成证据。全部 GLB 真正 settled 后才把 ready 设为真；任一对象 unmatched 或加载失败都会留下明确错误而不会画出色块。组件宽、深、高可以按当前对象调整，四角手柄继续做等比例缩放，地毯可按平面尺寸独立适配并保持薄层。用户保存时把当前完整模型写回 HTML，回传后只覆盖项目唯一 current.html 和 current-model.json。

- 输入：当前 coauthoring model；已物化真实 GLB；用户鼠标和数值编辑
- 核心规则：真实网格加载后才算完成；来源 footprint 只做碰撞；尺寸方向编辑共用一个模型；保存回传原子覆盖当前版
- 失败处理：真实资产加载失败时报告具体对象并修资产或加载器，不显示替代色块。
- 验收证据：浏览器状态 rendered 等于 furniture total、failed 和 unmatched 都为零，控制台和 WebGL 错误为零。


完整真实分支、回退路径和文件节点见根目录 `SKILL_MANUAL.pdf`。
