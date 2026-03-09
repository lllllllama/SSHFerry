#!/usr/bin/env python3
"""Quick import smoke test for SSHFerry."""

from src.services.connection_checker import ConnectionChecker
from src.core.scheduler import TaskScheduler
from src.engines.sftp_engine import SftpEngine
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.logging_ import setup_logger
from src.shared.models import RemoteEntry, SiteConfig, Task
from src.shared.paths import ensure_in_sandbox, normalize_remote_path


def main() -> None:
    print("Testing SSHFerry imports...")
    print("[OK] Imports successful")

    normalized = normalize_remote_path("/root//autodl-tmp/./test")
    assert normalized == "/root/autodl-tmp/test", f"Path normalization failed: {normalized}"
    print(f"[OK] normalize_remote_path: {normalized}")

    ensure_in_sandbox("/root/autodl-tmp/test", "/root/autodl-tmp")
    print("[OK] ensure_in_sandbox accepts valid path")

    try:
        ensure_in_sandbox("/etc/passwd", "/root/autodl-tmp")
        raise AssertionError("ensure_in_sandbox should reject out-of-sandbox paths")
    except Exception:
        print("[OK] ensure_in_sandbox rejects invalid path")

    site = SiteConfig(
        name="Test",
        host="localhost",
        port=22,
        username="user",
        auth_method="password",
        remote_root="/root/test",
    )
    print(f"[OK] SiteConfig: {site.name} @ {site.host}:{site.port}")

    _ = (ErrorCode, SSHFerryError, RemoteEntry, Task, setup_logger, SftpEngine, TaskScheduler, ConnectionChecker)
    print("All basic checks passed")


if __name__ == "__main__":
    main()
