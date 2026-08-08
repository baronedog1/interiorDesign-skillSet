# Local Runtime

## 变量

```text
CAD_BROWSER_BIN=<固定非 Snap Chrome/Chromium>
CAD_VIEWER_RUNTIME_DIR=<profile/cache/log 可写目录>
```

## 启动与验证

```bash
curl -sS -m 2 http://127.0.0.1:4178/__cad/server
npm --prefix scripts/viewer run serve -- --host 127.0.0.1 --dir <absolute-model-root> --shutdown-after 12h --json
```

复用前必须比较 `viewerVersion` 与 `scripts/viewer/package.json`。浏览器验收至少打开一个 STEP/GLB，保存桌面截图、console 结果和源文件 SHA-256。启动失败时保留日志并标记 `blocked`；不临时安装依赖，不把监听地址改成 `0.0.0.0`。
