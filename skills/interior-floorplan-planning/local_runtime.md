# Local Runtime

- Python 3.10+
- Pillow
- OpenCV (`cv2`)
- NumPy

```bash
python3 scripts/build_wall_geometry.py --help
python3 scripts/render_floorplan_quadrants.py --help
python3 scripts/validate_source_model.py --help
python3 scripts/finalize_floorplan_handoff.py --help
python3 scripts/compile_floorplan_handoff.py --help
python3 scripts/test_orientation_contract.py
python3 scripts/test_source_pixel_audit.py
```

正式项目只运行一条当前生产事实链：`图片候选定位 -> Agent 分类 -> compile_floorplan_handoff.py 直接编译尺寸/拓扑/对象 -> coauthoring handoff`。编译器把坐标、几何、量尺和拓扑合并在同一次生成中，直接交给 HTML；不在生成后重复运行强校验阻断客户任务。用户在 HTML 中校正后再形成正式 revision。

只有修改编译算法或准备发版时才运行：

```bash
python3 scripts/compile_floorplan_handoff.py --release-regression --source <source.png> --source-model <source-model.json> --out <regression-output>
python3 scripts/test_orientation_contract.py
python3 scripts/test_source_pixel_audit.py
```

回归失败说明算法需要修正；修正并通过真实案例后才能发布。不得把失败留给生产任务，也不得在生产入口继续堆门禁。

平台入库不属于本 Skill runtime。用户要求上传时，将 accepted 图片和 `assetKind` 交给 `/home/agentops/.codex/skills/idk-canvas-ingest-agent`，并复用项目根目录的 `baiende-project.json`。
