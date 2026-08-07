# Templates And Assets

## Skill 内唯一结构

```text
assets/
├── base-floorplan-template/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── structure-data.json
│   ├── component-layout.json
│   ├── scene-rig.json
│   ├── camera-plan.json
│   ├── backend-options.json
│   └── vendor/
└── component-library/
    ├── catalog/
    │   ├── public-assets.json
    │   └── platform-taxonomy.json
    ├── movable-green/catalog.js
    ├── fixed-purple/catalog.js
    ├── component-library.js
    ├── index.js
    ├── shared/
    └── gallery/
```

`public-assets.json` 是唯一人工不可直接编辑的 canonical catalog。两个运行时 `catalog.js` 都由同一 canonical JSON 确定性生成；绿色/紫色只表达 placement 语义，不拥有独立来源。

`base-floorplan-template/` 是唯一 HTML 运行模板：

- `component-layout.json` 内的 `relationHints` 只保存组件审阅方向轴、显式目标/墙体提示和展示标志，不保存距离、门限或“已通过”结论。贴墙、朝向、房间归属、对象净距和通道净空的唯一正式结果属于 `interior-circulation-planning`。
- `index.html` 只保留一个 `camera-live-preview-canvas` 和一个 resize handle。`app.js` 使用主场景 renderer 的独立 320×180 render target 填充；手柄仅缩放 16:9 CSS 显示框，平面和三维切换不重建预览，也不创建第二个 WebGL context。
- 相机、光源和目标只读写 `scene-rig.json`；单击/双击选择与直接拖动共用一套拾取，显式命令才进入固定机位。主视图居中与空白画布平移也只在该模板实现。
- 天花、窗框样式、阳台围护、墙端点补丁和连续碰撞只读写 `backend-options.json` 与当前项目 revision；不复制结构坐标。
- 客厅/阳台等开放空间的地面分界由 `relationHints.spaceDividerMarkers[]` 引用只读 `structure-data.json.semanticDividers[].id`；不改 handoff，不复制起终点，也不新增墙、门或项目私有画线数组。
- 项目可替换 JSON 和来源图，不得替换或复制 `app.js/index.html/styles.css` 形成第二套模板。

Skill 内不得出现：

- `movable-green/assets/` 或任何二进制全量模型目录；
- `asset-manifest.js`、`asset-sources.json` 或旧开放家具清单；
- 通用家具/柜体的程序化 builder；
- `old/`、`backup/`、`v1/`、`v2/` 和历史模板副本；
- 项目私有组件、平台凭据或上传脚本。

## Ubuntu 资产仓

```text
interior-component-library-v5/
├── catalog/
│   ├── public-asset-catalog.json
│   ├── asset-download-plan.json
│   └── asset-store-inventory.json
├── sources/
├── runtime/
├── previews/
├── receipts/
└── tools/
```

- `sources/` 保存可二次编辑的 glTF/GLB，或 Sweet Home 3D CC0 的 OBJ/MTL/纹理源码树，以及来源文件描述。
- `runtime/` 只保存浏览器使用的 GLB。
- `receipts/` 每项记录源码与运行模型 SHA-256、字节数、许可和完成时间。
- `previews/` 是可选展示附件，缺失不影响模型有效性。

## 项目物化

`materialize_component_assets.mjs` 读取项目 `component-layout.json`，只把实际使用的模型硬链接或复制到：

```text
<project>/component-library/models/<provider>/<component-id>.glb
```

并生成 `<project>/component-assets.lock.json`。standalone 构建器只内联该集合，未使用模型不得进入 HTML。

项目若因用户明确纠正摆位而改变来源位置或方向，只在同一 placement 增加 `reviewedAdjustment` 并更新 current transform；`source*` 保持不可变。最终 standalone 必须同时内联当前 `component-layout.json` 和该关系审计，不能回退到模板空 relation。

## 扩展规则

新增通用组件只能通过下一次正式采集审计：验证来源、许可、源码、功能类别、安装方式、尺度策略、标签、双外观和浏览器加载后，重新编译 canonical catalog。风格不能由名称、木色或材质猜测。临时产品继续使用 `movable-furniture-modeling` 的项目组件包，不直接写 catalog。
