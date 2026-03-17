"""Connection checking and remote session orchestration."""
from __future__ import annotations

from dataclasses import replace
import uuid

from fastapi import HTTPException, status

from backend.app.schemas.connections import (
    ConnectionCheckRequest,
    ConnectionCheckResponse,
    ConnectionCheckResultResponse,
    SessionOpenRequest,
    SessionResponse,
)
from src.services.site_store import SiteStore
from src.shared.models import SiteConfig


class ConnectionService:
    """Operations for site-based connection checks and remote sessions."""

    def __init__(self, site_store: SiteStore, remote_sessions: dict[str, SiteConfig]):
        self.site_store = site_store
        self.remote_sessions = remote_sessions

    def run_check(self, payload: ConnectionCheckRequest) -> ConnectionCheckResponse:
        runtime_site = self._resolve_runtime_site(
            payload.site_name,
            password=payload.password,
            key_passphrase=payload.key_passphrase,
        )
        try:
            from src.services.connection_checker import ConnectionChecker
        except ModuleNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Connection check dependency unavailable: {exc}",
            ) from exc

        checker = ConnectionChecker(runtime_site)
        results = checker.run_all_checks()
        return ConnectionCheckResponse(
            site_name=runtime_site.name,
            all_passed=all(item.passed for item in results),
            results=[
                ConnectionCheckResultResponse(
                    name=item.name,
                    passed=item.passed,
                    message=item.message,
                )
                for item in results
            ],
        )

    def list_sessions(self) -> list[SessionResponse]:
        items: list[SessionResponse] = []
        for session_id, site in self.remote_sessions.items():
            items.append(self._to_session_response(session_id, site))
        return items

    def open_session(self, payload: SessionOpenRequest) -> SessionResponse:
        runtime_site = self._resolve_runtime_site(
            payload.site_name,
            password=payload.password,
            key_passphrase=payload.key_passphrase,
        )
        session_id = str(uuid.uuid4())
        self.remote_sessions[session_id] = runtime_site
        return self._to_session_response(session_id, runtime_site)

    def close_session(self, session_id: str) -> None:
        if session_id not in self.remote_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found",
            )
        self.remote_sessions.pop(session_id, None)

    def _resolve_runtime_site(
        self,
        site_name: str,
        *,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> SiteConfig:
        site = self._load_site(site_name)
        runtime_site = replace(site)
        runtime_site.remote_root = runtime_site.remote_root.strip() or "/"

        if runtime_site.auth_method == "password":
            runtime_site.password = password if password is not None else runtime_site.password
            if not runtime_site.password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Site '{site_name}' requires a password",
                )
        elif runtime_site.auth_method == "key":
            runtime_site.key_passphrase = (
                key_passphrase if key_passphrase is not None else runtime_site.key_passphrase
            )
            if not runtime_site.key_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Site '{site_name}' requires a key_path",
                )

        return runtime_site

    def _load_site(self, site_name: str) -> SiteConfig:
        sites = self.site_store.load()
        for site in sites:
            if site.name == site_name:
                return site
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site '{site_name}' not found",
        )

    @staticmethod
    def _to_session_response(session_id: str, site: SiteConfig) -> SessionResponse:
        return SessionResponse(
            session_id=session_id,
            site_name=site.name,
            host=site.host,
            port=site.port,
            username=site.username,
            auth_method=site.auth_method,
            remote_root=site.remote_root,
            has_password=(site.auth_method == "password" and bool(site.password)),
        )
