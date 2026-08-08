---
name: interior-html-modeling
description: 当用户说“对这个户型建模”“只对这个空间建模”“做户型白模”“做 Three.js / 可交互 HTML / 3D 空间模型”，未指定 Blender/CAD 后端而要求整屋或指定空间建模，或要求在平面/三维中编辑相机、灯光、天花、窗型、阳台围护、墙端点、组件与持续预览时使用；整屋与单空间必须从同一 accepted handoff、同一模板、同一组件匹配器和同一碰撞链编译，只通过 model-scope 声明范围，生成 self-contained HTML 与原生模型清单供统一机位、渲染和交付链继续使用。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"model_backend":"html-threejs","floorplan_handoff_schema":"interior.floorplan-handoff.v3","model_scope_schema":"interior.model-scope.v1","structure_schema":"interior.floorplan-structure.v3","trace_components_schema":"interior.trace-components.v2","component_layout_schema":"interior.component-layout.v4","relation_hints_schema":"interior.layout-relation-hints.v2","scene_rig_schema":"interior.scene-rig.v1","camera_plan_schema":"interior.camera-plan.v8","native_model_manifest_schema":"interior.native-model-manifest.v1","custom_component_registry_schema":"interior.custom-component-registry.v3","public_component_catalog_schema":"interior.public-component-catalog.v5","component_library_version":"5.0.0","version":"17.0.0"}
---

# Interior HTML Modeling

所有上游文件先按 [data_contract.md](data_contract.md) 的 `semantic-content-first-v1` 发现；推荐目录和文件名只用于排序。阳台围护只能裁切到对应房间 polygon 的真实边界区间，混合墙的客厅区间必须保留原墙体。

## 使用前准备

- 管理员预装 Node.js 20+、Python 3.10+、非 Snap Chrome/Chromium + WebGL2，并提供版本化公共组件资产仓；通过 `CHROME_BIN` 与 `INTERIOR_COMPONENT_ASSET_STORE` 指向设备路径。
- 先读取 [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) 与 [local_runtime.md](local_runtime.md)，完成资产 manifest、Three.js 加载、桌面/390×844、console、WebGL2 和非空 canvas preflight。
- 必须已有 accepted `floorplan-handoff`；浏览器、资产仓或 handoff 缺失时在编译前标记 `blocked`，不得任务内下载浏览器、用 CDN 或项目临时方盒替代公共组件事实源。

## 目标

把 `interior-floorplan-planning` 已确认的户型事实确定性编译为唯一可编辑 HTML。整屋与单空间只有一个编译器；单空间仅用 `interior.model-scope-request.v1` 选择主空间和必要相邻上下文，禁止另写局部 HTML、手工几何或项目专用家具。不要重新识图、修墙、移动来源对象或从历史项目复制 JSON。

本 Skill 同时拥有室内链唯一的通用组件目录，但不拥有单品建模方法：

- `assets/base-floorplan-template/`：唯一户型 HTML 模板。
- `assets/component-library/catalog/public-assets.json`：公共组件元数据唯一事实源。
- Ubuntu 受管资产仓：公共组件源码、运行 GLB、预览和逐项哈希唯一二进制事实源。
- `movable-green/` 与 `fixed-purple/` 只是上游描线语义分区，不再各自拥有另一套模型来源或材质规则。

## 触发与路由

- 户型建模、单空间建模、白模、交互 HTML、Three.js 空间：使用本 Skill；单空间不是新后端或新模板。
- 用户只说“对户型建模”且没有指定后端：默认使用本 Skill。
- 用户明确要求 Blender、`.blend`、CAD、STEP 或 Text2CAD：分别使用 `interior-blender-modeling` 或 `interior-cad-modeling`；三个建模 Skill 不互相调用。
- 只有户型图/CAD/草图：先调用 `interior-floorplan-planning`，同任务继续本 Skill。
- 单个沙发、桌、椅、柜或品牌 SKU 建模：调用 `movable-furniture-modeling`；完成后本 Skill 只导入验收包。
- 模型 accepted 后：先调用 `interior-circulation-planning` 独立复核连接、动线和摆放关系；合格后再调用 `interior-camera-capture`。
- 保持空间不变出效果图：调用 `interior-space-rendering`。
- 项目创建、上传、HTML 预览和社区发布：调用 `idk-canvas-ingest-agent`。

## 高频数据入口

- 数据对象、ID、哈希与交接：[data_contract.md](data_contract.md)
- 天花、灯具、窗型、阳台、墙端点补丁和连续碰撞：[references/backend-architectural-options.md](references/backend-architectural-options.md)
- 固定执行、质量门与失败恢复：[playbook.md](playbook.md)
- 模板、公共目录与资产仓结构：[templates.md](templates.md)
- 脚本职责与退出条件：[scripts_logic.md](scripts_logic.md)
- 本地命令与浏览器验收：[local_runtime.md](local_runtime.md)
- 设备、共享仓和许可环境边界：[ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)

## 唯一事实源

| 事实 | 唯一位置 |
|---|---|
| 户型墙窗、空间、连接和源对象 | 当前 `floorplan-handoff.v3` |
| 整屋或单空间编译范围 | 项目 `model-scope.json`，只能由 importer 从 `model-scope-request.v1` 编译 |
| 公共组件条目、标签、许可和运行路径 | `assets/component-library/catalog/public-assets.json` |
| 公共组件可承接的原子功能类别 | `assets/component-library/catalog/functional-class-tags.v1.json` |
| 公共组件精确成员 | `assets/component-library/catalog/public-asset-selection.json` |
| 未通过来源/格式/几何审计的对象 | `assets/component-library/catalog/source-asset-exclusions.json` |
| 平台分类与风格枚举快照 | `assets/component-library/catalog/platform-taxonomy.json` |
| 公共组件二进制与校验回执 | `$INTERIOR_COMPONENT_ASSET_STORE` |
| 当前项目使用了哪些组件 | 项目 `component-layout.json` |
| 当前组件的审阅方向轴与关系目标提示 | `component-layout.json.relationHints` |
| 朝向、贴墙、房间归属、净距、通道和连接是否通过 | `interior-circulation-planning` 的当前 `circulation-audit.v2/result.v2` |
| 当前项目实际取入的模型和哈希 | 项目 `component-assets.lock.json` |
| 自定义单品 | 项目 `custom-components/registry.json` |
| 灯光与编辑相机 | 项目 `scene-rig.json` |
| 正式截图机位 | 项目 `camera-plan.json`，由机位 Skill 维护 |
| HTML 后端身份、模型哈希和截图适配器 | 项目 `native-model-manifest.json` |

## 公共组件硬规则

1. 正式目录中每一项必须是可编辑源码派生的真实 glTF/GLB，`builder=external-gltf`、`primitiveBoxOnly=false`。旧方盒家具、旧程序化柜体、旧挂画、旧吊灯和项目原创通用饰品全部退出正式目录。
2. 公共目录当前由 Poly Haven、Amazon Berkeley Objects 与 Sweet Home 3D 官方列出的 BlendSwap CC0 库组成。数量、分类和来源以 `public-assets.json` 动态统计为准，不在其它文档手写第二份清单。
3. Poly Haven 模型为 `CC0-1.0`，可自动进入研究、商业和发布链。ABO 数据集官网与桶内许可声明 `CC-BY-4.0`，但 AWS Registry 仍显示 `CC-BY-NC-4.0`；研究使用允许，自动商业与社区发布必须阻塞并等待人工许可复核。ABO 始终随项目 lock 保存作者、来源、许可、冲突状态和修改说明。
4. Poly Haven 只从逐项审阅的室内资产白名单收录；ABO 只有标题类别与官方 `product_type` 类别一致时才能进入候选。禁止用宽泛关键词或数量配额补齐目录，禁止把工具、游戏设备、户外路灯等错类资产塞进室内组件库。
5. 每项必须保存来源 URL、API/数据集、作者、许可、可编辑格式、源色/PBR、标准尺寸、安装方式、用途、颜色、平台分类和标签。入选清单是唯一成员事实；远端缓存里多出来的模型不能自动进入目录。
6. 沙发必须有 `seatingCapacity`。风格、材质、颜色、用途必须分字段维护：木色不等于中式，名称含 Chinese 不等于新中式。无法从造型和来源证据判断风格时写 `styleNeutral=true`，不得猜测。
7. 一体成型塑料椅等通用品不写假风格，使用“简易、大排档、户外、易清洁”等用途标签。
8. 所有绿色和紫色组件均使用同一几何提供 `white-model` 与 `source-color`。默认白模；切换源色只换材质，不改变 ID、位置、比例或碰撞脚印。
9. 默认只允许等比例缩放。仅目录明确标记 `axis-limited` 的直线柜体可在审核范围内分别调整宽、深、高；软包、洁具、灯具和自由曲面不得非等比拉伸。调整后的落地组件顶面、吊柜“离地高度 + 柜高”必须低于墙高 `0.05m`。
10. 多层柜体优先拆成独立地柜、吊柜、高柜和台面设备模块。只有目录声明的独立模块或真实 glTF 节点可以隐藏/删除；禁止用材质名、网格序号或视觉猜测伪造“可删层”。
11. “新中式”先选现代、简洁、比例合适的中性家具和通用封闭柜体，再以木饰面、留白和配色表达；`old/vintage/antique/ornate/traditional` 资产不得自动匹配。博古架、仿古屏风只在用户明确要古典陈设时使用。
12. 初始位置、方向和碰撞脚印由项目来源描线决定；公共模型决定可见三维外形。当前值只有
    两种合法修正来源：用户明确布局纠正，或 `interior-circulation-planning` 的
    `adjustment-plan.v2` 唯一摘要绑定可逆操作。两者都用同一个 `reviewedAdjustment`
    保存来源、当前值和证据；当前值成为唯一执行事实，`source*` 永远只保留溯源证据。
13. 大型二进制不复制进 Skill。项目只按 `component-layout.json` 取入实际使用的模型；standalone 也只内联当前项目用到的 GLB。
14. 组件“正面、背面、床头端”等方向必须来自真实 GLB 的浏览器审阅轴，不得从文件名、包围盒长边或品类常识猜测。HTML 只提供方向轴和可选目标/墙体提示；餐椅朝桌、床头贴墙、沙发背贴墙、沙发朝电视柜、柜门朝内以及动线净宽全部由 `interior-circulation-planning` 的统一算法复算。

## 执行顺序

1. 在空目录运行 `import_floorplan_handoff.mjs`。导入器只接受本轮附件对应、哈希闭合且状态 accepted 的 handoff。整屋不传 scope；单空间传 `--model-scope model-scope-request.json`，由导入器确定性生成 `model-scope.json`。请求只声明主空间、必要相邻上下文和原因，不能携带另一套墙、门窗、家具或模板。
2. 读取 `trace-components.json`；每个 accepted `sourceObjectCandidateId` 必须一对一进入 match 和 placement，不补造、不合并、不删除、不平移避碰。空户型项目也只能读取上游已确认原生平面布局产生的对象事实，不得在三维阶段重新设计。
3. 运行 `match_trace_components.mjs`。每条 trace 必须为 `quantity=1` 的原子对象，并先按完全相等的 `functionalClass` 与绿/紫分区过滤；之后才比较形态、尺寸和有证据的风格。没有同功能资产时停止，禁止把餐桌降级成茶几、坐便器降级成洗手台或跨类别 fallback。
4. 用户明确要求补齐、但原图没有清晰描线证据的功能对象，只能追加为 `user-explicit-addition`，记录用户指令和设计新增 ID；不得伪造来源 trace。新增对象从一开始就执行房间、墙、开口、碰撞和层高检查。
5. 正式导入不保留模板空布局。匹配器先撤销旧输出，再按“同绿紫分区 + 同原子 `functionalClass` + 同轮廓类别 + 资产允许的比例/轴向缩放”选中组件；同类别多个合格资产按风格、尺寸、文本分数和稳定资产 ID 确定性择一，不要求用户确认。随后自动调用 `materialize_component_assets.mjs`，只取当前项目组件并生成 `component-assets.lock.json`。资产仓不可用、任一资产未通过仓库校验或项目文件哈希不符时，不得写出正式 `component-layout.json`；全部成功后才原子提交。不存在 `deferred`、方盒占位或临时重模分支。
6. 如用户指定单品，使用 `import_custom_component_package.mjs` 导入已验收 v3 包；禁止把项目单品悄悄写回公共目录。
7. 打开 HTML，核对 handoff 墙窗和空间保留为可追溯来源；结构页不得增删墙、改房间或改开口类别，唯一允许的局部结构编辑是沿原轴拖动既有墙端点，并生成 `structure-edit-patch.v1`。每件组件可隐藏/显示/删除/移动/旋转/复位，且白模/源色均来自同一模型。为实际使用的组件登记浏览器审阅方向轴和可选目标/墙体提示；不得在本 Skill 自报餐椅、床、沙发、净距或通道已经通过。审核过的直线柜体显示宽深高控件；其它组件只显示等比尺度。
8. 平面和三维进入时都以户型包围盒中心为 Orbit 焦点。场景页中相机、灯光本体支持单击选中、双击进入编辑和直接拖动；预览窗可从右下角缩放并保持 16:9，切换视图或页签不消失。点击空白取消对象选择后，方向键平移整个画布焦点。水泥毛坯皮肤是结构默认状态并同时覆盖墙和地板，测距网格位于户型下方并延伸到户型外。Q1 隐藏组件且不显示槽位覆盖，Q2 显示同一家具柜体白模；两者保持同一水泥墙地面、相机和模型状态。semantic frame 必须导出组件完整 placement 与 `relationHints`，供下游 JSON 表达位置、朝向目标和贴墙关系。天花可一键显示/隐藏；灯具使用可编辑资产与 scene rig；窗框可在同一洞口内切换样式；阳台可按证据选择开放栏杆或封闭玻璃；墙端点编辑只能沿原轴并导出结构补丁；组件拖动必须连续碰撞并停在首次接触处。
9. 初始来源锁定 placement 不用第二套近似算法推翻上游事实。用户明确新增、用户在 HTML
   编辑或带合法 `reviewedAdjustment` 的纠错 placement，只在本 Skill 执行边界、墙、
   真实开口、组件碰撞和层高即时检查；失败即回滚。方向、贴墙、房间归属、家具净距和
   通道只在导出当前模型后由动线 Skill 正式计算。
10. 运行数据、组件目录、资产仓、模板、scene rig、standalone 和浏览器验收。
11. 运行 `export_native_model_manifest.mjs`，把 standalone HTML、模型范围、模型哈希、公共坐标变换和 `capture_html_views.mjs` 写入 `native-model-manifest.json`。
    `capture_html_views.mjs` 只是后端适配器，正式截图只能由 `interior-camera-capture/scripts/capture_model_views.py` 调度。调度器先验证相机和设备压力，再持有全局截图槽位；适配器在页面脚本执行前把外部 accepted `camera-plan.v8` 锁定为唯一运行时机位。standalone 内嵌历史机位只能供交互预览，不能覆盖正式计划；禁止项目脚本直接启动 Chrome 或事后补截图字段。
12. 将 handoff、当前 `component-layout.v4`、原生模型清单和模型哈希交给
    `interior-circulation-planning`。若返回 `correction-ready`，立即运行
    `apply_circulation_adjustment.mjs` 应用唯一选中操作，不询问用户；重新构建 standalone、
    导出新 manifest 并全量重审。只有 `circulation-result.v2` 放行后才能找机位。
13. 用户要求上传或社区发布时，把已验收产物交给 `idk-canvas-ingest-agent`；本 Skill 不读取平台凭据。

## 核心命令

```bash
node scripts/import_floorplan_handoff.mjs --handoff <handoff-dir>/floorplan-handoff.json [--model-scope <model-scope-request.json>] --out <empty-project>
node scripts/match_trace_components.mjs --trace <project>/trace-components.json --out <project>/component-layout.json [--commercial|--publish]
node scripts/apply_circulation_adjustment.mjs --layout <project>/component-layout.json --plan <project>/circulation-adjustment-plan.json --out <project>/component-layout.next.json
python3 scripts/build_standalone_html.py --project <project> --out <project>.html
node scripts/export_native_model_manifest.mjs --html <project>.html --handoff <project>/floorplan-handoff/floorplan-handoff.json --structure <project>/structure-data.json --components <project>/component-layout.json --model-scope <project>/model-scope.json --backend-options <project>/backend-options.json --capture-adapter scripts/capture_html_views.mjs --out <project>/native-model-manifest.json
```

完整公共目录浏览只在 Ubuntu 通过 HTTP 读取受管资产仓。飞书交付用抽样 standalone，不把数百个模型塞进一个 HTML。

## 验收

### 目录与许可

- `validate_component_library.mjs`：运行目录与 canonical JSON 完全一致；所有类别至少 20 项；标签、沙发人数、实用椅例外、双外观和许可完整。
- `validate_public_asset_store.mjs`：所有计划项都有完整源码树、有效 GLB、逐文件哈希回执；失败数为 0。Poly Haven 的 `.gltf`、`.bin`、纹理和官方文件描述缺一不可。预览缩略图缺失只记 warning，不得把有效 3D 源码判失败。
- Skill 内不存在旧 `movable-green/assets`、旧 asset manifest、程序化通用 builder 或二进制全量副本。
- 当前全部目录项允许本次研究使用；`--commercial/--publish` 只放行 `commercialUseAllowed=true`。ABO 条目因官方登记冲突必须在自动门禁失败，不能由 Agent 自行忽略。

### 项目与浏览器

- `component-layout.json` 与 `component-assets.lock.json` ID 集合一致，缺模型或哈希变化立即失败。
- `model-scope.json` 必须把全部来源房间唯一分为主空间、允许上下文和排除空间；单空间运行时只能显示前两者。其模板、组件目录、碰撞、场景和截图适配器必须与整屋完全相同，`customProjectGeometryAllowed=false`。
- 抽样至少覆盖每个类别、两个来源和绿/紫两分区；白模与源色截图不同但几何边界相同。
- 抽样源码可在 Blender 或等价工具中导入、选择网格并编辑；`axis-limited` 柜体须验证三个轴的上下界、墙高门禁和吊柜独立删除。
- Chrome 桌面和 390px 移动端画布非空，GLB 加载失败、控制台错误、WebGL context loss 均为 0。
- 平面/三维居中、预览窗缩放、相机/灯光单击或双击选中与直接拖动、空白画布方向键平移、持续实时预览、水泥墙地、天花显隐、窗型切换、结构补丁导出、连续碰撞停止、户型外测距网格以及组件逐件操作全部通过。
- `relationHints` 的浏览器审阅轴、目标/墙体引用和允许接触声明完整；不得包含距离、点积、净空、房间归属或通过结论。正式朝向、贴墙、房间完整包含、家具净距和过道净空必须由同模型的 `circulation-result.v2` 通过。
- 开放空间需要视觉分界时，在 `relationHints.spaceDividerMarkers` 只引用上游 `semanticDividers[].id` 并渲染低矮地面标志；不得改写 handoff，也不得为客厅/阳台等开放分界新增假墙。
- standalone 只包含当前 placement 使用的模型；不存在未使用模型二进制；单资产 `≤8MB`、原始资产合计 `≤18MB`、最终单文件 `<29MB`，超限必须使用 webStandalone 优化变体或停止，禁止生成 100MB 级文件。

## 交付

- 当前项目或 self-contained standalone HTML；
- `native-model-manifest.json` 与正式截图调度器产生的 HTML 原生截图回执；
- `floorplan-handoff/`、导入 receipt、`model-scope.json`、`structure-data.json`、`component-layout.json`、`component-assets.lock.json`、`scene-rig.json`；
- 当前目录 JSON、资产仓 inventory 和机器可读验收报告；
- 公共组件抽样展厅、桌面/移动端截图；
- 来源与许可说明。

飞书任务不得只给 `/home/agentops/...` 路径。大文件按飞书云盘、OSS/CDN 或平台项目交付；研究限定资产不得发布到公开社区。
