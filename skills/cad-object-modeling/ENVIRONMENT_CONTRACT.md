# Environment Contract

## 必需运行时

- `CAD_PYTHON_BIN`：能导入 build123d 0.11.x、OCP、cadpy 与 Pillow 的固定解释器。
- 系统 Python 3.10+：能导入 Pillow、NumPy 与 jsonschema，运行证据、计划和打包脚本。
- 已安装且版本明确的 `cad` 或 `cad-zh`，以及 `cad-viewer`。
- `CAD_BROWSER_BIN`：Viewer/快照使用的非 Snap Chrome/Chromium。

Ubuntu 的 `/home/agentops/...` 仅是设备示例；多设备运行必须由环境变量和 runtime manifest 指向本机路径。

## 目录与权限

- 源图、冻结证据、生成器、STEP、派生 GLB、投影和快照写入同一项目版本目录。
- CAD runtime、Viewer 依赖和浏览器由管理员维护；任务不得联网安装。
- 只执行本轮生成或明确授权、已审计的生成器。

## Preflight 与终态

```bash
"$CAD_PYTHON_BIN" -c 'import build123d, OCP, cadpy, PIL'
python3 -c 'import PIL, numpy, jsonschema'
"${CAD_BROWSER_BIN:-google-chrome-stable}" --version
```

`ready` 需要一个最小单对象完成 generator → STEP → GLB → 三向投影 → Viewer 快照 → hash 回执。依赖缺失为 `blocked`；证据不足但可声明推断范围时只能为 `provisional`。

## 安全

- 不读取 API Key、Codex auth 或其它设备的会话。
- 不把参考图的未知尺寸伪装为工程尺寸，不输出制造认证结论。
