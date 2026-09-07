# 数据合同

## 输入

`interior.camera-image-facts.v3` 与 `image.filename` 指向的同目录 PNG。JSON 至少包含 `generation`、`shot`、`image`、`visibleScene` 与 `semanticInventory`。

技术输入必须满足：JSON 可解析、`generation.imageRecognitionUsed=false`、shot/floorplan/room 身份非空、PNG 可读且 SHA-256 与 JSON 一致。对象缺失、构图提示或画面质量属于 advisory，不成为 schema 拒绝原因。

## 输出链

```text
camera-image-facts.v3 + paired PNG
  -> interior.model-image-render-plan.v13
  -> interior.render-context.v9
  -> interior.imagegen-request.v5
  -> optional imagegen.batch-plan.v1
  -> generated PNG
  -> interior.render-delivery.v1
```

## `render-context.v9`

记录 floorplan、shot、room、style、相机、可见空间、墙/开口、全部功能对象、当前模型截图、质量提示和非阻断策略。`functionalObjects` 来自 Camera semantic inventory，不由 Agent 手写。

## `imagegen-request.v5`

记录唯一 prompt、当前模型截图、可选参考图和 context 摘要。`executionPolicy.formalGenerationCount=1`、`qualityRetryForbidden=true`、`deliveryBlockedByQuality=false`。

## `render-delivery.v1`

只要 ImageGen 返回可读图片，就写 `status=delivered`、图片摘要和 `qualityAdvisories`。没有 `accepted/rejected` 质量状态；回执不宣称图片完美。

## 目录

推荐输出为 `render-plan.v13.json`、`contexts/`、`requests/`、`imagegen.batch-plan.v1.json`、`outputs/` 和 `delivery/`。路径是推荐布局，不是质量门禁。
