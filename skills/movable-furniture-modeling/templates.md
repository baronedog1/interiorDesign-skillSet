# 模板

- `templates/standalone.html` 是唯一单产品 HTML 壳，由 `build_product_standalone.py` 注入唯一 state、
  本地 Three.js 与 OrbitControls。
- `assets/vendor/` 是固定浏览器资源；正式 HTML 必须内嵌，不能依赖 CDN。
- 审阅图由 `extract_view_regions.py` 直接从 evidence 的产品/组件掩膜生成，不维护第二套 SVG 轮廓。
- standalone 默认 `white-model`，可切换 `source-color`；两种状态只改变材质。页面公开
  `__PRODUCT_APPEARANCE__` 与绑定同一 state 哈希的 `__PRODUCT_STANDALONE_READY__`，不生成第二份 HTML。
