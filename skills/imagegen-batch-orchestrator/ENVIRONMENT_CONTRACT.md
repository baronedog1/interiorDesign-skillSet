# 环境合同

## 多设备运行规则

- 无固定设备路径；Python、任务状态目录和输出目录以当前设备 runtime inventory 与任务工作区为准。
- 本 Skill 不安装模型工具、不读取 API Key；只有当前 Codex 会话实际提供原生 `imagegen` 且最小 job/receipt 通过时才登记 `ready`。
- 缺生成能力时在 `init` 前标记 `blocked`，不得把计划编排成功误报成图片生成成功。

- Python 3.10+，仅使用标准库。
- 状态目录必须位于当前任务可写目录。
- 图片生成使用 Codex 内置 `imagegen` 工具；本 Skill 不读取 API Key。
- 文件系统需要支持 `fcntl.flock` 和同目录原子替换。
- 网络、模型、速率限制和计费由调用图片工具的运行环境管理。
