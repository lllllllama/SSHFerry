"""Runtime configuration for backend deployment modes and auth settings."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

from src.shared.runtime_paths import backend_runtime_dir, backend_workspace_root


DEFAULT_ALLOWED_ORIGINS = (
    'http://127.0.0.1:5173',
    'http://localhost:5173',
    'http://127.0.0.1:4173',
    'http://localhost:4173',
    'http://127.0.0.1:3000',
    'http://localhost:3000',
)
RUNTIME_MODES = {'local-dev', 'deployed-web'}


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    return int(raw)


def _parse_runtime_mode() -> str:
    mode = os.getenv('SSHFERRY_RUNTIME_MODE', 'local-dev').strip().lower()
    if mode not in RUNTIME_MODES:
        raise RuntimeError(
            f'Unsupported SSHFERRY_RUNTIME_MODE={mode!r}. Expected one of: {", ".join(sorted(RUNTIME_MODES))}.'
        )
    return mode


def _public_origin(public_base_url: str | None) -> str | None:
    if not public_base_url:
        return None
    parsed = urlparse(public_base_url)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(
            'SSHFERRY_PUBLIC_BASE_URL must include scheme and host, for example https://sshferry.example.com.'
        )
    return f'{parsed.scheme}://{parsed.netloc}'


@dataclass(slots=True, frozen=True)
class RuntimeSettings:
    """Resolved backend runtime settings."""

    runtime_mode: str
    allowed_origins: tuple[str, ...]
    allow_credentials: bool
    access_cookie_name: str
    refresh_cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    workspace_root: Path
    public_base_url: str | None
    owner_file: Path
    users_file: Path
    owner_username: str | None
    owner_display_name: str | None
    owner_password: str | None
    owner_password_hash: str | None
    auth_secret: str | None
    local_dev_auto_login: bool
    legacy_local_token_enabled: bool
    login_rate_limit_window_seconds: int
    login_rate_limit_max_attempts: int
    login_lockout_seconds: int
    login_lockout_max_failures: int
    refresh_rate_limit_window_seconds: int
    refresh_rate_limit_max_attempts: int

    @property
    def is_deployed_web(self) -> bool:
        return self.runtime_mode == 'deployed-web'

    @property
    def auth_mode(self) -> str:
        return 'cookie-session' if self.is_deployed_web else 'local-dev-cookie'


def build_runtime_settings() -> RuntimeSettings:
    """Resolve environment-based runtime settings."""
    runtime_mode = _parse_runtime_mode()
    public_base_url = os.getenv('SSHFERRY_PUBLIC_BASE_URL', '').strip() or None
    public_origin = _public_origin(public_base_url)

    configured_origins = os.getenv('SSHFERRY_ALLOWED_ORIGINS', '').strip()
    if configured_origins:
        allowed_origins = tuple(item.strip() for item in configured_origins.split(',') if item.strip())
    else:
        allowed_origin_items = list(DEFAULT_ALLOWED_ORIGINS)
        if public_origin and public_origin not in allowed_origin_items:
            allowed_origin_items.append(public_origin)
        if runtime_mode == 'local-dev':
            allowed_origin_items.append('null')
        allowed_origins = tuple(allowed_origin_items)

    workspace_root_raw = os.getenv('SSHFERRY_WORKSPACE_ROOT', '').strip()
    workspace_root = Path(workspace_root_raw).expanduser() if workspace_root_raw else backend_workspace_root()

    owner_file_raw = os.getenv('SSHFERRY_OWNER_FILE', '').strip()
    owner_file = (
        Path(owner_file_raw).expanduser()
        if owner_file_raw
        else backend_runtime_dir() / 'auth' / 'owner.json'
    )
    users_file_raw = os.getenv('SSHFERRY_USERS_FILE', '').strip()
    users_file = Path(users_file_raw).expanduser() if users_file_raw else owner_file.parent / 'users.json'

    cookie_secure_default = False
    if public_origin:
        cookie_secure_default = urlparse(public_origin).scheme == 'https'
    cookie_secure = _get_bool('SSHFERRY_AUTH_COOKIE_SECURE', cookie_secure_default)
    cookie_samesite = os.getenv('SSHFERRY_AUTH_COOKIE_SAMESITE', 'lax').strip().lower() or 'lax'
    if cookie_samesite not in {'lax', 'strict', 'none'}:
        raise RuntimeError("SSHFERRY_AUTH_COOKIE_SAMESITE must be one of: lax, strict, none.")
    if cookie_samesite == 'none' and not cookie_secure:
        raise RuntimeError("SSHFERRY_AUTH_COOKIE_SAMESITE='none' requires SSHFERRY_AUTH_COOKIE_SECURE=true.")

    return RuntimeSettings(
        runtime_mode=runtime_mode,
        allowed_origins=allowed_origins,
        allow_credentials=True,
        access_cookie_name=os.getenv('SSHFERRY_ACCESS_COOKIE_NAME', 'sshferry_access_token').strip()
        or 'sshferry_access_token',
        refresh_cookie_name=os.getenv('SSHFERRY_REFRESH_COOKIE_NAME', 'sshferry_refresh_token').strip()
        or 'sshferry_refresh_token',
        cookie_secure=cookie_secure,
        cookie_samesite=cookie_samesite,
        access_token_ttl_seconds=_get_int('SSHFERRY_ACCESS_TOKEN_TTL_SECONDS', 15 * 60),
        refresh_token_ttl_seconds=_get_int('SSHFERRY_REFRESH_TOKEN_TTL_SECONDS', 7 * 24 * 60 * 60),
        workspace_root=workspace_root,
        public_base_url=public_base_url,
        owner_file=owner_file,
        users_file=users_file,
        owner_username=os.getenv('SSHFERRY_OWNER_USERNAME', '').strip() or None,
        owner_display_name=os.getenv('SSHFERRY_OWNER_DISPLAY_NAME', '').strip() or None,
        owner_password=os.getenv('SSHFERRY_OWNER_PASSWORD', '') or None,
        owner_password_hash=os.getenv('SSHFERRY_OWNER_PASSWORD_HASH', '').strip() or None,
        auth_secret=os.getenv('SSHFERRY_AUTH_SECRET', '').strip() or None,
        local_dev_auto_login=_get_bool('SSHFERRY_LOCAL_DEV_AUTO_LOGIN', runtime_mode == 'local-dev'),
        legacy_local_token_enabled=_get_bool('SSHFERRY_ENABLE_LOCAL_LEGACY_AUTH', runtime_mode == 'local-dev'),
        login_rate_limit_window_seconds=_get_int('SSHFERRY_LOGIN_RATE_LIMIT_WINDOW_SECONDS', 60),
        login_rate_limit_max_attempts=_get_int('SSHFERRY_LOGIN_RATE_LIMIT_MAX_ATTEMPTS', 10),
        login_lockout_seconds=_get_int('SSHFERRY_LOGIN_LOCKOUT_SECONDS', 10 * 60),
        login_lockout_max_failures=_get_int('SSHFERRY_LOGIN_LOCKOUT_MAX_FAILURES', 5),
        refresh_rate_limit_window_seconds=_get_int('SSHFERRY_REFRESH_RATE_LIMIT_WINDOW_SECONDS', 60),
        refresh_rate_limit_max_attempts=_get_int('SSHFERRY_REFRESH_RATE_LIMIT_MAX_ATTEMPTS', 20),
    )
