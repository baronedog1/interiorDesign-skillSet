# Templates

- [assets/source-evidence.example.json](assets/source-evidence.example.json)：墙面双线与开口线段的源证据格式。
- [assets/semantic-decisions.example.json](assets/semantic-decisions.example.json)：墙和开口各自唯一分类的格式。
- [assets/trace-spec.example.json](assets/trace-spec.example.json)：不含结构坐标副本的最小 authored spec，包含客厅、卧室、阳台的空间类型、种子、开口绑定和开放功能分界。
- [assets/wall-geometry.example.json](assets/wall-geometry.example.json)：与上述 spec 成对使用的唯一墙几何；真实项目必须由 `build_wall_geometry.py` 生成，不能照抄示例坐标。
- 四象限视觉职责见 [references/quadrant-contract.md](references/quadrant-contract.md)，不维护第二份模板正文。
