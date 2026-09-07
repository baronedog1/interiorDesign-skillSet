# 风格配方与造型扩展

编辑器、结构坐标和输入事件只有一套；风格是可执行数据，不是五套项目脚本。

## 使用已有风格
从 `catalog/styles.json` 选择ID并读取对应 `styles/<id>/PLAYBOOK.md`。初次建模可传 `--style <id>` 选择初始配方；在已有HTML“风格”页应用时只更换 CMF，保留当前 forms、家具形体/位置、灯光、机位和撤销历史。要采用新风格默认光源，单独点击“灯光→风格打灯”。

已有模型做 CMF 对照方案时保留墙、开口、房间用途、家具ID/摆放/尺寸/形态与当前照明。更换布局、家具造型或灯光需要对应独立动作，不是风格按钮的隐式行为。

## 添加未收录风格
1. 先运行style-resolve；非内置风格由宿主真实检索或采用用户明确提供的配方，记录证据和设计假设，再创建新id。修改theme（面板强调色/背景）、palette、materials、materialRecipes（表面类型、粗糙度/金属度）和forms。
2. 填写playbook的intent/forms/materials/details/lighting/avoid，以及renderBrief。lighting给出初始色温、环境/太阳/曝光与设备强度。
3. forms引用当前已实现分支；schemas/style.schema.json给出完整选项。任何命名都不应在缺构造器时冒充造型已支持。
4. `python skills/interior-html-modeling/scripts/run.py style-check my-style.json`。
5. `python skills/interior-html-modeling/scripts/run.py style-add my-style.json`：注册共享目录并生成PLAYBOOK。随后可`build layout.json --style my-style --out project`。
6. 页面也可以先“载入风格JSON→应用”，用于临时试配；保存方案会携带该配方。导出layout会携带customStyle，可直接命令行重编译；跨项目复用时再选择style-add注册。

## 添加真正的新形态/组件
新形态只扩 `runtime/style-components.js` 中该类分支，同步JS/Python风格schema的枚举。复用已有几何助手、本地+Z前向，结果归一化到placement.size。不能把五套style各复制一个app.js。

新组件类别同时登记 `catalog/components.json` 与构造器，补尺寸包络、旋转/选择/灯光绑定与截图检查。静态GLB通过native-assets.js实际加载，模型目录需提供本地字节和元数据。品牌使用权由来源确认；压缩、动画及不支持的扩展先转换，不只放路径就声称可用。

## 素材来源
木纹、石纹、灰泥、织物/编织、皮革和艺术画由随包代码生成，运行无CDN；PNG在assets/textures可独立取用。纹理中性底色乘材质色，不把奶油色烘进每张贴图。表面类型与粗糙度分别控制布/石/木/金属，不统一套成软塑料。

## 灯光
lighting默认值只是方案起点，不代表照度计算。实际点光/射灯以cd记录，界面可修改色温、目标和阴影；最终亮度还受距离/曝光/材质影响。环境是本地程序化HDR，不是摄影HDRI；此WebGL模式不是V-Ray/Corona或路径追踪。所有正式图从绑定模型捕获，不额外为某风格写私有补光脚本。

## 非内置与混合风格

`style-resolve`已知名称返回配方，未知返回research-required任务。由宿主Agent真实检索，再记录 evidence.query/retrievedAt/sources[url,title,supports]；不在前端伪造网页结果。选择主次风格及比例要披露设计选择，引用真实材料和造型证据。`style-evidence`只验证记录完整性，不冒称重新抓取来源。

用户自带完整recipe可直接style-check并以customStyle随布局保存；shape分支缺失时先扩runtime/style-components.js而不是把名称换掉。原生家具由library元数据风格标签与componentBindings按产品身份选择；没有实际模型时说清参数化替代，不虚构付费/品牌资产。
