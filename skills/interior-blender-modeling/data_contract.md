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

### `floorplan-handoff.v3`

唯一结构与 placement 事实。项目必须校验 `handoffDigestSha256` 以及 `structureData`、`traceComponents`、`sourceEvidence` 的逐文件哈希。

### `blender-asset-selection.json`

Schema：`interior.blender-asset-selection.v1`。

```json
{
  "schema": "interior.blender-asset-selection.v1",
  "floorplanId": "plan-a",
  "handoffDigestSha256": "...",
  "catalogSha256": "...",
  "items": [{
    "sourceObjectCandidateId": "candidate-object-sofa",
    "traceId": "green-sofa",
    "assetId": "polyhaven-painted-wooden-sofa",
    "assetSha256": "...",
    "appearance": "white-model",
    "axisAdapter": {"up": "+Z", "front": "-Y"},
    "scaleMode": "uniform-fit"
  }]
}
```

禁止出现 `position`、`rotation`、`roomId`、`width`、`depth` 或 `height`。这些字段只能从 handoff 对应对象读取。`scaleMode=uniform-fit` 固定表示使用目标宽、深、高与导入资产真实世界包围盒的三个比值中的最小值；它不是只看平面尺寸。上游对象必须是 `quantity=1/atomicObject=true` 并携带唯一 `functionalClass`；catalog 必须预先保存人工接受的 `supportedFunctionalClasses`。验证器只接受完全相等的功能类，不再从 `categoryHint`、名称或关键词临时猜类别。资产选择文件不能自行声明或改写类别相容性。

正式目录由 `catalog-policy.json` 与 `index_blender_asset_store.py` 从 Blender 专属资产仓生成。Skill 保存目录政策、分类覆盖与加载器；大型 `.blend`/GLB 二进制只存在该后端的受管资产仓，不被 HTML 或 CAD 后端读取。

每个需要方向关系的目录项还必须保存审阅 `directionalAxes`：沙发 `back/front`、床
`headboard`、餐椅 `front`、电视柜及柜体 `front`。Blender 只把这些轴连同当前 transform
交给动线 Skill，不保存关系通过结论。

截图实体索引必须输出 `relationHints.schema=interior.layout-relation-hints.v2`。其中
`directionalAxes[]` 只含 `assetId/role/localAxis/evidence`，`facing[]` 只含
`sourceId/targetId/axisRole`，`wallAttachment[]` 只含
`sourceId/wallId/axisRole`。禁止保存距离、门限、房间归属、净空区或 `passed`。

## 项目模型

Blender 使用米制右手坐标，`+Z` 向上。生成器必须保存从 handoff 坐标到 Blender 世界坐标的显式可逆矩阵和五个往返控制点。每个对象根节点保存：

- `sourceObjectCandidateId`
- `traceId`
- `assetId`
- `floorplanId`
- `handoffDigestSha256`
- `roomId`
- `semanticType`

导入模型原点不具有事实权。构建器必须以全部可渲染 `component-part` 的旋转后世界包围盒校正根节点，使平面中心与 handoff `center` 的误差不超过 `0.002m`、最低点与 `Z=0` 的误差不超过 `0.002m`，且最高点不超过 handoff `bbox.height+0.002m`。

### 集合

固定集合为：`STRUCTURE`、`OPENINGS`、`FLOORS`、`CEILINGS`、`FURNITURE`、`LIGHTS`、`CAMERAS`、`ANNOTATIONS`。

### 天花

每个 room 对应一个 ceiling root，字段包含 `roomId`、`heightMeters`、`stylePreset`、`inspectionHidden`。`inspectionHidden` 只改变显示，不删除 ceiling root。

### 窗和阳台

- `windowStyle`：`frameless-glass|casement|sliding|fixed-pane`
- `enclosureMode`：`open-railing|closed-glazing`

样式可替换框架和材质，不得改 handoff 洞口边界。开放阳台必须有独立栏杆对象和安全高度，不能生成封闭墙。

## 编辑

`interior.structure-edit-patch.v1` 记录 `entityId`、`operation=extend-collinear-endpoints`、`source.start/end`、`current.start/end`、`extensionMeters.start/end`、来源 trace 和宿主开口保护。Blender 只负责原生交互和候选导出；平面 Skill 统一验证后重新编译拓扑与 handoff。旧 handoff 保持不可变。

组件和灯具编辑写入项目 revision。`interior.native-component-motion.v1` 输入当前原生模型哈希、组件 world bounds、请求位移和 native obstacles；结果返回首次接触比例、碰撞对象 ID 和最终合法位移。

## 输出

`interior.native-layout-overrides.v1` 只保存经 `adjustment-plan.v2` 摘要验证的当前实体
中心、朝向和审计证据。它不能改变尺寸、房间、资产或来源 ID；每轮只追加一个操作并重建
完整 `.blend`。用户显式 transform 不得被算法 override 覆盖。

原生截图同时输出颜色图、32-bit 深度 EXR 和 32-bit `IndexOB` EXR。相同 `interiorEntityId` 的所有可渲染子物体共享同一 `pass_index`，映射与世界包围盒写入 `entity-index.json`。`scene-semantic-frame.v4` 只能由同一白模帧的 `IndexOB + Depth + 冻结空间多边形` 编译；RGB 语义遮罩只是这组原生数值的可视化，不得从截图识别、重画或修补。门窗洞口四角必须全部位于相机前方并输出正向深度证据；跨越相机近裁面或位于相机后方的连接不得写入当前帧。

Blender 唯一投影协议为 `blender-native-object-index-depth-room-v1`，`projectionEvidence.method` 固定为 `blender-native-object-index-plus-depth-to-room-polygon`。旧 Workbench 对象色协议不再接受。

`interior.native-model-manifest.v1` 至少包含：

- `modelBackend=blender`
- `nativeModelPath`、SHA-256、Blender 版本
- handoff ID/digest、结构 revision
- 坐标合同与可逆变换
- collections 与 entity index
- room、wall、opening、component、ceiling、light 数量
- `capabilities`: raycast、depth、entityId、visibilityStates、nativeCameraRender
- `captureAdapter`: Skill 内脚本、runtime、参数合同
- 资产目录和项目选择哈希
- validation 状态

`.blend` 是 Blender 后端唯一场景事实；GLB、PNG 和 semantic frame 都是从该哈希派生。
