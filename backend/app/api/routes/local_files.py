"""Local file system routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.schemas.local_files import (
    LocalDrivesListResponse,
    LocalListResponse,
    LocalSearchResponse,
    LocalStatResponse,
)
from backend.app.services.local_file_service import LocalFileService


router = APIRouter(prefix='/local-files', tags=['local-files'])


@router.get('/drives', response_model=LocalDrivesListResponse)
def list_drives() -> LocalDrivesListResponse:
    service = LocalFileService()
    items = service.list_drives()
    return LocalDrivesListResponse(items=items, total=len(items))


@router.get('/list', response_model=LocalListResponse)
def list_local_dir(path: str = Query(..., min_length=1)) -> LocalListResponse:
    service = LocalFileService()
    current_path, parent_path, items = service.list_dir(path)
    return LocalListResponse(
        current_path=current_path,
        parent_path=parent_path,
        items=items,
        total=len(items),
    )


@router.get('/search', response_model=LocalSearchResponse)
def search_local_files(
    path: str = Query(..., min_length=1),
    q: str = Query(..., min_length=1),
    limit: int = Query(120, ge=1, le=500),
    max_depth: int = Query(5, ge=0, le=8),
) -> LocalSearchResponse:
    service = LocalFileService()
    current_path, query, items, scanned, truncated = service.search(path, q, limit=limit, max_depth=max_depth)
    return LocalSearchResponse(
        current_path=current_path,
        query=query,
        items=items,
        total=len(items),
        scanned=scanned,
        truncated=truncated,
    )


@router.get('/stat', response_model=LocalStatResponse)
def stat_local_path(path: str = Query(..., min_length=1)) -> LocalStatResponse:
    service = LocalFileService()
    return LocalStatResponse(entry=service.stat_path(path))
