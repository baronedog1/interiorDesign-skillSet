# 灯光、摄像头与同源二维机位

## 职责边界

- `scene-rig.json` 保存用户在 HTML 内编辑的灯光和场景摄像头。
- `camera-plan.json` 由 `interior-camera-capture` 维护正式 shot、构图和逐机位灯光。
- 本 Skill 是 HTML、Three.js、二维机位显示和实时预览的唯一实现者；机位 Skill 只调用公开 API，不保存模板或另画机位图。

## 摄像头编辑

摄像头位置与目标都使用 Three.js `Y-up` 米制坐标。场景页支持三轴拖拽、滑杆/数字输入、16/24/35/50mm 焦距、FOV 双向换算、墙面吸附、固定视角微调和 `distortion=0`。

用户选择“在平面中编辑机位”时：

1. 主画布切到正俯视；
2. 同一 `scene-rig` 摄像头显示为平面圆环、目标点与水平视锥；
3. 相机位置、目标或灯光变化时，左上角由主 renderer 的独立 320×180 render target 绘制实时机位画面，再读入唯一预览 canvas；右下角手柄只缩放 16:9 显示框，不重建 WebGL 资源；
4. 主画布和实时预览不复制结构、相机或组件状态；切换平面、三维和页签时预览保持开启。

相机和光源在平面或自由三维中均可单击选中、双击进入位置编辑并直接拖动；方向光的高空位置使用可见辅助标记但保留真实坐标。固定相机视角只由检查器的显式命令或已保存 shot 触发，不能复用双击动作。空白点击取消选择后，方向键只平移主画布焦点。

正式第三象限使用：

```javascript
window.__INTERIOR_MODEL_EDITOR__.captureCameraPlanEvidenceDataUrl(shotId)
```

返回同一画布 PNG 与 `interior.camera-plan-evidence.v2`。JSON 包含 native model hash、`modelBackend=html-threejs`、position、target、fov、focalLengthMm、平面方向、水平视锥和显示策略；不得由下游脚本重新推算或绘制。

正式批量截图必须由 `interior-camera-capture/scripts/capture_model_views.py` 完成结构、机位、模型范围和设备压力验证，并在取得全设备截图槽位后调用 `capture_html_views.mjs`。适配器在页面任何业务脚本执行前注入并冻结外部 accepted `camera-plan.v8`。页面内嵌计划只服务 standalone 交互预览；其赋值会被正式截图运行时丢弃。每帧必须验证 `runtimeCameraPlanSource=external-formal-camera-plan-v8`，并由截图器直接把 `modelBackend`、`sourceModelSha256`、坐标系、`visibility` 和 `mustShowElements` 写进第三象限 JSON。运行时来源缺失、模型哈希不一致或页面仍采用内嵌历史机位时立即失败，不允许项目目录直接启动 Chrome，也不允许维护升级证据的临时脚本。

## 局部遮挡唯一规则

所有正式 shot 固定：

```json
{
  "mode": "all-spaces",
  "contextPolicy": "preserve-visible-adjacent-spaces",
  "hiddenElementIds": [],
  "preserveElementIds": []
}
```

HTML 只执行 `hiddenElementIds`，并先排除 `preserveElementIds`。它可以公开相机射线候选供 Agent 审阅，但不能自动扩大隐藏清单。不存在 `focus-room`、`isolateOtherSpaces`、`hideFocusOccluders` 或“失败后多隐藏一些”的兼容逻辑。关闭、切换机位或截图结束后完整恢复 `visible` 状态，任何对象都不被删除。

## 两种同机位证据状态

右上角“白模/水泥”是结构外观开关，不是渲染模式选择器：

- `slot-guided` 槽位引导：活动家具和柜体隐藏，placement slot 保留，结构强制 `concrete-shell`；
- `furnished-qa` 家具核对：显示已经从资产库物化的组件，结构继续强制 `concrete-shell`；只供人工核对，禁止提交给绘图模型。

水泥皮肤由确定性 CanvasTexture、粗糙度和同一场景光生成，不下载纹理，不改变几何、ID、相机、开口或空间坐标。`interior-space-rendering` 的生成输入固定为 `slot-guided`。

## 确定性截图

`?capture=1&shot=<shotId>&presentation=<mode>` 与右栏预览读取同一 shot，应用相同位置、目标、焦距、FOV、局部隐藏清单、灯光和曝光。截图隐藏编辑 UI、轴和网格，并输出帧可读性证据；槽位生成证据与家具核对证据必须具有相同像素尺寸、相机矩阵和模型版本。
