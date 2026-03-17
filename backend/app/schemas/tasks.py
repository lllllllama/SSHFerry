"""Pydantic schemas for task APIs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TaskEngine = Literal['auto', 'sftp', 'scp', 'parallel']


class TaskResponse(BaseModel):
    """Sanitized task payload exposed to the frontend."""

    task_id: str
    kind: str
    engine: str
    status: str
    src: str
    dst: str
    src_endpoint_type: str
    dst_endpoint_type: str
    src_session_id: str | None = None
    dst_session_id: str | None = None
    src_display_name: str | None = None
    dst_display_name: str | None = None
    src_label: str
    dst_label: str
    bytes_total: int
    bytes_done: int
    progress_percent: float
    speed: float
    retries: int
    error_code: str | None = None
    error_message: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    interrupted: bool
    paused: bool
    skipped: bool
    subtask_count: int
    subtask_done: int
    current_file: str
    is_finished: bool


class TaskListResponse(BaseModel):
    """List wrapper for task items."""

    items: list[TaskResponse]
    total: int


class TaskCreateUploadRequest(BaseModel):
    """Create a local-to-remote transfer task."""

    session_id: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    remote_path: str = Field(min_length=1)
    engine: TaskEngine = 'auto'


class TaskCreateDownloadRequest(BaseModel):
    """Create a remote-to-local transfer task."""

    session_id: str = Field(min_length=1)
    remote_path: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    engine: TaskEngine = 'auto'


class TaskCreateRemoteCopyRequest(BaseModel):
    """Create a remote-to-remote transfer task."""

    src_session_id: str = Field(min_length=1)
    dst_session_id: str = Field(min_length=1)
    src_path: str = Field(min_length=1)
    dst_path: str = Field(min_length=1)
    engine: TaskEngine = 'auto'


class TaskActionResponse(BaseModel):
    """Result of a task control action."""

    task_id: str
    action: str
    status: str

