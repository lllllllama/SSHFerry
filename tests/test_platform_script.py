"""Tests for the local platform diagnostics script."""

from __future__ import annotations

import builtins
import types

import _platform


def test_main_reports_qt_versions(monkeypatch, capsys):
    qtcore = types.SimpleNamespace(__version__="6.7.2", qVersion=lambda: "6.7.2")
    monkeypatch.setitem(_platform.sys.modules, "PySide6", types.SimpleNamespace(QtCore=qtcore))

    _platform.main()

    output = capsys.readouterr().out
    assert "Executable:" in output
    assert "Python:" in output
    assert "System:" in output
    assert "Platform tag:" in output
    assert "Implementation:" in output
    assert "Project dir:" in output
    assert "PySide6: 6.7.2" in output
    assert "Qt: 6.7.2" in output


def test_main_reports_qt_import_failure(monkeypatch, capsys):
    original_import = builtins.__import__

    def failing_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "PySide6":
            raise ModuleNotFoundError("missing test dependency")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(_platform.sys.modules, "PySide6", raising=False)
    monkeypatch.setattr(builtins, "__import__", failing_import)

    _platform.main()

    output = capsys.readouterr().out
    assert "PySide6: unavailable (ModuleNotFoundError: missing test dependency)" in output
