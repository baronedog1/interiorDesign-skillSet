# 单产品建模 说明书

版本：2.0.0

~~~yaml
---
name: product-modeling
description: 根据单个产品的图片、尺寸、描述或已有网格，先拆解零件与装配关系，再建模并制作可复用HTML工作台、独立产品源码/GLB与同源PDF说明书；支持参数款式、部件拆分、材质调整和导出。
version: 2.0.0
---
~~~

## 总流程：从任务到交付

触发：用户要求单产品建模；输入：单品照片、尺寸或网格；交付：源码、真实模型、验收与产品手册
两种输入路径汇合到同一验证和交付；文件用途在主节点展开。
- 接收任务与复用现有输入：单品照片、尺寸或网格
  - README.md：说明分发与使用范围
  - SKILL.md：识别任务和正式入口
  - data_contract.md：解释输入字段与产物状态
  - local_runtime.md：查当前依赖、权限和运行命令
  - package.json：确定Node包边界
  - scripts/requirements.txt：执行requirements对应处理
- 按输入选择建模分支：；work · 本次分支采用的执行模块 · 第2页
  - data_contract.md：解释输入字段与产物状态
- 参数结构或已有网格：结构重算、装配编辑、GLB/PDF导出
  - playbook.md：按目标选择方法并执行
- 多视图来源与区域雕刻：源图SHA与可逆注册→区域挤出求交→同一状态回投影；目标100像素、漏2：异或2，交并比98/100=0.98，不是精确通过；缺视图记推断，不是误差0；有推断交付预览状态
  - playbook.md：按目标选择方法并执行
- 核对实际结果与局部修复：只有受影响步骤暂停；技术检查与人看图/听审分开。；qa · 核对实际结果与局部修复 · 第3页
  - SKILL.md：识别任务和正式入口
- 交付结果、状态与复用入口：源码、真实模型、验收与产品手册；未完成项写明原因；已授权任务不重复求准。
  - CHANGELOG.md：执行CHANGELOG对应处理
  - MANIFEST.json：登记本版正式文件摘要
  - SKILL_MANUAL.pdf：交付人可阅读的流程说明
  - manual/skill-flowchart.svg：展示完整主流程
  - manual/skill-manual.json：维护与实现对应的流程源
  - manual/skill-manual.md：提供同源文字追溯
  - scripts/build_skill_manual.mjs：从图源生成PDF及文字
  - scripts/flowchart-layout.mjs：排布节点、连线与用途文字
  - scripts/release.py：核对当前文件摘要并打包可恢复ZIP
  - scripts/validate_skill_manual.mjs：核对图源、文件与流程对应
- in → route
- route → a：参数结构或已有网格
- route → b：多视图来源与区域雕刻
- a → qa
- b → qa
- qa → done

## 节点展开：方法与实际执行模块

展开「按输入选择建模分支」；完成后接回「核对实际结果与局部修复」，不是另一次调用。
展开主图节点的方法与实际文件；不构成第二个业务入口。
- 工作台与图形资源：按首页选定分支使用对应模块；文件用途列在各处理节点内。
  - Product_Workbench.html：为Product_Workbench.html提供实际渲染/素材资源
  - Start_Workbench.cmd：执行Start Workbench对应处理
  - assets/vendor/OrbitControls.js：为OrbitControls.js提供实际渲染/素材资源
  - assets/vendor/three.module.js：为three.module.js提供实际渲染/素材资源
  - assets/workbench/LICENSE-Three.js.txt：为LICENSE-Three.js.txt提供实际渲染/素材资源
  - assets/workbench/gltf-io.js：为gltf-io.js提供实际渲染/素材资源
  - assets/workbench/product-kernel.js：为product-kernel.js提供实际渲染/素材资源
  - assets/workbench/three-r164.js：为three-r164.js提供实际渲染/素材资源
  - assets/workbench/workbench.html：为workbench.html提供实际渲染/素材资源
  - assets/workbench/workbench.js：为workbench.js提供实际渲染/素材资源
- 产品结构、材料与证据合同：按首页选定分支使用对应模块；文件用途列在各处理节点内。
  - playbook.md：按目标选择方法并执行
  - playbook/delivery.md：解释delivery的方法与输入去向
  - playbook/materials.md：解释materials的方法与输入去向
  - playbook/multiview.md：解释multiview的方法与输入去向
  - playbook/structure.md：解释structure的方法与输入去向
  - playbook/viewer/standalone.html：为standalone.html提供实际渲染/素材资源
  - schemas/carving-plan.schema.json：执行carving plan.schema对应处理
  - schemas/component-package-v3.schema.json：执行component package v3.schema对应处理
  - schemas/product-browser-qa.schema.json：执行product browser qa.schema对应处理
  - schemas/view-region-evidence.schema.json：执行view region evidence.schema对应处理
- 参数求值与真实模型输出：按首页选定分支使用对应模块；文件用途列在各处理节点内。
  - schemas/visual-hull-state.schema.json：执行visual hull state.schema对应处理
  - scripts/blender_import.py：把用户已有网格导入Blender编辑环境
  - scripts/build_component_package.py：绑定证据和浏览器QA
  - scripts/build_product.py：生成真实GLB与产品PDF
  - scripts/build_product_standalone.py：生成同几何双外观网页
  - scripts/build_workbench.py：把共享几何与查看器资源生成离线工作台
  - scripts/carve_visual_hull.py：多视图挤出体求交
  - scripts/compare_view_projection.py：从同一几何回投影计算差异
  - scripts/evaluate.cjs：用共享表达式内核计算产品参数
  - scripts/export_quad_obj.py：将已有四边面源转换为OBJ
- 多视图雕刻、投影和组件交接：按首页选定分支使用对应模块；文件用途列在各处理节点内。
  - scripts/export_visual_hull.py：按实测单位导出雕刻网格
  - scripts/extract_view_regions.py：从源图提取组件区域
  - scripts/mask_utils.py：编码掩膜并计算唯一证据摘要
  - scripts/product_manual.py：从产品数据排版说明书
  - scripts/scripts.md：查询命令参数与职责
  - scripts/serve.py：本地提供工作台文件访问
- d0 → d1
- d1 → d2
- d2 → d3

## 节点展开：核对实际结果与局部修复

展开「核对实际结果与局部修复」；完成后接回「交付结果、状态与复用入口」，不是另一次调用。
展开主图节点的方法与实际文件；不构成第二个业务入口。
- 对照实际产物与结果标杆：先跑对应行为，再看真实产物；合成测试不证明艺术品质。
  - expected_outcome/cabinet/PRODUCT_MANIFEST.json：对照PRODUCT_MANIFEST.json的已声明示例品质
  - expected_outcome/cabinet/PRODUCT_MANUAL.pdf：对照PRODUCT_MANUAL.pdf的已声明示例品质
  - expected_outcome/cabinet/cabinet.product.json：对照cabinet.product.json的已声明示例品质
  - expected_outcome/cabinet/evaluated.json：对照evaluated.json的已声明示例品质
  - expected_outcome/cabinet/model.glb：对照model.glb的已声明示例品质
  - expected_outcome/cabinet/preview.png：对照preview.png的已声明示例品质
  - expected_outcome/expected_outcome.md：对照expected_outcome.md的已声明示例品质
  - expected_outcome/mesh-demo/mesh.glb：对照mesh.glb的已声明示例品质
  - expected_outcome/mesh-demo/mesh.product.json：对照mesh.product.json的已声明示例品质
  - expected_outcome/validation-report.json：对照validation-report.json的已声明示例品质
- 运行结构与回归检查：先跑对应行为，再看真实产物；合成测试不证明艺术品质。
  - scripts/validate_package.py：执行validate package对应处理
  - scripts/validate_view_regions.py：校验源图绑定和区域覆盖
  - tests/browser_smoke.py：验证browser smoke行为
  - tests/kernel.test.cjs：验证kernel.test.cjs行为
  - tests/test_export_paths.py：验证export paths行为
  - tests/test_visual_hull_pipeline.py：验证visual hull pipeline行为
- d0 → d1

## 文件索引（用途已在流程中对应）
- CHANGELOG.md：执行CHANGELOG对应处理
- MANIFEST.json：登记本版正式文件摘要
- Product_Workbench.html：为Product_Workbench.html提供实际渲染/素材资源
- README.md：说明分发与使用范围
- SKILL.md：识别任务和正式入口
- SKILL_MANUAL.pdf：交付人可阅读的流程说明
- Start_Workbench.cmd：执行Start Workbench对应处理
- assets/vendor/OrbitControls.js：为OrbitControls.js提供实际渲染/素材资源
- assets/vendor/three.module.js：为three.module.js提供实际渲染/素材资源
- assets/workbench/LICENSE-Three.js.txt：为LICENSE-Three.js.txt提供实际渲染/素材资源
- assets/workbench/gltf-io.js：为gltf-io.js提供实际渲染/素材资源
- assets/workbench/product-kernel.js：为product-kernel.js提供实际渲染/素材资源
- assets/workbench/three-r164.js：为three-r164.js提供实际渲染/素材资源
- assets/workbench/workbench.html：为workbench.html提供实际渲染/素材资源
- assets/workbench/workbench.js：为workbench.js提供实际渲染/素材资源
- data_contract.md：解释输入字段与产物状态
- expected_outcome/cabinet/PRODUCT_MANIFEST.json：对照PRODUCT_MANIFEST.json的已声明示例品质
- expected_outcome/cabinet/PRODUCT_MANUAL.pdf：对照PRODUCT_MANUAL.pdf的已声明示例品质
- expected_outcome/cabinet/cabinet.product.json：对照cabinet.product.json的已声明示例品质
- expected_outcome/cabinet/evaluated.json：对照evaluated.json的已声明示例品质
- expected_outcome/cabinet/model.glb：对照model.glb的已声明示例品质
- expected_outcome/cabinet/preview.png：对照preview.png的已声明示例品质
- expected_outcome/expected_outcome.md：对照expected_outcome.md的已声明示例品质
- expected_outcome/mesh-demo/mesh.glb：对照mesh.glb的已声明示例品质
- expected_outcome/mesh-demo/mesh.product.json：对照mesh.product.json的已声明示例品质
- expected_outcome/validation-report.json：对照validation-report.json的已声明示例品质
- local_runtime.md：查当前依赖、权限和运行命令
- manual/skill-flowchart.svg：展示完整主流程
- manual/skill-manual.json：维护与实现对应的流程源
- manual/skill-manual.md：提供同源文字追溯
- package.json：确定Node包边界
- playbook.md：按目标选择方法并执行
- playbook/delivery.md：解释delivery的方法与输入去向
- playbook/materials.md：解释materials的方法与输入去向
- playbook/multiview.md：解释multiview的方法与输入去向
- playbook/structure.md：解释structure的方法与输入去向
- playbook/viewer/standalone.html：为standalone.html提供实际渲染/素材资源
- schemas/carving-plan.schema.json：执行carving plan.schema对应处理
- schemas/component-package-v3.schema.json：执行component package v3.schema对应处理
- schemas/product-browser-qa.schema.json：执行product browser qa.schema对应处理
- schemas/view-region-evidence.schema.json：执行view region evidence.schema对应处理
- schemas/visual-hull-state.schema.json：执行visual hull state.schema对应处理
- scripts/blender_import.py：把用户已有网格导入Blender编辑环境
- scripts/build_component_package.py：绑定证据和浏览器QA
- scripts/build_product.py：生成真实GLB与产品PDF
- scripts/build_product_standalone.py：生成同几何双外观网页
- scripts/build_skill_manual.mjs：从图源生成PDF及文字
- scripts/build_workbench.py：把共享几何与查看器资源生成离线工作台
- scripts/carve_visual_hull.py：多视图挤出体求交
- scripts/compare_view_projection.py：从同一几何回投影计算差异
- scripts/evaluate.cjs：用共享表达式内核计算产品参数
- scripts/export_quad_obj.py：将已有四边面源转换为OBJ
- scripts/export_visual_hull.py：按实测单位导出雕刻网格
- scripts/extract_view_regions.py：从源图提取组件区域
- scripts/flowchart-layout.mjs：排布节点、连线与用途文字
- scripts/mask_utils.py：编码掩膜并计算唯一证据摘要
- scripts/product_manual.py：从产品数据排版说明书
- scripts/release.py：核对当前文件摘要并打包可恢复ZIP
- scripts/requirements.txt：执行requirements对应处理
- scripts/scripts.md：查询命令参数与职责
- scripts/serve.py：本地提供工作台文件访问
- scripts/validate_package.py：执行validate package对应处理
- scripts/validate_skill_manual.mjs：核对图源、文件与流程对应
- scripts/validate_view_regions.py：校验源图绑定和区域覆盖
- tests/browser_smoke.py：验证browser smoke行为
- tests/kernel.test.cjs：验证kernel.test.cjs行为
- tests/test_export_paths.py：验证export paths行为
- tests/test_visual_hull_pipeline.py：验证visual hull pipeline行为
