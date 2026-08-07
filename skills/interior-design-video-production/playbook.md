# Playbook

## 阶段 1：输入与版本锁定

1. 读取当前项目 `confirmed-version/manifest.json` 或用户本轮明确指定的文件。
2. 记录每个输入的路径、SHA-256、角色和来源 Skill。
3. 将输入分为：空间主图、细节图、产品图、人物、镜头参考、文案事实。
4. 拒绝历史候选、失败图、来源不明素材和同名不同哈希文件。
5. 需要真实空间关系时，检查机位截图与 `shot-scene-map` 属于同一相机和模型版本。

产出：`video-input-lock.json`。

## 阶段 2：叙事类型与时长

1. 从五类正式模板中选一个主类型。
2. 确定横竖屏、总时长、是否人物口播、目标渠道和核心信息。
3. 计算片段数量：每段 5-15 秒，总片数尽量少。
4. 为每段指定唯一主要空间或产品焦点，不能让一个镜头跨越没有真实连接的房间。

产出：`video-storyboard-plan.json` 的元数据、`shots[]` 骨架。

## 阶段 3：台词与逐秒镜头

1. 先写完整台词，再按自然语速拆到各片段。
2. 每句记录起止时间、字数和每秒字数。
3. 每 1-2 秒形成一个 `microBeat`，写清：
   - 机位和景别
   - 镜头路径
   - 构图和运动
   - 入场与出场转场
   - 焦点对象和细节
   - 对应台词
   - BGM、音效和灯光
4. `storyboardPanels[]` 与 `shots[]` 必须引用同一 shot ID 和时间轴。
5. 外部参考只写“参考哪一种镜头语言”，不得成为当前空间事实。

产出：完整 `video-storyboard-plan.json`。

## 阶段 4：分镜草图

1. 使用 [video-storyboard-prompt.md](references/video-storyboard-prompt.md) 和当前计划，
   通过 Codex 原生绘图生成一张中文粗线稿 storyboard sheet。
2. 每格必须有时间、shot ID、人物站位、焦点、运动箭头和转场。
3. Agent 对照计划逐格看图，逐项确认：
   - 房间和家具没有被替换
   - 镜头方向与 `cameraPath` 一致
   - 人物站位不遮挡主体
   - 时间和 shot ID 可读
4. 不通过则重做草图，不能靠修改 JSON 假装图已正确。
5. accepted 草图交给 `idk-canvas-ingest-agent` 上传项目，取得 HTTPS URL，并写入
   `storyboardSketch.imageUrl`。

## 阶段 5：HTML 审阅

运行：

```bash
node scripts/render_design_video_storyboard_html.mjs \
  video-storyboard-plan.json \
  --out video-storyboard-preview.html
```

检查：

- 所有主图和分镜图可加载。
- 角色、台词、镜头、声音、灯光和参考用途完整可读。
- 没有本地路径被当作远程素材。
- 用户确认分镜、台词、时长、人物和目标比例。

## 阶段 6：Seedance dry-run 与费用确认

运行：

```bash
node scripts/generate_seedance_video_from_storyboard.mjs \
  video-storyboard-plan.json \
  --out seedance-dry-run.json \
  --dry-run
```

dry-run 必须完全离线，不读取 Key。向用户说明：

- 计划生成几段
- 每段时长、依赖关系和素材
- 使用模型
- 预计总费用
- 失败后不会自动重试

没有用户对方案和费用的本轮明确确认时，到此停止。

## 阶段 7：真实生成

用户明确确认后，先运行零费用凭据预检：

```bash
node scripts/check_seedance_connectivity.mjs \
  --out seedance-connectivity-check.json
```

只有状态为 `reachable_auth_ok_no_task_created` 时才运行：

```bash
node scripts/generate_seedance_video_from_storyboard.mjs \
  video-storyboard-plan.json \
  --out seedance-video-generation-manifest.json \
  --output-dir outputs/seedance-video \
  --execute \
  --confirm-paid-generation
```

执行规则：

1. 生成脚本再次自动执行同一零费用鉴权预检，防止确认后凭据被轮换。
2. 串行提交第一段。
3. 轮询到成功后下载并记录 provider task ID、URL、字节数和本地路径。
4. 第二段使用上一段 provider 视频继续延长。
5. 任一阶段失败立即写 manifest 并停止。
6. 不批量提交，不自动重试，不自动改模型。

## 阶段 8：合片与 QA

1. 用 `ffprobe` 读取每段编码、分辨率、帧率、音轨和时长。
2. 只使用 Agent 接受的片段，并按 `shots[]` 固定顺序列入 concat 清单。
3. 优先无损拼接；编码不兼容时统一转码一次。
4. 再次用 `ffprobe` 检查最终时长和音视频轨道。
5. Agent 从头到尾观看，检查：
   - 空间和产品没有漂移或凭空新增
   - 人物身份和服装连续
   - 镜头衔接自然
   - 台词、字幕、口型和声音合理
   - 无黑帧、重复开场、突变和水印

只有 accepted 成片可以进入交付。

## 阶段 9：交付与平台交接

交付计划、分镜、HTML、generation manifest、片段、最终视频和 QA。

用户要求上传平台时：

```bash
node /home/agentops/.codex/skills/idk-canvas-ingest-agent/scripts/publish_project_artifact.mjs \
  --file <accepted-video.mp4> \
  --asset-kind design_video \
  --external-tool interior-design-video-production \
  --external-run-id <task-id> \
  --binding-file <project>/baiende-project.json
```

用户要求公开到社区时，另为发布 Skill 准备社区说明和 accepted 封面/视频。项目上传
不等于公开；本 Skill 不调用社区 API。

## 失败归因

- `input-fact`：当前版本或素材来源不清楚，回到阶段 1。
- `storyboard-spec`：台词、时长或镜头计划不完整，回到阶段 2-3。
- `storyboard-image`：草图和 JSON 不一致，回到阶段 4。
- `provider-request`：请求合同或素材 URL 错误，修正事实后重新 dry-run。
- `provider-generation`：模型生成失败或质量差，报告原因与新增费用，等待用户确认。
- `assembly`：片段编码/音轨不兼容，只修合片，不重做上游事实。
- `visual-quality`：画面不符合 accepted 空间或产品，拒绝该片段。
