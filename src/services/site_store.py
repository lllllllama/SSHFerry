"""Site configuration storage."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import tempfile
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.shared.runtime_paths import app_data_dir
from src.shared.models import SiteConfig

logger = logging.getLogger(__name__)

_SITE_SECRET_ENV = 'SSHFERRY_SITE_SECRET'
_LOCAL_SECRET_FILENAME = '.site_store.key'
_SECRET_FORMAT = 'fernet-v1'
_SECRET_FORMAT_FIELD = 'secret_format'
_PASSWORD_SECRET_FIELD = 'password_encrypted'
_KEY_PASSPHRASE_SECRET_FIELD = 'key_passphrase_encrypted'

_PERSIST_FIELDS = [
    'name',
    'owner_user_id',
    'host',
    'port',
    'username',
    'auth_method',
    'remote_root',
    'key_path',
    'proxy_jump',
    'ssh_config_path',
    'ssh_options',
    'default_transfer_protocol',
    'remember_password',
]


def _default_store_path() -> Path:
    """Return platform-appropriate config directory."""
    return app_data_dir() / 'sites.json'


def _atomic_write_text(path: Path, content: str, encoding: str = 'utf-8') -> None:
    """Atomically write text content to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f'.{path.name}.',
        suffix='.tmp',
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, 'w', encoding=encoding, newline='\n') as file_obj:
            file_obj.write(content)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _runtime_mode() -> str:
    return os.getenv('SSHFERRY_RUNTIME_MODE', 'local-dev').strip().lower() or 'local-dev'


class SiteSecretCipher:
    """Encrypt and decrypt persisted site secrets."""

    def __init__(self, store_path: Path, secret_key: str | None = None):
        self.store_path = store_path
        self.secret_key = (secret_key or '').strip() or None
        self._resolved_secret: str | None = None

    def encrypt(self, value: str) -> str:
        return self._fernet(allow_local_create=True).encrypt(value.encode('utf-8')).decode('utf-8')

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet(allow_local_create=False).decrypt(token.encode('utf-8')).decode('utf-8')
        except InvalidToken as exc:
            raise RuntimeError(
                'Failed to decrypt stored site secret. Check SSHFERRY_SITE_SECRET or the local site secret key file.'
            ) from exc

    def ensure_available_for_encrypted_data(self) -> None:
        self._fernet(allow_local_create=False)

    def _fernet(self, *, allow_local_create: bool) -> Fernet:
        secret = self._resolve_secret(allow_local_create=allow_local_create)
        if not secret:
            raise RuntimeError(
                'SSHFERRY_SITE_SECRET must be configured to persist or decrypt site secrets in deployed-web mode.'
            )
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest())
        return Fernet(key)

    def _resolve_secret(self, *, allow_local_create: bool) -> str | None:
        if self._resolved_secret:
            return self._resolved_secret

        env_secret = self.secret_key or os.getenv(_SITE_SECRET_ENV, '').strip()
        if env_secret:
            self._resolved_secret = env_secret
            return env_secret

        local_key_path = self.store_path.parent / _LOCAL_SECRET_FILENAME
        if _runtime_mode() != 'deployed-web':
            if local_key_path.exists():
                value = local_key_path.read_text(encoding='utf-8').strip()
                if value:
                    self._resolved_secret = value
                    return value
            if allow_local_create:
                generated = secrets.token_urlsafe(48)
                _atomic_write_text(local_key_path, generated, encoding='utf-8')
                self._resolved_secret = generated
                return generated

        return None


class SiteStore:
    """Load / save SiteConfig list from a JSON file."""

    def __init__(self, path: Optional[Path] = None, secret_key: str | None = None):
        self.path = path or _default_store_path()
        self._secret_cipher = SiteSecretCipher(self.path, secret_key=secret_key)

    def load(self) -> list[SiteConfig]:
        try:
            return self.load_or_raise()
        except Exception as exc:
            logger.error('Failed to load sites from %s: %s', self.path, exc)
            return []

    def load_or_raise(self) -> list[SiteConfig]:
        if not self.path.exists():
            return []

        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise RuntimeError(f'Site store {self.path} must contain a JSON list.')

        sites: list[SiteConfig] = []
        for item in data:
            if not isinstance(item, dict):
                raise RuntimeError(f'Site store {self.path} contains a non-object entry.')
            sites.append(self._deserialize_site(item))

        logger.info('Loaded %s sites from %s', len(sites), self.path)
        return sites

    def validate(self) -> None:
        self.load_or_raise()

    def save(self, sites: list[SiteConfig]) -> None:
        data = []
        for site in sites:
            item = {field_name: getattr(site, field_name) for field_name in _PERSIST_FIELDS}
            if site.auth_method == 'password' and site.remember_password and site.password:
                item[_SECRET_FORMAT_FIELD] = _SECRET_FORMAT
                item[_PASSWORD_SECRET_FIELD] = self._secret_cipher.encrypt(site.password)
            if site.auth_method == 'key' and site.key_passphrase:
                item[_SECRET_FORMAT_FIELD] = _SECRET_FORMAT
                item[_KEY_PASSPHRASE_SECRET_FIELD] = self._secret_cipher.encrypt(site.key_passphrase)
            data.append(item)

        payload = json.dumps(data, indent=2, ensure_ascii=False)
        _atomic_write_text(self.path, payload, encoding='utf-8')
        logger.info('Saved %s sites to %s', len(sites), self.path)

    def _deserialize_site(self, item: dict[str, object]) -> SiteConfig:
        secret_format = str(item.get(_SECRET_FORMAT_FIELD) or '').strip()
        if secret_format and secret_format != _SECRET_FORMAT:
            raise RuntimeError(f'Unsupported site secret format: {secret_format}.')

        password = self._extract_secret(item, plain_field='password', encrypted_field=_PASSWORD_SECRET_FIELD)
        key_passphrase = self._extract_secret(
            item,
            plain_field='key_passphrase',
            encrypted_field=_KEY_PASSPHRASE_SECRET_FIELD,
        )

        return SiteConfig(
            name=str(item['name']),
            owner_user_id=item.get('owner_user_id') if isinstance(item.get('owner_user_id'), str) else None,
            host=str(item['host']),
            port=int(item.get('port', 22)),
            username=str(item['username']),
            auth_method=str(item.get('auth_method', 'password')),
            remote_root=str(item.get('remote_root', '/') or '/'),
            password=password,
            key_path=item.get('key_path') if isinstance(item.get('key_path'), str) else None,
            key_passphrase=key_passphrase,
            proxy_jump=item.get('proxy_jump') if isinstance(item.get('proxy_jump'), str) else None,
            ssh_config_path=item.get('ssh_config_path') if isinstance(item.get('ssh_config_path'), str) else None,
            ssh_options=list(item.get('ssh_options', [])),
            default_transfer_protocol=str(item.get('default_transfer_protocol', 'sftp')),
            remember_password=bool(item.get('remember_password', False)),
        )

    def _extract_secret(self, item: dict[str, object], *, plain_field: str, encrypted_field: str) -> str | None:
        encrypted_value = item.get(encrypted_field)
        if isinstance(encrypted_value, str) and encrypted_value.strip():
            return self._secret_cipher.decrypt(encrypted_value)

        plain_value = item.get(plain_field)
        if isinstance(plain_value, str) and plain_value:
            return plain_value
        return None
