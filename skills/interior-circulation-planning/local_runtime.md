# 本地命令

```bash
python3 scripts/audit_user_returned_html.py \
  --model /path/to/current-model.json \
  --out /path/to/circulation-result.json
```

验收重点：结果可读、风险去重、`blocking=false`、`cameraWorkflowAllowed=true`，且模型摘要在运行前后不变。
