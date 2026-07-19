from datetime import datetime, timezone

from fastapi.testclient import TestClient

from opportunity_os.dashboard.app import DashboardDependencies, create_app
from opportunity_os.dashboard.auth import CsrfGuard, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.schemas import DashboardSnapshot


class ReadModel:
    def snapshot(self):
        return DashboardSnapshot(
            generated_at=datetime(2026, 7, 19, tzinfo=timezone.utc), components=[],
            opportunity_counts={"opportunities": 0, "experiments": 0, "reviews": 0, "tech_states": 0},
            portfolio_counts={"observe": 0, "validate": 0, "active": 0},
            portfolio_capacity={"observe": 5, "validate": 2, "active": 1},
            latest_review_at=None, overdue_tech_states=0, pending_approvals=0, active_incidents=0,
        )


def _client(tmp_path):
    sessions = SessionStore(tmp_path / "dashboard")
    config = DashboardConfig(dashboard_home=tmp_path / "dashboard")
    app = create_app(config, DashboardDependencies(ReadModel(), sessions, CsrfGuard()))
    client = TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 5000))
    response = client.post("/auth/local/exchange", json={"token": sessions.create_bootstrap()})
    assert response.status_code == 200
    return client


def test_dashboard_is_read_only_and_links_native_controls(tmp_path) -> None:
    client = _client(tmp_path)
    tools = client.get("/api/v1/native-tools")
    assert tools.status_code == 200
    assert tools.json()["openclaw"]["url"] == "http://127.0.0.1:18789/"
    assert "hermes -p opportunity-discovery dashboard" == tools.json()["hermes"]["command"]
    for path in (
        "/api/v1/conversations", "/api/v1/approvals/anything/apply",
        "/api/v1/tasks/job-1/changes/preview", "/api/v1/tasks/job-1/run-now/preview",
    ):
        assert client.post(path, json={}).status_code in {403, 404, 405}


def test_dashboard_keeps_auth_boundary_and_no_framework_docs(tmp_path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/v1/status").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/healthz", headers={"host": "attacker.example"}).status_code == 400
