# 执行 Playbook

## 1. 冻结当前画面事实

验证 accepted `shot-scene-map.v9`。Q1/Q2/Q3、可见空间、连接、结构、槽位与 closed-world 集合必须属于同一 shot/model/camera。回读打包的正式 camera-plan 与 Q3 JSON，逐字段确认相机等于 Q1 水泥截图的 selected shot；主图必须仍是墙法向 `one-point-frontal`。相机后方或画外空间不能补回。

先执行 prompt-safe scene gate：`visibleRoomIds`、rooms、visibleFrame 与 closed-world 房间集合必须完全相等；结构/槽位/连接不得引用画外房间；visibleFrame 不得包含 excluded 决策。完整排除诊断只核验 QA audit 哈希，不进入后续 context、prompt 或 request。

## 2. 编排镜头

按 primary room 分组，每组第一张设为 `frontal-master`。之后关系图按可见房间/槽位求交集：有交集必须串行并依赖此前全部重叠 accepted 图；无交集才可进入同一并行 batch。

## 3. 编译请求

先用 `build_projection_lock.py` 从 scene map 生成完整区域锁，再依次运行 context、prompt manifest、request 构建器。当前纯水泥 Q1 锁相机和结构；当前 scene/context JSON 锁功能对象类别、数量、位置、占地、朝向和关系。默认槽位引导不提交 Q2 或 masks。先前图只继承共享对象和表面身份。用户指定家具图片必须先编译为 `user-product-reference-manifest.v1` 并逐槽位绑定；被拒绝、未完成或未绑定图片禁止回流。

## 4. 有限生成与诚实停止

先用 `build_imagegen_batch_plan.py` 生成 DAG，再交给 `imagegen-batch-orchestrator`。独立空间 job 在最多五路的受控 worker pool 中并发；共享空间或槽位的关系图等待依赖主图 accepted 后绑定请求。每张图完成即独立落盘，兄弟任务失败不取消成功结果，只重试失败 job。该上限不适用于本机截图。本阶段不得改 camera；每个正视主图最多三个候选，全部失败后停止；没有 imagegen receipt v4 就没有 Q4。

## 5. 终审

独立 invocation 对照 Q1、scene map JSON、Q2 QA 图与生成图：逐项枚举 required/forbidden，并为 scene map 中每个槽位、结构、连接提供完整区域对应。验证器校验 ID 全集并采用最大误差；任何墙门窗变化、对象漏项/多项、共享身份变化或外部边界室内化均拒绝。

## 6. 四象限

accepted 后只运行 `build_four_quadrant_delivery.py`。Q4 必须来自 imagegen receipt v4；不得手工把四张效果图、四张机位图或原生场景截图拼成“四象限”。

全部 shot/style 生成四象限 evidence 后，必须运行 `validate_render_plan.py render-plan.v11.json --require-complete`。最终门禁失败时直接按唯一错误归属修正；已经由算法确定且可逆的修正不向用户反复确认。

## 返工归属

- Q1/Q2/Q3 或可见集合错误：退回 `interior-camera-capture`；
- 原生结构/家具错误：退回对应建模 Skill；
- 当前图风格或身份不一致：本 Skill 按依赖顺序重做；
- 平面结构事实错误：退回 `interior-floorplan-planning`。
