---
name: interior-html-modeling
description: 当用户要求把已编译户型快速生成可编辑 HTML/Three.js 整屋模型，或在 AI 初稿上直接调整墙、门窗、精细家具、摄像机与灯光时使用。未明确要求 Blender/CAD 时，本 Skill 是默认建模后端。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"model_backend":"html-threejs","floorplan_handoff_schema":"interior.floorplan-handoff.v3","structure_schema":"interior.floorplan-structure.v4","component_layout_schema":"interior.component-layout.v5","native_model_manifest_schema":"interior.native-model-manifest.v1","version":"34.0.0"}
---

# Interior HTML Modeling

## 定位

本 Skill 只有一个产品：`室内户型人机共创模板`。

AI 先从 `floorplan-handoff.v3` 一次生成完整三维初稿，用户再在同一 HTML 中直接修正少量问题。它不是复杂 CAD，也不要求用户从零建模。

唯一活动模板位于：

`assets/interior-coauthoring-template/`

不得保留第二套模板、旧版本目录、按版本命名的 HTML、兼容入口或任务级模板副本。历史报告可以保留文字和截图，但不得保留可再次运行的旧模板代码。

## 输入

- `interior.floorplan-handoff.v3`；
- 其中的 `interior.floorplan-structure.v4` 和 `interior.trace-components.v2`；
- 可选模型范围、产品绑定和 scene rig。

生产任务不重新看图猜坐标，也不运行后置强校验。尺寸、拓扑、墙门窗和对象几何由平面 Skill 同一次算法编译；本 Skill 只消费该事实并立即生成可编辑模型。

## 输出

1. `interior.component-layout.v5`；
2. `coauthoring-model.json` 与 `coauthoring-model.js`；
3. 自包含的 `室内户型人机共创模板.html`；
4. `interior.native-model-manifest.v1`；
5. 用户点击“保存新版 HTML”后得到的完整当前 HTML；它是用户修改后的唯一回传载体，不再要求用户同时管理第二份修订 JSON；
6. `interior.user-returned-html-receipt.v1`，记录旧版摘要、当前摘要、对象数量和原子覆盖结果。

单文件超过 30MB 时不得静默留在本机；按 Bridge 规范走飞书云盘 fallback、拆包或 OSS/CDN。

## 唯一生产流程

1. 用 `import_floorplan_handoff.mjs` 创建项目，禁止从旧项目复制模板代码。
2. 用 `match_trace_components.mjs` 按规范化后的相同 `functionalClass` 匹配受管资产并物化项目实际使用的 GLB。绿色/紫色只表示编辑语义，不能阻止完全相同功能类别的正式资产被采用。没有精确同类资产时必须先补入受管资产再继续，禁止生成色块或轮廓替身。
3. 匹配器自动调用 `compile_coauthoring_model.mjs`，把墙、门窗、房间、精细家具、摄像机和灯光编译为编辑器唯一模型。
4. 用 `build_standalone_html.py` 生成单文件；最终文件不得引用外部脚本、CSS、模型数据或 GLB。
5. 客户生产任务直接交付 HTML。保存按钮旁必须明确提示：“修改后请保存并把新 HTML 发回；模型会把它作为当前版覆盖工作区旧版”。
6. 收到用户回传 HTML 后，只运行 `import_returned_html.py`：从文件内 `#template-data` 读取当前模型，核对项目身份，然后原子覆盖工作区唯一 `current.html` 和 `current-model.json`。不得让旧 HTML、localStorage 或任务目录副本继续成为事实源。
7. 覆盖成功后直接进入非阻断动线提示和算法机位，不再要求平面 Skill 重新确认用户已经明确做出的可逆编辑。

## 交互合同

- 三维和二维共用同一个模型；二维只是正交俯视，不维护第二份墙线。
- 左键空白处旋转、右键平移、滚轮缩放；“适应窗口”按当前屏幕重新居中。
- 结构、组件、场景三个编辑域明确分开，点击对象不得自动跨域。
- 结构页顶部固定一行六个无文字 SVG 扁平按钮：选择、调整墙、添加墙、加窗、加门、删除。每个按钮必须有 `aria-label` 和悬停/键盘聚焦提示，不得用字符图标或把说明常驻挤占侧栏。
- 墙支持选择、双击进入编辑、端点拉长/缩短、磁吸、添加和删除。同一直线只允许端点接触，不允许正长度重叠；墙体只有接近 90° 的垂直相交可以穿越，斜交、穿门窗或穿家具都必须停在最后合法位置。
- 双击墙后，墙厚输入必须出现在当前对象顶部快捷区；修改厚度与拖端点共用碰撞内核，不能挤入相邻平行墙。垂直墙允许相交，不因厚度接触被误拒绝。
- 门窗必须附着宿主墙，可新增、移动、改宽高和删除；二维/三维使用同一坐标逻辑。同墙门窗至少保留 8cm 墙带，不能越出墙端、墙高或被其它墙穿过。
- 组件页顶部固定选择、新增、显隐、删除四个 SVG 快捷按钮；删除不得藏在检查器底部。双击组件显示一个移动点与四个角点，拖任一角点只做宽、深、高等比例缩放，不显示第二套数字缩放控件。
- 组件页支持精细家具选择、移动、旋转、隐藏、复位、缩放和删除；所有正式资产都可按当前对象宽、深、高调整，双击后的四角手柄继续做等比例缩放。地毯允许在平面两个方向独立适配并保持真实薄层高度。禁止退化成通用方盒或半透明色块。拖动和属性修改统一使用来源真实 footprint、竖向范围、户型边界、墙体实段和其它非地毯组件做碰撞判定。
- 所有创建、拖动、立面编辑和数值修改共用同一碰撞内核。接触允许、穿透拒绝；旧 handoff 已接受的嵌入/组合可以保持或沿脱离方向移动，但不能新增或加深穿透。
- 固定柜体、冰箱、洗手盆和洗衣机在模板载入时先做一次确定性固定构件归一化：删除被专用柜完整覆盖的重复通用柜，按最小位移解除边界、墙体和固定构件互穿；不能因为活动椅、桌等源位置关系把柜体推离原墙面。柜体顶部不得高于 `ceilingHeight`（未声明时等于墙高）。
- 场景页支持摄像机和灯光添加、选择与调整。
- 顶栏必须提供独立的“家具”和“空间标志”显隐按钮；图层页继续提供墙、门窗、家具、天花板、吊灯、摄像机、灯光、空间名和网格控制。天花默认隐藏，显示高度等于墙顶；吊灯显隐不得关闭实际光照计算。
- 所有编辑进入统一撤销/重做栈；导入、导出和截图可用。浏览器 localStorage 不能覆盖文件内模型，用户回传的完整 HTML 才是跨会话唯一当前版。
- 机位 Skill 只通过 `__INTERIOR_COAUTHORING_EDITOR__` 的稳定算法桥设置相机、临时隐藏最小遮挡和读取代码投影事实；不得再依赖旧模板私有接口。
- 墙体编辑不得重建精细家具。局部拖动期间只更新当前对象，不能把相机手势和对象手势同时触发。

## 精细家具合同

- 绿色对象只匹配 `movable-green`，紫色对象只匹配 `fixed-purple`。
- 资产必须与来源 `functionalClass` 一致，禁止跨类别替代。
- 正式资产使用受管组件库的真实网格、来源尺寸、方向轴和许可记录。
- `area-rug/floor-rug/carpet` 只作为 `rug` 的规范同义词；其它功能类别不得跨类替代。
- 绿色/紫色是对象可移动或安装语义，不是资产库隔离墙；同功能资产可以来自任一物理分区，项目继续保留原编辑语义。
- 每个对象必须具有 `assetStatus=matched`、真实 `componentId` 和可加载 GLB。匹配不到时在同一任务补充受管资产，禁止输出色块、轮廓体或程序化方盒。
- 项目去重运行资产上限 14MiB，单文件上限 29MiB；不得提高参数绕过。
- 商业发布仍按实际使用资产逐项复核许可，不能用浏览器加载成功代替许可验收。

## 校验边界

客户任务只硬停止于：

- 必需 handoff 缺失或确实属于另一项目；
- JSON 损坏到无法加载；
- 浏览器核心无法启动，用户看不到任何模型；
- 需要付费、公开发布或不可逆动作而未获授权。

轻微同类外观差异、原户型动线问题和可逆编辑不是生产硬停止；但缺少真实资产意味着模型尚未生成完成，必须补库后继续，不能用色块伪装完成。

强结构校验、全库审计、跨屏交互回归和负向扫描只在 Skill 修改/发版时运行。回归失败必须修算法或模板后再发布，不能把失败门禁留给客户任务。

## 发版验收

- `validate_template_ownership.py` 证明全 Skills 只有一个活动模板所有者；
- 活动 Skill 内不存在旧模板目录、版本化模板名或旧公共 API；
- 最终单文件在 Ubuntu Chrome 渲染盒真实打开；
- 受管家具 `matched = furniture total`，未匹配数、色块数和资产加载失败数均为 0；
- 结构顶部恰有六个 SVG-only 快捷按钮且均有 tooltip/无障碍名称；组件删除只在顶部快捷区出现；
- 真实鼠标完成墙选择、端点拖动，期间相机位姿不变且家具不重建；
- `validate_coauthoring_collisions.mjs` 在最终 standalone 中真实拖动家具和门窗、拖四角手柄等比缩放、修改墙厚，并证明固定构件初始穿模为 0、柜体超高、家具互穿/穿墙/越界、门窗重叠、共线墙重叠和斜交墙被拒绝，垂直墙相交被允许；
- 天花板与吊灯两个图层开关真实改变可见状态；所有家具必须生成真实受管网格，隐藏碰撞轮廓不得被误计为资产加载完成；
- 家具和空间标志两个顶栏开关都真实改变可见状态；
- 控制台错误和 WebGL 上下文丢失为 0；
- GCP 共享基线与 Ubuntu 活动副本逐文件一致；
- 不重启 Bridge。

## 高频数据入口

- [AI 可读完整说明书](references/skill-manual.md)
- [人类 A3 图文说明书](SKILL_MANUAL.pdf)
- [同源流程总览](references/skill-flowchart.svg)
- [模板与资产](templates.md)
- [数据合同](data_contract.md)
- [执行流程](playbook.md)
- [脚本职责](scripts_logic.md)
- [本地命令](local_runtime.md)
- [环境边界](ENVIRONMENT_CONTRACT.md)
