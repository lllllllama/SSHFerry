# SSHFerry Frontend API Guide

## Purpose

这份文档专门给前端开发使用。

开始前端开发前，先配合阅读 [FRONTEND_BUILD.md](./FRONTEND_BUILD.md)。

目标：

- 说明当前本地 FastAPI 后端已经提供的接口
- 固定请求参数和响应字段
- 说明鉴权、跨域和错误约定
- 作为 React 前端对接基线

当前接口前缀统一为：

```text
/api
```

## General Rules

### Backend Runtime

- 后端运行在用户本机
- 默认监听 `127.0.0.1:18080`
- 默认允许本地前端开发源：`localhost:5173`、`127.0.0.1:5173`、`localhost:4173`、`127.0.0.1:4173`、`localhost:3000`、`127.0.0.1:3000`
- 打包后如果前端以 `file://` 或本地壳运行，浏览器 `Origin` 可能为 `null`，当前后端已允许

### Response Style

- 成功时返回 `200` / `201` / `204`
- 失败时返回标准 FastAPI 错误格式：

```json
{
  "detail": "error message"
}
```

### Auth Rule

除以下接口外，其他 `/api` 接口都要求请求头带本地 token：

- `GET /api/health`
- `GET /api/auth/session`
- `GET /api/ws/tasks?token=...` 或 websocket 连接头带 `X-SSHFerry-Token`

请求头名称固定为：

```text
X-SSHFerry-Token
```

推荐前端启动顺序：

1. `GET /api/health`
2. `GET /api/auth/session`
3. 把返回的 `token` 写入全局请求头 `X-SSHFerry-Token`
4. 如果要连 websocket，用 `ws://127.0.0.1:18080/api/ws/tasks?token=...`
5. 再访问其他业务接口

### Session Concept

- `session_id` 表示一个远端会话上下文
- 当前阶段 `session_id` 是后端内存态对象，不是持久 SSH 长连接 ID
- 页面刷新后如果后端进程还在，`session_id` 仍有效
- 后端重启后，`session_id` 会丢失

## 1. Health

### `GET /api/health`

用途：

- 检查后端是否启动
- 检查核心服务是否可用
- 告知前端鉴权请求头名称

响应示例：

```json
{
  "status": "ok",
  "service": "sshferry-backend",
  "version": "0.1.1",
  "ready": true,
  "scheduler_running": true,
  "session_count": 0,
  "startup_error": null,
  "auth_required": true,
  "auth_header_name": "X-SSHFerry-Token"
}
```

## 2. Auth

### `GET /api/auth/session`

用途：

- 获取当前本地后端会话 token
- 供 React 前端初始化请求客户端时使用

响应示例：

```json
{
  "token": "random-token",
  "header_name": "X-SSHFerry-Token",
  "token_type": "local"
}
```

前端建议：

- 启动时调用一次即可
- 将 `token` 放进后续所有 REST 请求头
- 将 `token` 作为 websocket query 参数传给实时接口

## 3. Sites

### `GET /api/sites`

用途：

- 获取站点列表

### `POST /api/sites`

用途：

- 新建站点

### `PUT /api/sites/{site_name}`

用途：

- 更新已有站点

### `DELETE /api/sites/{site_name}`

用途：

- 删除站点
- 会同时清理引用该站点的内存 session

## 4. Connections

### `POST /api/connections/check`

用途：

- 对指定站点执行连接自检

## 5. Sessions

### `GET /api/sessions`

用途：

- 获取当前活动远端会话列表

### `POST /api/sessions/open`

用途：

- 创建一个远端会话上下文

### `POST /api/sessions/close`

用途：

- 关闭远端会话上下文

## 6. Local Files

### `GET /api/local-files/drives`

用途：

- 获取本地盘符或根目录入口

### `GET /api/local-files/list?path=...`

用途：

- 获取本地目录列表

### `GET /api/local-files/stat?path=...`

用途：

- 获取本地路径详情

## 7. Remote Files

### `GET /api/remote-files/list?session_id=...&path=...`

用途：

- 获取远端目录列表

### `GET /api/remote-files/stat?session_id=...&path=...`

用途：

- 获取远端文件或目录详情

### `POST /api/remote-files/mkdir`

用途：

- 新建远端目录

### `POST /api/remote-files/rename`

用途：

- 重命名或移动远端文件/目录

### `POST /api/remote-files/delete`

用途：

- 删除远端文件或目录

说明：

- 远端路径现在会拒绝空白字符串

## 8. Tasks REST

### `GET /api/tasks`

用途：

- 获取当前任务列表

说明：

- 当前返回全量任务快照
- 如果前端还没接 websocket，可以继续轮询这个接口

### `POST /api/tasks/upload`

用途：

- 创建本地到远端的上传任务
- 同时支持文件上传和目录上传

### `POST /api/tasks/download`

用途：

- 创建远端到本地的下载任务
- 同时支持文件下载和目录下载

### `POST /api/tasks/remote-copy`

用途：

- 创建远端到远端传输任务
- 同时支持文件与目录

### `POST /api/tasks/{task_id}/pause`

用途：

- 请求暂停一个运行中任务

### `POST /api/tasks/{task_id}/resume`

用途：

- 恢复一个已暂停任务

### `POST /api/tasks/{task_id}/cancel`

用途：

- 取消一个任务

### `POST /api/tasks/{task_id}/restart`

用途：

- 重启一个终态任务

### `DELETE /api/tasks/finished`

用途：

- 清理任务中心里的已完成终态任务

## 9. Tasks WebSocket

### `GET ws://127.0.0.1:18080/api/ws/tasks?token=...`

用途：

- 实时接收任务中心快照更新
- 用于替代前端轮询 `GET /api/tasks`

鉴权方式：

- 推荐：query 参数 `token`
- 兼容：请求头 `X-SSHFerry-Token`

消息格式 1：任务快照

```json
{
  "type": "task_snapshot",
  "items": [
    {
      "task_id": "uuid",
      "kind": "file_transfer",
      "engine": "scp",
      "status": "pending",
      "src": "E:\\SSHFerry\\workspace\\a.txt",
      "dst": "/remote/a.txt",
      "src_endpoint_type": "local",
      "dst_endpoint_type": "remote",
      "src_session_id": null,
      "dst_session_id": "session-1",
      "src_display_name": null,
      "dst_display_name": "demo",
      "src_label": "local:E:\\SSHFerry\\workspace\\a.txt",
      "dst_label": "demo:/remote/a.txt",
      "bytes_total": 12,
      "bytes_done": 0,
      "progress_percent": 0.0,
      "speed": 0.0,
      "retries": 0,
      "error_code": null,
      "error_message": null,
      "start_time": null,
      "end_time": null,
      "interrupted": false,
      "paused": false,
      "skipped": false,
      "subtask_count": 0,
      "subtask_done": 0,
      "current_file": "",
      "is_finished": false
    }
  ],
  "total": 1
}
```

消息格式 2：错误

```json
{
  "type": "error",
  "detail": "Task scheduler unavailable"
}
```

说明：

- 当前实现按任务快照变化推送，不是逐条事件流
- 初次连接后会立即推一帧当前快照
- 后续只有快照内容变化时才继续推送
- 当前推送粒度是轮询式快照刷新，适合第一版任务中心

## 10. Frontend Integration Order

建议前端按这个顺序接：

1. `GET /api/health`
2. `GET /api/auth/session`
3. 初始化全局请求头 `X-SSHFerry-Token`
4. 建立 `ws://127.0.0.1:18080/api/ws/tasks?token=...`
5. `GET /api/sites`
6. `POST /api/sessions/open`
7. `GET /api/local-files/drives`
8. `GET /api/local-files/list`
9. `GET /api/remote-files/list`
10. `POST /api/tasks/upload`
11. `POST /api/tasks/download`
12. `POST /api/tasks/remote-copy`
13. `POST /api/tasks/{task_id}/pause`
14. `POST /api/tasks/{task_id}/resume`
15. `POST /api/tasks/{task_id}/cancel`
16. `POST /api/tasks/{task_id}/restart`
17. `DELETE /api/tasks/finished`

## 11. Current Limitations

当前阶段还没有这些接口：

- 任务日志流接口
- 后端统一事件流接口
- 细粒度任务事件类型（目前只有快照）

当前前端建议：

- 任务中心优先使用 websocket
- 如果 websocket 断开，再回退轮询 `GET /api/tasks`

