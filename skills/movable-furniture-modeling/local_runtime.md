# 本地运行

浏览器读取 `CHROME_BIN`，Python/Node 读取设备 runtime inventory；依赖必须由管理员预装，任务不得运行 pip/npm/browser 下载。

要求 Python 3、Pillow、NumPy、OpenCV、jsonschema、Node.js、Google Chrome 和本地 Three.js。

```bash
python3 scripts/extract_view_regions.py top-segmentation-job.json top-view-region-evidence.json
python3 scripts/validate_view_regions.py top-view-region-evidence.json
python3 scripts/carve_visual_hull.py carving-plan.json visual-hull-state.json
python3 scripts/compare_view_projection.py carving-plan.json visual-hull-state.json projection-report.json
python3 scripts/build_product_standalone.py visual-hull-state.json product-standalone.html
python3 scripts/build_component_package.py carving-plan.json visual-hull-state.json projection-report.json product-standalone.html product-browser-qa.json component-package.json --package-id <id> --placement-class movable-green
python3 tests/test_visual_hull_pipeline.py
python3 scripts/validate_package.py .
```

浏览器必须验收桌面与手机、源/正/侧/顶/背、逐组件显示、同一几何的白模/源色、Orbit、非空画布、控制台错误
和 WebGL loss，并写出符合 `product-browser-qa.schema.json` 的哈希绑定结果。低清源图可以保持比例单位，
但提供视图的逻辑投影仍需零异或。
