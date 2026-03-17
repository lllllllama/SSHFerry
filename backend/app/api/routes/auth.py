"""Local auth bootstrap routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import X_SSHFERRY_TOKEN, get_app_state
from backend.app.services.app_state import AppState


router = APIRouter(prefix='/auth', tags=['auth'])


@router.get('/session')
def get_local_session(app_state: AppState = Depends(get_app_state)) -> dict[str, object]:
    """Return the current local backend token for trusted frontend bootstrapping."""
    return {
        'token': app_state.auth_token,
        'header_name': X_SSHFERRY_TOKEN,
        'token_type': 'local',
    }
