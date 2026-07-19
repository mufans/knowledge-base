from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opportunity_os.dashboard.app import DashboardDependencies, create_app
from opportunity_os.dashboard.auth import CsrfGuard, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.events import DashboardEvent, EventHub
from opportunity_os.dashboard.schemas import DashboardSnapshot


class FakeReadModel:
    def snapshot(self) -> DashboardSnapshot:
        return DashboardSnapshot(
            generated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            components=[],
            opportunity_counts={"opportunities": 0, "experiments": 0, "reviews": 0, "tech_states": 0},
            portfolio_counts={"observe": 0, "validate": 0, "active": 0},
            portfolio_capacity={"observe": 5, "validate": 2, "active": 1},
            latest_review_at=None,
            overdue_tech_states=0,
            pending_approvals=0,
            active_incidents=0,
        )


@pytest.fixture
def sessions(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "dashboard")


@pytest.fixture
def config(tmp_path: Path) -> DashboardConfig:
    return DashboardConfig(
        dashboard_home=tmp_path / "dashboard",
        remote_host="assigned.ngrok-free.app",
        origin_credential="origin-secret-for-tests",
    )


@pytest.fixture
def event_hub(tmp_path: Path) -> EventHub:
    return EventHub(tmp_path / "dashboard" / "event-cursor")


@pytest.fixture
def client(config: DashboardConfig, sessions: SessionStore, event_hub: EventHub) -> TestClient:
    dependencies = DashboardDependencies(
        read_model=FakeReadModel(), sessions=sessions, csrf=CsrfGuard(), event_hub=event_hub
    )
    return TestClient(
        create_app(config, dependencies),
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 51000),
    )


@pytest.fixture
def authenticated_client(client: TestClient, sessions: SessionStore) -> tuple[TestClient, str]:
    bootstrap = sessions.create_bootstrap()
    response = client.post("/auth/local/exchange", json={"token": bootstrap})
    assert response.status_code == 200
    return client, response.json()["csrf_token"]


def test_rejected_host_fails_closed(client: TestClient) -> None:
    response = client.get("/healthz", headers={"host": "attacker.example"})

    assert response.status_code == 400


@pytest.mark.parametrize("host", ["user@assigned.ngrok-free.app", "assigned.ngrok-free.app/path"])
def test_malformed_allowed_host_is_still_rejected(client: TestClient, host: str) -> None:
    response = client.get(
        "/api/v1/status",
        headers={"host": host, "x-dashboard-origin-credential": "origin-secret-for-tests"},
    )

    assert response.status_code == 400


def test_remote_request_requires_origin_credential(client: TestClient) -> None:
    response = client.get("/api/v1/status", headers={"host": "assigned.ngrok-free.app"})

    assert response.status_code == 401


def test_remote_request_rejects_wrong_origin(client: TestClient) -> None:
    response = client.get(
        "/api/v1/status",
        headers={
            "host": "assigned.ngrok-free.app",
            "origin": "https://attacker.example",
            "x-dashboard-origin-credential": "origin-secret-for-tests",
        },
    )

    assert response.status_code == 403


def test_malformed_origin_fails_closed(client: TestClient) -> None:
    response = client.get(
        "/api/v1/status",
        headers={"origin": "http://127.0.0.1:not-a-port"},
    )

    assert response.status_code == 403


def test_remote_origin_credential_creates_twelve_hour_session(client: TestClient) -> None:
    response = client.get(
        "/api/v1/status",
        headers={
            "host": "assigned.ngrok-free.app",
            "origin": "https://assigned.ngrok-free.app",
            "x-dashboard-origin-credential": "origin-secret-for-tests",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert response.headers["x-csrf-token"]


def test_successful_loopback_bootstrap_exchange_sets_strict_cookie(
    client: TestClient, sessions: SessionStore
) -> None:
    bootstrap = sessions.create_bootstrap()

    response = client.post("/auth/local/exchange", json={"token": bootstrap})

    assert response.status_code == 200
    assert response.json()["kind"] == "local"
    assert response.json()["csrf_token"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.get("/api/v1/status").status_code == 200


def test_local_exchange_is_rejected_through_remote_host(client: TestClient, sessions: SessionStore) -> None:
    response = client.post(
        "/auth/local/exchange",
        json={"token": sessions.create_bootstrap()},
        headers={
            "host": "assigned.ngrok-free.app",
            "origin": "https://assigned.ngrok-free.app",
            "x-dashboard-origin-credential": "origin-secret-for-tests",
        },
    )

    assert response.status_code == 403


def test_local_exchange_requires_loopback_peer(config: DashboardConfig, sessions: SessionStore) -> None:
    dependencies = DashboardDependencies(read_model=FakeReadModel(), sessions=sessions, csrf=CsrfGuard())
    remote_peer = TestClient(
        create_app(config, dependencies),
        base_url="http://127.0.0.1:8765",
        client=("203.0.113.5", 51000),
    )

    response = remote_peer.post(
        "/auth/local/exchange",
        json={"token": sessions.create_bootstrap()},
    )

    assert response.status_code == 403


def test_mutation_requires_csrf(authenticated_client: tuple[TestClient, str]) -> None:
    client, _ = authenticated_client
    response = client.post(
        "/api/v1/session/refresh",
        json={},
        headers={"origin": "http://127.0.0.1:8765"},
    )

    assert response.status_code == 403


def test_mutation_rejects_missing_origin_even_with_csrf(authenticated_client: tuple[TestClient, str]) -> None:
    client, csrf_token = authenticated_client
    response = client.post(
        "/api/v1/session/refresh",
        json={},
        headers={"x-csrf-token": csrf_token},
    )

    assert response.status_code == 403


def test_session_refresh_accepts_same_origin_and_csrf(authenticated_client: tuple[TestClient, str]) -> None:
    client, csrf_token = authenticated_client
    response = client.post(
        "/api/v1/session/refresh",
        json={},
        headers={"origin": "http://127.0.0.1:8765", "x-csrf-token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json()["csrf_token"] == csrf_token


def test_get_cannot_refresh_session(authenticated_client: tuple[TestClient, str]) -> None:
    client, csrf_token = authenticated_client
    response = client.get("/api/v1/session/refresh", headers={"x-csrf-token": csrf_token})

    assert response.status_code == 405


def test_framework_docs_are_not_anonymous_routes(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_sse_requires_an_authenticated_session(client: TestClient) -> None:
    assert client.get("/api/v1/events").status_code == 401


def test_sse_honors_last_event_id_and_emits_metadata_only(
    config: DashboardConfig, sessions: SessionStore
) -> None:
    class FiniteHub:
        requested_cursor: str | None = None

        async def subscribe(self, last_event_id: str | None):
            self.requested_cursor = last_event_id
            yield DashboardEvent(
                id="42",
                type="incident.firing",
                payload={"incident_id": "inc-1"},
                at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )

    hub = FiniteHub()
    dependencies = DashboardDependencies(
        read_model=FakeReadModel(), sessions=sessions, csrf=CsrfGuard(), event_hub=hub
    )
    streaming_client = TestClient(
        create_app(config, dependencies),
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 51000),
    )
    bootstrap = sessions.create_bootstrap()
    assert streaming_client.post("/auth/local/exchange", json={"token": bootstrap}).status_code == 200

    response = streaming_client.get("/api/v1/events", headers={"Last-Event-ID": "41"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert hub.requested_cursor == "41"
    assert "id: 42" in response.text
    assert "event: incident.firing" in response.text
    data = json.loads(re.search(r"^data: (.+)$", response.text, re.MULTILINE).group(1))
    assert data == {
        "at": "2026-07-19T00:00:00+00:00",
        "event_id": "42",
        "incident_id": "inc-1",
        "type": "incident.firing",
    }


def test_sse_heartbeat_interval_is_twenty_seconds() -> None:
    from opportunity_os.dashboard import app as app_module

    assert app_module.SSE_HEARTBEAT_SECONDS == 20


def test_initial_html_contains_no_private_snapshot_data(
    authenticated_client: tuple[TestClient, str],
) -> None:
    client, _ = authenticated_client

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "private-weekly-review" not in response.text
    assert "opportunity_counts" not in response.text
    assert "window.__" not in response.text


@pytest.mark.parametrize(
    "route",
    [
        "overview",
        "conversations",
        "signals",
        "opportunities",
        "tasks",
        "approvals",
        "reports",
        "monitoring",
    ],
)
def test_all_eight_pages_have_keyboard_accessible_navigation(
    authenticated_client: tuple[TestClient, str], route: str
) -> None:
    client, _ = authenticated_client
    html = client.get("/").text

    assert f'href="#{route}"' in html
    assert f'data-route="{route}"' in html
    assert "<nav" in html
    assert 'aria-label="主导航"' in html
    assert 'id="main-content"' in html
    assert 'tabindex="-1"' in html


def test_ui_renderers_cover_all_pages_and_runtime_states_without_errors() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the vanilla UI smoke test")
    app_js = Path(__file__).parents[2] / "src" / "opportunity_os" / "dashboard" / "static" / "app.js"
    runner = """
import fs from 'node:fs';
const source = fs.readFileSync(process.argv[1], 'utf8');
const module = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const renderers = [
  module.renderOverview, module.renderConversations, module.renderSignals,
  module.renderOpportunities, module.renderTasks, module.renderApprovals,
  module.renderReports, module.renderMonitoring,
];
const states = ['empty', 'healthy', 'degraded', 'disconnected'];
const output = renderers.flatMap(renderer => states.map(state => renderer({}, state)));
if (output.length !== 32 || output.some(html => typeof html !== 'string' || !html.includes('data-state='))) {
  throw new Error('renderer smoke check failed');
}
console.log(JSON.stringify({renderers: renderers.length, states: states.length, pages: output.length}));
"""

    result = subprocess.run(
        [node, "--input-type=module", "-e", runner, str(app_js)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"renderers": 8, "states": 4, "pages": 32}


def test_browser_reconnects_with_backoff_and_refetches_after_events() -> None:
    app_js = (
        Path(__file__).parents[2]
        / "src"
        / "opportunity_os"
        / "dashboard"
        / "static"
        / "app.js"
    ).read_text(encoding="utf-8")

    assert "Math.min(reconnectDelay * 2" in app_js
    assert "last_event_id" in app_js
    assert 'addEventListener("component.updated"' in app_js
    assert 'addEventListener("incident.firing"' in app_js
    assert "refreshOverview" in app_js
    assert "refreshMonitoring" in app_js
