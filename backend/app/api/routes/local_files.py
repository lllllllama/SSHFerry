"""Local file system routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.schemas.local_files import LocalDrivesListResponse, LocalListResponse, LocalStatResponse
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


@router.get('/stat', response_model=LocalStatResponse)
def stat_local_path(path: str = Query(..., min_length=1)) -> LocalStatResponse:
    service = LocalFileService()
    return LocalStatResponse(entry=service.stat_path(path))
