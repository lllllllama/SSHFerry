"""Local file system browsing service for the backend API."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from fastapi import HTTPException, status

from backend.app.schemas.local_files import LocalDriveResponse, LocalEntryResponse


class LocalFileService:
    """Read-only local file system operations used by the frontend."""

    def list_drives(self) -> list[LocalDriveResponse]:
        drives = self._available_drives()
        return [LocalDriveResponse(path=drive, label=drive.rstrip('/\\')) for drive in drives]

    def list_dir(self, raw_path: str) -> tuple[str, str | None, list[LocalEntryResponse]]:
        target = self._resolve_existing_path(raw_path, require_dir=True)
        items: list[LocalEntryResponse] = []
        try:
            with os.scandir(target) as entries:
                for entry in entries:
                    try:
                        stat_result = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    items.append(
                        LocalEntryResponse(
                            name=entry.name,
                            path=str(Path(entry.path).resolve(strict=False)),
                            is_dir=entry.is_dir(follow_symlinks=False),
                            size=0 if entry.is_dir(follow_symlinks=False) else int(stat_result.st_size),
                            mtime=float(stat_result.st_mtime),
                        )
                    )
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {target}",
            ) from exc

        items.sort(key=lambda item: (not item.is_dir, item.name.lower()))
        parent_path = self._parent_path(target)
        return str(target), parent_path, items

    def stat_path(self, raw_path: str) -> LocalEntryResponse:
        target = self._resolve_existing_path(raw_path)
        try:
            stat_result = target.stat()
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {target}",
            ) from exc
        return LocalEntryResponse(
            name=target.name or str(target),
            path=str(target),
            is_dir=target.is_dir(),
            size=0 if target.is_dir() else int(stat_result.st_size),
            mtime=float(stat_result.st_mtime),
        )

    def _resolve_existing_path(self, raw_path: str, *, require_dir: bool = False) -> Path:
        if not raw_path or not raw_path.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'path' is required",
            )
        target = Path(raw_path).expanduser().resolve(strict=False)
        if not target.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path not found: {raw_path}",
            )
        if require_dir and not target.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Path is not a directory: {raw_path}",
            )
        return target

    def _parent_path(self, target: Path) -> str | None:
        parent = target.parent
        if parent == target:
            return None
        return str(parent)

    def _available_drives(self) -> list[str]:
        if sys.platform != 'win32':
            return ['/']

        drives: list[str] = []
        try:
            import ctypes

            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                if bitmask & 1:
                    drives.append(f'{letter}:/')
                bitmask >>= 1
        except Exception:
            for letter in 'CDEFGHIJ':
                drive = f'{letter}:/'
                if os.path.exists(drive):
                    drives.append(drive)

        return drives if drives else ['C:/']
