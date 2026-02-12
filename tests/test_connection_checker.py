"""Tests for connection checker summary helpers."""
from src.services.connection_checker import CheckResult, ConnectionChecker
from src.shared.models import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="test",
        host="localhost",
        port=22,
        username="user",
        auth_method="password",
        password="secret",
        remote_root="/tmp",
    )


def test_get_summary_uses_ascii_status_labels():
    checker = ConnectionChecker(_site())
    checker.results = [
        CheckResult(name="TCP Connection", passed=True, message="ok"),
        CheckResult(name="SSH Handshake", passed=False, message="auth failed"),
    ]

    summary = checker.get_summary()

    assert "PASS TCP Connection: ok" in summary
    assert "FAIL SSH Handshake: auth failed" in summary


def test_all_passed_matches_results():
    checker = ConnectionChecker(_site())
    checker.results = [
        CheckResult(name="a", passed=True, message="ok"),
        CheckResult(name="b", passed=True, message="ok"),
    ]
    assert checker.all_passed() is True

    checker.results.append(CheckResult(name="c", passed=False, message="bad"))
    assert checker.all_passed() is False


def test_remote_root_readable_uses_context_manager_on_error(monkeypatch):
    events: list[str] = []

    class FakeEngine:
        def __init__(self, _site_config):
            pass

        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("exit")
            return False

        def check_path_readable(self, _path: str) -> bool:
            raise RuntimeError("boom")

    monkeypatch.setattr("src.services.connection_checker.SftpEngine", FakeEngine)

    checker = ConnectionChecker(_site())
    result = checker._check_remote_root_readable()

    assert result.passed is False
    assert "boom" in result.message
    assert events == ["enter", "exit"]
