"""Connection check and session routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from backend.app.api.deps import get_app_state, require_current_user
from backend.app.schemas.connections import (
    ConnectionCheckRequest,
    ConnectionCheckResponse,
    SessionCloseRequest,
    SessionListResponse,
    SessionOpenRequest,
    SessionResponse,
)
from backend.app.services.app_state import AppState
from backend.app.services.auth_service import AuthContext
from backend.app.services.connection_service import ConnectionService


router = APIRouter(tags=['connections', 'sessions'])


@router.post('/connections/check', response_model=ConnectionCheckResponse)
def check_connection(
    payload: ConnectionCheckRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> ConnectionCheckResponse:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    response = ConnectionCheckResponse.model_validate(service.run_check(payload))
    passed_count = sum(1 for item in response.results if item.passed)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='success' if response.all_passed else 'warning',
        category='session',
        action='checked',
        title='Connection check completed',
        message=f'{response.site_name}: {passed_count}/{len(response.results)} checks passed.',
    )
    return response


@router.get('/sessions', response_model=SessionListResponse)
def list_sessions(
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> SessionListResponse:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    items = service.list_sessions()
    return SessionListResponse(items=items, total=len(items))


@router.post('/sessions/open', response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def open_session(
    payload: SessionOpenRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> SessionResponse:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    response = service.open_session(payload)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='success',
        category='session',
        action='opened',
        title='Remote session opened',
        message=f'{response.site_name} -> {response.session_id}',
    )
    return response


@router.post('/sessions/close', status_code=status.HTTP_204_NO_CONTENT)
def close_session(
    payload: SessionCloseRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> Response:
    service = ConnectionService(app_state.site_store, app_state.remote_sessions, context.user.user_id, app_state.session_lock)
    service.close_session(payload.session_id)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='info',
        category='session',
        action='closed',
        title='Remote session closed',
        message=f'Session {payload.session_id} was closed.',
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
