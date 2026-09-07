# 来酷运行环境

使用已有 `C:\ProgramData\GCPManager\runtimes\interior-design-gpt6-v2\Scripts\python.exe`，复用 Playwright、Pillow，新增固定 PyMuPDF `1.28.2`。Chrome 为 `C:\Program Files\Google\Chrome\Application\chrome.exe`，可用 CHROME_BIN 指定管理员登记路径。中文字体使用 Windows 宋体和微软雅黑；不能假称已使用不存在的商业字体。

安装／升级依赖由设备管理员完成，普通排版不临时安装。浏览器仅创建独立 headless 实例并在 finally 关闭，不改桌面 Chrome。模板纯本地渲染，不需要平台凭据或外部出口；素材先经已授权渠道下载到来酷项目，再传本地路径。

来源：Ubuntu booklet-production 3.3.0 的叙事与视觉规范；此 4.1.0 是来酷 Windows 定制版，Ubuntu 不修改。确定性排版器与模板为本版实现，不继承旧 manifest / validator / Linux 命令链。
