"""Tests for direction-aware parallel preset selection in scheduler."""
from unittest.mock import MagicMock, patch

from src.core.scheduler import TaskScheduler
from src.shared.models import SiteConfig, Task


def _site() -> SiteConfig:
    return SiteConfig(
        name="test",
        host="localhost",
        port=22,
        username="user",
        auth_method="password",
        password="pwd",
        remote_root="/",
    )


def test_parallel_upload_uses_upload_preset(monkeypatch):
    captured = {}

    class FakeParallelEngine:
        def __init__(self, _site, _logger, preset_name=None):
            captured["preset"] = preset_name

        def upload_file(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("src.core.scheduler.ParallelSftpEngine", FakeParallelEngine)
    scheduler = TaskScheduler(_site(), logger=MagicMock())
    task = Task(
        task_id="u1",
        kind="upload",
        engine="parallel",
        src="a",
        dst="b",
        bytes_total=1,
    )
    scheduler._execute_parallel_upload(task)
    assert captured["preset"] == "medium"


def test_parallel_download_uses_download_preset(monkeypatch):
    captured = {}

    class FakeParallelEngine:
        def __init__(self, _site, _logger, preset_name=None):
            captured["preset"] = preset_name

        def download_file(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("src.core.scheduler.ParallelSftpEngine", FakeParallelEngine)
    scheduler = TaskScheduler(_site(), logger=MagicMock())
    task = Task(
        task_id="d1",
        kind="download",
        engine="parallel",
        src="a",
        dst="b",
        bytes_total=1,
    )
    scheduler._execute_parallel_download(task)
    assert captured["preset"] == "high"


def test_metric_preset_for_non_parallel_task():
    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(_site(), logger=MagicMock())
    task = Task(
        task_id="s1",
        kind="upload",
        engine="sftp",
        src="a",
        dst="b",
        bytes_total=1,
    )
    assert scheduler._metric_preset_for_task(task) == "sftp"
