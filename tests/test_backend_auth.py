"""Tests for local auth bootstrap and CORS behavior."""
from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from backend.app.api.deps import X_SSHFERRY_TOKEN
from backend.app.main import create_app
from backend.app.services.app_state import AppState
from src.services.site_store import SiteStore


ALLOWED_ORIGIN = 'http://localhost:5173'


def _build_state(store_path: Path) -> AppState:
    return AppState(site_store=SiteStore(path=store_path))


def _run_in_temp_store(test_name: str, runner):
    base_dir = Path('.tmp_test_backend_auth') / test_name
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    store_path = base_dir / 'sites.json'
    try:
        runner(store_path)
    finally:
        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_auth_session_returns_token_and_header_name():
    def runner(store_path: Path):
        state = _build_state(store_path)
        app = create_app(app_state_factory=lambda: state)

        with TestClient(app) as client:
            response = client.get('/api/auth/session')

        assert response.status_code == 200
        body = response.json()
        assert body['token'] == state.auth_token
        assert body['header_name'] == X_SSHFERRY_TOKEN
        assert body['token_type'] == 'local'

    _run_in_temp_store('auth-session', runner)


def test_protected_route_requires_token_header():
    def runner(store_path: Path):
        state = _build_state(store_path)
        app = create_app(app_state_factory=lambda: state)

        with TestClient(app) as client:
            missing = client.get('/api/sites')
            client.headers.update({X_SSHFERRY_TOKEN: state.auth_token})
            allowed = client.get('/api/sites')

        assert missing.status_code == 401
        assert allowed.status_code == 200

    _run_in_temp_store('token-required', runner)


def test_cors_preflight_allows_local_dev_origin():
    def runner(store_path: Path):
        state = _build_state(store_path)
        app = create_app(app_state_factory=lambda: state)

        with TestClient(app) as client:
            response = client.options(
                '/api/sites',
                headers={
                    'Origin': ALLOWED_ORIGIN,
                    'Access-Control-Request-Method': 'GET',
                    'Access-Control-Request-Headers': X_SSHFERRY_TOKEN,
                },
            )

        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == ALLOWED_ORIGIN

    _run_in_temp_store('cors-allowed', runner)


def test_cors_preflight_blocks_unknown_origin():
    def runner(store_path: Path):
        state = _build_state(store_path)
        app = create_app(app_state_factory=lambda: state)

        with TestClient(app) as client:
            response = client.options(
                '/api/sites',
                headers={
                    'Origin': 'https://evil.example.com',
                    'Access-Control-Request-Method': 'GET',
                    'Access-Control-Request-Headers': X_SSHFERRY_TOKEN,
                },
            )

        assert response.status_code == 400
        assert 'access-control-allow-origin' not in response.headers

    _run_in_temp_store('cors-blocked', runner)
