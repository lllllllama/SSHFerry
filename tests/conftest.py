"""Test environment guards for optional GUI dependencies."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _has_qt_widgets() -> bool:
    try:
        from PySide6 import QtWidgets  # noqa: F401
    except Exception:
        return False
    return True


collect_ignore_glob = []
if not _has_qt_widgets():
    collect_ignore_glob.append("test_local_panel.py")
