# Local Runtime

```bash
node scripts/audit_component_runtime_geometry.mjs --asset-store "$INTERIOR_COMPONENT_ASSET_STORE" --out <audit.json> --module-out assets/component-library/catalog/runtime-geometry-admission.v1.js
node scripts/validate_component_library.mjs
node scripts/validate_public_asset_store.mjs --store "$INTERIOR_COMPONENT_ASSET_STORE"
node scripts/import_floorplan_handoff.mjs --handoff <handoff.json> --out <project>
node scripts/match_trace_components.mjs --trace <project>/trace-components.json --out <project>/component-layout.json --asset-store "$INTERIOR_COMPONENT_ASSET_STORE"
python3 scripts/build_standalone_html.py --project <project> --out <project>/preview-standalone.html
node scripts/export_native_model_manifest.mjs --html <project>/preview-standalone.html --handoff <handoff.json> --structure <project>/structure-data.json --components <project>/component-layout.json --model-scope <project>/model-scope.json --backend-options <project>/backend-options.json --out <project>/native-model-manifest.json
python3 scripts/collect_modeling_stage_timing.py --task-start <ISO-8601> --import-receipt <project>/floorplan-import-receipt.json --component-layout <project>/component-layout.json --asset-lock <project>/project-component-assets.lock.json --standalone <project>/preview-standalone.html --native-manifest <project>/native-model-manifest.json --out <project>/modeling-stage-timing.json

python3 scripts/import_returned_html.py --returned-html <user-returned.html> --canonical-html <workspace>/current.html --model-json <workspace>/current-model.json --receipt <workspace>/user-returned-html-receipt.json --expected-floorplan-id <floorplanId>
```

以上是唯一生产路径：首次直接生成可编辑 HTML；用户回传时原子覆盖唯一当前版。每个对象必须匹配并加载真实受管资产；资产缺口先补库再重跑，禁止生成色块。

以下命令只在修改 Skill 算法、组件库或准备发版时运行，不进入客户任务：

```bash
node scripts/import_floorplan_handoff.mjs --release-regression --handoff <handoff.json> --out <regression-project>
node scripts/validate_component_layout.mjs <regression-project>/component-layout.json <regression-project>/structure-data.json
node scripts/validate_component_geometry.mjs <regression-project>/component-layout.json
node scripts/validate_coauthoring_collisions.mjs <regression-project>/preview-standalone.html <regression-project>/collision-browser-acceptance
```

匹配器在一次事务中完成同类选择、方向校准、许可策略、资产物化和哈希锁定。正式布局不使用授权文件跨类，不拆成可遗忘的手工步骤。项目几何校验器会自行注册 Skill 内唯一 Node 模块解析器，调用方不得另加实验 loader；它只验证当前项目组件，全库许可与 GLB 准入由前三个发布审计命令负责。浏览器验收必须真实加载所有当前项目资产并检查桌面/移动端、WebGL、双材质和结构边界。原生清单同时登记测量与截图适配器：前者只把同一场景的 OBB 与可退距交给 Camera Skill，后者只执行 Camera Skill 已接受的计划；二者都不自行选角度。
