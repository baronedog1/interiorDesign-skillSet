---
name: idk-canvas-ingest-agent
description: 当用户说“创建百恩得项目”“上传到平台”“放进当前项目”“给我平台/手机预览链接”“发布到社区/作品社区/公开分享”，或任一设计 Skill 需要交付已验收产物时使用；它是项目身份、受管凭据、平台资产上传、standalone HTML 预览和社区发布的唯一事实源。首次精确创建或复用一个项目并保存 baiende-project.json，后续所有 Skill 复用同一绑定；社区先生成私有预览，只有用户本轮明确确认后才公开发布。
metadata: {"category":"interior-design","skill_type":"platform","source_authority":"aliyun-project-source","version":"2.0.0","project_binding_schema":"baiende.project-binding.v1","community_publication_schema":"baiende.community-publication-spec.v1"}
---

# 百恩得平台项目与社区发布

## 唯一职责

本 Skill 独占以下能力：

1. 读取受管平台凭据并验证账号。
2. 首次精确查找或创建百恩得项目。
3. 保存和复用唯一 `baiende-project.json`。
4. 上传 accepted 图片、视频和 standalone HTML。
5. 回读平台资产并生成幂等发布回执。
6. 为 accepted 内容生成社区 HTML snapshot 预览。
7. 用户明确确认后发布到社区并返回公开链接。
8. 读取平台资产库；按授权上传用户个人资产。

它不生成设计内容、不验收业务美学、不调用付费生成或删除接口。

## 简单意图入口

- “创建一个项目 / 上传到百恩得 / 放到平台项目”：使用本 Skill。
- “把后面的平面、模型、机位和效果图都放在同一个项目”：首次创建一次，后续只复用
  同一 binding。
- “把 HTML 给我一个手机能打开的平台链接”：以 `preview3d_html` 上传项目。
- “发布到社区 / 作品社区 / 给公开分享链接”：先生成社区预览；只有本轮明确确认
  公开后才执行发布。
- “帮我规划 / 建模 / 出效果图 / 做视频 / 做 PDF”：先调用对应业务 Skill，
  accepted 后再回到本 Skill。

## 七个核心 Skill 的关系

其它六个核心业务 Skill 不保存 Key、API 路径、项目 ID 推断、上传 helper 或社区
发布代码。它们只产生平台 handoff，并指引 Agent 调用本 Skill。

独立视频 Skill 也遵守同一规则：只交接 accepted 视频和社区说明，不复制发布逻辑。

## 项目流程

1. 上游提交 accepted 文件、`assetKind`、来源 Skill、run ID 和 binding 路径。
2. 首次发布：
   - 有项目 ID 时精确绑定；
   - 只有项目名时精确查找；
   - 零个匹配时创建，一个匹配时复用，多个匹配时停止。
3. 写入项目根目录唯一 `baiende-project.json`，不写入 API Key。
4. 图片/视频走项目资产接口；完整 standalone HTML 走 `preview3d`。
5. 用内容哈希和稳定路径做幂等：
   - 同路径同哈希跳过；
   - 同路径不同哈希停止，要求显式版本化名称。
6. 回读平台资产并写 `baiende.project-publication-receipt.v1`。

## 社区流程

项目入库和公开社区是两个动作：

1. 上游准备 accepted 内容、标题、摘要、标签、HTML snapshot 和所有图片的 HTTPS 映射。
2. 本 Skill 调用 `/community/html-snapshots/preview`，只生成预览和诊断，不公开。
3. Agent 展示预览结论，核对标题、封面、正文、素材授权和目标项目。
4. 只有用户本轮明确说“确认公开发布”后，使用
   `--execute --confirm-public` 调用 `/community/posts`。
5. 保存 `baiende.community-publication-receipt.v1` 和公开链接。

禁止把“上传项目”自动解释成“公开社区”。

## 可接收产物

| 来源 | accepted 产物 | `assetKind` |
|---|---|---|
| `interior-floorplan-planning` | 原图、规划图、四象限图 | `floorplan_source`、`layout_plan`、`layout_annotation` |
| `interior-html-modeling` | 户型 standalone HTML | `preview3d_html` |
| `interior-camera-capture` | 正式机位图 | `camera_shot` |
| `interior-space-rendering` | 最终效果图 | `render_image` |
| `movable-furniture-modeling` | 产品参考、模型预览、单品 HTML | `product_reference`、`component_preview`、`preview3d_html` |
| `booklet-production` | 封面、页面预览、社区 snapshot | `booklet_preview` |
| `interior-design-video-production` | 分镜图、最终视频 | `storyboard_image`、`design_video` |

JSON、Markdown、PDF、组件包、scene map 和 QA 报告不是项目媒体，不通过媒体接口
上传；它们保留在任务交付或作为 HTML 元数据。

## 停止条件

- 上游状态不是 `accepted`。
- 首次绑定既无项目名也无项目 ID。
- binding 与命令项目身份冲突。
- 同路径存在不同 SHA-256。
- HTML 不是完整 standalone，含 localhost、本地路径或相对 runtime 依赖。
- 媒体类型与 `assetKind` 不一致。
- 缺少受管凭据。
- 用户只要求上传项目，却试图执行社区公开。
- 社区公开缺少 `--execute --confirm-public`。

缺凭据或 API 失败时明确停止；禁止降级为匿名 OSS、临时 CDN、旧脚本或第二套
上传方法。

## 禁止事项

- 不调用 `/generations*`、积分、删除、垃圾箱或批量覆盖接口。
- 不从业务 Skill、工作区或历史 Skill 读取复制密钥。
- 不把社区发布代码复制进 `booklet-production` 或其它 Skill。
- 不公开未确认、失败、retake、历史候选或无授权素材。
- 不把 JSON、PDF、ZIP 当作平台项目媒体。

## 文档路由

| 文档 | 负责事实 |
|---|---|
| [playbook.md](playbook.md) | 项目生命周期、跨 Skill 映射和社区确认流程 |
| [api.md](api.md) | 唯一 API 白名单和请求合同 |
| [data_contract.md](data_contract.md) | binding、项目回执、社区 spec 与回执 |
| [scripts_logic.md](scripts_logic.md) | 项目、社区和资产库脚本 |
| [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) | 受管凭据和安装边界 |
| [local_runtime.md](local_runtime.md) | dry-run 与真实命令 |

