"""Remote file system routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from backend.app.api.deps import get_app_state, require_current_user
from backend.app.schemas.remote_files import (
    RemoteBulkDeleteRequest,
    RemoteBulkDeleteResponse,
    RemoteDeleteRequest,
    RemoteListResponse,
    RemoteMkdirRequest,
    RemoteRenameRequest,
    RemoteStatResponse,
)
from backend.app.services.app_state import AppState
from backend.app.services.auth_service import AuthContext
from backend.app.services.remote_file_service import RemoteFileService


router = APIRouter(prefix='/remote-files', tags=['remote-files'])


@router.get('/list', response_model=RemoteListResponse)
def list_remote_dir(
    session_id: str = Query(..., min_length=1),
    path: str | None = Query(default=None),
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> RemoteListResponse:
    service = RemoteFileService(app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    current_path, parent_path, items = service.list_dir(session_id, path)
    return RemoteListResponse(
        session_id=session_id,
        current_path=current_path,
        parent_path=parent_path,
        items=items,
        total=len(items),
    )


@router.get('/stat', response_model=RemoteStatResponse)
def stat_remote_path(
    session_id: str = Query(..., min_length=1),
    path: str = Query(..., min_length=1),
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> RemoteStatResponse:
    service = RemoteFileService(app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    return RemoteStatResponse(entry=service.stat_path(session_id, path))


@router.post('/mkdir', status_code=status.HTTP_204_NO_CONTENT)
def mkdir_remote_path(
    payload: RemoteMkdirRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> Response:
    service = RemoteFileService(app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    service.mkdir(payload.session_id, payload.path)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='success',
        category='remote',
        action='mkdir',
        title='Remote directory created',
        message=f'{payload.session_id}:{payload.path}',
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/rename', status_code=status.HTTP_204_NO_CONTENT)
def rename_remote_path(
    payload: RemoteRenameRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> Response:
    service = RemoteFileService(app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    service.rename(payload.session_id, payload.old_path, payload.new_path)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='info',
        category='remote',
        action='rename',
        title='Remote path renamed',
        message=f'{payload.old_path} -> {payload.new_path}',
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/delete', status_code=status.HTTP_204_NO_CONTENT)
def delete_remote_path(
    payload: RemoteDeleteRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> Response:
    service = RemoteFileService(app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    service.delete(payload.session_id, payload.path, recursive=payload.recursive)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='warning',
        category='remote',
        action='delete',
        title='Remote path deleted',
        message=f'{payload.session_id}:{payload.path}',
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/bulk-delete', response_model=RemoteBulkDeleteResponse)
def bulk_delete_remote_paths(
    payload: RemoteBulkDeleteRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> RemoteBulkDeleteResponse:
    service = RemoteFileService(app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    deleted_paths = service.delete_many(payload.session_id, payload.paths, recursive=payload.recursive)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='warning',
        category='remote',
        action='delete',
        title='Remote paths deleted',
        message=f'{payload.session_id}:{len(deleted_paths)} path(s)',
    )
    return RemoteBulkDeleteResponse(deleted_paths=deleted_paths, total=len(deleted_paths))
