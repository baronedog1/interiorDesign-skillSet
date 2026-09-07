# 运行条件

五项安装于同一 skills 根；共用代码在本 Skill 的 scripts/engine，不是另一可调用 Skill。Python 3.10+，依赖见 scripts/requirements.txt。编译需要 jsonschema、shapely、numpy；截图另需 Playwright 和真实 Chrome/Edge。浏览器启动路径用 INTERIOR_CHROMIUM 指定。

来酷独立 Python：C:\ProgramData\GCPManager\runtimes\interior-design-gpt6-v2\Scripts\python.exe；Chrome：C:\Program Files\Google\Chrome\Application\chrome.exe。四个设计入口在 Windows 自动切到已安装的专用 Python，UTF-8 运行，不改变设备默认 Python。实际调用使用带引号绝对路径。模型、参考图、脚本产物均在来酷 C:\AgentWorkspaces\InteriorDesign 下，GCP 不保存过程文件。

双击完整 HTML 不需 Python。命令编译从 JSON 内嵌全部 JS/数据，不从网络加载 runtime。内置 GLB 样件在 scripts/engine/assets/library。未知风格检索由当前宿主联网，不在网页中读取登录态。

首次实际截图前确认内存、磁盘和浏览器资源；只开本任务一个浏览器，完成关闭该实例，不结束用户现有浏览器。纯语法检查不算 Windows 浏览器运行通过。

原生绘图是否可用以当前 Codex 工具为准；配置、说明书、准备回执都不能证明工具已实际调用。平台凭据仅由 idk-canvas-ingest-agent 管理。
