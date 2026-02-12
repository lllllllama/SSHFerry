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
- ⚡ 针对大文件的高吞吐并行分块传输

## 📌 当前范围

- 运行环境：Python `3.11+`
- GUI：`PySide6`
- 协议：`Paramiko`（SSH/SFTP）
- 引擎：
  - `sftp`（默认）
  - `parallel`（大文件原生并行分块传输）
- 任务状态：
  - `pending`、`running`、`paused`、`done`、`failed`、`canceled`、`skipped`

## 🧭 快速上手

1. 添加站点（表单填写或粘贴 SSH 命令）。
2. 建议将 `remote_root` 设置为独立项目目录（推荐）。留空时默认 `/`（全盘范围）。
3. 执行连接自检。
4. 连接后浏览远程目录树。
5. 上传/下载文件或文件夹。
6. 在任务中心监控并控制任务。

### 首次启动说明

- SSHFerry 启动后不再自动创建演示/测试站点。
- 如果站点列表为空，请点击 `Add Site` 创建首个连接。

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

## ⚡ 大文件传输性能

### 当前策略

- 对大文件，SSHFerry 会优先走加速传输路径。
- 大文件会自动切换到优化后的并行 SFTP 分块传输。
- 并行传输支持吞吐预设（`low` / `medium` / `high`）。
- 默认策略按方向区分：上传使用 `medium`，下载使用 `high`。

### 为什么现在回退更快

- 每个 worker 复用本地/远端文件句柄，减少按分片反复打开关闭的开销。
- 多连接并发分片传输。
- 进度回调做了批量上报，降低回调锁竞争开销。

### 最快传输优化建议

1. 先使用默认方向策略（`upload=medium`、`download=high`）作为基线。
2. 尽量使用稳定有线网络。
3. 优先密钥认证，并减少代理跳转层数。
4. 传输中断后优先续传，不要从零重传。
5. 保证两端磁盘 I/O 有余量，并行分块传输对存储瓶颈更敏感。

### 针对你的服务器做基准测试

```bash
python tools/benchmark_transfer.py --site "<站点名称>" --size-mb 512 --iterations 2
```

- 可通过 `--modes` 自定义模式，例如：`sftp,parallel:high,parallel:medium`。
- 最终调优请以基准结果为准，真实速度主要受服务器限流与 RTT 影响。

### 观测效果（倍数表达）

- 在真实远程链路测试中，大文件场景下 `parallel` 相比普通 `sftp` 的吞吐约为 **10x ~ 16x**。
- 在同一测试模式下：
  - 下载方向更偏向 `parallel:high`。
  - 上传方向更偏向 `parallel:medium`。
- 以上为**相对倍数**，不是固定速度值。实际结果会随带宽、RTT、服务器限流和磁盘 I/O 条件变化。

### 并行调优环境变量

- `SSHFERRY_PARALLEL_WORKERS`：覆盖并行 worker 数。
- `SSHFERRY_PARALLEL_CHUNK_BYTES`：覆盖分块大小（字节）。
- `SSHFERRY_PARALLEL_WARMUP_BATCH`：每批预热启动的 worker 数。
- `SSHFERRY_PARALLEL_WARMUP_DELAY`：预热批次间隔（秒）。
- `SSHFERRY_PARALLEL_MAX_CHUNK_RETRIES`：单分块最大重试次数。

## 🗂️ 项目结构

```text
src/
  app/        # 入口
  core/       # 调度器与任务逻辑
  engines/    # SFTP / 并行 SFTP
  services/   # 站点存储、连接检查、指标统计
  shared/     # 模型、错误、路径沙箱、日志
  ui/         # 主窗口与各面板

tests/        # Pytest 测试集
```

## 📝 说明

- 密码为运行时信息，不会通过 `SiteStore` 持久化。
- 当前项目定位为个人与学习用途。
- 为了更安全，建议使用最小权限账号，并尽量避免将 `remote_root` 设为根目录。
