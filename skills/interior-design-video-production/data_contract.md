# Data Contract

## `interior.design-video-input-lock.v1`

```json
{
  "schema": "interior.design-video-input-lock.v1",
  "taskId": "task-id",
  "confirmedVersionId": "version-id",
  "assets": [
    {
      "id": "living-render-01",
      "path": "confirmed-version/living-render.png",
      "sha256": "hex",
      "role": "accepted_render",
      "sourceSkill": "interior-space-rendering",
      "status": "accepted"
    }
  ],
  "allowedChanges": [
    "camera_motion",
    "transition",
    "voiceover",
    "sound_design"
  ],
  "lockedFacts": [
    "space_structure",
    "furniture_identity",
    "accepted_style"
  ]
}
```

## `interior.design-video-storyboard.v2`

```json
{
  "schema": "interior.design-video-storyboard.v2",
  "taskId": "task-id",
  "title": "客厅方案讲解",
  "narrativeType": "room_story",
  "aspectRatio": "16:9",
  "totalDurationSec": 20,
  "images": [
    {
      "id": "living-01",
      "url": "https://cdn.example/living.png",
      "sourceAssetId": "living-render-01",
      "role": "hero"
    }
  ],
  "aiCharacter": {
    "enabled": false,
    "library": null,
    "assetId": null,
    "assetUri": null,
    "sssid": null,
    "seedanceAssetUri": null
  },
  "globalReferenceVideos": [
    {
      "key": "slow-interior-pan",
      "url": "https://cdn.example/reference.mp4",
      "durationSeconds": 6,
      "referenceUse": ["camera_pacing"],
      "referenceNotes": "只参考缓慢横移节奏"
    }
  ],
  "storyboardSketch": {
    "imageUrl": "https://cdn.example/storyboard.png",
    "sourceSkill": "interior-design-video-production",
    "visualReviewStatus": "accepted"
  },
  "storyboardPanels": [
    {
      "panelId": "panel-01",
      "shotId": "shot-01",
      "timeRange": "0-2s",
      "roughVisual": "从客厅入口看向沙发墙",
      "cameraCue": "缓慢前推",
      "transitionCue": "淡入"
    }
  ],
  "shots": [
    {
      "id": "shot-01",
      "title": "进入客厅",
      "startSec": 0,
      "durationSec": 10,
      "imageIds": ["living-01"],
      "dialogueLines": [
        {
          "speakerName": "旁白",
          "start": 0.5,
          "end": 5.5,
          "text": "从入口进入，客厅的主要视线落在完整沙发背景墙。",
          "charCountNoPunctuation": 24,
          "charsPerSecond": 4.8
        }
      ],
      "microBeats": [
        {
          "start": 0,
          "end": 2,
          "shotSize": "全景",
          "camera": "入口机位",
          "cameraPath": "向前 0.5 米",
          "framing": "保持竖线垂直",
          "movement": "慢速前推",
          "transitionIn": "淡入",
          "transitionOut": "连续运动",
          "focusObject": "沙发墙",
          "detailCue": "保留左右留白",
          "dialogue": "从入口进入",
          "bgmCue": "低音量",
          "sfxCue": "无",
          "lightingCue": "保持当前日光"
        }
      ]
    }
  ],
  "seedancePromptPolicy": {
    "model": "seedance 2.0",
    "resolution": "720p",
    "generateAudio": true
  },
  "pricing": {
    "currency": "CNY",
    "estimatedCnyPerSecond": 1,
    "source": "本轮供应商报价或平台价格页",
    "observedAt": "2026-07-29T00:00:00.000Z"
  }
}
```

## `interior.design-video-generation.v3`

```json
{
  "schema": "interior.design-video-generation.v3",
  "mode": "dry-run",
  "sourcePlanPath": "video-storyboard-plan.json",
  "provider": "seedance",
  "endpointBase": "https://ark.cn-beijing.volces.com/api/v3",
  "apiKey": "not-required-in-dry-run",
  "credentialPreflight": null,
  "taskCount": 2,
  "generationPolicy": {
    "serialOnly": true,
    "sequentialExtension": true,
    "noBatchSubmit": true,
    "maxSingleVideoSeconds": 15,
    "retryRequiresUserConfirmation": true,
    "estimatedCostCny": 20
  },
  "tasks": []
}
```

执行模式下，每个 task 追加 `providerTaskId`、`status`、`videoUrl`、
`downloaded.path` 和 `downloaded.bytes`。密钥值永远不写入 manifest。
执行模式还必须记录脱敏的 `credentialPreflight`，其中
`createdTask=false`、`costIncurringRequest=false`；不得记录 Key 值。
`pricing.estimatedCnyPerSecond` 是本轮报价事实，不写死在 Skill；真实生成前必须
存在明确单价或每段 `estimatedCostCny`。

## 平台交接

```json
{
  "schema": "baiende.project-publication-handoff.v1",
  "file": "delivery/design-video.mp4",
  "assetKind": "design_video",
  "folderId": "video",
  "externalTool": "interior-design-video-production",
  "externalRunId": "task-id",
  "bindingFile": "baiende-project.json"
}
```

项目绑定、上传回执和社区发布 schema 只由 `idk-canvas-ingest-agent` 定义。
