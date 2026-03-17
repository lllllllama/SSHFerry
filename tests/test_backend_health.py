"""Tests for the FastAPI backend skeleton."""
from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint_reports_backend_status():
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["service"] == "sshferry-backend"
    assert payload["session_count"] == 0
    if payload["ready"]:
        assert payload["status"] == "ok"
        assert payload["scheduler_running"] is True
        assert payload["startup_error"] is None
    else:
        assert payload["status"] == "degraded"
        assert payload["scheduler_running"] is False
        assert payload["startup_error"]
