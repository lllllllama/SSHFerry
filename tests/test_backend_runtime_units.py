from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import secrets
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.api import deps
from backend.app.api.deps import X_SSHFERRY_TOKEN
from backend.app.config import RuntimeSettings, build_runtime_settings
from backend.app.main import create_app, lifespan_factory, run
from backend.app.services.activity_service import ActivityService
from backend.app.services.app_state import AppState, _build_auth_token, _build_site_store
from backend.app.services.auth_service import AuthContext, AuthSession, AuthUser
from backend.app.services.log_service import LogService


def _make_settings(tmp_path: Path, **overrides) -> RuntimeSettings:
    data = {
        'runtime_mode': 'local-dev',
        'allowed_origins': ('http://localhost:5173', 'null'),
        'allow_credentials': True,
        'access_cookie_name': 'access-cookie',
        'refresh_cookie_name': 'refresh-cookie',
        'cookie_secure': False,
        'cookie_samesite': 'lax',
        'access_token_ttl_seconds': 60,
        'refresh_token_ttl_seconds': 600,
        'workspace_root': tmp_path / 'workspace',
        'public_base_url': None,
        'owner_file': tmp_path / 'auth' / 'owner.json',
        'users_file': tmp_path / 'auth' / 'users.json',
        'owner_username': None,
        'owner_display_name': None,
        'owner_password': None,
        'owner_password_hash': None,
        'auth_secret': 'secret',
        'local_dev_auto_login': True,
        'legacy_local_token_enabled': True,
        'login_rate_limit_window_seconds': 60,
        'login_rate_limit_max_attempts': 10,
        'login_lockout_seconds': 300,
        'login_lockout_max_failures': 5,
        'refresh_rate_limit_window_seconds': 60,
        'refresh_rate_limit_max_attempts': 20,
    }
    data.update(overrides)
    return RuntimeSettings(**data)


def _make_context(user_id: str = 'owner-1', role: str = 'owner') -> AuthContext:
    return AuthContext(
        user=AuthUser(
            user_id=user_id,
            username=user_id,
            display_name=user_id,
            role=role,
        ),
        session=AuthSession(
            session_id=f'session-{user_id}',
            user_id=user_id,
            username=user_id,
            role=role,
            refresh_token_hash='hash',
            created_at=1,
            expires_at=9999999999,
            last_refreshed_at=1,
        ),
        auth_scheme='test',
    )


class _RouteState:
    def __init__(self, *, runtime_settings=None):
        self.runtime_settings = runtime_settings or SimpleNamespace(
            runtime_mode='local-dev',
            is_deployed_web=False,
            local_dev_auto_login=False,
            legacy_local_token_enabled=True,
            access_cookie_name='access-cookie',
            refresh_cookie_name='refresh-cookie',
            allowed_origins=('http://localhost:5173',),
            allow_credentials=True,
        )
        self.auth_token = 'route-token'
        self.activity_service = ActivityService()
        self.log_service = LogService()
        self.auth_service = SimpleNamespace(
            issue_captcha=lambda: SimpleNamespace(captcha_id='cap-1', code='ABCD', expires_at=123),
            get_access_cookie=lambda cookies: cookies.get('access-cookie'),
            get_refresh_cookie=lambda cookies: cookies.get('refresh-cookie'),
            authenticate_access_token=lambda token: _make_context('auth-user'),
            auto_login_local_dev=lambda client_ip, user_agent: (_make_context('auto-user'), SimpleNamespace(access_token='a', refresh_token='r')),
            attach_auth_cookies=lambda response, tokens: response,
            clear_auth_cookies=lambda response: response,
            verify_captcha=lambda captcha_id, captcha_code: None,
            signup=lambda **kwargs: (_make_context('signed-up'), SimpleNamespace(access_token='a', refresh_token='r')),
            login=lambda **kwargs: (_make_context('logged-in'), SimpleNamespace(access_token='a', refresh_token='r')),
            authenticate_refresh_token=lambda **kwargs: (_make_context('refreshed'), SimpleNamespace(access_token='a', refresh_token='r')),
            logout=lambda **kwargs: None,
            get_local_dev_context=lambda: _make_context('legacy-local'),
            is_ready=True,
            start=lambda: None,
            stop=lambda: None,
        )
        self.remote_sessions = {}
        self.session_lock = SimpleNamespace(__enter__=lambda self: self, __exit__=lambda self, exc_type, exc, tb: False)
        self.site_store = SimpleNamespace(validate=lambda: None)
        self.scheduler = SimpleNamespace(running=True, stop=lambda: None)
        self.startup_error = None

    def start(self):
        return None

    def stop(self):
        return None

    @property
    def session_count(self):
        return len(self.remote_sessions)

    @property
    def is_ready(self):
        return True

    def require_scheduler(self):
        return self.scheduler


def test_build_runtime_settings_supports_public_origin_and_secure_cookie(monkeypatch, tmp_path: Path):
    env = {
        'SSHFERRY_RUNTIME_MODE': 'deployed-web',
        'SSHFERRY_PUBLIC_BASE_URL': 'https://sshferry.example.com/app',
        'SSHFERRY_WORKSPACE_ROOT': str(tmp_path / 'workspace'),
        'SSHFERRY_OWNER_FILE': str(tmp_path / 'auth' / 'owner.json'),
        'SSHFERRY_AUTH_COOKIE_SAMESITE': 'none',
        'SSHFERRY_AUTH_COOKIE_SECURE': 'true',
    }
    monkeypatch.setattr(os, 'environ', {**os.environ, **env})

    settings = build_runtime_settings()

    assert settings.runtime_mode == 'deployed-web'
    assert settings.public_base_url == 'https://sshferry.example.com/app'
    assert 'https://sshferry.example.com' in settings.allowed_origins
    assert settings.cookie_secure is True
    assert settings.cookie_samesite == 'none'


def test_build_runtime_settings_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv('SSHFERRY_RUNTIME_MODE', 'unsupported')
    with pytest.raises(RuntimeError, match='Unsupported SSHFERRY_RUNTIME_MODE'):
        build_runtime_settings()

    monkeypatch.setenv('SSHFERRY_RUNTIME_MODE', 'local-dev')
    monkeypatch.setenv('SSHFERRY_PUBLIC_BASE_URL', 'sshferry.example.com')
    with pytest.raises(RuntimeError, match='must include scheme and host'):
        build_runtime_settings()

    monkeypatch.setenv('SSHFERRY_PUBLIC_BASE_URL', 'https://sshferry.example.com')
    monkeypatch.setenv('SSHFERRY_AUTH_COOKIE_SAMESITE', 'weird')
    with pytest.raises(RuntimeError, match='must be one of'):
        build_runtime_settings()

    monkeypatch.setenv('SSHFERRY_AUTH_COOKIE_SAMESITE', 'none')
    monkeypatch.setenv('SSHFERRY_AUTH_COOKIE_SECURE', 'false')
    with pytest.raises(RuntimeError, match='requires SSHFERRY_AUTH_COOKIE_SECURE=true'):
        build_runtime_settings()


def test_build_runtime_settings_uses_portable_data_dir_override(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / 'portable-data'
    monkeypatch.setenv('SSHFERRY_RUNTIME_MODE', 'local-dev')
    monkeypatch.setenv('SSHFERRY_DATA_DIR', str(data_dir))
    monkeypatch.delenv('SSHFERRY_WORKSPACE_ROOT', raising=False)
    monkeypatch.delenv('SSHFERRY_OWNER_FILE', raising=False)
    monkeypatch.delenv('SSHFERRY_USERS_FILE', raising=False)

    settings = build_runtime_settings()

    assert settings.workspace_root == data_dir / 'workspace'
    assert settings.owner_file == data_dir / 'backend_runtime' / 'auth' / 'owner.json'
    assert settings.users_file == data_dir / 'backend_runtime' / 'auth' / 'users.json'


def test_build_auth_token_prefers_env(monkeypatch):
    monkeypatch.setenv('SSHFERRY_LOCAL_TOKEN', 'explicit-token')
    assert _build_auth_token() == 'explicit-token'

    monkeypatch.delenv('SSHFERRY_LOCAL_TOKEN', raising=False)
    assert _build_auth_token()


def test_build_site_store_falls_back_to_workspace(monkeypatch, tmp_path: Path):
    class FakeSiteStore:
        def __init__(self, path=None):
            if path is None:
                raise RuntimeError('boom')
            self.path = path

    monkeypatch.setattr('backend.app.services.app_state.SiteStore', FakeSiteStore)
    monkeypatch.setattr(
        'backend.app.services.app_state.backend_runtime_dir',
        lambda: tmp_path / '.backend_runtime',
    )

    store = _build_site_store()

    assert store.path == tmp_path / '.backend_runtime' / 'sites.json'


def test_app_state_start_stop_and_require_scheduler(monkeypatch, tmp_path: Path):
    state = AppState(
        runtime_settings=_make_settings(tmp_path),
        site_store=SimpleNamespace(validate=lambda: (_ for _ in ()).throw(RuntimeError('site-bad'))),
    )

    class FakeScheduler:
        def __init__(self, logger, activity_service, workspace_root):
            assert workspace_root == state.runtime_settings.workspace_root
            self.running = True
            self.stopped = False

        def start(self):
            raise RuntimeError('scheduler-bad')

        def stop(self):
            self.stopped = True
            self.running = False

    fake_module = ModuleType('src.core.scheduler')
    fake_module.TaskScheduler = FakeScheduler
    monkeypatch.setitem(__import__('sys').modules, 'src.core.scheduler', fake_module)
    monkeypatch.setattr(state.auth_service, 'start', lambda: (_ for _ in ()).throw(RuntimeError('auth-bad')))

    state.start()

    assert state.startup_error == 'auth-bad; site-bad; scheduler-bad'
    with pytest.raises(RuntimeError, match='auth-bad; site-bad; scheduler-bad'):
        state.require_scheduler()

    state.scheduler = SimpleNamespace(running=True, stop=lambda: None)
    state.stop()


def test_app_state_ready_and_successful_start(monkeypatch, tmp_path: Path):
    state = AppState(
        runtime_settings=_make_settings(tmp_path),
        site_store=SimpleNamespace(validate=lambda: None),
    )

    class FakeScheduler:
        def __init__(self, logger, activity_service, workspace_root):
            self.running = False

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    fake_module = ModuleType('src.core.scheduler')
    fake_module.TaskScheduler = FakeScheduler
    monkeypatch.setitem(__import__('sys').modules, 'src.core.scheduler', fake_module)
    monkeypatch.setattr(state.auth_service, 'start', lambda: None)

    state.start()

    assert state.is_ready is True
    assert state.require_scheduler().running is True


def test_lifespan_factory_starts_and_stops_state():
    app = FastAPI()
    state = SimpleNamespace(started=False, stopped=False)

    def factory():
        return SimpleNamespace(
            start=lambda: setattr(state, 'started', True),
            stop=lambda: setattr(state, 'stopped', True),
        )

    async def runner():
        async with lifespan_factory(app, factory):
            assert state.started is True
            assert hasattr(app.state, 'app_state')
        assert state.stopped is True

    asyncio.run(runner())


def test_create_app_handles_preview_state_without_runtime_settings():
    app = create_app(app_state_factory=lambda: SimpleNamespace(start=lambda: None, stop=lambda: None))

    assert app.title == 'SSHFerry Backend'
    assert any(m.cls.__name__ == 'CORSMiddleware' for m in app.user_middleware)


def test_run_passes_env_to_uvicorn(monkeypatch):
    captured = {}
    monkeypatch.setenv('SSHFERRY_BACKEND_HOST', '0.0.0.0')
    monkeypatch.setenv('SSHFERRY_BACKEND_PORT', '19090')
    monkeypatch.setattr('backend.app.main.uvicorn.run', lambda app, host, port, reload: captured.update({
        'app': app,
        'host': host,
        'port': port,
        'reload': reload,
    }))

    run()

    assert captured == {
        'app': 'backend.app.main:app',
        'host': '0.0.0.0',
        'port': 19090,
        'reload': False,
    }


def test_deps_support_cookie_and_legacy_fallback_paths(tmp_path: Path):
    settings = _make_settings(tmp_path)
    app_state = SimpleNamespace(
        runtime_settings=settings,
        auth_token='expected-token',
        auth_service=SimpleNamespace(
            get_access_cookie=lambda cookies: cookies.get('access-cookie'),
            authenticate_access_token=lambda token: _make_context('cookie-user'),
            get_local_dev_context=lambda: _make_context('legacy-user'),
        ),
    )

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(app_state=app_state)), cookies={'access-cookie': 'ok'})
    assert deps.resolve_request_auth_context(request).user.user_id == 'cookie-user'

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(app_state=app_state)), cookies={})
    assert deps.resolve_request_auth_context(request, x_sshferry_token='expected-token').user.user_id == 'legacy-user'


def test_deps_raise_for_invalid_owner_and_websocket_auth(tmp_path: Path):
    settings = _make_settings(tmp_path, legacy_local_token_enabled=False)
    app_state = SimpleNamespace(runtime_settings=settings, auth_token='expected-token', auth_service=None)

    assert deps._legacy_local_auth_enabled(SimpleNamespace(runtime_settings=None)) is True
    assert deps._resolve_legacy_local_token(app_state, 'expected-token') is None

    with pytest.raises(HTTPException, match='Owner access required'):
        deps._require_owner_context(_make_context(role='viewer'))

    websocket = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(app_state=SimpleNamespace(
            runtime_settings=_make_settings(tmp_path),
            auth_token='expected-token',
            auth_service=SimpleNamespace(
                get_access_cookie=lambda cookies: cookies.get('access-cookie'),
                authenticate_access_token=lambda token: (_ for _ in ()).throw(HTTPException(status_code=401, detail='bad cookie')),
                get_local_dev_context=lambda: _make_context('ws-legacy'),
            ),
        ))),
        cookies={'access-cookie': 'bad'},
        query_params={},
        headers={},
    )
    with pytest.raises(Exception, match='bad cookie'):
        deps.require_websocket_authenticated(websocket)

    websocket.cookies = {}
    websocket.query_params = {'token': 'expected-token'}
    assert deps.require_websocket_authenticated(websocket).user.user_id == 'ws-legacy'

    websocket.query_params = {'token': 'wrong'}
    with pytest.raises(Exception, match='Invalid local session token'):
        deps.require_websocket_authenticated(websocket)

    websocket.query_params = {}
    websocket.headers = {}
    with pytest.raises(Exception, match='Not authenticated'):
        deps.require_websocket_authenticated(websocket)

    viewer_context = _make_context('viewer-1', role='viewer')
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr('backend.app.api.deps.require_websocket_authenticated', lambda _websocket: viewer_context)
    try:
        with pytest.raises(Exception, match='Owner access required'):
            deps.require_websocket_owner(SimpleNamespace())
    finally:
        monkeypatch.undo()


def test_ws_routes_cover_activity_and_log_snapshot_paths(monkeypatch):
    context = _make_context('user-a')
    state = SimpleNamespace(
        activity_service=SimpleNamespace(
            snapshot=lambda user_id, limit: SimpleNamespace(
                items=[SimpleNamespace(sequence=1, timestamp=1.0, level='info', category='task', action='done', title='Done', message='ok')],
                total=1,
                sequence=1,
            )
        ),
        log_service=SimpleNamespace(
            snapshot=lambda limit: SimpleNamespace(
                items=[SimpleNamespace(sequence=2, timestamp=2.0, level='INFO', logger='demo', message='msg', rendered='rendered')],
                total=1,
                sequence=2,
            )
        ),
        auth_token=secrets.token_urlsafe(16),
        start=lambda: None,
        stop=lambda: None,
        runtime_settings=SimpleNamespace(allowed_origins=('http://localhost:5173',), allow_credentials=True),
    )
    monkeypatch.setattr('backend.app.api.routes.ws.require_websocket_authenticated', lambda _websocket: context)
    monkeypatch.setattr('backend.app.api.routes.ws.require_websocket_owner', lambda _websocket: context)

    app = create_app(app_state_factory=lambda: state)
    with TestClient(app) as client:
        with client.websocket_connect('/api/ws/activity') as websocket:
            message = websocket.receive_json()
        with client.websocket_connect('/api/ws/logs') as websocket:
            log_message = websocket.receive_json()

    assert message['type'] == 'activity_snapshot'
    assert message['items'][0]['title'] == 'Done'
    assert log_message['type'] == 'log_snapshot'
    assert log_message['items'][0]['logger'] == 'demo'


def test_ws_routes_cover_error_paths(monkeypatch):
    context = _make_context('user-a')
    state = SimpleNamespace(
        activity_service=SimpleNamespace(snapshot=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('activity-bad'))),
        log_service=SimpleNamespace(snapshot=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('log-bad'))),
        auth_token=secrets.token_urlsafe(16),
        start=lambda: None,
        stop=lambda: None,
        runtime_settings=SimpleNamespace(allowed_origins=('http://localhost:5173',), allow_credentials=True),
    )
    monkeypatch.setattr('backend.app.api.routes.ws.require_websocket_authenticated', lambda _websocket: context)
    monkeypatch.setattr('backend.app.api.routes.ws.require_websocket_owner', lambda _websocket: context)

    app = create_app(app_state_factory=lambda: state)
    with TestClient(app) as client:
        with client.websocket_connect('/api/ws/activity') as websocket:
            activity_message = websocket.receive_json()
        with client.websocket_connect('/api/ws/logs') as websocket:
            log_message = websocket.receive_json()

    assert activity_message == {'type': 'error', 'detail': 'activity-bad'}
    assert log_message == {'type': 'error', 'detail': 'log-bad'}


def test_auth_and_log_routes_cover_remaining_branches(monkeypatch, tmp_path: Path):
    runtime_settings = SimpleNamespace(
        runtime_mode='deployed-web',
        is_deployed_web=True,
        local_dev_auto_login=False,
        legacy_local_token_enabled=False,
        allowed_origins=('http://localhost:5173',),
        allow_credentials=True,
    )
    state = _RouteState(runtime_settings=runtime_settings)
    state.auth_service.get_access_cookie = lambda cookies: 'bad-cookie'
    state.auth_service.authenticate_access_token = lambda token: (_ for _ in ()).throw(
        HTTPException(status_code=401, detail='bad-cookie')
    )

    app = create_app(app_state_factory=lambda: state)
    with TestClient(app) as client:
        session_response = client.get('/api/auth/session')
        me_response = client.get('/api/auth/me')

    assert session_response.status_code == 404
    assert me_response.status_code == 401

    owner_context = _make_context('owner-1', role='owner')
    app = create_app(app_state_factory=lambda: _RouteState())
    app.dependency_overrides[deps.resolve_request_auth_context] = lambda: owner_context

    with TestClient(app) as client:
        cleared = client.delete('/api/logs')
        alias = client.get('/api/auth/me/current', headers={X_SSHFERRY_TOKEN: 'ignored'})

    assert cleared.status_code == 204
    assert alias.status_code == 200
    assert alias.json()['username'] == 'owner-1'


def test_log_ws_still_rejects_invalid_token():
    state = _RouteState()
    app = create_app(app_state_factory=lambda: state)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect('/api/ws/tasks?token=wrong-token'):
                pass

    assert exc_info.value.code == 1008
