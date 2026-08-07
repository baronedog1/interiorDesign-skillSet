# 数据合同

## 推荐目录与语义发现

任务产物建议按阶段放置，便于人和 Agent 浏览，但目录与文件名只是**推荐位置**，绝不是有效性门禁：

| 目录 | 建议内容 |
|---|---|
| `source/` | 用户原图、附件和原始需求 |
| `planning/` | 平面 handoff、结构、描线和证据 |
| `model/<backend>/` | HTML、Blender 或 CAD 原生模型、布局及 manifest |
| `circulation/` | 动线 scene、audit、调整建议和 accepted result |
| `camera/` | camera plan、Q1/Q2/Q3、语义帧和 scene map |
| `rendering/` | render plan、请求、回执、终审和 Q4 |
| `delivery/` | 只放最终交付和验收摘要 |

读取上游产物必须遵循 `semantic-content-first-v1`：

1. 先用用户或 Bridge 明确提供的路径，再用上游 manifest 登记的相对路径。
2. 推荐路径不可用时，在当前任务工作区做有界搜索，按 schema、角色、`floorplanId`、模型 revision、内容哈希和 handoff digest 识别，而不是按文件名猜测。
3. 字段名或文件名缺少、增加或写错一个字符时，仅在内容结构有效且候选唯一时内存归一化；保留原文件并在 receipt 记录警告。
4. 多个候选内容哈希相同视为等价副本，优先推荐目录并记录其它路径；内容冲突时必须询问用户选择，不能自行挑路径。
5. 完全找不到时，先询问用户“是否已有该文件，请上传或提供路径”；用户确认没有后才能报告缺失。
6. 路径、目录名、文件名和 producer 的 patch 版本不能单独构成拒绝理由。Schema、身份哈希、空间/模型绑定、许可和内容冲突仍是硬门禁，不能因兼容发现而放宽。
7. 每次发现都输出 `artifactDiscovery`：推荐路径、实际路径、语义角色、内容哈希、归一化字段、等价副本和冲突状态。



## 输入

### `interior.floorplan-handoff.v3`

唯一结构与 placement 事实。必须校验 handoff digest、producer 为 schema 兼容的 `interior-floorplan-planning 6.x`，以及 `structureData`、`traceComponents` 和源证据逐文件哈希；patch 版本号不作为兼容性门禁。

### `interior.cad-asset-selection.v1`

```json
{
  "schema": "interior.cad-asset-selection.v1",
  "floorplanId": "plan-a",
  "handoffDigestSha256": "...",
  "catalogSha256": "...",
  "usageContext": "research-only",
  "items": [{
    "sourceObjectCandidateId": "candidate-sofa",
    "traceId": "green-sofa",
    "assetId": "freecad-sofa-armchair",
    "format": "step",
    "assetSha256": "...",
    "axisAdapter": {"up": "+Z", "front": "+X"},
    "scaleMode": "uniform-fit",
    "licenseDecision": "research-only"
  }]
}
```

禁止 `position`、`rotation`、`roomId`、`center`、`bbox`、`width`、`depth` 和 `height`。这些只能从 handoff 对象读取。验证器必须直接对比上游原子对象的 `functionalClass` 与目录 `supportedFunctionalClasses`；名称、`categoryHint`、关键词、尺寸相似或风格不得用来推断或改写功能类别。每个源对象必须 `atomicObject=true` 且 `quantity=1`，selection 不能自行声明“语义相容”。

`axisAdapter.up` 固定为 `+Z`，`front` 必须是经过原生预览确认的 `-Y|+Y|-X|+X`。它只把资产本地正面旋到统一正面；对象最终朝向仍完全读取 handoff 的 `rotationY`。

资产目录 `residential-catalog-v3.json` 对每个 accepted 资产唯一维护 `supportedFunctionalClasses`、`directionalAxes`、原文件哈希、许可和编辑格式。当前项目不得生成临时标签。

CAD entity index 必须输出 `relationHints.schema=interior.layout-relation-hints.v2`。
`directionalAxes[]` 只含 `assetId/role/localAxis/evidence`，`facing[]` 只含
`sourceId/targetId/axisRole`，`wallAttachment[]` 只含
`sourceId/wallId/axisRole`。这些是资产与引用事实，不是计算结果；距离、门限、房间归属、
净空区和 `passed` 一律禁止。

## CAD 坐标

- 单位：毫米；
- 右手坐标，`+Z` 向上；
- handoff 北西原点转换为 CAD 户型中心原点：`X=(sourceX-width/2)*1000`，`Y=(depth/2-sourceY)*1000`，`Z=sourceZ*1000`；
- 输出矩阵、逆矩阵和四角加中心五个往返控制点。

## STEP assembly

固定逻辑组：`STRUCTURE`、`OPENINGS`、`FLOORS`、`CEILINGS`、`FURNITURE`、`LIGHTS`、`CAMERAS`、`ANNOTATIONS`。逻辑组只保存在 sidecar；每个可渲染实体必须是 STEP 根装配下的独立顶层 occurrence，禁止再包一层组装配，否则 CAD Viewer 对一个家具的显隐可能错误作用到整组或整场景。每个实体标签和 sidecar entity index 保存：

- `interiorEntityId`
- `interiorEntityType`
- `sourceObjectCandidateId` / `traceId` / `assetId`
- `roomId`
- `handoffDigestSha256`
- CAD selector 与 B-rep bounding box

截图只允许对顶层 occurrence 使用 `selection.hide`：槽位引导隐藏有证据的局部遮挡物及活动家具/柜体，带家具核对图只隐藏机位计划中有原生射线证据的局部遮挡物。任何嵌套 selector 都必须在截图前拒绝。

两种状态必须复用同一 STEP、相机、分辨率和水泥结构外观。槽位引导图 `slot-guided` 隐藏活动家具与柜体，是唯一可提交绘图模型的 Q1；带家具图 `furnished-qa` 保留组件，只供人工核对一一对应的位置、尺寸和朝向，禁止提交绘图模型。两者的 `display.mode` 均固定为 `rendered`，不得用其它后端截图替代。

### 建筑选项

- 天花：每空间一个可显隐 ceiling 实体；
- 窗：`frameless-glass|fixed-pane|casement|sliding`；
- 阳台：`source|open-railing|closed-glazing`；
- 墙端点：仅 `extend-collinear-endpoints`，形成 `interior.structure-edit-patch.v1` 候选并回平面 Skill 生成新 revision；
- 碰撞：连续扫掠，返回首次接触参数和最终合法 transform。

## 许可

目录中仓库 blanket 许可与嵌入 `All rights reserved` 冲突时：

- 本地非分发研究可用 `usageContext=research-only`；
- `redistributionAllowed=false`；
- 不把受限资产打入飞书交付包、平台项目或社区；
- 商业/公开用途在人工确认前停止。

## 输出

`interior.native-model-manifest.v1` 至少包含：

- `modelBackend=cad-step`
- STEP 路径、SHA-256、build123d/OpenCascade 版本
- handoff digest 与结构 revision
- 坐标矩阵、assembly groups、entity index 和计数
- `semanticTopology`: 同次 STEP 导出自动派生的 occurrence 拓扑 GLB 路径、SHA-256 和 `format=step-derived-occurrence-glb`
- `capabilities`: `visibilityStates=true`、`nativeCameraRender=true`、`semanticProjection=true`、`projectionProfile=cad-same-brep-topology-zbuffer-v1`；当前 Snapshot 未输出的 `depth/entityId` 必须如实为 `false`
- `captureAdapter`: `capture_cad_views.py` 与 snapshot job 合同
- 双状态证据合同：`slot-guided=rendered`、`furnished-qa=rendered`，两者绑定同一 STEP、相机和水泥结构外观；只有前者具有生成权限
- 资产目录、选择、许可和构建报告哈希
- accepted validation

清单 accepted 后必须由 `interior-circulation-planning` 消费同一 handoff 与同一清单哈希，唯一计算通路和布局关系。CAD 清单不保存这些派生结论。

`interior.native-layout-overrides.v1` 只保存经 `adjustment-plan.v2` 摘要验证的当前实体中心、
朝向和证据；不能改变尺寸、房间、资产或来源 ID。构建器从同一 B-rep 资产重新放置并导出
新 STEP，而不是修改旧截图或维护第二套结构。

STEP 是 CAD 后端唯一场景事实；GLB 由同一 B-rep 通过 `build123d.export_gltf(binary=True)` 自动派生，可选 3MF/STL 由 `Mesher` 派生。原生彩色 PNG、occurrence 拓扑 Z-buffer 和 scene map 必须继续绑定 STEP 哈希；派生 GLB 只承担可验证的逐三角形求交，不得成为可编辑几何或第二份场景事实，也不得声称 CAD Snapshot 已生成它没有的深度/Entity-ID 通道。

`scene-semantic-frame.v4` 必须由 `cad_semantic_projection.py` 生成。组件槽位与房间可见区域都来自带 occurrence ID 的 STEP 派生拓扑，在与 `furnished-qa` 核对图相同的 camera plan、分辨率和显隐基线下做最近三角形 Z-buffer；不得读取彩色 PNG 判断对象或边界。输出方法名固定为 `cad-same-brep-topology-zbuffer-to-room-polygon`，房间 region 来源固定为 `same-step-topology-visible-surface-membership`。门窗洞口四角必须全部位于相机前方并输出正向深度证据；跨越相机近裁面或位于相机后方的连接不得写入当前帧。
