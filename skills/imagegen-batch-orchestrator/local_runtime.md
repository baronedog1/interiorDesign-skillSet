# 本地执行

使用当前设备的 Python 3.10+ 和任务工作区；无固定设备路径。运行前先确认原生 `imagegen` 可用和 run 目录可写，不在任务中安装依赖。

```bash
python3 scripts/manage_imagegen_batch.py init batch-plan.json run
python3 scripts/manage_imagegen_batch.py ready run
python3 scripts/manage_imagegen_batch.py bind-request run relation-shot requests/relation-shot.json
python3 scripts/manage_imagegen_batch.py start run dining
python3 scripts/manage_imagegen_batch.py succeed run dining /path/to/generated.png
python3 scripts/manage_imagegen_batch.py finalize run
```

Codex 对 `ready` 返回的 job 发起独立 `imagegen` 调用。并发分支必须各自捕获结果并立即执行 `succeed` 或 `fail`；批次聚合只能采用 `allSettled` 语义。

计划 `maxConcurrency` 只允许 `1..5`。默认业务计划可设为 `5`，但 `ready` 只释放依赖已满足且未超过剩余槽位的 job。本 Skill 不启动本机截图进程；模型截图由 `interior-camera-capture` 在设备压力门后最多两路运行。

中断恢复：

```bash
python3 scripts/manage_imagegen_batch.py recover run --stale-seconds 900
python3 scripts/manage_imagegen_batch.py ready run
```

不要删除运行目录后重跑整批，也不要覆盖已经成功的输出。
