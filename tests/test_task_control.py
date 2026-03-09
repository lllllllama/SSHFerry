"""Tests for task control (pause/resume/restart) and interactivity."""
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from src.core.scheduler import TaskScheduler
from src.shared.errors import ErrorCode, SSHFerryError
from src.shared.models import RemoteEntry, SiteConfig, Task


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
