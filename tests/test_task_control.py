"""Tests for task control (pause/resume/restart) and interactivity."""
import time
from unittest.mock import MagicMock, patch

import pytest
from src.core.scheduler import TaskScheduler
from src.shared.models import SiteConfig, Task


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
    assert mock_scheduler.task_queue.qsize() == 1
    
    # 3. Simulate failure
    with mock_scheduler.task_lock:
        task.status = "failed"
        task.error_message = "Network error"
        
    # 4. Test Restart
    assert mock_scheduler.restart_task("t1") is True
    assert task.status == "pending"
    assert task.error_message is None
    assert mock_scheduler.task_queue.qsize() == 2  # Re-queued again


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
