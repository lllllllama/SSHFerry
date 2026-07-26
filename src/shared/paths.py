"""Path utilities and sandbox validation for SSHFerry."""
import ntpath
import os
import posixpath
import sys
from typing import Optional

from src.shared.errors import ValidationError


def normalize_remote_path(path: str) -> str:
    """
    Normalize a remote path by:
    - Converting to POSIX format
    - Resolving . and .. components
    - Removing duplicate slashes
    - Ensuring absolute path
    
    Args:
        path: Remote path to normalize
        
    Returns:
        Normalized absolute path
    """
    # Use posixpath since remote is always POSIX
    normalized = posixpath.normpath(path)

    # Ensure absolute path
    if not normalized.startswith('/'):
        normalized = '/' + normalized

    # posixpath.normpath preserves leading // (POSIX implementation-defined).
    # We always want a single leading slash.
    while normalized.startswith('//'):
        normalized = normalized[1:]

    return normalized


def to_local_fs_path(path: str | os.PathLike[str]) -> str:
    """
    Return a local filesystem path suitable for OS calls.

    Windows uses the extended-length prefix so deep download trees can exceed
    MAX_PATH without failing during mkdir/open/getsize calls.
    """
    raw = os.fspath(path)
    if sys.platform != "win32" or not raw:
        return raw

    # Use ntpath explicitly (== os.path on Windows) so Windows semantics hold
    # even when sys.platform is patched in cross-platform tests.
    normalized = ntpath.normpath(raw)
    if normalized.startswith("\\\\?\\") or normalized.startswith("\\\\.\\"):
        return normalized

    absolute = normalized if ntpath.isabs(normalized) else ntpath.abspath(normalized)
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute.lstrip("\\")
    return "\\\\?\\" + absolute


def ensure_in_sandbox(path: str, remote_root: str) -> None:
    """
    Verify that a path is within the sandbox (remote_root).
    
    This is a critical security check that must be called before any
    dangerous remote operations (rm, rmdir, rename, mkdir, upload, download).
    
    Args:
        path: Remote path to check (will be normalized)
        remote_root: Sandbox root directory
        
    Raises:
        ValidationError: If path is outside sandbox
    """
    normalized_path = normalize_remote_path(path)
    normalized_root = normalize_remote_path(remote_root)

    # Root sandbox means full filesystem scope.
    if normalized_root == '/':
        return

    # Check if path is exactly root or starts with root/
    if normalized_path == normalized_root:
        return

    if normalized_path.startswith(normalized_root + '/'):
        return

    raise ValidationError(
        f"Path '{path}' is outside sandbox '{remote_root}'. "
        f"Normalized: '{normalized_path}' vs root '{normalized_root}'"
    )


def join_remote_path(*parts: str) -> str:
    """
    Join remote path components using POSIX conventions.
    
    Args:
        *parts: Path components to join
        
    Returns:
        Joined path
    """
    return posixpath.join(*parts)


def get_remote_parent(path: str) -> Optional[str]:
    """
    Get the parent directory of a remote path.
    
    Args:
        path: Remote path
        
    Returns:
        Parent directory or None if at root
    """
    normalized = normalize_remote_path(path)
    if normalized == '/':
        return None
    parent = posixpath.dirname(normalized)
    return parent if parent else '/'


def get_remote_basename(path: str) -> str:
    """
    Get the basename (filename) of a remote path.
    
    Args:
        path: Remote path
        
    Returns:
        Basename
    """
    return posixpath.basename(path)
