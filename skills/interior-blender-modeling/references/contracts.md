# 交接合同

## HTML → Blender

- 只传结构、房间和家具 transform；
- 不传 HTML GLB、资产锁或代理几何；
- `floorplanId` 必须一致。

## Blender 原生资产

- 每个功能类至少精确匹配一个登记资产；同类多款按房间风格标签和适用范围确定性选择；
- 文件 SHA-256、许可、选型状态、来源轴、预旋转、前向轴、朝向模式和精确尺寸策略固定；
- 缺资产即修 catalog，不生成方盒或跨类替代。

## Blender 建筑材料

- 墙、天花、干区地板和湿区地板分别绑定一个登记 PBR 模板；
- 每套模板必须有 Diffuse、Roughness、Normal、CC0 来源页面、物理尺度和 SHA-256；
- 无 UV 程序结构使用三轴 Box 投影；风格只调整混色、粗糙度倍率和微凹凸，禁止缺图后回退 Noise/Brick。

## Blender → Camera

- `.blend` 和场景审计包绑定摘要；
- Camera v3 plan 只在当前 HTML 求解一次；
- Blender 批处理逐图隔离执行相同 plan；非目标房间家具在 Eevee 分配纹理前删除，PNG 与 JSON 绑定同一模型、计划和剪枝回执。

## 交付

交付自包含 `.blend`、派生 GLB、各空间 Eevee 截图与 JSON、Eevee 总览联系表、构建/验证/批处理回执和许可可追溯的 Skill 包。
