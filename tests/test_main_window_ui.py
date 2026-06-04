from __future__ import annotations

import os
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.ui.panels.task_center import TaskCenterPanel
from src.shared.models import RemoteEntry, Task


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def test_list_response_scope_key_distinguishes_root_and_node():
    window = MainWindow.__new__(MainWindow)

    assert window._list_response_scope_key("sid", "/root", None) == ("sid", "root")
    assert window._list_response_scope_key("sid", "/root/child", object()) == (
        "sid",
        "node",
        "/root/child",
    )


def test_set_active_session_skips_restyle_when_unchanged():
    window = MainWindow.__new__(MainWindow)
    window.sessions = {"sid": object()}
    window._active_session_id = "sid"
    calls: list[tuple[str | None, str | None]] = []
    window._update_active_session_styles = lambda previous=None, current=None: calls.append((previous, current))

    window._set_active_session("sid")

    assert calls == []


def test_update_top_bar_status_skips_repeat_text_updates():
    class FakeLabel:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def setText(self, text: str) -> None:
            self.calls.append(text)

    window = MainWindow.__new__(MainWindow)
    window.sites = [object(), object()]
    window.sessions = {"a": object()}
    window._topbar_snapshot = None
    window.topbar_sites_label = FakeLabel()
    window.topbar_sessions_label = FakeLabel()
    window.topbar_tasks_label = FakeLabel()

    tasks = [Task(task_id="t1", kind="file_transfer", engine="sftp", src="a", dst="b", bytes_total=1)]

    window._update_top_bar_status(tasks)
    window._update_top_bar_status(tasks)

    assert window.topbar_sites_label.calls == ["Sites: 2"]
    assert window.topbar_sessions_label.calls == ["Sessions: 1"]
    assert window.topbar_tasks_label.calls == ["Active Tasks: 1"]


def test_task_center_reuses_checkbox_widget_for_same_task_ids():
    _app()
    panel = TaskCenterPanel()
    first = Task(task_id="t1", kind="file_transfer", engine="sftp", src="a", dst="b", bytes_total=100)
    second = Task(
        task_id="t1",
        kind="file_transfer",
        engine="sftp",
        src="a",
        dst="b",
        bytes_total=100,
        bytes_done=40,
        status="running",
    )

    panel.set_tasks([first])
    checkbox_widget = panel.table.cellWidget(0, 0)

    panel.set_tasks([second])

    assert panel.table.cellWidget(0, 0) is checkbox_widget


def test_remote_delete_prunes_nested_selected_entries():
    parent = RemoteEntry(name="folder", path="/remote/folder", is_dir=True, size=0, mtime=1.0)
    child = RemoteEntry(name="file.txt", path="/remote/folder/file.txt", is_dir=False, size=1, mtime=1.0)
    sibling = RemoteEntry(name="other.txt", path="/remote/other.txt", is_dir=False, size=1, mtime=1.0)

    pruned = MainWindow._prune_nested_remote_entries([child, sibling, parent, child])

    assert [entry.path for entry in pruned] == ["/remote/folder", "/remote/other.txt"]


def test_list_requests_are_queued_per_session():
    class FakeButton:
        def setEnabled(self, _enabled: bool) -> None:
            return None

    window = MainWindow.__new__(MainWindow)
    window.sessions = {"sid": SimpleNamespace(site=SimpleNamespace(name="demo"), refresh_button=FakeButton())}
    window._list_request_counter = 0
    window._inflight_list_requests = {}
    window._pending_list_requests = {}
    window._latest_list_response_ids = {}
    window._session_list_activity = {}
    window._max_remote_list_concurrency = 2
    started: list[str] = []
    window._start_list_request = lambda _sid, path, *_args: started.append(path)

    window._list_remote_dir("sid", "/remote/a")
    window._list_remote_dir("sid", "/remote/b")
    window._list_remote_dir("sid", "/remote/c")

    assert started == ["/remote/a", "/remote/b"]
    assert ("sid", "root", "/remote/c") in window._pending_list_requests

    window._finalize_list_request(("sid", "root", "/remote/a"))

    assert started == ["/remote/a", "/remote/b", "/remote/c"]


def test_list_completion_processes_current_result_before_draining_queue():
    class FakeButton:
        def setEnabled(self, _enabled: bool) -> None:
            return None

    class FakeLabel:
        def setText(self, _text: str) -> None:
            return None

    class FakePanel:
        current_path = "/remote/a"

        def __init__(self) -> None:
            self.root_entries: list[RemoteEntry] | None = None

        def set_path(self, path: str) -> None:
            self.current_path = path

        def set_root_entries(self, entries: list[RemoteEntry], preserve_state: bool = False) -> None:
            self.root_entries = entries

    panel = FakePanel()
    window = MainWindow.__new__(MainWindow)
    window.sessions = {
        "sid": SimpleNamespace(
            site=SimpleNamespace(name="demo"),
            refresh_button=FakeButton(),
            panel=panel,
            status_label=FakeLabel(),
        )
    }
    window._list_request_counter = 1
    window._inflight_list_requests = {("sid", "root", "/remote/a"): 1}
    window._pending_list_requests = {
        ("sid", "root", "/remote/b"): {
            "session_id": "sid",
            "path": "/remote/b",
            "parent_item": None,
            "retry_on_failure": False,
            "suppress_error_dialog": False,
        }
    }
    window._latest_list_response_ids = {("sid", "root"): 1}
    window._session_list_activity = {"sid": 1}
    window._max_remote_list_concurrency = 1
    window._start_list_request = lambda *_args: None
    entries = [RemoteEntry(name="a.txt", path="/remote/a/a.txt", is_dir=False, size=1, mtime=1.0)]

    window._on_list_completed(
        "sid",
        "/remote/a",
        entries,
        None,
        1,
        ("sid", "root", "/remote/a"),
        ("sid", "root"),
        "demo",
    )

    assert panel.root_entries == entries
    assert ("sid", "root", "/remote/b") in window._inflight_list_requests


def test_list_queue_does_not_spin_on_duplicate_inflight_request():
    class FakeButton:
        def setEnabled(self, _enabled: bool) -> None:
            return None

    window = MainWindow.__new__(MainWindow)
    window.sessions = {"sid": SimpleNamespace(site=SimpleNamespace(name="demo"), refresh_button=FakeButton())}
    window._list_request_counter = 0
    window._inflight_list_requests = {}
    window._pending_list_requests = {}
    window._latest_list_response_ids = {}
    window._session_list_activity = {}
    window._max_remote_list_concurrency = 2
    started: list[str] = []
    window._start_list_request = lambda _sid, path, *_args: started.append(path)

    window._list_remote_dir("sid", "/remote/a")
    window._list_remote_dir("sid", "/remote/b")
    window._list_remote_dir("sid", "/remote/a")

    assert started == ["/remote/a", "/remote/b"]
    assert ("sid", "root", "/remote/a") in window._pending_list_requests

    window._finalize_list_request(("sid", "root", "/remote/b"))

    assert started == ["/remote/a", "/remote/b"]
    assert ("sid", "root", "/remote/a") in window._pending_list_requests

    window._finalize_list_request(("sid", "root", "/remote/a"))

    assert started == ["/remote/a", "/remote/b", "/remote/a"]
