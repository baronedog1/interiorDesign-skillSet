# 脚本职责

`scripts/manage_imagegen_batch.py` 是唯一状态管理入口：

- `init <plan> <run-dir>`：校验并冻结计划，建立独立 job 状态。
- `ready <run-dir>`：返回当前批次可启动 job，数量不超过剩余并发槽位；计划上限只允许 `1..5`。
- `bind-request <run-dir> <job-id> <request>`：依赖成功后绑定延迟生成的请求。
- `start <run-dir> <job-id>`：再次核对绑定请求文件与哈希，原子增加尝试次数并标记 running。
- `succeed <run-dir> <job-id> <image>`：原子复制图片、计算哈希并标记 succeeded。
- `fail <run-dir> <job-id> --reason <text> [--retryable]`：只标记当前 job。
- `recover <run-dir> --stale-seconds <n>`：把超时 running job 转为可重试 failed。
- `status <run-dir>`：汇总状态。
- `finalize <run-dir>`：再次核对全部输出文件、大小和哈希后生成批次回执；重复调用返回同一回执，不改写时间或摘要。

所有状态写入使用文件锁和原子替换。未完成的较早批次会阻止后续批次，不能因单项永久失败而跳批。脚本不调用 ImageGen；Codex 在 `ready` 之后调用内置图片工具，并逐 job 回写结果。五路 ImageGen 并发不承担本机截图；截图的两路设备限流由机位 Skill 单独实现。
