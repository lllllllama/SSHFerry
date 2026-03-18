"""Log routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from backend.app.api.deps import get_app_state
from backend.app.schemas.logs import LogEntryResponse, LogListResponse
from backend.app.services.app_state import AppState
from backend.app.services.log_service import LogSnapshot


DEFAULT_LOG_LIMIT = 400
MAX_LOG_LIMIT = 2000
router = APIRouter(prefix='/logs', tags=['logs'])


def _to_response(snapshot: LogSnapshot) -> LogListResponse:
    return LogListResponse(
        items=[
            LogEntryResponse(
                sequence=item.sequence,
                timestamp=item.timestamp,
                level=item.level,
                logger=item.logger,
                message=item.message,
                rendered=item.rendered,
            )
            for item in snapshot.items
        ],
        total=snapshot.total,
        sequence=snapshot.sequence,
    )


@router.get('', response_model=LogListResponse)
def list_logs(
    limit: int = Query(default=DEFAULT_LOG_LIMIT, ge=1, le=MAX_LOG_LIMIT),
    app_state: AppState = Depends(get_app_state),
) -> LogListResponse:
    return _to_response(app_state.log_service.snapshot(limit=limit))


@router.delete('', status_code=status.HTTP_204_NO_CONTENT)
def clear_logs(app_state: AppState = Depends(get_app_state)) -> Response:
    app_state.log_service.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)