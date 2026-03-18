"""Pydantic schemas for log APIs."""
from __future__ import annotations

from pydantic import BaseModel


class LogEntryResponse(BaseModel):
    """Single log line returned to the frontend."""

    sequence: int
    timestamp: float
    level: str
    logger: str
    message: str
    rendered: str


class LogListResponse(BaseModel):
    """List wrapper for log entries."""

    items: list[LogEntryResponse]
    total: int
    sequence: int