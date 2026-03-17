"""Pydantic schemas for remote file system APIs."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RemoteEntryResponse(BaseModel):
    """Sanitized remote file system entry."""

    name: str
    path: str
    is_dir: bool
    size: int
    mtime: float
    mode: int | None = None


class RemoteListResponse(BaseModel):
    """Directory listing response for a remote session."""

    session_id: str
    current_path: str
    parent_path: str | None
    items: list[RemoteEntryResponse]
    total: int


class RemoteStatResponse(BaseModel):
    """Remote stat response."""

    entry: RemoteEntryResponse


class RemoteListQuery(BaseModel):
    """Query shape for remote list requests."""

    session_id: str = Field(min_length=1)
    path: str | None = None


class RemoteStatQuery(BaseModel):
    """Query shape for remote stat requests."""

    session_id: str = Field(min_length=1)
    path: str = Field(min_length=1)


class RemoteMkdirRequest(BaseModel):
    """Request body for remote directory creation."""

    session_id: str = Field(min_length=1)
    path: str = Field(min_length=1)


class RemoteRenameRequest(BaseModel):
    """Request body for remote rename or move."""

    session_id: str = Field(min_length=1)
    old_path: str = Field(min_length=1)
    new_path: str = Field(min_length=1)


class RemoteDeleteRequest(BaseModel):
    """Request body for remote delete."""

    session_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    recursive: bool = True
