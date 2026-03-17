"""Tests for connection checks and remote session APIs."""
from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.app_state import AppState
from backend.app.services.connection_service import ConnectionService
from src.services.site_store import SiteStore
from src.shared.models import SiteConfig


class _FakeCheckResponse:
    def __init__(self, *, site_name: str, all_passed: bool):
        self.site_name = site_name
        self.all_passed = all_passed
        self.results = [
            {
                'name': 'TCP Connection',
                'passed': all_passed,
                'message': 'ok' if all_passed else 'failed',
            }
        ]


def _build_test_client(store_path: Path) -> TestClient:
    def factory() -> AppState:
        return AppState(site_store=SiteStore(path=store_path))

    app = create_app(app_state_factory=factory)
    return TestClient(app)


def _run_in_temp_store(test_name: str, runner):
    base_dir = Path('.tmp_test_connections') / test_name
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    store_path = base_dir / 'sites.json'
    try:
        runner(store_path)
    finally:
        if base_dir.exists():
            shutil.rmtree(base_dir)


def _seed_site(store_path: Path, site: SiteConfig) -> None:
    SiteStore(path=store_path).save([site])


def test_session_open_list_and_close_flow():
    def runner(store_path: Path):
        _seed_site(
            store_path,
            SiteConfig(
                name='demo',
                host='example.com',
                port=22,
                username='alice',
                auth_method='password',
                password='secret',
                remote_root='/work',
            ),
        )

        with _build_test_client(store_path) as client:
            opened = client.post('/api/sessions/open', json={'site_name': 'demo', 'password': 'secret'})
            listed = client.get('/api/sessions')
            session_id = opened.json()['session_id']
            closed = client.post('/api/sessions/close', json={'session_id': session_id})
            listed_after = client.get('/api/sessions')

        assert opened.status_code == 201
        assert listed.status_code == 200
        assert listed.json()['total'] == 1
        assert closed.status_code == 204
        assert listed_after.json() == {'items': [], 'total': 0}

    _run_in_temp_store('session_flow', runner)


def test_session_open_requires_runtime_password_when_not_persisted():
    def runner(store_path: Path):
        _seed_site(
            store_path,
            SiteConfig(
                name='demo',
                host='example.com',
                port=22,
                username='alice',
                auth_method='password',
                remote_root='/work',
            ),
        )

        with _build_test_client(store_path) as client:
            missing = client.post('/api/sessions/open', json={'site_name': 'demo'})
            provided = client.post('/api/sessions/open', json={'site_name': 'demo', 'password': 'secret'})

        assert missing.status_code == 400
        assert provided.status_code == 201
        assert provided.json()['has_password'] is True

    _run_in_temp_store('password_required', runner)


def test_connection_check_route_uses_service_result(monkeypatch):
    def fake_run_check(self, payload):
        return {
            'site_name': payload.site_name,
            'all_passed': True,
            'results': [
                {
                    'name': 'TCP Connection',
                    'passed': True,
                    'message': 'ok',
                }
            ],
        }

    monkeypatch.setattr(ConnectionService, 'run_check', fake_run_check)

    def runner(store_path: Path):
        _seed_site(
            store_path,
            SiteConfig(
                name='demo',
                host='example.com',
                port=22,
                username='alice',
                auth_method='password',
                password='secret',
                remote_root='/work',
            ),
        )

        with _build_test_client(store_path) as client:
            response = client.post('/api/connections/check', json={'site_name': 'demo'})

        assert response.status_code == 200
        body = response.json()
        assert body['site_name'] == 'demo'
        assert body['all_passed'] is True
        assert body['results'][0]['name'] == 'TCP Connection'

    _run_in_temp_store('check', runner)

