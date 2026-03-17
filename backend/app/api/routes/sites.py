"""Site configuration routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from backend.app.api.deps import get_app_state
from backend.app.schemas.sites import SiteListResponse, SiteResponse, SiteUpsertRequest
from backend.app.services.app_state import AppState
from backend.app.services.site_service import SiteService


router = APIRouter(prefix='/sites', tags=['sites'])


@router.get('', response_model=SiteListResponse)
def list_sites(app_state: AppState = Depends(get_app_state)) -> SiteListResponse:
    service = SiteService(app_state.site_store)
    items = [service.to_response(site) for site in service.list_sites()]
    return SiteListResponse(items=items, total=len(items))


@router.post('', response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(payload: SiteUpsertRequest, app_state: AppState = Depends(get_app_state)) -> SiteResponse:
    service = SiteService(app_state.site_store)
    site = service.create_site(payload)
    return service.to_response(site)


@router.put('/{site_name}', response_model=SiteResponse)
def update_site(site_name: str, payload: SiteUpsertRequest, app_state: AppState = Depends(get_app_state)) -> SiteResponse:
    service = SiteService(app_state.site_store)
    site = service.update_site(site_name, payload)
    return service.to_response(site)


@router.delete('/{site_name}', status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_name: str, app_state: AppState = Depends(get_app_state)) -> Response:
    service = SiteService(app_state.site_store)
    service.delete_site(site_name)
    with app_state.session_lock:
        expired_sessions = [sid for sid, site in app_state.remote_sessions.items() if site.name == site_name]
        for session_id in expired_sessions:
            app_state.remote_sessions.pop(session_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
