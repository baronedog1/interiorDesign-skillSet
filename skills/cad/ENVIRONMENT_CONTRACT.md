# Environment Contract

## 必需运行时

- `CAD_PYTHON_BIN`：固定 Python 3.11/3.12 CAD 解释器，必须能导入 build123d 0.11.x、OCP、cadpy 与 Pillow。
- `CAD_BROWSER_BIN`：用于快照的非 Snap Chrome/Chromium；如果快照器使用 Playwright，其 browser cache 必须由管理员预装。
- `CAD_RUNTIME_ROOT`：版本化、管理员维护的 runtime 根目录；不得位于只读 Skill 目录。
- Node.js 20+：只在 Viewer 或辅助脚本确实需要时使用。

Ubuntu 示例可使用 `/home/agentops/.local/share/codex-cad-runtime/bin/python`；其它设备必须按自己的 runtime manifest 配置，不能把示例路径当成唯一入口。

## 目录与权限

- Skill 只读或可由设备 Codex 正常定制均可；生成器、STEP、GLB、截图、cache 和临时文件只能写当前项目或显式 runtime 目录。
- 浏览器 profile 与 `XDG_RUNTIME_DIR` 必须属于实际执行账号。
- 运行时由设备管理员安装和升级；业务任务不得执行 `pip install`、`npm install` 或浏览器下载。

## Preflight

```bash
"$CAD_PYTHON_BIN" -c 'import build123d, OCP, cadpy, PIL; print("CAD_IMPORTS_OK")'
"$CAD_PYTHON_BIN" scripts/step --help
"${CAD_BROWSER_BIN:-google-chrome-stable}" --version
```

正式 `ready` 还要求生成一个最小带孔零件，导出 STEP/GLB，完成拓扑检查与非空快照。任一门禁失败时状态为 `blocked`；不得改用未登记解释器或跳过快照。

## 外部能力与安全

- 不需要 API Key、网络服务或付费接口。
- 只执行本轮生成、用户授权或已审计的 Python 生成器；STEP 导入不等于允许执行同目录任意源码。
- 本 Skill 不提供可制造性、材料强度、认证或安全结论。
