---
name: imagegen-batch-orchestrator
description: 当上游已经给出多图片 ImageGen 依赖计划时使用。为每张图建立独立、持久、可恢复的 job，在依赖允许时最多五路真并发，完成即原子落盘，单图失败只重试该图。本 Skill 不拥有业务提示词、空间依赖或验收规则。
metadata: {"category":"image-generation","skill_type":"infrastructure","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"batch_plan_schema":"imagegen.batch-plan.v1","batch_receipt_schema":"imagegen.batch-receipt.v1","version":"2.0.0"}
---

# ImageGen Batch Orchestrator

## 输入

唯一输入是上游 accepted `imagegen.batch-plan.v1`。每个 job 必须有稳定 ID、请求文件与 SHA、依赖、输出名和最大尝试次数；依赖 job 可在前置结果 accepted 后延迟绑定请求。

## 输出

- 每个 job 的独立状态和事件日志；
- 每张成功图片的路径、SHA、大小和 provider/invocation ID；
- `imagegen.batch-receipt.v1`；
- 中断后可从未成功 job 继续的检查点。

## 唯一流程

1. `init` 冻结计划；重复初始化相同计划幂等，不同计划拒绝覆盖。
2. `ready` 从整个 DAG 返回依赖已成功且当前并发额度允许的 job；批次只表达拓扑层级，不构成整批屏障。
3. 每个 job 独立 `start` 并独立调用 ImageGen。
4. 每张结果返回后立即 `succeed` 原子落盘；失败立即 `fail`，不取消已完成的兄弟 job。若远端图片已经返回、只有本地落盘适配失败，必须从返回信息解析真实文件路径并用 `succeed --late-result` 接收原尝试，禁止重新生图。
5. 等待使用 `allSettled` 语义；聚合等待器不能拥有图片结果。
6. 中断后 `recover` 回收陈旧 running job，只重试未成功且仍有额度的 job。
7. 全部成功后 `finalize` 生成唯一回执。

## 并发规则

- `maxConcurrency` 为 `1..5`，只限制远端 ImageGen job。
- 同批 job 必须由上游证明可并行；本 Skill 不猜空间关系。
- 共享空间、槽位或身份参考的 job 必须通过依赖串行。
- 一个较早批次中的无关慢任务，不得阻塞依赖已经完成的后续 job。
- 每个调用有独立状态、请求 ID 和落盘回执，禁止用一个不可恢复的 `Promise.all()` 承载整批结果。
- `output_hint` 可能是包含路径的说明文字；调用层必须提取其中真实存在的图片文件。不能把整段说明当作路径，也不能因此重复调用 ImageGen。
- 本机 Chrome、Blender、CAD 截图不使用本 Skill 的五路额度。

## 硬停止

- 计划 schema、请求 SHA、依赖图或输出路径不合法；
- 依赖成环或跨批次倒序；
- 成功输出被篡改；
- 不可重试 job 失败。

单图可重试失败、进程中断和兄弟 job 失败只影响对应 job，不要求用户确认，不重做已成功图片。

## 时间观测

记录每个 job 的排队、调用和落盘时间，以及批次墙钟时间和串行时长总和。时间不作为业务门禁。

## 高频数据入口

- 数据合同：[data_contract.md](data_contract.md)
- 脚本职责：[scripts_logic.md](scripts_logic.md)
- 本地命令：[local_runtime.md](local_runtime.md)
- 环境边界：[ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)
