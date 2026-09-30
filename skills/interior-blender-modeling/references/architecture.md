# 架构

```text
current-model.json + structure-data.json
  ├─ 结构与家具 transform
  ├─ Blender 原生 catalog（同类多款、许可、来源轴、前向轴、朝向）
  ├─ Blender 材料 catalog（CC0 PBR 三图、物理尺度、许可和摘要）
  └─ Blender 风格预设（房间选型、材料引用、混色、微凹凸、Eevee 与贴图预算）
          ↓ 唯一编译器
current.blend + current.glb + build-report.v5
          ↓ Camera 已冻结的同一 plan
单图隔离并剪枝 → Eevee 材质渲染 + 同名 JSON
```

HTML 是布局事实源，不是 Blender 几何源。Blender catalog 是原生精细资产的唯一来源。Camera 只维护一套求解方法，Blender 只执行冻结结果。设备资源由渲染盒和逐图进程隔离共同约束。
