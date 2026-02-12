"""Tests for persistent site storage behavior."""
import json

from src.services.site_store import SiteStore
from src.shared.models import SiteConfig


def test_save_does_not_persist_runtime_password(tmp_path):
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
