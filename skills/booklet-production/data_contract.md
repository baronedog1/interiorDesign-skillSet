# 数据合同

## `booklet-brief.json`

```json
{
  "schema": "interior.design-booklet.v2",
  "projectId": "project-001",
  "audience": "client",
  "language": "zh-CN",
  "aspectRatio": "A4-portrait",
  "deliverables": ["pdf-highres", "pdf-sendable"],
  "whiteModelInset": {
    "enabled": true,
    "userExplicitlyDisabled": false,
    "preferredPositions": ["top-right", "bottom-right", "side-rail"],
    "widthRatioRange": [0.16, 0.28]
  },
  "includeTraceAppendix": false
}
```

`includeTraceAppendix` 默认 false；只有用户明确要求审计材料时才可设 true。

## `asset-register.json`

```json
{
  "schema": "interior.booklet-asset-register.v1",
  "assets": [
    {
      "assetId": "planning-clean",
      "role": "planning",
      "path": "assets/planning.png",
      "qaStatus": "passed"
    },
    {
      "assetId": "sofa-product-front",
      "role": "user-product",
      "path": "assets/sofa-front.jpg",
      "productId": "custom-sofa-001",
      "customPackageId": "custom-sofa-001-v1",
      "usedInSpaceIds": ["living"],
      "qaStatus": "passed"
    },
    {
      "assetId": "living-white-model",
      "role": "white-model-shot",
      "path": "assets/living-white.png",
      "shotId": "living-sofa-80",
      "qaStatus": "passed"
    },
    {
      "assetId": "living-render",
      "role": "final-render",
      "path": "assets/living-final.png",
      "renderId": "living-sofa-80-modern",
      "shotId": "living-sofa-80",
      "sourceSceneMap": "scene-maps/living-sofa-80.json",
      "qaStatus": "passed"
    }
  ]
}
```

允许 role：`planning|user-product|white-model-shot|final-render|detail|material`。

## `page-specs.json`

```json
{
  "schema": "interior.booklet-pages.v2",
  "pages": [
    {
      "pageNumber": 4,
      "section": "space",
      "spaceId": "living",
      "headline": "客厅",
      "layoutMode": "hero-with-top-right-white-model",
      "layoutReason": "主效果图承担情绪，右上小图证明机位与空间关系。",
      "primaryAssetId": "living-render",
      "whiteModelInset": {
        "enabled": true,
        "assetId": "living-white-model",
        "position": "top-right",
        "widthRatio": 0.22,
        "label": "空间原图"
      },
      "supportingAssetIds": ["sofa-product-front"],
      "bodyText": "以完整沙发墙为视觉中心，保留两侧真实留白。"
    }
  ]
}
```

section 顺序固定为：

`cover -> planning -> user-assets -> space -> detail/material -> closing`

空间页的 `primaryAssetId` 与 `whiteModelInset.assetId` 必须拥有同一 `shotId`。

## 输出目录

```text
<booklet>/
  booklet-brief.json
  asset-register.json
  page-specs.json
  source-reference.json
  images/
  html/index.html
  html/styles.css
  output/final-highres.pdf
  output/final-sendable.pdf
  qa-report.md
  manifest.json
```
