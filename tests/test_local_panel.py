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
    assert panel.model.iconProvider() is panel.icon_provider
    assert panel.tree.iconSize().width() == 18
    assert panel.tree.iconSize().height() == 18
    assert panel.model.testOption(panel.model.Option.DontUseCustomDirectoryIcons) is True
