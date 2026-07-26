"""Trust-on-first-use (TOFU) host key management.

Replaces paramiko's blind ``AutoAddPolicy`` with a policy that records each
server's key on first contact and then detects any later change — the
signal of a possible man-in-the-middle attack. Keys are stored in an
OpenSSH-compatible ``known_hosts`` file under the app data directory, so
they interoperate with the user's existing SSH trust store.
"""
from __future__ import annotations

import base64
import hashlib
import os
import threading
from collections.abc import Callable
from pathlib import Path

import paramiko

from src.shared.runtime_paths import app_data_dir

_HOSTS_FILENAME = "known_hosts"
# Serializes read-modify-write of the shared known_hosts file so concurrent
# first-time connections (e.g. parallel SFTP workers) cannot clobber it.
_save_lock = threading.Lock()

_TRUTHY = ("1", "true", "yes", "on")


def known_hosts_path() -> Path:
    """Path to SSHFerry's managed known_hosts file."""
    return app_data_dir() / _HOSTS_FILENAME


def is_strict_mode() -> bool:
    """Whether unknown hosts must already be trusted (no TOFU auto-add)."""
    return os.getenv("SSHFERRY_STRICT_HOSTKEY", "").strip().lower() in _TRUTHY


def fingerprint(key: paramiko.PKey) -> str:
    """Return the OpenSSH-style SHA256 fingerprint of a host key."""
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def load_known_hosts(client: paramiko.SSHClient) -> None:
    """Load the user's system known_hosts and SSHFerry's managed store.

    System keys are loaded first (read-only) so hosts the user already
    trusts via OpenSSH are recognized and their changes still detected.
    """
    try:
        client.load_system_host_keys()
    except Exception:
        # A missing or malformed ~/.ssh/known_hosts must not block connects.
        pass
    path = known_hosts_path()
    if path.exists():
        try:
            client.load_host_keys(str(path))
        except Exception:
            # Corrupt managed store: fall back to re-recording via TOFU
            # rather than refusing every connection.
            pass


def _record_host_key(hostname: str, key: paramiko.PKey) -> None:
    """Merge one host key into the managed store on disk, atomically wrt peers."""
    with _save_lock:
        path = known_hosts_path()
        merged = paramiko.HostKeys()
        if path.exists():
            try:
                merged.load(str(path))
            except Exception:
                merged = paramiko.HostKeys()
        merged.add(hostname, key.get_name(), key)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged.save(str(path))


class TofuHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Accept a host's key on first sight and persist it for later checks."""

    def __init__(self, on_new_host: Callable[[str, paramiko.PKey], None] | None = None):
        self._on_new_host = on_new_host

    def missing_host_key(self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey) -> None:
        _record_host_key(hostname, key)
        # Trust the key for the remainder of this connection too.
        client.get_host_keys().add(hostname, key.get_name(), key)
        if self._on_new_host is not None:
            try:
                self._on_new_host(hostname, key)
            except Exception:
                pass


def install_policy(
    client: paramiko.SSHClient,
    *,
    on_new_host: Callable[[str, paramiko.PKey], None] | None = None,
) -> None:
    """Load trusted keys and install the appropriate missing-key policy."""
    load_known_hosts(client)
    if is_strict_mode():
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(TofuHostKeyPolicy(on_new_host))
