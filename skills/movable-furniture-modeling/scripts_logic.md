# 脚本职责

| 脚本 | 职责 |
| --- | --- |
| `extract_view_regions.py` | 用源图、产品/背景种子和组件种子生成源分辨率产品与组件区域 |
| `validate_view_regions.py` | 验证哈希、RLE、覆盖、唯一归属、背景排除和坐标注册 |
| `mask_utils.py` | 提供 evidence、雕刻和回投影共用的唯一 RLE 掩膜编解码与像素集合运算 |
| `carve_visual_hull.py` | 主视图拉伸并与其余正交掩膜棱柱逐项求交，输出唯一 state 与网格 |
| `compare_view_projection.py` | 从最终占用体回投影，计算逐组件/整件 XOR、precision、recall、IoU |
| `build_product_standalone.py` | 从 state 生成内嵌 Three.js 的单文件交互 HTML |
| `build_component_package.py` | 绑定逐视图 evidence/源图、plan、不可变 state、零异或报告、standalone、桌面/手机 browser QA 与同几何白模/源色合同，并唯一派生包状态 |
| `validate_package.py` | 校验 Skill 文件图、Schema、单一流程和禁止旧逻辑 |

Agent 只提供语义、种子、遮挡和缺失方向假设；最终掩膜、体素求交、网格、指标与 pass 只能由代码
确定性生成。
