# Environment Contract

## 多设备运行规则

- 无固定设备路径或外部 secret；Python 解释器与可写输出目录以设备 runtime inventory 和当前工作区为准。
- 管理员只需保证 Python 3.11+；任务不得安装包或访问网络。
- 只有标准 fixture 与当前 handoff 的 hash/schema 检查均通过时为 `ready`；缺输入时是业务 `blocked`，不是运行时故障。

## Runtime

- Python `>=3.11`
- Standard library only
- No API key, browser session, database, paid service, or network access

## External authority

This Skill reads but does not own:

- `interior.floorplan-handoff.v3`
- source floorplan image
- `interior.floorplan-structure.v3`
- `interior.trace-components.v2`
- `interior.native-model-manifest.v1`
- current HTML, Blender, or CAD layout state
- the native model file

It owns only `interior.circulation-*` outputs.

## Write boundary

Scripts write only paths passed through `--out` or `--svg-out`. They do not edit the native model, floorplan handoff, structure, trace data, asset library, or another Skill.

## Security

- No credentials are read.
- No shell command is constructed from document values.
- All referenced evidence is hash-checked before final acceptance.
- Symbolic policy aliases and environment overrides are not supported; the checked-in policy is the sole numerical source.
