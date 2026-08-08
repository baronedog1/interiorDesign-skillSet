# 本地运行

使用当前设备的 Python、原生 `imagegen` 和任务工作区；无固定设备路径，不读取图像 API Key，也不在任务中安装模型工具。

```bash
python3 scripts/build_projection_lock.py \
  living-frontal.scene-map.json living-frontal.projection-lock.json

python3 scripts/build_scene_prompt_context.py \
  render-plan.v11.json living-frontal modern-minimal "现代简约" \
  living-frontal.render-context.json

python3 scripts/build_prompt_manifest.py \
  living-frontal.render-context.json living-frontal.scene-map.json \
  living-frontal.prompt-manifest.json \
  --model IMAGE_MODEL --parameters-json '{"size":"1536x1024"}'

python3 scripts/build_imagegen_request.py \
  living-frontal.prompt-manifest.json living-frontal.request.json \
  --generation-invocation-id GENERATION_ID

python3 scripts/validate_render_plan.py render-plan.v11.json

python3 scripts/build_imagegen_batch_plan.py \
  render-plan.v11.json imagegen.batch-plan.v1.json \
  --request living-frontal=./living-frontal.request.json \
  --max-concurrency 5

python3 ../imagegen-batch-orchestrator/scripts/manage_imagegen_batch.py \
  init imagegen.batch-plan.v1.json imagegen-run

python3 ../imagegen-batch-orchestrator/scripts/manage_imagegen_batch.py \
  ready imagegen-run

python3 scripts/build_four_quadrant_delivery.py \
  --scene-map living-frontal.scene-map.json \
  --request living-frontal.request.json \
  --receipt living-frontal.receipt.json \
  --review living-frontal.review.json \
  --room-name 客厅 --out living-frontal-four-quadrant.png

python3 scripts/validate_render_plan.py \
  render-plan.v11.json --require-complete
```

图像模型调用由 `imagegen-batch-orchestrator` 编排，运行环境负责真正调用；两个 Skill 都不保存 API Key。`--max-concurrency` 只允许 `1..5`，默认 `5`，但依赖 job 不会提前释放。该远端 ImageGen 并发与机位截图的本机上限 `2` 无关。每个 job 成功即独立落盘并记录回执，批次使用 all-settled 语义，只重试失败 job。三个候选均失败时停止并明确不交付 Q4，原生后端截图不得回退为渲染图。只有最后一条 `--require-complete` 命令成功，任务才可对外标记为完整渲染交付。
