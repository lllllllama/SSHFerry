"""Data models for SSHFerry."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Literal, Optional

from src.shared.errors import ErrorCode


EndpointType = Literal["local", "remote"]


@dataclass
class SiteConfig:
    """Configuration for an SSH site/server connection."""

    name: str
    host: str
    port: int
    username: str
    auth_method: str  # "password" or "key"
    remote_root: str  # Sandbox root directory (e.g., /root/autodl-tmp)

    # Auth credentials
    password: Optional[str] = None
    key_path: Optional[str] = None
    key_passphrase: Optional[str] = None
    remember_password: bool = False

    # Advanced SSH options
    proxy_jump: Optional[str] = None
    ssh_config_path: Optional[str] = None
    ssh_options: List[str] = field(default_factory=list)
    default_transfer_protocol: str = "sftp"  # "sftp" or "scp"

    def __post_init__(self):
        """Validate configuration."""
        if self.auth_method not in ("password", "key"):
            raise ValueError(f"Invalid auth_method: {self.auth_method}")
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")
        if self.default_transfer_protocol not in ("sftp", "scp"):
            raise ValueError(
                f"Invalid default_transfer_protocol: {self.default_transfer_protocol}"
            )


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
class TaskEndpoint:
    """Represents one side of a transfer task."""

    endpoint_type: EndpointType
    path: str
    session_id: Optional[str] = None
    site: Optional[SiteConfig] = None
    display_name: Optional[str] = None

    @property
    def label(self) -> str:
        if self.endpoint_type == "local":
            return f"local:{self.path}"
        site_name = self.display_name or (self.site.name if self.site else self.session_id) or "remote"
        return f"{site_name}:{self.path}"


@dataclass
class Task:
    """Represents a file operation or transfer task."""

    task_id: str
    kind: str  # "file_transfer", "folder_transfer", "delete", "mkdir", "rename"
    engine: str  # "sftp", "parallel", or "scp"
    src: str
    dst: str
    bytes_total: int
    src_endpoint_type: EndpointType = "local"
    dst_endpoint_type: EndpointType = "remote"
    src_session_id: Optional[str] = None
    dst_session_id: Optional[str] = None
    src_site_snapshot: Optional[SiteConfig] = None
    dst_site_snapshot: Optional[SiteConfig] = None
    src_display_name: Optional[str] = None
    dst_display_name: Optional[str] = None

    bytes_done: int = 0
    status: str = "pending"  # pending, running, paused, done, failed, canceled, skipped
    retries: int = 0
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    checkpoint_path: Optional[str] = None
    start_time: Optional[float] = None  # Unix timestamp when task started
    end_time: Optional[float] = None    # Unix timestamp when task finished
    speed: float = 0.0  # Current transfer speed in bytes/sec
    interrupted: bool = False  # Flag for graceful interruption
    paused: bool = False  # Flag for graceful pause (used by scheduler)
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
        return self.status in ("done", "failed", "canceled", "skipped")

    def __str__(self) -> str:
        return (
            f"Task({self.task_id[:8]}, {self.kind}, {self.status}, "
            f"{self.progress_percent:.1f}%)"
        )

    @property
    def src_endpoint(self) -> TaskEndpoint:
        return TaskEndpoint(
            endpoint_type=self.src_endpoint_type,
            path=self.src,
            session_id=self.src_session_id,
            site=self.src_site_snapshot,
            display_name=self.src_display_name,
        )

    @property
    def dst_endpoint(self) -> TaskEndpoint:
        return TaskEndpoint(
            endpoint_type=self.dst_endpoint_type,
            path=self.dst,
            session_id=self.dst_session_id,
            site=self.dst_site_snapshot,
            display_name=self.dst_display_name,
        )

    @property
    def is_remote_to_remote(self) -> bool:
        return self.src_endpoint_type == "remote" and self.dst_endpoint_type == "remote"

    @property
    def is_local_to_remote(self) -> bool:
        return self.src_endpoint_type == "local" and self.dst_endpoint_type == "remote"

    @property
    def is_remote_to_local(self) -> bool:
        return self.src_endpoint_type == "remote" and self.dst_endpoint_type == "local"
