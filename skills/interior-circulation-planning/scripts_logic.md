# 脚本职责

| 脚本 | 正式职责 |
|---|---|
| `audit_user_returned_html.py` | 直接读取当前模型，生成拓扑、净距和自然语言非阻断提示 |
| `build_circulation_scene.py` | 历史输入兼容与发版研究 |
| `audit_circulation.py` | 复杂回归研究；不得作为用户回传 HTML 门禁 |
| `finalize_circulation_delivery.py` | 历史结果兼容 |

正式脚本发现风险时仍退出 0。无法解析文件可以报错，但不能把设计风险变成失败码。
