<p align="center">
  <img src="docs/assets/logo.png" alt="SSHFerry logo" width="220" />
</p>

# SSHFerry

Multi-session SSH file transfer workspace for safer daily remote operations.

[中文](README_zh.md) | **English**

## 🚀 Overview

SSHFerry is an SSH file operations project that combines a desktop client, a local backend, and a web frontend in a single repository.

The desktop client is the current primary entry point. It already covers the main workflow for practical remote file work: browse, upload, download, remote-to-remote copy, task control, and safer remote boundaries through `remote_root`.

## Why SSHFerry

Many SSH file workflows are still pieced together from terminals, ad hoc scripts, and separate tools for browsing, transfer, and retry handling.

SSHFerry brings those daily operations into one workspace so routine remote work is easier to inspect, safer to control, and less error-prone:

- 🗂️ One place for local and remote browsing
- 🎯 Built-in task visibility and transfer control
- 🔗 Multiple remote sessions in the same workflow
- 🛡️ Safer remote boundaries through `remote_root`
- ⚡ Practical support for `sftp`, `scp`, and parallel transfer paths

## ✨ Highlights

- 🖥️ Desktop client: usable and recommended today
- 🧩 Backend service: available and integrated with repository transfer logic
- 🌐 Frontend app: present, partially functional, and still under active integration
- 📁 Manage multiple remote sites in one workspace
- ↔️ Browse local and remote files side by side
- 📤 Upload, download, and drag between remote sessions
- ⚙️ Use `sftp`, `scp`, and parallel transfer paths when appropriate
- ⏯️ Pause, resume, cancel, restart, and monitor transfer tasks
- 🔒 Restrict remote operations with `remote_root`
- 🧭 Import site information from SSH-style commands

## 🧱 Components

- 🖥️ Desktop client: Python + PySide6 application for day-to-day file operations
- 🧩 Backend service: FastAPI app for sites, sessions, tasks, logs, and workspace APIs
- 🌐 Frontend app: React + Vite UI being integrated around backend APIs

## 🗃️ Repository Layout

```text
src/        Desktop application, transfer engines, scheduler, shared models
backend/    FastAPI backend service
frontend/   React + Vite frontend application
docs/       Maintained implementation and design documents
tests/      Pytest suite
tools/      Packaging and benchmark scripts
```

## 🚀 Getting Started

### 📋 Requirements

- Python `3.11+`
- Node.js `18+` for frontend work
- Windows, Linux, or macOS for desktop development

### 🐍 Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 📦 Install Frontend Dependencies

```bash
cd frontend
npm install
```

## ▶️ Run

Windows:

```powershell
./run.bat
```

Linux or macOS:

```bash
./run.sh
```

Direct module entry:

```bash
python -m src.app.main
```

Backend service:

```bash
python -m backend.app.main
```

Frontend app:

```bash
cd frontend
npm run dev
```

Build the frontend:

```bash
cd frontend
npm run build
```

Common backend environment variables:

- `SSHFERRY_BACKEND_HOST` default: `127.0.0.1`
- `SSHFERRY_BACKEND_PORT` default: `18080`
- `SSHFERRY_ALLOWED_ORIGINS`
- `SSHFERRY_LOCAL_TOKEN`

## 🛠️ Typical Workflow

1. Add a site manually or import one from an SSH command
2. Set `remote_root` to a dedicated directory when possible
3. Run the built-in connection check
4. Open one or more remote sessions
5. Transfer files between local and remote panels, or drag between remote panels
6. Monitor and control work in the task center

Notes:

- 🔌 Site-level protocol defaults support `sftp` and `scp`
- 🎛️ A window-level override can force `Auto`, `SFTP`, or `SCP`
- 📍 If `remote_root` is empty, operations fall back to `/`

## 🧪 Testing

Run the full backend-focused test suite:

```bash
pytest
```

Quick import smoke check:

```bash
python -c "from src.shared.models import SiteConfig, Task; from src.core.scheduler import TaskScheduler; from src.services.connection_checker import ConnectionChecker; print('imports_ok')"
```

## 📦 Packaging

Windows packaging currently targets the desktop client.

Standard build:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -VenvPath .venv_compat
```

Debug build:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -Debug -VenvPath .venv_compat
```

Release build:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -VenvPath .venv_compat
```

Expected outputs:

```text
release/SSHFerry-<version>-windows/
release/SSHFerry-<version>-windows.zip
release/SSHFerry-<version>-windows.sha256
```

## 📚 Documentation

- [Docs Index](docs/README.md)
- [Chinese Docs Index](docs/README_zh.md)
- [Backend Overview](docs/backend/BACKEND_OVERVIEW.md)
- [Frontend Build Guide](docs/frontend/FRONTEND_BUILD.md)
- [Frontend API Guide](docs/frontend/FRONTEND_API.md)
- [Frontend Design Guide](docs/frontend/FRONTEND_DESIGN.md)
