# SSHFerry ✨

中文 | [English](README.md)

SSHFerry 是一个基于 Python + PySide6 的 SSH/SFTP 桌面图形工具。
核心目标是三点：**远程操作安全**、**传输行为实用**、**任务状态可观测**。

## 🚀 亮点能力

- 🛡️ 基于 `remote_root` 的远程沙箱保护
- 📦 文件与文件夹上传/下载（支持递归）
- ⏯️ 续传与跳过策略（断点续传、同尺寸跳过）
- 🧪 内置连接检查（TCP/SSH/SFTP/读写）
- 📊 任务中心支持暂停/恢复/取消/重试
- ⚡ 可选 `mscp` 加速（不可用时回退并行 SFTP）

## 📌 当前范围

- 运行环境：Python `3.11+`
- GUI：`PySide6`
- 协议：`Paramiko`（SSH/SFTP）
- 引擎：
  - `sftp`（默认）
  - `mscp`（可选外部二进制）
- 任务状态：
  - `pending`、`running`、`paused`、`done`、`failed`、`canceled`、`skipped`

## 🧭 快速上手

1. 添加站点（表单填写或粘贴 SSH 命令）。
2. `remote_root` 可以留空，留空时默认 `/`（全盘范围）；如需收敛权限可改为子目录。
3. 执行连接自检。
4. 连接后浏览远程目录树。
5. 上传/下载文件或文件夹。
6. 在任务中心监控并控制任务。

## 📦 安装

```bash
pip install -r requirements.txt
```

## ▶️ 启动

### Windows

```powershell
./run.bat
# 或
python -m src.app.main
```

### Linux / macOS

```bash
chmod +x run.sh
./run.sh
# 或
python3 -m src.app.main
```

## ✅ 功能验证

### 自动化验证

```bash
pytest -q
```

```bash
python -c "from src.shared.errors import ErrorCode; from src.shared.models import SiteConfig, Task; from src.shared.paths import normalize_remote_path, ensure_in_sandbox; from src.engines.sftp_engine import SftpEngine; from src.core.scheduler import TaskScheduler; from src.services.connection_checker import ConnectionChecker; print('imports_ok')"
```

### 建议手工验证

1. 使用独立沙箱目录连接测试主机。
2. 同一文件上传两次，确认第二次状态为 `skipped`。
3. 中断大文件传输后重试，确认续传生效。
4. 将远程文件拖拽到本地面板，确认创建下载任务。
5. 尝试对沙箱外路径操作，确认被拦截。

## 🗂️ 项目结构

```text
src/
  app/        # 入口
  core/       # 调度器与任务逻辑
  engines/    # SFTP / 并行 SFTP / MSCP
  services/   # 站点存储、连接检查、指标统计
  shared/     # 模型、错误、路径沙箱、日志
  ui/         # 主窗口与各面板

tests/        # Pytest 测试集
```

## 📝 说明

- `mscp` 加速依赖外部可执行文件。
- 密码为运行时信息，不会通过 `SiteStore` 持久化。
- 当前项目定位为个人与学习用途。
