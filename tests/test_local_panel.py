"""Smoke tests for the local file panel."""
import os

from PySide6.QtWidgets import QApplication, QFileIconProvider

from src.ui.panels.local_panel import LocalPanel, NameColumnDelegate


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def test_local_panel_configures_icon_provider_and_tree():
    _app()
    panel = LocalPanel()

    assert isinstance(panel.icon_provider, QFileIconProvider)
    assert panel.fs_model.iconProvider() is panel.icon_provider
    assert panel.tree.iconSize().width() == 18
    assert panel.tree.iconSize().height() == 18
    assert isinstance(panel.tree.itemDelegateForColumn(0), NameColumnDelegate)
    assert panel.fs_model.testOption(panel.fs_model.Option.DontUseCustomDirectoryIcons) is True


def test_local_panel_drag_animation_uses_pulse_highlight():
    _app()
    panel = LocalPanel()

    panel._start_drag_animation()

    assert panel._drag_pulse_timer.isActive() is True
    assert "border: 2px solid" in panel.tree.styleSheet()

    panel._stop_drag_animation()

    assert panel._drag_pulse_timer.isActive() is False
    assert panel.tree.styleSheet() == panel._base_tree_style


def test_local_panel_search_accepts_windows_style_patterns():
    _app()
    panel = LocalPanel()

    assert panel.path_edit.objectName() == "localPathInput"
    assert panel.search_edit.objectName() == "localSearchInput"

    panel.search_edit.setText("*.TXT")

    assert panel.model._search_terms == ["*.txt"]
    assert panel.model._search_score("Report.txt", "C:/work/Report.txt", panel.model._search_terms) == 0
    assert panel.model._search_score("notes.log", "C:/work/notes.log", panel.model._search_terms) is None

    panel.search_edit.setText(".log")

    assert panel.model._search_score("notes.LOG", "C:/work/notes.LOG", panel.model._search_terms) == 0

    panel.btn_clear_search.click()

    assert panel.search_edit.text() == ""
    assert panel.model._search_terms == []
