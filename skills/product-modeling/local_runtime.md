# 运行与维护

在用户指定设备的任务目录复制本包到 product-modeling/，将 scripts/package.json 复制为任务根 package.json 后执行 npm install。生成器与 Skill 共享任务根 node_modules；不向设备级 Skill 安装库，不把 node_modules、密钥或历史成果打进 Skill。

依赖版本由 scripts/package.json 唯一维护，任务安装产生 package-lock.json 并随可复现源码保留。Three 只内联一套，许可证与工作台一起保留。Node 路径、Chrome 路径、资源包装沿设备现有运行说明；Windows 用本机盘符和实际 Node，不把Linux绝对路径写入产品。

```sh
node product-modeling/scripts/build-workbench.mjs product.config.mjs model.html
node product-modeling/scripts/build-workbench.mjs --empty workbench.html
```

普通建模读取方法并构建；维护代码时才跑 `node --test product-modeling/scripts/test-product.mjs`，浏览器用最终 file:// HTML 验证，运行证据在任务目录。说明书改版使用 Skill Product Manager 的 build_skill_manual.mjs 与 validate_skill_manual.mjs，之后更新 MANIFEST 摘要；不是建模任务的前置审批。

同步只替换授权设备的 product-modeling 活跃目录；先保存旧目录到发现路径以外，再校验全目录摘要。源与安装版同一版本。旧会话若缓存了 Skill，显式读新版绝对路径；新会话由设备根自动发现，不声称旧会话已经热加载。
