from unittest.mock import MagicMock, patch
from types import SimpleNamespace

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
            dualpath_threshold=None,
            dualpath_chunk_size=None,
            relay_download_preset=None,
            relay_upload_preset=None,
        ):
            assert got_src == src_site
            assert got_dst == dst_site
            assert parallel_threshold == scheduler.parallel_threshold
            assert dualpath_threshold == scheduler.remote_dualpath_threshold
            assert dualpath_chunk_size == scheduler.remote_dualpath_chunk_size
            assert relay_download_preset == scheduler.parallel_download_preset
            assert relay_upload_preset == scheduler.parallel_upload_preset

        def transfer_file(self, src, dst, callback=None, check_interrupt=None, resume_offset=0, requested_engine=None):
            called["count"] += 1
            assert src == "/data/a.bin"
            assert dst == "/data/b.bin"
            assert resume_offset == 0
            assert requested_engine == "sftp"
            if callback:
                callback(10, 10)

    fake_dst_engine = MagicMock()
    fake_dst_engine.stat.side_effect = SSHFerryError(ErrorCode.PATH_NOT_FOUND, "not found")

    with patch("src.core.scheduler.SftpEngine", return_value=fake_dst_engine), patch(
        "src.core.scheduler.RemoteToRemoteTransferEngine",
        FakeRemoteTransferEngine,
    ):
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
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=128), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct",
            side_effect=SSHFerryError(ErrorCode.TRANSFER_FAILED, "direct failed"),
        ):
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin")

    assert mode == "parallel_bridge"
    bridge.assert_called_once()


def test_remote_to_remote_huge_file_prefers_dualpath():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"), patch(
        "src.engines.remote_transfer_engine.RemoteToRemoteTransferEngine._transfer_file_dualpath"
    ) as dualpath:
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
            dualpath_threshold=128,
        )
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=256), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct",
            side_effect=SSHFerryError(ErrorCode.TRANSFER_FAILED, "direct failed"),
        ):
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin")

    assert mode == "dualpath"
    dualpath.assert_called_once()


def test_remote_to_remote_explicit_dualpath_bypasses_direct_selection():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"), patch(
        "src.engines.remote_transfer_engine.RemoteToRemoteTransferEngine._transfer_file_dualpath"
    ) as dualpath:
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
            dualpath_threshold=128,
        )
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=32), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct",
        ) as direct:
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin", requested_engine="dualpath")

    assert mode == "dualpath"
    dualpath.assert_called_once()
    direct.assert_not_called()


def test_remote_to_remote_huge_file_prefers_direct_when_available():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
            dualpath_threshold=128,
        )
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=256), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct",
        ) as direct, patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_dualpath",
        ) as dualpath:
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin")

    assert mode == "direct"
    direct.assert_called_once()
    dualpath.assert_not_called()


def test_metric_preset_for_dualpath_remote_transfer_uses_parallel_bucket():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(logger=MagicMock(), parallel_preset="high")

    task = Task(
        task_id="r2r-metric",
        kind="file_transfer",
        engine="dualpath",
        src="/data/a.bin",
        dst="/data/b.bin",
        bytes_total=256,
        src_endpoint_type="remote",
        dst_endpoint_type="remote",
        src_site_snapshot=src_site,
        dst_site_snapshot=dst_site,
    )

    assert scheduler._metric_preset_for_task(task) == "high"


def test_remote_to_remote_resume_offset_prefers_resumable_bridge():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
            dualpath_threshold=128,
        )
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=256), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct_resume",
        ) as direct_resume, patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct",
        ) as direct, patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_dualpath",
        ) as dualpath:
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin", resume_offset=64)

    assert mode == "direct_resume"
    direct_resume.assert_called_once()
    direct.assert_not_called()
    dualpath.assert_not_called()


def test_remote_to_remote_resume_falls_back_to_bridge_when_direct_resume_fails():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
            dualpath_threshold=128,
        )
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=256), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct_resume",
            side_effect=SSHFerryError(ErrorCode.TRANSFER_FAILED, "resume failed"),
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_relay",
        ) as relay:
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin", resume_offset=64)

    assert mode == "bridge_resume"
    relay.assert_called_once()
    assert relay.call_args.kwargs["offset"] == 64


def test_remote_to_remote_direct_attempt_allowed_for_password_site():
    src_site = _site("src")
    dst_site = _site("dst")
    dst_site.auth_method = "password"
    dst_site.key_path = None
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(
            src_site,
            dst_site,
            logger,
            parallel_threshold=64,
            dualpath_threshold=128,
        )
        with patch.object(RemoteToRemoteTransferEngine, "_remote_file_size", return_value=256), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_direct",
        ) as direct:
            mode = engine.transfer_file("/data/a.bin", "/data/b.bin")

    assert mode == "direct"
    direct.assert_called_once()


def test_build_direct_scp_command_uses_site_ssh_metadata():
    src_site = _site("src")
    dst_site = _site("dst")
    dst_site.auth_method = "password"
    dst_site.key_path = r"D:\keys\id_rsa"
    dst_site.port = 60066
    dst_site.proxy_jump = "jump.example.com"
    dst_site.ssh_config_path = "/root/.ssh/config"
    dst_site.ssh_options = ["Compression=yes", "-o ConnectTimeout=5"]

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        command = engine._build_direct_scp_command("/data/src.bin", "/data/dst.bin")

    assert "'scp'" in command
    assert "'-P' '60066'" in command
    assert "'-F' '/root/.ssh/config'" in command
    assert "'-o' 'ProxyJump=jump.example.com'" in command
    assert "'-o' 'Compression=yes'" in command
    assert "'-o' 'ConnectTimeout=5'" in command
    assert "D:\\keys\\id_rsa" not in command
    assert "'user@dst.example.com:/data/dst.bin'" in command


def test_build_direct_ssh_probe_command_uses_site_ssh_metadata():
    src_site = _site("src")
    dst_site = _site("dst")
    dst_site.auth_method = "password"
    dst_site.key_path = None
    dst_site.port = 60066
    dst_site.proxy_jump = "jump.example.com"
    dst_site.ssh_config_path = "/root/.ssh/config"
    dst_site.ssh_options = ["ServerAliveInterval=15"]

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        command = engine._build_direct_ssh_probe_command("/data/dst.bin")

    assert "'ssh'" in command
    assert "'-p' '60066'" in command
    assert "'-F' '/root/.ssh/config'" in command
    assert "'-o' 'ProxyJump=jump.example.com'" in command
    assert "'-o' 'ServerAliveInterval=15'" in command
    assert "'user@dst.example.com'" in command
    assert "SSHFERRY_DIRECT_OK" in command


def test_build_direct_commands_use_ephemeral_key_override():
    src_site = _site("src")
    dst_site = _site("dst")
    dst_site.auth_method = "password"
    dst_site.key_path = None

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        direct_auth = {"mode": "ephemeral_key", "key_path": "/tmp/sshferry-direct-key"}
        probe_command = engine._build_direct_ssh_probe_command("/data/dst.bin", direct_auth=direct_auth)
        scp_command = engine._build_direct_scp_command("/data/src.bin", "/data/dst.bin", direct_auth=direct_auth)

    assert "'-i' '/tmp/sshferry-direct-key'" in probe_command
    assert "'-i' '/tmp/sshferry-direct-key'" in scp_command


def test_build_direct_resume_command_uses_tail_and_ssh_append():
    src_site = _site("src")
    dst_site = _site("dst")
    dst_site.auth_method = "password"
    dst_site.key_path = None

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        command = engine._build_direct_resume_command(
            "/data/src.bin",
            "/data/dst.bin",
            64,
            direct_auth={"mode": "ephemeral_key", "key_path": "/tmp/sshferry-direct-key"},
        )

    assert "command -v tail" in command
    assert "tail -c +$((64 + 1)) '/data/src.bin'" in command
    assert "'ssh'" in command
    assert "'-i' '/tmp/sshferry-direct-key'" in command
    assert "cat >> " in command
    assert "/data/dst.bin" in command


def test_prepare_direct_auth_bootstraps_ephemeral_key_for_password_site():
    src_site = _site("src")
    dst_site = _site("dst")
    dst_site.auth_method = "password"
    dst_site.key_path = None

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        src_engine = MagicMock()
        dst_engine = MagicMock()
        with patch.object(
            RemoteToRemoteTransferEngine,
            "_exec_remote_command",
            side_effect=[
                (0, "ssh-ed25519 AAAATEST sshferry-direct-1\n", ""),
                (0, "", ""),
            ],
        ):
            direct_auth = engine._prepare_direct_auth(src_engine, dst_engine)

    assert direct_auth is not None
    assert direct_auth["mode"] == "ephemeral_key"
    assert direct_auth["key_path"].startswith("/tmp/sshferry-direct-")
    assert direct_auth["marker"].startswith("sshferry-direct-")


def test_probe_direct_connectivity_surfaces_stderr_details():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        src_engine = MagicMock()
        with patch.object(
            RemoteToRemoteTransferEngine,
            "_exec_remote_command",
            return_value=(255, "", "lost connection"),
        ):
            try:
                engine._probe_direct_connectivity(src_engine, "/data/dst.bin")
            except SSHFerryError as exc:
                assert "direct probe failed" in exc.message
                assert "stderr=lost connection" in exc.message
            else:
                raise AssertionError("expected probe failure")


def test_cleanup_direct_auth_removes_ephemeral_key_and_authorized_key():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        src_engine = MagicMock()
        dst_engine = MagicMock()
        with patch.object(
            RemoteToRemoteTransferEngine,
            "_exec_remote_command",
            side_effect=[(0, "", ""), (0, "", "")],
        ) as exec_cmd:
            engine._cleanup_direct_auth(
                src_engine,
                dst_engine,
                {
                    "mode": "ephemeral_key",
                    "key_path": "/tmp/sshferry-direct-1",
                    "marker": "sshferry-direct-1",
                },
            )

    assert exec_cmd.call_count == 2


def test_exec_remote_command_with_progress_reports_destination_growth():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, MagicMock())
        src_engine = MagicMock()
        dst_engine = MagicMock()
        channel = MagicMock()
        channel.exit_status_ready.side_effect = [False, False, True]
        channel.recv_exit_status.return_value = 0
        stdout = MagicMock()
        stdout.channel = channel
        stdout.read.return_value = b""
        stderr = MagicMock()
        stderr.read.return_value = b""
        src_engine.ssh_client.exec_command.return_value = (MagicMock(), stdout, stderr)
        dst_engine.stat.side_effect = [SimpleNamespace(size=16), SimpleNamespace(size=48)]

        progress_updates: list[int] = []
        with patch("src.engines.remote_transfer_engine.time.sleep"):
            exit_code, std_out, std_err = engine._exec_remote_command_with_progress(
                src_engine,
                dst_engine,
                "scp ...",
                "/data/dst.bin",
                64,
                callback=lambda done, _total: progress_updates.append(done),
            )

    assert exit_code == 0
    assert std_out == ""
    assert std_err == ""
    assert progress_updates == [16, 48, 64]


def test_scheduler_remote_to_remote_resume_uses_existing_destination_prefix():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(logger=MagicMock())

    task = Task(
        task_id="r2r-resume",
        kind="file_transfer",
        engine="dualpath",
        src="/data/a.bin",
        dst="/data/b.bin",
        bytes_total=100,
        bytes_done=40,
        src_endpoint_type="remote",
        dst_endpoint_type="remote",
        src_site_snapshot=src_site,
        dst_site_snapshot=dst_site,
        status="running",
        paused=False,
    )

    fake_dst_engine = MagicMock()
    fake_dst_engine.stat.return_value = SimpleNamespace(size=55)

    class FakeRemoteTransferEngine:
        def __init__(self, *_args, **_kwargs):
            return None

        def transfer_file(self, src, dst, callback=None, check_interrupt=None, resume_offset=0, requested_engine=None):
            assert src == "/data/a.bin"
            assert dst == "/data/b.bin"
            assert resume_offset == 55
            assert requested_engine == "dualpath"
            if callback:
                callback(100, 100)
            return "bridge_resume"

    with patch("src.core.scheduler.SftpEngine", return_value=fake_dst_engine), patch(
        "src.core.scheduler.RemoteToRemoteTransferEngine",
        FakeRemoteTransferEngine,
    ):
        scheduler._execute_remote_to_remote_file(task)

    assert task.bytes_done == 100


def test_scheduler_remote_to_remote_overwrites_fresh_task_even_when_destination_size_matches():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(logger=MagicMock())

    task = Task(
        task_id="r2r-skip",
        kind="file_transfer",
        engine="dualpath",
        src="/data/a.bin",
        dst="/data/b.bin",
        bytes_total=100,
        bytes_done=0,
        src_endpoint_type="remote",
        dst_endpoint_type="remote",
        src_site_snapshot=src_site,
        dst_site_snapshot=dst_site,
        status="running",
        paused=False,
    )

    fake_dst_engine = MagicMock()
    fake_dst_engine.stat.return_value = SimpleNamespace(size=100)

    class FakeRemoteTransferEngine:
        def __init__(self, *_args, **_kwargs):
            return None

        def transfer_file(self, src, dst, callback=None, check_interrupt=None, resume_offset=0, requested_engine=None):
            assert src == "/data/a.bin"
            assert dst == "/data/b.bin"
            assert resume_offset == 0
            assert requested_engine == "dualpath"
            if callback:
                callback(100, 100)
            return "dualpath"

    with patch("src.core.scheduler.SftpEngine", return_value=fake_dst_engine), patch(
        "src.core.scheduler.RemoteToRemoteTransferEngine",
        FakeRemoteTransferEngine,
    ):
        scheduler._execute_remote_to_remote_file(task)

    assert task.status == "running"
    assert task.skipped is False
    assert task.bytes_done == 100


def test_scheduler_remote_to_remote_skips_resumed_task_when_destination_already_complete():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(logger=MagicMock())

    task = Task(
        task_id="r2r-skip",
        kind="file_transfer",
        engine="dualpath",
        src="/data/a.bin",
        dst="/data/b.bin",
        bytes_total=100,
        bytes_done=40,
        src_endpoint_type="remote",
        dst_endpoint_type="remote",
        src_site_snapshot=src_site,
        dst_site_snapshot=dst_site,
        status="running",
        paused=False,
    )

    fake_dst_engine = MagicMock()
    fake_dst_engine.stat.return_value = SimpleNamespace(size=100)

    with patch("src.core.scheduler.SftpEngine", return_value=fake_dst_engine), patch(
        "src.core.scheduler.RemoteToRemoteTransferEngine",
    ) as transfer_engine:
        scheduler._execute_remote_to_remote_file(task)

    assert task.status == "skipped"
    assert task.skipped is True
    assert task.bytes_done == 100
    assert task.end_time is not None
    transfer_engine.assert_not_called()


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
        src_file.readv.side_effect = lambda _chunks: iter([src_data])
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

    src_file.readv.assert_called_once_with([(0, 64)])
    dst_worker_file.seek.assert_called_with(0)
    dst_worker_file.write.assert_called_once_with(src_data)
    assert mock_parallel_cls.call_count == 2


def test_remote_to_remote_dir_relay_parallelizes_large_child_file():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine") as mock_sftp_cls:
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        bootstrap_src = MagicMock()
        bootstrap_dst = MagicMock()
        small_src = MagicMock()
        small_dst = MagicMock()
        mock_sftp_cls.side_effect = [bootstrap_src, bootstrap_dst, small_src, small_dst]

        bootstrap_src.list_dir.side_effect = [
            [
                SimpleNamespace(name="small.txt", path="/data/src/small.txt", is_dir=False, size=8),
                SimpleNamespace(name="big.bin", path="/data/src/big.bin", is_dir=False, size=64),
            ],
            [
                SimpleNamespace(name="small.txt", path="/data/src/small.txt", is_dir=False, size=8),
                SimpleNamespace(name="big.bin", path="/data/src/big.bin", is_dir=False, size=64),
            ]
        ]
        bootstrap_dst.mkdir.return_value = None

        src_file = MagicMock()
        src_file.read.side_effect = [b"12345678", b""]
        src_file.readv.side_effect = lambda _chunks: iter([b"12345678"])
        small_src.sftp_client.open.return_value.__enter__.return_value = src_file
        dst_file = MagicMock()
        small_dst.sftp_client.open.return_value.__enter__.return_value = dst_file

        progress: list[int] = []
        bridge_calls: list[tuple[str, str, int]] = []

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=16)

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_file_parallel_bridge",
            side_effect=lambda src, dst, total, callback=None, check_interrupt=None: (
                bridge_calls.append((src, dst, total)),
                callback and callback(total, total),
            ),
        ):
            bytes_done = engine._transfer_dir_relay(
                "/data/src",
                "/data/dst",
                callback=lambda done, _total: progress.append(done),
            )

    assert bytes_done == 72
    assert bridge_calls == [("/data/src/big.bin", "/data/dst/big.bin", 64)]
    dst_file.write.assert_called_once_with(b"12345678")
    assert progress[-1] == 72


def test_remote_to_remote_dir_prefers_mixed_mode_for_large_and_small_files():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        dir_plan = {
            "total_bytes": 72,
            "total_files": 2,
            "directories": [],
            "large_files": [{"src": "/data/src/big.bin", "dst": "/data/dst/big.bin", "size": 64}],
            "small_files": [{"src": "/data/src/small.txt", "rel_path": "small.txt", "size": 8}],
            "small_batches": [{"bundle_id": "bundle-0", "files": [{"rel_path": "small.txt", "size": 8}], "total_bytes": 8}],
        }

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_plan_remote_dir_transfer",
            return_value=dir_plan,
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_dir_mixed",
        ) as mixed:
            mode = engine.transfer_dir("/data/src", "/data/dst")

    assert mode == "dir_mixed"
    mixed.assert_called_once()


def test_plan_remote_dir_transfer_populates_large_file_destinations():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        src_engine = MagicMock()
        src_engine.list_dir.side_effect = [
            [
                SimpleNamespace(name="nested", path="/data/src/nested", is_dir=True, size=0),
                SimpleNamespace(name="big.bin", path="/data/src/big.bin", is_dir=False, size=64),
            ],
            [
                SimpleNamespace(name="small.txt", path="/data/src/nested/small.txt", is_dir=False, size=8),
            ],
        ]

        with patch("src.engines.remote_transfer_engine.SftpEngine", return_value=src_engine):
            dir_plan = engine._plan_remote_dir_transfer("/data/src", "/data/dst")

    assert dir_plan["directories"] == ["nested"]
    assert dir_plan["large_files"] == [
        {
            "src": "/data/src/big.bin",
            "dst": "/data/dst/big.bin",
            "rel_path": "big.bin",
            "size": 64,
        }
    ]
    assert dir_plan["small_files"] == [
        {
            "src": "/data/src/nested/small.txt",
            "dst": "/data/dst/nested/small.txt",
            "rel_path": "nested/small.txt",
            "size": 8,
        }
    ]


def test_scan_remote_dir_entries_fallback_skips_revisiting_canonical_paths():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        calls: list[str] = []
        src_engine = MagicMock()
        src_engine.sftp_client = SimpleNamespace(
            normalize=lambda path: "/data/src" if path == "/data/src/link" else path
        )

        def list_dir(path: str):
            calls.append(path)
            if path == "/data/src":
                return [
                    SimpleNamespace(name="link", path="/data/src/link", is_dir=True, size=0),
                    SimpleNamespace(name="a.txt", path="/data/src/a.txt", is_dir=False, size=8),
                ]
            raise AssertionError(f"cycle path should not be traversed: {path}")

        src_engine.list_dir.side_effect = list_dir

        files, directories = engine._scan_remote_dir_entries(src_engine, "/data/src", "/data/dst")

    assert calls == ["/data/src"]
    assert directories == ["link"]
    assert files == [
        {
            "src": "/data/src/a.txt",
            "dst": "/data/dst/a.txt",
            "rel_path": "a.txt",
            "size": 8,
        }
    ]


def test_remote_to_remote_dir_mixed_executes_large_files_and_small_bundles():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        engine.folder_large_file_workers = 1
        engine.folder_bundle_workers = 1

        dir_plan = {
            "total_bytes": 72,
            "large_files": [
                {"src": "/data/src/big.bin", "dst": "/data/dst/big.bin", "size": 64},
            ],
            "small_batches": [
                {
                    "bundle_id": "bundle-0",
                    "files": [{"rel_path": "small.txt", "size": 8}],
                    "total_bytes": 8,
                }
            ],
            "directories": ["nested"],
        }

        progress: list[int] = []
        large_calls: list[tuple[str, str]] = []
        bundle_calls: list[tuple[str, str, str]] = []

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_ensure_remote_directories_for_plan",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_probe_direct_bundle_support",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "transfer_file",
            side_effect=lambda src, dst, callback=None, check_interrupt=None, cleanup_cached_auth=True: (
                large_calls.append((src, dst)),
                callback and callback(64, 64),
                "parallel_bridge",
            ),
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_small_file_bundle",
            side_effect=lambda src_dir, dst_dir, files, bundle_id=None, progress_callback=None, check_interrupt=None: bundle_calls.append(
                (src_dir, dst_dir, bundle_id or "")
            ),
        ):
            bytes_done = engine._transfer_dir_mixed(
                "/data/src",
                "/data/dst",
                dir_plan,
                callback=lambda done, _total: progress.append(done),
            )

    assert bytes_done == 72
    assert large_calls == [("/data/src/big.bin", "/data/dst/big.bin")]
    assert bundle_calls == [("/data/src", "/data/dst", "bundle-0")]
    assert progress[-1] == 72


def test_scheduler_remote_to_remote_folder_updates_subtask_progress():
    src_site = _site("src")
    dst_site = _site("dst")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(logger=MagicMock())

    task = Task(
        task_id="r2r-folder",
        kind="folder_transfer",
        engine="sftp",
        src="/data/src",
        dst="/data/dst",
        bytes_total=72,
        subtask_count=3,
        src_endpoint_type="remote",
        dst_endpoint_type="remote",
        src_site_snapshot=src_site,
        dst_site_snapshot=dst_site,
        status="running",
    )

    class FakeRemoteTransferEngine:
        def __init__(self, *_args, **_kwargs):
            return None

        def transfer_dir(self, src, dst, callback=None, check_interrupt=None, item_callback=None):
            assert src == "/data/src"
            assert dst == "/data/dst"
            if item_callback:
                item_callback("start", "big.bin", 1)
            if callback:
                callback(64, 72)
            if item_callback:
                item_callback("complete", "big.bin", 1)
                item_callback("start", "2 files", 0)
            if callback:
                callback(72, 72)
            if item_callback:
                item_callback("complete", "2 files", 2)
            return "dir_mixed"

    with patch("src.core.scheduler.RemoteToRemoteTransferEngine", FakeRemoteTransferEngine):
        scheduler._execute_remote_to_remote_folder(task)

    assert task.bytes_done == 72
    assert task.subtask_done == 3
    assert task.current_file == ""


def test_remote_to_remote_dir_mixed_large_only_skips_bundle_probe():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        dir_plan = {
            "total_bytes": 64,
            "large_files": [{"src": "/data/src/big.bin", "dst": "/data/dst/big.bin", "size": 64}],
            "small_batches": [],
            "directories": [],
        }

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_ensure_remote_directories_for_plan",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_probe_direct_bundle_support",
            side_effect=AssertionError("bundle probe should not run"),
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "transfer_file",
            return_value="parallel_bridge",
        ):
            bytes_done = engine._transfer_dir_mixed("/data/src", "/data/dst", dir_plan)

    assert bytes_done == 64


def test_remote_to_remote_dir_mixed_warms_direct_auth_before_bundle_probe():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        dir_plan = {
            "total_bytes": 12,
            "large_files": [],
            "small_batches": [
                {
                    "bundle_id": "bundle-0",
                    "files": [{"rel_path": "a.txt", "size": 12}],
                    "total_bytes": 12,
                }
            ],
            "directories": [],
        }
        call_order: list[str] = []

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_ensure_remote_directories_for_plan",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_warm_cached_direct_auth",
            side_effect=lambda *args, **kwargs: call_order.append("warm"),
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_probe_direct_bundle_support",
            side_effect=lambda *args, **kwargs: call_order.append("probe"),
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_small_file_bundle",
        ):
            bytes_done = engine._transfer_dir_mixed("/data/src", "/data/dst", dir_plan)

    assert bytes_done == 12
    assert call_order[:2] == ["warm", "probe"]


def test_remote_to_remote_dir_mixed_defers_cached_auth_cleanup_until_end():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        dir_plan = {
            "total_bytes": 76,
            "large_files": [{"src": "/data/src/big.bin", "dst": "/data/dst/big.bin", "size": 64}],
            "small_batches": [
                {
                    "bundle_id": "bundle-0",
                    "files": [{"rel_path": "a.txt", "size": 12}],
                    "total_bytes": 12,
                }
            ],
            "directories": [],
        }

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_ensure_remote_directories_for_plan",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_warm_cached_direct_auth",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_probe_direct_bundle_support",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_small_file_bundle",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "transfer_file",
            return_value="direct",
        ) as transfer_file, patch.object(
            RemoteToRemoteTransferEngine,
            "_cleanup_cached_direct_auth",
        ) as cleanup:
            bytes_done = engine._transfer_dir_mixed("/data/src", "/data/dst", dir_plan)

    assert bytes_done == 76
    assert transfer_file.call_args.kwargs["cleanup_cached_auth"] is False
    cleanup.assert_called_once()


def test_remote_to_remote_dir_falls_back_to_relay_when_mixed_fails():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        dir_plan = {
            "total_bytes": 72,
            "total_files": 2,
            "directories": [],
            "large_files": [{"src": "/data/src/big.bin", "dst": "/data/dst/big.bin", "size": 64}],
            "small_files": [{"src": "/data/src/small.txt", "rel_path": "small.txt", "size": 8}],
            "small_batches": [{"bundle_id": "bundle-0", "files": [{"rel_path": "small.txt", "size": 8}], "total_bytes": 8}],
        }

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_plan_remote_dir_transfer",
            return_value=dir_plan,
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_dir_mixed",
            side_effect=SSHFerryError(ErrorCode.TRANSFER_FAILED, "bundle failed"),
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_dir_direct",
            side_effect=SSHFerryError(ErrorCode.TRANSFER_FAILED, "direct failed"),
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_transfer_dir_relay",
        ) as relay:
            mode = engine.transfer_dir("/data/src", "/data/dst")

    assert mode == "bridge"
    relay.assert_called_once()


def test_small_bundle_uses_directory_progress_polling():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        src_engine = MagicMock()
        dst_engine = MagicMock()
        files = [
            {"rel_path": "a.txt", "size": 8},
            {"rel_path": "b.txt", "size": 4},
        ]
        progress_updates: list[int] = []

        with patch("src.engines.remote_transfer_engine.SftpEngine", side_effect=[src_engine, dst_engine]), patch.object(
            RemoteToRemoteTransferEngine,
            "_prepare_direct_auth",
            return_value={"mode": "site_key", "key_path": "/tmp/key"},
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_exec_remote_command_with_directory_progress",
            return_value=(0, "SSHFERRY_BUNDLE_OK", ""),
        ) as progress_exec, patch.object(
            RemoteToRemoteTransferEngine,
            "_cleanup_remote_temp_dir",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_cleanup_direct_auth",
        ):
            engine._transfer_small_file_bundle(
                "/data/src",
                "/data/dst",
                files,
                bundle_id="bundle-1",
                progress_callback=lambda done, _total: progress_updates.append(done),
            )

    assert progress_exec.called
    assert progress_exec.call_args.args[3].startswith("/data/dst/.sshferry-bundle-bundle-1-")
    assert progress_exec.call_args.args[4] == 12


def test_small_bundle_keeps_temp_dir_under_destination_root():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine"):
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        src_engine = MagicMock()
        dst_engine = MagicMock()

        with patch("src.engines.remote_transfer_engine.SftpEngine", side_effect=[src_engine, dst_engine]), patch.object(
            RemoteToRemoteTransferEngine,
            "_prepare_direct_auth",
            return_value={"mode": "site_key", "key_path": "/tmp/key"},
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_exec_remote_command_with_directory_progress",
            return_value=(0, "SSHFERRY_BUNDLE_OK", ""),
        ) as progress_exec, patch.object(
            RemoteToRemoteTransferEngine,
            "_cleanup_remote_temp_dir",
        ), patch.object(
            RemoteToRemoteTransferEngine,
            "_cleanup_direct_auth",
        ):
            engine._transfer_small_file_bundle(
                "/data/src",
                "/data",
                [{"rel_path": "small.txt", "size": 8}],
                bundle_id="bundle-root",
            )

    assert progress_exec.call_args.args[3].startswith("/data/.sshferry-bundle-bundle-root-")


def test_warm_cached_direct_auth_bootstraps_once():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    with patch("src.engines.remote_transfer_engine.SftpEngine") as engine_cls:
        from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

        engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
        src_engine = MagicMock()
        dst_engine = MagicMock()
        engine_cls.side_effect = [src_engine, dst_engine]

        with patch.object(
            RemoteToRemoteTransferEngine,
            "_prepare_direct_auth",
            return_value={"mode": "ephemeral_key", "key_path": "/tmp/key", "marker": "m1"},
        ) as prepare:
            direct_auth = engine._warm_cached_direct_auth()

    assert direct_auth == {"mode": "ephemeral_key", "key_path": "/tmp/key", "marker": "m1"}
    prepare.assert_called_once_with(src_engine, dst_engine)
    src_engine.connect.assert_called_once()
    dst_engine.connect.assert_called_once()
    src_engine.disconnect.assert_called_once()
    dst_engine.disconnect.assert_called_once()


def test_warm_cached_direct_auth_reuses_existing_cache():
    src_site = _site("src")
    dst_site = _site("dst")
    logger = MagicMock()

    from src.engines.remote_transfer_engine import RemoteToRemoteTransferEngine

    engine = RemoteToRemoteTransferEngine(src_site, dst_site, logger, parallel_threshold=64)
    engine._cached_direct_auth = {"mode": "ephemeral_key", "key_path": "/tmp/key", "marker": "m1"}

    with patch("src.engines.remote_transfer_engine.SftpEngine") as engine_cls, patch.object(
        RemoteToRemoteTransferEngine,
        "_prepare_direct_auth",
    ) as prepare:
        direct_auth = engine._warm_cached_direct_auth()

    assert direct_auth == {"mode": "ephemeral_key", "key_path": "/tmp/key", "marker": "m1"}
    engine_cls.assert_not_called()
    prepare.assert_not_called()
