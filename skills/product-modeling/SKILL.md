---
name: product-modeling
description: 根据单个产品的图片、尺寸、描述或已有网格，先拆解零件与装配关系，再建模并制作可复用HTML工作台、独立产品源码/GLB与同源PDF说明书；支持参数款式、部件拆分、材质调整和导出。
version: 2.0.0
---

# 单产品建模

版本：2.0.0。

这不是室内全屋布局 Skill。用户给一个家具或其他单品时，完成其外观、零件、参数与说明书；只有当前资料支持的结构才能写为确定事实。

## 高频数据入口

- 用户原图、尺寸、已有网格与产品定义；缺少隐藏结构信息时记录推定。
- 还原分支读取源图 SHA、区域证据与多视图 plan；参数分支读取 product.json。
- 产物和状态见 [data_contract.md](data_contract.md)，依赖见 [local_runtime.md](local_runtime.md)。

## 入口与职责

输入多视图或要求照片证据还原时，按 [多视图还原](playbook/multiview.md) 完成区域雕刻、来源绑定、投影验收与组件交付。其余参数化/已有网格任务按下述入口。

先读 [工作方法](playbook.md) 与 [数据契约](data_contract.md)。制作一个新产品时，沿 [结构拆解](playbook/structure.md) 确立证据、材料、零件、接口和装配；依 [材质方法](playbook/materials.md) 处理形体与表面。需要修订时保留已认可的部件ID、形象和不受影响的参数，不重复求准。

用户要产品时交付三个类别：只含该产品的源码包（含派生GLB）、一份共用 [HTML工作台](Product_Workbench.html)、该产品PDF。用户要本Skill时才交付当前完整Skill及示例，不把多个示例混进单件产品源码包。

## 从当前文件开始执行

```bash
python scripts/build_product.py expected_outcome/cabinet/cabinet.product.json --out work/cabinet
python scripts/serve.py
```


## 必须成立的规则

- 建模前先建立来源、尺度与推定记录；单张照片看不到的背面、内部和材料成分不能伪称精确还原。
- 参数化结构根据零件关系重算，板厚、接口不随总体宽度一起拉伸。网格比例变化明确标为近似变形，不冒充结构重算。
- 稳定零件ID贯穿源码、GLB、装配组、编辑记录与PDF。包边、针脚能跟随所属软包移动。
- 共用工作台不硬编码某个产品。新产品改变数据或新增通用几何能力，不再复制十份页面。
- 不用照片或AI图片代替真实网格与真实渲染验收。PDF参数来自同一产品定义；GLB和HTML都不是制造加工图纸。
- 实际文件存在、ZIP关闭后CRC和重新解压摘要通过，才提供下载。没有运行Blender，不声称已有已验收的 `.blend`。

## 验证与交付

依 [交付与恢复](playbook/delivery.md) 检查加载、参数、款式、编辑、导出和同源手册；标准见 [预期成果](expected_outcome/expected_outcome.md)。运行环境与限制见 [local_runtime.md](local_runtime.md)。

[Skill说明书PDF](SKILL_MANUAL.pdf)、[AI说明书](manual/skill-manual.md)、[流程图](manual/skill-flowchart.svg) 来自 [同一说明书源](manual/skill-manual.json)。它们与每件产品自己的 `PRODUCT_MANUAL.pdf` 分开。

随包网格演示为 expected_outcome/mesh-demo 的合成三部件，验证联动与导出，不代表真实产品外观。历史私有沙发示例仅保留在审计快照，不公开分发。四边面 NPZ→OBJ 工具仍可处理用户有权使用的源文件。
