from __future__ import annotations

from pathlib import Path

from src.shared import runtime_paths


def test_app_data_dir_prefers_env_override(monkeypatch, tmp_path: Path):
    target = tmp_path / "portable-data"
    monkeypatch.setenv("SSHFERRY_DATA_DIR", str(target))
    monkeypatch.setattr(runtime_paths, "is_frozen_runtime", lambda: False)

    assert runtime_paths.app_data_dir() == target


def test_app_data_dir_uses_portable_folder_for_frozen_runtime(monkeypatch, tmp_path: Path):
    exe_path = tmp_path / "bundle" / "SSHFerry.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_text("", encoding="utf-8")
    monkeypatch.delenv("SSHFERRY_DATA_DIR", raising=False)
    monkeypatch.setattr(runtime_paths, "is_frozen_runtime", lambda: True)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(exe_path))

    assert runtime_paths.app_data_dir() == exe_path.parent / "data"


def test_app_data_dir_falls_back_to_user_dir_when_portable_dir_is_read_only(monkeypatch, tmp_path: Path):
    exe_path = tmp_path / "bundle" / "SSHFerry.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_text("", encoding="utf-8")
    user_home = tmp_path / "home"
    portable_dir = exe_path.parent / "data"
    fallback_dir = user_home / "AppData" / "Local" / "SSHFerry"

    original_mkdir = Path.mkdir

    def fake_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if self == portable_dir:
            raise PermissionError("read-only")
        return original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.delenv("SSHFERRY_DATA_DIR", raising=False)
    monkeypatch.setattr(runtime_paths, "is_frozen_runtime", lambda: True)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(exe_path))
    monkeypatch.setattr(Path, "home", lambda: user_home)
    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    assert runtime_paths.app_data_dir() == fallback_dir
