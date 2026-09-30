# 可编辑模型与定制节点

版本：5.0.2

```yaml
---
name: interior-html-modeling
description: 将布局 JSON 编译为可离线编辑的完整 Three.js HTML；支持墙门窗、家具库替换、CMF 风格、量尺面积、灯光相机和完整保存往返。
metadata: {version: "5.0.2", category: interior-design}
---
```

总分结构：1 张总图；3 张来自主节点的展开。

## 1. 总图 · 从用户当前布局到可编辑模型

触发：用户要求按当前布局制作或继续修改可编辑室内模型；输入：用户提供当前布局、同版需求或最新完整模型；输出：完整离线模型、同版场景及待核说明
布局：semantic-grid；选择理由：按因果顺序折行；构造、执行模块及保存交接分别展开，完整路径保持可读字号。

### n0 · 用户给布局或最新完整模型
读取同版需求；已有用户修改以最新完整模型为准。
- [入口] `SKILL.md`：接收布局、最新模型及用户要求，确定本次建模与交付范围

### n1 · 选择对象方法与用户参数
已确认尺寸和偏好只约束本项目；未知与允许发挥分开。
- [方法] `playbook/rule-selection.md`：区分通用构造方法与本项目尺寸、偏好和明确覆盖
- [方法] `local_runtime.md`：说明运行依赖、正式命令以及维护说明书和安装副本的方法

### n2 · 按真实尺寸构造板件和节点
选择结构家族、独立台面与真实门窗；资源用途见展开。
- [方法] `playbook/joinery.md`：按板厚、分区、独立台面孔与锚点构造柜桌及床台
D1 · 展开见第2页

### n3 · 生成当前离线编辑模板
正式构建同时输出完整页面、当前布局与绑定场景。
- [执行] `scripts/run.py`：将正式建模命令路由到本包引擎，并记录命令时间
D2 · 展开见第3页

### n4 · 编辑关联、保存并交接同版
以最终完整页面恢复编辑状态；交接当前需求与版本。
- [模块] `scripts/engine/runtime/workspace.js`：处理结构与家具编辑、量尺、撤销重做及完整HTML保存和导入
D3 · 展开见第4页

### n5 · 用户获得完整模型与场景数据
交付可离线编辑的完整页面和同版场景；待核事项保留说明。
- [数据] `data_contract.md`：规定布局、编辑状态、场景摘要和同版需求交接

连线：
- n0 → n1
- n1 → n2
- n2 → n3
- n3 → n4
- n4 → n5

## 2. D1 节点展开 · 把结构、家具和材料落实到构造事实

展开范围：只展开主图的真实尺寸构造节点；资源按本次对象需要读取，不增加统一建模门禁。；进入条件：构造或选型时需要查明板件、门窗、家具库与材料样件的用途
来源：总图 `main` 的 `n2`（按真实尺寸构造板件和节点）；返回 `n3`（生成当前离线编辑模板）。
布局：semantic-grid；选择理由：按因果顺序折行；构造、执行模块及保存交接分别展开，完整路径保持可读字号。

### method · 按用途和确认尺寸确定构造
柜体分段、板厚、面板分区与台面孔来自构造参数。
- [方法] `playbook.md`：说明家具结构、风格、量尺、灯光和完整保存的实际行为
- [方法] `playbook/joinery.md`：按板厚、分区、独立台面孔与锚点构造柜桌及床台
- [数据] `playbook/examples/cabinet-run.json`：演示柜体整组生成的分段尺寸、拼接和台面请求
- [数据] `playbook/examples/joinery-layout.json`：演示柜桌、台面、床台、吊顶与显式锚点的布局

### connection · 保留墙门窗和编辑关联
门窗依真实宿主与开合；关联变化回写同一布局。
- [方法] `playbook/editor-model.md`：说明统一模型编辑、墙角接缝、关联重建和旧数据迁移
- [方法] `playbook/space-connections.md`：定义门窗宿主、开合、填充和空间两端的源事实

### library · 按类别和尺度选择家具样件
明确结构家族和缩放政策；库内三件样品不代表完整产品库。
- [配置] `scripts/engine/catalog/components.json`：登记支持的组件类别、默认尺寸和参数范围
- [配置] `scripts/engine/assets/library/library.json`：登记样件类别、尺寸、缩放政策、文件与缩略图
- [登记] `scripts/engine/assets/library/PROVENANCE.md`：记录样件模型来源与适用范围，避免冒称完整生产库

### native · 使用选中的静态家具形体
仅选中且已获授权的本地样件参与该模型。
- [数据] `scripts/engine/assets/library/dining-chair.glb`：本地家具库中的餐椅静态模型样件
- [数据] `scripts/engine/assets/library/lounge-chair.glb`：本地家具库中的休闲椅静态模型样件
- [数据] `scripts/engine/assets/library/sideboard.glb`：本地家具库中的餐边柜静态模型样件

### thumb · 用缩略图核对家具选型
缩略图用于选型显示；形体仍来自对应模型数据。
- [数据] `scripts/engine/assets/library/dining-chair.png`：家具库选型时显示餐椅样件缩略图
- [数据] `scripts/engine/assets/library/lounge-chair.png`：家具库选型时显示休闲椅样件缩略图
- [数据] `scripts/engine/assets/library/sideboard.png`：家具库选型时显示餐边柜样件缩略图

### style · 读取已知风格或记录真实检索
未知风格由当前代理真实检索；证据记录不冒充已联网验证。
- [配置] `scripts/engine/catalog/styles.json`：保存已知风格配方、材料语义槽与初次造型选择
- [数据] `scripts/engine/schemas/style.schema.json`：声明风格配方、材料和检索证据的字段
- [模块] `scripts/engine/python/styles.py`：解析已知风格、检查新配方及证据；未知风格返回真实检索需求
- [方法] `scripts/engine/STYLE-GUIDE.md`：解释已有风格的材料、配色和初次造型选择

### style_methods · 按风格方法选择材料和细部
首次建模可选择细部；之后换风格只改颜色、材料与表面。
- [方法] `scripts/engine/styles/cream/PLAYBOOK.md`：说明奶油自然的材料、细部、灯光与应避免的造型
- [方法] `scripts/engine/styles/mid-century/PLAYBOOK.md`：说明中古暖木的材料、细部、灯光与应避免的造型
- [方法] `scripts/engine/styles/modern-minimal/PLAYBOOK.md`：说明现代极简的材料、细部、灯光与应避免的造型
- [方法] `scripts/engine/styles/new-chinese/PLAYBOOK.md`：说明新中式的材料、细部、灯光与应避免的造型
- [方法] `scripts/engine/styles/wabi-sabi/PLAYBOOK.md`：说明侘寂自然的材料、细部、灯光与应避免的造型

### texture_wood · 查看木材和墙面纹理样件
这些是可移植样图；离线页面由同源材料模块生成纹理。
- [登记] `scripts/engine/assets/textures/manifest.json`：登记可移植纹理样件来源；页面由同源材料模块生成纹理
- [数据] `scripts/engine/assets/textures/wood-color.png`：木材的可移植颜色纹理样图，供预览和导出
- [数据] `scripts/engine/assets/textures/wood-normal.png`：木材的可移植凹凸法线样图，供预览和导出
- [数据] `scripts/engine/assets/textures/plaster-color.png`：墙面灰泥的可移植颜色纹理样图，供预览和导出
- [数据] `scripts/engine/assets/textures/plaster-normal.png`：墙面灰泥的可移植凹凸法线样图，供预览和导出

### texture_cloth · 查看织物和皮革纹理样件
颜色图表达表面配色；法线图表达细小凹凸。
- [数据] `scripts/engine/assets/textures/fabric-color.png`：织物的可移植颜色纹理样图，供预览和导出
- [数据] `scripts/engine/assets/textures/fabric-normal.png`：织物的可移植凹凸法线样图，供预览和导出
- [数据] `scripts/engine/assets/textures/leather-color.png`：皮革的可移植颜色纹理样图，供预览和导出
- [数据] `scripts/engine/assets/textures/leather-normal.png`：皮革的可移植凹凸法线样图，供预览和导出

### texture_stone · 查看石材和编织纹理样件
预览和导出样件保持同源；不因换风格改变家具结构。
- [数据] `scripts/engine/assets/textures/stone-color.png`：石材的可移植颜色纹理样图，供预览和导出
- [数据] `scripts/engine/assets/textures/stone-normal.png`：石材的可移植凹凸法线样图，供预览和导出
- [数据] `scripts/engine/assets/textures/woven-color.png`：编织的可移植颜色纹理样图，供预览和导出
- [数据] `scripts/engine/assets/textures/woven-normal.png`：编织的可移植凹凸法线样图，供预览和导出

### resume · 带着构造事实回到生成页面
回总图“生成当前离线编辑模板”；本页不新增逐项读图门禁。
- [方法] `playbook/joinery.md`：按板厚、分区、独立台面孔与锚点构造柜桌及床台

连线：
- method → connection
- connection → library
- library → native
- native → thumb
- thumb → style
- style → style_methods
- style_methods → texture_wood
- texture_wood → texture_cloth
- texture_cloth → texture_stone
- texture_stone → resume

## 3. D2 节点展开 · 正式编译器怎样生成同一个离线编辑器

展开范围：只解释主图生成离线编辑模板的执行入口与模块；不改变设计方法或业务代码。；进入条件：构建、导入或修改模型时，需要了解唯一编译器和编辑器模块的真实职责
来源：总图 `main` 的 `n3`（生成当前离线编辑模板）；返回 `n4`（编辑关联、保存并交接同版）。
布局：semantic-grid；选择理由：按因果顺序折行；构造、执行模块及保存交接分别展开，完整路径保持可读字号。

### entry · 使用正式入口和任务运行环境
依任务使用构建、导入、整组柜体或风格命令。
- [执行] `scripts/run.py`：将正式建模命令路由到本包引擎，并记录命令时间
- [模块] `scripts/engine/python/cli.py`：分派构建、柜体整组生成、导入和风格等正式命令
- [模块] `scripts/engine/python/bootstrap.py`：仅Windows存在专用运行环境时转交该Python入口
- [配置] `scripts/requirements.txt`：列出编译、几何计算及输入检查所需的Python依赖

### normal · 让源数据与编辑使用同一模型
归一对象和关联参数；只检查可表示格式与引用，不加审美门槛。
- [模块] `scripts/engine/python/kernel.py`：调用与页面相同的模型内核，归一布局和构造参数
- [模块] `scripts/engine/runtime/model-kernel.js`：归一对象参数、执行编辑命令并让源数据与页面使用同一模型
- [模块] `scripts/engine/python/validate.py`：检查字段、引用和可表示数值，并输出非审美观察结果
- [数据] `scripts/engine/schemas/layout.schema.json`：声明布局、门窗、家具和关联参数的可表示字段

### compile · 编译完整离线页面和场景摘要
本包模板与运行模块一起内嵌；同版场景绑定页面摘要。
- [模块] `scripts/engine/python/model.py`：把布局、预设、资源与运行模块编译为完整离线HTML及场景数据
- [模块] `scripts/engine/python/common.py`：读写JSON、计算文件与场景摘要并定位本包资源
- [模板] `scripts/engine/runtime/studio.html`：提供底栏、房间视图和结构、家具、灯光面板的唯一页面模板
- [模块] `scripts/engine/runtime/three-r164.js`：提供本包固定版本的三维绘图运行库，不依赖外部下载
- [登记] `scripts/engine/LICENSE-Three.js.txt`：保留随离线页面分发的Three.js许可

### walls · 按真实宿主生成墙门窗
源开合姿态与可见状态一致，墙角和洞口由同一几何构造。
- [模块] `scripts/engine/python/openings.py`：按源事实求门窗开合姿态、透视状态和外部目标
- [模块] `scripts/engine/runtime/geometry.js`：提供墙体、洞口及组件使用的可复用几何构造函数
- [模块] `scripts/engine/runtime/architecture-kit.js`：构造房间建筑面、门窗及相关结构实体

### joinery · 生成参数化板件和连接
独立台面、开孔、分区和锚点关系随对象参数生成。
- [模块] `scripts/engine/python/joinery.py`：依据柜体整组请求计算布局分段、模块和独立台面
- [模块] `scripts/engine/runtime/joinery-kernel.js`：计算板件、面板分区、台面孔与显式锚点关联
- [模块] `scripts/engine/runtime/joinery.js`：将柜桌、床台和吊顶构造参数生成为页面几何

### furniture · 生成选定结构家族的家具
组件类别决定结构，初次细部在该家族内选型。
- [模块] `scripts/engine/runtime/components-base.js`：按组件类别生成基础家具、灯具和配件结构
- [模块] `scripts/engine/runtime/style-components.js`：在选定组件结构家族内生成初次风格细部
- [模块] `scripts/engine/runtime/components.js`：路由参数化组件生成并保留对象身份与实例变换

### native · 加入已授权的本地家具数据
校验自包含静态模型、摘要、类别和缩放政策；不偷偷用方块替代。
- [模块] `scripts/engine/python/native.py`：校验本地GLB、打包授权家具库并从完整HTML提取当前编辑状态
- [模块] `scripts/engine/runtime/native-assets.js`：解析自包含GLB，按授权家具身份和缩放政策加入当前场景

### scene · 组织当前场景与材料风格
材料同源生成；换风格保留已编辑家具形体、位置与灯光。
- [模块] `scripts/engine/runtime/scene.js`：组织房间、结构、家具、环境与预览机位的当前场景
- [模块] `scripts/engine/runtime/materials.js`：由同源确定性生成器建立离线颜色、凹凸纹理及材质槽
- [模块] `scripts/engine/runtime/styles.js`：验证并应用颜色、材料和表面风格，不移动或重建已编辑家具

### view · 加入灯光和可操作视图
实际光源和灯具网格分开；视图旋转、缩放保持同一相机。
- [模块] `scripts/engine/runtime/lights.js`：建立可编辑光源，并保存位置、目标、亮度、色温及绑定
- [模块] `scripts/engine/runtime/controls.js`：处理旋转、缩放和视图操作，保持同一相机与指针控制

### support · 保留量尺观察和局部性能处理
二维面积和量尺按当前布局计算；网格不跨对象根合并。
- [模块] `scripts/engine/runtime/spatial.js`：按同版布局计算面积、二维量尺和摆放包络观察
- [模块] `scripts/engine/runtime/optimization.js`：在各对象根内合并可共享网格，不跨墙门家具混合实体

### resume · 打开同版页面后回到编辑保存
启动当前模型和房间视图；回总图“编辑关联、保存并交接同版”。
- [模块] `scripts/engine/runtime/app.js`：启动当前模型、房间视图、显示状态及保存数据恢复

连线：
- entry → normal
- normal → compile
- compile → walls
- walls → joinery
- joinery → furniture
- furniture → native
- native → scene
- scene → view
- view → support
- support → resume

## 4. D3 节点展开 · 从当前编辑状态保存到同版交付

展开范围：只展开主图的编辑保存与同版交接节点；技能维护与普通模型交付按真实条件分流。；进入条件：保存、重开或向后续机位和绘图Skill交接当前版；仅技能改版才走维护分支
来源：总图 `main` 的 `n4`（编辑关联、保存并交接同版）；返回 `n5`（用户获得完整模型与场景数据）。
布局：semantic-grid；选择理由：按因果顺序折行；构造、执行模块及保存交接分别展开，完整路径保持可读字号。

### edit · 在当前页面编辑并保留关联
调整结构、家具、灯光和量尺；撤销重做恢复同一模型事实。
- [模块] `scripts/engine/runtime/workspace.js`：处理结构与家具编辑、量尺、撤销重做及完整HTML保存和导入
- [模块] `scripts/engine/runtime/app.js`：启动当前模型、房间视图、显示状态及保存数据恢复
- [方法] `playbook/editor-model.md`：说明统一模型编辑、墙角接缝、关联重建和旧数据迁移

### save_html · 保存完整页面并重开核对
完整页面保留当前布局和编辑状态；按需另导出静态模型。
补充说明：exporter.js导出GLB网格、材质与贴图；完整HTML保存由workspace.js负责。
- [模块] `scripts/engine/runtime/workspace.js`：处理结构与家具编辑、量尺、撤销重做及完整HTML保存和导入
- [模块] `scripts/engine/python/native.py`：校验本地GLB、打包授权家具库并从完整HTML提取当前编辑状态
- [模块] `scripts/engine/runtime/exporter.js`：按需导出含网格、材质和贴图的静态GLB，排除灯光与显示裁切
- [数据] `data_contract.md`：规定布局、编辑状态、场景摘要和同版需求交接

### handoff · 把同版场景交给机位和绘图
后续Skill按用户要求使用当前场景、需求及机位；未生成图片不写已完成。
- [模块] `scripts/engine/python/cameras.py`：根据当前场景求预览与正式机位，保留遮挡和构图观察
- [数据] `scripts/engine/schemas/cameras.schema.json`：声明绑定场景的机位、可见状态与检查结果
- [模块] `scripts/engine/python/render.py`：读取绑定的当前模型，并按机位与产品参考准备绘图请求
- [模块] `scripts/engine/python/native_image.py`：根据原生绘图能力准备调用事实并登记真实结果和人工审阅

### time · 记录真实执行与等待时间
按实际开始、完成、耗时和状态登记；不事后补造时间。
- [模块] `scripts/engine/python/timing.py`：在命令和编译阶段记录实际开始、结束、耗时与状态
- [方法] `playbook/timing.md`：统一记录每步开始、完成、耗时、状态与真实等待

### maintenance · 本次是否修改了技能规则或代码？
普通建模直接交付；仅技能改版进入维护检查。
- [方法] `local_runtime.md`：说明运行依赖、正式命令以及维护说明书和安装副本的方法

### test · 验证本次改动影响的门窗和机位
维护代码时才验证源开合、遮挡与主体退让；不作为每次建模前置。
- [验证] `scripts/engine/tests/test_space_connections.py`：改动门窗或机位代码时验证源开合、遮挡与完整主体退让

### manual · 按同一逻辑更新使用说明
只有技能改版才重制说明书；逐页阅读实际图面和路径用途。
- [图源] `manual/skill-manual.json`：维护总图、必要展开及真实节点与文件用途的唯一图源
- [交付] `manual/skill-manual.md`：同源输出总流程、必要展开和可追溯的文字说明
- [交付] `manual/skill-flowchart.svg`：提供可独立放大查看的完整六节点总图
- [交付] `manual/skill-manual.html`：提供可放大、跳转详情并按真实文件定位的交互说明书
- [交付] `SKILL_MANUAL.pdf`：供人阅读完整总图及构造、模块、保存交接的必要展开
- [依赖] `../skill-product-manager/scripts/build_skill_manual.mjs`：改版时由同一图源生成PDF、文字及交互说明
- [依赖] `../skill-product-manager/scripts/validate_skill_manual.mjs`：改版时只读核对图源、图面及实际PDF同源性

### register · 登记摘要并替换授权发行副本
核对正式文件和摘要；生成、安装与真实运行验证分开记录。
- [登记] `MANIFEST.json`：登记发行版本、正式文件清单和全部内容摘要
- [依赖] `../skill-product-manager/scripts/release.py`：改版时登记摘要、核对正式文件并打包发行副本

### resume · 带着当前模型和真实结果回到交付
回总图“用户获得完整模型与场景数据”；保留待核事项。
- [数据] `data_contract.md`：规定布局、编辑状态、场景摘要和同版需求交接

连线：
- edit → save_html
- save_html → handoff
- handoff → time
- time → maintenance
- maintenance → test：修改了技能
- maintenance → resume：普通建模
- test → manual
- manual → register
- register → resume

## 文件索引（全部用途已在节点内说明）
- `MANIFEST.json`：登记发行版本、正式文件清单和全部内容摘要；对应 save/register
- `SKILL.md`：接收布局、最新模型及用户要求，确定本次建模与交付范围；对应 main/n0
- `SKILL_MANUAL.pdf`：供人阅读完整总图及构造、模块、保存交接的必要展开；对应 save/manual
- `data_contract.md`：规定布局、编辑状态、场景摘要和同版需求交接；对应 main/n5、save/save_html、save/resume
- `local_runtime.md`：说明运行依赖、正式命令以及维护说明书和安装副本的方法；对应 main/n1、save/maintenance
- `manual/skill-flowchart.svg`：提供可独立放大查看的完整六节点总图；对应 save/manual
- `manual/skill-manual.html`：提供可放大、跳转详情并按真实文件定位的交互说明书；对应 save/manual
- `manual/skill-manual.json`：维护总图、必要展开及真实节点与文件用途的唯一图源；对应 save/manual
- `manual/skill-manual.md`：同源输出总流程、必要展开和可追溯的文字说明；对应 save/manual
- `playbook.md`：说明家具结构、风格、量尺、灯光和完整保存的实际行为；对应 construction/method
- `playbook/editor-model.md`：说明统一模型编辑、墙角接缝、关联重建和旧数据迁移；对应 construction/connection、save/edit
- `playbook/examples/cabinet-run.json`：演示柜体整组生成的分段尺寸、拼接和台面请求；对应 construction/method
- `playbook/examples/joinery-layout.json`：演示柜桌、台面、床台、吊顶与显式锚点的布局；对应 construction/method
- `playbook/joinery.md`：按板厚、分区、独立台面孔与锚点构造柜桌及床台；对应 main/n2、construction/method、construction/resume
- `playbook/rule-selection.md`：区分通用构造方法与本项目尺寸、偏好和明确覆盖；对应 main/n1
- `playbook/space-connections.md`：定义门窗宿主、开合、填充和空间两端的源事实；对应 construction/connection
- `playbook/timing.md`：统一记录每步开始、完成、耗时、状态与真实等待；对应 save/time
- `scripts/engine/LICENSE-Three.js.txt`：保留随离线页面分发的Three.js许可；对应 compiler/compile
- `scripts/engine/STYLE-GUIDE.md`：解释已有风格的材料、配色和初次造型选择；对应 construction/style
- `scripts/engine/assets/library/PROVENANCE.md`：记录样件模型来源与适用范围，避免冒称完整生产库；对应 construction/library
- `scripts/engine/assets/library/dining-chair.glb`：本地家具库中的餐椅静态模型样件；对应 construction/native
- `scripts/engine/assets/library/dining-chair.png`：家具库选型时显示餐椅样件缩略图；对应 construction/thumb
- `scripts/engine/assets/library/library.json`：登记样件类别、尺寸、缩放政策、文件与缩略图；对应 construction/library
- `scripts/engine/assets/library/lounge-chair.glb`：本地家具库中的休闲椅静态模型样件；对应 construction/native
- `scripts/engine/assets/library/lounge-chair.png`：家具库选型时显示休闲椅样件缩略图；对应 construction/thumb
- `scripts/engine/assets/library/sideboard.glb`：本地家具库中的餐边柜静态模型样件；对应 construction/native
- `scripts/engine/assets/library/sideboard.png`：家具库选型时显示餐边柜样件缩略图；对应 construction/thumb
- `scripts/engine/assets/textures/fabric-color.png`：织物的可移植颜色纹理样图，供预览和导出；对应 construction/texture_cloth
- `scripts/engine/assets/textures/fabric-normal.png`：织物的可移植凹凸法线样图，供预览和导出；对应 construction/texture_cloth
- `scripts/engine/assets/textures/leather-color.png`：皮革的可移植颜色纹理样图，供预览和导出；对应 construction/texture_cloth
- `scripts/engine/assets/textures/leather-normal.png`：皮革的可移植凹凸法线样图，供预览和导出；对应 construction/texture_cloth
- `scripts/engine/assets/textures/manifest.json`：登记可移植纹理样件来源；页面由同源材料模块生成纹理；对应 construction/texture_wood
- `scripts/engine/assets/textures/plaster-color.png`：墙面灰泥的可移植颜色纹理样图，供预览和导出；对应 construction/texture_wood
- `scripts/engine/assets/textures/plaster-normal.png`：墙面灰泥的可移植凹凸法线样图，供预览和导出；对应 construction/texture_wood
- `scripts/engine/assets/textures/stone-color.png`：石材的可移植颜色纹理样图，供预览和导出；对应 construction/texture_stone
- `scripts/engine/assets/textures/stone-normal.png`：石材的可移植凹凸法线样图，供预览和导出；对应 construction/texture_stone
- `scripts/engine/assets/textures/wood-color.png`：木材的可移植颜色纹理样图，供预览和导出；对应 construction/texture_wood
- `scripts/engine/assets/textures/wood-normal.png`：木材的可移植凹凸法线样图，供预览和导出；对应 construction/texture_wood
- `scripts/engine/assets/textures/woven-color.png`：编织的可移植颜色纹理样图，供预览和导出；对应 construction/texture_stone
- `scripts/engine/assets/textures/woven-normal.png`：编织的可移植凹凸法线样图，供预览和导出；对应 construction/texture_stone
- `scripts/engine/catalog/components.json`：登记支持的组件类别、默认尺寸和参数范围；对应 construction/library
- `scripts/engine/catalog/styles.json`：保存已知风格配方、材料语义槽与初次造型选择；对应 construction/style
- `scripts/engine/python/bootstrap.py`：仅Windows存在专用运行环境时转交该Python入口；对应 compiler/entry
- `scripts/engine/python/cameras.py`：根据当前场景求预览与正式机位，保留遮挡和构图观察；对应 save/handoff
- `scripts/engine/python/cli.py`：分派构建、柜体整组生成、导入和风格等正式命令；对应 compiler/entry
- `scripts/engine/python/common.py`：读写JSON、计算文件与场景摘要并定位本包资源；对应 compiler/compile
- `scripts/engine/python/joinery.py`：依据柜体整组请求计算布局分段、模块和独立台面；对应 compiler/joinery
- `scripts/engine/python/kernel.py`：调用与页面相同的模型内核，归一布局和构造参数；对应 compiler/normal
- `scripts/engine/python/model.py`：把布局、预设、资源与运行模块编译为完整离线HTML及场景数据；对应 compiler/compile
- `scripts/engine/python/native.py`：校验本地GLB、打包授权家具库并从完整HTML提取当前编辑状态；对应 compiler/native、save/save_html
- `scripts/engine/python/native_image.py`：根据原生绘图能力准备调用事实并登记真实结果和人工审阅；对应 save/handoff
- `scripts/engine/python/openings.py`：按源事实求门窗开合姿态、透视状态和外部目标；对应 compiler/walls
- `scripts/engine/python/render.py`：读取绑定的当前模型，并按机位与产品参考准备绘图请求；对应 save/handoff
- `scripts/engine/python/styles.py`：解析已知风格、检查新配方及证据；未知风格返回真实检索需求；对应 construction/style
- `scripts/engine/python/timing.py`：在命令和编译阶段记录实际开始、结束、耗时与状态；对应 save/time
- `scripts/engine/python/validate.py`：检查字段、引用和可表示数值，并输出非审美观察结果；对应 compiler/normal
- `scripts/engine/runtime/app.js`：启动当前模型、房间视图、显示状态及保存数据恢复；对应 compiler/resume、save/edit
- `scripts/engine/runtime/architecture-kit.js`：构造房间建筑面、门窗及相关结构实体；对应 compiler/walls
- `scripts/engine/runtime/components-base.js`：按组件类别生成基础家具、灯具和配件结构；对应 compiler/furniture
- `scripts/engine/runtime/components.js`：路由参数化组件生成并保留对象身份与实例变换；对应 compiler/furniture
- `scripts/engine/runtime/controls.js`：处理旋转、缩放和视图操作，保持同一相机与指针控制；对应 compiler/view
- `scripts/engine/runtime/exporter.js`：按需导出含网格、材质和贴图的静态GLB，排除灯光与显示裁切；对应 save/save_html
- `scripts/engine/runtime/geometry.js`：提供墙体、洞口及组件使用的可复用几何构造函数；对应 compiler/walls
- `scripts/engine/runtime/joinery-kernel.js`：计算板件、面板分区、台面孔与显式锚点关联；对应 compiler/joinery
- `scripts/engine/runtime/joinery.js`：将柜桌、床台和吊顶构造参数生成为页面几何；对应 compiler/joinery
- `scripts/engine/runtime/lights.js`：建立可编辑光源，并保存位置、目标、亮度、色温及绑定；对应 compiler/view
- `scripts/engine/runtime/materials.js`：由同源确定性生成器建立离线颜色、凹凸纹理及材质槽；对应 compiler/scene
- `scripts/engine/runtime/model-kernel.js`：归一对象参数、执行编辑命令并让源数据与页面使用同一模型；对应 compiler/normal
- `scripts/engine/runtime/native-assets.js`：解析自包含GLB，按授权家具身份和缩放政策加入当前场景；对应 compiler/native
- `scripts/engine/runtime/optimization.js`：在各对象根内合并可共享网格，不跨墙门家具混合实体；对应 compiler/support
- `scripts/engine/runtime/scene.js`：组织房间、结构、家具、环境与预览机位的当前场景；对应 compiler/scene
- `scripts/engine/runtime/spatial.js`：按同版布局计算面积、二维量尺和摆放包络观察；对应 compiler/support
- `scripts/engine/runtime/studio.html`：提供底栏、房间视图和结构、家具、灯光面板的唯一页面模板；对应 compiler/compile
- `scripts/engine/runtime/style-components.js`：在选定组件结构家族内生成初次风格细部；对应 compiler/furniture
- `scripts/engine/runtime/styles.js`：验证并应用颜色、材料和表面风格，不移动或重建已编辑家具；对应 compiler/scene
- `scripts/engine/runtime/three-r164.js`：提供本包固定版本的三维绘图运行库，不依赖外部下载；对应 compiler/compile
- `scripts/engine/runtime/workspace.js`：处理结构与家具编辑、量尺、撤销重做及完整HTML保存和导入；对应 main/n4、save/edit、save/save_html
- `scripts/engine/schemas/cameras.schema.json`：声明绑定场景的机位、可见状态与检查结果；对应 save/handoff
- `scripts/engine/schemas/layout.schema.json`：声明布局、门窗、家具和关联参数的可表示字段；对应 compiler/normal
- `scripts/engine/schemas/style.schema.json`：声明风格配方、材料和检索证据的字段；对应 construction/style
- `scripts/engine/styles/cream/PLAYBOOK.md`：说明奶油自然的材料、细部、灯光与应避免的造型；对应 construction/style_methods
- `scripts/engine/styles/mid-century/PLAYBOOK.md`：说明中古暖木的材料、细部、灯光与应避免的造型；对应 construction/style_methods
- `scripts/engine/styles/modern-minimal/PLAYBOOK.md`：说明现代极简的材料、细部、灯光与应避免的造型；对应 construction/style_methods
- `scripts/engine/styles/new-chinese/PLAYBOOK.md`：说明新中式的材料、细部、灯光与应避免的造型；对应 construction/style_methods
- `scripts/engine/styles/wabi-sabi/PLAYBOOK.md`：说明侘寂自然的材料、细部、灯光与应避免的造型；对应 construction/style_methods
- `scripts/engine/tests/test_space_connections.py`：改动门窗或机位代码时验证源开合、遮挡与完整主体退让；对应 save/test
- `scripts/requirements.txt`：列出编译、几何计算及输入检查所需的Python依赖；对应 compiler/entry
- `scripts/run.py`：将正式建模命令路由到本包引擎，并记录命令时间；对应 main/n3、compiler/entry

## 显式共享依赖
- `../skill-product-manager/scripts/build_skill_manual.mjs` [authoring]：改版时由同一图源生成PDF、文字及交互说明
- `../skill-product-manager/scripts/validate_skill_manual.mjs` [authoring]：改版时只读核对图源、图面及实际PDF同源性
- `../skill-product-manager/scripts/release.py` [authoring]：改版时登记摘要、核对正式文件并打包发行副本
