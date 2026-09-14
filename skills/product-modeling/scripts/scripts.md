# 可执行脚本索引

命令均从Skill根目录执行。

| 文件 | 作用与调用 |
| --- | --- |
| build_workbench.py | 将维护源内联为唯一无产品HTML：`python scripts/build_workbench.py` |
| evaluate.cjs | 用浏览器同源内核检查/求值：`node scripts/evaluate.cjs expected_outcome/cabinet/cabinet.product.json` |
| build_product.py | 单产品生成GLB、同源PDF和清单：`python scripts/build_product.py PRODUCT.json --out OUTPUT_DIR --preview preview.png`；preview可省略 |
| product_manual.py | 由build_product调用，生成当前产品PDF，不是独立命令入口 |
| serve.py | 本机自动加载：`python scripts/serve.py` |
| blender_import.py | 有Blender的设备可执行：`blender --background --python scripts/blender_import.py -- MODEL.glb MODEL.blend`；本轮未运行 |
| build_skill_manual.py | 同源JSON生成Skill PDF/MD/SVG：`node scripts/build_skill_manual.mjs` |
| package_skill.py | 检查文件与清单并打包：`python scripts/release.py zip . --out ../product-modeling.zip` |

`tests/kernel.test.cjs` 验证数据与参数关系；`tests/browser_smoke.py --out work/browser-checks` 实际打开HTML、修改、保存、导出并重新载入，依赖Playwright和本机Chromium。Linux软件WebGL可用 `xvfb-run -a python tests/browser_smoke.py --out /tmp/product-checks`。不可用浏览器时标注未执行，不把脚本存在当通过。

生成器不修改不相关的产品，不将整个Skill复制进单产品输出。需清理时只删除当前工作区中的已知临时文件；不自动删除用户Library内容。

## 多视图与组件交付

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

`python scripts/export_visual_hull.py state.json --mm-per-unit 1 --out work/carved`：按实测单位转换同一状态到共用工作台；`python scripts/export_quad_obj.py input.npz --out work/model.obj`：导出已有四边面源。

## 本 Skill 发行维护
修改正式文件后先重生成说明书，再执行 `python scripts/release.py inventory .` 登记摘要、`python scripts/release.py check .` 核验；需要ZIP时执行 `python scripts/release.py zip . --out /目标/skill.zip`。仅发行维护使用，不作为普通业务任务前置门禁。
