# 脚本入口

## `publish_project_artifact.mjs`

唯一项目创建、绑定和媒体上传入口：

1. 从受管 secret 读取凭据并验证账号。
2. 读取、创建或精确绑定一个项目。
3. 按文件类型选择项目媒体或 `preview3d`。
4. 使用内容哈希生成幂等键。
5. 图片/视频以一个 POST 写入文件和来源语义。
6. 回读资产，把资产 ID 和 SHA-256 写入唯一 binding。
7. 输出 `baiende.project-publication-receipt.v1`。

首次 dry-run：

```bash
node scripts/publish_project_artifact.mjs \
  --file <accepted.png> \
  --asset-kind layout_plan \
  --external-tool interior-floorplan-planning \
  --external-run-id <task-id> \
  --project-name <项目名> \
  --binding-file <项目目录>/baiende-project.json \
  --dry-run
```

后续只传同一 `--binding-file`。

## `publish_community_post.mjs`

唯一社区预览和公开入口：

- 输入 `baiende.community-publication-spec.v1`。
- `--dry-run` 只验证本地合同，不读取凭据、不请求平台。
- 默认只调用 HTML snapshot preview，不公开。
- 真实公开必须同时传 `--execute --confirm-public`。
- 发布 payload 必须来自同一次平台 preview 响应，业务 Skill 不能自行编造。
- 支持七个正式内容来源和独立视频 Skill，不硬编码为图册。

## `list_library_items.mjs`

只读平台风格、灯光、材质和家具资产库。支持 `--summary` 或
`--library <id>`、`--scope`、`--type`、`--limit`、`--json`。

## `upload_library_item.mjs`

把用户有权使用的图片写入个人资产库。必填 `--library`、`--name`；可选
`--image-file`、`--metadata-file`、重复 `--tag` 和 `--dry-run`。个人资产默认
不公开。

## `idk-env.mjs`

唯一平台请求 helper。只读取 `ENVIRONMENT_CONTRACT.md` 规定的受管 secret，
不扫描工作区、业务 Skill、cwd `.env` 或历史目录。
