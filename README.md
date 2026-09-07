# Interior Design Skill Set

室内设计 Skill 的版本化备份与分发仓库。2026-09-07 的 `main` 更新以下六项为小酷 Windows 实际安装版；六项之外的十项旧 Skill 保留原文件，不代表它们已经完成 GPT-6／Windows 适配。

## 当前六项设计 Skill

| Skill | 版本 | 职责 |
|---|---|---|
| [interior-floorplan-planning](skills/interior-floorplan-planning/SKILL.md) | 3.0.0 | 原图、尺度、拓扑、动线与家具锚点，交付布局 JSON |
| [interior-html-modeling](skills/interior-html-modeling/SKILL.md) | 3.0.0 | 代码生成离线 HTML 模型、CMF 风格、家具替换、量尺与保存 |
| [interior-camera-capture](skills/interior-camera-capture/SKILL.md) | 3.0.0 | 从真实模型求机位并截图，默认完整场景 |
| [interior-space-rendering](skills/interior-space-rendering/SKILL.md) | 3.0.0 | 同机位参照、原生绘图与指定资产约束 |
| [idk-canvas-ingest-agent](skills/idk-canvas-ingest-agent/SKILL.md) | 3.1.0 | 百恩得资产检索／下载与私有平台交付 |
| [booklet-production](skills/booklet-production/SKILL.md) | 4.1.0 Windows | 杂志式 HTML／PDF 方案册，含模板和样册 |

六项共125个分发文件，保留各项完整的代码、模板、说明书 JSON／Markdown／SVG／PDF 及自带资产。每项根目录 `SKILL_MANUAL.pdf` 是对应的流程说明；[设计编排与方案册说明](skills/booklet-production/SKILL_MANUAL.pdf)、[杂志式样册](skills/booklet-production/expected_outcome/demo.pdf) 可直接查看。样册使用公开参考图，不是客户户型或本轮原生绘图成果。

## 完整设计编排

客户户型图 → 规划 JSON → 代码生成准确整户型 → 初始机位看布局 → 用户风格 CMF／必要选型入模 → 正式同版机位截图 → 原生绘图 → 按目标交付。

- 图片任务直接交图片；模型任务交 HTML／JSON；完整方案才调用方案册 Skill。
- 初始截图不能直接配更新后的模型；保存风格版本后刷新正式截图。结构或家具包络变化时重新求解受影响机位。
- 平台资产和上传按需调用，已有同版成果复用，不强制重跑。
- 渲染默认带完整家具与细节。只有用户明确要求“白模／空白槽位”才切换空槽模式；两种模式都锁结构与机位，指定资产不变形。

## 安装与就绪边界

每项安装单元是 `skills/<skill-id>/`，将需要的六项目录安装到目标设备私有 `$CODEX_HOME/skills`；不要把历史 CAD／Blender 等目录一并当成新版安装。代码和模板可复制，但 Python、Chrome、字体、原生绘图工具及平台授权必须按各项 `local_runtime.md` 在目标设备配置。

- Git 中不含 API Key、`.runtime`、登录态、客户文件、软件程序或设备缓存。平台 Key 仅在已授权设备本地配置；不能把 Key 放入 HTML、PDF 或 Git。
- 本次发布没有改动小酷运行中的六项，也没有安装到其它设备。小酷原平台 Key 保留不变。
- Windows 建模／机位回归及方案册 PDF 已有目标设备测试记录；原生绘图真实生成能力不因推送 Git 就视为已验证。
- 新安装后旧 TUI 可能尚未发现新增 Skill；按实际情况读取明确入口或在同一工作区新开会话，不中断运行中任务。
- 旧 `scripts/audit-runtime-prerequisites.mjs` 仅保留为历史 Ubuntu 辅助工具，不适用于新版六项的精简目录合同。

## 历史与完整性

- `20260808-历史备份`：旧 main 完整备份。
- `20260907-gpt5.6`：Ubuntu 16项设计 Skill 历史快照。
- 这两个历史分支不因本次 main 更新而改动，也不改写 main 历史。
- `manifest.json` 区分当前来酷六项和保留的旧快照来源。
- `FILES.sha256` 记录 `skills/` 全部文件；运行 `node scripts/build-manifest.mjs --snapshot <ISO-8601>` 重建清单。

第三方代码和素材的许可、来源、署名以各自文件为准，不以仓库说明覆盖。
