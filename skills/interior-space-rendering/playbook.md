# 执行 Playbook

## 1. 读取当前事实

读取 Camera 同名 JSON 与 PNG。只检查文件是否真实存在、摘要是否一致、项目与 shot 身份是否明确。这是技术输入确认，不评价画面好坏。

## 2. 编译一次正式请求

运行 `compile_render_request.py`。Camera PNG 作为当前相机、结构、开口、家具排列和画面范围的图像依据；facts v3 中的 semantic inventory 与 visible scene 作为对象类别、数量、位置、尺寸和朝向依据。用户参考图只拥有对应产品或风格外观解释权。

编译器把 Camera 自带的 `subjectFocus.advisoryIssues` 和算法提示写入 context，但仍输出请求。旧 scene-map、Q1/Q2/Q3、mask、四象限和 accepted review 不再参与本流程。

## 3. 生成与并发

每个 shot/style 只形成一个正式请求，默认 `maxAttempts=1`。多空间无额外质量依赖，可交给 `imagegen-batch-orchestrator` 最多五路执行；工具级失败由编排器记录，不用质量重试，也不重做已经成功的图片。

## 4. 交付

ImageGen 返回可读图片后立即运行 `finalize_render_delivery.py`。Agent 可以把肉眼发现的问题作为 `--advisory` 写入回执，但回执固定 `status=delivered`、`deliveryBlocked=false`。图片、回执和提示一起交付。

## 5. 失败处理

- JSON/PNG 缺失或损坏：修事实源，不能换历史图。
- 身份冲突：定位项目唯一 current model 与 Camera run，不能猜。
- ImageGen 无图片：记录工具错误并说明未产生图片。
- 画面不好但图片存在：仍交付，后续只修改公共算法或提示编译逻辑。
- 付费、公开发布、删除、生产覆盖或批量外发：执行前取得用户确认。
