"""Main application entry point."""
import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

# Ensure project root is on path when running directly.
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(_src_dir))

if TYPE_CHECKING:
    from src.ui.main_window import MainWindow


def _runtime_dir() -> Path:
    """Return platform-appropriate app runtime directory."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "SSHFerry"
    else:
        base = Path.home() / ".config" / "sshferry"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _startup_log_path() -> Path:
    return _runtime_dir() / "startup.log"


def _bootstrap_frozen_pyside() -> None:
    """Ensure PySide6 DLL directories are registered before importing Qt."""
    if sys.platform != "win32":
        return

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))
    candidates.append(Path(sys.executable).resolve().parent)

    for base in candidates:
        pyside_dir = base / "PySide6"
        shiboken_dir = base / "shiboken6"
        if not pyside_dir.is_dir():
            continue

        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        os.environ["PATH"] = (
            os.pathsep.join(
                [
                    str(pyside_dir),
                    str(shiboken_dir),
                    os.environ.get("PATH", ""),
                ]
            ).rstrip(os.pathsep)
        )

        for dll_dir in (pyside_dir, shiboken_dir):
            if dll_dir.is_dir():
                os.add_dll_directory(str(dll_dir))
        return


def _append_startup_log(
    title: str,
    exc_type: type[BaseException] | None = None,
    exc_value: BaseException | None = None,
    exc_tb: TracebackType | None = None,
) -> None:
    """Best-effort startup diagnostics for windowed builds."""
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            f"[{now}] {title}",
            f"executable={sys.executable}",
            f"cwd={os.getcwd()}",
            f"argv={sys.argv}",
        ]
        if exc_type is not None:
            lines.append(
                "".join(traceback.format_exception(exc_type, exc_value, exc_tb)).rstrip()
            )
        with _startup_log_path().open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n\n")
    except Exception:
        pass


def _install_exception_hooks() -> None:
    def _sys_hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        _append_startup_log("unhandled exception (main thread)", exc_type, exc_value, exc_tb)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        _append_startup_log(
            f"unhandled exception (thread={args.thread.name})",
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
        )
        threading.__excepthook__(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


class WindowManager:
    """Manages multiple MainWindow instances."""

    _instance = None

    def __init__(self, main_window_cls):
        self._main_window_cls = main_window_cls
        self.windows = []

    @classmethod
    def instance(cls, main_window_cls=None):
        """Get the singleton instance."""
        if cls._instance is None:
            if main_window_cls is None:
                raise RuntimeError("WindowManager not initialized")
            cls._instance = WindowManager(main_window_cls)
        return cls._instance

    def create_window(self):
        """Create and show a new window."""
        window = self._main_window_cls()
        window.window_manager = self
        self.windows.append(window)
        window.destroyed.connect(lambda: self._on_window_destroyed(window))
        window.show()
        return window

    def _on_window_destroyed(self, window):
        """Handle window destruction."""
        if window in self.windows:
            self.windows.remove(window)

    def window_count(self) -> int:
        """Get the number of open windows."""
        return len(self.windows)


def main():
    """Run the application."""
    _install_exception_hooks()
    _append_startup_log("startup begin")
    try:
        _bootstrap_frozen_pyside()
        from PySide6.QtWidgets import QApplication
        from src.ui.main_window import MainWindow

        app = QApplication(sys.argv)
        app.setApplicationName("SSHFerry")
        app.setOrganizationName("SSHFerry")

        manager = WindowManager.instance(MainWindow)
        manager.create_window()
        exit_code = app.exec()
        _append_startup_log(f"startup end exit_code={exit_code}")
        sys.exit(exit_code)
    except Exception as exc:
        _append_startup_log("startup crash", type(exc), exc, exc.__traceback__)
        raise


if __name__ == "__main__":
    main()

