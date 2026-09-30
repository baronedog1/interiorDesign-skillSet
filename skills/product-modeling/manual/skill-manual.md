# 单品照片到三维 HTML

版本：3.1.1

```yaml
---
name: product-modeling
description: 将单件产品的一张或多张照片重建为可旋转、可编辑、可离线保存的三维 HTML；适用于家具等单品的形体、材质复建与原图同视角核对。
metadata: {version: "3.1.1", category: interior-design}
---
```

总分结构：1 张总图；2 张来自主节点的展开。

## 1. 总图 · 从产品原图，到可以旋转编辑的成品

触发：用户要求照片单品建模或修改、相关咨询或维护；输入：原始照片、已确认要求与当前文件；输出：三维HTML、源码、对照与已验证状态
布局：semantic-grid；选择理由：按制作因果排列，非建模任务从右侧直接收尾；细节单独展开。

### input · 用户给产品照片和制作要求
保留原始照片、确认尺寸、修改意见和现有文件。
- [入口] `SKILL.md`：识别单品建模请求、路由及最终交付范围

### scope · 这次需要制作或修改形体吗？
- [入口] `SKILL.md`：识别单品建模请求、路由及最终交付范围

### other · 按当前任务处理已有材料
咨询、发送、确定数据编译或只截图，按本次要求处理。
只有改技能代码或规则时进入改版详情。
- [入口] `SKILL.md`：识别单品建模请求、路由及最终交付范围
- [方法] `local_runtime.md`：任务依赖安装、构建命令与设备同步方法
D2 · 展开见第3页

### geometry · 按原图校准形体和连接
先骨架与机位，再局部排列、截面和接头。
背面可合理推测，可见处同机位核对。
- [方法] `playbook/geometry.md`：从款式特征、留空、截面及接头选择真实几何表示
- [数据] `data_contract.md`：规定生成器、真实锚点、单位、编辑与保存对象
D1 · 展开见第2页

### surface · 按部件贴合材质颜色和光影
先材质和颜色，再调灯光；花纹不抵消形体偏差。
- [方法] `playbook/surfaces.md`：根据源图分组件建立颜色、纹理和光影
- [模块] `scripts/materials.mjs`：在真实曲面建立UV材质与按类别遮挡筛选的照片投影

### build · 生成完整离线工作台
模型、图片和运行库内联；保留实际可用编辑工具。
- [执行] `scripts/build-workbench.mjs`：将生成器与唯一工作台打入离线单文件HTML
- [模板] `assets/workbench/workbench.html`：唯一产品工作台的界面和控件
- [模块] `assets/workbench/workbench.js`：执行视图、选件、编辑、导入导出与保存重开
- [模块] `assets/workbench/product-kernel.js`：解释产品参数及装配定义
- [模块] `assets/workbench/gltf-io.js`：读写GLB网格、基础材质和统一UV变换
- [依赖] `assets/workbench/LICENSE-Three.js.txt`：保留工作台运行库的许可信息
- [配置] `scripts/package.json`：声明任务目录使用的固定依赖版本

### verify · 打开成品核对形体和操作
实际本地打开，检查同版截图、离线和保存重开。
受阻项与已通过项分别记录；局部返修后重验。
- [方法] `expected_outcome/expected_outcome.md`：区分形体对应、浏览器运行及未完成事项

### deliver · 交付成品、源码、对照和限制
核对本次成品、源码、实际对照和限制后交付。
- [入口] `SKILL.md`：识别单品建模请求、路由及最终交付范围

连线：
- input → scope
- scope → geometry：需要建模
- scope → other：无需建模
- geometry → surface
- surface → build
- build → verify
- verify → deliver
- other → deliver

## 2. D1 节点展开 · 把看得见的特点，变成可检查的形体

展开范围：展开主图的形体校准节点，完成后回到材质阶段。；进入条件：实际制作或修改形体，需要理解校准计算时
来源：总图 `main` 的 `geometry`（按原图校准形体和连接）；返回 `surface`（按部件贴合材质颜色和光影）。
布局：semantic-grid；选择理由：单一展开阶段按因果顺序排列，不保留空列。

### observe · 找出这款产品靠什么被认出
部件与空隙、粗细、弧面、端头和连接分别记录。
- [方法] `playbook/geometry.md`：从款式特征、留空、截面及接头选择真实几何表示

### bind · 把原图结构点绑定真实几何
标注来自读图；自动的是投影计算，不是语义判断。
- [数据] `data_contract.md`：规定生成器、真实锚点、单位、编辑与保存对象
- [方法] `playbook/calibration.md`：区分点、轮廓与结构约束以及已执行与未测的误差

### solve · 调整同一相机与有界形体参数
点误差按图像对角线归一，再加权求和。
轮廓与结构项由任务脚本明确接入，未测不填零。
- [模块] `scripts/core.mjs`：计算透视相机、锚点投影、轮廓误差与有界求解
- [模块] `scripts/feature-report.mjs`：测量关键特征的点、间距、曲线及留出偏差

### inspect · 同机位核对整体和局部
1000×1000图上10像素点误差，归一约0.00707。
权重1的该点损失约0.00005；20像素留出点只报告。
轮廓未标注就写未测，不能当完全吻合。
- [方法] `playbook/calibration.md`：区分点、轮廓与结构约束以及已执行与未测的误差

### resume · 记录偏差后回到材质阶段
关键特征错位要修几何，整体重合分数不能抵消。
- [方法] `expected_outcome/expected_outcome.md`：区分形体对应、浏览器运行及未完成事项

连线：
- observe → bind
- bind → solve
- solve → inspect
- inspect → resume

## 3. D2 节点展开 · 仅改版时验证技能并更新使用说明

展开范围：咨询和普通模型制作不执行改版制图；改版完成回到当前材料处理节点。；进入条件：仅当本次任务修改技能规则、代码或目录时
来源：总图 `main` 的 `other`（按当前任务处理已有材料）；返回 `other`（按当前任务处理已有材料）。
布局：semantic-grid；选择理由：单一展开阶段按因果顺序排列，不保留空列。

### change · 改动规则或执行代码
普通建模不进入本页；保留旧版可恢复快照。
- [方法] `local_runtime.md`：任务依赖安装、构建命令与设备同步方法

### test · 验证改动实际影响的行为
测试相机、留出点和求解，并打开真实产物检验。
- [验证] `scripts/test-product.mjs`：改动代码时验证相机、求解、留出点及非法输入

### manual · 按同一逻辑制作说明书
使用 Skill Product Manager 制图工具，逐页检查可读性。
- [图源] `manual/skill-manual.json`：本说明书唯一结构化图源
- [交付] `manual/skill-manual.md`：与图源同义的文字说明
- [交付] `manual/skill-flowchart.svg`：可独立缩放查看的完整总图
- [交付] `manual/skill-manual.html`：带详情与文件定位的交互说明书
- [交付] `SKILL_MANUAL.pdf`：供人阅读的总流程及必要展开
- [依赖] `../skill-product-manager/scripts/build_skill_manual.mjs`：由同一图源生成PDF、文字与网页说明
- [依赖] `../skill-product-manager/scripts/validate_skill_manual.mjs`：核对图文源、布局与实际PDF

### install · 核对摘要并替换授权副本
旧目录退出活跃路径；不覆盖其他能力或凭据。
- [登记] `MANIFEST.json`：登记发行版本、正式文件和摘要
- [方法] `local_runtime.md`：任务依赖安装、构建命令与设备同步方法
- [依赖] `../skill-product-manager/scripts/release.py`：登记摘要并打包可重开的发行版

### resume · 带着验证结果回到本次交付
新版已生成、已安装和实际运行验证分开记录。
- [入口] `SKILL.md`：识别单品建模请求、路由及最终交付范围

连线：
- change → test
- test → manual
- manual → install
- install → resume

## 文件索引（全部用途已在节点内说明）
- `MANIFEST.json`：登记发行版本、正式文件和摘要；对应 maintenance/install
- `SKILL.md`：识别单品建模请求、路由及最终交付范围；对应 main/input、main/scope、main/other、main/deliver、maintenance/resume
- `SKILL_MANUAL.pdf`：供人阅读的总流程及必要展开；对应 maintenance/manual
- `assets/workbench/LICENSE-Three.js.txt`：保留工作台运行库的许可信息；对应 main/build
- `assets/workbench/gltf-io.js`：读写GLB网格、基础材质和统一UV变换；对应 main/build
- `assets/workbench/product-kernel.js`：解释产品参数及装配定义；对应 main/build
- `assets/workbench/workbench.html`：唯一产品工作台的界面和控件；对应 main/build
- `assets/workbench/workbench.js`：执行视图、选件、编辑、导入导出与保存重开；对应 main/build
- `data_contract.md`：规定生成器、真实锚点、单位、编辑与保存对象；对应 main/geometry、fitting/bind
- `expected_outcome/expected_outcome.md`：区分形体对应、浏览器运行及未完成事项；对应 main/verify、fitting/resume
- `local_runtime.md`：任务依赖安装、构建命令与设备同步方法；对应 main/other、maintenance/change、maintenance/install
- `manual/skill-flowchart.svg`：可独立缩放查看的完整总图；对应 maintenance/manual
- `manual/skill-manual.html`：带详情与文件定位的交互说明书；对应 maintenance/manual
- `manual/skill-manual.json`：本说明书唯一结构化图源；对应 maintenance/manual
- `manual/skill-manual.md`：与图源同义的文字说明；对应 maintenance/manual
- `playbook/calibration.md`：区分点、轮廓与结构约束以及已执行与未测的误差；对应 fitting/bind、fitting/inspect
- `playbook/geometry.md`：从款式特征、留空、截面及接头选择真实几何表示；对应 main/geometry、fitting/observe
- `playbook/surfaces.md`：根据源图分组件建立颜色、纹理和光影；对应 main/surface
- `scripts/build-workbench.mjs`：将生成器与唯一工作台打入离线单文件HTML；对应 main/build
- `scripts/core.mjs`：计算透视相机、锚点投影、轮廓误差与有界求解；对应 fitting/solve
- `scripts/feature-report.mjs`：测量关键特征的点、间距、曲线及留出偏差；对应 fitting/solve
- `scripts/materials.mjs`：在真实曲面建立UV材质与按类别遮挡筛选的照片投影；对应 main/surface
- `scripts/package.json`：声明任务目录使用的固定依赖版本；对应 main/build
- `scripts/test-product.mjs`：改动代码时验证相机、求解、留出点及非法输入；对应 maintenance/test

## 显式共享依赖
- `../skill-product-manager/scripts/build_skill_manual.mjs` [authoring]：由同一图源生成PDF、文字与网页说明
- `../skill-product-manager/scripts/validate_skill_manual.mjs` [authoring]：核对图文源、布局与实际PDF
- `../skill-product-manager/scripts/release.py` [authoring]：登记摘要并打包可重开的发行版
