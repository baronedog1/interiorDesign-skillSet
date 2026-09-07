# Local Runtime

Ubuntu 生产 Python：

`/home/agentops/agent-runtime/runtimes/interior-camera-capture-39/bin/python`

唯一客户生产命令：

```bash
CHROME_BIN=/home/agentops/agent-runtime/bin/render-chrome \
  $CAMERA_PYTHON scripts/run_camera_pipeline.py \
  --html current.html --structure structure-data.json \
  --camera-intent camera/user-camera-intent.json \
  --out-dir camera --views-per-room 1 --viewport 1600x1000
```

Blender 原生模型：

```bash
$CAMERA_PYTHON scripts/run_camera_pipeline.py \
  --backend blender \
  --native-model current.blend \
  --camera-plan camera/canonical/camera-plan.json \
  --structure structure-data.json \
  --blender-skill /home/agentops/.codex/skills/interior-blender-modeling \
  --out-dir camera
```

Blender 截图器必须通过 `/home/agentops/agent-runtime/bin/blender` 进入渲染任务盒。CAD 使用相同入口和 `--backend cad`，并提供 CAD 原生 Skill 路径与 manifest。

VTK 渲染器只用于共同求解所需的 Entity-ID/Depth/RGB 计算。正式 HTML 截图必须通过 `render-chrome`，正式 Blender 截图必须通过 Blender 原生场景；两者都不得用 VTK 代理图替代客户图。
