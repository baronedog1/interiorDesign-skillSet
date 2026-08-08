# Environment Contract

## 必需运行时

- Python 3.10+，模块：Pillow、NumPy、OpenCV、jsonschema。
- Node.js 20+。
- `CHROME_BIN`：固定、非 Snap Chrome/Chromium，必须支持 WebGL2；Three.js 运行文件随 Skill 包提供。

## 目录与权限

- 源图证据、carving state、投影报告、standalone HTML、browser QA 与组件包写当前项目目录。
- 浏览器 profile/cache/runtime 使用实际执行账号可写目录；Skill 与共享 runtime 不接收任务中间文件。
- Python/Node/browser 依赖由管理员安装；业务任务不得联网安装。

## Preflight

```bash
python3 -c 'import PIL, numpy, cv2, jsonschema; print("FURNITURE_IMPORTS_OK")'
node --version
"$CHROME_BIN" --version
python3 tests/test_visual_hull_pipeline.py
```

正式 `ready` 需要最小多视图 fixture 完成 carving、逐视图零异或投影、standalone HTML、桌面/390×844 截图、WebGL2/console/非空 canvas 和 package hash。OpenCV 或浏览器缺失时为 `blocked`；输入视图不完整且允许推断时最多为 `provisional`。

## 安全与外部能力

- 不需要 API Key、网络上传或付费服务。
- 不把源图或产品包写入公共组件库；公开/平台发布交给 `idk-canvas-ingest-agent` 并另行确认。
