# Data Contract

推荐目录不构成门禁。输入通过 schema、`floorplanId`、revision、artifact role 和 SHA-256 发现；同内容放在不同目录可以使用，内容身份冲突不能使用。

## 输入

- accepted `interior.floorplan-handoff.v3`；
- handoff 绑定的 `floorplan-structure.v4` 与 `trace-components.v2`；
- 可选 `model-scope-request.v1`，默认整屋；
- 可选用户指定产品绑定，只能绑定同一功能槽位。
- 可选用户回传的完整 HTML；必须由本模板“保存新版 HTML”生成，且文件内 `meta.documentRole=user-returned-current-html`。

`trace-components.objects[]` 每个原子对象必须具有：

- `traceId/sourceObjectCandidateId/roomId/semantic/functionalClass/quantity=1`；
- 米制 `center/bbox/rotationY` 与精确 `shapeEvidence`；
- `orientation.evidence` 和 `orientation.localAxes`，声明 `front/back/headboard`；
- 可选 source-evidenced assembly 关系。

## `interior.floorplan-structure.v4`

结构只从 handoff 编译：

- 墙、房间、地面、门、推拉门、开放通道和窗；
- `boundaryFeatures[]` 中的栏杆、矮墙、开放边和落地玻璃；
- 开放边不生成墙，栏杆不生成房间，窗不生成通行连接。

HTML 后端只物化这些事实，不拥有阳台替换模式或第二套开口推断。

## 用户回传 HTML

编辑器不原地改写 accepted handoff。每次墙、门、窗或家具修改仍进入统一撤销栈，并可记录 `interior.structure-edit-patch.v2`：

- `entityType/entityId/operation`；
- 修改前后的对象快照；
- `authoredBy=human-in-editor`、时间和 `reversible=true`；
- 涉及宿主时记录 `hostWallId`，级联删除时记录被删除的门窗 ID。

点击保存后必须下载完整 self-contained HTML，当前模型同时写入 `#template-data`。`import_returned_html.py` 从这里提取模型并原子覆盖工作区唯一当前 HTML/JSON，输出 `interior.user-returned-html-receipt.v1`。localStorage、旧 HTML 和独立 patch 文件都不能比用户回传 HTML 更有权威。

## `interior.component-layout.v5`

每个来源原子对象恰好对应一个 match 和一个 placement：

- `matchMethod=same-functional-class-nearest-fit|explicit-proportional-source-route`；
- `source.matchPolicy=canonical-functional-class-project-budget-v3`，并绑定 `interior.project-runtime-asset-budget.v1`；预算按当前项目实际使用的唯一资产去重计算，不能按 placement 重复计费，也不能由打包命令放宽；
- `functionalClass` 必须与资产受管标签完全相同；仅 `area-rug/floor-rug/carpet -> rug` 是登记过的规范同义关系；
- `assetStatus` 必须为 `matched`，`componentId` 必须指向真实受管 GLB；不存在色块或轮廓替身状态；
- 所有资产保留真实网格并支持宽、深、高尺寸调整和方向旋转；四角手柄默认等比缩放，地毯可按平面尺寸独立适配；
- `position/sourcePosition` 与 handoff 一致；
- `planFootprintRotationY/sourceRotationY` 与 handoff 一致；
- `rotationY` 是根据源语义轴和资产校准轴计算出的模型 yaw；
- `worldOrientation` 给出模型校准后的世界方向；
- footprint 始终使用源轮廓和 `planFootprintRotationY`，不能用 GLB 包围盒反写。

组合柜由多个 placement 和一个只含成员关系的 assembly 构成，组合本身不是巨型资产。

## `interior.layout-relation-hints.v3`

只保存简洁事实：

- `directionalAxes`：资产经浏览器复核的局部轴；轴标签与资产目录同版本发布，必须具有唯一资产 ID、合法角色和值；
- `worldOrientations`：placement 的 yaw 和世界方向向量；
- `facing`：餐椅到餐桌、沙发到电视柜等目标；
- `wallAttachment`：来源图已证明的床头、沙发背面或柜体安装面宿主墙；
- `allowedContacts`：仅逐对声明餐椅收进餐桌等来源允许接触。

它不保存距离、通过结论或动线结果；这些由动线 Skill 独立复算。

## `interior.native-model-manifest.v1`

绑定 handoff、结构、布局、standalone HTML、原生 OBB 测量适配器、截图适配器、model scope 和所有摘要。原生模型必须能在浏览器加载、切换水泥/原色、显示结构与组件，并暴露确定性测量和截图接口；两个适配器都不拥有机位选择。截图适配器从唯一 `hiddenElementIds` 派生墙、窗框和组件的运行时显隐，不能漏掉合法窗框 ID。

## 真正硬停止

- 输入摘要、项目或 revision 冲突；
- 必需结构或原子对象缺失；
- 资产文件损坏，或正式 accepted 模型无已确认 revision 却改变上游结构/数量/位置；
- standalone 或 manifest 摘要不闭合。
- 同类候选经过项目级组合择优后仍超过 14 MiB 运行资产或 29 MiB self-contained HTML 预算。

目录、轻微同类外观差异、可逆缩放、原布局动线风险和执行时长都不是硬停止。
