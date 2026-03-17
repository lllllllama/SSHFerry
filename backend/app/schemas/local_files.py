"""Pydantic schemas for local file system APIs."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LocalDriveResponse(BaseModel):
    """One available local drive or root entry."""

    path: str
    label: str


class LocalDrivesListResponse(BaseModel):
    """List wrapper for available local drives."""

    items: list[LocalDriveResponse]
    total: int


class LocalEntryResponse(BaseModel):
    """Sanitized local file system entry."""

    name: str
    path: str
    is_dir: bool
    size: int
    mtime: float
    exists: bool = True


class LocalListResponse(BaseModel):
    """Directory listing response."""

    current_path: str
    parent_path: str | None
    items: list[LocalEntryResponse]
    total: int


class LocalStatResponse(BaseModel):
    """Path stat response."""

    entry: LocalEntryResponse


class LocalPathQuery(BaseModel):
    """Shared query payload placeholder for documentation consistency."""

    path: str = Field(min_length=1)
