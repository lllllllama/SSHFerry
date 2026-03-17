"""Task routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from backend.app.api.deps import get_app_state
from backend.app.schemas.tasks import (
    TaskActionResponse,
    TaskCreateDownloadRequest,
    TaskCreateRemoteCopyRequest,
    TaskCreateUploadRequest,
    TaskListResponse,
    TaskResponse,
)
from backend.app.services.app_state import AppState
from backend.app.services.task_service import TaskService


router = APIRouter(prefix='/tasks', tags=['tasks'])


@router.get('', response_model=TaskListResponse)
def list_tasks(app_state: AppState = Depends(get_app_state)) -> TaskListResponse:
    service = TaskService(app_state)
    items = service.list_tasks()
    return TaskListResponse(items=items, total=len(items))


@router.post('/upload', response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_upload_task(
    payload: TaskCreateUploadRequest,
    app_state: AppState = Depends(get_app_state),
) -> TaskResponse:
    service = TaskService(app_state)
    return service.create_upload(payload)


@router.post('/download', response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_download_task(
    payload: TaskCreateDownloadRequest,
    app_state: AppState = Depends(get_app_state),
) -> TaskResponse:
    service = TaskService(app_state)
    return service.create_download(payload)


@router.post('/remote-copy', response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_remote_copy_task(
    payload: TaskCreateRemoteCopyRequest,
    app_state: AppState = Depends(get_app_state),
) -> TaskResponse:
    service = TaskService(app_state)
    return service.create_remote_copy(payload)


@router.post('/{task_id}/pause', response_model=TaskActionResponse)
def pause_task(task_id: str, app_state: AppState = Depends(get_app_state)) -> TaskActionResponse:
    service = TaskService(app_state)
    return service.pause_task(task_id)


@router.post('/{task_id}/resume', response_model=TaskActionResponse)
def resume_task(task_id: str, app_state: AppState = Depends(get_app_state)) -> TaskActionResponse:
    service = TaskService(app_state)
    return service.resume_task(task_id)


@router.post('/{task_id}/cancel', response_model=TaskActionResponse)
def cancel_task(task_id: str, app_state: AppState = Depends(get_app_state)) -> TaskActionResponse:
    service = TaskService(app_state)
    return service.cancel_task(task_id)


@router.post('/{task_id}/restart', response_model=TaskActionResponse)
def restart_task(task_id: str, app_state: AppState = Depends(get_app_state)) -> TaskActionResponse:
    service = TaskService(app_state)
    return service.restart_task(task_id)


@router.delete('/finished', status_code=status.HTTP_204_NO_CONTENT)
def clear_finished_tasks(app_state: AppState = Depends(get_app_state)) -> Response:
    service = TaskService(app_state)
    service.clear_finished_tasks()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
