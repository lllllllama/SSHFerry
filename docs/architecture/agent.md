# agent.md — SSHFerry（Python + PySide6 + Paramiko + MSCP 外部集成）
项目名称：SSHFerry
> 目标：指导 AI 以“可控、可验证、低风险”的方式增量实现一个专注 SSH/SFTP 的 GUI 文件管理与传输工具。  
> 关键约束：**MSCP 暂不库化**；优先稳定与可维护；开发期以 AutoDL 网关 SSH 形式为主要场景；所有危险操作限制在远端测试根目录沙箱内。

---

## 0. 产品定位与范围

### 0.1 产品定位
- 专注 SSH 服务器的 **图形化文件管理与传输**（SFTP 为文件管理主协议）
- 支持文件与文件夹：上传、下载、删除、重命名、新建文件夹
- 支持任务队列、并发、失败重试、暂停/继续
- 大文件与大目录加速：通过 **mscp（外部进程）** 进行多连接并行传输
- 兼容 AutoDL 的 SSH 网关形式：`ssh -p PORT user@connect.xxx.seetacloud.com`

### 0.2 当前已知测试环境（仅用于开发，不要写死在代码,同时要求尽量安全，不要进行破坏和违规，防止封号）
- SSH 命令形式：`ssh -p <PORT> root@connect.westb.seetacloud.com`
- 远端测试根目录（沙箱）：`/root/autodl-tmp`
- 认证方式：开发期允许密码；长期建议支持密钥并优先使用密钥
- **安全要求**：任何密码/密钥不得写入仓库、不得写日志、不得硬编码。密码只从用户输入或环境变量读取。

开发服务器暂定:
ssh命令：ssh -p 16921 root@connect.westb.seetacloud.com
密码：wRogEEjPxeuA
---

## 1. 必须遵守的工程原则（AI 生成代码的边界）

### 1.1 禁止事项（必须遵守）
- ❌ 不要从 WinSCP/Cyberduck/Electerm 等项目复制大段代码进本项目（只做“对照实现/借鉴交互”）
- ❌ 不要将远端 root 路径以外的目录作为删除/覆盖目标（开发期强制沙箱）
- ❌ 不要在日志中打印密码、私钥内容、或完整认证信息
- ❌ 不要在 UI 线程执行网络 I/O（避免界面卡死）

### 1.2 必须事项
- ✅ 所有远端危险操作（rm/rmdir/rename/mkdir/upload/download）必须先做“路径沙箱检查”
- ✅ 所有传输任务必须通过统一调度器 Scheduler 执行（状态机唯一来源）
- ✅ 所有异常必须映射为 ErrorCode（不允许散落字符串错误）
- ✅ mscp 只作为外部进程调用（subprocess），不得尝试库化/绑定
- ✅ 每个可交付阶段都必须有可运行的最小 Demo 与基本回归测试

---

## 2. 借鉴来源（你可以拉取项目，对照其行为）

> 仅用于“交互与功能边界对照”，不要直接搬代码。

### 2.1 WinSCP（对照交互规范）
借鉴点：
- 双面板文件管理习惯：本地/远端并列，Enter 进入目录，Back 返回
- 右键菜单基本项：下载/上传/删除/重命名/新建文件夹
- 传输队列：后台队列、失败重试、暂停/继续、显示进度与速度
用途：
- 作为我们 UI 的“行为参照”，写成 checklist

### 2.2 Cyberduck（对照“简洁易用”的书签/站点管理）
借鉴点：
- Bookmark（站点）模型：host/port/user/key/高级项尽量隐藏
- 简洁连接状态呈现：连接中/已连接/失败
用途：
- 站点表单字段与默认值策略

### 2.3 Electerm（对照任务中心布局）
借鉴点：
- 连接列表 + 文件面板 + 任务中心/日志
用途：
- UI 布局与任务列表呈现字段

### 2.4 Ghost Downloader 3（只借鉴自适应策略思想）
借鉴点：
- 采样窗口、阈值、冷却时间（避免频繁调整）
用途：
- 实现保守的自适应并发（先会话级，后可 checkpoint 重启优化）

### 2.5 mscp（对照参数体系与 checkpoint）
必须使用的能力：
- `-n` NR_CONNECTIONS（并发连接数）
- `-a` NR_AHEAD（inflight SFTP 命令）
- `-u` MAX_STARTUPS（并发认证连接尝试，默认 8）
- `-I` INTERVAL（连接尝试间隔，避免网关/防火墙误判）
- `-s/-S` chunk size（默认可不暴露，仅高级设置）
- `-W/-R` checkpoint 保存/恢复（失败续传卖点）

---

## 3. 技术栈与目录结构（便于 AI 分模块实现）

### 3.1 技术栈（MVP）
- Python 3.11
- PySide6（GUI）
- Paramiko（SFTP 文件管理与普通传输）
- mscp（二进制外部进程）
- pytest（测试）
- ruff（格式化与静态检查）
- 可选：mypy（类型检查，后置）

### 3.2 推荐目录结构
```

ssh_transfer_gui/
pyproject.toml
README.md
agent.md
src/
app/
main.py
shared/
models.py
errors.py
paths.py
logging_.py
core/
scheduler.py
events.py
task_state.py
engines/
sftp_engine.py
mscp_engine.py
services/
site_store.py
known_hosts.py
metrics.py
ui/
main_window.py
panels/
local_panel.py
remote_panel.py
widgets/
task_center.py
log_view.py
site_editor.py
tests/
test_paths.py
test_task_state.py
test_sftp_sandbox.py
tools/
mscp/
win/
mac/
linux/

```

---

## 4. 数据模型与错误码（必须先实现，避免后期混乱）

### 4.1 SiteConfig（站点配置）
字段（必需）：
- name: str
- host: str
- port: int
- username: str
- auth_method: "password" | "key"
- password: Optional[str]  # 运行时使用，不持久化或仅系统凭据库
- key_path: Optional[str]
- key_passphrase: Optional[str]  # 运行时使用
- remote_root: str  # 沙箱根目录（开发期必须设置，如 /root/autodl-tmp）
- mscp_path: Optional[str]  # 可为空，自动探测

字段（可选高级）：
- proxy_jump: Optional[str]  # 对应 mscp -J
- ssh_config_path: Optional[str]  # 对应 mscp -F
- ssh_options: List[str]  # 对应 mscp -o

### 4.2 RemoteEntry（远端文件条目）
- name: str
- path: str
- is_dir: bool
- size: int
- mtime: datetime/float
- mode: int (可选)

### 4.3 Task（传输/文件操作任务）
- task_id: str
- kind: "upload"|"download"|"delete"|"mkdir"|"rename"
- engine: "sftp"|"mscp"
- src: str
- dst: str
- bytes_total: int
- bytes_done: int
- status: "pending"|"running"|"paused"|"done"|"failed"|"canceled"
- retries: int
- error_code: Optional[ErrorCode]
- error_message: Optional[str]
- checkpoint_path: Optional[str]  # mscp 专用

### 4.4 ErrorCode（必须枚举化）
建议最小集合：
- AUTH_FAILED
- HOSTKEY_UNKNOWN
- HOSTKEY_CHANGED
- PERMISSION_DENIED
- PATH_NOT_FOUND
- NETWORK_TIMEOUT
- REMOTE_DISCONNECT
- VALIDATION_FAILED
- MSCP_NOT_FOUND
- MSCP_EXIT_NONZERO
- UNKNOWN_ERROR

---

## 5. 路径沙箱与安全策略（必须实现）

### 5.1 远端沙箱规则
开发期：所有远端操作必须限制在 `SiteConfig.remote_root` 下。
- 任何远端 path 操作前必须执行：
  - 规范化（去掉 `..`、重复 `/`）
  - 判断 `normalized_path.startswith(remote_root + "/")` 或等于 remote_root
- 对删除（尤其递归删除）必须二次确认，并且 UI 明确提示“仅在测试目录范围内”

### 5.2 凭据策略
- 密码/私钥 passphrase 只从 UI 输入或环境变量获取
- 禁止保存到普通配置文件；如需保存，必须使用系统凭据库（后置实现）
- 日志必须脱敏：不输出 password、passphrase、私钥内容

---

## 6. 引擎设计（可插拔、可维护、AI 易写）

### 6.1 SftpEngine（Paramiko）
职责：
- 文件管理：list/stat/mkdir/rm/rmdir/rename
- 普通传输：upload/download 单文件
- 目录递归：将目录展开为任务树（建议 Scheduler 执行）

要求：
- 每个 worker 使用独立 SFTPClient 连接（避免线程共享同一 client）
- 统一异常映射为 ErrorCode

### 6.2 MscpEngine（外部进程，不库化）
职责：
- 仅处理传输（文件或目录）
- 构建命令行、启动进程、读取 stdout/stderr、退出码判断
- 失败时可写 checkpoint（`-W`），恢复时使用 `-R`

必须支持的 GUI 抽象参数（不要暴露太多）：
- acceleration_preset: "low"|"medium"|"high"（映射到 -n/-a/-I 等）
- threshold_bytes: int（大于此值自动使用 mscp）

建议 Preset 默认值（AutoDL 网关更稳）：
- low:    `-n 4  -a 32 -u 8 -I 0`
- medium: `-n 8  -a 32 -u 8 -I 0.1`
- high:   `-n 16 -a 64 -u 8 -I 0.2`

Checkpoint 策略：
- 失败自动生成 checkpoint 文件（保存在 app 专用目录）
- UI 提供“续传”按钮执行 `mscp -R checkpoint`（工作目录固定到 checkpoint 所在目录以避坑）

### 6.3 进度策略（mscp 外部进程）
- 首选：解析 `-v/-vv` 输出（若输出不稳定则不依赖）
- 兜底：下载时监控本地文件增长计算速度；上传则优先解析输出
- 无法获取 bytes_total 时，UI 允许显示“未知总量/仅速度”

---

## 7. Scheduler（队列/状态机/并发）——系统核心

### 7.1 任务状态机
唯一可信来源：Scheduler 更新任务状态，UI 只订阅事件。
状态转移：
- pending -> running -> done
- running -> failed
- running -> paused -> running
- pending/running -> canceled

### 7.2 并发策略（MVP）
- 对 SFTP：使用 ThreadPoolExecutor，默认并发 4（可调）
- 对 MSCP：同一时刻建议最多 1 个 MSCP 大任务（避免大量连接冲突）；可后置允许多任务

### 7.3 重试策略
- NETWORK_TIMEOUT / REMOTE_DISCONNECT：指数退避重试（例如 1s/2s/4s，最多 3 次）
- PERMISSION_DENIED / VALIDATION_FAILED：不重试
- MSCP_EXIT_NONZERO：允许 1 次重试（并保留 checkpoint）

---

## 8. UI 设计（简单、稳定、AI 好实现）

### 8.1 必要界面
1) 站点管理（Site Editor）
- 支持粘贴 SSH 命令导入（解析 host/port/user）
- 支持设置 remote_root（开发期默认要求填写）

2) 主窗口
- 左侧：站点列表 + 连接状态
- 中间：双面板
  - 本地面板：QFileSystemModel
  - 远端面板：自定义 TableModel（RemoteEntry 列表）
- 底部：任务中心 + 日志面板（可切换）

3) 任务中心
- 列：任务名/方向/进度/速度/状态/按钮（暂停/继续/取消/重试/续传）

### 8.2 禁止 UI 卡顿
- 所有网络/传输必须在后台线程/进程运行
- UI 更新通过 Qt Signal/Slot 或事件总线

---

## 9. 开发里程碑（按顺序交付，每一步都可运行）

### Milestone 1：连接自检 + 远端列表
交付：
- 粘贴 SSH 命令导入站点（不含密码）
- Paramiko 连接 + SFTP listdir
- 连接自检按钮（5项检查：TCP/SSH/SFTP/remote_root 可读/remote_root 可写）
- 远端面板显示 `/root/autodl-tmp` 下内容（remote_root 来自配置）

### Milestone 2：基础文件操作 + 单文件上传下载（SFTP）
交付：
- mkdir/rm/rmdir/rename（均限制在 remote_root）
- 单文件上传下载（队列化、显示进度、失败提示）
- 任务中心最小可用（pending/running/done/failed）

### Milestone 3：目录递归（SFTP 方案）
交付：
- 上传文件夹 / 下载文件夹：展开为任务树并入队
- 删除文件夹：递归删除（安全确认 + 沙箱）
- 失败汇总：部分失败可继续，其它任务不崩

### Milestone 4：MSCP 外部集成（大文件/大目录加速）
交付：
- 自动阈值切换：>= threshold 使用 MSCP
- preset（low/medium/high）
- 失败自动写 checkpoint（-W）
- 一键续传（-R）

### Milestone 5：保守自适应（不库化的现实可行版）
交付：
- 会话级自适应：根据历史统计或短探测决定 preset/连接数（仅影响新任务）
- 可选高级：checkpoint 重启优化（最多 1-2 次，避免抖动）

---

## 10. 测试与回归（AI 必须补齐的最小测试）

### 10.1 单元测试（pytest）
- test_paths.py
  - normalize_remote_path
  - sandbox_check（必须覆盖 ../、//、root 目录边界）
- test_task_state.py
  - 状态机转移合法性
- test_sftp_sandbox.py
  - 对危险操作的沙箱拦截（mock）

### 10.2 集成测试（可选，后置）
- 允许用真实 AutoDL 服务器跑“手工回归”
- 后续可增加 docker sshd，但当前不是必需

---

## 11. 日志与可观测性（调试与长期维护的生命线）

### 11.1 结构化日志字段
每条日志至少包含：
- timestamp, level
- task_id, engine, kind
- host, port, user（user 可选脱敏）
- src, dst（可选脱敏）
- bytes_done, bytes_total, speed
- error_code（如有）

### 11.2 日志导出
- UI 提供“导出日志”按钮（生成 zip 或单文件）

---

## 12. 配置与敏感信息（必须遵守）

### 12.1 配置存储
- 站点配置可存储：name/host/port/user/remote_root/key_path 等非敏感信息
- 禁止存储明文 password/passphrase
- 若需要“记住密码”：必须接系统凭据库（后置）

### 12.2 运行时注入
- 密码/口令从 UI 输入
- 或从环境变量（仅开发机）：
  - `APP_SSH_PASSWORD`
  - `APP_SSH_KEY_PASSPHRASE`
- mscp 的环境变量（如使用）：
  - `MSCP_SSH_AUTH_PASSWORD`
  - `MSCP_SSH_AUTH_PASSPHRASE`

---

## 13. AI 任务拆分模板（每次只做一小块，避免大改崩盘）

当你分配给 AI 时，使用以下格式：
1) 目标文件（最多 1-3 个）
2) 输入/输出（函数签名、事件、错误码）
3) 约束（不得改动其它模块；不得引入新依赖）
4) 验证方式（如何手动验证 + pytest 用例）

示例：
- “实现 `paths.py` 的 `normalize_remote_path()` 与 `ensure_in_sandbox()`；补齐 test_paths.py；不得修改 UI；所有失败抛出 ValidationError 映射到 ErrorCode.VALIDATION_FAILED。”

---

## 14. 完成定义（Definition of Done）
要求分块多次提交
每个提交必须满足：
- ruff 通过
- pytest 通过（至少单元测试）
- UI 不冻结（网络操作在后台）
- 所有远端危险操作经沙箱检查
- 日志不泄露敏感信息
- 新增功能有最小手动回归步骤写在 README 或开发日志中

---

## 15. 当前第一优先任务清单（从这里开始）
1) 创建 `models.py / errors.py / paths.py`（数据模型、ErrorCode、沙箱检查）
2) 实现 `Site Editor`：支持粘贴 `ssh -p PORT user@host` 自动解析
3) 实现 `连接自检`：SSH/SFTP/remote_root 可读写
4) 实现 `RemotePanel`：显示 remote_root 内容
5) 实现 Scheduler 最小状态机（pending/running/done/failed）并打通 UI 任务中心


