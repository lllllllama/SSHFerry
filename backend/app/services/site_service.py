"""Site storage orchestration for backend APIs."""
from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.schemas.sites import SiteResponse, SiteUpsertRequest
from src.services.site_store import SiteStore
from src.shared.models import SiteConfig


class SiteService:
    """CRUD operations over persisted site configurations."""

    def __init__(self, site_store: SiteStore):
        self.site_store = site_store

    def list_sites(self) -> list[SiteConfig]:
        return self.site_store.load()

    def create_site(self, payload: SiteUpsertRequest) -> SiteConfig:
        sites = self.site_store.load()
        if any(site.name == payload.name for site in sites):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Site '{payload.name}' already exists",
            )
        site = self._to_site_config(payload)
        sites.append(site)
        self.site_store.save(sites)
        return site

    def update_site(self, current_name: str, payload: SiteUpsertRequest) -> SiteConfig:
        sites = self.site_store.load()
        idx = self._find_site_index(sites, current_name)
        if idx < 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site '{current_name}' not found",
            )
        if payload.name != current_name and any(site.name == payload.name for site in sites):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Site '{payload.name}' already exists",
            )
        site = self._to_site_config(payload)
        sites[idx] = site
        self.site_store.save(sites)
        return site

    def delete_site(self, current_name: str) -> None:
        sites = self.site_store.load()
        idx = self._find_site_index(sites, current_name)
        if idx < 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site '{current_name}' not found",
            )
        del sites[idx]
        self.site_store.save(sites)

    @staticmethod
    def to_response(site: SiteConfig) -> SiteResponse:
        return SiteResponse(
            name=site.name,
            host=site.host,
            port=site.port,
            username=site.username,
            auth_method=site.auth_method,
            remote_root=site.remote_root,
            key_path=site.key_path,
            remember_password=site.remember_password,
            proxy_jump=site.proxy_jump,
            ssh_config_path=site.ssh_config_path,
            ssh_options=list(site.ssh_options),
            default_transfer_protocol=site.default_transfer_protocol,
            has_password=(site.auth_method == "password" and site.remember_password and bool(site.password)),
        )

    @staticmethod
    def _find_site_index(sites: list[SiteConfig], current_name: str) -> int:
        for idx, site in enumerate(sites):
            if site.name == current_name:
                return idx
        return -1

    @staticmethod
    def _to_site_config(payload: SiteUpsertRequest) -> SiteConfig:
        return SiteConfig(
            name=payload.name.strip(),
            host=payload.host.strip(),
            port=payload.port,
            username=payload.username.strip(),
            auth_method=payload.auth_method,
            remote_root=payload.remote_root.strip() or "/",
            password=payload.password,
            key_path=payload.key_path,
            key_passphrase=payload.key_passphrase,
            remember_password=payload.remember_password,
            proxy_jump=payload.proxy_jump,
            ssh_config_path=payload.ssh_config_path,
            ssh_options=list(payload.ssh_options),
            default_transfer_protocol=payload.default_transfer_protocol,
        )

