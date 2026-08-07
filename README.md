# Interior Design Skill Set

室内设计与 CAD Codex Skills 的版本化备份和跨设备分发仓库。

本仓库当前快照来自 GCP Manager 受管设备 `ubuntu-01-codex` 的实际安装目录，包含 16 个设计相关 Skill。它不包含 Codex 登录态、会话、任务、日志、客户文件、平台密钥、`.env`、`node_modules` 或设备运行缓存。

## Skill 清单

室内设计主链：

- `interior-floorplan-planning`
- `interior-html-modeling`
- `interior-blender-modeling`
- `interior-cad-modeling`
- `interior-circulation-planning`
- `interior-camera-capture`
- `interior-space-rendering`
- `imagegen-batch-orchestrator`

设计交付扩展：

- `movable-furniture-modeling`
- `booklet-production`
- `interior-design-video-production`
- `idk-canvas-ingest-agent`

CAD 辅助能力：

- `cad`
- `cad-zh`
- `cad-object-modeling`
- `cad-viewer`

## 安装

每个 Skill 都位于 `skills/<skill-id>/`，可使用 Codex 的 `skill-installer` 按 GitHub 路径安装。例如：

```bash
python3 /path/to/skill-installer/scripts/install-skill-from-github.py \
  --repo baronedog1/interior-design-skill-set \
  --path skills/interior-floorplan-planning \
  --dest "$CODEX_HOME/skills"
```

批量安装时，对每个 `skills/<skill-id>` 逐项执行安装并在新开的 Codex 会话中验收。Codex TUI 在启动时加载 Skill 上下文；已经打开的旧会话不会自动获得后来安装的 Skill。

## 运行边界

- 本仓库保存 Skill 本体，不打包设备登录态、客户数据或受管 secret。
- ImageGen、Seedance、百恩得平台、Blender、CAD Viewer 和部分数据库查询仍需要目标设备具备对应 runtime、网络或获批凭据；缺失时必须明确报错，不得伪造成功。
- 设备安装副本必须独立管理 `$CODEX_HOME`、sessions、history、工作区和运行态。
- GitHub 是版本化分发与备份源，不自动覆盖任何生产设备；升级必须由 GCP Manager 显式同步并验收。

## 完整性

- `manifest.json`：Skill 级文件数、字节数和聚合 SHA-256。
- `FILES.sha256`：`skills/` 下每个文件的 SHA-256。
- `node scripts/build-manifest.mjs --snapshot <ISO-8601>`：重新生成上述清单。

第三方 Skill 的许可证和来源说明保留在各自目录中；本仓库不会覆盖各 Skill 原有许可证。
