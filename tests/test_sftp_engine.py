from unittest.mock import MagicMock
from types import SimpleNamespace

from src.engines.sftp_engine import SftpEngine
from src.shared.models import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="demo",
        host="example.com",
        port=22,
        username="alice",
        auth_method="password",
        password="secret",
        remote_root="/remote",
    )


def test_disconnect_without_successful_connect_does_not_log():
    logger = MagicMock()
    engine = SftpEngine(_site(), logger=logger)

    engine.disconnect()

    logger.info.assert_not_called()


def test_list_dir_keeps_directory_symlink_from_becoming_directory():
    logger = MagicMock()
    engine = SftpEngine(_site(), logger=logger)
    engine._connected = True
    engine.ssh_client = object()
    symlink_attr = SimpleNamespace(
        filename="linked-dir",
        st_mode=0o120777,
        st_size=9,
        st_mtime=10,
    )
    engine.sftp_client = SimpleNamespace(
        listdir_attr=lambda _path: [symlink_attr],
    )

    entries = engine.list_dir("/remote")

    assert len(entries) == 1
    assert entries[0].is_dir is False
    assert entries[0].path == "/remote/linked-dir"
    assert entries[0].mode == 0o120777
