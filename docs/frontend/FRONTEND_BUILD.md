# SSHFerry Frontend Build Guide

## Goal

这份文档用于固定 SSHFerry 新前端的开发与构建方案，避免后续前端开发时反复讨论脚手架、目录、启动顺序和联调方式。

目标是：

- 前端使用 `React`
- 后端使用本地 `FastAPI`
- 整体仍是桌面化产品形态
- 前端优先完成和当前桌面版等价的核心操作流

配套文档：

- 接口说明见 [FRONTEND_API.md](./FRONTEND_API.md)
- 后端迁移规划见 [BACKEND_TODO.md](../backend/BACKEND_TODO.md)

## Fixed Decisions

后续前端开发默认按下面这些约定执行，不再重复选型：

- 前端目录：`frontend/`
- 包管理器：`npm`
- 前端框架：`React + Vite + TypeScript`
- 路由：`react-router-dom`
- 服务端状态：`@tanstack/react-query`
- 客户端 UI 状态：`zustand`
- HTTP 客户端：`axios`
- 构建产物目录：`frontend/dist`
- 后续桌面壳：优先 `Electron`

这些选择的原因很直接：

- `Vite` 启动快，开发体验稳
- `TypeScript` 能把接口字段和任务模型约束住
- `React Query` 适合管理 REST 请求和缓存
- `Zustand` 适合承载会话、选中项、布局状态这类本地 UI 状态
- `Electron` 后续接 Python 本地后端最直接

## Source UI Baseline

前端开发必须对齐当前桌面版，而不是只把接口串起来。原桌面版最重要的 UI 语义有这些：

- 左侧是站点与全局操作区：站点增删改、连接检查、打开/关闭会话、全局传输协议覆盖（`Auto/SFTP/SCP`）
- 中间是本地文件面板：盘符切换、路径输入、刷新、父目录返回、多选、拖拽接收远端下载
- 右侧不是单个远端面板，而是“多远端 session 并排工作区”
- 底部是任务中心 + 日志区
- 任务创建不只有按钮，还包括拖拽：本地到远端、远端到本地、远端到远端
- 站点编辑不只是普通表单，还支持从 SSH 命令快速导入

后续 React 前端如果缺掉这些语义，就不能算“符合源程序”。

## Proposed Directory Layout

当前仓库还没有前端目录。开始开发时，目录按这个结构创建：

```text
frontend/
  index.html
  package.json
  tsconfig.json
  vite.config.ts
  .env.development
  .env.production
  src/
    main.tsx
    app/
      router.tsx
      providers.tsx
      store.ts
    api/
      http.ts
      auth.ts
      sites.ts
      sessions.ts
      localFiles.ts
      remoteFiles.ts
      tasks.ts
      ws.ts
      types.ts
    pages/
      sites/
      workspace/
      tasks/
    components/
      layout/
      sites/
      file-browser/
      remote-workspace/
      tasks/
      logs/
      common/
    hooks/
      useBackendSession.ts
      useTaskSocket.ts
      useRemoteSession.ts
    styles/
      index.css
      tokens.css
```

## Bootstrap Commands

如果下次开始真正创建前端，请直接执行下面这组命令：

```powershell
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install react-router-dom zustand @tanstack/react-query axios
```

如果后续要加代码规范，再补：

```powershell
npm install -D eslint prettier @types/node
```

## Environment Variables

前端一开始就统一走环境变量，不要把后端地址写死在组件里。

开发环境建议：

```env
VITE_BACKEND_HTTP_URL=http://127.0.0.1:18080
VITE_BACKEND_WS_URL=ws://127.0.0.1:18080
```

生产环境建议：

```env
VITE_BACKEND_HTTP_URL=http://127.0.0.1:18080
VITE_BACKEND_WS_URL=ws://127.0.0.1:18080
```

说明：

- 当前产品形态是本地桌面化，前后端都跑在用户机器上
- 不要把地址改成远程服务器语义
- 打包到 Electron 后，地址仍然建议保持 `127.0.0.1`

## Backend Startup Contract

前端联调默认依赖本地后端：

```powershell
python -m backend.app.main
```

后端启动后，前端必须遵循这个初始化顺序：

1. `GET /api/health`
2. `GET /api/auth/session`
3. 记录返回的 `token`
4. 将 `token` 写入后续所有 REST 请求头 `X-SSHFerry-Token`
5. 建立 `ws://127.0.0.1:18080/api/ws/tasks?token=...`

不要反过来先打业务接口，否则会被 `401` 拦住。

## Frontend App Flow

前端启动时建议这样分层：

1. `providers.tsx`
   - 初始化 `QueryClientProvider`
   - 初始化路由
2. `useBackendSession.ts`
   - 请求 `/api/health`
   - 请求 `/api/auth/session`
   - 将 token 写入全局请求客户端
3. 进入应用主界面
4. `useTaskSocket.ts`
   - 建立任务 websocket
   - 接收任务快照并同步到 store

## HTTP Client Rules

`axios` 客户端建议做成单例，例如 `src/api/http.ts`。

规则固定如下：

- baseURL 来自 `VITE_BACKEND_HTTP_URL`
- 所有业务接口自动加 `X-SSHFerry-Token`
- `401` 统一提示“本地后端会话失效，需要重新初始化”
- `503` 统一提示“后端未就绪或依赖缺失”
- 不要在组件内部直接手写 `fetch('http://127.0.0.1:18080/...')`

## WebSocket Rules

实时任务接口使用：

```text
ws://127.0.0.1:18080/api/ws/tasks?token=...
```

前端处理规则：

- 首次连接后立即消费第一帧 `task_snapshot`
- 收到新的 `task_snapshot` 时整体替换任务中心数据
- websocket 断开时自动重连
- 重连失败时退回轮询 `GET /api/tasks`
- 收到 `type=error` 时展示后端错误信息

当前后端 websocket 不是细粒度事件流，而是“变化时推送任务快照”。前端不要假设它会发送 `task_added`、`task_finished` 这类事件名。

## Required UI Mapping

下面这些界面点来自原桌面版，前端第一阶段必须保留：

### 1. Site Sidebar

至少包含：

- 站点列表
- `Add/Edit/Remove Site`
- `Check Connection`
- `Open Session`
- `Close Session`
- 全局 `Task Protocol Override` 选择器：`Auto/SFTP/SCP`

注意：

- 这个协议覆盖器是全局 UI 控件，不是站点字段
- 任务创建时要优先考虑它，再考虑站点默认协议

### 2. Site Editor

站点编辑界面至少包含：

- `Site Name`
- `Host`
- `Port`
- `Username`
- `Remote Root`
- `Default Transfer Protocol`
- `Auth Method`
- `Password` / `Key Path` / `Key Passphrase`
- `Remember Password`
- `Quick Import from SSH Command`

不要把站点页简化成只剩几个字段，否则会明显低于原程序能力。

### 3. Local File Panel

本地面板至少包含：

- 盘符选择器
- 当前路径输入框
- `..` 返回上级
- `Refresh`
- 文件列表多选
- 拖拽接收远端下载

这意味着前端不能只做一个“选择文件上传”按钮。必须保留“本地文件浏览器”的产品语义。

### 4. Remote Workspace

远端区域必须按“多 session 工作区”设计，而不是单个远端面板。

至少支持：

- 同时打开多个远端 session
- 并排显示多个远端面板
- 每个面板独立刷新、返回上级、关闭
- 每个面板内切换站点或 session 上下文
- 远端到远端拖拽互传

建议实现上用 `split panes` 或可关闭标签页加多列布局，但结果语义必须和原桌面版一致：能在一个窗口里同时看多个远端工作区。

### 5. Task Center

任务中心至少包含：

- 任务摘要
- 任务表格
- `Pause/Resume/Cancel/Restart`
- `Clear Finished`
- 按任务状态排序
- 文件夹任务显示子任务进度

后端 websocket 已经能提供实时快照，前端应直接把它用于任务中心。

### 6. Log Area

原桌面版底部右侧还有日志区。这个可以放到前端第二阶段，但文档里必须保留它，不要在设计上把它永久删掉。

## Suggested First Screens

第一阶段建议只做 3 个主屏，但屏内信息不要缩水：

1. `Sites / Session Sidebar`
   - 站点管理
   - 会话打开关闭
   - 全局协议覆盖器

2. `Workspace`
   - 左侧本地文件面板
   - 右侧多远端 session 工作区
   - 支持拖拽创建任务

3. `Tasks`
   - 任务中心
   - 实时 websocket 同步
   - 第二阶段再补日志区

## API-to-UI Mapping

建议前端直接按这个映射开发：

- 站点管理：`/api/sites`
- 连接检查：`/api/connections/check`
- 打开/关闭远端会话：`/api/sessions/open` / `/api/sessions/close`
- 本地文件树：`/api/local-files/drives` / `/api/local-files/list`
- 远端文件树：`/api/remote-files/list`
- 文件操作：`/api/remote-files/mkdir` / `/api/remote-files/rename` / `/api/remote-files/delete`
- 任务创建：`/api/tasks/upload` / `/api/tasks/download` / `/api/tasks/remote-copy`
- 任务控制：`/api/tasks/{task_id}/pause` 等
- 任务实时更新：`/api/ws/tasks`

## Shared Type Strategy

前端开发开始后，第一批类型建议手动定义在：

```text
frontend/src/api/types.ts
```

至少先建这些类型：

- `HealthResponse`
- `AuthSessionResponse`
- `SiteResponse`
- `SessionResponse`
- `LocalEntry`
- `RemoteEntry`
- `TaskItem`
- `TaskSnapshotMessage`

原则：

- 以后端实际响应字段为准
- 不在组件里写匿名对象类型
- 任务 websocket 和 `GET /api/tasks` 尽量复用同一套 `TaskItem`

## Build Commands

前端建好后，统一使用下面这些命令：

开发：

```powershell
cd frontend
npm run dev
```

构建：

```powershell
cd frontend
npm run build
```

构建产物：

```text
frontend/dist
```

后续 Electron 只负责：

- 加载 `frontend/dist`
- 启动 Python 后端进程
- 关闭窗口时回收后端进程

不要把业务逻辑再塞回 Electron 主进程。

## Local Development Checklist

开始前端开发时，建议按这个顺序自检：

1. 后端 `python -m backend.app.main` 能启动
2. `GET /api/health` 正常
3. `GET /api/auth/session` 正常
4. 前端能拿到 token 并打通 `GET /api/sites`
5. 前端能打通 `GET /api/local-files/drives`
6. 前端能打开一个远端 session
7. 前端能同时打开两个远端 session 并并排显示
8. 前端能列出远端目录
9. 前端能创建上传、下载、远端互传任务
10. 前端能切换全局传输协议覆盖器并影响任务创建
11. 前端能收到 websocket 任务快照

## Definition Of Done For Frontend Phase 1

第一阶段前端完成的标准建议定成：

- 能管理站点
- 能从 SSH 命令快速导入站点
- 能打开多个远端会话并同时显示
- 能浏览本地目录和远端目录
- 能创建上传、下载、远端互传任务
- 能切换全局协议覆盖器
- 能在任务中心实时看到任务变化
- 能做暂停、恢复、取消、重启、清空已完成

只要这 8 条打通，前端主链路才算真正对齐原桌面版。

## Current Risks

当前前端开发最容易踩的坑有这些：

- 忘记先取 `/api/auth/session`，导致业务接口全部 `401`
- 把 websocket 当成细粒度事件流，而不是快照流
- 在组件里直接拼后端 URL，后面切环境很难收口
- 把远端工作区做成单 session 视图，丢掉原程序多远端并排能力
- 忽略全局协议覆盖器，只保留站点默认协议
- 把本地文件面板简化成上传按钮，丢掉文件浏览器语义
- 过早引入复杂 UI 库，拖慢第一版联调

## Recommendation

下次正式开始前端开发时，不建议再先讨论技术方案。直接按这份文档执行：

1. 建 `frontend/`
2. 起 `Vite + React + TypeScript`
3. 先接 `/api/health` 和 `/api/auth/session`
4. 先做站点侧边栏、本地文件面板、多远端工作区、任务中心
5. 最后再补日志区和桌面壳细节

这样推进速度最快，也最不容易做偏。

