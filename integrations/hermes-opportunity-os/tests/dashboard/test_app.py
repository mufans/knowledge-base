from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opportunity_os.dashboard.app import DashboardDependencies, create_app
from opportunity_os.dashboard.auth import CsrfGuard, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
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
def client(config: DashboardConfig, sessions: SessionStore) -> TestClient:
    dependencies = DashboardDependencies(read_model=FakeReadModel(), sessions=sessions, csrf=CsrfGuard())
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
