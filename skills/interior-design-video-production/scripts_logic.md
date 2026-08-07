# Scripts Logic

## `render_design_video_storyboard_html.mjs`

- 读取正式 storyboard plan。
- 把当前图、人物、参考用途、中文分镜、台词、逐秒镜头和声音排成单文件 HTML。
- 不调用生成或平台 API，不修改计划。

## `generate_seedance_video_from_storyboard.mjs`

- 默认 dry-run；dry-run 不读取 API Key。
- 真实执行必须同时传 `--execute --confirm-paid-generation`。
- 真实执行在第一个付费 POST 前自动执行零费用鉴权 GET；未通过则停止。
- 根据同一 plan 确定性编译第一段和连续延长段的请求。
- 第一段使用 storyboard 和当前项目图片；后续段只依赖上一段 provider 视频。
- 串行创建、轮询和下载；任何失败立即停止并写 manifest。
- 禁止批量并发、自动重试和静默切换模型。

## `seedance_runtime.mjs`

- 独占受管 secret 路径、历史 Key 别名归一化、权限检查和 Ark 根地址校验。
- 独占零费用鉴权 GET 的实现，供检查脚本和生成脚本共同调用。
- 不输出 Key，不向工作区复制 Key，不创建生成任务。

## `check_seedance_connectivity.mjs`

- 从设备级唯一受管 secret 读取凭据。
- 查询一个必然不存在的 task ID；非鉴权 `4xx` 表示凭据可用。
- 输出脱敏状态、HTTP 状态和 provider error code；绝不发送付费 POST。

## `query_ai_video_references_db.mjs`

- 只读查询公司级 AI 视频参考库。
- 返回有限候选及真实 URL、参考用途、时长和元数据。
- 不写数据库，不导出完整表，不把参考空间当当前项目事实。

## `query_seedance_virtual_human_assets_db.mjs`

- 只读查询真实人物候选。
- 输出真实 asset ID/URI、人物标签和选择依据。
- 不编造人物，不写数据库。

## 合片

合片直接使用设备受管 `ffprobe` / `ffmpeg`：

1. `ffprobe` 检查 accepted 片段。
2. 按 storyboard 的 `shots[]` 写临时 concat 清单。
3. 编码一致时使用 concat demuxer 无损拼接。
4. 编码不一致时统一转码一次。
5. 删除临时清单前保存最终 QA 和媒体事实。

不在 Skill 中维护第二个视频渲染器或 GUI。

## 平台边界

本目录禁止出现 `IDK_API_KEY`、`idk-env.mjs`、项目创建、上传、社区 API 或
匿名 OSS 脚本。accepted 视频统一委托 `idk-canvas-ingest-agent`。
