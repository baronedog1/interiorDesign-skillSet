# Environment Contract

## 必需运行时

- Node.js 20+ 与 `scripts/viewer/package-lock.json` 对应的已安装依赖。
- `CAD_BROWSER_BIN`：固定、非 Snap Chrome/Chromium；需要自动截图时同时准备浏览器驱动或 Playwright browser。
- 本地环回网络与一个可用端口，默认从 `4178` 开始扫描。

## 目录与权限

- Viewer 仅绑定 `127.0.0.1`，不得监听公网或 Tailnet 全接口。
- `--dir` 必须是授权的只读模型根目录；cache、profile、日志与截图写实际执行账号可写的 runtime 目录。
- npm 依赖由管理员在发布/安装阶段锁定；业务任务不得执行 `npm install`。

## Preflight

```bash
node --version
npm --prefix scripts/viewer test
npm --prefix scripts/viewer run serve -- --host 127.0.0.1 --dir <fixture-root> --shutdown-after 5m --json
"${CAD_BROWSER_BIN:-google-chrome-stable}" --version
```

正式 `ready` 需要载入最小 STEP 与 GLB，验证桌面截图非空、console 无错误、文件 hash 与源文件一致。端口冲突按 Viewer 自带扫描处理；浏览器或依赖缺失时标记 `blocked`，不得改为远程公开服务。

## 安全

- 不读取凭据，不上传模型，不执行模型目录中的任意脚本。
- Review URL 只面向当前本机或明确授权的隧道。
