---
name: interior-html-modeling
description: 将布局 JSON 编译为可离线编辑的完整 Three.js HTML；支持墙门窗、家具库替换、CMF 风格、量尺面积、灯光相机和完整保存往返。
metadata: {version: "3.2.0", category: interior-design}
---
# HTML 室内共建

消费当前 `layout.json`，交付 `model.html`、`scene.json`。用户编辑后以最新完整 HTML 为准；导出布局重新编译，不能用旧模型覆盖用户修改。

先读取同名 `layout.requirements.json` 或规划明确交接的需求文件，访谈规则归[平面布局Skill](../interior-floorplan-planning/playbook/requirements-interview.md)。依用户已确认的功能、习惯、优先级、保留家具与风格实施建模，不从空白图猜偏好；未知与授权自由发挥分开。仅缺颜色不阻止基础结构建模；影响用途/容量的实质缺口回规划访谈，不重复询问已有答案。每次向机位、渲染、方案册交接同时说明这份需求及当前revision。

正式入口 `python scripts/run.py build layout.json --out DIR`。按需 `import-html FILE --out layout.json`、`asset-bundle library.json --out assets.json`、`style-resolve 风格名称`、`style-evidence recipe.json`、`style-add recipe.json`。

读 [方法与编辑功能](playbook.md)、[数据合同](data_contract.md)、[运行说明](local_runtime.md)。本 Skill 持有五项共用的确定性编译/截图引擎 `scripts/engine`，不是第六项 Skill；平台代码与密钥只属于平台 Skill。

切换风格只改 CMF，保留家具形体、位置、灯光、机位、撤销历史。换家具是另一个明确动作。不要删除床靠墙、正面朝向、门窗真实宿主与动线等设计知识；也不要加审美分数门禁。

实际截图交给 `interior-camera-capture`；效果图交给 `interior-space-rendering`；查询资产、上传 HTML/图片调用 `idk-canvas-ingest-agent`。

效果图链将HTML称为粗模：提供准确结构、布局、机位与约略家具尺度，不作为精细款式或照明参考。渲染按绑定的家具图片/精细定样锁款并重建光影，不锁粗模造型；这不改变HTML内CMF按钮的既有行为，也不表示二维家具图已转成3D资产。规则详见[渲染方法](../interior-space-rendering/playbook.md)。

人读 [PDF](SKILL_MANUAL.pdf)。

每一步必须记录开始、完成、耗时及状态，遵循[统一时间合同](playbook/timing.md)；正式命令自动记录，读图、识图、原生调用与交付等待随执行登记，不事后补时间。

门窗按源事实统一编译；空间两端、门型、开合、填充与外部目标随截图交接。读 [空间连接合同](playbook/space-connections.md)。不再写死半扇玻璃或截图时统一开门。
