# 从多视图还原单品

这是 product-modeling 的照片还原分支；参数化结构和已有网格仍走主工作台。不是独立旧 Skill，也不要求普通参数柜先做图像投影。

1. 冻结原图、尺寸和许可。通过 extract_view_regions.py 从原始像素、组件种子和梯度提取区域；validate_view_regions.py 检查覆盖、遮挡与可逆像素注册。图像 SHA 变化后重新提取受影响证据。
2. 选择正交主视图并登记世界坐标；carve_visual_hull.py 逐组件把主掩膜挤出，再与其他正交视图挤出体求交。透视图未求解相机时只作外观参考，不伪作正交证据。
3. compare_view_projection.py 将同一状态按原注册回投影。对接受的源掩膜逐组件比较 xorPixels、IoU、precision、recall。严格掩膜还原成功是 xorPixels=0、IoU=1；例：目标100像素，预测漏2像素，则异或2、交集98/并集100=0.98，不可报精确通过。无该视图是缺失，不是误差0。
4. 不相容视图保留差异并修源配准/分区，不移动边界伪造通过；仅该还原分支受影响。单视图仍可交付 provisional，缺失轴和隐藏结构逐项写 inferred；不伪称多视图实测。
5. build_product_standalone.py 用唯一 visual-hull-state 生成自包含 HTML。同一几何支持白模与源色。实际桌面/手机看图、交互、无空白及溢出后记录 browser QA；测试 fixture 不代替人工/真实浏览器。
6. build_component_package.py 绑定源图、区域、plan、state、投影、HTML与浏览器摘要；validate_package.py 复查。完整无推断且验收通过是 accepted，有推断仍 provisional。可交付明确标识的预览，不把缺失数据扩大为全任务停止。
7. 要进入共用工作台时运行 export_visual_hull.py：同一体素状态生成真实 GLB 和 product.json，之后 build_product.py 生成产品 PDF。该 GLB 编辑后不能沿用原投影验收，需重新验证几何与证据。组件包用于项目交接，公共组件库由用户另行指定的库入口管理。

脚本参数见 scripts/scripts.md；证据字段见 data_contract.md。旧版的固定品类、禁止任务内补依赖、必须先全设备QA才启动等通用限制不继承。
