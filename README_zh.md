<p align="center">
  <img src="docs/assets/logo.png" alt="SSHFerry 标识" width="220" />
</p>

# SSHFerry

<div align="center">
  <p>
    <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+">
    <img src="https://img.shields.io/badge/Desktop-PySide6-0F172A?style=for-the-badge" alt="桌面端 PySide6">
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="后端 FastAPI">
    <img src="https://img.shields.io/badge/Frontend-React%20%2B%20Vite-2563EB?style=for-the-badge&logo=react&logoColor=white" alt="前端 React 和 Vite">
  </p>

  <h3>面向日常远程文件操作的本地优先 SSH 工作区，提供多会话传输控制、更安全的远端边界，以及可观察的任务流。</h3>

  <p>
    SSHFerry 把桌面文件浏览、传输调度、本地后端接口和 Web 前端放进同一个仓库，目标不是抽象掉远程操作，而是把它变得更集中、更可控。
  </p>

  <p>
    <b>中文</b> |
    <a href="README.md">English</a>
  </p>

  <p>
    <a href="#项目概览">项目概览</a> |
    <a href="#它的差异化在哪里">它的差异化在哪里</a> |
    <a href="#工作流">工作流</a> |
    <a href="#快速开始">快速开始</a> |
    <a href="#你能得到什么">你能得到什么</a> |
    <a href="#文档">文档</a>
  </p>
</div>

## 项目概览

`SSHFerry` 是一个 SSH 文件操作工作区，当前由三部分组成：

- 基于 Python + PySide6 的桌面客户端
- 提供站点、会话、任务、日志和工作区接口的本地 FastAPI 后端
- 围绕后端接口持续集成中的 React + Vite 前端

当前最推荐的入口仍然是桌面客户端。它已经覆盖了日常远程文件处理的主要流程：本地与远端浏览、上传、下载、远端互传、任务控制，以及通过 `remote_root` 提供更安全的操作边界。

## 它的差异化在哪里

SSHFerry 面向的是“终端命令太散、重量级工具又太重”的那段实际工作带。它不假设 SSH 文件操作会变简单，但会尽量让流程更集中、更可检查。

| 常见 SSH 文件工作流 | SSHFerry |
|---|---|
| 浏览、传输、重试依赖多个终端命令和零散工具 | 在同一个工作区里处理浏览、传输和任务观察 |
| 远端互传往往需要手动协调多个会话 | 直接支持本地到远端、远端到本地、远端到远端 |
| 命令一旦启动，传输状态不容易追踪 | 提供任务进度、暂停、继续、取消和重试控制 |
| 很容易误触不该操作的远端目录 | 通过 `remote_root` 限制远端操作边界 |
| 站点录入重复且容易出错 | 支持手动配置，也支持从 SSH 风格命令导入 |

### 当前产品形态

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🖥️ 桌面端优先</h3>
      <p>桌面客户端已经可用，并且仍然是当前日常文件操作的主入口。</p>
    </td>
    <td width="33%" valign="top">
      <h3>🧩 共享传输核心</h3>
      <p>后端不是重新实现一套逻辑，而是复用了同一套调度器和传输核心。</p>
    </td>
    <td width="33%" valign="top">
      <h3>🌐 Web 持续集成中</h3>
      <p>前端不是摆设型原型，代码已经在仓库中，并围绕真实后端接口持续推进。</p>
    </td>
  </tr>
</table>

## 工作流

SSHFerry 的组织方式不是一组分散命令，而是一条可观察的远程文件工作流：

1. 手动新增站点，或从 SSH 风格命令导入
2. 尽量把 `remote_root` 设置为专用目录
3. 先执行内置连接检查
4. 打开一个或多个远端会话
5. 在本地和远端面板之间并排浏览
6. 在面板之间传输文件，或直接进行远端互传
7. 在任务中心查看并控制整个过程

运行说明：

- 站点级协议默认支持 `sftp` 和 `scp`
- 窗口级覆盖可强制使用 `Auto`、`SFTP` 或 `SCP`
- 如果 `remote_root` 为空，操作会回退到 `/`

## 快速开始

### 环境要求

- Python `3.11+`
- Node.js `18+`，用于前端开发
- Windows、Linux 或 macOS

### 安装

```bash
pip install -r requirements.txt
```

前端依赖：

```bash
cd frontend
npm install
```

### 推荐运行方式：桌面客户端

Windows：

```powershell
./run.bat
```

Linux 或 macOS：

```bash
./run.sh
```

直接使用模块入口：

```bash
python -m src.app.main
```

### 其他运行方式

后端服务：

```bash
python -m backend.app.main
```

前端应用：

```bash
cd frontend
npm run dev
```

前端生产构建：

```bash
cd frontend
npm run build
```

常用后端环境变量：

- `SSHFERRY_BACKEND_HOST`，默认值：`127.0.0.1`
- `SSHFERRY_BACKEND_PORT`，默认值：`18080`
- `SSHFERRY_ALLOWED_ORIGINS`
- `SSHFERRY_LOCAL_TOKEN`

## 你能得到什么

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>传输工作区</h3>
      <ul>
        <li>在同一个界面管理多个远端站点</li>
        <li>本地与远端文件并排浏览</li>
        <li>支持上传、下载和远端会话之间复制</li>
        <li>按场景选择 `sftp`、`scp` 或并行传输路径</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>运行控制</h3>
      <ul>
        <li>不只看终端输出，还能直接观察任务状态</li>
        <li>支持暂停、继续、取消、重试和进度监控</li>
        <li>通过 `remote_root` 收窄远端操作范围</li>
        <li>支持从 SSH 风格命令导入站点信息</li>
      </ul>
    </td>
  </tr>
</table>

## 测试

运行当前完整的后端测试集：

```bash
pytest
```

当前 `pytest` 配置会输出后端覆盖率，并要求覆盖率阈值达到 `99`。

快速导入自检：

```bash
python -c "from src.shared.models import SiteConfig, Task; from src.core.scheduler import TaskScheduler; from src.services.connection_checker import ConnectionChecker; print('imports_ok')"
```

## 打包

当前 Windows 打包主要面向桌面客户端。

标准构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -VenvPath .venv_compat
```

Debug 构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -Debug -VenvPath .venv_compat
```

Release 构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -VenvPath .venv_compat
```

预期输出：

```text
release/SSHFerry-<version>-windows/
release/SSHFerry-<version>-windows.zip
release/SSHFerry-<version>-windows.sha256
```

<details>
<summary><b>仓库结构</b></summary>

```text
src/        桌面应用、传输引擎、调度器、共享模型
backend/    FastAPI 后端服务
frontend/   React + Vite 前端应用
docs/       维护中的实现与设计文档
tests/      Pytest 测试集
tools/      打包与基准测试脚本
```

</details>

## 文档

- [文档索引](docs/README_zh.md)
- [English Docs Index](docs/README.md)
- [后端总览](docs/backend/BACKEND_OVERVIEW_zh.md)
- [前端构建指南](docs/frontend/FRONTEND_BUILD_zh.md)
- [前端接口指南](docs/frontend/FRONTEND_API_zh.md)
- [前端设计指南](docs/frontend/FRONTEND_DESIGN_zh.md)
