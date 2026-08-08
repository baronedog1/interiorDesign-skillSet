# Local Runtime

正式入口读取 `CHROME_BIN` 与 `INTERIOR_COMPONENT_ASSET_STORE`；下文 Ubuntu 路径只作示例。浏览器和资产仓必须由管理员预装/同步，任务不得下载或从其它设备借用。

- Node.js 20+
- Python 3.10+
- Google Chrome/Chromium
- Ubuntu 公共资产仓（默认 `/home/agentops/agent-runtime/shared-assets/interior-component-library-v5`）
- Blender 或等价 glTF 工具仅用于源码可编辑性抽样
- Three.js、OrbitControls 与 GLTFLoader 已内置，不使用 CDN

```bash
node scripts/validate_component_library.mjs
node scripts/validate_public_asset_store.mjs --store "$INTERIOR_COMPONENT_ASSET_STORE"
node --experimental-loader ./scripts/node_component_loader.mjs ./scripts/validate_component_geometry.mjs
node scripts/import_floorplan_handoff.mjs --handoff <handoff>/floorplan-handoff.json [--model-scope <scope-request.json>] --out <project>
node scripts/match_trace_components.mjs --trace <project>/trace-components.json --out <project>/component-layout.json [--commercial|--publish]
node scripts/validate_component_layout.mjs <project>/component-layout.json <project>/structure-data.json
node scripts/validate_scene_rig.mjs <project>/scene-rig.json
python3 scripts/build_standalone_html.py --project <project> --out <project>/preview-standalone.html
python3 scripts/build_component_gallery_standalone.py --project <project> --component-ids <id1,id2> --out <project>/component-sample.html
node scripts/export_native_model_manifest.mjs --html <project>/preview-standalone.html --handoff <project>/floorplan-handoff/floorplan-handoff.json --structure <project>/structure-data.json --components <project>/component-layout.json --model-scope <project>/model-scope.json --backend-options <project>/backend-options.json --capture-adapter scripts/capture_html_views.mjs --out <project>/native-model-manifest.json
node scripts/capture_html_views.mjs --model-manifest <project>/native-model-manifest.json --shots-manifest <project>/camera-plan.v8.json --out-dir <project>/capture-dry-run --dry-run
```

正式结构只由 importer 核对一次。匹配器在一次事务中完成同类资产选择、许可策略、项目物化、哈希锁定和正式布局提交；不得把匹配与物化拆成可遗忘的两个生产步骤。公共目录浏览器验收至少覆盖所有类别、两个来源和绿/紫分区；每个抽样资产要真实加载，白模/源色不同但几何相同。

项目浏览器验收必须使用真实 DOM 事件，不以直接调用编辑 API 代替：

1. 桌面平面和三维分别进入一次，确认 Orbit target 的 X/Z 精确等于户型边界中心。首次点击预览后记录 320×180 离屏帧指标；拖动右下角手柄，确认显示尺寸变化、比例仍为 16:9 且 render target 不变。
2. 在自由三维中用真实鼠标分别单击、双击并直接拖动相机和光源，确认选择 ID、场景坐标和预览签名同步变化。
3. 点击空白位置后确认选择为 `none`；按方向键后主相机与 target 同步平移、二者向量不变。再切换页签和视图，确认预览仍可见并继续更新。
4. 运行 `validate_component_layout.mjs` 并核对 `relationHintIssues=[]`、未授权碰撞为空；方向轴和目标引用必须完整，但餐椅朝桌、床头贴墙、沙发贴墙及通道净空的正式结论只能读取后续动线审计。
5. 桌面和 390×844 移动端都检查控制台、页面错误、WebGL context loss、横向溢出和主画布/预览画布非空。
6. 有 `relationHints.spaceDividerMarkers[].required=true` 的开放空间分界必须在平面和三维都可见；marker 只引用真实 semantic divider，结构 handoff 哈希保持不变，标志不改变拓扑和碰撞。
7. 上述直接适配器命令仅允许 `--dry-run`。正式截图必须改由 `interior-camera-capture/scripts/capture_model_views.py --structure ...` 调度；每个 record 必须为 `runtimeCameraPlanSource=external-formal-camera-plan-v8`。第三象限 JSON 的后端、模型哈希、position、target、FOV 和 `mustShowElements` 必须与外部 plan 完全一致。使用内嵌历史计划、事后补字段、绕过设备压力门或 Chrome profile 清理失败均视为截图失败。

上传与社区发布只交给 `idk-canvas-ingest-agent`。当前 ABO 组件因官网与 AWS Registry 许可标注冲突，商业和社区发布门禁必须拒绝；人工复核完成前不得只凭 CC BY 文件自动放行。
