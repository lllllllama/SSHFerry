"""Tests for task creation and control APIs."""
from dataclasses import replace
from pathlib import Path
import secrets
import shutil
from threading import Lock
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.api.deps import X_SSHFERRY_TOKEN
from backend.app.main import create_app
from backend.app.services.task_service import TaskService
from src.shared.models import SiteConfig, Task


class FakeScheduler:
    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.task_lock = Lock()
        self.task_queue: list[str] = []
        self.queued_task_ids: set[str] = set()
        self.active_task_ids: set[str] = set()
        self.futures: dict[str, object] = {}
        self.parallel_threshold = 50 * 1024 * 1024

    def add_task(self, task: Task) -> str:
        with self.task_lock:
            self.tasks[task.task_id] = task
            self.task_queue.append(task.task_id)
            self.queued_task_ids.add(task.task_id)
        return task.task_id

    def get_task(self, task_id: str) -> Task | None:
        with self.task_lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
        with self.task_lock:
            return [replace(task) for task in self.tasks.values()]

    def pause_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if task is None or task.status != 'running':
                return False
            task.paused = True
            return True

    def resume_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if task is None or task.status != 'paused':
                return False
            task.status = 'pending'
            task.paused = False
            return True

    def cancel_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if task is None or task.status not in ('pending', 'running', 'paused'):
                return False
            task.status = 'canceled'
            return True

    def restart_task(self, task_id: str) -> bool:
        with self.task_lock:
            task = self.tasks.get(task_id)
            if task is None or task.status not in ('failed', 'canceled', 'done', 'skipped'):
                return False
            task.status = 'pending'
            task.bytes_done = 0
            task.error_message = None
            task.error_code = None
            task.subtask_done = 0
            task.current_file = ''
            return True


class FakeAppState:
    def __init__(self, scheduler: FakeScheduler | None = None, remote_sessions: dict[str, SiteConfig] | None = None):
        self.scheduler = scheduler or FakeScheduler()
        self.remote_sessions = remote_sessions or {}
        self.session_lock = Lock()
        self.auth_token = secrets.token_urlsafe(16)
        self.startup_error = None
        self.site_store = None

    def start(self):
        return None

    def stop(self):
        return None

    def require_scheduler(self):
        if self.scheduler is None:
            raise RuntimeError('Task scheduler unavailable')
        return self.scheduler


REMOTE_SITE = SiteConfig(
    name='demo',
    host='example.com',
    port=22,
    username='alice',
    auth_method='password',
    password='secret',
    remote_root='/remote',
    default_transfer_protocol='scp',
)

REMOTE_SITE_B = SiteConfig(
    name='backup',
    host='backup.example.com',
    port=22,
    username='bob',
    auth_method='password',
    password='secret',
    remote_root='/backup',
)


def _build_test_client(state: FakeAppState) -> TestClient:
    app = create_app(app_state_factory=lambda: state)
    client = TestClient(app)
    client.headers.update({X_SSHFERRY_TOKEN: state.auth_token})
    return client


def _run_in_temp_fs(test_name: str, runner):
    base_dir = Path('.tmp_test_backend_tasks') / test_name
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    try:
        runner(base_dir)
    finally:
        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_upload_task_endpoint_creates_file_transfer_with_auto_engine():
    def runner(base_dir: Path):
        local_file = base_dir / 'data.bin'
        local_file.write_bytes(b'hello world')
        state = FakeAppState(remote_sessions={'session-1': REMOTE_SITE})

        with _build_test_client(state) as client:
            response = client.post(
                '/api/tasks/upload',
                json={
                    'session_id': 'session-1',
                    'local_path': str(local_file),
                    'remote_path': '/remote/data.bin',
                    'engine': 'auto',
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body['kind'] == 'file_transfer'
        assert body['engine'] == 'scp'
        assert body['src'].endswith('data.bin')
        assert body['dst'] == '/remote/data.bin'
        assert body['dst_session_id'] == 'session-1'
        assert body['bytes_total'] == 11
        assert body['status'] == 'pending'

    _run_in_temp_fs('upload_file', runner)


def test_download_task_endpoint_creates_folder_transfer(monkeypatch):
    class FakeEngine:
        def connect(self):
            return None

        def disconnect(self):
            return None

        def stat(self, path):
            assert path == '/remote/docs'
            return SimpleNamespace(name='docs', path=path, is_dir=True, size=0, mtime=1.0, mode=None)

        def list_dir(self, path):
            if path == '/remote/docs':
                return [
                    SimpleNamespace(name='a.txt', path='/remote/docs/a.txt', is_dir=False, size=3, mtime=1.0, mode=None),
                    SimpleNamespace(name='sub', path='/remote/docs/sub', is_dir=True, size=0, mtime=1.0, mode=None),
                ]
            if path == '/remote/docs/sub':
                return [SimpleNamespace(name='b.txt', path='/remote/docs/sub/b.txt', is_dir=False, size=4, mtime=1.0, mode=None)]
            return []

    monkeypatch.setattr(TaskService, '_build_remote_engine', staticmethod(lambda _site: FakeEngine()))

    def runner(base_dir: Path):
        target_dir = base_dir / 'downloads' / 'docs'
        state = FakeAppState(remote_sessions={'session-1': REMOTE_SITE})

        with _build_test_client(state) as client:
            response = client.post(
                '/api/tasks/download',
                json={
                    'session_id': 'session-1',
                    'remote_path': '/remote/docs',
                    'local_path': str(target_dir),
                    'engine': 'auto',
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body['kind'] == 'folder_transfer'
        assert body['engine'] == 'sftp'
        assert body['subtask_count'] == 2
        assert body['bytes_total'] == 7
        assert body['src_endpoint_type'] == 'remote'
        assert body['dst_endpoint_type'] == 'local'

    _run_in_temp_fs('download_folder', runner)


def test_remote_copy_endpoint_creates_remote_to_remote_task(monkeypatch):
    class FakeEngine:
        def connect(self):
            return None

        def disconnect(self):
            return None

        def stat(self, path):
            assert path == '/remote/a.txt'
            return SimpleNamespace(name='a.txt', path=path, is_dir=False, size=9, mtime=1.0, mode=None)

    monkeypatch.setattr(TaskService, '_build_remote_engine', staticmethod(lambda _site: FakeEngine()))
    state = FakeAppState(remote_sessions={'src-1': REMOTE_SITE, 'dst-1': REMOTE_SITE_B})

    with _build_test_client(state) as client:
        response = client.post(
            '/api/tasks/remote-copy',
            json={
                'src_session_id': 'src-1',
                'dst_session_id': 'dst-1',
                'src_path': '/remote/a.txt',
                'dst_path': '/backup/a.txt',
                'engine': 'auto',
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body['kind'] == 'file_transfer'
    assert body['src_session_id'] == 'src-1'
    assert body['dst_session_id'] == 'dst-1'
    assert body['src_display_name'] == 'demo'
    assert body['dst_display_name'] == 'backup'
    assert body['engine'] == 'sftp'
    assert body['bytes_total'] == 9


def test_task_control_and_clear_finished_routes():
    scheduler = FakeScheduler()
    running_task = Task(
        task_id='task-running',
        kind='file_transfer',
        engine='sftp',
        src='a',
        dst='b',
        bytes_total=10,
        status='running',
    )
    failed_task = Task(
        task_id='task-failed',
        kind='file_transfer',
        engine='sftp',
        src='c',
        dst='d',
        bytes_total=10,
        status='failed',
        error_message='boom',
    )
    done_task = Task(
        task_id='task-done',
        kind='file_transfer',
        engine='sftp',
        src='e',
        dst='f',
        bytes_total=10,
        status='done',
    )
    scheduler.tasks = {
        running_task.task_id: running_task,
        failed_task.task_id: failed_task,
        done_task.task_id: done_task,
    }
    state = FakeAppState(scheduler=scheduler, remote_sessions={'session-1': REMOTE_SITE})

    with _build_test_client(state) as client:
        listed = client.get('/api/tasks')
        paused = client.post('/api/tasks/task-running/pause')
        with scheduler.task_lock:
            scheduler.tasks['task-running'].status = 'paused'
        resumed = client.post('/api/tasks/task-running/resume')
        restarted = client.post('/api/tasks/task-failed/restart')
        canceled = client.post('/api/tasks/task-running/cancel')
        cleared = client.delete('/api/tasks/finished')
        listed_after = client.get('/api/tasks')

    assert listed.status_code == 200
    assert listed.json()['total'] == 3
    assert paused.status_code == 200
    assert paused.json() == {'task_id': 'task-running', 'action': 'pause', 'status': 'running'}
    assert resumed.status_code == 200
    assert resumed.json()['status'] == 'pending'
    assert restarted.status_code == 200
    assert restarted.json()['status'] == 'pending'
    assert canceled.status_code == 200
    assert canceled.json()['status'] == 'canceled'
    assert cleared.status_code == 204
    assert listed_after.status_code == 200
    assert listed_after.json()['total'] == 1
    remaining_ids = {item['task_id'] for item in listed_after.json()['items']}
    assert remaining_ids == {'task-failed'}


def test_task_routes_return_404_for_missing_task():
    state = FakeAppState(remote_sessions={'session-1': REMOTE_SITE})

    with _build_test_client(state) as client:
        response = client.post('/api/tasks/missing/restart')

    assert response.status_code == 404
    assert "Task 'missing' not found" in response.json()['detail']


def test_task_routes_reject_blank_remote_path():
    def runner(base_dir: Path):
        local_file = base_dir / 'data.bin'
        local_file.write_bytes(b'hello world')
        state = FakeAppState(remote_sessions={'session-1': REMOTE_SITE})

        with _build_test_client(state) as client:
            response = client.post(
                '/api/tasks/upload',
                json={
                    'session_id': 'session-1',
                    'local_path': str(local_file),
                    'remote_path': '   ',
                    'engine': 'auto',
                },
            )

        assert response.status_code == 400
        assert response.json()['detail'] == 'Remote path must not be blank'

    _run_in_temp_fs('blank-remote-path', runner)
