"""FastAPI backend entry point for the local SSHFerry service."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
import os

import uvicorn
from fastapi import FastAPI

from backend.app.api.routes import api_router
from backend.app.services.app_state import AppState
from src import __version__


@asynccontextmanager
async def lifespan_factory(app: FastAPI, app_state_factory: Callable[[], AppState]):
    """Initialize and clean up shared backend state."""
    app_state = app_state_factory()
    app_state.start()
    app.state.app_state = app_state
    try:
        yield
    finally:
        app_state.stop()


def create_app(app_state_factory: Callable[[], AppState] | None = None) -> FastAPI:
    """Create the FastAPI application."""
    factory = app_state_factory or AppState
    app = FastAPI(
        title="SSHFerry Backend",
        version=__version__,
        lifespan=lambda app_instance: lifespan_factory(app_instance, factory),
    )
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()


def run() -> None:
    """Run the local backend service."""
    host = os.getenv("SSHFERRY_BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("SSHFERRY_BACKEND_PORT", "18080"))
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
