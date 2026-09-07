# 平台唯一入口

生产基础地址 https://www.baiende.com/api/v1，受管 IDK_API_KEY 放入 X-IDK-API-Key，工具名用 X-IDK-Tool-Name。首次 profile 验证身份，项目通过 GET /projects 可见列表精确选择；不虚构 GET /projects/{id}。一套方案只绑定一个 project-binding.json，四个阶段复用；名字重名时请用户选 ID，创建需明确 --create 与名称。

找素材先 GET /library/summary，再 GET /library/{id}/items，按材质/风格/家具用途挑实际条目。下载使用条目提供的地址；外部 HTTPS 不携平台 Key，拒绝带认证重定向。下载内容哈希有平台提供则核对，没有则记录本地哈希不声称远端逐字一致。下载文件在来酷项目或资产目录，不落 GCP。

完整 HTML 用 POST /projects/{id}/preview3d 顶层 html；图片/视频用 POST /projects/{id}/assets。JSON/PDF/ZIP 不是媒体接口的图片，保留任务交付；HTML 不得引用 file:/本地盘或外部 runtime。生成工具、run ID、kind 与项目 ID 记录在回执，Key 不记录。

同路径同内容已有上传记录则回读复用；内容改变用明确版本化文件名，不能直接覆盖旧作品。写请求哈希生成稳定 ASCII 幂等键；429/502/503/504 最多三次，同键同请求体。API 成功后 GET assets 回读真实 ID，有远端 SHA 才做字节一致结论。生成、上传和公开是不同状态。

设计草稿可在用户授权下上传并保留问题标签；不要求 accepted 美学状态，不让平台脚本判断家具好不好。缺凭据、身份冲突、格式不受支持是具体技术/授权问题，仅暂停依赖该条件的操作。不会调用 generations、删除、社区或收费接口。
