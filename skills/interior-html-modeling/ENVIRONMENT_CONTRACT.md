# Environment Contract

## 多设备运行规则

- 下文 Ubuntu 路径只作已验收示例；正式入口由 `CHROME_BIN`、`INTERIOR_COMPONENT_ASSET_STORE` 和设备 runtime inventory 决定。
- 浏览器与版本化组件仓由管理员预装/同步，任务不得下载浏览器、访问 CDN 或从其它设备目录读取资产。
- 只有实际执行账号通过资产 manifest、桌面/390×844、WebGL2、console、非空 canvas 与模型 hash 验收后才为 `ready`；缺浏览器或资产仓时为 `blocked`。

- 共享权威源：`/home/baronedog111/gcp-manager/skills/interior-html-modeling`。
- Ubuntu 安装副本：`/home/agentops/.codex/skills/interior-html-modeling`；百亿和百万共用内容，工作区与 Bridge 仍隔离。
- Ubuntu 公共组件资产仓：`/home/agentops/agent-runtime/shared-assets/interior-component-library-v5`，可用 `INTERIOR_COMPONENT_ASSET_STORE` 显式覆盖。
- Skill 是唯一 HTML 模板和公共组件目录维护者；其它 Skill、历史项目和一次性交付 HTML 不得成为新任务模板。
- Skill 只保存 catalog、精确成员/排除清单、加载器和小型模板，不保存数百个二进制模型。资产仓保存 source/runtime/previews/receipts/inventory；项目按 placement 取入所需 GLB。
- Poly Haven 源码在采集阶段通过官方 API 获取完整可编辑 glTF 依赖树并确定性转换为运行 GLB；ABO 直接保留其原始 GLB。每份回执保存源码树逐文件哈希。正式项目运行离线，不在浏览器访问外部 API。
- `public-assets.json` 只由明确的资产采集审计任务生成；平台分类快照只读取得，不改生产平台。
- Poly Haven 为 CC0，可自动进入商业/发布。ABO 数据集官网和桶内许可为 CC BY 4.0，但 AWS Registry 仍显示 CC BY-NC 4.0；研究模式可用，商业/发布模式必须阻塞到人工许可复核完成。冲突、作者、来源、许可和修改说明必须保留在项目 lock。
- 水泥毛坯纹理由模板内确定性 CanvasTexture 生成，覆盖墙和地板；测距网格独立位于户型下方并延伸到户型外。
- Three.js、OrbitControls、GLTFLoader 随 Skill 打包。源码可编辑性抽样使用 Ubuntu 已安装 Blender 或等价 glTF 工具。
- 品牌/SKU 单品由 `movable-furniture-modeling` 维护，不得复制到公共 catalog。
- 平台项目、凭据、上传和社区发布只由 `idk-canvas-ingest-agent` 维护。本 Skill 不读取平台 secret。
- 正式 `camera-plan.json` 由 `interior-camera-capture` 生成；本 Skill 只载入并执行。
- 同步后必须运行目录、许可、资产仓、脚本语法、standalone 和浏览器验收。
