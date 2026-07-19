from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opportunity_os.dashboard.app import DashboardDependencies, create_app
from opportunity_os.dashboard.auth import CsrfGuard, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.conversations import (
    MAX_MESSAGE_BYTES,
    ConversationRequest,
    ConversationResult,
    ConversationService,
    HermesConversationAdapter,
    OpenClawConversationAdapter,
    normalize_session_id,
)
from opportunity_os.dashboard.events import EventHub
from opportunity_os.dashboard.probes import CommandResult, CommandRunner, OPENCLAW_EXECUTABLE_PATH
from opportunity_os.dashboard.schemas import DashboardSnapshot


@dataclass
class FakeRunner:
    result: CommandResult = field(
        default_factory=lambda: CommandResult(
            exit_code=0,
            stdout='{"final":"ok"}',
            stderr="",
            timed_out=False,
            duration_ms=12,
        )
    )
    calls: list[tuple[tuple[str, ...], float]] = field(default_factory=list)

    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append((argv, timeout))
        return self.result


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


def test_openclaw_adapter_uses_fixed_gateway_agent_command(fake_runner: FakeRunner) -> None:
    adapter = OpenClawConversationAdapter(
        fake_runner, openclaw_path="/opt/homebrew/bin/openclaw"
    )

    adapter.send("dashboard-main", "Hermes 状态")

    assert fake_runner.calls == [
        (
            (
                "/opt/homebrew/bin/openclaw",
                "agent",
                "--session-id",
                "dashboard-main",
                "--message",
                "Hermes 状态",
                "--timeout",
                "600",
                "--json",
            ),
            600,
        )
    ]
    assert "--deliver" not in fake_runner.calls[0][0]


def test_hermes_adapter_uses_exact_quiet_profile_skill_command(fake_runner: FakeRunner) -> None:
    HermesConversationAdapter(fake_runner).send("research", "分析端侧 Agent")

    argv, timeout = fake_runner.calls[0]
    assert argv == (
        "hermes",
        "-p",
        "opportunity-discovery",
        "chat",
        "-Q",
        "-q",
        "分析端侧 Agent",
        "--source",
        "tool",
        "--skills",
        "opportunity-discovery",
    )
    assert timeout == 1_500
    assert "--yolo" not in argv
    assert "--deliver" not in argv


def test_absolute_openclaw_executable_still_gets_fixed_node_path(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        observed.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    CommandRunner().run(("/opt/homebrew/bin/openclaw", "agent", "--json"), 1)

    assert observed["shell"] is False
    assert observed["env"]["PATH"] == OPENCLAW_EXECUTABLE_PATH


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (" Dashboard/Main .. ", "dashboard-main"),
        ("RESEARCH___2026", "research___2026"),
        ("a" * 80, "a" * 64),
    ],
)
def test_session_ids_are_normalized(candidate: str, expected: str) -> None:
    assert normalize_session_id(candidate) == expected


@pytest.mark.parametrize("candidate", ["", "   ", "../../", "研究会话"])
def test_session_ids_without_safe_characters_are_rejected(candidate: str) -> None:
    with pytest.raises(ValueError, match="session_id"):
        normalize_session_id(candidate)


def test_adapter_normalizes_session_before_command(fake_runner: FakeRunner) -> None:
    result = OpenClawConversationAdapter(fake_runner).send(" Dashboard/Main ", "status")

    assert result.session_id == "dashboard-main"
    assert fake_runner.calls[0][0][3] == "dashboard-main"


def test_messages_are_bounded_by_utf8_bytes(fake_runner: FakeRunner) -> None:
    adapter = OpenClawConversationAdapter(fake_runner)
    adapter.send("main", "a" * MAX_MESSAGE_BYTES)

    with pytest.raises(ValueError, match="8192"):
        adapter.send("main", "界" * ((MAX_MESSAGE_BYTES // 3) + 1))


def test_openclaw_json_is_parsed_and_final_text_is_sanitized(fake_runner: FakeRunner) -> None:
    fake_runner.result = CommandResult(
        exit_code=0,
        stdout=json.dumps(
            {
                "result": {
                    "text": "Authorization: Bearer sk-private-value",
                    "provider": "openrouter",
                    "model": "model-safe",
                    "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
                    "cost_status": "unknown",
                }
            }
        ),
        stderr="raw provider stderr with api_key=never-return-this",
        timed_out=False,
        duration_ms=31,
    )

    result = OpenClawConversationAdapter(fake_runner).send("main", "status")
    payload = result.model_dump(mode="json")

    assert payload == {
        "session_id": "main",
        "final_text": "[REDACTED]",
        "provider": "openrouter",
        "model": "model-safe",
        "token_status": "reported",
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
        "cost_status": "unknown",
        "exit_code": 0,
        "duration_ms": 31,
        "error_code": None,
    }
    assert "stderr" not in payload
    assert "never-return-this" not in repr(result)


def test_invalid_json_and_nonzero_exit_return_safe_failure_without_stderr(
    fake_runner: FakeRunner,
) -> None:
    fake_runner.result = CommandResult(
        exit_code=2,
        stdout="not-json",
        stderr="Authorization: Bearer secret-error",
        timed_out=False,
        duration_ms=9,
    )

    result = OpenClawConversationAdapter(fake_runner).send("main", "status")

    assert result.final_text == ""
    assert result.exit_code == 2
    assert result.error_code == "command_failed"
    assert result.token_status == "unknown"
    assert result.cost_status == "unknown"
    assert "secret-error" not in repr(result)


@pytest.mark.parametrize(
    ("adapter_factory", "timeout"),
    [
        (lambda runner: OpenClawConversationAdapter(runner), 600),
        (lambda runner: HermesConversationAdapter(runner), 1_500),
    ],
)
def test_timeout_is_a_safe_result_without_partial_output(
    fake_runner: FakeRunner, adapter_factory, timeout: int
) -> None:
    fake_runner.result = CommandResult(
        exit_code=None,
        stdout='{"final":"partial private reasoning"}',
        stderr="private traceback",
        timed_out=True,
        duration_ms=timeout * 1_000,
    )

    result = adapter_factory(fake_runner).send("main", "status")

    assert result.error_code == "timeout"
    assert result.final_text == ""
    assert result.exit_code is None
    assert fake_runner.calls[0][1] == timeout
    assert "private" not in repr(result)


class StubAdapter:
    def __init__(self, target: str) -> None:
        self.target = target
        self.calls: list[tuple[str, str]] = []

    def send(self, session_id: str, message: str) -> ConversationResult:
        self.calls.append((session_id, message))
        return ConversationResult(
            session_id=normalize_session_id(session_id),
            final_text=f"{self.target} final",
            provider="fixture-provider",
            model="fixture-model",
            token_status="unknown",
            cost_status="unknown",
            exit_code=0,
            duration_ms=7,
        )


def _wait_for_terminal(service: ConversationService, task_id: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        task = service.get(task_id)
        if task.status in {"succeeded", "failed"}:
            return task
        time.sleep(0.01)
    raise AssertionError("conversation task did not finish")


def test_service_streams_metadata_lifecycle_and_persists_only_session_metadata(
    tmp_path: Path,
) -> None:
    hub = EventHub(tmp_path / "event-cursor")
    openclaw = StubAdapter("openclaw")
    hermes = StubAdapter("hermes")
    sessions_path = tmp_path / "sessions.json"
    service = ConversationService(
        openclaw=openclaw,
        hermes=hermes,
        event_hub=hub,
        sessions_path=sessions_path,
    )

    task_id = service.submit(
        ConversationRequest(
            target="hermes", session_id=" Research/Main ", message="private question"
        )
    )
    task = _wait_for_terminal(service, task_id)

    assert task.status == "succeeded"
    assert task.result is not None
    assert task.result.final_text == "hermes final"
    events = hub.replay(None)
    assert [(item.type, dict(item.payload)) for item in events] == [
        ("conversation.started", {"task_id": task_id, "target": "hermes"}),
        ("conversation.completed", {"task_id": task_id, "target": "hermes"}),
    ]
    persisted = sessions_path.read_text(encoding="utf-8")
    assert json.loads(persisted)["sessions"]["research-main"]["provider"] == "fixture-provider"
    assert "private question" not in persisted
    assert "hermes final" not in persisted
    assert "reasoning" not in persisted.casefold()
    assert "credential" not in persisted.casefold()


def test_service_failure_event_contains_no_raw_stderr(tmp_path: Path) -> None:
    class FailingAdapter:
        def send(self, session_id: str, message: str) -> ConversationResult:
            return ConversationResult(
                session_id=normalize_session_id(session_id),
                final_text="",
                token_status="unknown",
                cost_status="unknown",
                exit_code=1,
                duration_ms=4,
                error_code="command_failed",
            )

    hub = EventHub(tmp_path / "event-cursor")
    service = ConversationService(
        openclaw=FailingAdapter(),
        hermes=FailingAdapter(),
        event_hub=hub,
        sessions_path=tmp_path / "sessions.json",
    )

    task_id = service.submit(
        ConversationRequest(target="openclaw", session_id="main", message="status")
    )
    task = _wait_for_terminal(service, task_id)

    assert task.status == "failed"
    assert [(item.type, dict(item.payload)) for item in hub.replay(None)] == [
        ("conversation.started", {"task_id": task_id, "target": "openclaw"}),
        ("conversation.failed", {"task_id": task_id, "target": "openclaw"}),
    ]
    assert "stderr" not in json.dumps(task.model_dump(mode="json"))


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


def test_authenticated_api_submits_and_reads_conversation_task(tmp_path: Path) -> None:
    sessions = SessionStore(tmp_path / "dashboard")
    hub = EventHub(tmp_path / "event-cursor")
    service = ConversationService(
        openclaw=StubAdapter("openclaw"),
        hermes=StubAdapter("hermes"),
        event_hub=hub,
        sessions_path=tmp_path / "sessions.json",
    )
    app = create_app(
        DashboardConfig(dashboard_home=tmp_path / "dashboard"),
        DashboardDependencies(
            read_model=FakeReadModel(),
            sessions=sessions,
            csrf=CsrfGuard(),
            event_hub=hub,
            conversation_service=service,
        ),
    )
    client = TestClient(
        app,
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 51000),
    )
    bootstrap = sessions.create_bootstrap()
    exchange = client.post("/auth/local/exchange", json={"token": bootstrap})
    csrf = exchange.json()["csrf_token"]

    unauthenticated = TestClient(
        app,
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 51001),
    )
    assert unauthenticated.post(
        "/api/v1/conversations",
        json={"target": "openclaw", "session_id": "main", "message": "status"},
        headers={"origin": "http://127.0.0.1:8765"},
    ).status_code == 401

    response = client.post(
        "/api/v1/conversations",
        json={"target": "openclaw", "session_id": "main", "message": "status"},
        headers={
            "origin": "http://127.0.0.1:8765",
            "x-csrf-token": csrf,
        },
    )

    assert response.status_code == 202
    task_id = response.json()["task_id"]
    _wait_for_terminal(service, task_id)
    task_response = client.get(f"/api/v1/conversations/{task_id}")
    assert task_response.status_code == 200
    assert task_response.json()["result"]["final_text"] == "openclaw final"
    assert "message" not in task_response.text
    assert "stderr" not in task_response.text


def test_api_rejects_oversized_message_before_submission(tmp_path: Path) -> None:
    sessions = SessionStore(tmp_path / "dashboard")
    hub = EventHub(tmp_path / "event-cursor")
    service = ConversationService(
        openclaw=StubAdapter("openclaw"),
        hermes=StubAdapter("hermes"),
        event_hub=hub,
        sessions_path=tmp_path / "sessions.json",
    )
    app = create_app(
        DashboardConfig(dashboard_home=tmp_path / "dashboard"),
        DashboardDependencies(
            read_model=FakeReadModel(),
            sessions=sessions,
            csrf=CsrfGuard(),
            event_hub=hub,
            conversation_service=service,
        ),
    )
    client = TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 51000))
    exchange = client.post(
        "/auth/local/exchange", json={"token": sessions.create_bootstrap()}
    )

    response = client.post(
        "/api/v1/conversations",
        json={"target": "hermes", "session_id": "main", "message": "界" * 3_000},
        headers={
            "origin": "http://127.0.0.1:8765",
            "x-csrf-token": exchange.json()["csrf_token"],
        },
    )

    assert response.status_code == 422
    assert service.tasks == {}
