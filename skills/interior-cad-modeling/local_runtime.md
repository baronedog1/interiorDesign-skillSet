# 本地运行

正式命令读取 `CAD_PYTHON_BIN`、`INTERIOR_CAD_ASSET_STORE` 与 `INTERIOR_CAD_SNAPSHOT_COMMAND`；下文路径只作示例，任务不得自行安装或替换 runtime。

运行条件：Python 3.11+、build123d 0.11.x、OpenCascade/OCP、CAD snapshot renderer。环境变量：

- `CAD_PYTHON_BIN=/home/agentops/agent-runtime/bin/cad-python`；Ubuntu 正式构建唯一入口，进入 `cad-heavy` 渲染任务盒子。
- `INTERIOR_CAD_ASSET_STORE=/home/agentops/agent-runtime/workspaces/interior-design-2/cad-asset-library`
- `INTERIOR_CAD_SNAPSHOT_COMMAND`：接收 `--job <json>` 的原生 CAD renderer 命令。

标准顺序：

```bash
"$CAD_PYTHON_BIN" scripts/init_cad_model_project.py --handoff floorplan-handoff.json --options assets/interior-cad-template/backend-options.json --out project
"$CAD_PYTHON_BIN" scripts/validate_asset_selection.py --handoff floorplan-handoff.json --selection cad-asset-selection.json --catalog assets/cad-component-library/residential-catalog-v3.json --asset-store "$INTERIOR_CAD_ASSET_STORE" --report selection-validation.json
"$CAD_PYTHON_BIN" scripts/apply_circulation_adjustment.py --plan circulation-adjustment-plan.json --existing native-layout-overrides.json --out native-layout-overrides.next.json
"$CAD_PYTHON_BIN" scripts/build_cad_floorplan.py --handoff floorplan-handoff.json --selection cad-asset-selection.json --catalog assets/cad-component-library/residential-catalog-v3.json --asset-store "$INTERIOR_CAD_ASSET_STORE" --options assets/interior-cad-template/backend-options.json --out-step project/model/floorplan.step --out-report project/reports/build.json --out-entities project/model/entity-index.json
"$CAD_PYTHON_BIN" scripts/export_native_model_manifest.py --report project/reports/build.json --adapter scripts/capture_cad_views.py --out project/model/native-model-manifest.json
```

有 override 时向构建命令增加 `--layout-overrides native-layout-overrides.json`。生成机位截图时，
`capture_cad_views.py` 只接受同 STEP 哈希的 `camera-plan.v8`。
