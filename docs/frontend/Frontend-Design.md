# SSHFerry Frontend Design Specification

## Purpose

这份文档不是通用审美提示词，而是 SSHFerry 前端的产品与交互规格。

目标：

- 让 React 前端在产品语义上对齐当前桌面版
- 明确 Phase 1 的信息架构、交互规则、状态反馈和视觉方向
- 减少“接口接通了，但产品已经变味”的情况

适用范围：

- 工作区布局
- 站点管理
- 本地与远端文件浏览
- 拖拽创建任务
- 任务中心与日志区预留
- Phase 1 的视觉语言与可用性基线

## Product Positioning

SSHFerry 不是营销型 SaaS 仪表盘，也不是一个“上传按钮壳”。它是一个偏开发者和运维使用场景的本地桌面化传输工作台。

应该传达出的感受：

- 稳定
- 工具感强
- 信息密度高但不乱
- 适合长时间停留与重复操作
- 任务状态清楚，不依赖花哨动画理解系统状态

不应该做成：

- 首页风格的卡片堆叠
- 只有单远端视图的网页文件管理器
- 过分轻盈、空白极多、靠大色块撑视觉的界面
- 为了“现代”牺牲文件管理和任务可视化效率的布局

## Visual Direction

### Theme Direction

第一阶段建议采用“工业化桌面工具”方向，而不是夸张的实验视觉。

关键词：

- industrial utilitarian
- calm but dense
- light-neutral workspace
- sharp status accents
- monospaced path details

### Color Strategy

推荐浅色主界面，避免紫色渐变和默认 SaaS 配色。

建议色板：

- 背景：偏暖浅灰或浅米色
- 面板：略亮于背景，带明确分隔线
- 主强调色：偏钢蓝或深青蓝
- 次强调色：橙色用于拖拽热点、待处理和提醒
- 成功：深绿色
- 失败：砖红色
- 警告：土黄色或琥珀色
- 文本：深灰，不用纯黑

Phase 1 不要求支持深色主题，但要确保后续可以扩展。

### Typography

不要使用 `Arial`、`Inter`、`Roboto`、系统默认无衬线作为唯一选择。

建议：

- 正文：`IBM Plex Sans` 或同类中性、专业、略带工具气质的字体
- 路径、session id、任务标签：`IBM Plex Mono` 或同类等宽字体
- 不需要展示型标题字体；这是工具，不是品牌官网

### Motion

动效要服务于结构理解，而不是装饰。

只建议保留这些动效：

- 启动页进入工作区的轻量过渡
- pane 新开/关闭时的短时过渡
- 底部任务区展开/折叠
- 拖拽进入合法目标时的高亮反馈
- websocket 连接状态的轻量提示变化

不要做这些：

- 大面积浮夸渐变流动
- 无意义的按钮弹跳
- 大量微动效让文件列表显得不稳

## Information Architecture

Phase 1 以单窗口工作区为核心，不拆成很多页面。

主结构如下：

1. 顶部状态区
   - 应用名
   - 后端连接状态
   - websocket 状态
   - 全局任务协议覆盖器
2. 左侧站点侧栏
   - 站点列表
   - 站点操作按钮
   - 会话入口
3. 中间本地文件面板
4. 右侧多远端 session 工作区
5. 底部任务中心
6. 底部右侧预留日志区或日志标签位

`/tasks` 路由只是任务中心的放大视图，不是另一套产品结构。

## Wireframes

### Workspace

```text
+------------------------------------------------------------------------------------------------+
| SSHFerry | Backend: Ready | Task WS: Connected | Protocol Override: [ Auto v ]                 |
+------------------------------------------------------------------------------------------------+
| Sites / Sessions | Local Panel                         | Remote Pane A | Remote Pane B         |
|------------------|-------------------------------------|---------------|-----------------------|
| [Add] [Edit]     | [Drive v] [ Path................ ]  | [demo] [..]   | [gpu-box] [..]        |
| [Remove] [Check] | [..] [Refresh] [New Folder? no ]    | [Refresh]     | [Refresh]             |
| [Open] [Close]   |-------------------------------------|---------------|-----------------------|
| Sites list       | local file table                    | remote table   | remote table          |
| - demo           |                                     |                |                       |
| - gpu-box        |                                     |                |                       |
+------------------------------------------------------------------------------------------------+
| Task Center [expanded/collapsed] | Summary | Running | Failed | [Clear Finished] [Open Tasks Page] |
|------------------------------------------------------------------------------------------------|
| task table with progress / speed / status / action buttons                                     |
+------------------------------------------------------------------------------------------------+
| Log Area placeholder                                                                            |
+------------------------------------------------------------------------------------------------+
```

### Site Editor

```text
+--------------------------------------------------------------------------------+
| Site Editor                                                                    |
|--------------------------------------------------------------------------------|
| Site Name               [________________________]                             |
| Host                    [________________________]  Port [____]                |
| Username                [________________________]                             |
| Remote Root             [________________________]                             |
| Default Protocol        [ sftp v ]                                             |
| Auth Method             [ password v ]                                         |
| Password / Key fields   [________________________]                             |
| Remember Password       [ ]                                                    |
|--------------------------------------------------------------------------------|
| Quick Import from SSH Command                                                  |
| [ ssh -p 16921 root@example.com______________________________ ] [Parse]        |
|--------------------------------------------------------------------------------|
| Advanced                                                                    [v]|
| Proxy Jump              [________________________]                             |
| SSH Config Path         [________________________]                             |
| SSH Options             [________________________]                             |
|--------------------------------------------------------------------------------|
|                                             [Cancel] [Save]                    |
+--------------------------------------------------------------------------------+
```

### Tasks Page

```text
+------------------------------------------------------------------------------------------------+
| Task Summary | Total 12 | Running 2 | Pending 3 | Failed 1 | Done 6                           |
+------------------------------------------------------------------------------------------------+
| Filters / Sort / Search placeholder                                                             |
+------------------------------------------------------------------------------------------------+
| task table                                                                                      |
| name | direction | engine | progress | speed | status | current file | actions               |
+------------------------------------------------------------------------------------------------+
```

## Layout Rules

### Left Sidebar

左侧栏不是装饰，而是主操作区。

必须承载：

- 站点列表
- 当前选中站点详情摘要
- `Add/Edit/Remove Site`
- `Check Connection`
- `Open Session`
- `Close Session`
- 全局协议覆盖器

规则：

- 站点列表和会话列表可以分区显示，但仍放在同一侧栏
- `Open Session` 面向站点
- `Close Session` 面向已打开的 session
- 同一个站点允许打开多个 session
- 删除站点前要明确提示“会关闭引用该站点的当前会话”

### Local Panel

本地面板必须保留“文件浏览器”语义。

必须包含：

- 盘符切换
- 路径输入框
- `..` 返回上级
- `Refresh`
- 多选列表
- 拖拽来源能力
- 拖拽目标能力，接收远端下载

规则：

- 双击目录进入目录
- 双击文件默认不做预览，保持聚焦在传输工作流
- 列表按“目录优先、名称排序”展示
- 当前路径变化后应清空旧选中项
- 如果路径不可访问，要在面板内给出明确错误态，而不是全局 toast 一闪而过

### Remote Workspace

远端区域必须体现“多 session 并排工作”的核心价值。

规则：

- 打开第一个 session 时，显示一个远端 pane
- 再打开 session 时，默认追加到右侧，形成多列布局
- 每个 pane 有自己的当前路径、选中项、刷新按钮和关闭按钮
- 每个 pane 的标题里必须能看见 `site_name`
- 每个 pane 都要能清楚识别对应 `session_id` 或其缩略标识
- 没有任何打开 session 时，远端区域显示空状态，提示从左侧打开站点
- session 失效时，该 pane 进入 stale 状态，不要静默消失

建议但不强制：

- pane 宽度可拖动调整
- pane 标题区支持切换到另一个已打开 session

### Task Center

任务中心必须始终可达，不能藏得太深。

规则：

- 工作区底部默认显示一个可折叠任务区
- `/tasks` 页面复用相同数据与操作逻辑，只是更宽更适合排查
- 默认排序优先级建议：`running` > `pending` > `paused` > `failed` > `canceled` > `skipped` > `done`
- 目录任务必须展示总进度和 `current_file`
- 任务失败时，错误信息要能展开查看

### Log Area

第一阶段可以不做完整日志能力，但布局上必须预留。

建议：

- 放在任务区右侧标签页或折叠区域
- 以“预留中”状态存在，而不是完全删掉

## Site Editor Specification

### Required Fields

站点编辑器至少覆盖这些字段：

- `Site Name`
- `Host`
- `Port`
- `Username`
- `Remote Root`
- `Default Transfer Protocol`
- `Auth Method`
- `Password`
- `Key Path`
- `Key Passphrase`
- `Remember Password`
- `Proxy Jump`
- `SSH Config Path`
- `SSH Options`

### Auth Field Switching

规则：

- 当 `Auth Method=password` 时，显示 `Password` 与 `Remember Password`
- 当 `Auth Method=key` 时，显示 `Key Path` 与 `Key Passphrase`
- 切换认证方式时，不要偷偷提交另一种认证方式的旧值
- 编辑已有站点时，如果后端只返回 `has_password=true` 而没有明文密码，密码框默认留空，旁边可提示“已保存密码”

### Quick Import from SSH Command

前端本地解析规则，直接对齐当前桌面版实现，不额外发明新语法。

支持范围：

- 只承诺支持这种基本格式：`ssh [-p PORT] [USER@]HOST`
- 示例：`ssh -p 16921 root@connect.westb.seetacloud.com`

不承诺支持：

- `-i`
- `-J`
- `-o`
- 复杂 quoting
- 在命令后追加远端命令
- 多段 SSH 配置推导

解析行为：

- 能匹配到 `port` 就填 `Port`
- 能匹配到 `username` 就填 `Username`
- 能匹配到 `host` 就填 `Host`
- 如果 `Site Name` 当前为空，则用 `host` 的第一个点前片段作为默认名字
- 如果无法匹配，保持原表单不变，并显示“当前只支持基础 SSH 命令格式”的提示

这条规则要和实现保持一致，不要在文档里把能力写大。

## Drag And Drop Contract

拖拽是核心能力，必须写死规则。

### Local -> Remote

来源：

- 本地面板选中条目

目标：

- 某个远端 pane 的目录行
- 某个远端 pane 的空白区域，表示当前目录

行为：

- 每个顶层选中条目创建一个上传任务
- 目标是目录行时，使用该目录作为目标目录
- 目标是 pane 空白区域时，使用 pane 当前目录作为目标目录
- 如果选中的是目录，创建一个 `folder_transfer` 任务
- 如果选中的是文件，创建一个文件任务

### Remote -> Local

来源：

- 某个远端 pane 的选中条目

目标：

- 本地面板目录行
- 本地面板空白区域，表示当前目录

行为：

- 每个顶层选中条目创建一个下载任务
- 目标是目录行时，使用该目录作为本地目标目录
- 目标是本地面板空白区域时，使用本地当前目录

### Remote -> Remote

来源：

- 远端 pane A 的选中条目

目标：

- 远端 pane B 的目录行
- 远端 pane B 的空白区域，表示其当前目录

行为：

- 每个顶层选中条目创建一个远端互传任务
- 目标 pane 必须明确对应一个 `dst_session_id`
- 第一阶段只保证跨 pane 远端互传，不要求同 pane 拖拽实现“远端移动”

### Invalid Drops

这些情况视为非法拖拽：

- 拖到不是目录也不是 pane 背景的区域
- 没有明确目标 session 的远端区域
- session 已失效的 pane
- 本地或远端当前没有任何选中项

处理规则：

- 光标显示为不可放置
- 不触发任何请求
- 不要做静默失败后又莫名创建任务

### Protocol Resolution During Drag

拖拽创建任务时协议选择规则固定为：

- 全局覆盖器为 `Auto` 时，请求体传 `engine='auto'`
- 全局覆盖器为 `SFTP` 时，请求体传 `engine='sftp'`
- 全局覆盖器为 `SCP` 时，请求体传 `engine='scp'`
- 最终展示以后端回传的 `task.engine` 为准

### Conflict Handling In Phase 1

第一阶段没有客户端覆盖策略向导。

规则：

- 不做上传前覆盖检查弹窗
- 如果后端或传输引擎报错，直接让任务进入失败态
- UI 负责把失败原因展示清楚

## Destructive Action Rules

下面这些操作必须确认：

- 删除站点
- 删除远端文件
- 删除远端目录
- 关闭仍有活动任务关联的 pane 或 session

确认文案最低要求：

- 清楚写出对象名称
- 删除目录时显示完整路径
- 删除站点时说明会影响哪些 session
- 不要只写“Are you sure?” 这种空洞文案

## State And Feedback Specification

### Startup States

- `health` 未通过：显示全屏后端未就绪页，含重试按钮
- `auth/session` 获取失败：显示全屏初始化失败页，不要进入半残工作区
- 初始化成功但站点为空：显示空状态，引导创建第一个站点

### Panel States

每个文件面板至少要支持：

- loading
- empty directory
- permission denied
- path not found
- generic request error
- stale session

规则：

- 面板错误优先在面板内部展示
- 不要只靠 toast 表达目录加载失败
- stale session 需要给出“重新打开会话”或“关闭 pane”的明确动作

### Task States

任务区至少要体现：

- websocket 已连接
- websocket 正在重连
- 已退回轮询
- 任务失败可查看详情
- 没有任务时的空状态

### Toast Strategy

toast 只用于短消息：

- 创建成功
- 控制动作成功
- 轻量错误提醒

这些不要只用 toast：

- 目录加载失败
- 会话失效
- 连接检查结果
- 任务失败详情

## Accessibility And Interaction Baseline

第一阶段至少做到这些：

- 所有可点击控件都有清晰 focus state
- 表格和列表支持键盘选中
- `Enter` 可进入目录
- `Delete` 只在已有确认流时触发删除入口
- 颜色不是唯一状态来源，状态文本必须同时存在
- 关键状态颜色对比足够

## Phase 1 Non-Goals

第一阶段明确不做这些：

- 本地文件的后端写操作 API 扩展
- 复杂覆盖策略向导
- 高级搜索、过滤和批量规则引擎
- 完整日志系统
- 深色主题与多主题系统
- 花哨品牌动效

## Design Review Checklist

一个页面如果通过不了下面这些检查，就说明偏了：

- 是否还能一眼看出“左站点、中本地、右多远端、下任务”的工作结构
- 是否保留了多远端并排这件最核心的产品语义
- 是否保留了文件浏览器而不是退化成上传下载按钮集合
- 是否让任务状态、失败原因和当前传输对象足够清楚
- 是否让破坏性操作都有明确确认
- 是否把视觉重点放在信息可读性而不是装饰上
