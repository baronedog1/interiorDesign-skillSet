# 脚本职责

所有正式代码只在本 Skill 的 `scripts/` 中；未登记脚本不得作为生产入口。

| 脚本 | 唯一职责 | 停止条件 |
|---|---|---|
| `compile_render_request.py` | 从 Camera v3 facts 与配对 PNG 直接编译 plan/context/request/batch plan；质量提示只写入产物 | JSON/PNG 不可读、摘要损坏、身份冲突 |
| `finalize_render_delivery.py` | 把实际 ImageGen 图片绑定到请求并记录非阻断质量提示 | 请求不可读或没有实际图片 |

两个脚本均不调用付费 API、不执行发布、不删除项目文件。ImageGen 由当前运行环境或 `imagegen-batch-orchestrator` 执行。
