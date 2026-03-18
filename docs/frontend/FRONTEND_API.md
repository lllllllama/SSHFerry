# SSHFerry Frontend API Guide

## Purpose

这份文档专门给前端开发使用。

开始前端开发前，配合阅读：

- [FRONTEND_BUILD.md](./FRONTEND_BUILD.md)
- [Frontend-Design.md](./Frontend-Design.md)

目标：

- 说明当前本地 FastAPI 后端已经提供的接口
- 固定请求参数和响应字段
- 说明鉴权、跨域、错误和状态约定
- 作为 React 前端对接基线

当前接口前缀统一为：

```text
/api
```

## Runtime Baseline

- 后端运行在用户本机
- 默认 HTTP 地址：`http://127.0.0.1:18080`
- 默认 WebSocket 地址：`ws://127.0.0.1:18080`
- 默认允许本地前端开发源：`localhost:5173`、`127.0.0.1:5173`、`localhost:4173`、`127.0.0.1:4173`、`localhost:3000`、`127.0.0.1:3000`
- 打包后如果前端以 `file://` 或本地壳运行，浏览器 `Origin` 可能为 `null`，当前后端已允许

## General Rules

### Response Style

- 成功时返回 `200`、`201` 或 `204`
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

### Shared Value Conventions

- 时间字段使用 Unix 时间戳秒值，类型为 `number`
- 文件大小、传输字节数使用整数，单位为字节
- `session_id` 是后端内存态会话 ID，不是持久 SSH 连接 ID
- `engine` 可能出现：`auto`、`sftp`、`scp`、`parallel`
- 任务 `status` 当前会出现：`pending`、`running`、`paused`、`done`、`failed`、`canceled`、`skipped`
- 列表接口统一返回 `{ items, total }` 包装结构

## 1. Health

### `GET /api/health`

用途：

- 检查后端是否启动
- 检查核心服务是否可用
- 告知前端鉴权请求头名称

鉴权：

- 不需要 token

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

前端处理建议：

- `ready=false` 时不要继续打业务接口
- `startup_error` 不为空时，在启动页直接展示
- `auth_header_name` 目前固定为 `X-SSHFerry-Token`，前端仍按返回值初始化

## 2. Auth

### `GET /api/auth/session`

用途：

- 获取当前本地后端会话 token
- 供 React 前端初始化请求客户端时使用

鉴权：

- 不需要 token

响应示例：

```json
{
  "token": "random-token",
  "header_name": "X-SSHFerry-Token",
  "token_type": "local"
}
```

前端规则：

- 启动时调用一次即可
- 将 `token` 放进后续所有 REST 请求头
- 将 `token` 作为 websocket query 参数传给实时接口

## 3. Sites

### Shared Request Shape: `SiteUpsertRequest`

`POST /api/sites` 和 `PUT /api/sites/{site_name}` 使用同一套请求体：

```json
{
  "name": "demo",
  "host": "connect.westb.seetacloud.com",
  "port": 16921,
  "username": "root",
  "auth_method": "password",
  "remote_root": "/root/autodl-tmp",
  "password": "secret",
  "key_path": null,
  "key_passphrase": null,
  "remember_password": false,
  "proxy_jump": null,
  "ssh_config_path": null,
  "ssh_options": [],
  "default_transfer_protocol": "sftp"
}
```

字段说明：

- `auth_method` 固定为 `password` 或 `key`
- `default_transfer_protocol` 固定为 `sftp` 或 `scp`
- `password` 只在 `auth_method=password` 时有意义
- `key_path`、`key_passphrase` 只在 `auth_method=key` 时有意义
- `remember_password=true` 才表示允许后端持久保存密码
- `proxy_jump`、`ssh_config_path`、`ssh_options` 当前后端已支持存储，前端表单不要删掉
- 当前没有单独的“SSH 命令快速导入”接口，这个能力需要前端本地解析后再填表

### Shared Response Shape: `SiteResponse`

```json
{
  "name": "demo",
  "host": "connect.westb.seetacloud.com",
  "port": 16921,
  "username": "root",
  "auth_method": "password",
  "remote_root": "/root/autodl-tmp",
  "key_path": null,
  "remember_password": false,
  "proxy_jump": null,
  "ssh_config_path": null,
  "ssh_options": [],
  "default_transfer_protocol": "sftp",
  "has_password": false
}
```

字段说明：

- 响应里不会返回明文 `password`
- `has_password=true` 仅表示后端当前已持久保存可用密码
- 编辑站点时，如果 `has_password=false`，前端密码输入框默认应为空

### `GET /api/sites`

用途：

- 获取站点列表

响应示例：

```json
{
  "items": [
    {
      "name": "demo",
      "host": "connect.westb.seetacloud.com",
      "port": 16921,
      "username": "root",
      "auth_method": "password",
      "remote_root": "/root/autodl-tmp",
      "key_path": null,
      "remember_password": false,
      "proxy_jump": null,
      "ssh_config_path": null,
      "ssh_options": [],
      "default_transfer_protocol": "sftp",
      "has_password": false
    }
  ],
  "total": 1
}
```

### `POST /api/sites`

用途：

- 新建站点

成功响应：

- `201 Created`
- 返回 `SiteResponse`

常见失败：

- `409 Conflict`：站点名已存在

### `PUT /api/sites/{site_name}`

用途：

- 更新已有站点
- 允许改名，改名后的最终名字以后端请求体 `name` 为准

成功响应：

- `200 OK`
- 返回 `SiteResponse`

常见失败：

- `404 Not Found`：路径参数里的原站点不存在
- `409 Conflict`：请求体里的新站点名与其他站点冲突

### `DELETE /api/sites/{site_name}`

用途：

- 删除站点
- 会同时清理引用该站点的内存 session

成功响应：

- `204 No Content`

前端注意：

- 删除前应二次确认
- 如果当前 UI 里有依赖该站点的打开会话，需要同步关闭对应 pane

## 4. Connections

### Shared Request Shape: `ConnectionCheckRequest`

```json
{
  "site_name": "demo",
  "password": "secret",
  "key_passphrase": null
}
```

字段说明：

- `site_name` 必填
- `password` 用于覆盖站点里未保存的密码
- `key_passphrase` 用于覆盖站点里未保存的私钥口令

### `POST /api/connections/check`

用途：

- 对指定站点执行连接自检

成功响应示例：

```json
{
  "site_name": "demo",
  "all_passed": true,
  "results": [
    {
      "name": "tcp_connect",
      "passed": true,
      "message": "TCP connection established"
    },
    {
      "name": "sftp_listdir",
      "passed": true,
      "message": "Remote root is readable"
    }
  ]
}
```

前端处理建议：

- 连接检查结果要按 `results[]` 原样展示，不要只展示 `all_passed`
- `auth_method=password` 且站点没有保存密码时，前端应先收集运行时密码再调用
- `auth_method=key` 且未提供 `key_path` 时，后端会拒绝

常见失败：

- `400 Bad Request`：缺少运行时密码或缺少 `key_path`
- `404 Not Found`：站点不存在
- `503 Service Unavailable`：依赖缺失，当前机器无法执行连接检查

## 5. Sessions

### Shared Response Shape: `SessionResponse`

```json
{
  "session_id": "9fdd0dfd-784c-4eab-bb47-8e07fa538f8b",
  "site_name": "demo",
  "host": "connect.westb.seetacloud.com",
  "port": 16921,
  "username": "root",
  "auth_method": "password",
  "remote_root": "/root/autodl-tmp",
  "has_password": false
}
```

字段说明：

- `session_id` 表示一个远端会话上下文
- 页面刷新后如果后端进程还在，`session_id` 仍有效
- 后端重启后，`session_id` 会全部失效

### `GET /api/sessions`

用途：

- 获取当前活动远端会话列表

响应示例：

```json
{
  "items": [
    {
      "session_id": "9fdd0dfd-784c-4eab-bb47-8e07fa538f8b",
      "site_name": "demo",
      "host": "connect.westb.seetacloud.com",
      "port": 16921,
      "username": "root",
      "auth_method": "password",
      "remote_root": "/root/autodl-tmp",
      "has_password": false
    }
  ],
  "total": 1
}
```

### `POST /api/sessions/open`

用途：

- 创建一个远端会话上下文

请求体：

```json
{
  "site_name": "demo",
  "password": "secret",
  "key_passphrase": null
}
```

成功响应：

- `201 Created`
- 返回 `SessionResponse`

前端注意：

- 前端应允许同一个站点被多次打开为多个独立 `session_id`
- `remote_root` 最终以后端返回值为准

### `POST /api/sessions/close`

用途：

- 关闭远端会话上下文

请求体：

```json
{
  "session_id": "9fdd0dfd-784c-4eab-bb47-8e07fa538f8b"
}
```

成功响应：

- `204 No Content`

常见失败：

- `404 Not Found`：会话不存在

## 6. Local Files

### `GET /api/local-files/drives`

用途：

- 获取本地盘符或根目录入口

响应示例：

```json
{
  "items": [
    {
      "path": "C:/",
      "label": "C:"
    },
    {
      "path": "D:/",
      "label": "D:"
    }
  ],
  "total": 2
}
```

### `GET /api/local-files/list?path=...`

用途：

- 获取本地目录列表

请求示例：

```text
GET /api/local-files/list?path=E:\SSHFerry
```

成功响应示例：

```json
{
  "current_path": "E:\\SSHFerry",
  "parent_path": "E:\\",
  "items": [
    {
      "name": "backend",
      "path": "E:\\SSHFerry\\backend",
      "is_dir": true,
      "size": 0,
      "mtime": 1710742585.0,
      "exists": true
    },
    {
      "name": "README.md",
      "path": "E:\\SSHFerry\\README.md",
      "is_dir": false,
      "size": 2048,
      "mtime": 1710742585.0,
      "exists": true
    }
  ],
  "total": 2
}
```

前端注意：

- `path` 必填且不能为空白
- 返回项已按“目录优先、名称升序”排好
- 本地文件 API 当前只负责浏览和读取元信息，不负责本地删除、重命名、创建目录

常见失败：

- `400 Bad Request`：`path` 为空或不是目录
- `403 Forbidden`：没有访问权限
- `404 Not Found`：路径不存在

### `GET /api/local-files/stat?path=...`

用途：

- 获取本地路径详情

响应示例：

```json
{
  "entry": {
    "name": "README.md",
    "path": "E:\\SSHFerry\\README.md",
    "is_dir": false,
    "size": 2048,
    "mtime": 1710742585.0,
    "exists": true
  }
}
```

## 7. Remote Files

### Shared Response Shape: `RemoteEntryResponse`

```json
{
  "name": "dataset",
  "path": "/root/autodl-tmp/dataset",
  "is_dir": true,
  "size": 0,
  "mtime": 1710742585.0,
  "mode": 16877
}
```

### `GET /api/remote-files/list?session_id=...&path=...`

用途：

- 获取远端目录列表

请求规则：

- `session_id` 必填
- `path` 可省略
- `path` 省略或传空白时，后端按当前 session 的 `remote_root` 列目录

成功响应示例：

```json
{
  "session_id": "9fdd0dfd-784c-4eab-bb47-8e07fa538f8b",
  "current_path": "/root/autodl-tmp",
  "parent_path": "/root",
  "items": [
    {
      "name": "dataset",
      "path": "/root/autodl-tmp/dataset",
      "is_dir": true,
      "size": 0,
      "mtime": 1710742585.0,
      "mode": 16877
    }
  ],
  "total": 1
}
```

前端注意：

- 返回项已按“目录优先、名称升序”排好
- `current_path` 以后端返回值为准，不要自己拼
- `parent_path=null` 时表示已经没有可回退上级

### `GET /api/remote-files/stat?session_id=...&path=...`

用途：

- 获取远端文件或目录详情

响应示例：

```json
{
  "entry": {
    "name": "a.txt",
    "path": "/root/autodl-tmp/a.txt",
    "is_dir": false,
    "size": 12,
    "mtime": 1710742585.0,
    "mode": 33188
  }
}
```

### `POST /api/remote-files/mkdir`

用途：

- 新建远端目录

请求体：

```json
{
  "session_id": "9fdd0dfd-784c-4eab-bb47-8e07fa538f8b",
  "path": "/root/autodl-tmp/new-dir"
}
```

成功响应：

- `204 No Content`

### `POST /api/remote-files/rename`

用途：

- 重命名或移动远端文件/目录

请求体：

```json
{
  "session_id": "9fdd0dfd-784c-4eab-bb47-8e07fa538f8b",
  "old_path": "/root/autodl-tmp/a.txt",
  "new_path": "/root/autodl-tmp/b.txt"
}
```

成功响应：

- `204 No Content`

### `POST /api/remote-files/delete`

用途：

- 删除远端文件或目录

请求体：

```json
{
  "session_id": "9fdd0dfd-784c-4eab-bb47-8e07fa538f8b",
  "path": "/root/autodl-tmp/dataset",
  "recursive": true
}
```

字段说明：

- `recursive` 默认就是 `true`
- 删除目录时，前端应先二次确认

成功响应：

- `204 No Content`

常见失败：

- `400 Bad Request`：远端路径为空白
- `404 Not Found`：session 不存在或远端路径不存在
- `503 Service Unavailable`：远端依赖缺失

## 8. Tasks REST

### Shared Response Shape: `TaskResponse`

`GET /api/tasks`、任务创建接口和 websocket 快照里的任务项使用同一套字段：

```json
{
  "task_id": "uuid",
  "kind": "file_transfer",
  "engine": "scp",
  "status": "pending",
  "src": "E:\\SSHFerry\\workspace\\a.txt",
  "dst": "/root/autodl-tmp/a.txt",
  "src_endpoint_type": "local",
  "dst_endpoint_type": "remote",
  "src_session_id": null,
  "dst_session_id": "session-1",
  "src_display_name": null,
  "dst_display_name": "demo",
  "src_label": "local:E:\\SSHFerry\\workspace\\a.txt",
  "dst_label": "demo:/root/autodl-tmp/a.txt",
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
```

字段说明：

- `kind` 当前主要会出现 `file_transfer` 或 `folder_transfer`
- `engine` 是后端最终采用的引擎，不一定等于前端请求时提交的值
- `src_label`、`dst_label` 可直接用于 UI 展示
- 目录任务通过 `subtask_count`、`subtask_done`、`current_file` 展示聚合进度

### Shared Request Shape: Upload

```json
{
  "session_id": "dst-session",
  "local_path": "E:\\SSHFerry\\workspace\\a.txt",
  "remote_path": "/root/autodl-tmp/a.txt",
  "engine": "auto"
}
```

### Shared Request Shape: Download

```json
{
  "session_id": "src-session",
  "remote_path": "/root/autodl-tmp/a.txt",
  "local_path": "E:\\SSHFerry\\downloads\\a.txt",
  "engine": "auto"
}
```

### Shared Request Shape: Remote Copy

```json
{
  "src_session_id": "src-session",
  "dst_session_id": "dst-session",
  "src_path": "/root/autodl-tmp/a.txt",
  "dst_path": "/root/autodl-tmp-copy/a.txt",
  "engine": "auto"
}
```

### Shared Response Shape: `TaskActionResponse`

```json
{
  "task_id": "uuid",
  "action": "pause",
  "status": "paused"
}
```

### `GET /api/tasks`

用途：

- 获取当前任务列表

响应示例：

```json
{
  "items": [
    {
      "task_id": "uuid",
      "kind": "file_transfer",
      "engine": "scp",
      "status": "pending",
      "src": "E:\\SSHFerry\\workspace\\a.txt",
      "dst": "/root/autodl-tmp/a.txt",
      "src_endpoint_type": "local",
      "dst_endpoint_type": "remote",
      "src_session_id": null,
      "dst_session_id": "session-1",
      "src_display_name": null,
      "dst_display_name": "demo",
      "src_label": "local:E:\\SSHFerry\\workspace\\a.txt",
      "dst_label": "demo:/root/autodl-tmp/a.txt",
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

说明：

- 当前返回全量任务快照
- 如果前端还没接 websocket，可以继续轮询这个接口

### `POST /api/tasks/upload`

用途：

- 创建本地到远端的上传任务

成功响应：

- `201 Created`
- 返回 `TaskResponse`

前端注意：

- 如果本地源是目录，后端会创建 `kind=folder_transfer`
- 目录上传当前固定走 `engine=sftp`
- 文件上传时，如果传 `engine=auto`，后端会按站点默认协议和文件大小决定最终引擎

### `POST /api/tasks/download`

用途：

- 创建远端到本地的下载任务

成功响应：

- `201 Created`
- 返回 `TaskResponse`

前端注意：

- 如果远端源是目录，后端会创建 `kind=folder_transfer`
- 目录下载当前固定走 `engine=sftp`

### `POST /api/tasks/remote-copy`

用途：

- 创建远端到远端传输任务

成功响应：

- `201 Created`
- 返回 `TaskResponse`

前端注意：

- 如果源是目录，当前固定走 `engine=sftp`
- 文件远端互传时，`engine=auto` 会回退为 `sftp`

### `POST /api/tasks/{task_id}/pause`

用途：

- 请求暂停一个运行中任务

成功响应：

- `200 OK`
- 返回 `TaskActionResponse`

### `POST /api/tasks/{task_id}/resume`

用途：

- 恢复一个已暂停任务

### `POST /api/tasks/{task_id}/cancel`

用途：

- 取消一个任务

### `POST /api/tasks/{task_id}/restart`

用途：

- 重启一个终态任务

任务控制接口通用规则：

- 成功时返回 `TaskActionResponse`
- `404 Not Found`：任务不存在
- `409 Conflict`：当前状态不允许执行该动作

### `DELETE /api/tasks/finished`

用途：

- 清理任务中心里的已完成终态任务

成功响应：

- `204 No Content`

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
      "dst": "/root/autodl-tmp/a.txt",
      "src_endpoint_type": "local",
      "dst_endpoint_type": "remote",
      "src_session_id": null,
      "dst_session_id": "session-1",
      "src_display_name": null,
      "dst_display_name": "demo",
      "src_label": "local:E:\\SSHFerry\\workspace\\a.txt",
      "dst_label": "demo:/root/autodl-tmp/a.txt",
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
- 当前推送粒度是快照刷新，前端不要假设存在 `task_added`、`task_finished` 这类事件名

## 10. Recommended Frontend Integration Order

建议前端按这个顺序接：

1. `GET /api/health`
2. `GET /api/auth/session`
3. 初始化全局请求头 `X-SSHFerry-Token`
4. 建立 `ws://127.0.0.1:18080/api/ws/tasks?token=...`
5. `GET /api/sites`
6. `GET /api/sessions`
7. `GET /api/local-files/drives`
8. `GET /api/local-files/list`
9. `POST /api/sessions/open`
10. `GET /api/remote-files/list`
11. `POST /api/tasks/upload`
12. `POST /api/tasks/download`
13. `POST /api/tasks/remote-copy`
14. `POST /api/tasks/{task_id}/pause`
15. `POST /api/tasks/{task_id}/resume`
16. `POST /api/tasks/{task_id}/cancel`
17. `POST /api/tasks/{task_id}/restart`
18. `DELETE /api/tasks/finished`

## 11. Current Backend Gaps

当前阶段还没有这些接口：

- 任务日志流接口
- 后端统一事件流接口
- 细粒度任务事件类型
- SSH 命令快速导入接口
- 传输冲突预检或覆盖策略协商接口
- 任务过滤、分页、搜索接口

当前前端建议：

- 任务中心优先使用 websocket
- websocket 断开时回退轮询 `GET /api/tasks`
- SSH 命令快速导入放在前端本地实现
- 文件名冲突、权限问题等第一阶段先按后端返回错误或任务失败状态展示
