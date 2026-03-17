"""Pydantic schemas for connection checks and remote sessions."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectionCheckRequest(BaseModel):
    """Request body for running a connection self-check against a saved site."""

    site_name: str = Field(min_length=1)
    password: str | None = None
    key_passphrase: str | None = None


class ConnectionCheckResultResponse(BaseModel):
    """One connection check result item."""

    name: str
    passed: bool
    message: str


class ConnectionCheckResponse(BaseModel):
    """Response payload for a full connection check."""

    site_name: str
    all_passed: bool
    results: list[ConnectionCheckResultResponse]


class SessionOpenRequest(BaseModel):
    """Request body for creating a remote session context."""

    site_name: str = Field(min_length=1)
    password: str | None = None
    key_passphrase: str | None = None


class SessionCloseRequest(BaseModel):
    """Request body for closing a remote session."""

    session_id: str = Field(min_length=1)


class SessionResponse(BaseModel):
    """Sanitized remote session payload."""

    session_id: str
    site_name: str
    host: str
    port: int
    username: str
    auth_method: str
    remote_root: str
    has_password: bool = False


class SessionListResponse(BaseModel):
    """List wrapper for active sessions."""

    items: list[SessionResponse]
    total: int
