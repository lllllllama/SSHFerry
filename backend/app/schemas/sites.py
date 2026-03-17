"""Pydantic schemas for site configuration APIs."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SiteUpsertRequest(BaseModel):
    """Request body for creating or updating a site."""

    name: str = Field(min_length=1)
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1)
    auth_method: str = Field(pattern="^(password|key)$")
    remote_root: str = Field(default="/", min_length=1)
    password: str | None = None
    key_path: str | None = None
    key_passphrase: str | None = None
    remember_password: bool = False
    proxy_jump: str | None = None
    ssh_config_path: str | None = None
    ssh_options: list[str] = Field(default_factory=list)
    default_transfer_protocol: str = Field(default="sftp", pattern="^(sftp|scp)$")


class SiteResponse(BaseModel):
    """Sanitized site payload returned to the frontend."""

    name: str
    host: str
    port: int
    username: str
    auth_method: str
    remote_root: str
    key_path: str | None = None
    remember_password: bool = False
    proxy_jump: str | None = None
    ssh_config_path: str | None = None
    ssh_options: list[str] = Field(default_factory=list)
    default_transfer_protocol: str
    has_password: bool = False


class SiteListResponse(BaseModel):
    """List wrapper for site API responses."""

    items: list[SiteResponse]
    total: int
