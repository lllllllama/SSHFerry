"""Site storage orchestration for backend APIs."""
from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.schemas.sites import SiteResponse, SiteUpsertRequest
from src.services.site_store import SiteStore
from src.shared.models import SiteConfig


class SiteService:
    """CRUD operations over persisted site configurations."""

    def __init__(self, site_store: SiteStore, owner_user_id: str):
        self.site_store = site_store
        self.owner_user_id = owner_user_id

    def list_sites(self) -> list[SiteConfig]:
        return [site for site in self._load_sites() if self._is_owned_site(site)]

    def create_site(self, payload: SiteUpsertRequest) -> SiteConfig:
        sites = self._load_sites()
        owned_sites = [site for site in sites if self._is_owned_site(site)]
        if any(site.name == payload.name for site in owned_sites):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Site '{payload.name}' already exists",
            )
        site = self._to_site_config(payload)
        sites.append(site)
        self._save_sites(sites)
        return site

    def update_site(self, current_name: str, payload: SiteUpsertRequest) -> SiteConfig:
        sites = self._load_sites()
        idx = self._find_site_index(sites, current_name)
        if idx < 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site '{current_name}' not found",
            )
        if payload.name != current_name and any(
            site.name == payload.name and self._is_owned_site(site)
            for site in sites
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Site '{payload.name}' already exists",
            )
        site = self._to_site_config(payload, existing=sites[idx])
        sites[idx] = site
        self._save_sites(sites)
        return site

    def delete_site(self, current_name: str) -> None:
        sites = self._load_sites()
        idx = self._find_site_index(sites, current_name)
        if idx < 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site '{current_name}' not found",
            )
        del sites[idx]
        self._save_sites(sites)

    def delete_sites(self, current_names: list[str]) -> list[str]:
        names = list(dict.fromkeys(current_names))
        sites = self._load_sites()
        missing = [name for name in names if self._find_site_index(sites, name) < 0]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site '{missing[0]}' not found",
            )

        name_set = set(names)
        next_sites = [site for site in sites if not (site.name in name_set and self._is_owned_site(site))]
        self._save_sites(next_sites)
        return names

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
            has_password=(site.auth_method == 'password' and site.remember_password and bool(site.password)),
            has_key_passphrase=(site.auth_method == 'key' and bool(site.key_passphrase)),
        )

    def _is_owned_site(self, site: SiteConfig) -> bool:
        return site.owner_user_id in (None, self.owner_user_id)

    def _load_sites(self) -> list[SiteConfig]:
        try:
            return self.site_store.load_or_raise()
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    def _save_sites(self, sites: list[SiteConfig]) -> None:
        try:
            self.site_store.save(sites)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    def _find_site_index(self, sites: list[SiteConfig], current_name: str) -> int:
        for idx, site in enumerate(sites):
            if site.name == current_name and self._is_owned_site(site):
                return idx
        return -1

    def _to_site_config(self, payload: SiteUpsertRequest, existing: SiteConfig | None = None) -> SiteConfig:
        password = payload.password
        if (
            payload.auth_method == 'password'
            and existing is not None
            and existing.auth_method == 'password'
            and payload.remember_password
            and not password
            and existing.remember_password
            and existing.password
        ):
            password = existing.password

        key_passphrase = payload.key_passphrase
        if (
            payload.auth_method == 'key'
            and existing is not None
            and existing.auth_method == 'key'
            and key_passphrase is None
            and existing.key_passphrase
        ):
            key_passphrase = existing.key_passphrase

        return SiteConfig(
            name=payload.name.strip(),
            host=payload.host.strip(),
            port=payload.port,
            username=payload.username.strip(),
            auth_method=payload.auth_method,
            remote_root=payload.remote_root.strip() or '/',
            owner_user_id=self.owner_user_id,
            password=password,
            key_path=payload.key_path,
            key_passphrase=key_passphrase,
            remember_password=payload.remember_password,
            proxy_jump=payload.proxy_jump,
            ssh_config_path=payload.ssh_config_path,
            ssh_options=list(payload.ssh_options),
            default_transfer_protocol=payload.default_transfer_protocol,
        )
