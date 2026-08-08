# Local Runtime

## 变量

```text
CAD_PYTHON_BIN=<固定 CAD Python>
CAD_RUNTIME_ROOT=<版本化 CAD runtime 根目录>
CAD_BROWSER_BIN=<固定非 Snap Chrome/Chromium>
```

如果未显式注入变量，先读取设备 runtime inventory；找不到唯一、已验收入口时停止，不能扫描并猜一个 Python。

## 最小检查

```bash
"$CAD_PYTHON_BIN" -c 'import build123d, OCP, cadpy, PIL'
"$CAD_PYTHON_BIN" scripts/step --help
"$CAD_PYTHON_BIN" scripts/inspect --help
"$CAD_PYTHON_BIN" scripts/snapshot --help
```

正式 smoke 使用本轮工作目录中的最小生成器，依次产出 STEP、原生 GLB、facts/measurements 和快照；所有文件登记 SHA-256。失败时保留 stderr 与中间产物，状态写 `blocked`，不在任务中安装依赖或改用系统 Python。
