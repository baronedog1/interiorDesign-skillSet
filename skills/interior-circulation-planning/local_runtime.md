# 本地运行

无固定设备路径；使用当前 runtime inventory 中的 Python 3.11+ 和当前任务可写目录，不需要也不得临时安装包。

## 要求

- Python 3.11 或更高版本
- 不需要 pip 包、网络服务或 API Key
- UTF-8 文件系统

## 语法检查

```bash
python3 -m py_compile scripts/*.py
```

## 顺序

```text
build_circulation_scene.py
  -> audit_circulation.py
  -> [plan_layout_adjustments.py -> 后端自动应用唯一操作 -> 导出新 revision -> 从头重跑]
  -> finalize_circulation_delivery.py
```

所有路径建议使用绝对路径。脚本会读取真实文件并核对 SHA-256，因此移动或重写证据后必须重新生成上游合同。
