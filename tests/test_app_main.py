"""Tests for desktop app startup helpers."""

from __future__ import annotations

from pathlib import Path
import sys
import types

from src.app import main as app_main


def test_resource_path_finds_project_icon(monkeypatch):
    monkeypatch.delattr(app_main.sys, "_MEIPASS", raising=False)

    icon_path = app_main._resource_path("src", "ui", "assets", "app_icon.png")

    expected = Path(app_main.__file__).resolve().parents[2] / "src" / "ui" / "assets" / "app_icon.png"
    assert icon_path == expected


def test_apply_application_icon_prefers_png(monkeypatch):
    class FakeIcon:
        def __init__(self, path: str):
            self.path = path

        def isNull(self) -> bool:
            return False

    class FakeApp:
        def __init__(self) -> None:
            self.icon = None

        def setWindowIcon(self, icon) -> None:
            self.icon = icon

    fake_qtgui = types.SimpleNamespace(QIcon=FakeIcon)
    monkeypatch.setitem(sys.modules, "PySide6", types.ModuleType("PySide6"))
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", fake_qtgui)
    monkeypatch.setattr(
        app_main,
        "_resource_path",
        lambda *parts: Path("chosen.png") if parts[-1] == "app_icon.png" else None,
    )

    app = FakeApp()
    app_main._apply_application_icon(app)

    assert isinstance(app.icon, FakeIcon)
    assert app.icon.path == "chosen.png"
