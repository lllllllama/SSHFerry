"""SCP engine for file transfer operations using Paramiko + scp."""
import logging
import os
from pathlib import Path
from typing import Callable, Optional

import paramiko
try:
    from scp import SCPClient, SCPException
except Exception:  # pragma: no cover - exercised only when dependency is missing
    SCPClient = None

    class SCPException(Exception):
        """Fallback exception when scp dependency is unavailable."""

from src.shared.errors import (
    AuthenticationError,
    ErrorCode,
    NetworkError,
    SSHFerryError,
)
from src.engines.sftp_engine import _parse_proxy_jump
from src.shared.host_keys import fingerprint, install_policy
from src.shared.models import SiteConfig
from src.shared.paths import ensure_in_sandbox, normalize_remote_path, to_local_fs_path


class ScpEngine:
    """SCP transfer engine using a single SSH connection."""

    def __init__(self, site_config: SiteConfig, logger: Optional[logging.Logger] = None):
        self.site_config = site_config
        self.logger = logger or logging.getLogger(__name__)
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.scp_client: Optional[SCPClient] = None
        self._proxy_client: Optional[paramiko.SSHClient] = None
        self._connected = False

    def connect(self) -> None:
        """Establish SSH and SCP connections."""
        try:
            self.ssh_client = paramiko.SSHClient()
            install_policy(self.ssh_client)
            connect_kwargs = {
                "hostname": self.site_config.host,
                "port": self.site_config.port,
                "username": self.site_config.username,
                "timeout": 10,
                "allow_agent": True,
                "look_for_keys": True,
            }

            if self.site_config.auth_method == "password":
                connect_kwargs["password"] = self.site_config.password
            elif self.site_config.auth_method == "key":
                if self.site_config.key_path:
                    connect_kwargs["key_filename"] = self.site_config.key_path
                if self.site_config.key_passphrase:
                    connect_kwargs["passphrase"] = self.site_config.key_passphrase

            proxy_sock = self._open_proxy_channel()
            if proxy_sock is not None:
                connect_kwargs["sock"] = proxy_sock
            self.ssh_client.connect(**connect_kwargs)
            if SCPClient is None:
                raise SSHFerryError(
                    ErrorCode.UNKNOWN_ERROR,
                    "scp dependency missing. Install with: pip install scp",
                )
            buff_size = 1024 * 1024
            try:
                buff_size = max(64 * 1024, int(os.getenv("SSHFERRY_SCP_BUFF_BYTES", "") or buff_size))
            except ValueError:
                pass
            try:
                # The 16 KB default causes small socket writes and a progress
                # callback per 16 KB.
                self.scp_client = SCPClient(self.ssh_client.get_transport(), buff_size=buff_size)
            except TypeError:
                self.scp_client = SCPClient(self.ssh_client.get_transport())
            self._connected = True
            self.logger.info(f"SCP connected to {self.site_config.host}:{self.site_config.port}")
        except paramiko.BadHostKeyException as e:
            raise SSHFerryError(
                ErrorCode.HOSTKEY_CHANGED,
                f"Host key verification failed for {self.site_config.host}:{self.site_config.port}. "
                f"The server key changed and may indicate a man-in-the-middle attack. "
                f"Expected {fingerprint(e.expected_key)}, got {fingerprint(e.key)}.",
            )
        except paramiko.AuthenticationException as e:
            raise AuthenticationError(f"Authentication failed: {e}")
        except paramiko.SSHException as e:
            if "not found in known_hosts" in str(e):
                raise SSHFerryError(
                    ErrorCode.HOSTKEY_UNKNOWN,
                    f"Host {self.site_config.host}:{self.site_config.port} is not in known_hosts "
                    f"and strict host key checking is enabled.",
                )
            raise NetworkError(ErrorCode.REMOTE_DISCONNECT, f"SSH error: {e}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.UNKNOWN_ERROR, f"SCP connection failed: {e}")

    def _open_proxy_channel(self):
        """Open a direct-tcpip channel through the configured ProxyJump host."""
        proxy_spec = (self.site_config.proxy_jump or "").strip()
        if not proxy_spec:
            return None

        proxy_user, proxy_host, proxy_port = _parse_proxy_jump(
            proxy_spec, default_user=self.site_config.username
        )
        proxy_kwargs = {
            "hostname": proxy_host,
            "port": proxy_port,
            "username": proxy_user,
            "timeout": 10,
            "allow_agent": True,
            "look_for_keys": True,
        }
        if self.site_config.auth_method == "password":
            proxy_kwargs["password"] = self.site_config.password
        elif self.site_config.auth_method == "key":
            if self.site_config.key_path:
                proxy_kwargs["key_filename"] = self.site_config.key_path
            if self.site_config.key_passphrase:
                proxy_kwargs["passphrase"] = self.site_config.key_passphrase

        self._proxy_client = paramiko.SSHClient()
        install_policy(self._proxy_client)
        self._proxy_client.connect(**proxy_kwargs)
        transport = self._proxy_client.get_transport()
        if transport is None:
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Jump host transport unavailable")
        return transport.open_channel(
            "direct-tcpip",
            (self.site_config.host, self.site_config.port),
            ("", 0),
        )

    def disconnect(self) -> None:
        """Close SCP and SSH connections."""
        if self.scp_client:
            self.scp_client.close()
            self.scp_client = None
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None
        if self._proxy_client:
            self._proxy_client.close()
            self._proxy_client = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self.ssh_client is not None and self.scp_client is not None

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        callback: Optional[Callable] = None,
        check_interrupt: Optional[Callable] = None,
    ) -> None:
        """Upload file with SCP. Semantics are overwrite-by-default."""
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)
        fs_local_path = to_local_fs_path(local_path)
        file_size = os.path.getsize(fs_local_path)

        def _progress(_filename: str, size: int, sent: int):
            if check_interrupt and check_interrupt():
                raise InterruptedError("Transfer interrupted")
            if callback:
                callback(sent, size)

        try:
            self.scp_client.put(
                fs_local_path,
                remote_path=normalized_path,
                recursive=False,
                preserve_times=True,
                progress=_progress,
            )
            if callback and file_size == 0:
                callback(0, 0)
        except InterruptedError:
            raise
        except SCPException as e:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"SCP upload failed: {e}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"SCP upload failed: {e}")

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable] = None,
        check_interrupt: Optional[Callable] = None,
    ) -> None:
        """Download file with SCP. Semantics are overwrite-by-default."""
        if not self.is_connected():
            raise SSHFerryError(ErrorCode.REMOTE_DISCONNECT, "Not connected")

        ensure_in_sandbox(remote_path, self.site_config.remote_root)
        normalized_path = normalize_remote_path(remote_path)
        fs_local_path = to_local_fs_path(local_path)
        Path(fs_local_path).parent.mkdir(parents=True, exist_ok=True)

        def _progress(_filename: str, size: int, sent: int):
            if check_interrupt and check_interrupt():
                raise InterruptedError("Transfer interrupted")
            if callback:
                callback(sent, size)

        try:
            self.scp_client.get(
                normalized_path,
                local_path=fs_local_path,
                recursive=False,
                preserve_times=True,
                progress=_progress,
            )
        except InterruptedError:
            raise
        except SCPException as e:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"SCP download failed: {e}")
        except Exception as e:
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, f"SCP download failed: {e}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
