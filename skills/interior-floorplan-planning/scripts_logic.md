# Scripts

| 脚本 | 唯一职责 |
|---|---|
| `build_wall_geometry.py` | 从冻结候选的两条源图边确定性生成墙带 |
| `topology_compiler.py` | 直接注入唯一墙几何、物理开口决定和独立语义分界，再从带空间类型的独立种子一次生成净地面、真实空间、面积、墙邻接与连接两侧；种子必须与其不可变源房名锚点落在同一区域 |
| `render_floorplan_quadrants.py` | 按 `layoutAuthority` 把结构层固定到原图、对象层固定到原图或 accepted 原生布局图，生成机器绑定图、六张分层复核图、四象限和独立结构图 |
| `validate_source_model.py` | 一次检查哈希链、结构/家具双事实源、同画布结构锁、门窗图形签名、唯一原图坐标系、辅助图双向变换与五点往返、六张分层叠图、墙/开口/对象输出对其权威图可见线的支持、对象与物理净开口互斥、对象轮廓与编译空间 assignment 一致、对象一对一消费、不可变房名与独立种子同区、空间拓扑和 Agent 逐项视觉绑定 |
| `finalize_floorplan_handoff.py` | 编译唯一结构数据，锁定对象候选到绿紫描线及组件的一对一关系，调用上述一次检查，注册来源并封装 `floorplan-handoff.v3` |
| `validate_structure_edit_patch.py` | 验证三个建模后端导出的沿轴墙端点补丁，并强制通过新平面/模型 revision 提交 |

authored spec 不含墙、门窗/通道/语义分界坐标、房间多边形、面积或拓扑输出。物理开口只引用 `sourceOpeningId`，窗只引用一个 `hostWallTraceId`；finalizer 验证窗源线与宿主墙平行且两端投影都在墙段内。无实体墨线的功能分界只引用 `sourceDividerId`；`traversal=open-passage` 才能同时生成连接，`boundary-only` 只生成边界。绿紫对象只引用冻结的 `sourceObjectCandidateId`。编译器在同一像素拓扑中生成房间和整户边界，并让贴外墙房间与 `floorBoundary` 共享精确边界顶点；轮廓简化偏差超过固定的两倍简化精度即失败。没有第二套结构表、对象表、对齐检查、流水线检查或消费者图像复验。下游只核对正式包的哈希、唯一报告和来源 ID。
