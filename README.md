<p align="center">
  <img src="docs/assets/logo.png" alt="SSHFerry logo" width="220" />
</p>

# SSHFerry

Multi-session SSH file transfer workspace for safer daily remote operations.

[中文](README_zh.md) | **English**

## Overview

SSHFerry is an SSH file operations project with three active parts in one repository:

- A desktop client built with Python and PySide6
- A local FastAPI backend that exposes transfer, site, task, and workspace APIs
- A React + Vite frontend that is being integrated around the backend APIs

The current primary entry point is the desktop client. It already covers the core workflow for practical remote file work: browsing, upload, download, remote-to-remote copy, task control, and safer path boundaries through `remote_root`.

## Current Status

- Desktop client: usable and the recommended way to run SSHFerry today
- Backend service: available and wired into the repository's transfer logic
- Frontend app: present and functional in parts, but still under active integration

## Core Capabilities

- Manage multiple remote sites in one workspace
- Browse local and remote files side by side
- Upload, download, and drag between remote sessions
- Use `sftp`, `scp`, and parallel transfer paths where appropriate
- Pause, resume, cancel, restart, and observe task progress
- Restrict remote operations with `remote_root`
- Import site information from SSH-style commands

## Repository Layout

```text
src/        Desktop application, transfer engines, scheduler, shared models
backend/    FastAPI backend service
frontend/   React + Vite frontend application
docs/       Maintained implementation and design documents
tests/      Pytest suite
tools/      Packaging and benchmark scripts
```

## Requirements

- Python `3.11+`
- Node.js `18+` for frontend work
- Windows, Linux, or macOS for desktop development

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Frontend dependencies:

```bash
cd frontend
npm install
```

## Quick Start

### Run the desktop client

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

### Run the backend service

```bash
python -m backend.app.main
```

Useful backend environment variables:

- `SSHFERRY_BACKEND_HOST` default: `127.0.0.1`
- `SSHFERRY_BACKEND_PORT` default: `18080`
- `SSHFERRY_ALLOWED_ORIGINS`
- `SSHFERRY_LOCAL_TOKEN`

### Run the frontend app

```bash
cd frontend
npm run dev
```

Build the frontend:

```bash
cd frontend
npm run build
```

## Typical Desktop Workflow

1. Add a site manually or import one from an SSH command
2. Set `remote_root` to a dedicated directory when possible
3. Run the built-in connection check
4. Open one or more remote sessions
5. Transfer files between local and remote panels, or drag between remote panels
6. Monitor and control work in the task center

Notes:

- Site-level protocol defaults support `sftp` and `scp`
- A window-level override can force `Auto`, `SFTP`, or `SCP`
- If `remote_root` is empty, operations fall back to `/`

## Testing

Run the test suite:

```bash
pytest -q
```

Quick import smoke check:

```bash
python -c "from src.shared.models import SiteConfig, Task; from src.core.scheduler import TaskScheduler; from src.services.connection_checker import ConnectionChecker; print('imports_ok')"
```

## Packaging

Windows packaging targets the desktop client.

Build:

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

## Documentation

- [Docs Index](docs/README.md)
- [Chinese Docs Index](docs/README_zh.md)
- [Backend Overview](docs/backend/BACKEND_OVERVIEW.md)
- [Frontend Build Guide](docs/frontend/FRONTEND_BUILD.md)
- [Frontend API Guide](docs/frontend/FRONTEND_API.md)
- [Frontend Design Guide](docs/frontend/FRONTEND_DESIGN.md)
