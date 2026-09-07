---
name: interior-circulation-planning
description: 当户型初稿或用户回传的可编辑 HTML 需要检查空间可达、门口堵塞、通道压窄和家具关系时使用。只生成去重后的自然语言提示，不修改用户布局、不阻断机位和后续交付。
metadata: {"category":"interior-design","skill_type":"business","source_authority":"gcp-manager-shared-baseline","default_for_all_agents":false,"scene_schema":"interior.circulation-scene.v3","result_schema":"interior.circulation-result.v3","version":"6.0.0"}
---

# Interior Circulation Planning

## 产品原则

动线检查是“提醒用户看看这里”，不是审批用户方案。

- AI 初稿和用户修改都按当前事实检查；
- 用户已经移动、删除或新增的对象保持原样；
- 原户型固有狭窄、堵门、通道压窄、关系不理想和空间疑似不通都只提示；
- 结果无论有没有风险，`cameraWorkflowAllowed` 都为 `true`；
- 发现问题不自动搬家具、不回滚 HTML、不要求用户重复确认。

## 输入

优先读取用户回传 HTML 经 `interior-html-modeling/import_returned_html.py` 提取的唯一 `current-model.json`。首次建模也可读取同结构的 `coauthoring-model.json`。

生产不再要求 accepted handoff、native manifest 和当前 HTML 的多重摘要先全部通过才开始检查。文件无法解析时如实报告“没有可读模型”，但不能把内容风险包装成硬门禁。

## 输出

唯一输出为 `interior.circulation-result.v3`，至少包括：

- 空间连接图和从入户出发的可达结果；
- 门、移门、开放通道附近的疑似堵塞；
- 过窄通道和家具关系提示；
- 每条提示的位置、相关对象和大白话说明；
- `policy.blocking=false`、`policy.userLayoutPreserved=true`；
- `verdict.accepted=true`、`cameraWorkflowAllowed=true`。

## 唯一生产算法

1. 用门、移门和开放通道建立房间图；窗、固定玻璃和栏杆不算入口。
2. 用家具真实 footprint 与门洞中心做距离和净宽近似，找出疑似堵点。
3. 相同物理位置只报一次，不把一处堵点拆成多条路线错误。
4. 用 `audit_user_returned_html.py` 直接生成提示；脚本发现 0 条或多条风险都以退出码 0 完成。
5. 结果立即交给用户并继续机位。若用户随后再改 HTML，覆盖当前版后重新运行一次即可。

## 验证边界

Skill 发版回归可以用旧审计器、复杂网格或负向案例衡量算法质量，但这些结果不进入客户任务的阻断逻辑。验证发现误报、漏报或无法理解的位置时，修改本 Skill 算法并重新发版，不让生产任务停在 `blocked-input-integrity`。

## 高频入口

- [执行流程](playbook.md)
- [数据合同](data_contract.md)
- [脚本职责](scripts_logic.md)
- [本地命令](local_runtime.md)
- [环境边界](ENVIRONMENT_CONTRACT.md)
