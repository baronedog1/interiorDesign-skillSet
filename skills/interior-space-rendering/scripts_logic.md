# 脚本职责

| 脚本 | 唯一职责 |
|---|---|
| `render_contract.py` | 重算 prompt-safe closed-world facts、scene-map 投影锁、正式 Q1/Q3/camera-plan 相机权威、有限执行策略、空间重叠依赖、并行批次和唯一提示词；拒绝机位漂移、excluded 诊断或画外 ID 泄漏 |
| `build_projection_lock.py` | 从 scene map 全量房间、结构、连接和槽位区域确定性编译 `projectionLock` |
| `build_scene_prompt_context.py` | 从 plan v11 + scene map v9 绑定纯水泥 Q1、精确槽位/关系、建筑处理、已 accepted 身份参考和逐槽位用户产品参考，生成 context v7；Q2/masks 永远只作 QA |
| `build_imagegen_batch_plan.py` | 从 plan v11 与各 shot request v4 确定性生成 imagegen batch DAG；独立镜头同批，共享空间/槽位镜头建立依赖，远端并发默认且最高为 5 |
| `build_prompt_manifest.py` | 从 context 唯一生成 prompt manifest v7，禁止手工清单 |
| `validate_prompt_manifest.py` | 核对唯一槽位引导的 Q1、JSON 与依赖参考；拒绝把 Q2/masks 提交给图像模型 |
| `build_imagegen_request.py` | 用 `closed-world-scene-v2` 编译 request v4，并限制提示词不超过 32KB |
| `validate_imagegen_request.py` | 重算 prompt、事实 digest 和图片附件链 |
| `validate_user_product_reference_manifest.py` | 验证用户产品图片、图中产品区域、产品类别及逐槽位绑定，限制其仅拥有外观身份权 |
| `validate_generation_receipt.py` | 只验证真实 imagegen receipt；拒绝原生场景截图回退 |
| `validate_render_review.py` | 以 scene map 全量 ID 为基准，重算每个对象、结构、连接区域及主要墙线的最大误差，拒绝抽样、漏项和删除失败证据 |
| `validate_render_plan.py` | 普通模式验证全局 shot 调度与可继续执行状态；`--require-complete` 强制每个 shot/style accepted 且绑定已复验四象限 evidence，是唯一最终完成门禁 |
| `build_four_quadrant_delivery.py` | 从同一 shot 的 accepted 证据确定性生成 Q1/Q2/Q3/Q4 |
| `validate_four_quadrant_delivery.py` | 核对四象限顺序、来源、哈希、尺寸和同 shot/model 身份 |
