# Environment Contract

- 共享基线：`/home/baronedog111/gcp-manager/skills/interior-camera-capture`。
- Ubuntu 活动副本：`/home/agentops/.codex/skills/interior-camera-capture`。
- Ubuntu 运行用户：`agentops`。
- Python 运行时：`/home/agentops/agent-runtime/runtimes/interior-camera-capture-39`，不写入 Skill 目录。
- 固定依赖：Python 3.14、NumPy 2.3.5、Pillow 12.1.1、SciPy 1.18.1、VTK 9.7.0。
- HTML Node：`/home/agentops/agent-runtime/bin/node`。
- HTML Chrome：`/home/agentops/agent-runtime/bin/render-chrome`。
- Blender：`/home/agentops/agent-runtime/bin/blender`，只通过 Ubuntu 渲染任务盒运行。
- 后端模板：Skill 内 `assets/backend-templates/`；模板不得包含另一套相机选择算法。
- 本 Skill 不保存模型、HTML、平台凭据、Cookie 或 Codex auth。
- VTK 可在无 X Server、无 GPU 权限时使用软件路径；EGL 警告必须记录，但只有输出缺失才算失败。
- Chrome、Blender 与 CAD 截图统一进入各自 Ubuntu 渲染任务盒子；不设置固定的启动前空闲内存或 load 门槛，由设备资源队列决定立即执行或等待，并在资源耗尽时只回收当前截图任务。
- 同步 Skill 文件不要求重启 Bridge。旧 TUI 只有在需要重新加载新 Skill 文档时才按会话反思规范换新，不得为了文件同步直接杀 pane。
- GCP 与 Ubuntu 活动树必须逐文件一致；回滚只保留上一版不可执行归档。
