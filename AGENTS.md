# Interior Design Skill Set 维护规范

## 定位

本仓库是室内设计与 CAD Skill 的版本化备份和跨设备分发源。每个正式 Skill 的唯一安装单元是 `skills/<skill-id>/`。

## 强制规则

- 不得提交 `.env`、Codex auth、API key、Cookie、SSH key、会话、history、任务、日志、客户附件、客户作品或设备运行数据。
- 不得提交 `node_modules`、Python cache、测试缓存或临时渲染产物。
- 保留第三方 Skill 自带的 LICENSE、来源和署名；不得用仓库级说明覆盖原许可证。
- Skill 内容变更必须遵循其 `SKILL.md` 和 GCP Manager 的 Skill 治理规范；安装副本不得反向覆盖权威源。
- 新增、删除或修改 Skill 后，运行 `node scripts/build-manifest.mjs --snapshot <ISO-8601>`，再执行 frontmatter、secret、符号链接和脚本语法检查。
- 每个 Skill 的 `SKILL.md` 前部必须有 `## 使用前准备`，并同时提供 `ENVIRONMENT_CONTRACT.md` 与 `local_runtime.md`；设备依赖只由管理员预装，业务任务不得临时下载。安装后运行 `scripts/audit-runtime-prerequisites.mjs`，把 `installed` 与 `ready/degraded/blocked/conditional` 分开登记。
- 向设备安装必须显式指定目标 `$CODEX_HOME/skills`，不得碰触其它 Agent、OpenSlaw Agent Space 或设备级登录态。

## 验收

1. 每个一级目录都存在 `SKILL.md` 和 `name` frontmatter。
2. `manifest.json`、`FILES.sha256` 与实际文件一致。
3. 没有逃逸仓库的符号链接、secret-like 文件或高风险密钥字面量。
4. 目标设备安装后逐文件哈希一致，并在新 Codex 会话中完成 Skill 发现验收。
5. 目标执行账号运行 runtime audit；依赖外部授权的能力只登记存在性和状态，不读取或复制 secret 值。
