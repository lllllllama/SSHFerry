from __future__ import annotations

import builtins
import io
import logging
from pathlib import Path
from threading import Lock
from types import ModuleType, SimpleNamespace

from fastapi import HTTPException, UploadFile
import pytest

from backend.app.schemas.connections import ConnectionCheckRequest, SessionOpenRequest
from backend.app.schemas.remote_files import RemoteEntryResponse
from backend.app.schemas.sites import SiteUpsertRequest
from backend.app.schemas.tasks import TaskCreateUploadRequest
from backend.app.services.connection_service import ConnectionService
from backend.app.services.local_file_service import LocalFileService
from backend.app.services.log_service import InMemoryLogHandler, LogService
from backend.app.services.remote_file_service import RemoteFileService
from backend.app.services.site_service import SiteService
from backend.app.services.task_service import TaskService
from backend.app.services.user_cleanup_service import UserCleanupService
from backend.app.services.workspace_service import WorkspaceService
from src.services.site_store import SiteStore
from src.shared.models import SiteConfig, Task


def _site(**overrides) -> SiteConfig:
    data = {
        'name': 'demo',
        'host': 'example.com',
        'port': 22,
        'username': 'alice',
        'auth_method': 'password',
        'password': 'secret',
        'remote_root': '/remote',
        'owner_user_id': 'user-a',
        'default_transfer_protocol': 'sftp',
    }
    data.update(overrides)
    return SiteConfig(**data)


def test_connection_service_covers_check_and_session_branches(monkeypatch, tmp_path: Path):
    store = SiteStore(path=tmp_path / 'sites.json')
    store.save([
        _site(name='password-site'),
        _site(name='key-site', auth_method='key', password=None, key_path='C:/keys/id_ed25519', key_passphrase='phrase'),
        _site(name='foreign-site', owner_user_id='user-b'),
    ])
    sessions = {}
    service = ConnectionService(store, sessions, 'user-a')

    class FakeChecker:
        def __init__(self, runtime_site):
            self.runtime_site = runtime_site

        def run_all_checks(self):
            return [SimpleNamespace(name='TCP', passed=True, message='ok')]

    fake_module = ModuleType('src.services.connection_checker')
    fake_module.ConnectionChecker = FakeChecker
    monkeypatch.setitem(__import__('sys').modules, 'src.services.connection_checker', fake_module)

    result = service.run_check(ConnectionCheckRequest(site_name='password-site', password='secret'))
    assert result.all_passed is True
    assert result.results[0].name == 'TCP'

    opened = service.open_session(SessionOpenRequest(site_name='key-site', key_passphrase='phrase'))
    assert opened.site_name == 'key-site'
    assert service.list_sessions()[0].session_id == opened.session_id

    with pytest.raises(HTTPException, match="Session 'missing' not found"):
        service.close_session('missing')

    foreign_session_id = 'foreign'
    sessions[foreign_session_id] = _site(name='foreign', owner_user_id='user-b')
    with pytest.raises(HTTPException, match="Session 'foreign' not found"):
        service.close_session(foreign_session_id)

    service.close_session(opened.session_id)
    assert service.list_sessions() == []


def test_connection_service_covers_runtime_site_errors(tmp_path: Path):
    store = SiteStore(path=tmp_path / 'sites.json')
    store.save([
        _site(name='password-site', password=None),
        _site(name='key-site', auth_method='key', password=None, key_path=None),
    ])
    service = ConnectionService(store, {}, 'user-a')

    with pytest.raises(HTTPException, match="requires a password"):
        service._resolve_runtime_site('password-site')

    with pytest.raises(HTTPException, match="requires a key_path"):
        service._resolve_runtime_site('key-site')

    with pytest.raises(HTTPException, match="Site 'missing' not found"):
        service._load_site('missing')

    broken_store = SimpleNamespace(load_or_raise=lambda: (_ for _ in ()).throw(RuntimeError('store-bad')))
    broken_service = ConnectionService(broken_store, {}, 'user-a')
    with pytest.raises(HTTPException, match='store-bad'):
        broken_service._load_site('anything')


def test_workspace_service_covers_validation_and_file_branches(monkeypatch, tmp_path: Path):
    service = WorkspaceService(tmp_path / 'workspace')

    with pytest.raises(HTTPException, match='At least one file is required'):
        service.save_uploads('user-a', [])

    with pytest.raises(HTTPException, match='At least one workspace path is required'):
        service.delete_paths('user-a', [])

    file_root = service._user_root_path('user-a')
    file_root.parent.mkdir(parents=True, exist_ok=True)
    file_root.write_text('standalone', encoding='utf-8')
    assert service.clear_user_root('user-a') == (1, 0, len('standalone'))
    assert file_root.is_dir()

    user_root = service._ensure_user_root('user-b')
    (user_root / 'existing.txt').write_text('hello', encoding='utf-8')
    upload = UploadFile(filename='existing.txt', file=io.BytesIO(b'hello'))
    with pytest.raises(HTTPException, match='Workspace path already exists'):
        service.save_uploads('user-b', [upload])

    upload_a = UploadFile(filename='a.txt', file=io.BytesIO(b'a'))
    upload_b = UploadFile(filename='b.txt', file=io.BytesIO(b'b'))
    with pytest.raises(HTTPException, match='Duplicate upload target'):
        service.save_uploads('user-b', [upload_a, upload_b], relative_paths=['dup.txt', 'dup.txt'])

    with pytest.raises(HTTPException, match='relative_paths must match'):
        service._normalize_relative_paths([upload_a], ['a.txt', 'b.txt'])
    with pytest.raises(HTTPException, match='Illegal upload path'):
        service._normalize_relative_paths([upload_a], ['/bad.txt'])

    not_dir = user_root / 'single.txt'
    not_dir.write_text('x', encoding='utf-8')
    with pytest.raises(HTTPException, match='is not a directory'):
        service._resolve_virtual_path(user_root, '/single.txt', require_exists=True, require_dir=True)

    with pytest.raises(HTTPException, match='Workspace path not found'):
        service.resolve_workspace_path('user-b', '/missing.txt', require_exists=True)

    assert service._sanitize_user_id(' user:/a ') == 'user--a'
    assert service._sanitize_user_id('   ') == 'unknown-user'
    assert service._parent_virtual_path('/') is None
    assert service._parent_virtual_path('/docs') == '/'
    assert service._to_virtual_path(user_root, user_root) == '/'

    monkeypatch.setattr('backend.app.services.workspace_service.os.scandir', lambda path: (_ for _ in ()).throw(PermissionError('denied')))
    with pytest.raises(HTTPException, match='Permission denied'):
        service.list_dir('user-b')

    monkeypatch.setattr(service, '_ensure_user_root', lambda user_id: user_root)
    monkeypatch.setattr(
        service,
        '_resolve_virtual_path',
        lambda root, raw_path, require_exists, require_dir: ('/', user_root),
    )
    real_stat = Path.stat
    monkeypatch.setattr(
        Path,
        'stat',
        lambda self, *args, **kwargs: (_ for _ in ()).throw(PermissionError('denied'))
        if self == user_root
        else real_stat(self, *args, **kwargs),
    )
    with pytest.raises(HTTPException, match='Permission denied'):
        service.stat_path('user-b')


def test_workspace_service_covers_remaining_helper_branches(monkeypatch, tmp_path: Path):
    service = WorkspaceService(tmp_path / 'workspace')
    user_root = service._ensure_user_root('user-a')
    (user_root / 'file.txt').write_text('hello', encoding='utf-8')

    class FakeEntry:
        def __init__(self, name: str, path: Path, *, fail: bool = False):
            self.name = name
            self.path = str(path)
            self._fail = fail

        def stat(self, follow_symlinks=False):
            if self._fail:
                raise OSError('broken')
            return Path(self.path).stat()

        def is_dir(self, follow_symlinks=False):
            return False

    class FakeScandir:
        def __enter__(self):
            return [FakeEntry('broken.txt', user_root / 'broken.txt', fail=True), FakeEntry('file.txt', user_root / 'file.txt')]

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('backend.app.services.workspace_service.os.scandir', lambda path: FakeScandir())
    listed = service.list_dir('user-a')
    assert listed.total == 1
    assert listed.items[0].name == 'file.txt'

    deleted = service.delete_paths('user-a', ['/file.txt', '/file.txt'])
    assert deleted.deleted_paths == ['/file.txt']

    with pytest.raises(HTTPException, match='Illegal upload path'):
        service._normalize_relative_paths([UploadFile(filename='a.txt', file=io.BytesIO(b'a'))], ['docs/../a.txt'])

    assert service._normalize_virtual_path('.') == '/'
    single_file = user_root / 'single.bin'
    single_file.write_bytes(b'1234')
    assert service._scan_stats(single_file) == (1, 0, 4)


def test_local_file_service_covers_branches(monkeypatch, tmp_path: Path):
    service = LocalFileService()
    local_dir = tmp_path / 'docs'
    local_dir.mkdir()
    (local_dir / 'a.txt').write_text('a', encoding='utf-8')

    with pytest.raises(HTTPException, match="Query parameter 'path' is required"):
        service._resolve_existing_path('   ')
    with pytest.raises(HTTPException, match='Path not found'):
        service._resolve_existing_path(str(tmp_path / 'missing'))
    with pytest.raises(HTTPException, match='Path is not a directory'):
        service._resolve_existing_path(str(local_dir / 'a.txt'), require_dir=True)

    assert service._parent_path(Path('/')) is None

    monkeypatch.setattr('backend.app.services.local_file_service.sys.platform', 'linux')
    assert service.list_drives()[0].path == '/'

    monkeypatch.setattr('backend.app.services.local_file_service.os.scandir', lambda path: (_ for _ in ()).throw(PermissionError('denied')))
    with pytest.raises(HTTPException, match='Permission denied'):
        service.list_dir(str(local_dir))

    monkeypatch.setattr(service, '_resolve_existing_path', lambda raw_path, require_dir=False: local_dir)
    real_stat = Path.stat
    monkeypatch.setattr(
        Path,
        'stat',
        lambda self, *args, **kwargs: (_ for _ in ()).throw(PermissionError('denied'))
        if self == local_dir
        else real_stat(self, *args, **kwargs),
    )
    with pytest.raises(HTTPException, match='Permission denied'):
        service.stat_path(str(local_dir))


def test_local_file_service_covers_remaining_branches(monkeypatch, tmp_path: Path):
    service = LocalFileService()
    local_dir = tmp_path / 'docs'
    local_dir.mkdir()
    (local_dir / 'ok.txt').write_text('ok', encoding='utf-8')

    class FakeEntry:
        def __init__(self, name: str, path: Path, *, fail: bool = False):
            self.name = name
            self.path = str(path)
            self._fail = fail

        def stat(self, follow_symlinks=False):
            if self._fail:
                raise OSError('broken')
            return Path(self.path).stat()

        def is_dir(self, follow_symlinks=False):
            return False

    class FakeScandir:
        def __enter__(self):
            return [FakeEntry('broken.txt', local_dir / 'broken.txt', fail=True), FakeEntry('ok.txt', local_dir / 'ok.txt')]

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('backend.app.services.local_file_service.os.scandir', lambda path: FakeScandir())
    current_path, parent_path, items = service.list_dir(str(local_dir))
    assert current_path.endswith('docs')
    assert parent_path is not None
    assert [item.name for item in items] == ['ok.txt']

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'ctypes':
            raise ImportError('ctypes unavailable')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    monkeypatch.setattr('backend.app.services.local_file_service.sys.platform', 'win32')
    monkeypatch.setattr('backend.app.services.local_file_service.os.path.exists', lambda drive: drive == 'D:/')
    drives = service.list_drives()
    assert len(drives) == 1
    assert drives[0].path == 'D:/'
    assert drives[0].label == 'D:'


def test_remote_file_service_covers_paths_and_disconnect(monkeypatch):
    operations = []

    class FakeEngine:
        def connect(self):
            operations.append('connect')

        def disconnect(self):
            operations.append('disconnect')
            raise RuntimeError('ignore disconnect failure')

        def list_dir(self, path):
            operations.append(('list_dir', path))
            return [SimpleNamespace(name='data.txt', path=f'{path}/data.txt', is_dir=False, size=4, mtime=1.0, mode='644')]

        def stat(self, path):
            operations.append(('stat', path))
            return SimpleNamespace(name='docs', path=path, is_dir=True, size=0, mtime=1.0, mode='755')

        def mkdir(self, path):
            operations.append(('mkdir', path))

        def rename(self, source, target):
            operations.append(('rename', source, target))

        def remove_dir_recursive(self, path):
            operations.append(('rm-r', path))

        def remove_dir(self, path):
            operations.append(('rmdir', path))

        def remove_file(self, path):
            operations.append(('rm', path))

    service = RemoteFileService({'session-1': _site(owner_user_id='user-a')}, 'user-a')
    monkeypatch.setattr(service, '_build_engine', staticmethod(lambda site: FakeEngine()))

    target, parent, items = service.list_dir('session-1')
    assert target == '/remote'
    assert parent == '/'
    assert items[0].path == '/remote/data.txt'

    assert isinstance(service.stat_path('session-1', '/remote/docs'), RemoteEntryResponse)
    service.mkdir('session-1', '/remote/new')
    service.rename('session-1', '/remote/old', '/remote/new')
    service.delete('session-1', '/remote/docs', recursive=False)

    monkeypatch.setattr(FakeEngine, 'stat', lambda self, path: SimpleNamespace(name='a.txt', path=path, is_dir=False, size=1, mtime=1.0, mode='644'))
    service.delete('session-1', '/remote/a.txt')
    deleted = service.delete_many('session-1', ['/remote/folder/file.txt', '/remote/a.txt', '/remote/a.txt'])
    assert deleted == ['/remote/folder/file.txt', '/remote/a.txt']

    with pytest.raises(HTTPException, match='Remote path must not be blank'):
        service._require_non_blank_remote_path('   ')
    with pytest.raises(HTTPException, match="Session 'missing' not found"):
        service._require_session('missing')

    assert operations


def test_remote_file_service_covers_remaining_helpers(monkeypatch):
    service = RemoteFileService({}, 'user-a')
    assert service._normalize_optional_remote_path('   ') is None

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'src.engines.sftp_engine':
            raise ModuleNotFoundError('missing-sftp')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    with pytest.raises(HTTPException, match='Remote file dependency unavailable'):
        service._build_engine(_site())


def test_site_service_covers_error_paths():
    payload = SiteUpsertRequest(
        name='demo',
        host='example.com',
        port=22,
        username='alice',
        auth_method='password',
        remote_root=' ',
        remember_password=True,
        password='secret',
        default_transfer_protocol='sftp',
    )

    service = SiteService(SimpleNamespace(load_or_raise=lambda: (_ for _ in ()).throw(RuntimeError('load-bad'))), 'user-a')
    with pytest.raises(HTTPException, match='load-bad'):
        service.list_sites()

    save_service = SiteService(
        SimpleNamespace(
            load_or_raise=lambda: [_site(owner_user_id='user-a')],
            save=lambda sites: (_ for _ in ()).throw(RuntimeError('save-bad')),
        ),
        'user-a',
    )
    with pytest.raises(HTTPException, match='save-bad'):
        save_service.delete_site('demo')

    in_memory_sites = [_site(owner_user_id='user-a')]
    concrete = SiteService(
        SimpleNamespace(load_or_raise=lambda: list(in_memory_sites), save=lambda sites: in_memory_sites.__setitem__(slice(None), sites)),
        'user-a',
    )
    with pytest.raises(HTTPException, match="Site 'missing' not found"):
        concrete.update_site('missing', payload)

    response = SiteService.to_response(_site(remember_password=False, password='secret'))
    assert response.has_password is False

    updated = concrete._to_site_config(
        SiteUpsertRequest(
            name='gpu',
            host='gpu.example.com',
            port=22,
            username='alice',
            auth_method='key',
            remote_root=' ',
            key_path='C:/keys/id',
            default_transfer_protocol='scp',
        ),
        existing=_site(name='gpu', auth_method='key', password=None, key_path='C:/keys/id', key_passphrase='phrase'),
    )
    assert updated.key_passphrase == 'phrase'
    assert updated.remote_root == '/'


def test_log_service_covers_duplicate_attach_and_close(monkeypatch):
    service = LogService(max_entries=2)
    logger = logging.getLogger('test-log-service')
    service.attach_logger(logger)
    service.attach_logger(logger)
    logger.info('hello')
    logger.info('world')
    logger.info('third')

    snapshot = service.snapshot(limit=1)
    assert snapshot.total == 2
    assert len(snapshot.items) == 1

    service.clear()
    assert service.snapshot().total == 0

    handler = InMemoryLogHandler(service)
    monkeypatch.setattr(service, 'append_entry', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('emit-bad')))
    record = logging.makeLogRecord({'msg': 'boom', 'levelname': 'INFO', 'levelno': logging.INFO, 'name': 'demo'})
    monkeypatch.setattr(handler, 'handleError', lambda rec: setattr(rec, '_handled', True))
    handler.emit(record)
    assert getattr(record, '_handled', False) is True

    service.close()
    assert service._attached_loggers == {}


def test_user_cleanup_service_covers_error_paths(monkeypatch, tmp_path: Path):
    service = UserCleanupService(SimpleNamespace(scheduler=None))
    assert service._cancel_and_clear_tasks('user-a') == (0, 0)

    task = Task(
        task_id='task-1',
        kind='file_transfer',
        engine='sftp',
        src='a',
        dst='b',
        bytes_total=1,
        owner_user_id='user-a',
        status='running',
    )
    scheduler = SimpleNamespace(
        tasks={'task-1': task},
        task_lock=Lock(),
        cancel_task=lambda task_id: True,
        task_queue=['task-1'],
        queued_task_ids={'task-1'},
        active_task_ids={'task-1'},
        futures={'task-1': object()},
    )
    cleanup = UserCleanupService(SimpleNamespace(scheduler=scheduler))
    timeline = iter([0.0, 6.0, 6.0])
    monkeypatch.setattr('backend.app.services.user_cleanup_service.time.monotonic', lambda: next(timeline))
    monkeypatch.setattr('backend.app.services.user_cleanup_service.time.sleep', lambda seconds: None)
    with pytest.raises(HTTPException, match='still stopping'):
        cleanup._cancel_and_clear_tasks('user-a')

    for app_state in (
        SimpleNamespace(site_store=None),
        SimpleNamespace(site_store=SimpleNamespace(load_or_raise=lambda: (_ for _ in ()).throw(RuntimeError('load-bad')))),
    ):
        with pytest.raises(HTTPException):
            UserCleanupService(app_state)._delete_sites('user-a')

    failing_save_state = SimpleNamespace(
        site_store=SimpleNamespace(
            load_or_raise=lambda: [_site(owner_user_id='user-a')],
            save=lambda items: (_ for _ in ()).throw(RuntimeError('save-bad')),
        )
    )
    with pytest.raises(HTTPException, match='save-bad'):
        UserCleanupService(failing_save_state)._delete_sites('user-a')

    with pytest.raises(HTTPException, match='Workspace root is unavailable'):
        UserCleanupService(SimpleNamespace(runtime_settings=None))._clear_workspace('user-a')

    assert UserCleanupService(SimpleNamespace(activity_service=None))._clear_activity('user-a') == 0


def test_task_service_covers_helper_branches(monkeypatch, tmp_path: Path):
    scheduler = SimpleNamespace(
        parallel_threshold='bad',
        remote_dualpath_threshold='bad',
        task_lock=Lock(),
        tasks={},
        queued_task_ids=set(),
        active_task_ids=set(),
        futures={},
        task_queue=[],
        get_task=lambda task_id: None,
        add_task=lambda task: scheduler.tasks.setdefault(task.task_id, task),
        pause_task=lambda task_id: False,
    )
    state = SimpleNamespace(
        require_scheduler=lambda: scheduler,
        remote_sessions={'session-1': _site(owner_user_id='user-a')},
        session_lock=Lock(),
        runtime_settings=SimpleNamespace(workspace_root=tmp_path / 'workspace'),
    )
    service = TaskService(state)

    with pytest.raises(HTTPException, match="Task 'missing' not found"):
        service.pause_task('missing', 'user-a')

    broken_service = TaskService(SimpleNamespace(require_scheduler=lambda: (_ for _ in ()).throw(RuntimeError('scheduler-bad'))))
    with pytest.raises(HTTPException, match='scheduler-bad'):
        broken_service.list_tasks('user-a')

    with pytest.raises(HTTPException, match="Session 'missing' not found"):
        service._require_session('missing', 'user-a')
    with pytest.raises(HTTPException, match='Local path must not be blank'):
        service._resolve_local_path('   ', require_exists=False)
    with pytest.raises(HTTPException, match='Path not found'):
        service._resolve_local_path(str(tmp_path / 'missing'), require_exists=True)
    with pytest.raises(HTTPException, match='Remote path must not be blank'):
        service._require_non_blank_remote_path('   ')

    assert service._resolve_file_engine(_site(default_transfer_protocol='scp'), 1, 'scp', scheduler) == 'scp'
    assert service._resolve_file_engine(_site(default_transfer_protocol='sftp'), 999999999, 'parallel', scheduler) == 'parallel'
    assert service._resolve_file_engine(_site(default_transfer_protocol='sftp'), 1, 'sftp', scheduler) == 'sftp'
    assert service._resolve_remote_copy_engine('dualpath', 1, scheduler) == 'dualpath'
    assert service._parallel_threshold(scheduler) == 50 * 1024 * 1024
    assert service._remote_dualpath_threshold(scheduler) == 128 * 1024 * 1024

    local_file = tmp_path / 'workspace' / 'user-a' / 'docs' / 'report.txt'
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_text('hello', encoding='utf-8')
    endpoint_type, path, label = service._present_endpoint('local', str(local_file), 'local')
    assert (endpoint_type, path, label) == ('workspace', '/docs/report.txt', 'workspace:/docs/report.txt')
    assert service._present_endpoint('remote', '/remote/a.txt', 'remote') == ('remote', '/remote/a.txt', 'remote')

    broken_state = SimpleNamespace(runtime_settings=None)
    broken_service = TaskService(SimpleNamespace(runtime_settings=None))
    with pytest.raises(HTTPException, match='Workspace root is unavailable'):
        broken_service._workspace_service()

    class BadEngine:
        def disconnect(self):
            raise RuntimeError('ignore')

    service._disconnect_quietly(BadEngine())
    assert service._task_lock(SimpleNamespace(task_lock=None)).__class__.__name__ == 'nullcontext'


def test_task_service_covers_remaining_creation_and_import_branches(monkeypatch, tmp_path: Path):
    class Scheduler:
        def __init__(self):
            self.parallel_threshold = 1
            self.remote_dualpath_threshold = 1
            self.task_lock = Lock()
            self.tasks = {}
            self.queued_task_ids = set()
            self.active_task_ids = set()
            self.futures = {}
            self.task_queue = []

        def add_task(self, task):
            self.tasks[task.task_id] = task

        def get_task(self, task_id):
            return self.tasks.get(task_id)

        def pause_task(self, task_id):
            return False

        def get_all_tasks(self):
            return list(self.tasks.values())

    scheduler = Scheduler()
    state = SimpleNamespace(
        require_scheduler=lambda: scheduler,
        remote_sessions={'session-1': _site(owner_user_id='user-a'), 'dst-1': _site(name='backup', owner_user_id='user-a')},
        session_lock=Lock(),
        runtime_settings=SimpleNamespace(workspace_root=tmp_path / 'workspace'),
    )
    service = TaskService(state)

    upload_dir = tmp_path / 'upload-dir'
    (upload_dir / 'nested').mkdir(parents=True)
    (upload_dir / 'nested' / 'a.txt').write_text('a', encoding='utf-8')
    uploaded = service.create_upload(
        TaskCreateUploadRequest(session_id='session-1', local_path=str(upload_dir), remote_path='/remote/upload-dir', engine='auto'),
        'user-a',
    )
    assert uploaded.kind == 'folder_transfer'

    workspace_dir = tmp_path / 'workspace' / 'user-a' / 'docs'
    workspace_dir.mkdir(parents=True)
    (workspace_dir / 'a.txt').write_text('a', encoding='utf-8')
    workspace_uploaded = service.create_upload_from_workspace(
        SimpleNamespace(session_id='session-1', workspace_path='/docs', remote_path='/remote/docs', engine='auto'),
        'user-a',
    )
    assert workspace_uploaded.kind == 'folder_transfer'

    class FileEngine:
        def connect(self):
            return None

        def disconnect(self):
            return None

        def stat(self, path):
            return SimpleNamespace(name='a.txt', path=path, is_dir=False, size=5, mtime=1.0, mode='644')

        def list_dir(self, path):
            return [SimpleNamespace(name='a.txt', path=f'{path}/a.txt', is_dir=False, size=5, mtime=1.0, mode='644')]

    monkeypatch.setattr(service, '_build_remote_engine', staticmethod(lambda site: FileEngine()))
    downloaded = service.create_download(
        SimpleNamespace(session_id='session-1', remote_path='/remote/a.txt', local_path=str(tmp_path / 'downloads' / 'a.txt'), engine='auto'),
        'user-a',
    )
    assert downloaded.kind == 'file_transfer'

    class DirEngine(FileEngine):
        def stat(self, path):
            return SimpleNamespace(name='docs', path=path, is_dir=True, size=0, mtime=1.0, mode='755')

        def list_dir(self, path):
            return [SimpleNamespace(name='a.txt', path=f'{path}/a.txt', is_dir=False, size=5, mtime=1.0, mode='644')]

    monkeypatch.setattr(service, '_build_remote_engine', staticmethod(lambda site: DirEngine()))
    to_workspace = service.create_download_to_workspace(
        SimpleNamespace(session_id='session-1', remote_path='/remote/docs', workspace_path='/docs', engine='auto'),
        'user-a',
    )
    assert to_workspace.kind == 'folder_transfer'

    remote_copy = service.create_remote_copy(
        SimpleNamespace(src_session_id='session-1', dst_session_id='dst-1', src_path='/remote/docs', dst_path='/backup/docs', engine='auto'),
        'user-a',
    )
    assert remote_copy.kind == 'folder_transfer'

    scheduler.tasks['task-1'] = Task(
        task_id='task-1',
        kind='file_transfer',
        engine='sftp',
        src='a',
        dst='b',
        bytes_total=1,
        owner_user_id='user-a',
        status='running',
    )
    with pytest.raises(HTTPException, match='Cannot pause task'):
        service.pause_task('task-1', 'user-a')

    assert service._resolve_file_engine(_site(default_transfer_protocol='sftp'), 999, 'auto', scheduler) == 'parallel'
    assert service._scan_local_dir(upload_dir) == (1, 1)

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'src.engines.sftp_engine':
            raise ModuleNotFoundError('missing-sftp')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    with pytest.raises(HTTPException, match='Remote task dependency unavailable'):
        TaskService._build_remote_engine(_site())
