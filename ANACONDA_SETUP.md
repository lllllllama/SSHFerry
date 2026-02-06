# Anaconda 环境配置说明

## 好消息！

您的 Anaconda 环境已经包含所需的依赖：
- ✅ PySide6 6.6.1 (已安装)
- ✅ Python 3.12.7

## 快速开始

### 方法一：使用 run.bat（推荐）
```bash
.\run.bat
```

### 方法二：直接运行
```bash
python -m src.app.main
```

## 安装其他依赖（如果需要）

```bash
# 安装 paramiko（SSH 库）
pip install paramiko

# 安装测试工具
pip install pytest

# 或者一次性安装所有依赖
pip install paramiko pytest ruff
```

## 注意事项

- **不需要**创建虚拟环境（.venv）
- 直接使用 Anaconda 的 base 环境即可
- 如果遇到问题，确保在 Anaconda Prompt 中运行

## 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 快速验证
python -c "from src.ui.main_window import MainWindow; print('✅ 所有模块加载成功')"
```

## 环境信息

```bash
# 查看当前环境
conda info

# 查看已安装的包
conda list | grep -i pyside
pip list | grep -i pyside
```
