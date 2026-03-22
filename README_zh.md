<p align="center">
  <img src="docs/assets/logo.png" alt="SSHFerry 标识" width="220" />
</p>

# SSHFerry

面向日常远程操作的多会话 SSH 文件传输工作区。

**中文** | [English](README.md)

## 🚀 项目概览

SSHFerry 是一个 SSH 文件操作项目，在同一仓库中同时包含桌面客户端、本地后端和 Web 前端。

当前最推荐的入口仍然是桌面客户端。它已经覆盖日常远程文件处理的主要流程，包括浏览、上传、下载、远端互传、任务控制，以及通过 `remote_root` 提供更安全的操作边界。

## 为什么选择 SSHFerry

很多 SSH 文件处理流程仍然依赖终端、零散脚本，以及彼此分离的浏览、传输和重试工具。

SSHFerry 试图把这些高频日常操作收拢到同一个工作区里，让远程文件工作更容易观察、更容易控制，也更不容易出错：

- 🗂️ 在同一个界面里处理本地与远端浏览
- 🎯 内置任务可视化与传输控制
- 🔗 支持把多个远端会话放进同一条工作流
- 🛡️ 通过 `remote_root` 提供更安全的远端操作边界
- ⚡ 面向实际使用场景支持 `sftp`、`scp` 和并行传输路径

## ✨ 亮点

- 🖥️ 桌面客户端：已经可用，当前推荐优先使用
- 🧩 后端服务：已经落地，并接入仓库中的传输逻辑
- 🌐 前端应用：代码已在仓库中，部分功能可用，仍在持续集成中
- 📁 在同一个工作区中管理多个远端站点
- ↔️ 本地与远端文件并排浏览
- 📤 支持上传、下载，以及远端面板之间的拖拽复制
- ⚙️ 根据场景使用 `sftp`、`scp` 或并行传输路径
- ⏯️ 支持暂停、继续、取消、重试和任务进度观察
- 🔒 使用 `remote_root` 限制远端操作范围
- 🧭 支持从 SSH 风格命令快速导入站点信息

## 🧱 组成部分

- 🖥️ 桌面客户端：基于 Python + PySide6 的日常文件操作入口
- 🧩 后端服务：提供站点、会话、任务、日志与工作区接口的 FastAPI 应用
- 🌐 前端应用：围绕后端接口持续集成的 React + Vite 界面

## 🗃️ 仓库结构

```text
src/        桌面应用、传输引擎、调度器、共享模型
backend/    FastAPI 后端服务
frontend/   React + Vite 前端应用
docs/       维护中的实现与设计文档
tests/      Pytest 测试集
tools/      打包与基准测试脚本
```

## 🚀 快速上手

### 📋 环境要求

- Python `3.11+`
- Node.js `18+`，用于前端开发
- Windows、Linux 或 macOS

### 🐍 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 📦 安装前端依赖

```bash
cd frontend
npm install
```

## ▶️ 运行方式

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

后端服务：

```bash
python -m backend.app.main
```

前端应用：

```bash
cd frontend
npm run dev
```

构建前端：

```bash
cd frontend
npm run build
```

常用后端环境变量：

- `SSHFERRY_BACKEND_HOST`，默认值：`127.0.0.1`
- `SSHFERRY_BACKEND_PORT`，默认值：`18080`
- `SSHFERRY_ALLOWED_ORIGINS`
- `SSHFERRY_LOCAL_TOKEN`

## 🛠️ 典型工作流

1. 手动新增站点，或从 SSH 命令导入站点
2. 尽量把 `remote_root` 设置为专用目录
3. 先执行内置连接检查
4. 打开一个或多个远端会话
5. 在本地与远端面板之间传输文件，或直接在远端面板之间拖拽
6. 在任务中心查看并控制传输进度

说明：

- 🔌 站点级协议默认支持 `sftp` 和 `scp`
- 🎛️ 窗口级覆盖可强制使用 `Auto`、`SFTP` 或 `SCP`
- 📍 如果 `remote_root` 为空，操作会回退到 `/`

## 🧪 测试

运行当前完整的后端测试集：

```bash
pytest
```

快速导入自检：

```bash
python -c "from src.shared.models import SiteConfig, Task; from src.core.scheduler import TaskScheduler; from src.services.connection_checker import ConnectionChecker; print('imports_ok')"
```

## 📦 打包

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

## 📚 文档

- [文档索引](docs/README_zh.md)
- [English Docs Index](docs/README.md)
- [后端总览](docs/backend/BACKEND_OVERVIEW_zh.md)
- [前端构建指南](docs/frontend/FRONTEND_BUILD_zh.md)
- [前端接口指南](docs/frontend/FRONTEND_API_zh.md)
- [前端设计指南](docs/frontend/FRONTEND_DESIGN_zh.md)
