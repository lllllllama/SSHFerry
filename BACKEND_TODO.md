# SSHFerry Backend TODO

## Goal

将当前 `PySide6` 桌面应用改造成“桌面化前后端分离”架构：

- 前端：`React`
- 后端：`FastAPI`
- 运行形态：整体仍运行在用户本机
- 产品定位：保留本地文件系统访问、远端 SSH/SFTP/SCP、任务调度、任务中心、远端互传能力

当前阶段只开发后端，不处理 React 页面实现。

## Principles

- 后端只监听 `127.0.0.1`
- 后端负责所有本地文件系统访问、SSH 连接、任务调度、站点存储
- 前端不直接接触 SSH、磁盘、凭据
- 优先复用现有 `src/core`、`src/engines`、`src/services`、`src/shared`
- 不一次性重写传输逻辑，先做“可调用化”和“服务化”
- 先跑通 API 和任务推送，再做 UI

## Existing Reusable Modules

这些模块优先复用，不先推翻：

- `src/shared/models.py`
- `src/shared/errors.py`
- `src/shared/paths.py`
- `src/shared/logging_.py`
- `src/core/task_state.py`
- `src/core/scheduler.py`
- `src/engines/sftp_engine.py`
- `src/engines/scp_engine.py`
- `src/engines/parallel_sftp_engine.py`
- `src/engines/remote_transfer_engine.py`
- `src/services/site_store.py`
- `src/services/connection_checker.py`
- `src/services/metrics.py`

这些模块未来会被替换：

- `src/app/main.py`
- `src/ui/**`
- `src/core/events.py`

## Target Backend Structure

建议新增后端目录：

```text
backend/
  app/
    main.py                 # FastAPI app entry
    api/
      routes/
        health.py
        sites.py
        local_files.py
        remote_files.py
        tasks.py
        connections.py
        sessions.py
      ws/
        tasks.py
    schemas/
      common.py
      sites.py
      files.py
      tasks.py
      connections.py
    services/
      app_state.py
      site_service.py
      local_file_service.py
      remote_session_service.py
      remote_file_service.py
      task_service.py
      connection_service.py
    adapters/
      legacy/
        core/
        engines/
        services/
        shared/
```

第一阶段可以先不移动旧代码，先通过 `backend/app/services` 包装现有 `src/*` 逻辑。

## Phase 0 - Backend Skeleton

- [ ] 新建 `backend/app/main.py`
- [ ] 引入 `FastAPI`
- [ ] 配置基础中间件
- [ ] 统一 API 前缀，例如 `/api`
- [ ] 新建基础健康检查接口 `GET /api/health`
- [ ] 配置后端启动方式
- [ ] 明确开发命令和目录结构

验收标准：

- [ ] `uvicorn backend.app.main:app --reload` 可以启动
- [ ] `GET /api/health` 返回 `200`

## Phase 1 - Application State

先建立一个长期存在的本地后端状态容器，替代当前 `MainWindow` 持有的全局对象。

- [ ] 新建 `backend/app/services/app_state.py`
- [ ] 在 `AppState` 中持有：
  - [ ] `SiteStore`
  - [ ] `TaskScheduler`
  - [ ] 内存态远端 session 注册表
  - [ ] 日志广播器
  - [ ] WebSocket 连接管理器
- [ ] 应用启动时初始化 `TaskScheduler`
- [ ] 应用关闭时停止 `TaskScheduler`

验收标准：

- [ ] FastAPI 生命周期内仅有一个 `TaskScheduler`
- [ ] 应用退出时调度器能干净停止

## Phase 2 - Site APIs

先把站点管理从桌面 UI 中抽出来。

- [ ] 定义 `Site` 相关 Pydantic schema
- [ ] 新建 `SiteService`
- [ ] 实现接口：
  - [ ] `GET /api/sites`
  - [ ] `POST /api/sites`
  - [ ] `PUT /api/sites/{site_name}`
  - [ ] `DELETE /api/sites/{site_name}`
- [ ] 保持与当前 `SiteStore` 的兼容
- [ ] 处理 `remember_password` 语义
- [ ] 返回结构里不要直接泄露敏感字段

验收标准：

- [ ] 可以通过 API 增删改查站点
- [ ] `sites.json` 兼容旧格式
- [ ] 默认不返回明文密码

## Phase 3 - Connection APIs

把连接检查和会话打开逻辑从 Qt 线程改成服务接口。

- [ ] 新建 `ConnectionService`
- [ ] 复用 `ConnectionChecker`
- [ ] 实现接口：
  - [ ] `POST /api/connections/check`
  - [ ] `POST /api/sessions/open`
  - [ ] `POST /api/sessions/close`
  - [ ] `GET /api/sessions`
- [ ] 设计 `session_id`
- [ ] 内存中维护 `session_id -> SiteConfig`

注意：

- 当前项目的“session”本质是一个 UI 视角下的远端工作区，不等于持久 SSH 长连接
- 第一阶段可以先保持这个语义，不强行做连接池

验收标准：

- [ ] 能通过 API 检查站点连通性
- [ ] 能创建和关闭远端 session
- [ ] 同一个站点允许打开多个 session

## Phase 4 - Local File APIs

这一步是桌面化前后端分离的关键，因为浏览器前端本身不能直接浏览整机磁盘。

- [ ] 新建 `LocalFileService`
- [ ] 实现接口：
  - [ ] `GET /api/local-files/drives`
  - [ ] `GET /api/local-files/list?path=...`
  - [ ] `GET /api/local-files/stat?path=...`
- [ ] 统一 Windows / Linux / macOS 表现
- [ ] 定义本地文件条目 schema
- [ ] 限制危险输入，避免路径遍历和无效路径异常扩散

验收标准：

- [ ] 能列出盘符或根目录
- [ ] 能浏览本地目录
- [ ] 前端能拿到和当前 `LocalPanel` 等价的基础信息

## Phase 5 - Remote File APIs

把远端文件树操作从 `MainWindow` 中拆出。

- [ ] 新建 `RemoteFileService`
- [ ] 复用 `SftpEngine`
- [ ] 实现接口：
  - [ ] `GET /api/remote-files/list`
  - [ ] `POST /api/remote-files/mkdir`
  - [ ] `POST /api/remote-files/rename`
  - [ ] `POST /api/remote-files/delete`
  - [ ] `GET /api/remote-files/stat`
- [ ] 所有危险操作统一走 `ensure_in_sandbox()`
- [ ] 把错误稳定映射成 API 错误响应

接口输入建议：

- 通过 `session_id` 指定站点上下文
- 不让前端直接传完整 `SiteConfig`

验收标准：

- [ ] 可以通过 API 浏览远端目录
- [ ] 可以创建目录、重命名、删除
- [ ] 越过 `remote_root` 的操作被拒绝

## Phase 6 - Task APIs

先把任务创建和控制能力服务化，保留现有 `TaskScheduler`。

- [ ] 新建 `TaskService`
- [ ] 实现接口：
  - [ ] `GET /api/tasks`
  - [ ] `POST /api/tasks/upload-file`
  - [ ] `POST /api/tasks/upload-folder`
  - [ ] `POST /api/tasks/download-file`
  - [ ] `POST /api/tasks/download-folder`
  - [ ] `POST /api/tasks/remote-copy-file`
  - [ ] `POST /api/tasks/remote-copy-folder`
  - [ ] `POST /api/tasks/{task_id}/pause`
  - [ ] `POST /api/tasks/{task_id}/resume`
  - [ ] `POST /api/tasks/{task_id}/cancel`
  - [ ] `POST /api/tasks/{task_id}/restart`
  - [ ] `POST /api/tasks/clear-finished`
- [ ] 把 `MainWindow` 中任务创建逻辑迁入 service
- [ ] 统一请求 DTO

验收标准：

- [ ] 能通过 API 创建上传下载任务
- [ ] 能暂停、恢复、取消、重试
- [ ] `GET /api/tasks` 能返回当前任务快照

## Phase 7 - Task Event Push

不要沿用 Qt 定时器轮询，改成 WebSocket 推送。

- [ ] 新建 WebSocket 路由 `WS /api/ws/tasks`
- [ ] 增加任务事件广播器
- [ ] 在任务状态变化时推送：
  - [ ] `task_added`
  - [ ] `task_updated`
  - [ ] `task_finished`
- [ ] 在日志变化时可选推送 `log_message`
- [ ] 前端仍可保留 `GET /api/tasks` 作为兜底同步接口

实现建议：

- 初期不强改 `TaskScheduler` 内部结构
- 可以先由后端定时采样任务快照并广播
- 跑通后再改成更细粒度事件流

验收标准：

- [ ] 前端能实时看到任务进度变化
- [ ] 页面刷新后可通过 `GET /api/tasks` 恢复状态

## Phase 8 - Auth and Local Security

虽然是本机后端，也不能裸奔。

- [ ] 后端仅监听 `127.0.0.1`
- [ ] 增加本地 session token 机制
- [ ] 限制 CORS 只允许桌面前端来源
- [ ] 敏感接口校验 token
- [ ] 明确日志脱敏策略
- [ ] 明确密码返回策略和持久化策略

验收标准：

- [ ] 无 token 时敏感接口拒绝访问
- [ ] 后端不对外网卡监听
- [ ] 日志不输出密码和私钥内容

## Phase 9 - Legacy Refactor

在 API 跑通后，再逐步把旧代码重组。

- [ ] 将现有 `src/shared` 迁到后端正式包
- [ ] 将现有 `src/core` 迁到后端正式包
- [ ] 将现有 `src/engines` 迁到后端正式包
- [ ] 将现有 `src/services` 迁到后端正式包
- [ ] 清理 Qt 依赖残留
- [ ] 删除 `MainWindow` 对业务逻辑的承载角色

验收标准：

- [ ] 后端核心不再依赖 `src/ui`
- [ ] 旧 UI 可以被彻底替换而不影响后端

## Initial API Draft

### Health

- [ ] `GET /api/health`

### Sites

- [ ] `GET /api/sites`
- [ ] `POST /api/sites`
- [ ] `PUT /api/sites/{name}`
- [ ] `DELETE /api/sites/{name}`

### Connections / Sessions

- [ ] `POST /api/connections/check`
- [ ] `GET /api/sessions`
- [ ] `POST /api/sessions/open`
- [ ] `POST /api/sessions/close`

### Local Files

- [ ] `GET /api/local-files/drives`
- [ ] `GET /api/local-files/list`
- [ ] `GET /api/local-files/stat`

### Remote Files

- [ ] `GET /api/remote-files/list`
- [ ] `GET /api/remote-files/stat`
- [ ] `POST /api/remote-files/mkdir`
- [ ] `POST /api/remote-files/rename`
- [ ] `POST /api/remote-files/delete`

### Tasks

- [ ] `GET /api/tasks`
- [ ] `POST /api/tasks/upload-file`
- [ ] `POST /api/tasks/upload-folder`
- [ ] `POST /api/tasks/download-file`
- [ ] `POST /api/tasks/download-folder`
- [ ] `POST /api/tasks/remote-copy-file`
- [ ] `POST /api/tasks/remote-copy-folder`
- [ ] `POST /api/tasks/{task_id}/pause`
- [ ] `POST /api/tasks/{task_id}/resume`
- [ ] `POST /api/tasks/{task_id}/cancel`
- [ ] `POST /api/tasks/{task_id}/restart`
- [ ] `POST /api/tasks/clear-finished`

### WebSocket

- [ ] `WS /api/ws/tasks`

## Immediate Development Order

这是接下来建议的实际开发顺序：

1. [ ] 建 `backend/app/main.py`
2. [ ] 建 `AppState`
3. [ ] 接 `GET /api/health`
4. [ ] 接 `GET /api/sites`
5. [ ] 接 `POST /api/sites`
6. [ ] 接 `POST /api/connections/check`
7. [ ] 接 `GET /api/local-files/list`
8. [ ] 接 `POST /api/sessions/open`
9. [ ] 接 `GET /api/remote-files/list`
10. [ ] 接 `GET /api/tasks`
11. [ ] 接 `POST /api/tasks/upload-file`
12. [ ] 接 `WS /api/ws/tasks`

## Out of Scope For Now

当前阶段先不做这些：

- [ ] React 页面实现
- [ ] Electron 打包
- [ ] 登录体系和多用户
- [ ] 远程部署版 Web 服务
- [ ] 数据库存储
- [ ] 彻底重写 `TaskScheduler`
- [ ] 自适应 preset 完整闭环

## Notes

- 当前项目的核心风险不在 SSH 能力，而在“把桌面本地文件能力稳定地收口到本地后端”
- 后端先跑通后，再回头决定 React 状态管理和桌面壳
- 迁移期间允许“旧 `src` 逻辑 + 新 `backend/app` 包装层”并存
