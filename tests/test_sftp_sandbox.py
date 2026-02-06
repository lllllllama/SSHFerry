"""Tests for SFTP sandbox enforcement (mocked – no real server needed)."""
from unittest.mock import MagicMock

import pytest

from src.shared.errors import ValidationError
from src.shared.models import SiteConfig


def _make_site(**overrides) -> SiteConfig:
    defaults = dict(
        name="test",
        host="localhost",
        port=22,
        username="user",
        auth_method="password",
        remote_root="/root/autodl-tmp",
    )
    defaults.update(overrides)
    return SiteConfig(**defaults)


def _make_engine():
    """Create an SftpEngine that appears connected (fully mocked)."""
    from src.engines.sftp_engine import SftpEngine

    engine = SftpEngine(_make_site())
    engine._connected = True
    engine.ssh_client = MagicMock()
    engine.sftp_client = MagicMock()
    return engine


class TestSftpEngineSandbox:
    """Ensure SftpEngine rejects operations outside the sandbox."""

    def test_list_dir_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.list_dir("/etc")

    def test_mkdir_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.mkdir("/tmp/evil")

    def test_remove_file_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.remove_file("/etc/passwd")

    def test_remove_dir_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.remove_dir("/root")

    def test_rename_src_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.rename("/etc/hosts", "/root/autodl-tmp/hosts")

    def test_rename_dst_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.rename("/root/autodl-tmp/file", "/tmp/file")

    def test_upload_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.upload_file("local.txt", "/tmp/remote.txt")

    def test_download_outside_sandbox_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.download_file("/etc/passwd", "local.txt")

    def test_dotdot_escape_rejected(self):
        engine = _make_engine()
        with pytest.raises(ValidationError):
            engine.list_dir("/root/autodl-tmp/../../etc")

    def test_inside_sandbox_allowed(self):
        engine = _make_engine()
        engine.sftp_client.listdir_attr.return_value = []
        result = engine.list_dir("/root/autodl-tmp/subdir")
        assert result == []
