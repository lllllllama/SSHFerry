"""Smoke tests for the remote panel."""
import os
import time

from PySide6.QtWidgets import QApplication

from src.shared.models import RemoteEntry
from src.ui.i18n import tr
from src.ui.panels.remote_panel import RemotePanel


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def _entry(name: str, path: str, is_dir: bool = False, size: int = 0) -> RemoteEntry:
    return RemoteEntry(name=name, path=path, is_dir=is_dir, size=size, mtime=time.time())


def _spin_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.time() + timeout
    app = QApplication.instance()
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_remote_panel_populates_root_entries_asynchronously():
    _app()
    panel = RemotePanel()
    entries = [_entry("a.txt", "/a.txt", size=1), _entry("b.txt", "/b.txt", size=2)]

    panel.set_root_entries(entries)

    _spin_until(lambda: panel.tree.topLevelItemCount() == 2)
    assert panel.tree.topLevelItem(0).text(0) == "a.txt"
    assert panel.tree.topLevelItem(1).text(0) == "b.txt"


def test_remote_panel_discards_stale_root_population():
    _app()
    panel = RemotePanel()
    first_batch = [_entry(f"old-{idx}.txt", f"/old-{idx}.txt", size=idx) for idx in range(250)]
    second_batch = [_entry("fresh.txt", "/fresh.txt", size=1)]

    panel.set_root_entries(first_batch)
    panel.set_root_entries(second_batch)

    _spin_until(lambda: panel.tree.topLevelItemCount() == 1)
    assert panel.tree.topLevelItem(0).text(0) == "fresh.txt"


def test_remote_panel_drag_animation_uses_pulse_highlight():
    _app()
    panel = RemotePanel()

    panel._start_drag_animation()

    assert panel._drag_pulse_timer.isActive() is True
    assert "border: 2px solid" in panel.tree.styleSheet()

    panel._stop_drag_animation()

    assert panel._drag_pulse_timer.isActive() is False
    assert panel.tree.styleSheet() == panel._base_tree_stylesheet


def test_remote_panel_context_selection_preserves_multi_select_for_delete():
    _app()
    panel = RemotePanel()
    entries = [
        _entry("a.txt", "/remote/a.txt", size=1),
        _entry("b.txt", "/remote/b.txt", size=2),
    ]

    panel.set_root_entries(entries)
    _spin_until(lambda: panel.tree.topLevelItemCount() == 2)
    first = panel.tree.topLevelItem(0)
    second = panel.tree.topLevelItem(1)
    first.setSelected(True)
    second.setSelected(True)

    selected = panel._prepare_context_selection(first)

    assert [entry.path for entry in selected] == ["/remote/a.txt", "/remote/b.txt"]
    assert panel._delete_action_label(selected) == tr("label.delete_many", count=2)


def test_remote_panel_delete_selected_entries_emits_all_selected_paths():
    _app()
    panel = RemotePanel()
    entries = [
        _entry("a.txt", "/remote/a.txt", size=1),
        _entry("b.txt", "/remote/b.txt", size=2),
    ]
    emitted: list[list[str]] = []
    panel.request_delete_entries.connect(lambda selected: emitted.append([entry.path for entry in selected]))

    panel.set_root_entries(entries)
    _spin_until(lambda: panel.tree.topLevelItemCount() == 2)
    panel.tree.topLevelItem(0).setSelected(True)
    panel.tree.topLevelItem(1).setSelected(True)

    handled = panel._request_delete_selected_entries()

    assert handled is True
    assert emitted == [["/remote/a.txt", "/remote/b.txt"]]


def test_remote_panel_delete_action_ignores_qaction_checked_argument():
    _app()
    panel = RemotePanel()
    entry = _entry("a.txt", "/remote/a.txt", size=1)
    emitted: list[list[str]] = []
    panel.request_delete_entries.connect(lambda selected: emitted.append([item.path for item in selected]))

    panel._emit_delete_entries([entry], True)

    assert emitted == [["/remote/a.txt"]]
