"""Route registration for the backend API."""
from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router


api_router = APIRouter()
api_router.include_router(health_router)
