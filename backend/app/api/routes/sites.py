"""Site configuration routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from backend.app.api.deps import get_app_state, require_current_user
from backend.app.schemas.sites import (
    SiteBulkDeleteRequest,
    SiteBulkDeleteResponse,
    SiteListResponse,
    SiteResponse,
    SiteUpsertRequest,
)
from backend.app.services.app_state import AppState
from backend.app.services.auth_service import AuthContext
from backend.app.services.site_service import SiteService


router = APIRouter(prefix='/sites', tags=['sites'])


@router.get('', response_model=SiteListResponse)
def list_sites(
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> SiteListResponse:
    service = SiteService(app_state.site_store, context.user.user_id)
    items = [service.to_response(site) for site in service.list_sites()]
    return SiteListResponse(items=items, total=len(items))


@router.post('', response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteUpsertRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> SiteResponse:
    service = SiteService(app_state.site_store, context.user.user_id)
    site = service.create_site(payload)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='success',
        category='site',
        action='created',
        title='Site created',
        message=f'{site.name} ({site.username}@{site.host}:{site.port})',
    )
    return service.to_response(site)


@router.put('/{site_name}', response_model=SiteResponse)
def update_site(
    site_name: str,
    payload: SiteUpsertRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> SiteResponse:
    service = SiteService(app_state.site_store, context.user.user_id)
    site = service.update_site(site_name, payload)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='info',
        category='site',
        action='updated',
        title='Site updated',
        message=f'{site.name} ({site.username}@{site.host}:{site.port})',
    )
    return service.to_response(site)


@router.delete('/{site_name}', status_code=status.HTTP_204_NO_CONTENT)
def delete_site(
    site_name: str,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> Response:
    service = SiteService(app_state.site_store, context.user.user_id)
    service.delete_site(site_name)
    with app_state.session_lock:
        expired_sessions = [
            sid
            for sid, site in app_state.remote_sessions.items()
            if site.name == site_name and site.owner_user_id in (None, context.user.user_id)
        ]
        for session_id in expired_sessions:
            app_state.remote_sessions.pop(session_id, None)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='warning',
        category='site',
        action='deleted',
        title='Site deleted',
        message=f'{site_name}; closed {len(expired_sessions)} related session(s).',
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/bulk-delete', response_model=SiteBulkDeleteResponse)
def bulk_delete_sites(
    payload: SiteBulkDeleteRequest,
    context: AuthContext = Depends(require_current_user),
    app_state: AppState = Depends(get_app_state),
) -> SiteBulkDeleteResponse:
    service = SiteService(app_state.site_store, context.user.user_id)
    deleted_names = service.delete_sites(payload.names)
    deleted_name_set = set(deleted_names)
    with app_state.session_lock:
        expired_sessions = [
            sid
            for sid, site in app_state.remote_sessions.items()
            if site.name in deleted_name_set and site.owner_user_id in (None, context.user.user_id)
        ]
        for session_id in expired_sessions:
            app_state.remote_sessions.pop(session_id, None)
    app_state.activity_service.publish(
        user_id=context.user.user_id,
        level='warning',
        category='site',
        action='deleted',
        title='Sites deleted',
        message=f'{len(deleted_names)} site(s); closed {len(expired_sessions)} related session(s).',
    )
    return SiteBulkDeleteResponse(deleted=deleted_names, closed_sessions=len(expired_sessions))
