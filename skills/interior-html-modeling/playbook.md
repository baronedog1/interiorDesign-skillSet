# 执行 Playbook

## 1. 锁定输入

取得第一 Skill 当前轮 `floorplan-handoff.json`：

- `structure-data.json` 是第一 Skill 从同一墙、开口和空间拓扑编译生成的唯一结构；
- 第二象限提供原图、空间边界和分类证据；
- 第三象限提供红墙蓝窗结构图；
- 第四象限提供绿色活动家具和紫色固定组件描线；固定组件包括柜体、设备、灯具、挂画、镜子等，不再把紫色类误称为只有柜体。
- 运行一次：

```bash
node scripts/import_floorplan_handoff.mjs \
  --handoff <handoff-dir>/floorplan-handoff.json \
  --out <empty-project-dir>
```

- 导入器在写项目目录前调用唯一结构验证器，核对所有文件、哈希、唯一源模型报告、真实房间、面积、墙邻接、开口、`floorplanId`，以及 accepted
  `sourceObjectCandidateIds` 与 `trace-components` 的精确对应。
- 历史项目、其它 Session、裸 JSON 和旧模板不参与补缺。

输入不一致时导入器直接失败，回到第一 Skill 重新生成 handoff，不在本 Skill 修补。

## 2. 锁定来源，单线处理结构修订

1. 导入的 `walls[]`、`windows[]`、`floorBoundary` 和房间多边形是不可改写的来源基线；导入 receipt 始终保存其哈希。
2. 不新增、删除墙，不新增、删除或重命名 `rooms[]`，不修改 `spaceType/topologyClass/areaM2/adjacentRoomIds/connections[]/topology`，也不改变窗洞类别或宿主关系。
3. HTML 只允许用户沿原墙轴拖动既有墙的起点或终点。当前 revision 写唯一 active 端点，同时生成 `structure-edit-patch.v1`，保存来源端点、当前端点、延长量和 trace；窗 offset 联动以保持世界位置。补丁不冒充原图事实。
4. 端点候选必须仍在户型边界内，不破坏窗洞、不压住组件且墙长有效；失败即回滚。若修订要进入 Blender、CAD 或下一轮正式结构，必须把补丁交回 `interior-floorplan-planning` 复核并重新发布 handoff，禁止其它后端直接读取 HTML 私有补丁。
5. 导入器已经完成唯一结构检查；除上述补丁门外，后续不再运行另一套结构解释。运行时来源文件与 receipt 哈希不同，项目作废并重新导入。
6. 打开标注模式，确认每个空间边界、名称和面积直接来自 `rooms[]`；悬停区域必须与同一 polygon 一致。

结构数据禁止嵌入组件目录和 placement。

## 3. 逐个导入上游绿紫对象

本 Skill 不登记对象。每个对象必须已由第一 Skill 的源图候选台账和绿紫描线一对一
生成，导入时只读取：

```json
{
  "traceId": "green-living-sofa",
  "sourceObjectCandidateId": "candidate-object-living-sofa",
  "name": "三人位沙发",
  "semantic": "movable-green",
  "shapeClass": "rectilinear",
  "bbox": {"width": 2.22, "depth": 0.94},
  "center": [2.2, 2.1],
  "rotationY": 0,
  "roomId": "living",
  "typeHint": "三人位沙发"
}
```

- 核对对象 ID 注册表、绿色/紫色数量和唯一源模型报告三者一致。
- 组合图形中的独立轮廓必须已在上游分别登记，禁止后续合并或静默省略。
- 曲面、圆形、L/U 形、有机形和方正形明确分类。
- 对象存在性、轮廓和房间来自 `sourceObjectCandidateId`；中心、方向和宽深来自同一描线。

## 4. 按颜色直接路由

运行：

```bash
node scripts/match_trace_components.mjs \
  --trace <trace-components.json> \
  --out <project>/component-layout.json
```

匹配顺序固定：

1. 绿色只打开 `movable-green/`；
2. 紫色只打开 `fixed-purple/`；
3. 先按 `functionalClass` 和用途排除错误类别；
4. 检查形态、安装方式和尺寸；
5. 最后才使用有证据的风格标签；`styleNeutral` 可以进入任意风格，`excludedStyleIntents` 必须先排除；
6. 普通组件用宽深比例选择最接近的原组件；审核过的直线柜体才可按 `axisScaleRange` 分轴匹配；两者都把描线宽深原值写入 `targetDimensions`；
7. 使用类型文字或明确 `componentHint` 确定唯一原组件。

新中式不得以关键词“中式”直接搜名称。现代中性沙发、封闭通用柜体和木饰面可以组合成新中式；带 `old/vintage/antique/ornate/traditional` 的博古架、屏风和繁复木作只在用户明确要求古典陈设时进入候选。

组件匹配完成后必须在真实浏览器单独查看本项目实际使用的 GLB，并登记 `relationHints.directionalAxes`。至少确认：餐椅 `front`、床 `headboard`、沙发 `back/front`、柜体 `front|back`。轴是 authored 模型事实，不得按包围盒长边或类别猜测。然后只在同一个 `component-layout.json` 登记以下关系提示：

- 每把餐椅的所属餐桌；
- 每张床的宿主床头墙；
- 每张沙发的宿主墙，以及房间内存在电视柜时的目标电视柜；
- 柜门的正面轴和预期房间；
- 餐椅收进桌下只能用受限 `chair-tucked-under-table` 接触记录，不能放宽全局碰撞。

用户明确纠正上游位置或方向时，当前 placement 写入用户权威 `reviewedAdjustment`。动线 Skill
返回 `adjustment-plan.v2/correction-ready` 时，本后端用脚本复算计划和操作摘要，直接写入
动线算法权威 `reviewedAdjustment`，不询问用户。两者都保留不可变 `source*`，不另建第二套 active 布局。

不得先查混合列表、不得跨库、不得 fallback。随后运行：

```bash
node scripts/validate_component_layout.mjs \
  <project>/component-layout.json \
  <project>/structure-data.json
```

确认对象 ID、`quantity=1`、`functionalClass` 与数量等式、每条 `libraryPartition/libraryDirectory`、未纠错对象的中心/宽深/方向与 `source*` 逐项相等；纠错对象必须以 `reviewedAdjustment.previous/active` 闭合。初始对象的空间归属只读取第一 Skill 的逐像素报告，不再用矩形净空近似复判。当前后端只检查资产、边界、墙、开口、组件碰撞和层高；方向、贴墙、房间完整包含、对象净距和通道关系由导出原生模型后的 `interior-circulation-planning` 统一复算。随后至少测试普通组件等比缩放、直线柜体宽深高调整和吊柜删除，确认超出审核范围、超过墙高、越界、穿墙、跨开口和未授权组件互撞会被同一共享算法拒绝并回滚。

## 5. 确认项目物化结果

唯一导入器只从两套活动资产初始化，并从已验证 handoff 物化：

- `structure-data.json`
- `trace-components.json`
- `structure-source.png`
- `scene-rig.json`
- 空 `camera-plan.json` 适配文件
- `floorplan-handoff/` 完整来源包与 `floorplan-import-receipt.json`

组件匹配在后续生成 `component-layout.json`。不要从旧项目复制运行时代码、结构 JSON 或混合组件目录。`init_html_model_project.mjs --template-only` 只用于模板自身 QA。

## 6. 白模和摆放检查

1. 墙、窗台墙、窗上墙、窗框和地板默认白色；活动家具默认白模，可显式切换同一几何的项目材质。未声明 `finishPreset` 时项目材质就是来源 PBR；通用柜体可使用经审核的饰面预设，但不得由饰面反推风格；
2. 玻璃透明但基础色仍为白色；
3. 绿色、紫色数量分别与描线一致；
4. 每个组件的形态和绝对平面宽深与上游一致；位置和方向要么与 `source*` 精确相等，要么有完整用户复核调整，不允许第三种状态；
5. 曲面对象使用真实曲面几何；
6. 第一 Skill 的对象空间报告中声明空间像素大于 0、其它空间像素为 0，活动家具中心位于声明空间，跨开口对象为 0；
7. 所有来源 placement 保留不可变 `source*`；任何当前变换差异都有唯一 `reviewedAdjustment`。地毯保持地面覆盖层语义，不作为承托家具的碰撞阻挡物；
8. `relationHints` 的方向轴和关系引用完整，且没有任何计算字段；正式朝向、贴墙、房间包含、对象净距和通道必须在后续 circulation audit 通过；
9. 对移动、旋转和缩放后的非法候选，离线校验与 `window.__INTERIOR_MODEL_AUDIT__` 使用同一共享算法并一致拒绝；
10. 模板没有预置组件和“可添加家具”清单。

## 7. 交互检查

1. 首屏是完整户型正俯视，不是场景摄像头；平面和三维共用 `Y-up` Orbit 基准及同一鼠标逻辑，拖动后取消“平面”高亮并进入自由三维。
2. 二维依据默认隐藏，开关后画布自适应。
3. 空间筛选支持单选、多选、全选和清空；画布、结构/组件/场景列表和已保存机位同步变化。全选、清空和空房间都有地板；单选/多选保留已选空间地板。
4. 右上角标注开关同时显示空间虚线边界、名称、净面积和外部尺寸；鼠标进入空间时只高亮该空间边界与地面。关闭标注后边界、文字和高亮全部隐藏。
5. 结构页只能拾取 handoff 墙窗；单选空间显示其四周真实墙段，长墙不越过房间边界。墙体显示两个可拖端点，但只允许沿原轴延长/缩短并写结构补丁；窗洞可在同一洞口切换表现样式，洞口尺寸、宿主和类别不变。缺墙、假墙、缺门、空间边界错误或需要新增/删除墙时必须退回第一 Skill，不能用端点补丁掩盖。
6. 组件页只能拾取组件，单击后可隐藏/显示、用方向键移动、画布直接拖动，并可通过方形图标逐件顺时针旋转 `90°`、复位或删除；隐藏不删除槽位事实。
7. 场景页只能拾取光源、摄像头和辅助轴，禁止选中墙或家具；单击、双击和按住拖动本体都必须命中同一场景对象。
8. 组件移动、旋转、合理等比缩放在交互时受边界、墙体、真实开口和组件互撞约束；提交 revision 后必须重跑 circulation audit，浏览器提示不能替代正式动线结论。
9. 两点量尺、撤销、重做、俯视、三维和图层正常。
10. 非法编辑回退并显示具体原因；组件删除保留来源 match 和 `removedSourceTraceIds` 审计。

## 8. 灯光与摄像头检查

1. 默认一盏日光主灯和一个全景摄像头，`scene-rig.json` 显式包含 exposure/ambient/hemisphere/detail 并校验通过。
2. `光` / `摄像头` 两个模式切换后，只出现当前模式的列表、添加命令和检查器。
3. 新增光源后可切换平行光、点光源、聚光灯；开关、位置、亮度、色温和类型专属参数生效。
4. 位置和焦点的 X/Y/Z 滑杆、数字输入及画布三轴相互同步；中心点水平拖动与单轴拖动均生效。
5. 摄像头可自由拖动；开启墙面吸附后，拖动期间保持轻量预览，松手时才计算最近墙并挂载。
6. 16/24/35/50mm 四档镜头、焦距、FOV、直线透视和焦段说明一致生效，所有 `distortion=0`。
7. 对相机或光源执行真实双击后，必须保持对象选中并进入位置拖动；拖动本体或 XYZ 轴会改变 `scene-rig` 坐标。双击相机同时开启实时预览，但不自动进入固定视角。
8. 固定视角只能通过检查器显式“进入视角”或已保存 shot 触发；固定状态内用方向键平移、`W/S` 或滚轮前后移动、双击空白画布调整焦点。退出后的自由视角不改固定机位 JSON。
9. 关闭辅助线只隐藏三轴和焦点连线，光源与摄像头本体仍可见、可选。
10. 当前视角截图不包含三轴、焦点线、网格、选择框或侧栏，且截图后编辑状态恢复。
11. 正式机位固定为 `all-spaces`，只应用带逐项证据的 `hiddenElementIds`，并优先保留 `preserveElementIds`、开口和背景空间；恢复后对象数量和可见性完整还原。
12. 载入本户型 `camera-plan.v8` 后，“已保存机位”位于当前摄像头参数之后，数量与 shots 一致；计划必须绑定 `modelBackend=html-threejs` 和当前 standalone HTML SHA-256。点击后检查器同步三 envelope framing、焦点、位置、零畸变镜头、空间聚焦、逐机位打光和 exposure/ambient/hemisphere/detail。
13. 从一个机位切换到另一个机位时参数以原场景快照为基线，不叠加；再次点击当前机位时原摄像头、原灯光、原选择和原视图完整恢复。
14. 其它 `floorplanId` 不得误载；摄像头视角与 capture 模式不显示任何编辑标记。
15. 导出的场景设置保持 `interior.scene-rig.v1`，不包含临时机位或临时灯光，不覆盖 `camera-plan.json`。
16. 光源与摄像头分别执行至少 500 次连续滑杆输入和 100 步画布拖动；输入期间场景 Rig 重建增量不超过 1，WebGL context 丢失/恢复、program 无效和控制台错误均为 0。
17. 平面和三维进入时均以户型边界中心为 Orbit 焦点；显式点击“预览”后，左上角独立 16:9 画面随相机位置变化，拖动右下角手柄可调整显示大小。切换视图、页签或自由 Orbit 时预览不得消失；导出的 camera-plan evidence PNG/JSON 必须来自同一 HTML 相机状态。
18. 点击无可拾取对象的空白处后，选择状态为 `none`；方向键平移主相机与 Orbit target，且相机到 target 的向量不变。对象或固定机位被选中时不得触发画布平移。
19. 每个 capture shot 的帧可读性为 `true`；槽位引导 Q1 使用墙地同材的水泥毛坯结构，隐藏组件且不绘制槽位轮廓、色块或编号；家具核对 Q2 显示同一资产库家具柜体并保持同一水泥墙地面。两图必须具有相同像素尺寸、相机、几何和结构皮肤，只允许组件显隐不同。完整槽位和 `relationHints` 进入 semantic frame JSON。网格位于户型下方并超出户型边界。开放空间分界需要地面标志时，`relationHints.spaceDividerMarkers[]` 必须引用已存在 semantic divider 并渲染，不能改 handoff 或生成假墙。

## 9. 展厅检查

打开 `component-library/gallery/index.html`：

- 运行目录与 `public-assets.json` 的动态总数和分区数完全一致；公共资产仓完成数等于目录数、失败数为 0；
- 分库筛选、类别筛选和关键词搜索有效；
- 点击后显示对应白模，绿色和紫色组件均可切到同一几何的项目材质；未声明饰面时保留原色 PBR；
- URL 支持 `partition + component` 深链；
- 标准尺寸、缩放、形态、来源语义和许可可见。

目录数据全量离线校验；浏览器抽样至少覆盖每个类别、三个来源与两个分区。源码可编辑性抽样覆盖家具、柜体、卫浴、设备、灯具和饰品；柜体还须覆盖分轴尺寸、墙高门禁和独立吊柜删除。

## 10. 浏览器验收

先检查资源门槛，再用一个真实 Chrome：

- 桌面至少 1440×900；
- 移动约 390×844；
- 检查控制台、画布像素、横向溢出、文字和点击；
- 在桌面真实执行相机/光源单击、双击与直接拖动、预览手柄缩放、平面转三维、空白点击和方向键画布平移；记录坐标、预览尺寸及相机-target 向量，仅调用内部函数不算交互验收；
- 在 390px 移动端确认持续预览和 30px resize handle 不遮挡工具栏、不超出视口，画布非空且无横向溢出；
- 记录 `window.__INTERIOR_MODEL_AUDIT__`；
- 记录 `window.__COMPONENT_EXPLORER_AUDIT__`。

## 11. 构建与交接

```bash
python3 scripts/build_standalone_html.py \
  --project <project> \
  --out <project>/interior-model-standalone.html

python3 scripts/build_component_gallery_standalone.py \
  --project <project> \
  --out <project>/component-library-standalone.html
```

交给机位 Skill：

- 当前 HTML；
- `structure-data.json`；
- `trace-components.json`；
- `component-layout.json`；
- 其中唯一 `relationHints` 及全部 `reviewedAdjustment` 审计；
- `scene-rig.json`；
- 当前项目空机位适配文件；正式 `camera-plan.json` 由机位 Skill生成后回写项目；
- capture 页面提供的 `getSceneSemanticFrame()`；本 Skill 的原生适配器用同一相机同步写 `scene-semantic-frame.v4`、无组件无槽位覆盖的纯水泥 `slot-guided` 图片、水泥墙地加资产组件的 `furnished-qa` 图片、entity-ID mask、room-ID mask 与 native model hash。正式区域来自组件显示状态下的 GPU 可见像素与深度反投影，不得从 PNG 二次识别，也不得用 AABB、凸包或事后重命名替代；只有 Q1 和闭合 JSON 可进入渲染 Skill；
- 浏览器审计。

只交当前任务确定版本，不搜索其它 Session。
