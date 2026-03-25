from __future__ import annotations

import os
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.ui.panels.task_center import TaskCenterPanel
from src.shared.models import Task


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
