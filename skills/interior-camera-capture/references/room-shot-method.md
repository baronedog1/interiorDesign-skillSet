# 空间机位执行方法

1. 读取当前后端原生模型清单和冻结结构。
2. 用房间功能选主角，不能以空墙代替缺失组件。
3. 量取三 envelope；声明 `cameraHostRoomId`，从该空间多边形与目标射线计算可退距和合法相机区域，禁止手填深度。
4. 主要空间选择真实背景墙并沿法向计算相机。
5. 生成固定排序的焦段和占比组合，只原生渲染第一张可拟合主候选；投影失败时最多再渲染下一张回退候选。
6. 几何与原生投影硬门限按固定顺序接受第一张合格候选；Agent 只核对画面语义并归因失败，不能比较后改选其它角度。
7. 主图不足以表达连接关系时补一张关系图，不扭转主图。

完整计算见 [camera-composition-method.md](camera-composition-method.md)，逐空间参数见 [room-algorithm-matrix.md](room-algorithm-matrix.md)。
