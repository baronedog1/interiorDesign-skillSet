# 设计链意图路由

| 用户意图 | 首个 Skill | 后续 |
|---|---|---|
| 对户型做平面规划、描线、四象限 | `interior-floorplan-planning` | 产出唯一 handoff |
| 对户型建模，未指定后端 | `interior-html-modeling` | 机位 -> 渲染 |
| 用 HTML/Three.js 建户型 | `interior-html-modeling` | 机位 -> 渲染 |
| 用 Blender 建户型、交付 `.blend` | `interior-blender-modeling` | 机位 -> 渲染 |
| 用 Text2CAD/CAD 建户型、交付 STEP | `interior-cad-modeling` | 机位 -> 渲染 |
| 找角度、截图、四象限机位 | `interior-camera-capture` | 可进入渲染 |
| 空间不变出效果图 | `interior-space-rendering` | 可进入图册/平台 |
| 单个家具或柜体建模 | `movable-furniture-modeling` | 交付单品 HTML/组件包 |
| 方案册/PDF | `booklet-production` | 可进入平台 |
| 创建项目、上传、社区发布 | `idk-canvas-ingest-agent` | 平台回读验收 |

三种完整户型后端平级，直接消费同一 accepted handoff。明确要求多个版本时冻结同一 handoff 并分别编译；任何一个后端的模型、回执、组件库或截图都不成为另一个后端的输入。

机位和渲染分别只有一个正式 Skill。它们通过 `native-model-manifest.v1`、`camera-plan.v8` 和 `shot-scene-map.v9` 兼容三个后端，不复制三套算法。
