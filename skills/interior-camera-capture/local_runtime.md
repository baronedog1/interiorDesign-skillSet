# Local Runtime

公共依赖：Python 3.10+。原生截图运行时由模型清单声明：

- HTML：Node.js 20+、Chrome/Chromium、WebGL2。
- Blender：清单登记的 Blender LTS 与 `BLENDER_BIN`。
- CAD：清单登记的 STEP/CAD snapshot renderer 与 `INTERIOR_CAD_SNAPSHOT_COMMAND`。

语法检查：

```bash
python3 -m py_compile scripts/*.py
```

正视主种子求解：

```bash
python3 scripts/solve_frontal_camera_seeds.py \
  --structure structure-data.json \
  --scene circulation-scene.json \
  --circulation-result circulation-result.json \
  --native-manifest native-model-manifest.json \
  --out camera-frontal-seeds.json
```

同一输入重复运行必须得到相同 `seedSetDigestSha256`。该步骤是代码算法，不等待用户选角度。

原生适配器一次写出所有 seed 的 OBB 八角点包围范围与可退距后，批量编译候选：

```bash
python3 scripts/compile_camera_candidates.py \
  --seeds camera-frontal-seeds.json \
  --measurements native-camera-envelope-measurements.json \
  --out camera-candidate-batch.json
```

同一 seed set 与 measurement digest 必须产生同一 `batchDigestSha256`；camera plan 只能复制并绑定该 batch 的候选，不能逐空间手工重算。

绑定正视种子后的计划验收：

```bash
python3 scripts/validate_camera_manifest.py \
  camera-plan.json native-model-manifest.json structure-data.json
```

统一截图：

```bash
python3 scripts/capture_model_views.py \
  --model-manifest native-model-manifest.json \
  --camera-plan camera-plan.json \
  --structure structure-data.json \
  --out captures
```

`--prepare-only` 只检查调度并生成作业，不构成 accepted 截图。正式交付必须让原生适配器真实运行并返回 `accepted=true`。真实适配器不得直接执行：正式入口会先运行 camera validator 和设备压力门，并通过 `/tmp/interior-capture-slots-v1` 保证整机最多 `2` 个截图作业；每个 HTML 作业只启动一个 Chrome 并顺序拍摄其 shots。

语义栅格最大宽度固定为 800px。设备压力不合格时停止并保存证据；不能绕过正式入口、提高截图并发、改用二维包围盒、凸包或图片识别作为正式证据。截图上限 `2` 与 `imagegen-batch-orchestrator` 的远端生成上限 `5` 相互独立。

平台入库不属于本 Skill；accepted 文件交给 `idk-canvas-ingest-agent`。
