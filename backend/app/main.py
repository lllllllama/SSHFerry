"""FastAPI backend entry point for the local SSHFerry service."""
from __future__ import annotations

from contextlib import asynccontextmanager
import os

import uvicorn
from fastapi import FastAPI

from backend.app.api.routes import api_router
from backend.app.services.app_state import AppState
from src import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up shared backend state."""
    app_state = AppState()
    app_state.start()
    app.state.app_state = app_state
    try:
        yield
    finally:
        app_state.stop()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="SSHFerry Backend",
        version=__version__,
        lifespan=lifespan,
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
