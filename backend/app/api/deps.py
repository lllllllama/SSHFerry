"""Shared API dependencies."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, WebSocket, WebSocketException, status

from backend.app.services.app_state import AppState


X_SSHFERRY_TOKEN = 'X-SSHFerry-Token'


def get_app_state(request: Request) -> AppState:
    """Return the singleton app state stored on the FastAPI app."""
    return request.app.state.app_state


def get_websocket_app_state(websocket: WebSocket) -> AppState:
    """Return the singleton app state stored on the FastAPI app for websocket routes."""
    return websocket.app.state.app_state


def require_local_token(
    request: Request,
    x_sshferry_token: str | None = Header(default=None, alias=X_SSHFERRY_TOKEN),
) -> None:
    """Protect local backend routes with an in-memory session token."""
    app_state = get_app_state(request)
    if not x_sshferry_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f'Missing {X_SSHFERRY_TOKEN} header',
        )
    if not secrets.compare_digest(x_sshferry_token, app_state.auth_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid local session token',
        )


def require_websocket_local_token(websocket: WebSocket) -> AppState:
    """Validate websocket token via query string or header and return app state."""
    app_state = get_websocket_app_state(websocket)
    provided = websocket.query_params.get('token') or websocket.headers.get(X_SSHFERRY_TOKEN)
    if not provided:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=f'Missing {X_SSHFERRY_TOKEN}')
    if not secrets.compare_digest(provided, app_state.auth_token):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason='Invalid local session token')
    return app_state
