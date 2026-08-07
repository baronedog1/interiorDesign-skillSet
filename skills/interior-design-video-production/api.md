# Seedance / Ark API 合同

## 请求边界

- 默认根地址：`https://ark.cn-beijing.volces.com/api/v3`
- 根地址可由 `SEEDANCE_VIDEO_API_BASE_URL` 覆盖，但必须是 HTTPS。
- 创建任务：`POST /contents/generations/tasks`
- 查询任务：`GET /contents/generations/tasks/{taskId}`
- 鉴权：`Authorization: Bearer ${VOLCENGINE_ARK_API_KEY}`
- 请求与响应为 JSON。

本 Skill 只允许以上创建和查询路径。平台项目、社区发布、资产库写入和其它付费
接口不属于该 API 客户端。

## 生成请求

创建请求的核心字段：

```json
{
  "model": "doubao-seedance-2-0-260128",
  "content": [
    {
      "type": "text",
      "text": "从已确认分镜编译的完整提示词"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "https://cdn.example/storyboard.png"
      },
      "role": "reference_image"
    }
  ],
  "resolution": "720p",
  "ratio": "16:9",
  "duration": 8,
  "generate_audio": true,
  "watermark": false
}
```

约束：

- 单片段时长限制为 5-15 秒；更长视频必须拆分。
- 支持比例：`16:9`、`9:16`、`1:1`、`4:3`、`3:4`。
- 第一段可使用 storyboard、当前方案图和全局镜头参考。
- 第二段起只使用上一段 provider 视频继续延长；不重新加入外部空间参考。
- 全局参考视频总时长不超过 15 秒；每个参考方面只允许一个主参考。
- 人物模式必须同时在提示词与请求体记录真实人物资产字段。

## 任务状态

脚本兼容以下成功状态：

- `succeeded`
- `success`
- `completed`
- `done`

以下状态立即失败：

- `failed`
- `failure`
- `error`
- `cancelled`
- `canceled`
- `expired`

其它状态按 `SEEDANCE_VIDEO_POLL_INTERVAL_MS` 轮询，最多
`SEEDANCE_VIDEO_MAX_POLLS` 次。超时、失败或下载错误都会停止整个串行任务。

## Dry-run

dry-run 只编译请求并写入 generation manifest：

- 不读取 `VOLCENGINE_ARK_API_KEY`
- 不发送 HTTP 请求
- 不轮询
- 不下载视频
- 明确列出片段数、模型、每段时长、素材、依赖关系和预计费用

## 零费用鉴权预检

真实生成前必须先用同一凭据执行：

`GET /contents/generations/tasks/codex-auth-probe-<timestamp>-not-a-real-task`

- 预期返回不存在任务的 `404` 或其它非鉴权 `4xx`，证明网络和 Bearer 凭据可用。
- `401/403` 视为凭据失效，立即停止。
- 该检查绝不发送 `POST`，因此 `createdTask=false`、`costIncurringRequest=false`。
- `generate_seedance_video_from_storyboard.mjs` 在首次付费创建前自动执行相同预检。

## 真实执行

真实执行必须同时满足：

1. 命令包含 `--execute --confirm-paid-generation`。
2. `VOLCENGINE_ARK_API_KEY` 来自进程临时注入或设备级唯一受管 secret。
3. 用户已确认当前 storyboard、预计费用和素材授权。
4. 所有远程图片/视频是 HTTPS URL，人物使用真实资产 URI。

禁止自动重试。需要再次创建任务时，必须作为新的用户确认动作执行。
