# SSHFerry 传输规则对齐说明

本文面向前后端协作，说明当前代码里“文件传输”这块的真实实现，重点覆盖单文件、小文件/大文件判定、分块规则、目录批量传输、远端到远端复制，以及前后端各自负责什么。

这份文档以当前代码为准，重点参考：

- `frontend/src/pages/workspace/WorkspacePage.tsx`
- `frontend/src/api/tasks.ts`
- `backend/app/api/routes/tasks.py`
- `backend/app/services/task_service.py`
- `src/core/scheduler.py`
- `src/engines/sftp_engine.py`
- `src/engines/parallel_sftp_engine.py`
- `src/engines/remote_transfer_engine.py`

## 1. 总体链路

当前项目里，传输功能虽然会经过 `frontend` 和 `backend`，但真正的传输策略基本都在共享的 `src` 里。

链路可以概括为：

1. 前端在工作区页面发起上传、下载、远端复制任务。
2. 后端 `tasks` 路由接收请求，`TaskService` 负责校验路径、探测文件/目录、创建 `Task`。
3. `TaskScheduler` 根据任务类型、文件大小、目标端点，决定用哪种引擎执行。
4. 具体数据传输由 `SftpEngine`、`ParallelSftpEngine`、`RemoteToRemoteTransferEngine`、`ScpEngine` 完成。
5. 任务进度通过 websocket 推送到前端；socket 不可用时，前端退化为轮询。

需要特别区分两类“上传”：

- 浏览器文件上传到 workspace：这是 `frontend -> backend /api/workspace/uploads` 的 HTTP 上传，不走 `TaskScheduler`，也不属于 SSH 传输逻辑。
- 本地/workspace 和远端站点之间的传输：这才是本文要对齐的 SSH/SFTP/SCP 传输链路。

## 2. 前端、后端、共享传输层的职责

### 前端

前端主要做三件事：

- 从 `WorkspacePage` 汇总用户操作，调用 `createUploadTask`、`createDownloadTask`、`createRemoteCopyTask` 等 API。
- 通过 `protocolOverride` 把用户选择的协议传给后端。
- 用 `useTaskSocket` 接收任务快照，展示任务状态、进度、速度、暂停/恢复/取消。

前端当前可选的协议覆盖值只有：

- `auto`
- `sftp`
- `scp`

也就是说，虽然后端 schema 允许 `parallel` 和 `dualpath`，当前 Web UI 并没有直接暴露这两个选项。

### 后端

后端主要负责：

- 校验请求参数和登录用户权限。
- 根据源路径是文件还是目录，创建 `file_transfer` 或 `folder_transfer` 任务。
- 对单文件任务，根据文件大小和用户指定协议，预先决定 `task.engine`。
- 把任务交给 `TaskScheduler` 异步执行。

### `src` 共享传输层

真正的传输规则在这里：

- `SftpEngine`：普通串行 SFTP 传输，支持按 offset 续传。
- `ParallelSftpEngine`：本地<->远端的大文件并行分块传输。
- `RemoteToRemoteTransferEngine`：远端到远端复制，支持 direct、bridge、parallel bridge、dual-path。
- `TaskScheduler`：决定什么时候该用普通传输、并行传输、目录 bundle、恢复传输等。

这也解释了你说的“其他目录是打包成本地 exe 版本”：本地 GUI 版和 Web 版在传输核心上是复用 `src` 的，不是两套完全不同的传输实现。

## 3. 本地/Workspace <-> 远端：单文件规则

### 3.1 基础阈值

本地/workspace 与远端之间的单文件“大文件阈值”默认是：

- `50 MB`

来源：

- `src/engines/parallel_sftp_engine.py`
- `backend/app/services/task_service.py`
- `src/core/scheduler.py`

对应常量和环境变量：

- 默认值：`DEFAULT_PARALLEL_THRESHOLD_BYTES = 50 * 1024 * 1024`
- 可被 `SSHFERRY_PARALLEL_THRESHOLD_BYTES` 覆盖

### 3.2 后端创建任务时的 engine 判定

`TaskService._resolve_file_engine()` 的规则是：

- 如果前端显式传 `parallel`，直接用 `parallel`
- 如果前端显式传 `scp`，直接用 `scp`
- 如果前端显式传 `sftp`：
  - 文件 `< 50MB` 时保留 `sftp`
  - 文件 `>= 50MB` 时会被提升成 `parallel`
- 如果前端传 `auto`：
  - 先看站点默认协议 `default_transfer_protocol`
  - 如果默认协议不是 `scp` 且文件 `>= 50MB`，用 `parallel`
  - 否则用站点默认协议

结论：

- 对本地/远端单文件来说，大文件默认优先走并行 SFTP。
- 只有用户明确选了 `scp`，或者站点默认协议就是 `scp` 且没有被并行规则改写时，才会走 SCP。

### 3.3 普通 SFTP 的传输方式

`SftpEngine.upload_file()` / `download_file()` 是串行流式传输：

- 默认流块大小：`4 MB`
- 上传时支持 `offset`
- 下载时支持 `offset`
- 断点续传时走追加/seek 模式，不做并行分块

所以普通 SFTP 的特点是：

- 适合小文件
- 也负责续传场景
- 分块是顺序读写块，不是多连接并发块

### 3.4 并行 SFTP 的分块规则

`ParallelSftpEngine` 是大文件优化的核心。

预设如下：

- `low`: `4` workers, `2 MB` chunk
- `medium`: `10` workers, `4 MB` chunk
- `high`: `16` workers, `8 MB` chunk

调度器默认使用：

- 上传：`medium`
- 下载：`high`

因此默认情况下：

- 大文件上传通常是 `10` 个 worker，`4 MB` 分块
- 大文件下载通常是 `16` 个 worker，`8 MB` 分块

但还有一个细节：

- 如果文件大小 `< 当前 chunk_size`，`ParallelSftpEngine` 会回退到普通 `SftpEngine`

也就是说，进入 `parallel` 任务后，是否真的并行，还取决于“文件是否至少大于单块大小”。

### 3.5 并行传输的执行方式

并行上传/下载的基本流程是：

1. 先计算文件总大小。
2. 预分配目标文件大小。
3. 按 `chunk_size` 切块，块的元数据是 `(offset, length)`。
4. 多个 worker 各自建立独立 SFTP 连接。
5. 每个 worker 对目标文件 `seek(offset)`，只写自己负责的区间。
6. 块失败会重试，默认每块最多重试 `4` 次。
7. 全部块完成后任务才算成功。

并行引擎还有两层自适应行为：

- 建连失败会降级当前主机的 worker 上限
- 连续成功后会逐步恢复 worker 上限

### 3.6 续传和并行之间的关系

这是一个很关键的实现细节：

- 如果检测到目标端已经存在同名文件，且大小相同，任务会直接 `skip`
- 如果目标端存在部分文件，且大小小于源文件，任务会从该 `offset` 续传
- 但只要 `offset > 0`，当前实现就不会走 `ParallelSftpEngine`
- 续传统一退回普通 `SftpEngine`

因此当前规则不是“并行也支持断点续传”，而是：

- 全新大文件：并行传输
- 部分已传文件：串行续传

## 4. 本地/Workspace <-> 远端：目录规则

目录传输不是简单地“递归逐个传文件”，而是有混合策略。

### 4.1 目录内文件如何分成大文件和小文件

`TaskScheduler._build_local_folder_mixed_plan()` 会把目录里的文件分成两类：

- 大文件：`size >= parallel_threshold`，默认 `>= 50MB`
- 小文件：`size < parallel_threshold`

然后小文件再按 batch 聚合：

- 单批累计字节上限：`128 MB`
- 单批文件数上限：`256`

对应环境变量：

- `SSHFERRY_FOLDER_ARCHIVE_FILE_COUNT_THRESHOLD`
- `SSHFERRY_FOLDER_ARCHIVE_MAX_BYTES`
- `SSHFERRY_FOLDER_ARCHIVE_MAX_FILES`

### 4.2 什么时候启用 mixed 模式

`_should_use_local_folder_mixed_transfer()` 的规则：

- 如果 bundle 功能关闭，则不用 mixed
- 如果目录里同时有大文件和小文件，用 mixed
- 如果目录里只有大文件，也用 mixed
- 如果目录里只有小文件，那么当小文件数量 `>= 32` 时用 mixed

所以 mixed 模式本质上是目录传输的默认优化模式，不只是“大文件目录”才会触发。

### 4.3 mixed 模式下的处理方式

mixed 模式里会分两路：

- 大文件：按文件单独传，大文件本身仍会套用并行传输规则
- 小文件：优先打包成 tar bundle 传输

小文件 bundle 的上传下载规则：

- 上传：本地先打成 `.tar`，上传到远端临时文件，再在远端解包
- 下载：先在远端打 `.tar`，下载到本地临时文件，再本地解包

### 4.4 哪些小文件不能进 bundle

`_partition_local_folder_small_files()` 会把部分小文件排除出 bundle，改走逐文件 worker：

- 目标端已经存在同大小文件，需要直接 skip
- 目标端已经存在部分文件，需要从 offset 续传

原因很直接：

- bundle 是整包传输，不适合单文件 skip/续传

### 4.5 远端 tar 依赖和 fallback

目录 bundle 依赖远端 shell 和 `tar`：

- 上传 bundle 前会探测远端是否有 `tar`
- 下载 bundle 同样依赖远端打包能力

如果探测失败，或者 bundle 执行失败：

- 会回退成逐文件传输

还有一个特殊优化：

- 上传目录时，如果探测到目标远端目录看起来是空的，会优先把全部小文件都放进 bundle

## 5. 远端 -> 远端：单文件规则

远端到远端复制和本地/远端不同，核心由 `RemoteToRemoteTransferEngine` 决定。

### 5.1 创建任务时的初步 engine

`TaskService._resolve_remote_copy_engine()` 的规则是：

- 如果请求里显式给了 `sftp/scp/parallel/dualpath`，原样保留
- 否则：
  - 文件 `>= 128MB` 时，设为 `dualpath`
  - 否则设为 `sftp`

默认远端复制的大文件阈值是：

- `128 MB`

对应环境变量：

- `SSHFERRY_REMOTE_DUALPATH_THRESHOLD_BYTES`

### 5.2 实际执行时的自动选路

真正执行时，`RemoteToRemoteTransferEngine.transfer_file()` 的优先级是：

1. 如果检测到目标端已有部分文件，先走 resume 分支
2. 如果请求显式是 `dualpath` 且功能开启，强制 `dualpath`
3. 否则先尝试 direct copy
4. direct 失败后：
   - 文件 `>= dualpath_threshold` 时走 `dualpath`
   - 否则文件 `>= parallel_threshold` 时走 `parallel_bridge`
   - 否则走普通 `bridge`

这里的几种模式含义是：

- `direct`：源远端直接 `scp` 到目标远端
- `bridge`：通过当前应用所在机器做中继串流
- `parallel_bridge`：中继模式下按块并发读写
- `dualpath`：同时跑 direct lane 和 relay lane，按块竞争

### 5.3 一个需要特别注意的实现现状

虽然后端 schema 和 `TaskService` 都接受远端复制的 `engine = scp / parallel / dualpath`，但当前 `transfer_file()` 里真正显式识别并强制的只有：

- `dualpath`

也就是说当前远端复制里：

- `dualpath` 可以强制
- `sftp/scp/parallel` 更多只是任务标签或上游意图
- 实际模式仍然可能进入自动选路逻辑

这是前后端对齐时必须知道的点：远端复制的 engine 语义，和本地/远端单文件的 engine 语义并不完全一致。

### 5.4 远端复制的续传规则

调度器会先检查目标远端文件状态：

- 目标大小等于总大小且任务已有进度：直接标记 `skipped`
- 目标大小在 `(0, total)` 且任务已有进度：从目标已有大小继续
- 否则从 `0` 开始

resume 时的策略是：

- 若可 direct，则优先 `direct_resume`
- 否则退回 `bridge_resume`

所以远端复制是支持续传的，但不是所有模式都对称支持；续传优先 direct append，不行再 bridge append。

### 5.5 普通 bridge 的分块

普通 bridge 本质上是串行中继：

- 从源远端按 `4 MB` 块读
- 通过当前进程写到目标远端
- 支持 `offset`

所以它是“顺序流式桥接”，不是并行桥接。

### 5.6 parallel bridge 的分块

当 direct 失败且文件达到并行阈值时，会走 `parallel_bridge`。

它会综合源端下载 preset 和目标端上传 preset，取两边较小值：

- worker 数：两边 preset worker 的较小值
- chunk 大小：两边 preset chunk 的较小值

默认配置下：

- relay download preset = `high` = `16 workers / 8MB`
- relay upload preset = `medium` = `10 workers / 4MB`

因此默认 `parallel_bridge` 实际会取：

- `10 workers`
- `4 MB` chunk

### 5.7 dual-path 的分块和规则

`dualpath` 是远端大文件复制里最复杂的模式，默认参数：

- 阈值：`128 MB`
- chunk 大小：`32 MB`

核心思路：

1. 把文件切成 `32MB` 左右的块。
2. 同时开两条 lane：
   - `direct lane`：源端用 `dd` 读块，再写到目标端分片文件
   - `relay lane`：源端 SFTP 读块，经本机中继写到目标端分片文件
3. 每个块谁先完成就算谁赢。
4. 如发现另一条 lane 明显慢，允许有限度地对同一块做“重复挑战”。
5. 全部分片在目标端合并成最终文件。
6. 临时分片目录和临时文件清理掉。

当前默认只允许有限重复块：

- `SSHFERRY_REMOTE_DUALPATH_MAX_DUP_CHUNKS`
- 默认值是 `1`

所以 dual-path 不是简单“双倍并行”，而是带竞争和纠偏机制的双通路复制。

## 6. 远端 -> 远端：目录规则

远端目录复制也有 mixed 模式。

### 6.1 目录规划

`_plan_remote_dir_transfer()` 会：

- 扫描目录树
- 统计总文件数和总字节数
- 把文件拆成 `large_files` 和 `small_files`
- 把小文件按 bundle 规则分批

阈值与本地目录规则相似：

- 大文件阈值：`parallel_threshold`，默认 `50MB`
- 小文件 bundle 条件阈值：默认 `32` 个文件
- 单 bundle 最大字节：默认 `128MB`
- 单 bundle 最大文件数：默认 `256`

### 6.2 mixed 模式启用条件

规则与本地目录类似：

- 有大文件且有小文件：启用
- 只有大文件：启用
- 只有小文件但数量达到阈值：启用

### 6.3 mixed 模式执行方式

远端目录 mixed 会并行跑两类工作：

- 大文件：逐个调用 `transfer_file()`，因此会继续套用 direct / dualpath / parallel bridge / bridge 的单文件选路
- 小文件：按 bundle 批次，通过源端 `tar` 打流并直接发送到目标端解包

和本地目录 bundle 不同的是，远端目录 bundle 尽量走“远端到远端直连 tar pipe”，不是先落到本机再中转。

### 6.4 依赖条件

远端目录 bundle 依赖：

- 源端有 `tar`
- 能从源端 `ssh/scp` 到目标端
- 目标端目录可写

如果这些 direct bundle 条件不满足，会退回 direct/relay 的目录复制路径。

## 7. 任务恢复、跳过、暂停、重试

### 7.1 skip 规则

以下情况会直接跳过：

- 本地/远端单文件或目录子文件：目标同名文件大小完全一致
- 远端->远端单文件：目标文件大小等于总大小，且任务状态表明已完成进度

### 7.2 resume 规则

以下情况会续传：

- 本地上传：远端目标文件存在且更小
- 本地下载：本地目标文件存在且更小
- 远端复制：目标远端存在且更小

但续传和并行不是叠加关系：

- 本地/远端续传时回退到普通 SFTP
- 远端复制续传优先 direct resume，再退 bridge resume

### 7.3 chunk / worker 级重试

当前代码里可见的块级重试：

- `ParallelSftpEngine`：每个块默认最多重试 `4` 次
- `parallel_bridge`：每个块默认最多重试 `4` 次
- `dualpath`：每个块失败超过 `4` 次后整体失败

### 7.4 暂停 / 恢复

任务支持 pause / resume / cancel / restart，但实现语义要注意：

- `pause` 本质是设置中断标记并停止当前执行
- `resume` 会重新排队
- 对单文件任务，调度器会基于现有目标文件大小做恢复判断
- 对目录任务，`resume` 会把 `bytes_done` / `subtask_done` 归零，再重新按每个文件是否已存在来跳过或续传

所以目录恢复更接近“重新扫描 + 跳过已完成项”，不是严格保存每个子任务现场。

## 8. 参数和可调项

和传输规则最相关的环境变量包括：

- `SSHFERRY_PARALLEL_THRESHOLD_BYTES`
- `SSHFERRY_PARALLEL_PRESET`
- `SSHFERRY_PARALLEL_UPLOAD_PRESET`
- `SSHFERRY_PARALLEL_DOWNLOAD_PRESET`
- `SSHFERRY_PARALLEL_WORKERS`
- `SSHFERRY_PARALLEL_CHUNK_BYTES`
- `SSHFERRY_PARALLEL_MAX_CHUNK_RETRIES`
- `SSHFERRY_FOLDER_ARCHIVE_ENABLED`
- `SSHFERRY_FOLDER_ARCHIVE_FILE_COUNT_THRESHOLD`
- `SSHFERRY_FOLDER_ARCHIVE_MAX_BYTES`
- `SSHFERRY_FOLDER_ARCHIVE_MAX_FILES`
- `SSHFERRY_REMOTE_DUALPATH_THRESHOLD_BYTES`
- `SSHFERRY_REMOTE_DUALPATH_CHUNK_BYTES`
- `SSHFERRY_REMOTE_DUALPATH_ENABLED`
- `SSHFERRY_REMOTE_DUALPATH_MAX_DUP_CHUNKS`
- `SSHFERRY_REMOTE_RELAY_DOWNLOAD_PRESET`
- `SSHFERRY_REMOTE_RELAY_UPLOAD_PRESET`
- `SSHFERRY_SFTP_WINDOW_BYTES`（SFTP 通道接收窗口，默认 16MB；高延迟链路的单连接吞吐上限约为 窗口/RTT）
- `SSHFERRY_SCP_BUFF_BYTES`（SCP 传输缓冲区，默认 1MB）

如果后面要和你另一个合作者继续对齐，这些变量就是“规则开关”和“性能旋钮”的主入口。

## 9. 建议你们对齐时重点确认的点

从当前实现看，最值得前后端一起确认的是下面这些：

1. Web 前端现在只允许 `auto/sftp/scp`，没有把 `parallel/dualpath` 暴露出来。
2. 本地/远端单文件里，用户即使选 `sftp`，大于 `50MB` 也会升级成 `parallel`。
3. 本地/远端的大文件并行传输不做 offset 续传；一旦进入续传，统一退回普通 SFTP。
4. 目录里的小文件不是简单逐个传，而是可能被打成 tar bundle。
5. 远端复制的 `engine` 语义和本地/远端不一致，当前真正可强制的主要是 `dualpath`。
6. 远端大文件复制默认会优先尝试 `direct`，失败后才考虑 `dualpath` 或 `parallel_bridge`。
7. exe 桌面版和 Web 版的传输核心是共享 `src` 的，所以规则文档最好围绕 `src` 写，而不是把前端和桌面端拆成两套结论。

## 10. 一句话总结

当前 SSHFerry 的传输实现不是“单一 SFTP 上传下载”，而是一个分层调度系统：

- 前端负责提交任务和显示状态
- 后端负责建任务和调度入口
- `src` 负责真正的传输策略

其中最核心的规则是：

- 单文件按大小决定是否并行
- 目录按“大文件逐个传 + 小文件 bundle”做混合优化
- 远端复制优先 direct，不行再走 bridge / parallel bridge / dual-path
- 续传优先保证正确性，很多场景会退回串行路径
