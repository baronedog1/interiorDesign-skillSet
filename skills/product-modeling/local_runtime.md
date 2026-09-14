# 运行与依赖

## 免安装查看

一个支持WebGL2的桌面浏览器；所有JS内联在Product_Workbench.html，纹理来自所选GLB，没有CDN。打开空白工作台后手选产品文件。可以使用目录选择（浏览器支持时），或一次选择多个JSON及其GLB。

本轮实际浏览器验收用Linux Chromium + Playwright +软件WebGL，在Xvfb环境运行；读取交付HTML字节再set_content。未将Windows双击或file://导航计为已实测，不修改浏览器管理策略。

自动加载相邻资源使用 `python scripts/serve.py`。默认只监听127.0.0.1:8765。地址 `Product_Workbench.html?product=expected_outcome/cabinet/cabinet.product.json` 会自动载入。停止服务按Ctrl+C。不要直接扩大监听到公网。

## 构建单件产品与说明书

Python3.10+、Node18+；Python依赖见 `scripts/requirements.txt`。安装依赖会访问软件源，运行查看器无需安装。NumPy读曲面源；trimesh生成/重读模型；ReportLab生成PDF；Pillow处理图像。本轮实际环境为Python3.11、Node22、NumPy、trimesh、ReportLab可用。

```bash
python -m pip install -r scripts/requirements.txt
python scripts/build_workbench.py
python scripts/build_product.py expected_outcome/cabinet/cabinet.product.json --out work/cabinet
node scripts/build_skill_manual.mjs
node tests/kernel.test.cjs
```

说明书PDF使用标准中文CID字体，不捆绑字体文件。流程SVG的系统字体显示随设备变化；PDF是正式可打印产物。

## 外部软件与许可

本包的Three.js r164核心来自用户资料库既有离线模板，沿用其MIT许可，许可文本在assets/workbench/LICENSE-Three.js.txt。版本号是此包固定依赖，不宣称是当前最新。静态GLB读写为本Skill自带实现，不依赖远程loader。


Blender不是查看器/参数柜构建器的运行前置；只有要求原生工程时才使用用户已有Blender执行脚本。此环境没有Blender或bpy，因此本轮未运行Blender。无需为了查看HTML配置Blender。

## 资源范围

不需要密钥，不写用户云盘，不自动安装到平台。生成产物写入指定目录；正式ZIP输出在Skill目录外。产品JSON不能要求执行任意代码或跨目录/跨域读取资源。

## 多视图分支依赖
Python 3.10+、NumPy、Pillow、OpenCV、jsonschema；导出GLB还需trimesh，产品PDF需reportlab。仅检查当前路径所需模块，缺失时按设备授权配置安装，或交付明确的未完成步骤。浏览器使用实际可用的 Chrome/Chromium。

## 说明书制作环境
仅重新制作说明书时需要 Node、Python cairosvg 与 Ghostscript。运行 `node scripts/build_skill_manual.mjs .`，以 manual/skill-manual.json 为源；这不是业务任务的前置检查。

## 本次受管安装
本次通用测试/新增能力 Python：`/home/agentops/agent-runtime/shared/skill-media-interior-20260914/bin/python`。既有F5/Qwen模型继续使用原入口，不迁移权重或登录态。Mac 非交互Shell请加入设备 `agent-runtime/bin`、`agent-runtime/tools/media-bin`，或按具体入口配置 FFmpeg。
