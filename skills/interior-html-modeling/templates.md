# Templates And Assets

## 唯一模板

```text
assets/
├── interior-coauthoring-template/
│   ├── index.html
│   ├── coauthoring-model.json
│   ├── coauthoring-model.js
│   └── vendor/
│       ├── three.module.js
│       ├── loaders/GLTFLoader.js
│       └── utils/BufferGeometryUtils.js
└── component-library/
    ├── catalog/
    ├── movable-green/catalog.js
    ├── fixed-purple/catalog.js
    ├── component-library.js
    ├── index.js
    ├── shared/
    └── gallery/
```

模板的产品名和交付文件名统一为：`室内户型人机共创模板`。

`index.html` 是唯一交互代码；墙、门窗、房间、家具、摄像机和灯光只来自 `coauthoring-model`。项目创建后可以替换模型数据，禁止复制或改名 `index.html` 形成第二套模板。

模板固定包含：

- 外部专家编辑器的墙体、门窗、二维/三维、场景、撤销重做和导入导出能力；
- 受管组件库的精细家具渲染；所有对象都必须加载真实资产，不存在来源轮廓色块；
- 顶栏家具显隐和空间标志显隐；
- 结构页一行六个 SVG-only 扁平快捷按钮，组件页顶部选择/新增/显隐/删除按钮，以及悬停与键盘提示；
- 双击组件后的中心移动点和四角等比例缩放点；双击墙后的顶部墙厚输入；
- 默认隐藏但可独立显示的天花板与吊灯层；
- 图层、截图、本地恢复和结构/组件/场景域隔离；
- 单一碰撞内核：家具、固定构件、墙、门窗的鼠标拖动、四角缩放、键盘和数字输入共享同一套几何规则，非法候选停在上一合法状态；
- 稳定公共 API：`window.__INTERIOR_COAUTHORING_EDITOR__`；
- 稳定启动状态：`window.__INTERIOR_COAUTHORING_BOOT__`。

发版诊断 API 固定为 `window.__INTERIOR_COLLISION_DIAGNOSTICS__`，用于浏览器回归重算家具、洞口和墙体候选。它只暴露确定性几何诊断，不建立第二份模型状态，也不进入客户生产步骤。

## 唯一组件库

`assets/component-library/catalog/public-assets.json` 是唯一 canonical catalog。绿色和紫色目录只表达放置语义，不拥有第二套来源事实。

项目匹配完成后，`materialize_component_assets.mjs` 只把实际使用资产物化到：

```text
<project>/component-library/models/<provider>/<component-id>.glb
```

并生成 `component-assets.lock.json`。standalone 构建器只内联该集合；同一资产重复使用只计一次预算。

## 禁止项

活动 Skill 内不得出现：

- 第二个 HTML 编辑器入口；
- 按版本号命名的模板目录或模板文件；
- `old/`、`backup/`、`archive/`、兼容模板或旧公共 API；
- 项目私有模板副本；
- 跨类别方盒替代正式家具；
- 未使用 GLB 被整体塞入最终 HTML；
- 平台凭据、任务附件或客户项目数据。

历史研究目录可以保留报告、截图和验收 JSON；可执行的旧 HTML 和完整旧模板代码必须从活动发现范围清除。
