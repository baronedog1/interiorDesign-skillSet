# Ubuntu 本地运行

所有 Blender 调用必须经过 `/home/agentops/agent-runtime/bin/blender` 渲染盒入口。

```bash
python3 scripts/acquire_blenderkit_assets.py --request assets/blender-component-library/precision-asset-acquisition.v1.json --out-root /home/agentops/agent-runtime/shared-assets/blender-interior-research/precision-v2 --manifest assets/blender-component-library/acquisition-manifest.v1.json --client-bin <reviewed-blenderkit-client>

python3 scripts/acquire_polyhaven_materials.py --request assets/blender-material-library/material-acquisition.v1.json --out-root /home/agentops/agent-runtime/shared-assets/blender-interior-research/materials-v1 --manifest assets/blender-material-library/acquisition-manifest.v1.json

python3 scripts/init_blender_model_project.py --model current-model.json --structure structure-data.json --blender-catalog assets/blender-component-library/catalog.json --material-catalog assets/blender-material-library/catalog.json --style-preset assets/blender-style-presets/warm-modern-neutral.json --template-options assets/blender-template/backend-options.json --out project

/home/agentops/agent-runtime/bin/blender --background --factory-startup --python-exit-code 1 --python scripts/build_floorplan_scene.py -- --model current-model.json --structure structure-data.json --blender-catalog assets/blender-component-library/catalog.json --material-catalog assets/blender-material-library/catalog.json --style-preset assets/blender-style-presets/warm-modern-neutral.json --backend-options assets/blender-template/backend-options.json --out-blend model/current.blend --out-glb model/current.glb --out-report reports/build-report.json

python3 scripts/capture_blender_batch.py --blend model/current.blend --camera-plan camera-plan.json --adapter scripts/capture_blender_views.py --out-dir camera --viewport 960x600
```

资产获取只允许显式审过的免费 ID，受限资产立即停止，不复制登录态。设备盒默认 `MemoryHigh=6G/MemoryMax=7500M/MemorySwapMax=1G`。禁止为完成截图提高限额；批处理通过“单图进程＋目标房间剪枝”释放内存并保留 Eevee 材质渲染。
