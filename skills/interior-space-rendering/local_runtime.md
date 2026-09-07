# 本地运行

```bash
python3 scripts/compile_render_request.py \
  --camera-facts camera/delivery/01-bedroom.json \
  --style modern=现代风 \
  --out-dir rendering/current

python3 ../imagegen-batch-orchestrator/scripts/manage_imagegen_batch.py \
  init rendering/current/imagegen.batch-plan.v1.json rendering/current/imagegen-run

python3 scripts/finalize_render_delivery.py \
  --request rendering/current/requests/01-bedroom-modern.imagegen-request.v5.json \
  --output-image rendering/current/outputs/01-bedroom-modern.png \
  --out rendering/current/delivery/01-bedroom-modern.render-delivery.v1.json \
  --advisory "如有画面问题，用自然语言如实说明"
```

脚本只做确定性编译与回执。真正生成图片使用当前环境的 ImageGen 能力；没有图片时不得伪造回执。
