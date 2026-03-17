"""Application state shared across backend routes and services."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.services.site_store import SiteStore
from src.shared.logging_ import setup_logger
from src.shared.models import SiteConfig

if TYPE_CHECKING:
    from src.core.scheduler import TaskScheduler


_module_logger = logging.getLogger(__name__)


def _build_site_store() -> SiteStore:
    """Create the site store with a workspace-local fallback for restricted envs."""
    try:
        return SiteStore()
    except Exception as exc:
        fallback_dir = Path.cwd() / ".backend_runtime"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_dir / "sites.json"
        _module_logger.warning("Falling back to workspace site store at %s: %s", fallback_path, exc)
        return SiteStore(path=fallback_path)


@dataclass(slots=True)
class AppState:
    """Long-lived backend objects shared across requests."""

    logger: logging.Logger = field(default_factory=lambda: setup_logger("sshferry.backend"))
    site_store: SiteStore = field(default_factory=_build_site_store)
    scheduler: TaskScheduler | None = field(init=False, default=None)
    remote_sessions: dict[str, SiteConfig] = field(default_factory=dict)
    startup_error: str | None = field(init=False, default=None)

    @property
    def session_count(self) -> int:
        """Return the number of active in-memory remote sessions."""
        return len(self.remote_sessions)

    @property
    def is_ready(self) -> bool:
        """Return whether core backend services started successfully."""
        return self.scheduler is not None and self.scheduler.running and self.startup_error is None

    def start(self) -> None:
        """Start backend background services."""
        try:
            from src.core.scheduler import TaskScheduler

            self.scheduler = TaskScheduler(logger=self.logger)
            self.scheduler.start()
            self.startup_error = None
            self.logger.info("Backend app state started")
        except Exception as exc:
            self.scheduler = None
            self.startup_error = str(exc)
            self.logger.error("Backend app state failed to start core services: %s", exc)

    def stop(self) -> None:
        """Stop backend background services."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.stop()
        self.logger.info("Backend app state stopped")

    def require_scheduler(self) -> TaskScheduler:
        """Return the scheduler or raise a clear startup error."""
        if self.scheduler is None:
            raise RuntimeError(self.startup_error or "Task scheduler is unavailable")
        return self.scheduler
