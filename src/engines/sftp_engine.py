"""SFTP engine for file operations using Paramiko."""
import builtins
import logging
import os
from pathlib import Path
from typing import Callable, Optional

import paramiko
from paramiko import SFTPClient, SSHClient

from src.shared.errors import (
    AuthenticationError,
    ErrorCode,
    NetworkError,
    PathNotFoundError,
    SSHFerryError,
)
from src.shared.errors import PermissionError as SFPermissionError
from src.shared.models import RemoteEntry, SiteConfig
from src.shared.paths import ensure_in_sandbox, normalize_remote_path


class SftpEngine:
    """
    SFTP engine for file management and transfer operations.
    
    Each instance maintains its own SSH/SFTP connection.
    Thread-safe when each thread uses its own instance.
    """

    def __init__(self, site_config: SiteConfig, logger: Optional[logging.Logger] = None):
        """
        Initialize SFTP engine.
        
        Args:
            site_config: Site configuration
            logger: Optional logger instance
        """
        self.site_config = site_config
        self.logger = logger or logging.getLogger(__name__)
        self.ssh_client: Optional[SSHClient] = None
        self.sftp_client: Optional[SFTPClient] = None
        self._connected = False

    def connect(self) -> None:
        """
        Establish SSH and SFTP connections.
        
        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If connection fails
            SSHFerryError: For other connection issues
        """
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Prepare connection kwargs
            connect_kwargs = {
                'hostname': self.site_config.host,
                'port': self.site_config.port,
                'username': self.site_config.username,
                'timeout': 10,
            }

            # Add authentication
            if self.site_config.auth_method == 'password':
                connect_kwargs['password'] = self.site_config.password
            elif self.site_config.auth_method == 'key':
                if self.site_config.key_path:
                    connect_kwargs['key_filename'] = self.site_config.key_path
                if self.site_config.key_passphrase:
                    connect_kwargs['passphrase'] = self.site_config.key_passphrase

            self.ssh_client.connect(**connect_kwargs)
            self.sftp_client = self.ssh_client.open_sftp()
            self._connected = True

            self.logger.info(
                f"Connected to {self.site_config.host}:{self.site_config.port}"
            )

        except paramiko.AuthenticationException as e:
            raise AuthenticationError(f"Authentication failed: {e}")
        except paramiko.SSHException as e:
            raise NetworkError(ErrorCode.REMOTE_DISCONNECT, f"SSH error: {e}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Connection failed: {e}")

    def disconnect(self) -> None:
        """Close SSH and SFTP connections."""
        if self.sftp_client:
            self.sftp_client.close()
            self.sftp_client = None
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
        self._connected = False
        self.logger.info("Disconnected from server")

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self.ssh_client is not None

    def list_dir(self, remote_path: str) -> list[RemoteEntry]:
        """
        List directory contents.
        
        Args:
            remote_path: Remote directory path
            
        Returns:
            List of RemoteEntry objects
            
        Raises:
            PathNotFoundError: If path doesn't exist
            PermissionError: If permission denied
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        # Sandbox check
        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)

        try:
            entries = []
            for attr in self.sftp_client.listdir_attr(normalized_path):
                entry = RemoteEntry(
                    name=attr.filename,
                    path=f"{normalized_path}/{attr.filename}".replace('//', '/'),
                    is_dir=attr.st_mode is not None and (attr.st_mode & 0o170000) == 0o040000,
                    size=attr.st_size or 0,
                    mtime=attr.st_mtime or 0,
                    mode=attr.st_mode,
                )
                entries.append(entry)

            return entries

        except FileNotFoundError:
            raise PathNotFoundError(f"Path not found: {remote_path}")
        except builtins.PermissionError:
            raise SFPermissionError(f"Permission denied: {remote_path}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to list directory: {e}")

    def mkdir(self, remote_path: str) -> None:
        """
        Create remote directory.
        
        Args:
            remote_path: Remote directory path to create
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)

        try:
            self.sftp_client.mkdir(normalized_path)
            self.logger.info(f"Created directory: {normalized_path}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to create directory: {e}")

    def remove_file(self, remote_path: str) -> None:
        """
        Remove remote file.
        
        Args:
            remote_path: Remote file path to remove
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)

        try:
            self.sftp_client.remove(normalized_path)
            self.logger.info(f"Removed file: {normalized_path}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to remove file: {e}")

    def remove_dir(self, remote_path: str) -> None:
        """
        Remove remote directory (must be empty).
        
        Args:
            remote_path: Remote directory path to remove
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)

        try:
            self.sftp_client.rmdir(normalized_path)
            self.logger.info(f"Removed directory: {normalized_path}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to remove directory: {e}")

    def rename(self, old_path: str, new_path: str) -> None:
        """
        Rename/move remote file or directory.
        
        Args:
            old_path: Current path
            new_path: New path
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(old_path, self.site_config.remote_root)
        ensure_in_sandbox(new_path, self.site_config.remote_root)

        old_normalized = normalize_remote_path(old_path)
        new_normalized = normalize_remote_path(new_path)

        try:
            self.sftp_client.rename(old_normalized, new_normalized)
            self.logger.info(f"Renamed {old_normalized} -> {new_normalized}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to rename: {e}")

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        callback: Optional[Callable] = None
    ) -> None:
        """
        Upload a file to remote server.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            callback: Optional progress callback(bytes_transferred, bytes_total)
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)

        try:
            self.sftp_client.put(local_path, normalized_path, callback=callback)
            self.logger.info(f"Uploaded {local_path} -> {normalized_path}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to upload file: {e}")

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable] = None
    ) -> None:
        """
        Download a file from remote server.
        
        Args:
            remote_path: Remote file path
            local_path: Local destination path
            callback: Optional progress callback(bytes_transferred, bytes_total)
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)

        try:
            # Ensure local directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            self.sftp_client.get(normalized_path, local_path, callback=callback)
            self.logger.info(f"Downloaded {normalized_path} -> {local_path}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to download file: {e}")

    def stat(self, remote_path: str) -> RemoteEntry:
        """
        Get file/directory attributes.
        
        Args:
            remote_path: Remote path
            
        Returns:
            RemoteEntry with file attributes
        """
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)

        try:
            attr = self.sftp_client.stat(normalized_path)
            name = os.path.basename(normalized_path)
            return RemoteEntry(
                name=name,
                path=normalized_path,
                is_dir=(attr.st_mode & 0o170000) == 0o040000,
                size=attr.st_size or 0,
                mtime=attr.st_mtime or 0,
                mode=attr.st_mode,
            )
        except FileNotFoundError:
            raise PathNotFoundError(f"Path not found: {remote_path}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"Failed to stat path: {e}")

    def check_path_readable(self, remote_path: str) -> bool:
        """
        Check if a remote path is readable.
        
        Args:
            remote_path: Remote path to check
            
        Returns:
            True if readable, False otherwise
        """
        try:
            self.stat(remote_path)
            return True
        except:
            return False

    def check_path_writable(self, remote_path: str) -> bool:
        """
        Check if a remote path is writable by attempting to create a test file.
        
        Args:
            remote_path: Remote directory path to check
            
        Returns:
            True if writable, False otherwise
        """
        if not self.is_connected():
            return False

        try:
            test_file = f"{remote_path}/.sshferry_write_test"
            ensure_in_sandbox(test_file, self.site_config.remote_root)

            # Try to create and remove a test file
            self.sftp_client.open(test_file, 'w').close()
            self.sftp_client.remove(test_file)
            return True
        except:
            return False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
