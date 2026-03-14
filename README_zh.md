# SSHFerry

中文 | [English](README.md)

SSHFerry 是一个基于 Python + PySide6 的 SSH/SFTP/SCP 桌面图形工具。
项目当前聚焦三件事：**远程操作安全**、**传输行为实用**、**任务状态清晰可见**。

## 亮点能力

- 基于 `remote_root` 的远程沙箱保护
- 支持文件与文件夹上传/下载，支持递归
- 支持续传与跳过策略
- 内置连接检查：TCP / SSH / SFTP / 读写
- 任务中心支持暂停 / 恢复 / 取消 / 重试
- 大文件支持高吞吐并行分块传输
- 单窗口支持多个远端会话
- 支持在两个远端面板之间拖拽，创建远端到远端传输任务

## 当前范围

- 运行环境：Python `3.11+`
- GUI：`PySide6`
- 协议 / 依赖库：`Paramiko`（SSH/SFTP）+ `scp`
- 传输引擎：
  - `sftp`（默认）
  - `parallel`（大文件并行分块传输）
  - `scp`（手动选择的传输模式，默认覆盖）
- 任务状态：
  - `pending`、`running`、`paused`、`done`、`failed`、`canceled`、`skipped`

## 快速开始

1. 添加站点，可以手动填写表单，也可以直接粘贴 SSH 命令。
2. 尽量把 `remote_root` 设置为独立项目目录。若留空，默认是 `/`。
3. 执行连接检查。
4. 打开一个或多个远端会话并连接。
5. 上传或下载文件 / 文件夹。
   - 站点级默认传输协议可设置为 `sftp` 或 `scp`
   - 主窗口可按任务覆盖协议：`Auto / SFTP / SCP`
6. 可直接在两个远端面板之间拖拽，创建远端到远端传输任务。
   - 文件任务会直接入队
   - 文件夹任务会先扫描，以便统计总文件数和总字节数
7. 在任务中心查看和控制任务。

### 首次启动说明

- SSHFerry 启动后不再自动创建演示站点
- 如果站点列表为空，点击 `Add Site` 创建第一个连接

## 安装

```bash
pip install -r requirements.txt
```

## 启动

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

## Windows 打包发布

使用 PyInstaller 生成可分发 GUI 应用：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -VenvPath .venv_compat
```

推荐的验证流程：

```powershell
# 1) 先构建带控制台的调试包
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -Debug -VenvPath .venv_compat

# 2) 启动与连接检查正常后，再构建 GUI 正式包
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -VenvPath .venv_compat
```

也可以使用包装脚本：

```bat
tools\build_windows.bat
```

输出目录：

```text
release/SSHFerry-<version>-windows/
```

调试包目录：

```text
release/SSHFerryDebug-<version>-windows-debug/
```

脚本还会生成：

```text
release/SSHFerry-<version>-windows.zip
release/SSHFerry-<version>-windows.sha256
```

打包注意事项：

- 发布时请保留整个目录，或直接发布 `.zip`，不要只单独分发 `.exe`
- Windows 构建采用 `onedir` 布局，以提高 PySide6 运行稳定性
- 默认禁用 UPX，减少 Qt 运行问题和杀毒软件误报

推荐发布流程：

1. 上传 `.zip`
2. 同时上传 `.sha256` 校验文件

### GitHub Release 检查清单

发布前建议确认：

1. `pytest -q` 本地通过
2. `release/SSHFerryDebug-<version>-windows-debug/SSHFerryDebug.exe` 能正常启动
3. `release/SSHFerry-<version>-windows/SSHFerry.exe` 能正常启动
4. Windows 下本地文件面板图标显示正常
5. 需要时会在 `%USERPROFILE%\AppData\Local\SSHFerry\` 下生成 `startup.log`

推荐上传的 Release 附件：

- `SSHFerry-<version>-windows.zip`
- `SSHFerry-<version>-windows.sha256`
- 可选：`SSHFerryDebug-<version>-windows-debug.zip`

## 功能验证

### 自动化检查

```bash
pytest -q
```

```bash
python -c "from src.shared.errors import ErrorCode; from src.shared.models import SiteConfig, Task; from src.shared.paths import normalize_remote_path, ensure_in_sandbox; from src.engines.sftp_engine import SftpEngine; from src.core.scheduler import TaskScheduler; from src.services.connection_checker import ConnectionChecker; print('imports_ok')"
```

### 建议手工验证

1. 使用独立沙箱目录连接测试主机
2. 同一文件上传两次，确认第二次状态为 `skipped`
3. 中断大文件传输后重试，确认续传生效
4. 将远端文件拖到本地面板，确认会创建下载任务
5. 打开两个远端会话，在它们之间拖拽文件或文件夹，确认会创建远端到远端任务
6. 尝试操作沙箱外路径，确认被拦截

## 大文件性能

### 当前策略

- 大文件优先走加速传输路径
- 当文件达到阈值后，会自动切换到并行 SFTP 分块传输
- 并行传输支持吞吐预设：`low` / `medium` / `high`
- 默认按方向区分：
  - 上传使用 `medium`
  - 下载使用 `high`
- 调度器默认按协议限制并发：
  - `max_workers_total=3`
  - `max_workers_sftp=3`
  - `max_workers_scp=2`
  - `max_workers_parallel=1`

### SCP 行为说明

- 文件上传 / 下载任务支持 SCP
- SCP 默认是覆盖语义，不支持原生续传
- 如果 SCP 失败，调度器会自动回退一次到 SFTP
- 回退后仍可继续使用 SFTP 已有的续传 / 跳过逻辑

### 远端到远端传输说明

- 远端到远端任务通过两个远端面板之间拖拽创建
- 对较小文件，程序会优先尝试在源服务器上直接执行 `scp` 复制到目标服务器
- 直连复制当前要求目标站点使用密钥认证，并提供 `key_path`
- 如果直连失败，程序会回退到桥接模式，由 SSHFerry 同时连接两端做中继传输
- 大文件默认跳过直连，直接走并行桥接
- 文件夹传输也是同样思路：先尝试递归 `scp`，失败后回退为中继复制

### 为什么现在回退更快

- 每个 worker 复用远端文件句柄，而不是每个分块重复打开关闭
- 使用多连接并发传输分块
- 进度回调做了批量化，降低回调开销

### 速度优化建议

1. 先保持默认方向策略：`upload=medium`、`download=high`
2. 尽量使用稳定的有线网络
3. 优先使用密钥认证，并尽量减少代理跳转层数
4. 传输中断后优先续传，不要从零开始
5. 保证两端磁盘 I/O 有余量，并行分块对存储瓶颈更敏感

### 针对自己服务器做基准测试

```bash
python tools/benchmark_transfer.py --site "<你的站点名>" --size-mb 512 --iterations 2
```

- 可通过 `--modes` 自定义模式，例如：`sftp,parallel:high,parallel:medium`
- 最终调优建议以基准结果为准，真实速度主要受 RTT、限流和磁盘 I/O 影响

### 观测到的相对收益

- 在真实远程链路测试中，大文件场景下 `parallel` 相比普通 `sftp` 的吞吐约为 **10x 到 16x**
- 同一测试模式下：
  - 下载更偏向 `parallel:high`
  - 上传更偏向 `parallel:medium`
- 这些是相对倍数，不是固定速度值，实际效果会随网络与服务器条件变化

### 并行调优环境变量

- `SSHFERRY_PARALLEL_WORKERS`：覆盖 worker 数
- `SSHFERRY_PARALLEL_CHUNK_BYTES`：覆盖分块大小
- `SSHFERRY_PARALLEL_WARMUP_BATCH`：每批预热启动的 worker 数
- `SSHFERRY_PARALLEL_WARMUP_DELAY`：预热批次之间的间隔秒数
- `SSHFERRY_PARALLEL_MAX_CHUNK_RETRIES`：单分块最大重试次数
- `SSHFERRY_STRICT_HOSTKEY`：设置为 `1` / `true` / `yes` / `on` 时启用严格 host key 校验

## 项目结构

```text
src/
  app/        # 入口
  core/       # 调度器与任务逻辑
  engines/    # SFTP / SCP / 并行 SFTP / 远端到远端传输
  services/   # 站点存储、连接检查、指标统计
  shared/     # 模型、错误、路径沙箱、日志
  ui/         # 主窗口与面板

tests/        # Pytest 测试
```

## 说明

- 默认不持久化保存密码。如果你在密码认证站点勾选 `Save password to sites.json`，密码会保存到本机站点配置文件
- 站点存储路径：
  - Windows：`%USERPROFILE%\AppData\Local\SSHFerry\sites.json`
  - Linux/macOS：`~/.config/sshferry/sites.json`
- 当前项目定位仍然是个人与学习用途
- 为了更安全，建议使用最小权限账号，并尽量避免把 `remote_root` 设为根目录
