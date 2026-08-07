# 脚本职责

| 脚本 | 唯一职责 |
|---|---|
| `validate_circulation_gate.py` | 在任何机位计算前验证动线 result 已接受，并与当前后端、floorplan、handoff 和原生模型哈希一致 |
| `solve_frontal_camera_seeds.py` | 从结构、动线场景/result 和原生模型身份，为拍摄范围内每个空间稳定求解唯一 `one-point-frontal` 主种子；不截图、不做主观选片 |
| `calculate_camera_geometry.py` | 只从正视 seed、三个原生 OBB envelope、焦段链、可退距和真实背景墙生成公共坐标有界候选 |
| `compile_camera_candidates.py` | 一次读取全部正视 seed 和原生 envelope 测量，批量调用唯一几何公式并输出与 seed/model/hash 绑定的候选 batch；不允许逐空间手工重抄参数 |
| `validate_camera_manifest.py` | 同时读取 camera plan v8、正视 seed set、候选 batch、原生模型清单和结构 v3，独立重跑 seed 算法，并重算逐空间正视覆盖、宿主空间归属、真实可退距、模型哈希、原生截图相机状态、构图公式、墙法向、射线、边距、尺度；拒绝手写 seed、手抄候选、复用其它机位证据、无界重试或非首个合格候选 |
| `capture_model_views.py` | 正式截图唯一入口；先复验 camera plan/model scope/结构/原生模型哈希，再检查设备内存、swap、load、PSI、磁盘和 `/tmp`，持有最多两个设备级截图槽位后按 `modelBackend` 调度唯一原生适配器，并保存前后压力证据 |
| `view_visibility.py` | 按唯一策略从原生像素覆盖、功能对象归属和洞口前向深度编译当前提示词可见集合，并复制无组件、无槽位标记的纯水泥 Q1；Room mask 仅作 QA |
| `build_shot_scene_map.py` | 从 backend-native `scene-semantic-frame.v4` 单向编译 `shot-scene-map.v9`，只保留当前相机前方可见事实、完整槽位位置/关系及 required/forbidden/外部边界终止合同；excluded 决策另写 QA-only visibility audit |
| `validate_shot_scene_map.py` | 回读 camera plan、原生 semantic frame 与 visibility audit，逐主角边距、房间、开口、结构、槽位、封闭世界合同、Q1/Q2 证据资产和模型哈希验证，并拒绝任一 excluded ID 泄漏到 scene map |
| `build_camera_quadrant_sheet.py` | 固定排版 Q1 纯水泥空结构、Q2 同机位家具 QA、Q3 平面相机，Q4 只保留 accepted render 占位 |

HTML、Blender、CAD 的坐标转换和截图实现分别归各自建模 Skill，但真实执行只能由本 Skill 的正式调度器进入。本 Skill 不保存第二套 HTML 截图器、Blender 场景构建器、CAD 渲染器、二维机位手绘器、图片识别器、随机试角脚本或模式选择器；项目脚本不得直接启动截图进程。
