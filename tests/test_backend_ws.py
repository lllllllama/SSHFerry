"""Tests for realtime task websocket APIs."""
from dataclasses import replace
import secrets
from threading import Lock

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.main import create_app
from src.shared.models import Task


class FakeScheduler:
    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.task_lock = Lock()
        self.parallel_threshold = 50 * 1024 * 1024
        self.running = True

    def get_all_tasks(self) -> list[Task]:
        with self.task_lock:
            return [replace(task) for task in self.tasks.values()]


class FakeAppState:
    def __init__(self, scheduler: FakeScheduler | None = None):
        self.scheduler = scheduler
        self.remote_sessions = {}
        self.session_lock = Lock()
        self.auth_token = secrets.token_urlsafe(16)
        self.startup_error = None
        self.site_store = None

    def start(self):
        return None

    def stop(self):
        return None

    @property
    def is_ready(self) -> bool:
        return self.scheduler is not None and getattr(self.scheduler, 'running', False)

    @property
    def session_count(self) -> int:
        return 0

    def require_scheduler(self):
        if self.scheduler is None:
            raise RuntimeError('Task scheduler unavailable')
        return self.scheduler


def _build_test_client(state: FakeAppState) -> TestClient:
    app = create_app(app_state_factory=lambda: state)
    return TestClient(app)


def test_tasks_websocket_streams_initial_snapshot():
    scheduler = FakeScheduler()
    scheduler.tasks['task-1'] = Task(
        task_id='task-1',
        kind='file_transfer',
        engine='sftp',
        src='a',
        dst='b',
        bytes_total=10,
        status='pending',
    )
    state = FakeAppState(scheduler=scheduler)

    with _build_test_client(state) as client:
        with client.websocket_connect(f'/api/ws/tasks?token={state.auth_token}') as websocket:
            message = websocket.receive_json()

    assert message['type'] == 'task_snapshot'
    assert message['total'] == 1
    assert message['items'][0]['task_id'] == 'task-1'
    assert message['items'][0]['status'] == 'pending'


def test_tasks_websocket_pushes_update_when_snapshot_changes():
    scheduler = FakeScheduler()
    state = FakeAppState(scheduler=scheduler)

    with _build_test_client(state) as client:
        with client.websocket_connect(f'/api/ws/tasks?token={state.auth_token}') as websocket:
            initial = websocket.receive_json()
            with scheduler.task_lock:
                scheduler.tasks['task-2'] = Task(
                    task_id='task-2',
                    kind='file_transfer',
                    engine='scp',
                    src='x',
                    dst='y',
                    bytes_total=20,
                    status='running',
                )
            updated = websocket.receive_json()

    assert initial == {'type': 'task_snapshot', 'items': [], 'total': 0}
    assert updated['type'] == 'task_snapshot'
    assert updated['total'] == 1
    assert updated['items'][0]['task_id'] == 'task-2'
    assert updated['items'][0]['status'] == 'running'


def test_tasks_websocket_rejects_invalid_token():
    state = FakeAppState(scheduler=FakeScheduler())

    with _build_test_client(state) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect('/api/ws/tasks?token=invalid-token'):
                pass

    assert exc_info.value.code == 1008


def test_tasks_websocket_reports_scheduler_error_message():
    state = FakeAppState(scheduler=None)

    with _build_test_client(state) as client:
        with client.websocket_connect(f'/api/ws/tasks?token={state.auth_token}') as websocket:
            message = websocket.receive_json()

    assert message['type'] == 'error'
    assert 'Task scheduler unavailable' in message['detail']
