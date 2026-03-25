"""Runtime data path helpers for source and packaged app modes."""
from __future__ import annotations

import os
import sys
from pathlib import Path


_APP_NAME = "SSHFerry"
_DATA_DIR_ENV = "SSHFERRY_DATA_DIR"


def is_frozen_runtime() -> bool:
    """Return whether the current process is running from a frozen bundle."""
    return bool(getattr(sys, "frozen", False))


def _user_app_data_dir() -> Path:
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / _APP_NAME
    return Path.home() / ".config" / _APP_NAME.lower()


def app_data_dir() -> Path:
    """Return the root data directory for persistent runtime files."""
    configured = os.getenv(_DATA_DIR_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
    else:
        path = Path(sys.executable).resolve().parent / "data" if is_frozen_runtime() else _user_app_data_dir()

    fallback_path = _user_app_data_dir() if is_frozen_runtime() and not configured else None
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        if fallback_path is None or fallback_path == path:
            raise
        fallback_path.mkdir(parents=True, exist_ok=True)
        return fallback_path
    return path


def backend_runtime_dir() -> Path:
    """Return the backend runtime directory."""
    if os.getenv(_DATA_DIR_ENV, "").strip() or is_frozen_runtime():
        return app_data_dir() / "backend_runtime"
    return Path.cwd() / ".backend_runtime"


def backend_workspace_root() -> Path:
    """Return the backend workspace root directory."""
    if os.getenv(_DATA_DIR_ENV, "").strip() or is_frozen_runtime():
        return app_data_dir() / "workspace"
    return Path.cwd() / ".workspace"
