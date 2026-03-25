"""Tests for task control (pause/resume/restart) and interactivity."""
import io
import os
import tarfile
import threading
import time
import types
from unittest.mock import MagicMock, patch

import pytest
from src.core.scheduler import TaskScheduler
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import RemoteEntry, SiteConfig, Task
from src.shared.remote_scan import RemoteScanEntry


def create_mock_scheduler():
    # Helper to create scheduler with mocked MetricsCollector
    # We patch the class where it is used
    with patch("src.core.scheduler.MetricsCollector"):
        site_config = SiteConfig(
            name="test",
            host="localhost",
            port=22,
            username="user",
            auth_method="password",
            password="password",
            remote_root="/tmp",
        )
        scheduler = TaskScheduler(site_config, logger=MagicMock())
        # We need to manually start the patch or keep it active if needed later?
        # Actually for init it is enough. But for usage?
        # Scheduler already has self.metrics set to the mock instance.
        # So subsequent calls to scheduler.metrics.record() will use that instance.
        return scheduler


def test_pause_resume_restart_cycle():
    mock_scheduler = create_mock_scheduler()
    # Setup - add a running task
    task = Task(task_id="t1", kind="upload", engine="sftp", src="src", dst="dst", bytes_total=100)
    mock_scheduler.add_task(task)
    # Manually set to running to simulate execution (since scheduler loop isn't running)
    with mock_scheduler.task_lock:
        task.status = "running"
    
    # 1. Test Pause
    assert mock_scheduler.pause_task("t1") is True
    assert task.status == "running"  # Should just set flag
    assert task.paused is True
    
    # Simulate execution loop finding the paused flag
    with mock_scheduler.task_lock:
        if task.paused:
            task.status = "paused"
            
    assert task.status == "paused"
    
    # 2. Test Resume
    assert mock_scheduler.resume_task("t1") is True
    assert task.status == "pending"
    assert task.paused is False
    assert mock_scheduler.pending_task_count() == 1
    
    # 3. Simulate failure
    with mock_scheduler.task_lock:
        task.status = "failed"
        task.error_message = "Network error"
        
    # 4. Test Restart
    assert mock_scheduler.restart_task("t1") is True
    assert task.status == "pending"
    assert task.error_message is None
    assert mock_scheduler.pending_task_count() == 1  # No duplicate enqueue for same task


def test_restart_invalid_state():
    mock_scheduler = create_mock_scheduler()
    # Setup - add a running task
    task = Task(task_id="t2", kind="upload", engine="sftp", src="src", dst="dst", bytes_total=100)
    mock_scheduler.add_task(task)
    with mock_scheduler.task_lock:
        task.status = "running"
    
    # Try to restart running task - should fail
    assert mock_scheduler.restart_task("t2") is False
    assert task.status == "running"
    
    # Pause it
    with mock_scheduler.task_lock:
        task.status = "paused"

    # Try to restart paused task - should fail (must be terminal)
    # Based on implementation, paused is not terminal state for restart?
    # Let's check implementation again: if task.status in ("failed", "canceled", "done", "skipped"):
    assert mock_scheduler.restart_task("t2") is False


def test_ensure_local_directories_uses_windows_extended_prefix(monkeypatch):
    scheduler = create_mock_scheduler()
    created: list[tuple[str, bool]] = []

    monkeypatch.setattr("src.shared.paths.sys.platform", "win32")
    monkeypatch.setattr(
        "src.core.scheduler.os.makedirs",
        lambda path, exist_ok=True: created.append((path, exist_ok)),
    )

    scheduler._ensure_local_directories([r"C:\deep\folder"])

    assert created == [(r"\\?\C:\deep\folder", True)]


def test_restart_done_task():
    mock_scheduler = create_mock_scheduler()
    # Setup - add a completed task
    task = Task(task_id="t3", kind="upload", engine="sftp", src="src", dst="dst", bytes_total=100)
    mock_scheduler.add_task(task)
    with mock_scheduler.task_lock:
        task.status = "done"
        task.bytes_done = 100
    
    assert mock_scheduler.restart_task("t3") is True
    assert task.status == "pending"
    assert task.bytes_done == 0


def test_restart_done_folder_task_resets_subtask_counters():
    mock_scheduler = create_mock_scheduler()
    task = Task(
        task_id="t4",
        kind="folder_download",
        engine="sftp",
        src="/remote/folder",
        dst="local/folder",
        bytes_total=1000,
        subtask_count=3,
        subtask_done=3,
        current_file="c.bin",
        status="done",
    )
    mock_scheduler.add_task(task)

    assert mock_scheduler.restart_task("t4") is True
    assert task.status == "pending"
    assert task.bytes_done == 0
    assert task.subtask_done == 0
    assert task.current_file == ""
    assert task.subtask_count == 3


def test_scan_remote_folder_tree_prefers_shell_scan(tmp_path, monkeypatch):
    scheduler = create_mock_scheduler()
    monkeypatch.setattr(
        "src.core.scheduler.scan_remote_tree_via_shell",
        lambda _engine, _root: [
            RemoteScanEntry(rel_path="nested", is_dir=True, size=0),
            RemoteScanEntry(rel_path="nested/a.jpg", is_dir=False, size=12),
        ],
    )

    items = scheduler._scan_remote_folder_tree(object(), "/remote/root", str(tmp_path))

    assert items == [
        ("/remote/root/nested", os.path.join(str(tmp_path), "nested"), True, 0),
        ("/remote/root/nested/a.jpg", os.path.join(str(tmp_path), "nested", "a.jpg"), False, 12),
    ]


def test_scan_remote_folder_tree_fallback_skips_revisiting_canonical_paths(monkeypatch):
    scheduler = create_mock_scheduler()
    monkeypatch.setattr("src.core.scheduler.scan_remote_tree_via_shell", lambda *_args, **_kwargs: None)

    calls: list[str] = []

    class FakeSftpClient:
        @staticmethod
        def normalize(path: str) -> str:
            return "/remote/root" if path == "/remote/root/link" else path

    class FakeEngine:
        sftp_client = FakeSftpClient()

        def list_dir(self, path: str):
            calls.append(path)
            if path == "/remote/root":
                return [
                    RemoteEntry(name="link", path="/remote/root/link", is_dir=True, size=0, mtime=time.time()),
                    RemoteEntry(name="a.txt", path="/remote/root/a.txt", is_dir=False, size=5, mtime=time.time()),
                ]
            raise AssertionError(f"cycle path should not be traversed: {path}")

    items = scheduler._scan_remote_folder_tree(FakeEngine(), "/remote/root", r"C:\downloads")

    assert calls == ["/remote/root"]
    assert items == [
        ("/remote/root/link", os.path.join(r"C:\downloads", "link"), True, 0),
        ("/remote/root/a.txt", os.path.join(r"C:\downloads", "a.txt"), False, 5),
    ]


def test_run_local_folder_transfer_mixed_uses_parallel_bundle_workers(tmp_path, monkeypatch):
    scheduler = create_mock_scheduler()
    scheduler.folder_bundle_workers = 2
    scheduler.folder_bundle_max_files = 2
    scheduler.folder_bundle_max_bytes = 1024 * 1024
    scheduler.folder_bundle_enabled = True
    monkeypatch.setattr(scheduler, "_probe_remote_folder_bundle_support", lambda *args, **kwargs: None)

    task = Task(
        task_id="bundle-parallel",
        kind="folder_transfer",
        engine="sftp",
        src="/remote/images",
        dst=str(tmp_path),
        bytes_total=40,
        subtask_count=4,
        src_site_snapshot=scheduler.site_config,
    )

    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_transfer(*_args, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        kwargs["add_progress"](10)
        with lock:
            active -= 1

    monkeypatch.setattr(scheduler, "_transfer_folder_download_bundle", fake_transfer)

    mixed_plan = {
        "large_files": [],
        "small_files": [
            {
                "src": f"/remote/images/{index}.jpg",
                "dst": str(tmp_path / f"{index}.jpg"),
                "size": 10,
                "rel_path": f"{index}.jpg",
                "tuple": (f"/remote/images/{index}.jpg", str(tmp_path / f"{index}.jpg"), False, 10),
            }
            for index in range(4)
        ],
        "small_batches": [],
    }

    scheduler._run_local_folder_transfer_mixed(
        task,
        mixed_plan,
        direction="download",
        local_root=str(tmp_path),
        remote_root="/remote/images",
    )

    assert max_active >= 2


def test_transfer_folder_download_bundle_uses_parallel_engine_for_large_archives(tmp_path, monkeypatch):
    scheduler = create_mock_scheduler()
    scheduler.folder_bundle_parallel_threshold = 10

    task = Task(
        task_id="bundle-download",
        kind="folder_transfer",
        engine="sftp",
        src="/remote/images",
        dst=str(tmp_path),
        bytes_total=30,
        subtask_count=1,
        src_site_snapshot=scheduler.site_config,
    )

    fake_engine = types.SimpleNamespace(
        ssh_client=object(),
        sftp_client=object(),
        stat=lambda _path: types.SimpleNamespace(size=100),
        remove_file=lambda _path: None,
        download_file=lambda *_args, **_kwargs: pytest.fail("single-connection download should not be used"),
        connect=lambda: None,
        disconnect=lambda: None,
    )

    monkeypatch.setattr(scheduler, "_exec_remote_shell", lambda *_args, **_kwargs: (0, "", ""))

    called = {"parallel": 0}

    def fake_parallel_download(self, _remote_path, local_path, callback=None, check_interrupt=None):
        called["parallel"] += 1
        with tarfile.open(local_path, "w") as archive:
            payload = io.BytesIO(b"abc")
            info = tarfile.TarInfo(name="a.jpg")
            info.size = 3
            archive.addfile(info, payload)
        if callback:
            callback(100, 100)

    monkeypatch.setattr("src.core.scheduler.ParallelSftpEngine.download_file", fake_parallel_download)

    scheduler._transfer_folder_download_bundle(
        task,
        scheduler.site_config,
        "/remote/images",
        str(tmp_path),
        [{"rel_path": "a.jpg", "size": 3}],
        engine=fake_engine,
        bundle_id="bundle-0",
        add_progress=lambda _done: None,
    )

    assert called["parallel"] == 1
    assert (tmp_path / "a.jpg").read_bytes() == b"abc"


def test_scheduler_uses_higher_bundle_concurrency_defaults():
    scheduler = create_mock_scheduler()

    assert scheduler.folder_bundle_workers == 4
    assert scheduler.folder_bundle_max_bytes == 256 * 1024 * 1024
    assert scheduler.folder_bundle_parallel_threshold == 256 * 1024 * 1024
    assert scheduler.folder_bundle_parallel_download_preset == "medium"


def test_add_task_does_not_queue_preparing_task():
    scheduler = create_mock_scheduler()
    task = Task(
        task_id="prep1",
        kind="folder_transfer",
        engine="sftp",
        src="local/folder",
        dst="/remote/folder",
        bytes_total=0,
        preparing=True,
        current_file="Preparing directory...",
    )

    scheduler.add_task(task)

    assert scheduler.pending_task_count() == 0
    with scheduler.task_lock:
        assert "prep1" in scheduler.tasks


def test_finish_preparing_task_queues_folder_transfer():
    scheduler = create_mock_scheduler()
    task = Task(
        task_id="prep2",
        kind="folder_transfer",
        engine="sftp",
        src="local/folder",
        dst="/remote/folder",
        bytes_total=0,
        preparing=True,
        current_file="Preparing directory...",
    )
    scheduler.add_task(task)

    assert scheduler.finish_preparing_task("prep2", 3, 1024) is True

    with scheduler.task_lock:
        prepared = scheduler.tasks["prep2"]
        assert prepared.preparing is False
        assert prepared.subtask_count == 3
        assert prepared.bytes_total == 1024
        assert prepared.current_file == ""
    assert scheduler.pending_task_count() == 1


def test_progress_callback_throttles_intermediate_updates_but_keeps_completion(monkeypatch):
    scheduler = create_mock_scheduler()
    scheduler.progress_update_interval_seconds = 10.0
    scheduler.progress_update_min_bytes = 1000
    task = Task(task_id="progress1", kind="file_transfer", engine="sftp", src="a", dst="b", bytes_total=100)

    callback = scheduler._progress_callback(task)
    callback(10, 100)
    assert task.bytes_done == 10

    callback(20, 100)
    assert task.bytes_done == 10

    callback(100, 100)
    assert task.bytes_done == 100


def test_resume_paused_folder_task_rebuilds_aggregate_progress():
    mock_scheduler = create_mock_scheduler()
    task = Task(
        task_id="t4_resume",
        kind="folder_transfer",
        engine="sftp",
        src="/remote/folder",
        dst="local/folder",
        bytes_total=1000,
        bytes_done=640,
        subtask_count=3,
        subtask_done=2,
        current_file="b.bin",
        status="paused",
        paused=True,
        speed=12.5,
    )
    mock_scheduler.add_task(task)

    assert mock_scheduler.resume_task("t4_resume") is True
    assert task.status == "pending"
    assert task.paused is False
    assert task.bytes_done == 0
    assert task.subtask_done == 0
    assert task.current_file == ""
    assert task.speed == 0.0
    assert task.subtask_count == 3


def test_folder_download_updates_progress_during_file_transfer(tmp_path):
    scheduler = create_mock_scheduler()
    task = Task(
        task_id="fd1",
        kind="folder_download",
        engine="sftp",
        src="/remote",
        dst=str(tmp_path / "dl"),
        bytes_total=1000,
        subtask_count=1,
    )
    task.start_time = time.time()
    progress_snapshots: list[int] = []

    class FakeEngine:
        def list_dir(self, _path):
            return [
                RemoteEntry(
                    name="a.bin",
                    path="/remote/a.bin",
                    is_dir=False,
                    size=1000,
                    mtime=time.time(),
                )
            ]

        def download_file(self, _src, _dst, callback=None, check_interrupt=None, offset=0):
            if callback:
                callback(400, 1000)
                progress_snapshots.append(task.bytes_done)
                callback(1000, 1000)

    scheduler._download_dir_recursive(FakeEngine(), task, "/remote", str(tmp_path / "dl"))

    assert task.subtask_done == 1
    assert task.bytes_done == 1000
    assert progress_snapshots == [400]
    assert os.path.isdir(str(tmp_path / "dl"))


def test_get_all_tasks_returns_snapshots():
    scheduler = create_mock_scheduler()
    task = Task(
        task_id="snap1",
        kind="download",
        engine="sftp",
        src="/remote.bin",
        dst="local.bin",
        bytes_total=100,
        status="pending",
    )
    scheduler.add_task(task)

    snapshot = scheduler.get_all_tasks()[0]
    snapshot.status = "failed"
    snapshot.bytes_done = 77

    original = scheduler.get_task("snap1")
    assert original is not None
    assert original.status == "pending"
    assert original.bytes_done == 0


def test_folder_upload_updates_progress_during_file_transfer(tmp_path):
    scheduler = create_mock_scheduler()
    local_dir = tmp_path / "up"
    local_dir.mkdir()
    local_file = local_dir / "a.bin"
    local_file.write_bytes(b"x" * 1000)

    task = Task(
        task_id="fu1",
        kind="folder_upload",
        engine="sftp",
        src=str(local_dir),
        dst="/remote",
        bytes_total=1000,
        subtask_count=1,
    )
    task.start_time = time.time()
    progress_snapshots: list[int] = []

    class FakeEngine:
        def mkdir(self, _path):
            return None

        def stat(self, _path):
            raise SSHFerryError(ErrorCode.PATH_NOT_FOUND, "not found")

        def upload_file(self, _src, _dst, callback=None, check_interrupt=None, offset=0):
            if callback:
                callback(400, 1000)
                progress_snapshots.append(task.bytes_done)
                callback(1000, 1000)

    scheduler._upload_dir_recursive(FakeEngine(), task, str(local_dir), "/remote")

    assert task.subtask_done == 1
    assert task.bytes_done == 1000
    assert progress_snapshots == [400]


def test_folder_upload_parallelizes_large_child_file(tmp_path):
    scheduler = create_mock_scheduler()
    local_dir = tmp_path / "up_parallel"
    local_dir.mkdir()
    local_file = local_dir / "big.bin"
    local_file.write_bytes(b"x" * 32)
    scheduler.parallel_threshold = 16

    task = Task(
        task_id="fu2",
        kind="folder_transfer",
        engine="sftp",
        src=str(local_dir),
        dst="/remote",
        bytes_total=32,
        subtask_count=1,
        dst_site_snapshot=scheduler.site_config,
    )
    task.start_time = time.time()

    class BootstrapEngine:
        def mkdir(self, _path):
            return None

        def stat(self, _path):
            raise SSHFerryError(ErrorCode.PATH_NOT_FOUND, "not found")

        @property
        def site_config(self):
            return scheduler.site_config

    parallel_calls: list[tuple[str, str]] = []

    class FakeParallel:
        def __init__(self, _site, _logger, preset_name=None):
            self.preset_name = preset_name

        def upload_file(self, src, dst, callback=None, check_interrupt=None):
            parallel_calls.append((src, dst))
            if callback:
                callback(32, 32)

    with patch("src.core.scheduler.ParallelSftpEngine", FakeParallel):
        scheduler._upload_dir_recursive(BootstrapEngine(), task, str(local_dir), "/remote")

    assert parallel_calls == [(str(local_file), "/remote/big.bin")]
    assert task.subtask_done == 1
    assert task.bytes_done == 32


def test_folder_upload_mixed_bundles_small_files_and_parallelizes_large_ones(tmp_path):
    scheduler = create_mock_scheduler()
    local_dir = tmp_path / "up_mixed"
    local_dir.mkdir()
    large_file = local_dir / "big.bin"
    large_file.write_bytes(b"x" * 32)
    (local_dir / "a.txt").write_text("aaaa", encoding="utf-8")
    (local_dir / "b.txt").write_text("bbbb", encoding="utf-8")
    scheduler.parallel_threshold = 16

    task = Task(
        task_id="fu_mixed",
        kind="folder_transfer",
        engine="sftp",
        src=str(local_dir),
        dst="/remote",
        bytes_total=40,
        subtask_count=3,
        dst_site_snapshot=scheduler.site_config,
    )
    task.start_time = time.time()

    class BootstrapEngine:
        def mkdir(self, _path):
            return None

        def stat(self, _path):
            raise SSHFerryError(ErrorCode.PATH_NOT_FOUND, "not found")

        @property
        def site_config(self):
            return scheduler.site_config

    parallel_calls: list[tuple[str, str]] = []
    bundle_calls: list[list[str]] = []

    class FakeParallel:
        def __init__(self, _site, _logger, preset_name=None):
            self.preset_name = preset_name

        def upload_file(self, src, dst, callback=None, check_interrupt=None):
            parallel_calls.append((src, dst))
            if callback:
                callback(32, 32)

    with patch("src.core.scheduler.ParallelSftpEngine", FakeParallel):
        with patch.object(scheduler, "_probe_remote_folder_bundle_support", return_value=None):
            with patch.object(
                scheduler,
                "_transfer_folder_upload_bundle",
                side_effect=lambda *args, **kwargs: bundle_calls.append([item["rel_path"] for item in args[4]]),
            ):
                scheduler._upload_dir_recursive(BootstrapEngine(), task, str(local_dir), "/remote")

    assert parallel_calls == [(str(large_file), "/remote/big.bin")]
    assert bundle_calls == [["a.txt", "b.txt"]]
    assert task.subtask_done == 3
    assert task.bytes_done == 40


def test_folder_download_mixed_bundles_small_files_and_parallelizes_large_ones(tmp_path):
    scheduler = create_mock_scheduler()
    local_dir = tmp_path / "dl_mixed"
    scheduler.parallel_threshold = 16

    task = Task(
        task_id="fd_mixed",
        kind="folder_transfer",
        engine="sftp",
        src="/remote",
        dst=str(local_dir),
        bytes_total=40,
        subtask_count=3,
        src_site_snapshot=scheduler.site_config,
    )
    task.start_time = time.time()

    class FakeEngine:
        def list_dir(self, _path):
            return [
                RemoteEntry(name="big.bin", path="/remote/big.bin", is_dir=False, size=32, mtime=time.time()),
                RemoteEntry(name="a.txt", path="/remote/a.txt", is_dir=False, size=4, mtime=time.time()),
                RemoteEntry(name="b.txt", path="/remote/b.txt", is_dir=False, size=4, mtime=time.time()),
            ]

        @property
        def site_config(self):
            return scheduler.site_config

    parallel_calls: list[tuple[str, str]] = []
    bundle_calls: list[list[str]] = []

    class FakeParallel:
        def __init__(self, _site, _logger, preset_name=None):
            self.preset_name = preset_name

        def download_file(self, src, dst, callback=None, check_interrupt=None):
            parallel_calls.append((src, dst))
            if callback:
                callback(32, 32)

    with patch("src.core.scheduler.ParallelSftpEngine", FakeParallel):
        with patch.object(scheduler, "_probe_remote_folder_bundle_support", return_value=None):
            with patch.object(
                scheduler,
                "_transfer_folder_download_bundle",
                side_effect=lambda *args, **kwargs: bundle_calls.append([item["rel_path"] for item in args[4]]),
            ):
                scheduler._download_dir_recursive(FakeEngine(), task, "/remote", str(local_dir))

    assert parallel_calls == [("/remote/big.bin", os.path.join(str(local_dir), "big.bin"))]
    assert bundle_calls == [["a.txt", "b.txt"]]
    assert task.subtask_done == 3
    assert task.bytes_done == 40


def test_folder_upload_mixed_keeps_resumable_small_files_out_of_bundle(tmp_path):
    scheduler = create_mock_scheduler()
    scheduler.folder_bundle_file_count_threshold = 2
    scheduler.parallel_threshold = 16
    local_dir = tmp_path / "up_resume_mixed"
    local_dir.mkdir()
    (local_dir / "a.txt").write_text("aaaa", encoding="utf-8")
    (local_dir / "b.txt").write_text("bbbb", encoding="utf-8")

    task = Task(
        task_id="fu_resume_mixed",
        kind="folder_transfer",
        engine="sftp",
        src=str(local_dir),
        dst="/remote",
        bytes_total=8,
        subtask_count=2,
        dst_site_snapshot=scheduler.site_config,
    )
    task.start_time = time.time()

    class BootstrapEngine:
        def mkdir(self, _path):
            return None

        def stat(self, path):
            if path.endswith("/a.txt"):
                return RemoteEntry(name="a.txt", path=path, is_dir=False, size=2, mtime=time.time())
            raise SSHFerryError(ErrorCode.PATH_NOT_FOUND, "not found")

        @property
        def site_config(self):
            return scheduler.site_config

    uploads: list[tuple[str, str, int]] = []
    bundle_calls: list[list[str]] = []

    class FakeSftpEngine:
        def __init__(self, _site, _logger):
            pass

        def connect(self):
            return None

        def disconnect(self):
            return None

        def stat(self, _path):
            raise SSHFerryError(ErrorCode.PATH_NOT_FOUND, "not found")

        def upload_file(self, src, dst, callback=None, check_interrupt=None, offset=0):
            uploads.append((src, dst, offset))
            if callback:
                callback(4, 4)

    with patch("src.core.scheduler.SftpEngine", FakeSftpEngine):
        with patch.object(scheduler, "_probe_remote_folder_bundle_support", return_value=None):
            with patch.object(
                scheduler,
                "_transfer_folder_upload_bundle",
                side_effect=lambda *args, **kwargs: bundle_calls.append([item["rel_path"] for item in args[4]]),
            ):
                scheduler._upload_dir_recursive(BootstrapEngine(), task, str(local_dir), "/remote")

    assert bundle_calls == [["b.txt"]]
    assert uploads == [(str(local_dir / "a.txt"), "/remote/a.txt", 2)]
    assert task.subtask_done == 2
    assert task.bytes_done == 8


def test_folder_upload_mixed_skips_per_file_probe_when_remote_tree_is_empty(tmp_path):
    scheduler = create_mock_scheduler()
    scheduler.folder_bundle_file_count_threshold = 2
    scheduler.parallel_threshold = 16
    local_dir = tmp_path / "up_empty_tree_mixed"
    local_dir.mkdir()
    (local_dir / "a.txt").write_text("aaaa", encoding="utf-8")
    (local_dir / "b.txt").write_text("bbbb", encoding="utf-8")

    task = Task(
        task_id="fu_empty_tree_mixed",
        kind="folder_transfer",
        engine="sftp",
        src=str(local_dir),
        dst="/remote",
        bytes_total=8,
        subtask_count=2,
        dst_site_snapshot=scheduler.site_config,
    )
    task.start_time = time.time()

    class BootstrapEngine:
        ssh_client = object()
        sftp_client = object()

        def mkdir(self, _path):
            return None

        def stat(self, _path):
            raise AssertionError("per-file stat should be skipped when remote tree is empty")

        @property
        def site_config(self):
            return scheduler.site_config

    bundle_calls: list[list[str]] = []

    with patch.object(scheduler, "_remote_tree_appears_empty", return_value=True):
        with patch.object(scheduler, "_probe_remote_folder_bundle_support", return_value=None):
            with patch.object(
                scheduler,
                "_transfer_folder_upload_bundle",
                side_effect=lambda *args, **kwargs: bundle_calls.append([item["rel_path"] for item in args[4]]),
            ):
                scheduler._upload_dir_recursive(BootstrapEngine(), task, str(local_dir), "/remote")

    assert bundle_calls == [["a.txt", "b.txt"]]
    assert task.subtask_done == 2
    assert task.bytes_done == 8


def test_folder_download_mixed_keeps_resumable_small_files_out_of_bundle(tmp_path):
    scheduler = create_mock_scheduler()
    scheduler.folder_bundle_file_count_threshold = 2
    scheduler.parallel_threshold = 16
    local_dir = tmp_path / "dl_resume_mixed"
    local_dir.mkdir()
    (local_dir / "a.txt").write_text("aa", encoding="utf-8")

    task = Task(
        task_id="fd_resume_mixed",
        kind="folder_transfer",
        engine="sftp",
        src="/remote",
        dst=str(local_dir),
        bytes_total=8,
        subtask_count=2,
        src_site_snapshot=scheduler.site_config,
    )
    task.start_time = time.time()

    class FakeEngine:
        def list_dir(self, _path):
            return [
                RemoteEntry(name="a.txt", path="/remote/a.txt", is_dir=False, size=4, mtime=time.time()),
                RemoteEntry(name="b.txt", path="/remote/b.txt", is_dir=False, size=4, mtime=time.time()),
            ]

        @property
        def site_config(self):
            return scheduler.site_config

    downloads: list[tuple[str, str, int]] = []
    bundle_calls: list[list[str]] = []

    class FakeSftpEngine:
        def __init__(self, _site, _logger):
            pass

        def connect(self):
            return None

        def disconnect(self):
            return None

        def download_file(self, src, dst, callback=None, check_interrupt=None, offset=0):
            downloads.append((src, dst, offset))
            if callback:
                callback(4, 4)

    with patch("src.core.scheduler.SftpEngine", FakeSftpEngine):
        with patch.object(scheduler, "_probe_remote_folder_bundle_support", return_value=None):
            with patch.object(
                scheduler,
                "_transfer_folder_download_bundle",
                side_effect=lambda *args, **kwargs: bundle_calls.append([item["rel_path"] for item in args[4]]),
            ):
                scheduler._download_dir_recursive(FakeEngine(), task, "/remote", str(local_dir))

    assert bundle_calls == [["b.txt"]]
    assert downloads == [("/remote/a.txt", os.path.join(str(local_dir), "a.txt"), 2)]
    assert task.subtask_done == 2
    assert task.bytes_done == 8


def test_folder_upload_bundle_checks_interrupt_while_staging(tmp_path):
    scheduler = create_mock_scheduler()
    local_dir = tmp_path / "bundle_interrupt"
    local_dir.mkdir()
    file_a = local_dir / "a.txt"
    file_b = local_dir / "b.txt"
    file_a.write_text("aaaa", encoding="utf-8")
    file_b.write_text("bbbb", encoding="utf-8")
    task = Task(
        task_id="fu_bundle_interrupt",
        kind="folder_transfer",
        engine="sftp",
        src=str(local_dir),
        dst="/remote",
        bytes_total=8,
        subtask_count=2,
        dst_site_snapshot=scheduler.site_config,
    )
    task.start_time = time.time()
    add_calls: list[str] = []
    upload_calls: list[tuple[str, str]] = []
    interrupt_calls = {"count": 0}

    class FakeArchive:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add(self, src, arcname):
            add_calls.append(f"{src}:{arcname}")

    class FakeSftpEngine:
        def __init__(self, _site, _logger):
            pass

        def connect(self):
            return None

        def disconnect(self):
            return None

        def upload_file(self, src, dst, callback=None, check_interrupt=None):
            upload_calls.append((src, dst))

        def remove_file(self, _path):
            return None

    def fake_interrupt_checker(_task):
        def check_interrupt():
            interrupt_calls["count"] += 1
            if interrupt_calls["count"] >= 2:
                raise InterruptedError("Task interrupted")
            return False

        return check_interrupt

    files = [
        {"src": str(file_a), "dst": "/remote/a.txt", "size": 4, "rel_path": "a.txt"},
        {"src": str(file_b), "dst": "/remote/b.txt", "size": 4, "rel_path": "b.txt"},
    ]

    with patch("src.core.scheduler.SftpEngine", FakeSftpEngine):
        with patch("src.core.scheduler.tarfile.open", return_value=FakeArchive()):
            with patch("src.core.scheduler.os.path.getsize", return_value=8):
                with patch.object(scheduler, "_interrupt_checker", side_effect=fake_interrupt_checker):
                    with pytest.raises(InterruptedError):
                        scheduler._transfer_folder_upload_bundle(
                            task,
                            scheduler.site_config,
                            str(local_dir),
                            "/remote",
                            files,
                            bundle_id="bundle-test",
                            add_progress=lambda _done: None,
                        )

    assert len(add_calls) == 1
    assert upload_calls == []


def test_progress_callback_uses_rolling_speed_window():
    scheduler = create_mock_scheduler()
    task = Task(task_id="speed1", kind="file_transfer", engine="sftp", src="a", dst="b", bytes_total=1000, status="running")
    task.start_time = 100.0
    callback = scheduler._progress_callback(task)

    with patch("src.core.scheduler.time.time", side_effect=[100.0, 101.0, 102.0, 107.0]):
        callback(0, 1000)
        callback(400, 1000)
        callback(900, 1000)
        with scheduler.task_lock:
            scheduler._refresh_task_speed_locked(task)

    assert task.speed == 0.0


def test_progress_callback_uses_recent_samples_not_lifetime_average():
    scheduler = create_mock_scheduler()
    task = Task(task_id="speed2", kind="file_transfer", engine="sftp", src="a", dst="b", bytes_total=1000, status="running")
    task.start_time = 100.0
    callback = scheduler._progress_callback(task)

    with patch("src.core.scheduler.time.time", side_effect=[100.0, 101.0, 102.0]):
        callback(0, 1000)
        callback(400, 1000)
        callback(900, 1000)

    assert task.speed > 400


def test_progress_callback_does_not_advance_when_task_is_paused():
    scheduler = create_mock_scheduler()
    task = Task(
        task_id="pause-progress",
        kind="file_transfer",
        engine="sftp",
        src="a",
        dst="b",
        bytes_total=1000,
        bytes_done=400,
        status="paused",
        paused=True,
    )
    callback = scheduler._progress_callback(task)

    callback(700, 1000)

    assert task.bytes_done == 400
