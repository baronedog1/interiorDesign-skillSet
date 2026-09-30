# 三项建模 Skill · 当前代理执行

发行：`modeling-current-agent-2026.10.01.1`。本轮只更新及安装下面三项，默认由当前代理完成建模。各包的入口、数据、脚本和同源 PDF 完整保留，强制或建议委派与专用交接文件退出发行包。

| Skill | 版本 | 入口 |
| --- | --- | --- |
| HTML户型 | 5.0.2 | [interior-html-modeling](skills/interior-html-modeling/SKILL.md) |
| 精细Blender整屋 | 5.1.1 | [interior-blender-modeling](skills/interior-blender-modeling/SKILL.md) |
| 单品照片建模 | 3.1.1 | [product-modeling](skills/product-modeling/SKILL.md) |

整改方法与任务核查见 [发行说明](RELEASE.md)。同源说明书在每项根目录的 SKILL_MANUAL.pdf，AI说明书及可交互总图在 manual/。建模代码、模板、资产和设计方法与整改前保持一致；旧版独立标签与主分支保留。

共享源由 GCP Manager 管理，四设备按本次授权定向安装三项。设备的私有.runtime、认证、素材、工作区、客户模型和Bridge分别保留。其它五项设计目录继承自父发行，不属于本次更新，也不据本标签自动覆盖到设备；当前设计主链仍按各设备现役登记执行。

安装层逐文件摘要通过不等于本地软件、资产或后端已运行就绪。Lecoo独立Blender能力保持原状，新增同源Blender目录仅登记installed/runtime-unverified。旧TUI需显式读取当前Skill，新会话加载原生配置。

manifest.json与FILES.sha256提供整个分支的文件追溯；source.currentDesignRelease.skillIds只列本次三项更新范围。同步脚本不复制凭据或私有运行态，不把维护验证加入客户任务前置流程。
