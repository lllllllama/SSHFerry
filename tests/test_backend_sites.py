"""Tests for site configuration APIs."""
from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.app_state import AppState
from src.services.site_store import SiteStore


def _build_test_client(store_path: Path) -> TestClient:
    def factory() -> AppState:
        return AppState(site_store=SiteStore(path=store_path))

    app = create_app(app_state_factory=factory)
    return TestClient(app)


def _run_in_temp_store(test_name: str, runner):
    base_dir = Path('.tmp_test_sites') / test_name
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    store_path = base_dir / 'sites.json'
    try:
        runner(store_path)
    finally:
        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_sites_list_is_empty_by_default():
    def runner(store_path: Path):
        with _build_test_client(store_path) as client:
            response = client.get('/api/sites')

        assert response.status_code == 200
        assert response.json() == {'items': [], 'total': 0}

    _run_in_temp_store('empty', runner)


def test_create_site_returns_sanitized_payload():
    payload = {
        'name': 'demo',
        'host': 'example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'password',
        'remote_root': '/work',
        'password': 'top-secret',
        'remember_password': False,
        'default_transfer_protocol': 'sftp',
    }

    def runner(store_path: Path):
        with _build_test_client(store_path) as client:
            response = client.post('/api/sites', json=payload)
            listed = client.get('/api/sites')

        assert response.status_code == 201
        body = response.json()
        assert body['name'] == 'demo'
        assert body['has_password'] is False
        assert 'password' not in body
        assert listed.json()['total'] == 1

    _run_in_temp_store('create', runner)


def test_create_site_rejects_duplicate_name():
    payload = {
        'name': 'demo',
        'host': 'example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'password',
        'remote_root': '/work',
        'default_transfer_protocol': 'sftp',
    }

    def runner(store_path: Path):
        with _build_test_client(store_path) as client:
            first = client.post('/api/sites', json=payload)
            second = client.post('/api/sites', json=payload)

        assert first.status_code == 201
        assert second.status_code == 409

    _run_in_temp_store('duplicate', runner)


def test_update_site_can_rename_and_change_protocol():
    initial = {
        'name': 'demo',
        'host': 'example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'password',
        'remote_root': '/work',
        'default_transfer_protocol': 'sftp',
    }
    updated = {
        'name': 'demo-prod',
        'host': 'prod.example.com',
        'port': 2222,
        'username': 'alice',
        'auth_method': 'key',
        'remote_root': '/srv/app',
        'key_path': 'C:/keys/id_rsa',
        'default_transfer_protocol': 'scp',
    }

    def runner(store_path: Path):
        with _build_test_client(store_path) as client:
            create_response = client.post('/api/sites', json=initial)
            update_response = client.put('/api/sites/demo', json=updated)
            listed = client.get('/api/sites')

        assert create_response.status_code == 201
        assert update_response.status_code == 200
        body = update_response.json()
        assert body['name'] == 'demo-prod'
        assert body['host'] == 'prod.example.com'
        assert body['default_transfer_protocol'] == 'scp'
        assert listed.json()['items'][0]['name'] == 'demo-prod'

    _run_in_temp_store('update', runner)


def test_delete_site_removes_persisted_config():
    payload = {
        'name': 'demo',
        'host': 'example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'password',
        'remote_root': '/work',
        'default_transfer_protocol': 'sftp',
    }

    def runner(store_path: Path):
        with _build_test_client(store_path) as client:
            create_response = client.post('/api/sites', json=payload)
            delete_response = client.delete('/api/sites/demo')
            listed = client.get('/api/sites')

        assert create_response.status_code == 201
        assert delete_response.status_code == 204
        assert listed.json() == {'items': [], 'total': 0}

    _run_in_temp_store('delete', runner)
