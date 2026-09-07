# 数据合同

## 输入

`imagegen.batch-plan.v1`：

```json
{
  "schema": "imagegen.batch-plan.v1",
  "planId": "three-space-render",
  "sourceSkill": "interior-space-rendering",
  "sourcePlan": {"path": "render-plan.json", "sha256": "..."},
  "maxConcurrency": 5,
  "batches": [
    {"batchId": "independent-masters", "jobIds": ["dining", "living", "kitchen"]}
  ],
  "jobs": [
    {
      "jobId": "dining",
      "requestPath": "requests/dining.json",
      "requestSha256": "...",
      "dependencies": [],
      "outputFile": "dining.png",
      "maxAttempts": 3
    }
  ]
}
```

约束：

- `jobs` 与 `batches[].jobIds` 一一对应；每个 job 只出现一次。
- `maxConcurrency` 必须是 `1..5`；它只限制当前 running 的远端 ImageGen job。依赖批次仍优先于并发额度，不能用五路上限越过依赖。
- 依赖只能指向更早批次。
- `requestPath` 和 `sourcePlan.path` 可相对计划文件或使用绝对路径；初始化时必须与声明哈希一致。
- 每个 job 真正启动前再次核对 request 哈希；绑定后被移动、删除或改写的请求不得调用。
- 依赖不为空的 job 可把 `requestPath` 与 `requestSha256` 设为 `null`；依赖成功后由上游构建请求，再用 `bind-request` 原子绑定。
- `outputFile` 必须是 `outputs/` 下的相对文件名，不能逃逸运行目录。
- 计划不得包含 Chrome/Blender/CAD 截图命令；本机截图属于另一 Skill，设备级上限为 `2`。

## 运行目录

```text
run/
  plan.json
  run.json
  events.jsonl
  jobs/<jobId>.json
  outputs/<outputFile>
  imagegen.batch-receipt.v1.json
```

每个 job 独立保存 `queued | running | succeeded | failed`、尝试次数、时间、错误、输入哈希和输出哈希。运行环境提供调用 ID 或提供方请求 ID 时同步保存；没有该字段时保持 `null`，不能伪造。

若图片已由原尝试返回、仅本地结果适配失败，可在该 job 仍为 `failed + retryable`、尚无 accepted output 且提供原调用 ID 时接收 late result。该操作不增加 attempts，并沿用失败记录中的完成时间；它不是第二次 ImageGen 调用。

## 输出

`imagegen.batch-receipt.v1` 只有在全部 job 成功且输出文件仍与已保存大小、哈希一致后生成。它列出每个输出、尝试次数、开始结束时间、批次和依赖，并报告是否观察到真实时间重叠。回执一经生成即幂等；内容不变时重复 `finalize` 必须返回原文件。回执不代替上游的图片质量验收。
