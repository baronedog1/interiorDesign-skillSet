# Data Contract

## 输入

- 后端模板：`interior.camera-backend-template.v1`，活动值为 `html|blender|cad`。
- 当前结构：同项目、同 revision 的 `structure-data.json`。
- HTML：`current.html` 或首次 standalone，以及内嵌的 `current-model.json`/`coauthoring-model.json`。
- 可选用户机位意图：`interior.user-camera-intent.v1`；每个请求包含 roomId、shotId、有向 `desiredOpticalAxisXZ` 与 `sourceEvidence`，只在用户已明确确认方向时使用。
- Blender：accepted `.blend`、同 revision 结构与 HTML 已冻结的 `interior.algorithmic-camera-plan.v3`。
- CAD：accepted 原生模型、`interior.native-model-manifest.v1`、同 revision 结构与同一冻结 plan。

## 输入准备回执

HTML 场景生成使用 `interior.camera-input-preparation-receipt.v1`；Blender/CAD 原生场景包使用等价的 backend scene receipt。都必须包含：

- `status=complete|failed`；
- `downstreamReady`；
- 模型、结构、GLTF、semantic facts、native geometry 的路径和 SHA-256。
- `semanticInventory[].placementWorld`：从当前模型读取的源局部宽、深、高、旋转和中心，专门用于站位碰撞与方向判断；`world` 继续保存浏览器真实网格包络用于 VTK 显隐评分。

## 正式计划

`interior.algorithmic-camera-plan.v3` 由唯一求解器生成。每个 shot 至少包含：

- `shotId/roomId/sequenceOrder`；
- `position/target/fov/windowCenter`；
- `primarySubjectElementIds/framingElementIds/companionElementIds`；
- `hiddenWallIds/hiddenOpeningIds/hiddenElementIds`；
- `targetSpacePolicy.projectionCrop`：房内和后退镜头统一使用的目标房间墙体裁切框；`top=0`，左右与底部按原生投影决定；
- `frontalContract/targetSpacePolicy/algorithmEvidence`。
- `algorithmEvidence.analytic.fixtureFacadeAlignment/fixtureFacadeAxisCount`：靠墙设备有符号正面覆盖。
- `userCameraIntent`：若存在，记录用户确认的有向光轴及来源证据；所选光轴与它的点积必须不小于 `0.92`。
- `algorithmEvidence.nativePixelValidation.primaryFixtureMaxOverlap/primaryFixtureMinCenterSeparation`：多主体原生投影重叠与中心间距。

计划冻结后，任何渲染器和后端转换器都不得修改上述字段，也不得再次运行求解器。HTML/Blender/CAD 的正式图片事实必须记录相同 plan SHA-256。

## 图片事实

`interior.camera-image-facts.v3` 与 PNG 同名，至少记录：

- 当前冻结 shot；
- 图片尺寸、字节数和 SHA-256；
- 原始 viewport、最终裁切尺寸、裁切来源与裁切后重新映射的屏幕投影；
- 原生场景可见房间、墙、开口、家具及世界位置/尺寸/朝向/投影；
- Entity-ID、Depth 和首个射线命中证据；
- `imageRecognitionUsed=false`；
- `deliveryBlocked=false`。

## 流水线计时

`interior.camera-pipeline-receipt.v2` 记录 `backend`、backend template 路径/摘要、场景准备、初次求解、可选原生探测、最终求解、正式截图和总耗时，单位为秒。计时只用于性能分析，`deliveryBlockedByTiming=false`。

## 下游交接

- HTML/Blender/CAD 客户交付：PNG + facts v3 + delivery index。
- Blender 默认直接读取公共 plan v3；CAD 如需 v8 合同，由 `export_backend_camera_plan.py` 只复制冻结 pose，不能改选机位。
- 效果图：`interior-camera-capture` 直接把同名 `camera-image-facts.v3 + PNG` 交给 `interior-space-rendering`。Camera pipeline 完成且配对文件可读时即 `downstreamReady=true`，不再生成或等待 scene map。

## 目录与保留

推荐当前 run：`camera/input/`、`camera/plan/`、`camera/rendered/`、`camera/delivery/`。路径不是读取硬门禁，摘要和项目身份才是事实。

客户默认只交付 PNG、facts、机位图和索引。原始 Depth NPY、Entity-ID 原图、低分辨率候选和 diagnostics 是研发证据，默认保留在 run 内但不作为飞书附件批量外发。
