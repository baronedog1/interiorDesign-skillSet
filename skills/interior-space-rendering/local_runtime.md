# 原生工具接入

Python 仅准备与登记，依赖同安装根 HTML Skill 的 scripts/engine。真实图像由当前宿主原生绘图工具执行；有工具才在 capabilities.nativeImage 写 available=true 与实际 toolName，否则写 false 并说明。

实际调用记录字段 source=host-native-tool、toolName、status=succeeded、jobDigest、outputSha256；providerRequestId 仅使用服务实际值。它不是可伪造为“调用成功”的测试夹具。结果文件由原生工具返回后校验可读性并识图；目录全部在来酷。

平台 Key 不在本 Skill。平台查询、下载、私有上传调用 idk-canvas-ingest-agent。原生工具缺失时不能静默改走付费 API。
