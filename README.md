# Interior Design Skill Set

当前唯一基准：2026-09-08 来酷设备六项设计 Skill。main 仅发布这六项，不混入旧 CAD、Blender、独立动线或旧家具建模 Skill；历史内容可从历史分支及 Git 提交回溯。

## 当前六项设计 Skill

| Skill | 版本 | 职责 |
|---|---|---|
| [interior-floorplan-planning](skills/interior-floorplan-planning/SKILL.md) | 3.3.0 | 需求到功能/结构家族选型、尺度/拓扑/动线与真实家具锚点 |
| [interior-html-modeling](skills/interior-html-modeling/SKILL.md) | 3.2.2 | 代码粗模、透明白模、画边及跨房间可见产品、CMF与设计意图交接 |
| [interior-camera-capture](skills/interior-camera-capture/SKILL.md) | 3.2.1 | 主体正视、地面天花共同构图、真实可见空间与按用途选图 |
| [interior-space-rendering](skills/interior-space-rendering/SKILL.md) | 3.3.1 | 固定建筑与布局、全屋选品按镜头附图、参考板适配容量、同空间原生绘图 |
| [idk-canvas-ingest-agent](skills/idk-canvas-ingest-agent/SKILL.md) | 3.1.0 | 百恩得资产检索／下载与私有平台交付 |
| [booklet-production](skills/booklet-production/SKILL.md) | 4.1.1 Windows | 杂志式 HTML／PDF 方案册，含模板和样册 |

六项共131个分发文件，保留各项完整的代码、模板、说明书 JSON／Markdown／SVG／PDF 及自带资产。每项根目录 `SKILL_MANUAL.pdf` 是对应的流程说明；[设计编排与方案册说明](skills/booklet-production/SKILL_MANUAL.pdf)、[杂志式样册](skills/booklet-production/expected_outcome/demo.pdf) 可直接查看。样册使用公开参考图，不是客户户型或本轮原生绘图成果。

## 完整设计编排

客户户型图 → 规划 JSON → 代码生成准确整户型 → 初始机位看布局 → 用户风格 CMF／必要选型入模 → 正式同版机位截图 → 原生绘图 → 按目标交付。

- 图片任务直接交图片；模型任务交 HTML／JSON；完整方案才调用方案册 Skill。
- 初始截图不能直接配更新后的模型；保存风格版本后刷新正式截图。结构或家具包络变化时重新求解受影响机位。
- 平台资产和上传按需调用，已有同版成果复用，不强制重跑。
- 渲染默认带完整家具与细节。只有用户明确要求“白模／空白槽位”才切换空槽模式；两种模式都锁结构与机位，指定资产不变形。

### 建模到渲染的共同事实

- 规划记录空间身份、连接端点、隔断类型、门扇状态和玻璃属性；未知信息标为待确认，不猜成房间或户外。
- HTML 与机位共用 openings.py 编译的真实门窗组件，不在截图时统一开门。
- 主图默认同时带到地面和天花，地毯、灯具、餐桌按表达目的调整比例；特写是补充，不替代主图。
- 截图附当前空间、实际抽样可见的相邻空间及门窗状态，渲染保持连接关系和机位，可深化饰面与光影。
- 可见性与画面比例是有限射线抽样，不是逐像素保证；窄卧室可能只露侧边地面。未确认的开合状态使用显式标注的关闭预览，不代表现场事实。

窄卧室首图须拍全床体：先房内取景，无法自然完整时沿正面轴虚拟后退，冻结near近裁切参数。模型不变，真实截图和可见性共用near并恢复状态；明确标虚拟取景，不冒充实地摄影。渲染不得再次裁床或补回镜头前的剖切遮挡墙。

## 安装与就绪边界

每项安装单元是 `skills/<skill-id>/`，将需要的六项目录安装到目标设备私有 `$CODEX_HOME/skills`；历史 CAD／Blender 等目录已从 main 移出。代码和模板可复制，但 Python、Chrome、字体、原生绘图工具及平台授权必须按各项 `local_runtime.md` 在目标设备配置。

- Git 中不含 API Key、`.runtime`、登录态、客户文件、软件程序或设备缓存。平台 Key 仅在已授权设备本地配置；不能把 Key 放入 HTML、PDF 或 Git。
- 本次以设备当前六项完整去敏快照作为基准；不改业务逻辑，不修改设备安装、平台 Key 或其他设备。
- 粗模截图仅提供布局与机位；参考图提供精细家具身份，真实附图绑定实例，光影重新生成。二维终图不代表精细家具已写回 HTML 三维资产。
- 完整设计用design-brief的common/spaces统一墙顶灯窗和陈设，并真实附入styleReferences。门窗洞口固定，框扇外观、天花饰面和设计照明不锁粗模；风格图不提供建筑或产品身份。HTML按钮只换CMF，不等于原生设计只能换色。
- Windows 建模／机位回归及方案册 PDF 已有目标设备测试记录；原生绘图真实生成能力不因推送 Git 就视为已验证。
- 新安装后旧 TUI 可能尚未发现新增 Skill；按实际情况读取明确入口或在同一工作区新开会话，不中断运行中任务。
- 旧 Ubuntu runtime audit 已从 main 移出；历史提交可回溯，不作为新版安装入口。

## 历史与完整性

- `20260808-历史备份`：旧 main 完整备份。
- `20260907-gpt5.6`：Ubuntu 16项设计 Skill 历史快照。
- 这两个历史分支不因本次 main 更新而改动，也不改写 main 历史。
- `manifest.json` 只登记当前来酷六项基准，旧快照不混入当前清单。
- `FILES.sha256` 记录 `skills/` 全部文件；运行 `node scripts/build-manifest.mjs --snapshot <ISO-8601>` 重建清单。

第三方代码和素材的许可、来源、署名以各自文件为准，不以仓库说明覆盖。
