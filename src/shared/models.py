"""Data models for SSHFerry."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from src.shared.errors import ErrorCode


@dataclass
class SiteConfig:
    """Configuration for an SSH site/server connection."""

    name: str
    host: str
    port: int
    username: str
    auth_method: str  # "password" or "key"
    remote_root: str  # Sandbox root directory (e.g., /root/autodl-tmp)

    # Auth credentials (runtime only, not persisted)
    password: Optional[str] = None
    key_path: Optional[str] = None
    key_passphrase: Optional[str] = None

    # MSCP configuration
    mscp_path: Optional[str] = None

    # Advanced SSH options
    proxy_jump: Optional[str] = None
    ssh_config_path: Optional[str] = None
    ssh_options: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate configuration."""
        if self.auth_method not in ("password", "key"):
            raise ValueError(f"Invalid auth_method: {self.auth_method}")
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")


@dataclass
class RemoteEntry:
    """Represents a file or directory on the remote server."""

    name: str
    path: str
    is_dir: bool
    size: int
    mtime: float  # Unix timestamp
    mode: Optional[int] = None

    @property
    def mtime_datetime(self) -> datetime:
        """Get modification time as datetime."""
        return datetime.fromtimestamp(self.mtime)

    def __str__(self) -> str:
        type_str = "DIR" if self.is_dir else "FILE"
        return f"{type_str} {self.name} ({self.size} bytes)"


@dataclass
class Task:
    """Represents a file operation or transfer task."""

    task_id: str
    kind: str  # "upload", "download", "delete", "mkdir", "rename"
    engine: str  # "sftp" or "mscp"
    src: str
    dst: str
    bytes_total: int

    bytes_done: int = 0
    status: str = "pending"  # pending, running, paused, done, failed, canceled, skipped
    retries: int = 0
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    checkpoint_path: Optional[str] = None  # For mscp resume
    start_time: Optional[float] = None  # Unix timestamp when task started
    speed: float = 0.0  # Current transfer speed in bytes/sec
    interrupted: bool = False  # Flag for graceful interruption
    skipped: bool = False  # File already exists and is complete
    
    # Folder task aggregation fields
    subtask_count: int = 0  # Total number of files in folder
    subtask_done: int = 0   # Number of completed files
    current_file: str = ""  # Currently processing file name

    @property
    def progress_percent(self) -> float:
        """Get progress as percentage (0-100)."""
        if self.bytes_total <= 0:
            return 0.0
        return (self.bytes_done / self.bytes_total) * 100.0

    @property
    def is_finished(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in ("done", "failed", "canceled")

    def __str__(self) -> str:
        return (
            f"Task({self.task_id[:8]}, {self.kind}, {self.status}, "
            f"{self.progress_percent:.1f}%)"
        )
