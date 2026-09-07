# 唯一执行入口

`python scripts/run.py brief.json --out <新输出目录>`。

run.py：解析资料、保持比例／RGB 图片内嵌、用 assets/magazine.css 排版、调用 Chrome、长文续页、两份 PDF 导出、独立重开和全部页预览、生成摘要。不会执行 JSON 中的代码、联网取图、调用绘图工具或读取凭据。

先由 Agent 完成每页编排和图像选择；缺实际图、非法路径／字段、解码失败返回具体错误。溢出／字体／低分辨率等观察写入 manifest，Agent 查看并修改源；不是以静态检查替代审美判断。
