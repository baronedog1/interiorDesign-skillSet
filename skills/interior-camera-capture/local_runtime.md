# 截图环境

依赖同安装根 HTML Skill 的 scripts/engine，具体 Python、Playwright 和 Chrome 路径见 [运行说明](../interior-html-modeling/local_runtime.md)。本 Skill 的 capture 是正式模型截图入口；渲染 Skill 不重复提供截图入口。

截图前确认当前 HTML 同版、Windows 原生浏览器可初始化 WebGL2；Linux 开发回归不能充当 Windows 验收。render_shots 只关闭本次创建的 browser，不重启桌面、Bridge 或其他会话。

Windows SSH/服务会话的桌面 D3D 上下文存在间歇性初始化失败。自动截图的独立离线 Chrome 默认使用 SwiftShader 软件 WebGL；不是 AI 图片、不是硬件 GPU 验收，也不改变用户桌面 Chrome 设置。明确验证后可设置 INTERIOR_HEADLESS_RENDERER=hardware。仅加载本任务生成的离线模型，不用此自动化实例浏览外站。是否可用以实际文件页面 ready/加载错误为准，不在 about:blank 先做阻断检查。

输出文件在来酷项目目录；renders.json 保留 sourceType=webgl，与原生生成严格区分。几何候选状态不阻止实际截图；真实浏览器失败单独报告，不捏造 PNG。
