# 数据合同

## `baiende.project-binding.v1`

位于设计项目根目录，不进入 Skill 包。

```json
{
  "schema": "baiende.project-binding.v1",
  "projectId": "platform-project-uuid",
  "projectName": "住宅 A 方案",
  "projectUrl": "https://www.baiende.com/projects/platform-project-uuid",
  "apiBaseUrl": "https://www.baiende.com/api/v1",
  "artifacts": {
    "plan/layout-plan-v1.png": {
      "assetId": "platform-asset-uuid",
      "assetKind": "layout_plan",
      "folderId": "plan",
      "name": "layout-plan-v1.png",
      "mimeType": "image/png",
      "sha256": "hex",
      "bytes": 123456,
      "externalTool": "interior-floorplan-planning",
      "externalRunId": "task-id",
      "publishedAt": "2026-07-29T00:00:00.000Z"
    }
  },
  "boundAt": "2026-07-29T00:00:00.000Z"
}
```

不保存 API Key、Cookie、签名 URL 或用户登录态。

## 项目发布请求

必填：

| 字段 | 说明 |
|---|---|
| `file` | accepted 本地文件 |
| `assetKind` | 上游业务语义 |
| `externalTool` | 来源 Skill |
| `externalRunId` | 本轮 run/task ID |
| `bindingFile` | 当前项目唯一 binding |
| `projectName` 或 `projectId` | 仅首次绑定需要 |

可选：`folderId`、`caption`、`title`、`roomName`、`manifestFile`、
`sourceProjectAssetId`、`sourceNodeId`。

## 项目媒体

- 图片：PNG、JPEG、WEBP。
- 视频：MP4、WEBM、MOV。
- 3D 预览：完整 standalone HTML，且 `assetKind=preview3d_html`。

禁止将 JSON、Markdown、PDF、ZIP、组件包或 QA 报告作为项目媒体。

## `baiende.project-publication-receipt.v1`

```json
{
  "schema": "baiende.project-publication-receipt.v1",
  "dryRun": false,
  "project": {
    "id": "platform-project-uuid",
    "name": "住宅 A 方案",
    "url": "https://www.baiende.com/projects/platform-project-uuid",
    "created": true,
    "bindingFile": "/project/baiende-project.json"
  },
  "artifact": {
    "file": "/project/living-render-v1.png",
    "name": "living-render-v1.png",
    "mimeType": "image/png",
    "assetKind": "render_image",
    "folderId": "living",
    "sha256": "hex",
    "bytes": 123456,
    "externalTool": "interior-space-rendering",
    "externalRunId": "run-id"
  },
  "publication": {
    "assetId": "platform-asset-uuid"
  },
  "publishedAt": "2026-07-29T00:01:00.000Z"
}
```

## `baiende.community-publication-spec.v1`

由业务 Skill 准备内容，平台字段只由本 Skill解释。

```json
{
  "schema": "baiende.community-publication-spec.v1",
  "bindingFile": "baiende-project.json",
  "sourceSkill": "booklet-production",
  "sourceRunId": "task-id",
  "title": "现代简约住宅方案",
  "summary": "客厅、餐厅与卧室完整方案",
  "tags": ["现代简约", "住宅设计"],
  "htmlPath": "community-snapshot.html",
  "cssPaths": [],
  "imageAssetMap": {
    "images/cover.png": "https://cdn.example/cover.png"
  },
  "coverSourceAssetId": "platform-asset-uuid"
}
```

`sourceSkill` 只能是：

- `interior-floorplan-planning`
- `interior-html-modeling`
- `interior-camera-capture`
- `interior-space-rendering`
- `movable-furniture-modeling`
- `booklet-production`
- `interior-design-video-production`

所有 snapshot 图片必须映射到 HTTPS 平台/CDN URL。spec 不能包含
`templateId`、`themeId`、`renderMode`、`templateDraft`、`layoutSnapshot`、
`blocks` 或 `pages` 等平台布局实现字段。

## `baiende.community-publication-receipt.v1`

```json
{
  "schema": "baiende.community-publication-receipt.v1",
  "mode": "preview_only",
  "projectId": "platform-project-uuid",
  "preview": {
    "htmlLength": 120000,
    "diagnostics": null
  },
  "communityPostPayload": {},
  "generatedAt": "2026-07-29T00:02:00.000Z"
}
```

公开后追加：

```json
{
  "publish": {
    "id": "post-id",
    "sharePath": "/community/post-id",
    "shareUrl": "https://www.baiende.com/community/post-id"
  }
}
```

