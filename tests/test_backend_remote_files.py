"""Tests for remote file system APIs."""
from pathlib import Path
import shutil
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from backend.app.api.deps import X_SSHFERRY_TOKEN
from backend.app.main import create_app
from backend.app.services.app_state import AppState
from backend.app.services.remote_file_service import RemoteFileService
from src.services.site_store import SiteStore
from src.shared.models import SiteConfig


def _build_test_client(store_path: Path, session_site: SiteConfig | None = None) -> TestClient:
    state = AppState(site_store=SiteStore(path=store_path))
    if session_site is not None:
        with state.session_lock:
            state.remote_sessions['session-1'] = session_site
    app = create_app(app_state_factory=lambda: state)
    client = TestClient(app)
    client.headers.update({X_SSHFERRY_TOKEN: state.auth_token})
    return client


def _run_in_temp_store(test_name: str, runner):
    base_dir = Path('.tmp_test_remote_files') / test_name
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    store_path = base_dir / 'sites.json'
    try:
        runner(store_path)
    finally:
        if base_dir.exists():
            shutil.rmtree(base_dir)


@pytest.fixture
def remote_site() -> SiteConfig:
    return SiteConfig(
        name='demo',
        host='example.com',
        port=22,
        username='alice',
        auth_method='password',
        password='secret',
        remote_root='/remote',
    )


def test_remote_list_defaults_to_session_remote_root(monkeypatch, remote_site):
    class FakeEngine:
        def connect(self):
            return None

        def disconnect(self):
            return None

        def list_dir(self, path):
            assert path == '/remote'
            return [
                SimpleNamespace(name='docs', path='/remote/docs', is_dir=True, size=0, mtime=1.0, mode=None),
                SimpleNamespace(name='a.txt', path='/remote/a.txt', is_dir=False, size=3, mtime=2.0, mode=None),
            ]

    monkeypatch.setattr(RemoteFileService, '_build_engine', staticmethod(lambda _site: FakeEngine()))

    def runner(store_path: Path):
        with _build_test_client(store_path, remote_site) as client:
            response = client.get('/api/remote-files/list', params={'session_id': 'session-1'})

        assert response.status_code == 200
        body = response.json()
        assert body['current_path'] == '/remote'
        assert body['total'] == 2
        assert body['items'][0]['name'] == 'docs'
        assert body['items'][0]['is_dir'] is True

    _run_in_temp_store('list', runner)


def test_remote_stat_returns_entry(monkeypatch, remote_site):
    class FakeEngine:
        def connect(self):
            return None

        def disconnect(self):
            return None

        def stat(self, path):
            assert path == '/remote/a.txt'
            return SimpleNamespace(name='a.txt', path=path, is_dir=False, size=7, mtime=3.0, mode=33188)

    monkeypatch.setattr(RemoteFileService, '_build_engine', staticmethod(lambda _site: FakeEngine()))

    def runner(store_path: Path):
        with _build_test_client(store_path, remote_site) as client:
            response = client.get('/api/remote-files/stat', params={'session_id': 'session-1', 'path': '/remote/a.txt'})

        assert response.status_code == 200
        body = response.json()
        assert body['entry']['name'] == 'a.txt'
        assert body['entry']['size'] == 7

    _run_in_temp_store('stat', runner)


def test_remote_mkdir_rename_and_delete_routes(monkeypatch, remote_site):
    calls: list[tuple[str, str, str | bool | None]] = []

    class FakeEngine:
        def connect(self):
            calls.append(('connect', '', None))

        def disconnect(self):
            calls.append(('disconnect', '', None))

        def mkdir(self, path):
            calls.append(('mkdir', path, None))

        def rename(self, old_path, new_path):
            calls.append(('rename', old_path, new_path))

        def stat(self, path):
            calls.append(('stat', path, None))
            return SimpleNamespace(name='docs', path=path, is_dir=True, size=0, mtime=0.0, mode=None)

        def remove_dir_recursive(self, path):
            calls.append(('remove_dir_recursive', path, None))

    monkeypatch.setattr(RemoteFileService, '_build_engine', staticmethod(lambda _site: FakeEngine()))

    def runner(store_path: Path):
        with _build_test_client(store_path, remote_site) as client:
            mkdir_resp = client.post('/api/remote-files/mkdir', json={'session_id': 'session-1', 'path': '/remote/docs'})
            rename_resp = client.post('/api/remote-files/rename', json={'session_id': 'session-1', 'old_path': '/remote/docs', 'new_path': '/remote/docs2'})
            delete_resp = client.post('/api/remote-files/delete', json={'session_id': 'session-1', 'path': '/remote/docs', 'recursive': True})

        assert mkdir_resp.status_code == 204
        assert rename_resp.status_code == 204
        assert delete_resp.status_code == 204
        assert ('mkdir', '/remote/docs', None) in calls
        assert ('rename', '/remote/docs', '/remote/docs2') in calls
        assert ('remove_dir_recursive', '/remote/docs', None) in calls

    _run_in_temp_store('mutations', runner)


def test_remote_bulk_delete_route_deletes_files_and_folders_in_one_engine(monkeypatch, remote_site):
    calls: list[tuple[str, str | None]] = []

    class FakeEngine:
        def connect(self):
            calls.append(('connect', None))

        def disconnect(self):
            calls.append(('disconnect', None))

        def stat(self, path):
            calls.append(('stat', path))
            return SimpleNamespace(
                name=path.rsplit('/', 1)[-1],
                path=path,
                is_dir=path.endswith('/docs'),
                size=0,
                mtime=0.0,
                mode=None,
            )

        def remove_dir_recursive(self, path):
            calls.append(('remove_dir_recursive', path))

        def remove_file(self, path):
            calls.append(('remove_file', path))

    monkeypatch.setattr(RemoteFileService, '_build_engine', staticmethod(lambda _site: FakeEngine()))

    def runner(store_path: Path):
        with _build_test_client(store_path, remote_site) as client:
            response = client.post(
                '/api/remote-files/bulk-delete',
                json={'session_id': 'session-1', 'paths': ['/remote/a.txt', '/remote/docs'], 'recursive': True},
            )

        assert response.status_code == 200
        assert response.json() == {'deleted_paths': ['/remote/a.txt', '/remote/docs'], 'total': 2}
        assert calls.count(('connect', None)) == 1
        assert calls.count(('disconnect', None)) == 1
        assert ('remove_file', '/remote/a.txt') in calls
        assert ('remove_dir_recursive', '/remote/docs') in calls

    _run_in_temp_store('bulk-delete', runner)


def test_remote_files_require_valid_session(remote_site):
    def runner(store_path: Path):
        with _build_test_client(store_path, remote_site) as client:
            response = client.get('/api/remote-files/list', params={'session_id': 'missing'})

        assert response.status_code == 404
        assert "Session 'missing' not found" in response.json()['detail']

    _run_in_temp_store('missing-session', runner)


def test_remote_files_reject_blank_remote_path(monkeypatch, remote_site):
    class FakeEngine:
        def connect(self):
            return None

        def disconnect(self):
            return None

    monkeypatch.setattr(RemoteFileService, '_build_engine', staticmethod(lambda _site: FakeEngine()))

    def runner(store_path: Path):
        with _build_test_client(store_path, remote_site) as client:
            response = client.post('/api/remote-files/mkdir', json={'session_id': 'session-1', 'path': '   '})

        assert response.status_code == 400
        assert response.json()['detail'] == 'Remote path must not be blank'

    _run_in_temp_store('blank-path', runner)
