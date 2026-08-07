# 生成器模板

`assets/cad-object-generator.py` 是可复制的 schema 驱动 build123d 骨架，不是第二套几何事实。使用方式：

1. 复制到物品版本目录并与 `cad-object-plan.json` 放在一起；
2. 所有尺寸、位置和角度从计划读取；
3. 为计划中的每个 `componentId` 生成一个带同名标签的 shape；
4. 内置原语不足时，在同一文件增加具名构造函数，并让参数继续来自计划；
5. `gen_step()` 返回 `AssemblyHelper.build()` 的带标签 Compound；
6. 通过 `$cad-zh scripts/step` 从 Python 源生成 STEP，禁止直接导出后手改。

## 内置原语

- `box`：锐边长方体；
- `rounded_box`：全边圆角长方体，圆角失败会报错而不是静默退化；
- `cylinder`：沿局部 Z 的圆柱；
- `extruded_polygon`：XY 闭合多边形沿局部 Z 拉伸。

## 复杂物品

软包、旋转体、曲面外壳或五金通常需要新增函数：

- 软垫：圆角实体、多个截面 loft，必要时以稳定曲线 sweep；
- 扶手/靠背：侧视轮廓拉伸后，用正视或俯视约束宽度；
- 管脚/框架：圆或矩形截面 sweep，并显式标注接触基准；
- 外壳：主体、抽壳、开孔、凸台、加强筋，最后圆角；
- 对称重复件：从同一参数生成多个有用途标签的实例。

不要把高密度像素边界直接逐点 loft。先拟合受约束圆弧/样条并记录最大像素残差，再由 STEP 投影门禁验证。
