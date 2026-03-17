"""Remote file browsing and mutation service for backend APIs."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace

from fastapi import HTTPException, status

from backend.app.schemas.remote_files import RemoteEntryResponse
from src.shared.models import SiteConfig
from src.shared.paths import get_remote_parent


class RemoteFileService:
    """SFTP-backed remote file operations scoped to an active session."""

    def __init__(self, remote_sessions: dict[str, SiteConfig], session_lock=None):
        self.remote_sessions = remote_sessions
        self.session_lock = session_lock

    def list_dir(self, session_id: str, path: str | None = None) -> tuple[str, str | None, list[RemoteEntryResponse]]:
        site = self._require_session(session_id)
        target_path = self._normalize_optional_remote_path(path) or site.remote_root
        engine = self._build_engine(site)
        try:
            engine.connect()
            entries = [self._to_response(item) for item in engine.list_dir(target_path)]
        finally:
            self._disconnect_quietly(engine)
        entries.sort(key=lambda item: (not item.is_dir, item.name.lower()))
        return target_path, get_remote_parent(target_path), entries

    def stat_path(self, session_id: str, path: str) -> RemoteEntryResponse:
        site = self._require_session(session_id)
        target_path = self._require_non_blank_remote_path(path)
        engine = self._build_engine(site)
        try:
            engine.connect()
            entry = engine.stat(target_path)
            return self._to_response(entry)
        finally:
            self._disconnect_quietly(engine)

    def mkdir(self, session_id: str, path: str) -> None:
        site = self._require_session(session_id)
        target_path = self._require_non_blank_remote_path(path)
        engine = self._build_engine(site)
        try:
            engine.connect()
            engine.mkdir(target_path)
        finally:
            self._disconnect_quietly(engine)

    def rename(self, session_id: str, old_path: str, new_path: str) -> None:
        site = self._require_session(session_id)
        source_path = self._require_non_blank_remote_path(old_path)
        target_path = self._require_non_blank_remote_path(new_path)
        engine = self._build_engine(site)
        try:
            engine.connect()
            engine.rename(source_path, target_path)
        finally:
            self._disconnect_quietly(engine)

    def delete(self, session_id: str, path: str, recursive: bool = True) -> None:
        site = self._require_session(session_id)
        target_path = self._require_non_blank_remote_path(path)
        engine = self._build_engine(site)
        try:
            engine.connect()
            entry = engine.stat(target_path)
            if entry.is_dir:
                if recursive:
                    engine.remove_dir_recursive(target_path)
                else:
                    engine.remove_dir(target_path)
            else:
                engine.remove_file(target_path)
        finally:
            self._disconnect_quietly(engine)

    def _require_session(self, session_id: str) -> SiteConfig:
        with self._session_guard():
            site = self.remote_sessions.get(session_id)
            if site is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session '{session_id}' not found",
                )
            return replace(site)

    def _session_guard(self):
        return self.session_lock if self.session_lock is not None else nullcontext()

    @staticmethod
    def _normalize_optional_remote_path(path: str | None) -> str | None:
        if path is None:
            return None
        normalized = path.strip()
        return normalized or None

    @staticmethod
    def _require_non_blank_remote_path(path: str) -> str:
        normalized = path.strip()
        if not normalized:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Remote path must not be blank",
            )
        return normalized

    @staticmethod
    def _to_response(entry) -> RemoteEntryResponse:
        return RemoteEntryResponse(
            name=entry.name,
            path=entry.path,
            is_dir=entry.is_dir,
            size=entry.size,
            mtime=entry.mtime,
            mode=entry.mode,
        )

    @staticmethod
    def _disconnect_quietly(engine) -> None:
        try:
            engine.disconnect()
        except Exception:
            pass

    @staticmethod
    def _build_engine(site: SiteConfig):
        try:
            from src.engines.sftp_engine import SftpEngine
        except ModuleNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f'Remote file dependency unavailable: {exc}',
            ) from exc
        return SftpEngine(site)
