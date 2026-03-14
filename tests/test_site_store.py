"""Tests for persistent site storage behavior."""
import json

from src.services.site_store import SiteStore
from src.shared.models import SiteConfig


def test_save_does_not_persist_password_by_default(tmp_path):
    path = tmp_path / "sites.json"
    store = SiteStore(path=path)
    site = SiteConfig(
        name="demo",
        host="example.com",
        port=22,
        username="alice",
        auth_method="password",
        password="top-secret",
        remote_root="/work",
    )

    store.save([site])

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "password" not in raw[0]
    assert raw[0]["remember_password"] is False


def test_save_persists_password_when_explicitly_enabled(tmp_path):
    path = tmp_path / "sites.json"
    store = SiteStore(path=path)
    site = SiteConfig(
        name="demo",
        host="example.com",
        port=22,
        username="alice",
        auth_method="password",
        password="top-secret",
        remote_root="/work",
        remember_password=True,
    )

    store.save([site])

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw[0]["password"] == "top-secret"
    assert raw[0]["remember_password"] is True

    loaded = store.load()
    assert loaded[0].password == "top-secret"
    assert loaded[0].remember_password is True


def test_load_defaults_empty_remote_root_to_slash(tmp_path):
    path = tmp_path / "sites.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "demo",
                    "host": "example.com",
                    "port": 22,
                    "username": "alice",
                    "auth_method": "password",
                    "remote_root": "",
                }
            ]
        ),
        encoding="utf-8",
    )

    store = SiteStore(path=path)
    loaded = store.load()

    assert len(loaded) == 1
    assert loaded[0].remote_root == "/"


def test_default_transfer_protocol_persisted_and_backward_compatible(tmp_path):
    path = tmp_path / "sites.json"
    store = SiteStore(path=path)
    site = SiteConfig(
        name="demo",
        host="example.com",
        port=22,
        username="alice",
        auth_method="password",
        remote_root="/work",
        default_transfer_protocol="scp",
    )
    store.save([site])

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].default_transfer_protocol == "scp"

    # Backward compatibility: missing key defaults to sftp
    path.write_text(
        json.dumps(
            [
                {
                    "name": "legacy",
                    "host": "old.example.com",
                    "port": 22,
                    "username": "bob",
                    "auth_method": "password",
                    "remote_root": "/",
                }
            ]
        ),
        encoding="utf-8",
    )
    loaded_legacy = store.load()
    assert loaded_legacy[0].default_transfer_protocol == "sftp"
