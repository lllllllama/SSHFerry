"""Tests for local file system APIs."""
from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from backend.app.api.deps import X_SSHFERRY_TOKEN
from backend.app.main import create_app
from backend.app.services.app_state import AppState
from src.services.site_store import SiteStore


def _build_test_client(store_path: Path) -> TestClient:
    state = AppState(site_store=SiteStore(path=store_path))
    app = create_app(app_state_factory=lambda: state)
    client = TestClient(app)
    client.headers.update({X_SSHFERRY_TOKEN: state.auth_token})
    return client


def _run_in_temp_fs(test_name: str, runner):
    base_dir = Path('.tmp_test_local_files') / test_name
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    store_path = base_dir / 'sites.json'
    try:
        runner(base_dir, store_path)
    finally:
        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_local_drives_endpoint_returns_entries():
    def runner(_base_dir: Path, store_path: Path):
        with _build_test_client(store_path) as client:
            response = client.get('/api/local-files/drives')

        assert response.status_code == 200
        body = response.json()
        assert body['total'] >= 1
        assert body['items'][0]['path']
        assert body['items'][0]['label']

    _run_in_temp_fs('drives', runner)


def test_local_list_returns_directory_entries_sorted_dirs_first():
    def runner(base_dir: Path, store_path: Path):
        target_dir = base_dir / 'workspace'
        target_dir.mkdir()
        (target_dir / 'z-file.txt').write_text('hello', encoding='utf-8')
        (target_dir / 'a-dir').mkdir()

        with _build_test_client(store_path) as client:
            response = client.get('/api/local-files/list', params={'path': str(target_dir)})

        assert response.status_code == 200
        body = response.json()
        assert body['current_path'].endswith('workspace')
        assert body['total'] == 2
        assert body['items'][0]['name'] == 'a-dir'
        assert body['items'][0]['is_dir'] is True
        assert body['items'][1]['name'] == 'z-file.txt'
        assert body['items'][1]['is_dir'] is False
        assert body['items'][1]['size'] == 5

    _run_in_temp_fs('list', runner)


def test_local_stat_returns_file_metadata():
    def runner(base_dir: Path, store_path: Path):
        target_file = base_dir / 'data.bin'
        target_file.write_bytes(b'abc123')

        with _build_test_client(store_path) as client:
            response = client.get('/api/local-files/stat', params={'path': str(target_file)})

        assert response.status_code == 200
        body = response.json()
        assert body['entry']['name'] == 'data.bin'
        assert body['entry']['is_dir'] is False
        assert body['entry']['size'] == 6

    _run_in_temp_fs('stat', runner)


def test_local_list_returns_404_for_missing_path():
    def runner(base_dir: Path, store_path: Path):
        missing = base_dir / 'missing-dir'
        with _build_test_client(store_path) as client:
            response = client.get('/api/local-files/list', params={'path': str(missing)})

        assert response.status_code == 404
        assert 'Path not found' in response.json()['detail']

    _run_in_temp_fs('missing', runner)
