# 本地运行时

## 变量

```text
CAD_PYTHON_BIN=<固定 CAD Python>
CAD_RUNTIME_ROOT=<版本化 CAD runtime 根目录>
CAD_BROWSER_BIN=<固定非 Snap Chrome/Chromium>
```

## 常用入口

```bash
"$CAD_PYTHON_BIN" scripts/step --help
"$CAD_PYTHON_BIN" scripts/inspect --help
"$CAD_PYTHON_BIN" scripts/snapshot --help
```

新设备先运行最小生成器，确认 STEP、原生 GLB、facts、measurements 与快照都来自同一模型哈希。找不到唯一受管解释器或浏览器时直接标记 `blocked`；不要自动使用系统 Python、Snap browser 或任务内下载的 runtime。
