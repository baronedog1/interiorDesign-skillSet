# Local Runtime

解释器以设备 runtime inventory 为准；Python、Pillow、NumPy、OpenCV 必须由管理员预装并固定，任务不得临时 `pip install`。

- Python 3.10+
- Pillow
- OpenCV (`cv2`)
- NumPy

```bash
python3 scripts/build_wall_geometry.py --help
python3 scripts/render_floorplan_quadrants.py --help
python3 scripts/validate_source_model.py --help
python3 scripts/finalize_floorplan_handoff.py --help
```

正式项目只运行这一条事实链。语义由 Agent 看源图后写入，代码负责几何和量尺；任何失败都回到源证据或语义判断修正。

平台入库不属于本 Skill runtime。用户要求上传时，将 accepted 图片和 `assetKind` 交给 `/home/agentops/.codex/skills/idk-canvas-ingest-agent`，并复用项目根目录的 `baiende-project.json`。
