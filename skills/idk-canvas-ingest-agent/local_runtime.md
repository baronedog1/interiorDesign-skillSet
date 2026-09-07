# 内部凭据与平台执行

Python 标准库执行 scripts/platform_bridge.py，入口 scripts/run.py；JSON 原子写工具复用 HTML Skill 的 scripts/engine/python/common.py。

内部安装位置 `.runtime/baiende-platform.env`，只在来酷保留；或显式 IDK_ENV_FILE。实际键名 IDK_API_KEY、IDK_API_BASE_URL、IDK_TOOL_NAME、IDK_REQUEST_TIMEOUT_MS。管理员按用户授权从 Ubuntu 的受管凭据文件安全复制，不能在终端输出内容。Git、PDF、ZIP 分发排除 .runtime；内部部署同步凭据，不表示把密钥嵌入公开包。

生产 HTTPS https://www.baiende.com/api/v1；国内平台走来酷本地网络。外部下载不携平台 Key。连接错误只报告状态/错误类型，不输出请求头、完整异常或带签名链接。

验收区分 profile、实际库读取、下载、私有上传回读；静态代码及 mock 不算生产联调。只有用户授权上传的文件才 --apply，本轮安装不自动公开社区内容。

2026-09-07 生产字段差异：preview3d 使用 name/title/folderId/html/externalTool/externalRunId；不能混入媒体的 assetKind/origin/sourceType，也不能把 operationKey 放入请求体。幂等操作键通过 Idempotency-Key 请求头传递。媒体上传仍使用独立 materials[] 合同，不能把两类 payload 合并。
