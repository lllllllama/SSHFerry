"""Error codes and exceptions for SSHFerry."""
from enum import Enum, auto


class ErrorCode(Enum):
    """Enumeration of all possible error codes in the application."""

    AUTH_FAILED = auto()
    HOSTKEY_UNKNOWN = auto()
    HOSTKEY_CHANGED = auto()
    PERMISSION_DENIED = auto()
    PATH_NOT_FOUND = auto()
    NETWORK_TIMEOUT = auto()
    REMOTE_DISCONNECT = auto()
    VALIDATION_FAILED = auto()
    MSCP_NOT_FOUND = auto()
    MSCP_EXIT_NONZERO = auto()
    UNKNOWN_ERROR = auto()


class SSHFerryError(Exception):
    """Base exception for SSHFerry errors."""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code.name}] {message}")


class ValidationError(SSHFerryError):
    """Raised when validation fails (e.g., sandbox check)."""

    def __init__(self, message: str):
        super().__init__(ErrorCode.VALIDATION_FAILED, message)


class AuthenticationError(SSHFerryError):
    """Raised when authentication fails."""

    def __init__(self, message: str):
        super().__init__(ErrorCode.AUTH_FAILED, message)


class PermissionError(SSHFerryError):
    """Raised when permission is denied."""

    def __init__(self, message: str):
        super().__init__(ErrorCode.PERMISSION_DENIED, message)


class PathNotFoundError(SSHFerryError):
    """Raised when a path is not found."""

    def __init__(self, message: str):
        super().__init__(ErrorCode.PATH_NOT_FOUND, message)


class NetworkError(SSHFerryError):
    """Raised when network issues occur."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(code, message)
