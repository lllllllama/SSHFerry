"""Route registration for the backend API."""
from fastapi import APIRouter

from backend.app.api.routes.connections import router as connections_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.sites import router as sites_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(sites_router)
api_router.include_router(connections_router)
