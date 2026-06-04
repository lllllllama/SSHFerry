"""Tests for site configuration APIs."""
from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from backend.app.api.deps import X_SSHFERRY_TOKEN
from backend.app.main import create_app
from backend.app.services.app_state import AppState
from src.services.site_store import SiteStore


TEST_SITE_SECRET = 'backend-site-test-secret'


def _build_test_client(store_path: Path) -> TestClient:
    state = AppState(site_store=SiteStore(path=store_path, secret_key=TEST_SITE_SECRET))
    app = create_app(app_state_factory=lambda: state)
    client = TestClient(app)
    client.headers.update({X_SSHFERRY_TOKEN: state.auth_token})
    return client


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
        assert body['has_key_passphrase'] is False
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


def test_update_site_keeps_saved_password_when_left_blank():
    initial = {
        'name': 'demo',
        'host': 'example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'password',
        'remote_root': '/work',
        'password': 'top-secret',
        'remember_password': True,
        'default_transfer_protocol': 'sftp',
    }
    updated = {
        'name': 'demo',
        'host': 'prod.example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'password',
        'remote_root': '/work',
        'remember_password': True,
        'default_transfer_protocol': 'sftp',
    }

    def runner(store_path: Path):
        store = SiteStore(path=store_path, secret_key=TEST_SITE_SECRET)
        with _build_test_client(store_path) as client:
            create_response = client.post('/api/sites', json=initial)
            update_response = client.put('/api/sites/demo', json=updated)

        loaded = store.load_or_raise()
        assert create_response.status_code == 201
        assert update_response.status_code == 200
        assert update_response.json()['has_password'] is True
        assert loaded[0].password == 'top-secret'
        assert loaded[0].host == 'prod.example.com'

    _run_in_temp_store('keep_password', runner)


def test_update_key_site_keeps_saved_key_passphrase_when_left_blank():
    initial = {
        'name': 'gpu',
        'host': 'example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'key',
        'remote_root': '/work',
        'key_path': 'C:/keys/id_ed25519',
        'key_passphrase': 'phrase-secret',
        'default_transfer_protocol': 'sftp',
    }
    updated = {
        'name': 'gpu',
        'host': 'gpu.example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'key',
        'remote_root': '/work',
        'key_path': 'C:/keys/id_ed25519',
        'default_transfer_protocol': 'sftp',
    }

    def runner(store_path: Path):
        store = SiteStore(path=store_path, secret_key=TEST_SITE_SECRET)
        with _build_test_client(store_path) as client:
            create_response = client.post('/api/sites', json=initial)
            update_response = client.put('/api/sites/gpu', json=updated)

        loaded = store.load_or_raise()
        assert create_response.status_code == 201
        assert update_response.status_code == 200
        assert update_response.json()['has_key_passphrase'] is True
        assert loaded[0].key_passphrase == 'phrase-secret'
        assert loaded[0].host == 'gpu.example.com'

    _run_in_temp_store('keep_key_passphrase', runner)


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


def test_bulk_delete_sites_removes_selected_configs_only():
    def payload(name: str) -> dict[str, object]:
        return {
            'name': name,
            'host': f'{name}.example.com',
            'port': 22,
            'username': 'alice',
            'auth_method': 'password',
            'remote_root': '/work',
            'default_transfer_protocol': 'sftp',
        }

    def runner(store_path: Path):
        with _build_test_client(store_path) as client:
            for name in ['alpha', 'beta', 'gamma']:
                create_response = client.post('/api/sites', json=payload(name))
                assert create_response.status_code == 201

            delete_response = client.post('/api/sites/bulk-delete', json={'names': ['alpha', 'gamma']})
            listed = client.get('/api/sites')

        assert delete_response.status_code == 200
        assert delete_response.json() == {'deleted': ['alpha', 'gamma'], 'closed_sessions': 0}
        assert [item['name'] for item in listed.json()['items']] == ['beta']

    _run_in_temp_store('bulk_delete', runner)


def test_bulk_delete_sites_is_all_or_nothing_when_name_is_missing():
    def payload(name: str) -> dict[str, object]:
        return {
            'name': name,
            'host': f'{name}.example.com',
            'port': 22,
            'username': 'alice',
            'auth_method': 'password',
            'remote_root': '/work',
            'default_transfer_protocol': 'sftp',
        }

    def runner(store_path: Path):
        with _build_test_client(store_path) as client:
            create_response = client.post('/api/sites', json=payload('alpha'))
            delete_response = client.post('/api/sites/bulk-delete', json={'names': ['alpha', 'missing']})
            listed = client.get('/api/sites')

        assert create_response.status_code == 201
        assert delete_response.status_code == 404
        assert [item['name'] for item in listed.json()['items']] == ['alpha']

    _run_in_temp_store('bulk_delete_missing', runner)
