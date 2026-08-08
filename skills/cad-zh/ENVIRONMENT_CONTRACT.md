# Environment Contract

## 必需运行时

- `CAD_PYTHON_BIN`：固定 Python 3.11/3.12 CAD 解释器，能导入 build123d 0.11.x、OCP、cadpy 与 Pillow。
- `CAD_BROWSER_BIN`：CAD 快照使用的非 Snap Chrome/Chromium；Playwright browser cache 由管理员预装。
- `CAD_RUNTIME_ROOT`：版本化 runtime 根目录。

本文件与 `cad` 使用同一运行时事实，中文文档不形成第二套 CAD 解释器。Ubuntu 路径只可作为示例，其它设备读取环境变量和 runtime manifest。

## 目录、权限与 Preflight

- 生成器与产物写当前项目；runtime、浏览器和依赖由管理员维护。
- 浏览器 profile/cache/runtime 必须对实际执行账号可写。
- 任务不得执行 `pip install`、浏览器下载或修改共享 runtime。

```bash
"$CAD_PYTHON_BIN" -c 'import build123d, OCP, cadpy, PIL; print("CAD_IMPORTS_OK")'
"$CAD_PYTHON_BIN" scripts/step --help
"$CAD_PYTHON_BIN" scripts/inspect --help
"${CAD_BROWSER_BIN:-google-chrome-stable}" --version
```

正式 `ready` 要求中文指令生成最小零件，并通过 STEP、选择器、尺寸、GLB 和快照回归。失败时标记 `blocked`，不得跳过任一门禁。

## 安全

- 无 API Key 或外部服务依赖。
- 不输出未经证明的制造、公差、材料或认证结论。
