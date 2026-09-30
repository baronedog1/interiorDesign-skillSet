# 模板与资产索引

- `assets/blender-template/backend-options.json`：唯一后端行为和 Ubuntu Eevee 原生渲染策略。
- `assets/blender-component-library/catalog.json`：多款 Blender 原生资产、摘要、许可、房间范围、风格标签、来源轴、前向轴、朝向模式和缩放合同。
- `assets/blender-component-library/precision-asset-acquisition.v1.json`：本版经人工审过并允许下载的免费 BlenderKit 资产 ID；不是自动搜索结果。
- `assets/blender-component-library/acquisition-manifest.v1.json`：实际下载文件、来源页面、许可、字节数和 SHA-256 回执。
- `assets/blender-style-presets/warm-modern-neutral.json`：暖现代墙顶地材、各房间资产标签、Eevee 灯光、曝光、样本和贴图内存策略。
- `assets/blender-material-library/catalog.json`：墙、天花、干区地板和湿区地板的 CC0 PBR 三图、物理尺度和摘要。
- `assets/blender-material-library/material-acquisition.v1.json`：人工审过的 Poly Haven 材料 ID 与固定 1K 获取请求。
- `assets/blender-material-library/acquisition-manifest.v1.json`：实际下载来源、许可、文件大小和摘要回执。

HTML 与 Blender 共用布局数据，不共用几何资产。Camera 的 Blender 模板只传入冻结 plan、`.blend` 和本 Skill 批处理适配器；正式图片不得使用 Workbench。
