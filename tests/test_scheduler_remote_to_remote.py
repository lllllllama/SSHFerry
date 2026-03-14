from unittest.mock import MagicMock, patch

from src.core.scheduler import TaskScheduler
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import SiteConfig, Task


def _site(name: str) -> SiteConfig:
    return SiteConfig(
        name=name,
        host=f"{name}.example.com",
        port=22,
        username="user",
        auth_method="key",
        key_path="/tmp/key",
        remote_root="/data",
    )


def test_create_remote_to_remote_task_sets_endpoint_metadata():
    src_site = _site("src")
    dst_site = _site("dst")

    task = TaskScheduler.create_remote_to_remote_task(
        "/data/a.bin",
        "/data/b.bin",
        123,
        src_site=src_site,
        dst_site=dst_site,
    )

    assert task.kind == "file_transfer"
    assert task.is_remote_to_remote is True
    assert task.src_site_snapshot == src_site
    assert task.dst_site_snapshot == dst_site
    assert task.src_endpoint.label == "src:/data/a.bin"
    assert task.dst_endpoint.label == "dst:/data/b.bin"


def test_execute_remote_to_remote_file_uses_remote_transfer_engine():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(logger=MagicMock())

    task = Task(
        task_id="r2r1",
        kind="file_transfer",
        engine="sftp",
        src="/data/a.bin",
        dst="/data/b.bin",
        bytes_total=10,
        src_endpoint_type="remote",
        dst_endpoint_type="remote",
        src_site_snapshot=src_site,
        dst_site_snapshot=dst_site,
        src_display_name="src",
        dst_display_name="dst",
    )

    called = {"count": 0}

    class FakeRemoteTransferEngine:
        def __init__(
            self,
            got_src,
            got_dst,
            _logger,
            parallel_threshold=None,
            relay_download_preset=None,
            relay_upload_preset=None,
        ):
            assert got_src == src_site
            assert got_dst == dst_site
            assert parallel_threshold == scheduler.parallel_threshold
            assert relay_download_preset == scheduler.parallel_download_preset
            assert relay_upload_preset == scheduler.parallel_upload_preset

        def transfer_file(self, src, dst, callback=None, check_interrupt=None):
            called["count"] += 1
            assert src == "/data/a.bin"
            assert dst == "/data/b.bin"
            if callback:
                callback(10, 10)

    with patch("src.core.scheduler.RemoteToRemoteTransferEngine", FakeRemoteTransferEngine):
        scheduler._execute_remote_to_remote_file(task)

    assert called["count"] == 1
    assert task.bytes_done == 10


def test_remote_to_remote_engine_fallback_to_relay_on_direct_failure():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            MagicMock(),
            parallel_threshold=1024,
        )

        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=10), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct",
            side_effect=SSHFerryError(ErrorCode.TRANSFER_FAILED, "boom"),
        ), patch.object(RemoteToRemoteTransferEngine, "_transfer_file_relay") as relay:
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin")

    assert mode == "bridge"
    relay.assert_called_once()


def test_remote_to_remote_large_file_prefers_parallel_bridge():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"), patch(
        "src.engines.remote_transfer_engine.RemoteToRemoteTransferEngine._transfer_file_parallel_bridge"
    ) as bridge:
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
        )
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=128):
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin")

    assert mode == "parallel_bridge"
    bridge.assert_called_once()


def test_remote_to_remote_bridge_uses_parallel_workers_for_large_file():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine") as mock_sftp_cls, patch(
        "src.engines.remote_transfer_engine.ParallelSftpEngine"
    ) as mock_parallel_cls:
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        init_dst = MagicMock()
        src_worker = MagicMock()
        dst_worker = MagicMock()
        mock_sftp_cls.side_effect = [init_dst, src_worker, dst_worker]

        dst_file = MagicMock()
        init_dst.sftp_client.open.return_value.__enter__.return_value = dst_file

        src_data = b"x" * 64
        src_file = MagicMock()
        src_file.read.side_effect = [src_data, b""]
        src_worker.sftp_client.open.return_value.__enter__.return_value = src_file

        dst_worker_file = MagicMock()
        dst_worker.sftp_client.open.return_value.__enter__.return_value = dst_worker_file

        parallel_instance = MagicMock()
        parallel_instance.max_workers = 1
        parallel_instance.chunk_size = 64
        mock_parallel_cls.side_effect = [parallel_instance, parallel_instance]

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
        )
        engine._transfer_file_parallel_bridge("/data/a.bin", "/data/b.bin", 64)

    src_file.seek.assert_called_with(0)
    dst_worker_file.seek.assert_called_with(0)
    dst_worker_file.write.assert_called_once_with(src_data)
    assert mock_parallel_cls.call_count == 2
