---
name: imagegen-batch-orchestrator
description: 执行已规划的多图片 ImageGen 任务；为每张图建立独立、持久、可恢复的作业，按依赖批次限制并发，完成一张立即落盘，只重试失败项。用于多机位、多空间或多版本图片生成，不负责决定业务提示词、空间依赖或验收标准。
metadata: {"category":"image-generation","skill_type":"infrastructure","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"batch_plan_schema":"imagegen.batch-plan.v1","batch_receipt_schema":"imagegen.batch-receipt.v1","version":"1.1.0"}
---

# ImageGen 批量编排

## 使用前准备

- 本地只需 Python 3.10+ 标准库和支持原子写入/`fcntl.flock` 的可写任务目录；图片生成依赖当前 Codex 会话已提供原生 `imagegen` 能力。
- 先读取 [ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md) 与 [local_runtime.md](local_runtime.md)，确认 batch plan、请求文件、输出目录和 receipt 目录可写。
- 上游必须先给出完整 `imagegen.batch-plan.v1`；缺少调用能力、计划或可写目录时在首次 `init` 前标记 `blocked`，不得把 API Key 写入 Skill 或临时改造并发器。

## 职责

本 Skill 只执行上游给出的 `imagegen.batch-plan.v1`。上游业务 Skill 决定每张图的输入、依赖和可并行批次；本 Skill 负责独立状态、并发调用、即时保存、失败隔离与续跑。

不在本 Skill 中重写提示词、猜测任务依赖、放宽图片验收标准或决定业务流程。

## 唯一流程

1. 上游生成计划，并保证每个 job 有独立请求文件、请求哈希、依赖、输出文件名和最大尝试次数。
2. 运行 `scripts/manage_imagegen_batch.py init` 冻结计划。
3. 运行 `ready` 读取当前可执行 job；同一返回批次可并发，不同批次不可越过依赖。
   依赖图完成后才生成的请求，先运行 `bind-request` 绑定请求文件和哈希。
4. 对每个 ready job 先运行 `start`，再发起独立 ImageGen 调用。
5. 每张图返回后立即运行 `succeed`；单张失败运行 `fail`，不得取消或重做已成功的兄弟 job。
6. 进程中断后运行 `recover` 回收超时的 running job，再从 `ready` 继续。
7. 全部成功后运行 `finalize`，输出唯一回执 `imagegen.batch-receipt.v1.json`。

## 调用约束

- 使用有上限的并发，不使用一个不可恢复的聚合调用承载整批结果。
- `maxConcurrency` 只允许 `1..5`；业务计划默认可用 `5`，但 `ready` 仍受依赖批次和当前 running 数量约束，不能越过共享空间、槽位或身份参考依赖。
- 并发等待采用 `allSettled` 语义：每个分支自行保存成功或失败状态。
- 独立空间可并发；共享空间、共享槽位或需要继承已验收图片的 job 必须写成依赖。
- 完成结果按 job 独立落盘；重启时只处理未成功 job。
- 后续视角的请求可以延迟绑定，但只有其依赖全部成功后才能绑定。
- 不要求用户确认可逆的运行恢复、同输入重试或失败项续跑。
- 本 Skill 的五路额度只用于远端 ImageGen job。Chrome、Blender、CAD 等本机截图由 `interior-camera-capture` 管理，设备级最多两个，禁止混用额度或在本 Skill 启动截图进程。

## 资料

- 输入输出合同：[data_contract.md](data_contract.md)
- 工具调用方式：[local_runtime.md](local_runtime.md)
- 脚本职责：[scripts_logic.md](scripts_logic.md)
- 环境边界：[ENVIRONMENT_CONTRACT.md](ENVIRONMENT_CONTRACT.md)
