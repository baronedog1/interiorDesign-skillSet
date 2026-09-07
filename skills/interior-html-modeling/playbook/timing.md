# 逐步骤时间，不事后补写

六项设计 Skill 的正式命令自动向输出目录 `timing.jsonl` 追加开始与完成事件。设置 `INTERIOR_TIMING_LOG` 可汇总到同一项目日志，不能指向 Skill 安装目录。每次尝试独立 spanId，含 step、kind、startedAt、finishedAt、elapsedMs、status；嵌套步骤含 parentSpanId。时间用 UTC ISO，展示可换北京时间；代码耗时用单调时钟，跨进程时间注明 wall-clock。

代码阶段包括规划交接、模型编译、机位求解、逐图截图、请求准备、结果登记、平台命令、PDF 构建与两种输出。截图的每张完成时间另在 renders.json；PDF 两种输出在 manifest.json。父子步骤、并行绘图的耗时不可直接相加。中断只有 start 没 finish 就标中断/未知，不把缺项当 0。

读图/人工布局判断、选型、逐图识图、原生调用等待和渠道交付不是代码内部可以自动看见的操作。Agent 在动作前后使用引擎 `python/timing.py start|finish --record <新文件>`：start 指定 `--step` 与 `--kind agent|native-generation|delivery`，finish 指定实际 `--status`。不要把文件 mtime 或 job 准备时间冒充开始时间。

原生绘图用渲染 Skill 的 native-start → 实际工具调用 → native-complete → 逐图识图 → native-result。调用返回立即 complete，再做复核；其中 elapsedMs 是宿主调用到回收登记的跨度，不是供应商纯计算时间。真实完整 prompt 与全部附图来自 job，不在调用时偷偷增加未记录的提示词。

正常确定性建模/机位应以秒至分钟为优化目标，不是无条件服务承诺。异常变慢时看具体 span、场景规模、浏览器加载、网格量和网络等待；不要靠缩短超时或删除质量说明伪造速度。交付报告列代码净耗时、宿主绘图等待、Agent复核及总跨度，未知明确写未知。
