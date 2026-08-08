# 本机运行时

解释器优先读取 `CAD_PYTHON_BIN`，浏览器读取 `CAD_BROWSER_BIN`；下文 `/home/agentops/...` 只作 Ubuntu 示例。找不到设备 runtime manifest 时停止，不得猜路径或任务内安装。

## 解释器与底层 Skill

合同、边界、打包和 Skill 校验脚本使用系统 Python：

```bash
/usr/bin/python3
```

STEP、build123d、OCP、cadpy 和 STEP 投影使用共享 CAD 解释器：

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python
```

底层 CAD Skill：

```text
/home/agentops/.codex/skills/cad-zh
```

CAD Viewer Skill：

```text
/home/agentops/.codex/skills/cad-viewer
```

使用当前安装路径前先确认文件存在；如果设备路径不同，按当前 `$cad-zh` 和 `$cad-viewer` 的 SKILL.md 解析，不要把路径写入产品 JSON 事实。

## 典型命令

```bash
/usr/bin/python3 <skill>/scripts/freeze_sources.py source-job.json source-inventory.json
/usr/bin/python3 <skill>/scripts/build_view_evidence.py boundary-job.json view-evidence.json
/usr/bin/python3 <skill>/scripts/finalize_cad_object_plan.py cad-object-plan.draft.json cad-object-plan.json --project-root .
/usr/bin/python3 <skill>/scripts/validate_coordinate_contract.py cad-object-plan.json coordinate-report.json
```

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python \
  /home/agentops/.codex/skills/cad-zh/scripts/step model.py --glb model.glb
```

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python \
  /home/agentops/.codex/skills/cad-zh/scripts/inspect refs model.step \
  --facts --planes --positioning
```

```bash
/home/agentops/.local/share/codex-cad-runtime/bin/python \
  <skill>/scripts/compare_step_projection.py projection-job.json projection-report.json
```

## 信任与写入边界

- `cad-zh/scripts/step` 会导入并执行生成器；只执行本轮生成、用户授权或已审计源码。
- 所有目标传明确相对路径，禁止整目录批量生成。
- STEP 与生成器同名并放同一版本目录；派生 GLB 和快照也登记哈希。
- 临时渲染放项目 `intermediate/validation/` 或系统临时目录；确定版本只登记通过门禁的包。
- 不直接修改共享 `cad-zh`、`cad-viewer` 或现有 HTML 活动家具 Skill。

## 无 GPU 环境

流程不依赖 RTX/GPU。STEP 生成、OCP 检查、正交投影和 CAD 快照可在 CPU 环境运行。复杂 loft/高密度网格应先用合理公差验证，避免把像素噪声变成超高面数几何。
