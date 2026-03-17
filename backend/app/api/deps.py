"""Shared API dependencies."""
from __future__ import annotations

from fastapi import Request

from backend.app.services.app_state import AppState


def get_app_state(request: Request) -> AppState:
    """Return the singleton app state stored on the FastAPI app."""
    return request.app.state.app_state
