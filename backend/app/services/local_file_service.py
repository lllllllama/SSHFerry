"""Local file system browsing service for the backend API."""
from __future__ import annotations

import fnmatch
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

    def search(
        self,
        raw_path: str,
        raw_query: str,
        *,
        limit: int = 120,
        max_depth: int = 5,
    ) -> tuple[str, str, list[LocalEntryResponse], int, bool]:
        target = self._resolve_existing_path(raw_path, require_dir=True)
        query = raw_query.strip()
        if not query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'q' is required",
            )

        terms = [term.casefold() for term in query.split() if term.strip()]
        limit = max(1, limit)
        max_depth = max(0, max_depth)
        matches: list[tuple[int, LocalEntryResponse]] = []
        scanned = 0
        truncated = False

        def walk(directory: Path, depth: int) -> None:
            nonlocal scanned, truncated
            if len(matches) >= limit:
                truncated = True
                return
            try:
                with os.scandir(directory) as iterator:
                    entries = sorted(
                        iterator,
                        key=lambda entry: (not entry.is_dir(follow_symlinks=False), entry.name.casefold()),
                    )
            except (OSError, PermissionError):
                return

            for entry in entries:
                if len(matches) >= limit:
                    truncated = True
                    return
                try:
                    stat_result = entry.stat(follow_symlinks=False)
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue

                scanned += 1
                entry_path = Path(entry.path).resolve(strict=False)
                relative_path = self._relative_display_path(target, entry_path)
                score = self._search_score(entry.name, relative_path, terms)
                if score is not None:
                    matches.append(
                        (
                            score,
                            LocalEntryResponse(
                                name=entry.name,
                                path=str(entry_path),
                                is_dir=is_dir,
                                size=0 if is_dir else int(stat_result.st_size),
                                mtime=float(stat_result.st_mtime),
                            ),
                        )
                    )

                if is_dir and depth < max_depth:
                    walk(entry_path, depth + 1)

        walk(target, 0)
        matches.sort(key=lambda pair: (pair[0], not pair[1].is_dir, pair[1].name.casefold(), pair[1].path.casefold()))
        return str(target), query, [entry for _, entry in matches[:limit]], scanned, truncated

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

    @staticmethod
    def _relative_display_path(root: Path, target: Path) -> str:
        try:
            return target.relative_to(root).as_posix()
        except ValueError:
            return target.as_posix()

    @staticmethod
    def _search_score(name: str, relative_path: str, terms: list[str]) -> int | None:
        name_folded = name.casefold()
        relative_folded = relative_path.replace('\\', '/').casefold()
        scores: list[int] = []

        for term in terms:
            normalized_term = term.replace('\\', '/')
            if any(char in normalized_term for char in '*?['):
                if fnmatch.fnmatchcase(name_folded, normalized_term) or fnmatch.fnmatchcase(relative_folded, normalized_term):
                    scores.append(0)
                    continue
                return None
            if normalized_term.startswith('.') and name_folded.endswith(normalized_term):
                scores.append(1)
                continue
            if name_folded == normalized_term:
                scores.append(0)
                continue
            if name_folded.startswith(normalized_term):
                scores.append(1)
                continue
            if normalized_term in name_folded:
                scores.append(2)
                continue
            if normalized_term in relative_folded:
                scores.append(3)
                continue
            return None

        return max(scores, default=3)

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
