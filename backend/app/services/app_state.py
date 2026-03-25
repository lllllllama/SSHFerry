"""Application state shared across backend routes and services."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import secrets
from threading import RLock
from typing import TYPE_CHECKING

from backend.app.config import RuntimeSettings, build_runtime_settings
from backend.app.services.activity_service import ActivityService
from backend.app.services.auth_service import AuthService
from backend.app.services.log_service import LogService
from src.shared.runtime_paths import backend_runtime_dir
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
        fallback_dir = backend_runtime_dir()
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_dir / 'sites.json'
        _module_logger.warning('Falling back to workspace site store at %s: %s', fallback_path, exc)
        return SiteStore(path=fallback_path)


def _build_auth_token() -> str:
    configured = os.getenv('SSHFERRY_LOCAL_TOKEN', '').strip()
    return configured or secrets.token_urlsafe(32)


@dataclass(slots=True)
class AppState:
    """Long-lived backend objects shared across requests."""

    logger: logging.Logger = field(default_factory=lambda: setup_logger('sshferry.backend'))
    runtime_settings: RuntimeSettings = field(default_factory=build_runtime_settings)
    site_store: SiteStore = field(default_factory=_build_site_store)
    activity_service: ActivityService = field(init=False)
    log_service: LogService = field(init=False)
    auth_service: AuthService = field(init=False)
    scheduler: TaskScheduler | None = field(init=False, default=None)
    remote_sessions: dict[str, SiteConfig] = field(default_factory=dict)
    session_lock: RLock = field(default_factory=RLock)
    auth_token: str = field(default_factory=_build_auth_token)
    startup_error: str | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.activity_service = ActivityService()
        self.log_service = LogService()
        self.auth_service = AuthService(settings=self.runtime_settings, logger=self.logger)
        self.log_service.attach_logger(self.logger)
        self.log_service.attach_logger(logging.getLogger('src'))
        self.log_service.attach_logger(logging.getLogger('backend.app'))

    @property
    def session_count(self) -> int:
        """Return the number of active in-memory remote sessions."""
        with self.session_lock:
            return len(self.remote_sessions)

    @property
    def is_ready(self) -> bool:
        """Return whether core backend services started successfully."""
        return (
            self.scheduler is not None
            and self.scheduler.running
            and self.auth_service.is_ready
            and self.startup_error is None
        )

    def start(self) -> None:
        """Start backend background services."""
        errors: list[str] = []
        try:
            self.auth_service.start()
        except Exception as exc:
            errors.append(str(exc))

        try:
            self.site_store.validate()
        except Exception as exc:
            errors.append(str(exc))

        try:
            from src.core.scheduler import TaskScheduler

            self.scheduler = TaskScheduler(
                logger=self.logger,
                activity_service=self.activity_service,
                workspace_root=self.runtime_settings.workspace_root,
            )
            self.scheduler.start()
        except Exception as exc:
            self.scheduler = None
            errors.append(str(exc))
            self.logger.error('Backend app state failed to start core services: %s', exc)

        self.startup_error = '; '.join(errors) if errors else None
        if self.startup_error is None:
            self.logger.info('Backend app state started')

    def stop(self) -> None:
        """Stop backend background services."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.stop()
        self.auth_service.stop()
        self.logger.info('Backend app state stopped')
        self.activity_service.close()
        self.log_service.close()

    def require_scheduler(self) -> TaskScheduler:
        """Return the scheduler or raise a clear startup error."""
        if self.scheduler is None:
            raise RuntimeError(self.startup_error or 'Task scheduler is unavailable')
        return self.scheduler
