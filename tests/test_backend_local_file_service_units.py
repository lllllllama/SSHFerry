"""Unit tests for LocalFileService edge branches."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.services.local_file_service import LocalFileService


@pytest.fixture
def service() -> LocalFileService:
    return LocalFileService()


def test_search_requires_non_empty_query(service, tmp_path: Path):
    with pytest.raises(HTTPException) as excinfo:
        service.search(str(tmp_path), "   ")
    assert excinfo.value.status_code == 400


def test_search_skips_unreadable_directories(service, tmp_path: Path, monkeypatch):
    (tmp_path / "match.txt").write_text("x", encoding="utf-8")
    blocked = tmp_path / "blocked"
    blocked.mkdir()

    real_scandir = os.scandir

    def fake_scandir(path):
        if Path(path) == blocked.resolve():
            raise PermissionError("denied")
        return real_scandir(path)

    monkeypatch.setattr("backend.app.services.local_file_service.os.scandir", fake_scandir)

    _target, _query, items, _scanned, truncated = service.search(str(tmp_path), "match")

    assert [item.name for item in items] == ["match.txt"]
    assert truncated is False


def test_search_skips_entries_that_fail_stat(service, tmp_path: Path, monkeypatch):
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    (tmp_path / "gone.txt").write_text("x", encoding="utf-8")

    real_scandir = os.scandir

    class FlakyEntry:
        def __init__(self, entry):
            self._entry = entry
            self.name = entry.name
            self.path = entry.path

        def is_dir(self, follow_symlinks=True):
            return self._entry.is_dir(follow_symlinks=follow_symlinks)

        def stat(self, follow_symlinks=True):
            if self.name == "gone.txt":
                raise OSError("vanished")
            return self._entry.stat(follow_symlinks=follow_symlinks)

    class FlakyScandir:
        def __init__(self, path):
            self._iterator = real_scandir(path)

        def __enter__(self):
            return (FlakyEntry(entry) for entry in self._iterator)

        def __exit__(self, exc_type, exc, tb):
            self._iterator.close()
            return False

    monkeypatch.setattr(
        "backend.app.services.local_file_service.os.scandir",
        lambda path: FlakyScandir(path),
    )

    _target, _query, items, scanned, _truncated = service.search(str(tmp_path), "txt")

    assert [item.name for item in items] == ["ok.txt"]
    assert scanned == 1


def test_search_marks_truncation_before_descending(service, tmp_path: Path):
    sub = tmp_path / "a_sub"
    sub.mkdir()
    (sub / "match_deep.txt").write_text("x", encoding="utf-8")
    (tmp_path / "match_top.txt").write_text("x", encoding="utf-8")

    _target, _query, items, _scanned, truncated = service.search(
        str(tmp_path), "match", limit=1
    )

    assert len(items) == 1
    assert truncated is True


def test_search_stops_descent_once_limit_is_reached(service, tmp_path: Path):
    matching_dir = tmp_path / "match_dir"
    matching_dir.mkdir()
    (matching_dir / "match_child.txt").write_text("x", encoding="utf-8")

    _target, _query, items, _scanned, truncated = service.search(
        str(tmp_path), "match", limit=1
    )

    assert [item.name for item in items] == ["match_dir"]
    assert truncated is True


def test_available_drives_reads_windows_drive_bitmask(service, monkeypatch):
    import ctypes
    from types import SimpleNamespace

    monkeypatch.setattr("backend.app.services.local_file_service.sys.platform", "win32")
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(kernel32=SimpleNamespace(GetLogicalDrives=lambda: 0b1100)),
        raising=False,
    )

    assert service._available_drives() == ["C:/", "D:/"]


def test_relative_display_path_falls_back_for_unrelated_paths():
    root = Path("/tmp/root-a")
    target = Path("/tmp/other-b/file.txt")
    assert LocalFileService._relative_display_path(root, target) == target.as_posix()


def test_search_score_covers_match_tiers():
    score = LocalFileService._search_score
    # glob pattern hit and miss
    assert score("notes.txt", "notes.txt", ["*.txt"]) == 0
    assert score("notes.txt", "notes.txt", ["*.zzz"]) is None
    # extension suffix shorthand
    assert score("notes.txt", "notes.txt", [".txt"]) == 1
    # exact, prefix, substring, relative-path-only tiers
    assert score("notes", "dir/notes", ["notes"]) == 0
    assert score("notes.txt", "dir/notes.txt", ["note"]) == 1
    assert score("mynotes.txt", "dir/mynotes.txt", ["notes"]) == 2
    assert score("file.txt", "special-dir/file.txt", ["special"]) == 3
    # no tier matches at all
    assert score("file.txt", "dir/file.txt", ["absent"]) is None


def test_available_drives_windows_fallback(service, monkeypatch):
    monkeypatch.setattr("backend.app.services.local_file_service.sys.platform", "win32")

    drives = service._available_drives()

    # On non-Windows hosts the ctypes probe fails and no drive letters
    # exist, so the fallback default applies.
    assert drives == ["C:/"]


def test_list_drives_uses_drive_path_as_label_for_posix_root(service, monkeypatch):
    monkeypatch.setattr(service, "_available_drives", lambda: ["/", "D:/"])

    items = service.list_drives()

    assert [(item.path, item.label) for item in items] == [("/", "/"), ("D:/", "D:")]
