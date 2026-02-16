"""Tests for SCP routing, fallback behavior, and protocol-aware scheduling."""
from unittest.mock import MagicMock, patch

import pytest

from src.core.scheduler import TaskScheduler
from src.shared.errors import ErrorCode, SSHFerryError
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
        default_transfer_protocol="sftp",
    )


def test_scp_upload_fallback_to_sftp_once():
    class FakeScpEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        def connect(self):
            return None

        def disconnect(self):
            return None

        def upload_file(self, *_args, **_kwargs):
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "scp failed")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(_site(), logger=MagicMock())
    task = Task(
        task_id="u1",
        kind="upload",
        engine="scp",
        src="a.bin",
        dst="/a.bin",
        bytes_total=10,
    )
    task.start_time = 1.0

    called = {"fallback": 0}

    def _fallback(_task):
        called["fallback"] += 1

    with patch("src.core.scheduler.ScpEngine", FakeScpEngine):
        scheduler._execute_upload = _fallback
        scheduler._execute_scp_upload(task)

    assert called["fallback"] == 1


def test_scp_upload_fallback_failure_surfaces_both_errors():
    class FakeScpEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        def connect(self):
            return None

        def disconnect(self):
            return None

        def upload_file(self, *_args, **_kwargs):
            raise SSHFerryError(ErrorCode.TRANSFER_FAILED, "scp failed")

    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(_site(), logger=MagicMock())
    task = Task(
        task_id="u2",
        kind="upload",
        engine="scp",
        src="a.bin",
        dst="/a.bin",
        bytes_total=10,
    )
    task.start_time = 1.0

    def _fallback(_task):
        raise RuntimeError("sftp failed")

    with patch("src.core.scheduler.ScpEngine", FakeScpEngine):
        scheduler._execute_upload = _fallback
        with pytest.raises(SSHFerryError) as exc:
            scheduler._execute_scp_upload(task)
    assert "SCP failed" in exc.value.message
    assert "fallback SFTP failed" in exc.value.message


def test_protocol_limit_affects_selection():
    with patch("src.core.scheduler.MetricsCollector"):
        scheduler = TaskScheduler(
            _site(),
            logger=MagicMock(),
            max_workers=3,
            max_workers_sftp=3,
            max_workers_scp=2,
            max_workers_parallel=1,
        )
    t1 = Task(task_id="p1", kind="upload", engine="parallel", src="a", dst="b", bytes_total=1)
    t2 = Task(task_id="s1", kind="upload", engine="sftp", src="a", dst="b", bytes_total=1)
    scheduler.add_task(t1)
    scheduler.add_task(t2)

    with scheduler.task_lock:
        scheduler.active_by_protocol["parallel"] = 1
        picked = scheduler._select_next_runnable_task_locked()

    assert picked is not None
    _, task, protocol = picked
    assert protocol == "sftp"
    assert task.task_id == "s1"


def test_create_task_keeps_scp_when_auto_engine_enabled():
    task = TaskScheduler.create_upload_task(
        "a.bin",
        "/a.bin",
        file_size=1024 * 1024 * 1024,
        engine="scp",
        auto_engine=True,
    )
    assert task.engine == "scp"
