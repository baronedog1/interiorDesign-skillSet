# API 合同

## 鉴权

- 根地址：`https://www.baiende.com/api/v1`
- 请求头：`X-IDK-API-Key`、`X-IDK-Tool-Name`
- 所有写操作携带 `Idempotency-Key`；请求层把 UTF-8 业务键统一哈希为固定 ASCII 头，中文项目名和文件名不能直接进入 HTTP header
- API Key 绑定的用户就是项目和资产所有权边界

## 项目发布白名单

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/auth/profile` | 验证受管凭据 |
| GET | `/projects` | 精确查找项目 |
| POST | `/projects` | 首次创建项目 |
| GET | `/projects/{projectId}/assets` | 查重与回读 |
| POST | `/projects/{projectId}/assets` | 上传外部已有图片/视频 |
| POST | `/projects/{projectId}/preview3d` | 上传 standalone HTML |

普通项目资产使用一次原子 POST。顶层和 `materials[]` 同时携带
`assetKind`、`externalTool`、`externalRunId`、`origin=uploaded`、
`sourceType=external_upload` 及可选空间说明；每项材料包含
`folderId`、`name`、`mimeType`、`base64`。不再先上传再 PATCH 元数据。
HTML 请求必须在 `preview3d` payload 顶层使用 `html` 字符串，不能包装成普通 `file/html` 对象。

平台没有按项目 ID 单独读取的路由。项目绑定校验必须读取 `/projects`，再按 UUID 精确匹配一条，不得臆造 `/projects/{projectId}`。

## 个人资产库白名单

- `GET /library/summary`
- `GET /library/{libraryId}/items`
- `POST /library/{libraryId}/items`

允许 `style_template`、`lighting_template`、`material_soft`、`material_hard`、`material_other`。个人上传默认不公开。

## 社区发布白名单

- `POST /community/html-snapshots/preview`
- `POST /community/posts`，仅在用户本轮明确确认后发布

社区正文由任一 accepted 设计成果组成，但必须先编译为
`baiende.community-publication-spec.v1`，并由 preview 接口返回正式
`communityPostPayload`。业务 Skill 不得直接拼 `/community/posts` 请求。

## 禁止

- `/generations*` 及任何 AI 生成、编辑、去背、营销图、视频或积分接口。
- 日常发布不得调用 DELETE、垃圾箱和批量覆盖。
- 非 `/api/v1` 根、匿名 OSS/CDN 上传。
