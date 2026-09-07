# 本地执行

```bash
python3 scripts/manage_imagegen_batch.py init batch-plan.json run
python3 scripts/manage_imagegen_batch.py ready run
python3 scripts/manage_imagegen_batch.py bind-request run relation-shot requests/relation-shot.json
python3 scripts/manage_imagegen_batch.py start run dining
python3 scripts/manage_imagegen_batch.py succeed run dining /path/to/generated.png
python3 scripts/manage_imagegen_batch.py succeed run dining /path/to/already-returned.png --invocation-id imagegen-call-1 --late-result
python3 scripts/manage_imagegen_batch.py finalize run
```

Codex 对 `ready` 返回的 job 发起独立 `imagegen` 调用。并发分支必须各自捕获结果并立即执行 `succeed` 或 `fail`；批次聚合只能采用 `allSettled` 语义。

原生绘图工具的 `output_hint` 可能是一段包含实际路径的说明文字。调用层先提取并验证其中真实存在的图片文件；若图片已成功返回而落盘适配失败，使用 `--late-result` 接收同一次调用结果，保留原 `startedAt`、`finishedAt` 和尝试次数，禁止重新生图。

计划 `maxConcurrency` 只允许 `1..5`。默认业务计划可设为 `5`，但 `ready` 只释放依赖已满足且未超过剩余槽位的 job。本 Skill 不启动本机截图进程；模型截图由 `interior-camera-capture` 在设备压力门后最多两路运行。

中断恢复：

```bash
python3 scripts/manage_imagegen_batch.py recover run --stale-seconds 900
python3 scripts/manage_imagegen_batch.py ready run
```

不要删除运行目录后重跑整批，也不要覆盖已经成功的输出。
