# 设备外置运行配置

本包在 Ubuntu、Windows 来酷和 Genmachine 使用同一份业务代码。Python 3.10+、Node、Chrome/Edge、中文字体及依赖由本机设计 runtime 配置提供；优先用设备登记的 interior-python 包装入口。普通任务不临时安装软件。所有输入和交付保存在当前设备当前工作区。

HTML 和截图共享 interior-html-modeling/scripts/engine。纯 HTML 离线打开不需要 Python；编译依赖 jsonschema、shapely、numpy，截图使用 Playwright 和 INTERIOR_CHROMIUM 指定的浏览器。资源盒由本机包装器沿用，任务结束只关闭本次浏览器。依赖列表见正式 scripts 中的 requirements 文件。

平台凭据通过设备既有 IDK_ENV_FILE 或私有 .runtime 链接提供，分发包不包含凭据；不得跨设备复制登录态。原生绘图使用当前宿主实际提供的绘图工具，准备文件不等于生成图片。
