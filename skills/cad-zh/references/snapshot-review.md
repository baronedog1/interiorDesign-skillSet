# 快照复核

为主 STEP/STP 选择 `scripts/snapshot` 保存输出时读取本文件。

## 强制规则

快照验证是必需步骤。每个新建或可见修改的主 STEP/STP 零件/装配体至少要生成并实际查看一张 PNG；确定性检查通过不能成为跳过理由。使用 CAD `scripts/snapshot`，不要手动打开 Viewer 或另写 Playwright：该工具更轻、更快、路径和渲染条件也更确定。静态审查用 PNG；运动/动画（包括 STEP 模块参数动画）用 GIF。

只有以下情况可跳过保存快照：

- 纯格式转换，几何没有改变
- 源码变化不影响可见几何
- 只检查或回答测量问题，没有创建/修改产物
- Python 或 STEP 生成失败，没有有效产物

跳过时报告原因和仍然执行的确定性证据。

不要对快照无限循环。只有源码修复改变了可见几何，或具体视觉疑点需要确认时才重新渲染。

## 验收包大小

简单静态零件一张 PNG 足够。出现以下情况时使用小型多视图包：

- 装配体或多个实体/零件
- 多个面或轴上的孔
- 壳体、内部空腔、孔道、开放外壳或剖切关键特征
- 加强筋、角撑、凸台、支撑柱、槽、开口、减重孔、鳍片、叶片或重复阵列
- 几何、布尔、选择器或特征失败后的源码修复
- 任务明确要求“看起来像目标对象”
- 确定性检查通过，但外形语义仍不确定

## 小型多视图包

优先使用单个 `view` JSON 作业：

```json
{
  "input": "models/part.step",
  "mode": "view",
  "outputs": [
    { "path": "/tmp/render/iso.png", "camera": "iso" },
    { "path": "/tmp/render/iso_opposite.png", "camera": { "direction": [-1, 1, -0.8] } },
    { "path": "/tmp/render/top_ortho.png", "camera": "top" },
    { "path": "/tmp/render/front_ortho.png", "camera": "front" }
  ],
  "render": { "viewLabels": true, "padding": 0.12, "sizeProfile": "diagnostic" }
}
```

相反方向的两张轴测图保证每个面至少出现一次；俯视主要检查阵列和对称，正视主要检查轮廓。

`input` 指向主 STEP/STP，可用相对或绝对路径。CLI 从输入推导内部渲染根。默认 `appearance: "workbench"`、`display.mode: "solid"`，与 CAD Viewer 一致。未给尺寸时，带标签/剖切视图默认为 1600×1200。复杂装配使用 `render.sizeProfile: "assembly"` 或 `"assembly-large"`（1800×1200 或 1920×1440）。静态 CAD 复核使用 `view` 和 `section`；需要明确线框语义时选择 `solid`、`transparent`、`hidden_edges`、`hidden_lines_removed` 或 `wireframe`。

`--focus '#o1.2' ...` 只渲染指定实例或子装配；`--hide '#o1.2' ...` 隐藏指定实例。两者不能在同一命令/作业中同时使用，也只接受 Occurrence 选择器，不接受面、边、点或 Shape 选择器。

CLI 会为验收包每个输出文件在扩展名前追加同一个 UTC 秒级时间戳，例如 `iso_solid.png` 变为 `iso_solid_20260527T163012Z.png`。

## 针对性视图

只有简报或失败模式需要时添加：

- 参考图复刻：添加与参考图相同视角，进行并排比较
- `section`：壳体、孔道、空腔、盲孔、外壳或墙/底关系
- `solid`：带清晰边线的着色 CAD 视图
- `rendered`：无边线的材质着色视图
- `transparent`：重叠、碰撞、外壳或隐藏接触；透明比全线框更清楚时使用
- `hidden_edges`：实体不透明，但显示遮挡边
- `hidden_lines_removed`：线稿复核，隐藏被遮挡边
- `wireframe`：内部干涉或装配碰撞疑点，需要完整三角线时使用
- 标签/注释：使用 CAD Viewer 支持的选择器、选中状态、截图或 GUI 链接

爆炸图和标签复核是一种意图，不是渲染模式；通过 Viewer 已支持的机制、JSON 作业设置或 GUI 链接实现。

## 诊断规则

视觉复核只用于诊断，不是最终权威。每个视觉疑点都必须转成几何检查后才能写成验证结论：

- 孔阵列看似不对称 → 测量孔中心和边距
- 盖板/子件/实例看似偏移 → 检查 frame 和 mate delta
- 角撑、凸台、柱、筋或板看似悬空 → 检查实体数、标签、连通性、接触或距离
- 空腔、孔道、盲孔看似错误 → 做剖切，再测壁厚、深度或是否通孔
- 重复阵列看似不均匀 → 测中心、角间距或实例 frame

最终报告附上生成的 PNG/GIF，或写明允许的跳过原因，并列出支撑视觉判断的确定性检查。
