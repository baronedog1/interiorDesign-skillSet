# 单产品建模 · 交付修复版 1.0.1


## 最快开始

解压整个目录后，双击根目录 `Product_Workbench.html`（Windows也可用 `Start_Workbench.cmd`）。工作台最初不加载产品，因为它是共用工具。


“部件”页用于选择、联动、隐藏、隔离与分解；“参数”页从产品定义自动生成；“说明”页显示已知来源与限制。修改后保存JSON及导出GLB。保存JSON不会自动覆盖原模型或PDF。

## 包里有什么

- [Skill入口](SKILL.md)、方法与契约、可执行脚本、[Skill PDF](SKILL_MANUAL.pdf)。
- 一份无产品内嵌的 [共用工作台](Product_Workbench.html)，其可维护源在 `assets/workbench/`。

## 如需自动加载

```bash
python scripts/serve.py
```

打开控制台显示的本地地址，即可自动载入柜体。服务只监听本机。浏览器本地文件安全机制限制任意读取相邻文件；直接双击时使用文件选择器，不绕过浏览器策略。

## 重要范围

工作台使用静态、未压缩GLB的受支持子集，不支持骨骼、动画、Draco或Meshopt压缩等扩展。原始GLB可独立显示，但未知结构参数不会凭空出现。复杂几何须先建好源网格再接入；当前声明式构建器支持盒体、柱体和球体组合，不是通用CAD或雕刻软件。


本包未安装到用户设备、资料库或平台；没有生成并验证 `.blend`。可选Blender脚本仅供有Blender的设备实际执行。交付修复的测试范围详见 [验收记录](expected_outcome/validation-report.json)。
