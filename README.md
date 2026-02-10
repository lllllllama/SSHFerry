# SSHFerry ✨

[中文](README_zh.md) | English

SSHFerry is a desktop GUI for SSH/SFTP file operations, built with Python + PySide6.
It focuses on three goals: **safe remote operations**, **practical transfer behavior**, and **clear task visibility**.

## 🚀 Highlights

- 🛡️ Sandbox-protected remote operations (`remote_root`)
- 📦 File and folder upload/download (recursive)
- ⏯️ Resume/skip-aware transfer behavior
- 🧪 Built-in connection checker (TCP/SSH/SFTP/read/write)
- 📊 Task center with pause/resume/cancel/restart
- ⚡ Optional `mscp` acceleration with fallback to parallel SFTP

## 📌 Current Scope

- Runtime: Python `3.11+`
- GUI: `PySide6`
- Protocol: `Paramiko` (SSH/SFTP)
- Engines:
  - `sftp` (default)
  - `mscp` (optional external binary)
- Task states:
  - `pending`, `running`, `paused`, `done`, `failed`, `canceled`, `skipped`

## 🧭 Quick Start

1. Add a site (manual form or paste SSH command).
2. `remote_root` can be left empty; it will default to `/` (full filesystem scope). You can narrow it to a subdirectory if needed.
3. Run connection check.
4. Connect and browse remote tree.
5. Upload/download files or folders.
6. Monitor and control tasks in Task Center.

## 📦 Install

```bash
pip install -r requirements.txt
```

## ▶️ Run

### Windows

```powershell
./run.bat
# or
python -m src.app.main
```

### Linux / macOS

```bash
chmod +x run.sh
./run.sh
# or
python3 -m src.app.main
```

## ✅ Functional Verification

### Automated checks

```bash
pytest -q
```

```bash
python -c "from src.shared.errors import ErrorCode; from src.shared.models import SiteConfig, Task; from src.shared.paths import normalize_remote_path, ensure_in_sandbox; from src.engines.sftp_engine import SftpEngine; from src.core.scheduler import TaskScheduler; from src.services.connection_checker import ConnectionChecker; print('imports_ok')"
```

### Suggested manual checks

1. Connect with a dedicated sandbox path.
2. Upload the same file twice; verify second attempt is `skipped`.
3. Interrupt a large transfer, retry, and verify resume behavior.
4. Drag remote files into local panel; verify download tasks are created.
5. Attempt an operation outside sandbox; verify it is blocked.

## 🗂️ Project Layout

```text
src/
  app/        # Entry point
  core/       # Scheduler and task logic
  engines/    # SFTP / parallel SFTP / MSCP
  services/   # Site storage, connection checks, metrics
  shared/     # Models, errors, path sandboxing, logging
  ui/         # Main window and panels

tests/        # Pytest test suite
```

## 📝 Notes

- `mscp` acceleration requires an external binary.
- Passwords are runtime-only and not persisted by `SiteStore`.
- Current positioning: personal and educational use.
