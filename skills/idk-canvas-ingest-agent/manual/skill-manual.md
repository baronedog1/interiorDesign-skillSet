# 百恩得平台 · 素材流入与私有交付 说明书

版本：3.0.1

~~~yaml
---
name: idk-canvas-ingest-agent
description: 设计链访问百恩得资产库、绑定同一私有项目、下载选定资产并上传图片或完整 HTML 时使用；独占受管 Key、API 和真实回读，不负责生成或美学验收。
metadata: {version: "3.0.1", category: interior-design}
---
~~~

## 调用场景

### 平台操作：资产流入与交付流出分别处理

本页保留实际业务步骤；蓝色节点链接专题，回源节点明确返回位置。文件逐项列明用途。

输入：资产检索条件 / 用户授权的交付物
输出：本地下载、私有项目链接与回执

#### 平台操作：资产流入与交付流出分别处理
- a：其它 Skill 的资产/交付请求；Key 只在本平台 Skill；不放 HTML/PDF
  - scripts/run.py：平台唯一命令入口
- q：本机受管身份可访问？；profile 实测；只用真实权限与 HTTPS（详见 identity）
  - playbook.md：平台操作授权与步骤
  - local_runtime.md：本机私有 Key、HTTPS、本地网络和字段合同
- no：否：报告凭据/权限/服务故障；不输出 Key 或完整鉴权异常
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- intent：读资产还是推送成果？；当前只支持私有项目；不是社区公开发布
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- read：资产总览 → 条目 → 下载；用户选定素材，真实链接下载本机（详见 download）
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- write：唯一项目 → 上传 → 回读；按 HTML/媒体合同；没有授权仅 dry-run（详见 upload）
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- a → q：访问身份
- q → no：否
- q → intent：是
- intent → write：上传
- intent → read：查询/下载

## 完整文件地图
- .gitignore：配方、资源与实现说明：.gitignore
- MANIFEST.json：发布版本与完整文件清单
- SKILL.md：调用范围、输入输出与关键规则
- SKILL_MANUAL.pdf：面向人的算法说明书
- local_runtime.md：本机私有 Key、HTTPS、本地网络和字段合同
- manual/skill-flowchart.svg：同源说明书内容与图形
- manual/skill-manual.json：同源说明书内容与图形
- manual/skill-manual.md：同源说明书内容与图形
- playbook.md：平台操作授权与步骤
- scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- scripts/run.py：平台唯一命令入口

## 具体逻辑解释

### 身份、网络与授权

按实际输入、计算、分支和文件消费者展开。

#### 身份与访问：只读和写操作的边界不同
- a：加载本机平台 env；IDK_API_KEY/IDK_API_BASE_URL/IDK_TOOL_NAME；只记录位置，秘密内容不进入报告或图
  - scripts/run.py：平台唯一命令入口
  - playbook.md：平台操作授权与步骤
  - local_runtime.md：本机私有 Key、HTTPS、本地网络和字段合同
- q：地址与操作在实际允许范围？；HTTPS /api/v1；拒绝鉴权重定向；只用 profile/projects/library/私有资产路由
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- bad：否：准确报告不支持/权限失败；不发明端点；不静默匿名上传；不输出完整服务器响应或签名链接
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- ok：是：GET 可读；POST 需任务授权；publish 不加 --apply 只 dry-run；写请求固定幂等键；429/502/503/504 有界重试；不公开、不付费生成、不删除
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- out：后续只在当前账号可见范围内找项目/资产；common 只处理数据保存，绝不承担鉴权
  - ../interior-html-modeling/scripts/engine/python/common.py：JSON 与回执原子写入
- a → q：受管配置
- q → bad：否
- q → ok：是
- ok → out：明确权限

### 真实资产下载

按实际输入、计算、分支和文件消费者展开。

#### 素材流入：从可见条目到本机文件
- a：真实 library summary / items；平台资产条目不等于全部都是 3D 模型；选定 libraryId 与 itemId；不猜 URL
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- b：选中条目实际返回的 source URL；同源才携 Key；外部 HTTPS 不携 Key；拒绝认证重定向，下载预算 64MiB
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- q：文件与可得摘要相符？；有远端 SHA 则核对；无 SHA 只记本地摘要
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- bad：否：报告缺失/网络/摘要问题；不称下载成功，不用其它素材偷偷替换
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- out：是：文件＋下载回执；交回建模/原生绘图 Skill 使用
  - ../interior-html-modeling/scripts/engine/python/common.py：文件原子写入与 SHA
- a → b：真实条目
- b → q：字节
- q → bad：否
- q → out：是

### HTML/媒体分流与回读

按实际输入、计算、分支和文件消费者展开。

#### 交付流出：HTML 与媒体 payload 不混用
- bind：精确绑定唯一可见项目；GET projects 按 UUID/唯一名称；不猜同名项目；创建需本次授权；已有绑定不得静默切项目
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- q：文件是完整 HTML 还是媒体？；文件非对应格式如实报告；ZIP/PDF不是项目媒体
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- html：HTML → preview3d；name/title/folderId/html/externalTool/externalRunId；完整内嵌依赖，不带 file: 或本机路径；不混入媒体字段，不传 body.operationKey
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- media：图片/视频 → assets；materials[]: name/mimeType/base64/folderId；顶层与条目保留来源和 assetKind；不是平台生成接口
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
- out：固定幂等键 → 返回资产 ID → GET assets 回读；同名同SHA复用，文件改变需新版本名；有远端摘要才声称内容一致；回执只含项目/资产身份、本地摘要和状态，不含 Key
  - scripts/platform_bridge.py：实际白名单 API、下载、绑定和回读
  - ../interior-html-modeling/scripts/engine/python/common.py：绑定与回执 JSON 保存
- bind → q：项目与文件
- q → media：媒体
- q → html：HTML
- html → out：POST
- media → out：POST
