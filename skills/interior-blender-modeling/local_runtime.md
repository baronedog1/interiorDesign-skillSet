# 本地运行

```bash
/home/agentops/agent-runtime/bin/blender --version
/home/agentops/agent-runtime/bin/blender --background --factory-startup --python-exit-code 1 --python scripts/build_floorplan_scene.py -- --help
/home/agentops/agent-runtime/bin/blender-mcp-server-0.1.3/bin/python scripts/test_mcp_connection.py --help
python3 scripts/apply_circulation_adjustment.py --plan circulation-adjustment-plan.json --existing native-layout-overrides.json --out native-layout-overrides.next.json
```

正式构建使用 Blender 后台 Python；有 override 时向 `build_floorplan_scene.py` 传
`--layout-overrides native-layout-overrides.json`。MCP 只做连接、reopen、场景检查和有界编辑。
