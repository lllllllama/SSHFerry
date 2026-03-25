"""Smoke tests for the local file panel."""
import os

from PySide6.QtWidgets import QApplication, QFileIconProvider

from src.ui.panels.local_panel import LocalPanel


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
