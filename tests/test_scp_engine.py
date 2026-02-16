"""Tests for SCP engine behavior."""
from pathlib import Path

import pytest

from src.engines.scp_engine import ScpEngine, SCPException
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import SiteConfig


class _FakeSSHClient:
    def __init__(self):
        self.connected = False

    def set_missing_host_key_policy(self, _policy):
        return None

    def connect(self, **_kwargs):
        self.connected = True

    def get_transport(self):
        return object()

    def close(self):
        self.connected = False


class _FakeSCPClient:
    def __init__(self, _transport):
        self.closed = False
        self.raise_on_put = False

    def put(self, local_path, remote_path=None, recursive=False, preserve_times=True, progress=None):
        if self.raise_on_put:
            raise SCPException("put failed")
        size = Path(local_path).stat().st_size
        if progress:
            progress(remote_path or local_path, size, size)

    def get(self, remote_path, local_path=None, recursive=False, preserve_times=True, progress=None):
        size = 8
        Path(local_path).write_bytes(b"download")
        if progress:
            progress(remote_path, size, size)

    def close(self):
        self.closed = True


def _site() -> SiteConfig:
    return SiteConfig(
        name="test",
        host="localhost",
        port=22,
        username="user",
        auth_method="password",
        password="pwd",
        remote_root="/sandbox",
    )


def test_scp_upload_download_progress(monkeypatch, tmp_path):
    monkeypatch.setattr("src.engines.scp_engine.paramiko.SSHClient", _FakeSSHClient)
    monkeypatch.setattr("src.engines.scp_engine.SCPClient", _FakeSCPClient)
    engine = ScpEngine(_site())
    engine.connect()

    local_src = tmp_path / "a.bin"
    local_src.write_bytes(b"12345678")
    local_dst = tmp_path / "b.bin"

    seen = {"up": None, "down": None}
    engine.upload_file(
        str(local_src),
        "/sandbox/a.bin",
        callback=lambda done, total: seen.update({"up": (done, total)}),
    )
    engine.download_file(
        "/sandbox/a.bin",
        str(local_dst),
        callback=lambda done, total: seen.update({"down": (done, total)}),
    )
    engine.disconnect()

    assert seen["up"] == (8, 8)
    assert seen["down"] == (8, 8)
    assert local_dst.read_bytes() == b"download"


def test_scp_upload_interrupt(monkeypatch, tmp_path):
    monkeypatch.setattr("src.engines.scp_engine.paramiko.SSHClient", _FakeSSHClient)
    monkeypatch.setattr("src.engines.scp_engine.SCPClient", _FakeSCPClient)
    engine = ScpEngine(_site())
    engine.connect()

    local_src = tmp_path / "a.bin"
    local_src.write_bytes(b"12345678")
    with pytest.raises(InterruptedError):
        engine.upload_file(
            str(local_src),
            "/sandbox/a.bin",
            check_interrupt=lambda: True,
        )


def test_scp_upload_maps_scp_exception(monkeypatch, tmp_path):
    monkeypatch.setattr("src.engines.scp_engine.paramiko.SSHClient", _FakeSSHClient)

    class _FailingSCPClient(_FakeSCPClient):
        def __init__(self, transport):
            super().__init__(transport)
            self.raise_on_put = True

    monkeypatch.setattr("src.engines.scp_engine.SCPClient", _FailingSCPClient)
    engine = ScpEngine(_site())
    engine.connect()
    local_src = tmp_path / "a.bin"
    local_src.write_bytes(b"12345678")

    with pytest.raises(SSHFerryError) as exc:
        engine.upload_file(str(local_src), "/sandbox/a.bin")
    assert exc.value.code == ErrorCode.TRANSFER_FAILED
