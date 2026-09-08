# HTML 建模 · 编译、编辑与状态交接 说明书

版本：3.1.2

~~~yaml
---
name: interior-html-modeling
description: 将布局 JSON 编译为可离线编辑的完整 Three.js HTML；支持墙门窗、家具库替换、CMF 风格、量尺面积、灯光相机和完整保存往返。
metadata: {version: "3.1.2", category: interior-design}
---
~~~

## 调用场景

### HTML 编辑：不同意图进入不同状态域

本页保留实际业务步骤；蓝色节点链接专题，回源节点明确返回位置。文件逐项列明用途。 效果图链把HTML作为粗模位置/结构参考；按精细家具图片锁款，二维生成不会回写3D网格。

输入：布局 JSON / 当前完整 HTML
输出：可离线编辑 HTML + 场景合同

#### HTML 编辑：不同意图进入不同状态域
- in：当前 JSON 或用户编辑后的完整 HTML；最新编辑是事实源，不拿旧模型覆盖；先读同名需求侧车，已确认功能/习惯/风格落实到布局与CMF；未知或授权推荐不冒称确认；向下游携带同一revision
  - scripts/run.py：模型/风格/资产命令入口
  - ../interior-floorplan-planning/playbook/requirements-interview.md：Agent需求读取与缺口回问
- build：编译一次完整编辑器；建筑、组件、CMF、光源、相机和编辑数据同源；随步骤记录开始、完成、耗时；代码与绘图等待分开。（详见 compile）
  - scripts/engine/python/model.py：生成单文件 HTML 和 scene.json
  - playbook/timing.md：计时口径
  - scripts/engine/python/timing.py：正式命令自动计时
- intent：用户要改什么？；风格、家具、结构/测量、保存不是同一动作
  - playbook.md：编辑职责、家具和动线知识
  - data_contract.md：布局、完整 HTML、材质与机位状态
- cmf：只换风格 → CMF 域；保持 forms、位置、灯光、相机；保留撤销；CLI与UI都保留forms/lighting；克隆墙地顶材质同步。（详见 cmf）
  - scripts/engine/runtime/app.js：applyStyle/restoreCMF 与历史
- asset：家具库 → 实例与材质槽；真实 GLB 同类替换；指定资产按比例与尺寸（详见 library）
  - scripts/engine/runtime/workspace.js：目录选择、资产替换和材质编辑
- edit：结构、量尺与完整保存；墙门窗显式编辑；地面拉尺/面积；完整 HTML 往返后再生成同版 scene（详见 editing）
  - scripts/engine/runtime/app.js：结构、测量、灯光、相机与导出
- in → build：当前数据
- build → intent：已打开
- intent → cmf：风格
- intent → asset：家具
- intent → edit：结构/测量/保存

## 完整文件地图
- MANIFEST.json：发布版本与完整文件清单
- SKILL.md：调用范围、输入输出与关键规则
- SKILL_MANUAL.pdf：面向人的算法说明书
- data_contract.md：布局、完整 HTML、材质与机位状态
- local_runtime.md：运行工具、路径与凭据边界
- manual/skill-flowchart.svg：同源说明书内容与图形
- manual/skill-manual.json：同源说明书内容与图形
- manual/skill-manual.md：同源说明书内容与图形
- playbook.md：编辑职责、家具和动线知识
- playbook/timing.md：六项共用的逐步骤时间、异步等待和历史未知口径
- scripts/engine/LICENSE-Three.js.txt：原第三方运行库许可
- scripts/engine/STYLE-GUIDE.md：风格扩展与 CMF 约束
- scripts/engine/assets/library/PROVENANCE.md：样本来源说明
- scripts/engine/assets/library/dining-chair.glb：餐椅样本
- scripts/engine/assets/library/dining-chair.png：餐椅缩略图
- scripts/engine/assets/library/library.json：三份示例的目录索引
- scripts/engine/assets/library/lounge-chair.glb：单椅样本
- scripts/engine/assets/library/lounge-chair.png：单椅缩略图
- scripts/engine/assets/library/sideboard.glb：柜体样本
- scripts/engine/assets/library/sideboard.png：柜体缩略图
- scripts/engine/assets/textures/fabric-color.png：组件贴图或图像参考
- scripts/engine/assets/textures/fabric-normal.png：组件贴图或图像参考
- scripts/engine/assets/textures/leather-color.png：组件贴图或图像参考
- scripts/engine/assets/textures/leather-normal.png：组件贴图或图像参考
- scripts/engine/assets/textures/manifest.json：机器读取的 manifest.json 数据/格式
- scripts/engine/assets/textures/plaster-color.png：组件贴图或图像参考
- scripts/engine/assets/textures/plaster-normal.png：组件贴图或图像参考
- scripts/engine/assets/textures/stone-color.png：组件贴图或图像参考
- scripts/engine/assets/textures/stone-normal.png：组件贴图或图像参考
- scripts/engine/assets/textures/wood-color.png：组件贴图或图像参考
- scripts/engine/assets/textures/wood-normal.png：组件贴图或图像参考
- scripts/engine/assets/textures/woven-color.png：组件贴图或图像参考
- scripts/engine/assets/textures/woven-normal.png：组件贴图或图像参考
- scripts/engine/catalog/components.json：组件类别和尺寸语义
- scripts/engine/catalog/styles.json：保存新配方
- scripts/engine/python/bootstrap.py：切换 Windows 专用 Python
- scripts/engine/python/cameras.py：初始预设和实体角点
- scripts/engine/python/cli.py：分派 build/import-html
- scripts/engine/python/common.py：生成摘要与文件
- scripts/engine/python/model.py：编译更新后模型
- scripts/engine/python/native.py：import_html 提取当前布局
- scripts/engine/python/native_image.py：实现 native_image 的确定性行为
- scripts/engine/python/render.py：同机位截图；粗模定位/精细参考锁款的实际请求、系列策略与画幅记录
- scripts/engine/python/styles.py：证据记录和 style-add
- scripts/engine/python/timing.py：命令/嵌套步骤计时及Agent动作start/finish
- scripts/engine/python/validate.py：技术输入和业务观察
- scripts/engine/runtime/app.js：importProject/exportProject
- scripts/engine/runtime/architecture-kit.js：门窗和墙构造
- scripts/engine/runtime/components-base.js：家具基元
- scripts/engine/runtime/components.js：组件实例化
- scripts/engine/runtime/controls.js：相机移动和投影
- scripts/engine/runtime/exporter.js：GLB 导出
- scripts/engine/runtime/geometry.js：几何基元
- scripts/engine/runtime/lights.js：光源序列化
- scripts/engine/runtime/materials.js：真实材质参数
- scripts/engine/runtime/native-assets.js：内嵌模型保留
- scripts/engine/runtime/optimization.js：场景优化
- scripts/engine/runtime/scene.js：组装建筑与家具
- scripts/engine/runtime/spatial.js：实体使用区观察
- scripts/engine/runtime/studio.html：完整编辑器模板
- scripts/engine/runtime/style-components.js：风格形体
- scripts/engine/runtime/styles.js：配方角色映射
- scripts/engine/runtime/three-r164.js：Three.js 渲染器
- scripts/engine/runtime/workspace.js：完整状态恢复负责人
- scripts/engine/schemas/cameras.schema.json：机器读取的 cameras.schema.json 数据/格式
- scripts/engine/schemas/layout.schema.json：布局机器结构
- scripts/engine/schemas/style.schema.json：可用配方字段
- scripts/engine/styles/cream/PLAYBOOK.md：配方、资源与实现说明：PLAYBOOK.md
- scripts/engine/styles/mid-century/PLAYBOOK.md：配方、资源与实现说明：PLAYBOOK.md
- scripts/engine/styles/modern-minimal/PLAYBOOK.md：配方、资源与实现说明：PLAYBOOK.md
- scripts/engine/styles/new-chinese/PLAYBOOK.md：配方、资源与实现说明：PLAYBOOK.md
- scripts/engine/styles/wabi-sabi/PLAYBOOK.md：配方、资源与实现说明：PLAYBOOK.md
- scripts/requirements.txt：编译/截图 Python 依赖版本
- scripts/run.py：模型/风格/资产命令入口

## 具体逻辑解释

### 离线编译完整依赖链

按实际输入、计算、分支和文件消费者展开。

#### 编译链：输入到离线页面的全部代码文件
- a：读取、校验、生成模型标识；需求→类别→结构家族→目录componentId；直排/贵妃位由组件选型，不由风格强加；产品改变家族时回布局再编译
  - scripts/run.py：模型/风格/资产命令入口
  - scripts/engine/python/bootstrap.py：切换 Windows 专用 Python
  - scripts/engine/python/cli.py：分派 build/import-html
  - scripts/engine/python/model.py：布局与运行时编译
  - scripts/engine/python/common.py：JSON、文件摘要、运行时摘要
  - scripts/engine/python/validate.py：技术输入和业务观察
- b：结构与风格输入依赖；校验只针对实际字段；初始机位由本布局计算
  - scripts/engine/python/styles.py：风格配方有效性
  - scripts/engine/python/cameras.py：初始预设和实体角点
  - scripts/engine/schemas/layout.schema.json：布局机器结构
  - scripts/engine/schemas/style.schema.json：风格机器结构
  - scripts/engine/catalog/components.json：29 类组件元数据
  - scripts/engine/catalog/styles.json：当前风格配方
- c：按依赖顺序内嵌运行时 · 后半段；编辑器在浏览器执行，数据仍保留在完整 HTML
  - scripts/engine/runtime/exporter.js：GLB 导出
  - scripts/engine/runtime/optimization.js：场景优化
  - scripts/engine/runtime/controls.js：机位控制数学
  - scripts/engine/runtime/lights.js：光源状态
  - scripts/engine/runtime/spatial.js：空间观察
  - scripts/engine/runtime/native-assets.js：内嵌 GLB 实例
  - scripts/engine/runtime/workspace.js：文件选择与整体保存
  - scripts/engine/runtime/app.js：启动、交互、实际截图
- d：单文件页面与运行时 · 前半段；每个文件真实参与离线编译，不虚构文件覆盖；水槽：柜体壳板＋独立盆腔，实心柜块会遮盆
  - scripts/engine/runtime/studio.html：完整编辑器模板
  - scripts/engine/runtime/three-r164.js：Three.js 渲染器
  - scripts/engine/runtime/materials.js：材质构造
  - scripts/engine/runtime/styles.js：CMF 应用
  - scripts/engine/runtime/geometry.js：几何基元
  - scripts/engine/runtime/architecture-kit.js：墙门窗/楼板
  - scripts/engine/runtime/components-base.js：家具基元
  - scripts/engine/runtime/style-components.js：风格形体
  - scripts/engine/runtime/components.js：组件实例化
  - scripts/engine/runtime/scene.js：组装建筑与家具
- a → b：依赖
- b → d：页面编译
- d → c：继续内嵌

### CMF 与智能风格

按实际输入、计算、分支和文件消费者展开。

#### 风格：已知配方直接用，未知风格先真实检索
- a：用户偏好 / 风格名称；五种预设只是起点
  - scripts/engine/STYLE-GUIDE.md：风格扩展与 CMF 约束
- q：已有同名/id 配方？；按中文名、英文名及 id 匹配
  - scripts/engine/python/styles.py：resolve_style 匹配/生成研究请求
- web：未知：宿主联网研究后整理配方；检索颜色、材料、家具/灯光及细节；记录 URL、日期和支持结论；不冒充已检索
  - scripts/engine/python/styles.py：证据记录和 style-add
  - scripts/engine/schemas/style.schema.json：可用配方字段
  - scripts/engine/catalog/styles.json：保存新配方
- apply：CMF 更新材质，不重建形体；HTML按钮只改CMF，保留编辑几何；不是最终设计只能改色；原生渲染另读取完整设计意图
  - scripts/engine/runtime/app.js：applyStyle/restoreCMF/撤销重做
  - scripts/engine/runtime/styles.js：配方角色映射
  - scripts/engine/runtime/materials.js：真实材质参数
- save：当前状态连同配方完整保存；已有独立 GLB 不整件强制刷色；指定资产身份由材质槽编辑保留
  - scripts/engine/runtime/workspace.js：完整 HTML 保存
  - scripts/engine/python/native.py：导回最新 HTML 数据
- a → q：查询
- q → apply：是：直接应用
- q → web：否
- web → apply：配方
- apply → save：更新后

### 真实家具库

按实际输入、计算、分支和文件消费者展开。

#### 家具库：读索引 → 解析真实资产 → 放入明确实例
- a：用户选定本地目录；不扫描整机；索引相对路径必须留在库内
  - scripts/engine/assets/library/library.json：三份示例的目录索引
  - scripts/engine/assets/library/PROVENANCE.md：样本来源说明
  - scripts/engine/runtime/workspace.js：目录选择与筛选
- b：读取样本或实际用户资产；GLB 与缩略图逐项对应；不是全部模型库
  - scripts/engine/assets/library/dining-chair.glb：餐椅样本
  - scripts/engine/assets/library/dining-chair.png：餐椅缩略图
  - scripts/engine/assets/library/lounge-chair.glb：单椅样本
  - scripts/engine/assets/library/lounge-chair.png：单椅缩略图
  - scripts/engine/assets/library/sideboard.glb：柜体样本
  - scripts/engine/assets/library/sideboard.png：柜体缩略图
- q：格式与目标实例匹配？；GLB2 静态三角网格、自包含；不是压缩/骨骼；同类组件；+Z 正面；尺寸和材质槽来自资产
  - scripts/engine/python/native.py：bundle_library 解析与路径检查
  - scripts/engine/runtime/native-assets.js：GLB 读取与实例化
- bad：不支持：预转换或更换正确资产；明确问题文件；不拿矩形占位冒充原模型；尺寸不合适回选型/布局，不压扁指定资产
  - scripts/engine/catalog/components.json：组件类别和尺寸语义
- ok：替换后保留实例位置与身份，再保存完整 HTML；materialOverrides 按材质名；uniform 保持比例；问题报告与模型同时保留
  - scripts/engine/runtime/workspace.js：选定实例替换与材质编辑
  - scripts/engine/runtime/spatial.js：使用区/边界观察
  - scripts/engine/runtime/app.js：状态保存、恢复和撤销
- a → b：索引
- b → q：实际文件
- q → bad：否
- q → ok：是

### 结构、测量和保存

按实际输入、计算、分支和文件消费者展开。

#### 编辑与往返：修改域、量尺、保存、下游更新
- a：结构与使用尺寸；墙门窗引用真实宿主；不得将餐桌认作客厅；床头靠墙、开门/柜门/拉椅与通道按规划事实
  - playbook.md：编辑职责、家具和动线知识
  - data_contract.md：布局、完整 HTML、材质与机位状态
  - scripts/engine/runtime/architecture-kit.js：门窗和墙构造
  - scripts/engine/runtime/spatial.js：实体使用区观察
- b：量尺 / 面积 / 灯光 / 相机；地面两点距离；m/mm；房间多边形面积；24 光源，3 投影射灯；相机由当前用户操作
  - scripts/engine/runtime/app.js：尺、结构/相机交互、项目导出
  - scripts/engine/runtime/lights.js：光源序列化
  - scripts/engine/runtime/controls.js：相机移动和投影
- c：保存完整 HTML 或项目 JSON；包含布局、GLB、材质、配方、测量、光源、相机
  - scripts/engine/runtime/workspace.js：saveHTML 与导入
  - scripts/engine/runtime/native-assets.js：内嵌模型保留
- q：重开与原状态一致？；布局、材质、相机、灯光及量尺逐项查看；不靠重置作品掩盖状态丢失
  - scripts/engine/runtime/app.js：importProject/exportProject
- fix：否：修对应序列化源函数；保留用户当前作品，再回保存步骤
  - scripts/engine/runtime/workspace.js：完整状态恢复负责人
- out：是：新布局重编译后交接；sceneKey/htmlSha256/cameraDigest 同版；机位、渲染、平台读取这份结果
  - scripts/engine/python/native.py：import_html 提取当前布局
  - scripts/engine/python/model.py：编译更新后模型
  - scripts/engine/python/common.py：生成摘要与文件
- a → b：当前编辑
- b → c：保存
- c → q：实际重开
- q → fix：否
- q → out：是
