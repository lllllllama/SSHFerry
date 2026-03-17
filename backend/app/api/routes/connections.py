"""Connection check and session routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from backend.app.api.deps import get_app_state
from backend.app.schemas.connections import (
    ConnectionCheckRequest,
    ConnectionCheckResponse,
    SessionCloseRequest,
    SessionListResponse,
    SessionOpenRequest,
    SessionResponse,
)
from backend.app.services.app_state import AppState
from backend.app.services.connection_service import ConnectionService


router = APIRouter(tags=['connections', 'sessions'])


@router.post('/connections/check', response_model=ConnectionCheckResponse)
def check_connection(
    payload: ConnectionCheckRequest,
    app_state: AppState = Depends(get_app_state),
) -> ConnectionCheckResponse:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, app_state.session_lock)
    return service.run_check(payload)


@router.get('/sessions', response_model=SessionListResponse)
def list_sessions(app_state: AppState = Depends(get_app_state)) -> SessionListResponse:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, app_state.session_lock)
    items = service.list_sessions()
    return SessionListResponse(items=items, total=len(items))


@router.post('/sessions/open', response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def open_session(
    payload: SessionOpenRequest,
    app_state: AppState = Depends(get_app_state),
) -> SessionResponse:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, app_state.session_lock)
    return service.open_session(payload)


@router.post('/sessions/close', status_code=status.HTTP_204_NO_CONTENT)
def close_session(
    payload: SessionCloseRequest,
    app_state: AppState = Depends(get_app_state),
) -> Response:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, app_state.session_lock)
    service.close_session(payload.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
