"""Tests for TOFU host key management and ProxyJump parsing."""
from __future__ import annotations

from pathlib import Path

import paramiko
import pytest

from src.engines.sftp_engine import _parse_proxy_jump
from src.shared import host_keys


@pytest.fixture
def isolated_store(monkeypatch, tmp_path: Path):
    store = tmp_path / "known_hosts"
    monkeypatch.setattr(host_keys, "known_hosts_path", lambda: store)
    monkeypatch.delenv("SSHFERRY_STRICT_HOSTKEY", raising=False)
    return store


def _make_key() -> paramiko.PKey:
    return paramiko.RSAKey.generate(1024)


def test_fingerprint_is_stable_sha256(isolated_store):
    key = _make_key()
    fp = host_keys.fingerprint(key)
    assert fp.startswith("SHA256:")
    assert host_keys.fingerprint(key) == fp


def test_tofu_policy_records_new_host(isolated_store):
    client = paramiko.SSHClient()
    key = _make_key()
    host_keys.TofuHostKeyPolicy().missing_host_key(client, "example.com", key)

    assert isolated_store.exists()
    stored = paramiko.HostKeys(str(isolated_store))
    assert stored.lookup("example.com") is not None
    # The in-memory client now trusts the key for the rest of the session.
    assert client.get_host_keys().lookup("example.com") is not None


def test_tofu_policy_invokes_new_host_callback(isolated_store):
    seen = []
    client = paramiko.SSHClient()
    key = _make_key()
    policy = host_keys.TofuHostKeyPolicy(on_new_host=lambda host, k: seen.append((host, k)))
    policy.missing_host_key(client, "host.example", key)
    assert [h for h, _ in seen] == ["host.example"]


def test_record_merges_without_dropping_existing_hosts(isolated_store):
    client_a = paramiko.SSHClient()
    client_b = paramiko.SSHClient()
    host_keys.TofuHostKeyPolicy().missing_host_key(client_a, "host-a", _make_key())
    host_keys.TofuHostKeyPolicy().missing_host_key(client_b, "host-b", _make_key())

    stored = paramiko.HostKeys(str(isolated_store))
    assert stored.lookup("host-a") is not None
    assert stored.lookup("host-b") is not None


def test_install_policy_uses_reject_in_strict_mode(isolated_store, monkeypatch):
    monkeypatch.setenv("SSHFERRY_STRICT_HOSTKEY", "1")
    client = paramiko.SSHClient()
    host_keys.install_policy(client)
    assert isinstance(client._policy, paramiko.RejectPolicy)


def test_install_policy_uses_tofu_by_default(isolated_store):
    client = paramiko.SSHClient()
    host_keys.install_policy(client)
    assert isinstance(client._policy, host_keys.TofuHostKeyPolicy)


def test_load_known_hosts_tolerates_missing_and_corrupt(isolated_store):
    client = paramiko.SSHClient()
    # Missing file: no error.
    host_keys.load_known_hosts(client)
    # Corrupt file: still no error.
    isolated_store.write_text("this is not a known_hosts line\n", encoding="utf-8")
    host_keys.load_known_hosts(client)


def test_is_strict_mode_reads_env(isolated_store, monkeypatch):
    monkeypatch.setenv("SSHFERRY_STRICT_HOSTKEY", "on")
    assert host_keys.is_strict_mode() is True
    monkeypatch.setenv("SSHFERRY_STRICT_HOSTKEY", "0")
    assert host_keys.is_strict_mode() is False


@pytest.mark.parametrize(
    "spec, default_user, expected",
    [
        ("jump.example.com", "alice", ("alice", "jump.example.com", 22)),
        ("bob@jump.example.com", "alice", ("bob", "jump.example.com", 22)),
        ("bob@jump.example.com:2222", "alice", ("bob", "jump.example.com", 2222)),
        ("jump.example.com:2200", "alice", ("alice", "jump.example.com", 2200)),
        ("[2001:db8::1]:2222", "alice", ("alice", "2001:db8::1", 2222)),
        ("[2001:db8::1]", "alice", ("alice", "2001:db8::1", 22)),
    ],
)
def test_parse_proxy_jump(spec, default_user, expected):
    assert _parse_proxy_jump(spec, default_user=default_user) == expected
