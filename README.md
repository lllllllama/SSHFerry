# SSHFerry ✨

[中文](README_zh.md) | English

SSHFerry is a desktop GUI for SSH/SFTP/SCP file operations, built with Python + PySide6.
It focuses on three goals: **safe remote operations**, **practical transfer behavior**, and **clear task visibility**.

## 🚀 Highlights

- 🛡️ Sandbox-protected remote operations (`remote_root`)
- 📦 File and folder upload/download (recursive)
- ⏯️ Resume/skip-aware transfer behavior
- 🧪 Built-in connection checker (TCP/SSH/SFTP/read/write)
- 📊 Task center with pause/resume/cancel/restart
- ⚡ High-throughput parallel chunk transfer for large files
- 🪟 Multi-session remote workspace in one window
- 🔁 Remote-to-remote transfer by dragging between remote sessions

## 📌 Current Scope

- Runtime: Python `3.11+`
- GUI: `PySide6`
- Protocols/Libraries: `Paramiko` (SSH/SFTP) + `scp`
- Engines:
  - `sftp` (default)
  - `parallel` (native chunked transfer for large files)
  - `scp` (manual-select transfer mode; overwrite-by-default)
- Task states:
  - `pending`, `running`, `paused`, `done`, `failed`, `canceled`, `skipped`

## 🧭 Quick Start

1. Add a site (manual form or paste SSH command).
2. Set `remote_root` to a dedicated project directory whenever possible (recommended). If left empty, it defaults to `/` (full filesystem scope).
3. Run connection check.
4. Open one or more remote sessions and connect.
5. Upload/download files or folders.
   - Site-level default transfer protocol can be set to `sftp` or `scp`.
   - Per-task override is available from the main window (`Auto/SFTP/SCP`).
6. Drag between remote panels to create remote-to-remote transfer tasks.
   - File tasks are queued immediately.
   - Folder tasks are scanned first so total bytes/file counts are known.
7. Monitor and control tasks in Task Center.

### First-run note

- SSHFerry no longer auto-creates demo/test sites on startup.
- If site list is empty, click `Add Site` to create your first connection.

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

## 📦 Publish As App (Windows)

Build a distributable GUI app (`SSHFerry.exe`) with PyInstaller:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -VenvPath .venv_compat
```

Recommended validation flow on Windows:

```powershell
# 1) Build a console-enabled debug package first
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -Debug -VenvPath .venv_compat

# 2) After startup/connect checks pass, build the GUI release package
powershell -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Clean -VenvPath .venv_compat
```

Or use the wrapper:

```bat
tools\build_windows.bat
```

Output package directory:

```text
release/SSHFerry-<version>-windows/
```

Debug package directory:

```text
release/SSHFerryDebug-<version>-windows-debug/
```

The script also generates:

```text
release/SSHFerry-<version>-windows.zip
release/SSHFerry-<version>-windows.sha256
```

Important packaging notes:

- Publish the full directory or generated `.zip`, not the standalone `.exe` only.
- The Windows build uses `onedir` layout for better PySide6 stability.
- UPX compression is disabled by default to reduce Qt runtime issues and antivirus false positives.

Recommended release flow:

1. Upload the `.zip` file.
2. Publish the `.sha256` checksum alongside it for integrity verification.

### GitHub Release Checklist

Before creating a GitHub Release, verify the following:

1. `pytest -q` passes locally.
2. `release/SSHFerryDebug-<version>-windows-debug/SSHFerryDebug.exe` starts correctly.
3. `release/SSHFerry-<version>-windows/SSHFerry.exe` starts correctly.
4. Local file panel icons render correctly on Windows.
5. `startup.log` is created under `%USERPROFILE%\AppData\Local\SSHFerry\` when needed.

Recommended GitHub Release assets:

- `SSHFerry-<version>-windows.zip`
- `SSHFerry-<version>-windows.sha256`
- optional: `SSHFerryDebug-<version>-windows-debug.zip` for testers only

Suggested release notes template:

```text
Highlights
- Fixed Windows packaged app startup stability
- Improved local file icon handling
- Stabilized PySide6/PyInstaller build toolchain

Downloads
- SSHFerry-<version>-windows.zip
- SSHFerry-<version>-windows.sha256

Notes
- Keep the whole extracted folder together; do not run only the .exe
- sites.json: %USERPROFILE%\AppData\Local\SSHFerry\sites.json
- startup.log: %USERPROFILE%\AppData\Local\SSHFerry\startup.log
```

Recommended tag workflow:

```powershell
git add .
git commit -m "release: prepare v<version>"
git push origin main
git tag v<version>
git push origin v<version>
```

After the tag is pushed, create a GitHub Release from `v<version>` and upload the generated `.zip` and `.sha256`.

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
5. Open two remote sessions and drag file/folder between them; verify remote-to-remote tasks are created.
6. Attempt an operation outside sandbox; verify it is blocked.

## ⚡ Large File Performance

### Current strategy

- For large files, SSHFerry prefers accelerated transfer path selection.
- Large files are automatically switched to optimized parallel SFTP chunk transfer.
- Parallel transfer uses throughput presets (`low` / `medium` / `high`).
- Default preset policy is direction-aware: upload uses `medium`, download uses `high`.
- Scheduler has protocol-aware concurrency caps by default:
  - `max_workers_total=3`
  - `max_workers_sftp=3`
  - `max_workers_scp=2`
  - `max_workers_parallel=1`

### SCP behavior notes

- SCP is now supported for file upload/download tasks.
- SCP default semantics are overwrite-oriented (no native resume).
- If an SCP transfer fails, SSHFerry automatically falls back once to SFTP (`fallback=scp_to_sftp`).
- On fallback, existing SFTP resume/skip behavior applies.

### Remote-to-remote behavior

- Remote-to-remote tasks are created when dragging from one remote session into another.
- For smaller files, SSHFerry first tries direct remote copy by running `scp` on the source host.
- Direct remote copy currently requires destination key authentication (`key_path`).
- If direct copy fails, SSHFerry falls back to a relay path through the running app process.
- Large files skip direct copy and use parallel bridge transfer by default.
- Directory transfer follows the same idea: try direct recursive `scp`, then fall back to relay copy.

### Why fallback is faster now

- Reuses per-worker local/remote file handles instead of opening per chunk.
- Uses multi-connection concurrent chunk transfer.
- Keeps progress updates batched to reduce callback overhead.

### Optimization tips for best speed

1. Keep current direction-aware defaults (`upload=medium`, `download=high`) as baseline.
2. Use stable wired network when possible.
3. Prefer key auth and reduce proxy-hop count.
4. Resume interrupted transfers instead of restarting.
5. Keep enough disk I/O headroom on both ends; chunked parallel transfer is sensitive to storage bottlenecks.

### Benchmark your own server

```bash
python tools/benchmark_transfer.py --site "<your-site-name>" --size-mb 512 --iterations 2
```

- Modes can be customized with `--modes`, for example: `sftp,parallel:high,parallel:medium`.
- Use benchmark results as your final tuning source, because host limits and RTT dominate real speed.

### Observed improvement (ratio-based)

- In a real remote test, `parallel` mode achieved about **10x to 16x** throughput compared with plain `sftp` on large files.
- For that same test pattern:
  - Download favored `parallel:high`.
  - Upload favored `parallel:medium`.
- These are **relative multipliers**, not fixed speeds. Your actual result depends on network bandwidth, RTT, server limits, and disk I/O.

### Parallel tuning env vars

- `SSHFERRY_PARALLEL_WORKERS`: override worker count.
- `SSHFERRY_PARALLEL_CHUNK_BYTES`: override chunk size in bytes.
- `SSHFERRY_PARALLEL_WARMUP_BATCH`: workers launched per warmup batch.
- `SSHFERRY_PARALLEL_WARMUP_DELAY`: seconds between warmup batches.
- `SSHFERRY_PARALLEL_MAX_CHUNK_RETRIES`: per-chunk retry limit.
- `SSHFERRY_STRICT_HOSTKEY`: set to `1`/`true`/`yes`/`on` to enable strict SSH host-key verification (`RejectPolicy` + system known_hosts).

## 🗂️ Project Layout

```text
src/
  app/        # Entry point
  core/       # Scheduler and task logic
  engines/    # SFTP / SCP / parallel SFTP / remote-to-remote transfer
  services/   # Site storage, connection checks, metrics
  shared/     # Models, errors, path sandboxing, logging
  ui/         # Main window and panels

tests/        # Pytest test suite
```

## 📝 Notes

- Passwords are not persisted by default. If you enable `Save password to sites.json` for a password-based site, it will be stored locally in the site store on this machine.
- Site storage path:
  - Windows: `%USERPROFILE%\AppData\Local\SSHFerry\sites.json`
  - Linux/macOS: `~/.config/sshferry/sites.json`
- Current positioning: personal and educational use.
- For safer operations, prefer least-privilege accounts and a non-root `remote_root`.
