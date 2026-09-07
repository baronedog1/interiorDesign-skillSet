# 执行流程

1. 从工作区唯一当前 HTML 提取 `current-model.json`；首次生成可直接使用 `coauthoring-model.json`。
2. 运行 `audit_user_returned_html.py --model ... --out ...`。
3. 把风险按位置去重，用自然语言告诉用户；不移动家具、不覆盖 HTML。
4. 无论风险数量多少，立即把当前模型交给 `interior-camera-capture`。

旧 `build_circulation_scene.py -> audit_circulation.py -> finalize_circulation_delivery.py` 只用于兼容历史结构和发版研究，不是用户回传 HTML 的生产入口。
