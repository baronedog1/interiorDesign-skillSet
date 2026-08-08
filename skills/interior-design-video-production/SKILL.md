---
name: interior-design-video-production
description: 当用户说“把这些效果图做成视频”“做室内空间漫游/方案讲解/家具展示/材质细节/社区预热视频”“做视频分镜”“调用 Seedance 生成设计视频”或要求虚拟设计师口播时使用；只接收已确认的空间图、机位图、产品图和方案文案，先完成中文分镜、台词、镜头和费用确认，再调用 Seedance/Ark 串行生成并确定性合片。户型规划、3D 建模、机位截图、效果图、PDF、平台项目上传和社区发布分别交给对应 Skill，本 Skill 不重做这些事实。
metadata: {"category":"interior-design","skill_type":"business-extension","source_authority":"ubuntu-01-device-source","version":"1.1.0","storyboard_schema":"interior.design-video-storyboard.v2","generation_schema":"interior.design-video-generation.v3"}
---

# 室内设计视频制作

## 使用前准备

- 管理员预装 Node.js 22、ffmpeg 与 ffprobe；先读取 [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) 与 [local_runtime.md](local_runtime.md)，完成 storyboard、时间线和 `--dry-run` preflight。
- 查询参考库需受管数据库或 SSH 只读入口；真实 Seedance/Ark 生成需设备独立 secret，并在付费前取得用户本轮明确确认。未授权时必须保持 `degraded/dry-run-only`。
- 必须已有 accepted 静态资产、来源哈希和明确的视频 brief；依赖、授权或输入缺失时在生成前标记 `blocked`，禁止任务内安装工具、复制其它设备凭据或自动付费重试。

## 唯一职责

把已经验收的室内设计静态资产变成可确认、可生成、可追溯的视频：

1. 锁定当前确认版空间图、产品图、文字和人物资产。
2. 选择唯一叙事类型并写台词、分镜、镜头、声音和转场。
3. 生成中文粗线稿 storyboard sheet 和 HTML 审阅页。
4. 在不调用付费接口的 dry-run 中形成完整 Seedance 请求清单和费用估算。
5. 用户明确确认方案与费用后，先执行零费用 Ark 鉴权预检，再逐段调用
   Seedance/Ark，失败即停。
6. 对已接受片段执行固定顺序合片和视听复核。

本 Skill 不重新解释墙窗、房间、家具位置或效果图风格；这些事实必须来自对应
上游 Skill 的 accepted 产物。

## 简单意图入口

- “把这几张效果图做成视频 / 做空间漫游”：使用本 Skill。
- “做设计视频分镜 / 先给我看脚本和镜头”：使用本 Skill，只执行到 dry-run。
- “用虚拟设计师讲解方案”：使用本 Skill，并从真实人物资产库选择候选。
- “把这个沙发做成产品展示视频”：使用本 Skill；产品 3D 或产品图先由
  `movable-furniture-modeling` 验收。
- “规划户型 / 户型建模 / 找机位 / 出效果图 / 做 PDF”：不用本 Skill，分别路由
  `interior-floorplan-planning`、`interior-html-modeling`、
  `interior-camera-capture`、`interior-space-rendering`、
  `booklet-production`。
- “上传项目 / 发布社区”：不用本 Skill；把 accepted 视频和社区发布说明交给
  `idk-canvas-ingest-agent`。

## 输入门槛

- 必须有明确的当前确认版资产清单和 SHA-256；不得扫描历史目录猜最新文件。
- 空间视频至少有一张 accepted 效果图；需要真实空间连续关系时，应同时提供正式
  机位图和 `shot-scene-map`。
- 产品视频必须提供 accepted 产品参考或单产品 standalone HTML。
- 外部参考视频只能约束镜头语言、节奏或材质表现，不能替换当前项目空间与产品。
- 需要人物时，必须记录真实 `assetId`、`assetUri`、`sssid` 和
  `seedanceAssetUri`，不能编造人物。
- 用户没有确认视频方案和预计付费时，只允许 storyboard 与 dry-run。

## 唯一流程

严格执行 [playbook.md](playbook.md) 的九阶段流程：

1. 输入和版本锁定。
2. 叙事类型与时长规划。
3. 台词、逐秒镜头和素材映射。
4. 原生分镜草图及 Agent 逐格复核。
5. HTML 审阅与用户确认。
6. Seedance dry-run 和费用确认。
7. 逐段真实生成。
8. 固定顺序合片与 QA。
9. 交付，按需转平台发布 Skill。

不得跳过阶段 4-6 直接付费生成。

## 叙事类型

每个任务只选择一个主类型：

- `whole_house_walkthrough`：按真实空间连接进行全屋导览。
- `room_story`：单空间方案讲解。
- `furniture_detail`：单件家具的轮廓、结构、可动部件和使用情境。
- `material_detail`：材质、收口、光影和触感细节。
- `community_teaser`：短时长社区预告，只展示当前项目已确认内容。

模板见 `references/`。模板提供结构，不覆盖用户给出的真实空间、产品、品牌或尺寸。

## 付费与公开边界

- `--dry-run` 不读取 API Key、不发出网络生成请求。
- 真实生成统一读取设备受管 secret；不得把长期 Key 放入工作区 `.env`。
- 真实生成在第一个付费 `POST` 前自动发出一次不存在任务的 `GET` 鉴权预检；
  `401/403` 立即停止，且不会创建任务或产生生成费用。
- 真实生成必须同时使用 `--execute --confirm-paid-generation`。
- 片段串行生成；任何失败立即停止，不自动重试，不继续消耗。
- 失败片段若要重试，必须重新向用户说明失败原因和新增费用。
- 项目上传不是公开发布；社区公开必须另由用户明确确认，并交给
  `idk-canvas-ingest-agent --execute --confirm-public`。

## 交付

每次完成至少交付：

- `video-storyboard-plan.json`
- 中文 storyboard sheet
- `video-storyboard-preview.html`
- `seedance-video-generation-manifest.json`
- 已接受片段与最终视频；只做方案时则明确标为 `dry-run`
- 当前输入、人物、参考视频和产物来源清单
- QA 结论及未通过项

需要平台交付时，本 Skill 只提交：

```json
{
  "file": "delivery/design-video.mp4",
  "assetKind": "design_video",
  "externalTool": "interior-design-video-production",
  "externalRunId": "task-id",
  "bindingFile": "baiende-project.json"
}
```

项目创建、鉴权、上传、社区预览和公开发布逻辑不得复制到本 Skill。

## 禁止事项

- 不生成或修改户型、Three.js 模型、机位、效果图和 PDF。
- 不把未验收图、历史候选或外部参考空间当成当前项目画面。
- 不在没有真实人物资产时让模型随机保持“同一人物”。
- 不批量并发提交 Seedance 片段。
- 不把本地路径传给远程视频 API；所有远程素材必须是 HTTPS URL 或受支持资产 URI。
- 不把密钥、Cookie、数据库密码、签名 URL 写入计划、日志、MANIFEST 或交付包。
- 不调用百恩得生成、积分、删除或社区接口。

## 验收

- 分镜每一格可追溯到当前确认图和 `storyboardPanels[]`。
- 台词、镜头、焦点、声音、灯光、转场和时长字段完整。
- dry-run 请求数、模型、时长、比例、素材和预计费用可读。
- 每段视频通过 `ffprobe`；最终视频时长与已接受片段之和一致。
- Agent 视觉复核空间、家具、人物、镜头连续性和文字/口播，无凭空新增房间。
- 交付不含密钥，平台发布只存在于共享发布 Skill。

## 文档路由

| 文档 | 负责事实 |
|---|---|
| [playbook.md](playbook.md) | 九阶段执行、确认点、QA 和交付 |
| [api.md](api.md) | Seedance/Ark 请求、轮询和素材合同 |
| [data_contract.md](data_contract.md) | 分镜、生成清单和平台交接 schema |
| [scripts_logic.md](scripts_logic.md) | 六个确定性脚本及禁止边界 |
| [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) | 环境变量、密钥和运行依赖 |
| [local_runtime.md](local_runtime.md) | 本地命令与顺序 |
