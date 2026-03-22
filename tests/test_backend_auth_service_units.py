from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.responses import Response
import pytest

from backend.app.config import RuntimeSettings
from backend.app.services.auth_service import (
    AuthService,
    CaptchaChallenge,
    FailedLoginState,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    ROLE_OPERATOR,
    AuthSession,
    AuthUser,
    _b64encode,
    hash_password,
    render_captcha_svg,
    verify_password,
)


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
        'auth_secret': 'fixed-secret',
        'local_dev_auto_login': True,
        'legacy_local_token_enabled': True,
        'login_rate_limit_window_seconds': 60,
        'login_rate_limit_max_attempts': 10,
        'login_lockout_seconds': 300,
        'login_lockout_max_failures': 2,
        'refresh_rate_limit_window_seconds': 60,
        'refresh_rate_limit_max_attempts': 20,
    }
    data.update(overrides)
    return RuntimeSettings(**data)


def _build_started_service(tmp_path: Path, **settings_overrides) -> AuthService:
    service = AuthService(_make_settings(tmp_path, **settings_overrides), logger=logging.getLogger('test.auth'))
    service.start()
    return service


def test_auth_service_start_sets_ready_error_when_bootstrap_fails(monkeypatch, tmp_path: Path):
    service = AuthService(_make_settings(tmp_path))
    monkeypatch.setattr(service, '_load_or_create_users', lambda: (_ for _ in ()).throw(RuntimeError('boom')))

    with pytest.raises(RuntimeError, match='boom'):
        service.start()

    assert service.ready_error == 'boom'
    assert service.is_ready is False


def test_auth_service_login_and_captcha_validation_paths(monkeypatch, tmp_path: Path):
    service = _build_started_service(tmp_path)
    with pytest.raises(HTTPException, match='Username and password are required'):
        service.login('', '', client_ip=None, user_agent=None)

    service.signup('alice', 'secret-pass', None, client_ip='127.0.0.1', user_agent='ua')
    with pytest.raises(HTTPException, match='Invalid username or password'):
        service.login('alice', 'wrong-pass', client_ip='127.0.0.1', user_agent='ua')

    with pytest.raises(HTTPException, match='Captcha is required'):
        service.verify_captcha('', '')

    service._captchas_by_id['expired'] = CaptchaChallenge(captcha_id='expired', code='ABCD', expires_at=0)
    with pytest.raises(HTTPException, match='Captcha expired'):
        service.verify_captcha('expired', 'ABCD')

    challenge = service.issue_captcha()
    with pytest.raises(HTTPException, match='Incorrect captcha code'):
        service.verify_captcha(challenge.captcha_id, 'ZZZZ')

    assert challenge.captcha_id not in service._captchas_by_id


def test_auth_service_signup_refresh_and_logout_paths(tmp_path: Path):
    service = _build_started_service(tmp_path)
    context, tokens = service.signup('alice', 'secret-pass', 'Alice', client_ip='127.0.0.1', user_agent='ua')
    assert context.user.role == ROLE_OPERATOR

    with pytest.raises(HTTPException, match='Username is already registered'):
        service.signup('alice', 'another-pass', None, client_ip='127.0.0.1', user_agent='ua')

    refreshed_context, refreshed_tokens = service.authenticate_refresh_token(
        tokens.refresh_token,
        client_ip='127.0.0.2',
        user_agent='ua-2',
    )
    assert refreshed_context.user.username == 'alice'
    assert refreshed_tokens.refresh_token != tokens.refresh_token

    service.logout(refresh_token=refreshed_tokens.refresh_token)
    with pytest.raises(HTTPException, match='Invalid or expired refresh token'):
        service.authenticate_refresh_token(refreshed_tokens.refresh_token, client_ip=None, user_agent=None)

    service.logout(access_token=tokens.access_token)
    assert service._sessions_by_id[context.session.session_id].revoked_at is not None

    service.logout(access_token='malformed-token')


def test_auth_service_access_and_refresh_error_paths(monkeypatch, tmp_path: Path):
    service = _build_started_service(tmp_path)
    user = AuthUser(user_id='user-1', username='alice', display_name='Alice', role=ROLE_OPERATOR)
    session = AuthSession(
        session_id='session-1',
        user_id='user-1',
        username='alice',
        role=ROLE_OPERATOR,
        refresh_token_hash='hash-1',
        created_at=1,
        expires_at=9999999999,
        last_refreshed_at=1,
    )
    service._users_by_id[user.user_id] = user
    service._sessions_by_id[session.session_id] = session

    monkeypatch.setattr(service, '_decode_access_token', lambda token: {'typ': 'refresh'})
    with pytest.raises(HTTPException, match='Invalid access token'):
        service.authenticate_access_token('bad')

    monkeypatch.setattr(service, '_decode_access_token', lambda token: {'typ': 'access'})
    with pytest.raises(HTTPException, match='Invalid access token payload'):
        service.authenticate_access_token('bad')

    monkeypatch.setattr(service, '_decode_access_token', lambda token: {'typ': 'access', 'session_id': session.session_id})
    session.expires_at = 0
    with pytest.raises(HTTPException, match='Session expired or revoked'):
        service.authenticate_access_token('bad')

    session.expires_at = 9999999999
    service._users_by_id.clear()
    with pytest.raises(HTTPException, match='User no longer exists'):
        service.authenticate_access_token('bad')

    with pytest.raises(HTTPException, match='Missing refresh token'):
        service.authenticate_refresh_token('', client_ip=None, user_agent=None)

    service._users_by_id[user.user_id] = user
    context, tokens = service._issue_session(user, client_ip='127.0.0.1', user_agent='ua')
    assert context.user.username == 'alice'
    with pytest.raises(HTTPException, match='Invalid or expired refresh token'):
        service.authenticate_refresh_token('not-a-real-token', client_ip=None, user_agent=None)

    service._users_by_id.clear()
    with pytest.raises(HTTPException, match='User no longer exists'):
        service.authenticate_refresh_token(tokens.refresh_token, client_ip=None, user_agent=None)


def test_auth_service_cookie_and_local_dev_helpers(tmp_path: Path):
    service = _build_started_service(tmp_path)
    _, tokens = service.auto_login_local_dev(client_ip='127.0.0.1', user_agent='ua')
    response = Response()
    service.attach_auth_cookies(response, tokens)
    cookie_header = response.headers['set-cookie']
    assert 'access-cookie=' in cookie_header

    cleared = service.clear_auth_cookies(Response())
    assert 'set-cookie' in cleared.headers
    assert service.get_access_cookie({'access-cookie': 'a'}) == 'a'
    assert service.get_refresh_cookie({'refresh-cookie': 'r'}) == 'r'
    assert service.get_local_dev_context().auth_scheme == 'local-token'

    service.stop()
    assert service._sessions_by_id == {}
    assert service._captchas_by_id == {}


def test_auth_service_user_loading_error_paths(tmp_path: Path):
    service = AuthService(_make_settings(tmp_path))
    service.settings.users_file.parent.mkdir(parents=True, exist_ok=True)

    service.settings.users_file.write_text(json.dumps({'items': {}}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='must contain a list of users'):
        service._load_users_payload_locked()

    service.settings.owner_file.write_text(json.dumps({'username': '', 'password_hash': ''}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='missing username or password_hash'):
        service._load_owner_bootstrap_payload_locked()

    service = AuthService(_make_settings(tmp_path / 'owner-env', owner_username='owner'))
    with pytest.raises(RuntimeError, match='Owner bootstrap requires'):
        service._load_owner_bootstrap_payload_locked()


def test_auth_service_load_or_create_users_error_paths(tmp_path: Path):
    settings = _make_settings(tmp_path)
    settings.users_file.parent.mkdir(parents=True, exist_ok=True)

    duplicate_hash = hash_password('secret-pass')
    settings.users_file.write_text(
        json.dumps([
            {'id': 'u1', 'username': 'alice', 'display_name': 'Alice', 'role': ROLE_OPERATOR, 'password_hash': duplicate_hash, 'created_at': 1},
            {'id': 'u2', 'username': 'Alice', 'display_name': 'Alice 2', 'role': ROLE_OPERATOR, 'password_hash': duplicate_hash, 'created_at': 2},
        ]),
        encoding='utf-8',
    )
    service = AuthService(settings)
    with pytest.raises(RuntimeError, match='Duplicate username'):
        service._load_or_create_users()

    settings = _make_settings(tmp_path / 'missing-hash')
    settings.users_file.parent.mkdir(parents=True, exist_ok=True)
    settings.users_file.write_text(
        json.dumps([{'id': 'u1', 'username': 'alice', 'display_name': 'Alice', 'role': ROLE_OPERATOR, 'created_at': 1}]),
        encoding='utf-8',
    )
    service = AuthService(settings)
    with pytest.raises(RuntimeError, match='missing password_hash'):
        service._load_or_create_users()

    service = AuthService(_make_settings(tmp_path / 'deployed', runtime_mode='deployed-web'))
    with pytest.raises(RuntimeError, match='No owner account is initialized'):
        service._load_or_create_users()


def test_auth_service_loads_owner_payload_and_purges_expired_sessions(tmp_path: Path):
    settings = _make_settings(tmp_path / 'owner-file')
    settings.owner_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'id': 'owner',
        'username': 'owner',
        'display_name': 'Owner',
        'password_hash': hash_password('secret-pass'),
        'created_at': 1,
    }
    settings.owner_file.write_text(json.dumps(payload), encoding='utf-8')
    service = AuthService(settings)
    loaded = service._load_owner_bootstrap_payload_locked()
    assert loaded['username'] == 'owner'

    settings = _make_settings(tmp_path / 'owner-merge', owner_username='owner', owner_password='secret-pass')
    settings.users_file.parent.mkdir(parents=True, exist_ok=True)
    settings.users_file.write_text(
        json.dumps([
            {
                'id': 'owner',
                'username': 'owner',
                'display_name': 'Old Owner',
                'role': ROLE_OPERATOR,
                'password_hash': hash_password('old-pass'),
                'created_at': 1,
            }
        ]),
        encoding='utf-8',
    )
    service = AuthService(settings)
    service._load_or_create_users()
    assert service.owner_user is not None
    assert service.owner_user.role == 'owner'

    user = AuthUser(user_id='user-1', username='alice', display_name='Alice', role=ROLE_OPERATOR)
    session = AuthSession(
        session_id='expired-session',
        user_id='user-1',
        username='alice',
        role=ROLE_OPERATOR,
        refresh_token_hash='hash-1',
        created_at=1,
        expires_at=1,
        last_refreshed_at=1,
    )
    service._sessions_by_id[session.session_id] = session
    service._session_ids_by_refresh_hash[session.refresh_token_hash] = session.session_id
    service._purge_expired_sessions(2)
    assert service._sessions_by_id == {}
    assert service._session_ids_by_refresh_hash == {}


def test_auth_service_decodes_tokens_and_validates_rate_limits(monkeypatch, tmp_path: Path):
    service = _build_started_service(tmp_path)
    user = AuthUser(user_id='user-1', username='alice', display_name='Alice', role=ROLE_OPERATOR)
    session = AuthSession(
        session_id='session-1',
        user_id='user-1',
        username='alice',
        role=ROLE_OPERATOR,
        refresh_token_hash='hash-1',
        created_at=1,
        expires_at=9999999999,
        last_refreshed_at=1,
    )
    token, _ = service._create_access_token(user, session)
    assert service._decode_access_token(token)['session_id'] == 'session-1'

    with pytest.raises(HTTPException, match='Invalid access token'):
        service._decode_access_token('bad')

    payload = token.split('.', 2)
    with pytest.raises(HTTPException, match='Unsupported access token version'):
        service._decode_access_token(f'v2.{payload[1]}.{payload[2]}')

    with pytest.raises(HTTPException, match='Invalid access token signature'):
        service._decode_access_token(f'v1.{payload[1]}.bad-signature')

    bad_payload = _b64encode(b'not-json')
    bad_sig = _b64encode(__import__('hmac').new(service._secret, bad_payload.encode('ascii'), __import__('hashlib').sha256).digest())
    with pytest.raises(HTTPException, match='Malformed access token payload'):
        service._decode_access_token(f'v1.{bad_payload}.{bad_sig}')

    monkeypatch.setattr('backend.app.services.auth_service.time.time', lambda: 10_000)
    expired_payload = _b64encode(json.dumps({'exp': 1}).encode('utf-8'))
    expired_sig = _b64encode(__import__('hmac').new(service._secret, expired_payload.encode('ascii'), __import__('hashlib').sha256).digest())
    with pytest.raises(HTTPException, match='Access token expired'):
        service._decode_access_token(f'v1.{expired_payload}.{expired_sig}')

    service._check_rate_limit('login:1', 60, 2, 'slow down')
    service._check_rate_limit('login:1', 60, 2, 'slow down')
    with pytest.raises(HTTPException, match='slow down'):
        service._check_rate_limit('login:1', 60, 2, 'slow down')


def test_auth_service_login_lockout_and_validation_helpers(tmp_path: Path):
    service = AuthService(_make_settings(tmp_path, login_lockout_max_failures=1, login_lockout_seconds=30))
    service._record_login_failure('alice')
    assert isinstance(service._login_failures['alice'], FailedLoginState)

    with pytest.raises(HTTPException, match='Too many failed login attempts'):
        service._ensure_login_not_locked('alice')

    service._login_failures['alice'].locked_until = 1
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr('backend.app.services.auth_service.time.time', lambda: 2)
        service._ensure_login_not_locked('alice')
    service._ensure_login_not_locked('alice')
    assert 'alice' not in service._login_failures

    service._login_failures['alice'] = FailedLoginState(failed_attempts=1)
    service._reset_login_failures('alice')
    assert 'alice' not in service._login_failures

    service._ready_error = 'startup-bad'
    with pytest.raises(HTTPException, match='startup-bad'):
        service._ensure_ready()

    with pytest.raises(HTTPException, match='Username is required'):
        service._validate_username('   ')
    with pytest.raises(HTTPException, match='Username must be 3-32 characters'):
        service._validate_username('bad user')

    with pytest.raises(HTTPException, match=f'at least {MIN_PASSWORD_LENGTH}'):
        service._validate_password('short')
    with pytest.raises(HTTPException, match=f'at most {MAX_PASSWORD_LENGTH}'):
        service._validate_password('x' * (MAX_PASSWORD_LENGTH + 1))

    assert service._normalize_display_name('  Alice Example  ', 'alice') == 'Alice Example'
    assert service._normalize_display_name(None, 'alice') == 'alice'


def test_auth_helpers_cover_password_and_captcha_utilities():
    encoded = hash_password('secret-pass')
    assert verify_password('secret-pass', encoded) is True
    assert verify_password('secret-pass', 'bad') is False
    assert verify_password('secret-pass', encoded.replace('pbkdf2_sha256', 'bcrypt')) is False
    assert verify_password('secret-pass', encoded.replace('$600000$', '$bad$')) is False

    svg = render_captcha_svg('ABCD')
    assert "<svg" in svg
    assert 'ABCD'[0] in svg
