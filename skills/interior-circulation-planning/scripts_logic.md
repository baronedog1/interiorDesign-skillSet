# 脚本职责

## `common.py`

提供 JSON、SHA-256、点线面关系、轮廓变换和确定性输出工具；不单独作为命令运行。

## `build_circulation_scene.py`

校验完整事实链，将 HTML、Blender 或 CAD 当前布局归一化为同一平面 scene。任何 ID、哈希、原生模型或精确轮廓缺失均以非零状态退出。

## `audit_circulation.py`

构建结构基线和当前布局两张自由空间图，运行开口拓扑、外部入口可达性、房间穿行、
最大瓶颈净宽及贴墙/面向审计，输出 JSON 与 SVG。accepted 类状态返回 0，
`blocked-input-integrity` 返回 2，`needs-layout-adjustment` 返回 3；调用方不能把进程成功等同业务通过。

## `plan_layout_adjustments.py`

对被归因组件确定性搜索同房间路线修复、贴墙和面向候选，按固定键排序，每轮只授权一个
`apply-without-user-confirmation` 操作。它不写模型、不改结构；无安全候选输出
`algorithm-blocked`，失败向量未改善输出 `algorithm-stalled`，均以非零状态退出。

## `finalize_circulation_delivery.py`

核对 Agent 视觉证据和所有绑定哈希。audit 尚有布局/输入错误、证据文件变化、漏审路线或任一视觉检查失败时拒绝生成 result。

所有脚本只使用 Python 标准库，输出采用确定性字段顺序和 canonical SHA-256。
