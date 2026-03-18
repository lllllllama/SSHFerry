"""Route registration for the backend API."""
from fastapi import APIRouter, Depends

from backend.app.api.deps import require_local_token
from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.connections import router as connections_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.local_files import router as local_files_router
from backend.app.api.routes.logs import router as logs_router
from backend.app.api.routes.remote_files import router as remote_files_router
from backend.app.api.routes.sites import router as sites_router
from backend.app.api.routes.tasks import router as tasks_router
from backend.app.api.routes.ws import router as ws_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(ws_router)

protected_router = APIRouter(dependencies=[Depends(require_local_token)])
protected_router.include_router(sites_router)
protected_router.include_router(connections_router)
protected_router.include_router(local_files_router)
protected_router.include_router(remote_files_router)
protected_router.include_router(tasks_router)
protected_router.include_router(logs_router)

api_router.include_router(protected_router)