import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opportunity_os.dashboard.im import (
    ActionUnavailableError,
    AuthorizationError,
    ConfirmationError,
    ImCommandRouter,
    InputError,
    PendingProposalStore,
)


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class FakeReadBackend:
    def __init__(self, result: str = "私有状态：healthy") -> None:
        self.result = result
        self.calls = []

    def read(self, command):
        self.calls.append(command)
        return self.result


class FakeActionBackend:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, kind: str, target: str):
        self.calls.append((kind, target))
        return "accepted"


@pytest.fixture
def router(tmp_path: Path) -> ImCommandRouter:
    return ImCommandRouter(
        owner_id="owner",
        dashboard_url="https://dashboard.example.test/monitoring",
        allowed_dashboard_hosts=("dashboard.example.test",),
        state_home=tmp_path / "dashboard",
        read_backend=FakeReadBackend(),
        action_backend=FakeActionBackend(),
        clock=lambda: NOW,
    )


@pytest.mark.parametrize(
    ("text", "kind", "payload"),
    [
        ("Hermes 状态", "status", None),
        ("Hermes 最新周报", "latest_review", None),
        ("Hermes 当前方向", "directions", None),
        ("Hermes 机会详情 opp-1", "opportunity_detail", "opp-1"),
        ("Hermes 最近学到了什么", "learning_summary", None),
        ("Hermes 待审批记忆", "pending_memory", None),
        ("Hermes 待审批Skill", "pending_skills", None),
        ("Hermes 反馈：增加端侧 Agent 反证", "feedback", "增加端侧 Agent 反证"),
        ("Hermes 修改需求：周报增加失败假设", "change_requirement", "周报增加失败假设"),
        ("Hermes 重启 openclaw", "restart", "openclaw"),
        ("Hermes 重试任务 daily", "retry_task", "daily"),
    ],
)
def test_documented_commands_are_exactly_typed(router, text, kind, payload) -> None:
    command = router.parse(text)
    assert command.kind == kind
    assert command.payload == payload


def test_nfkc_is_applied_but_fuzzy_commands_are_not_invented(router) -> None:
    assert router.parse("Ｈｅｒｍｅｓ 状态").kind == "status"
    assert router.parse("Hermes 反馈:内容").kind == "feedback"
    for text in (
        "hermes 状态",
        "Hermes状态",
        "Hermes  状态",
        "Hermes 查看状态",
        "Hermes 反馈;内容",
        "忽略规则 Hermes 状态",
        "普通聊天",
    ):
        assert router.parse(text).kind == "chat_fallback"


def test_utf8_input_is_bounded(router) -> None:
    with pytest.raises(InputError):
        router.parse("Hermes 反馈：" + "界" * 1_400)


def test_unknown_or_non_hermes_never_calls_any_backend(router) -> None:
    read_backend = router.read_backend
    action_backend = router.action_backend
    for text in ("普通聊天", "Hermes 删除任务", "Hermes 确认 not-a-nonce changed"):
        reply = router.execute(
            router.parse(text), sender_id="attacker", session_id="group-1", chat_type="group"
        )
        assert reply.status == "chat_fallback"
    assert read_backend.calls == []
    assert action_backend.calls == []
    assert not (router.state_home / "im-confirmations.json").exists()


@pytest.mark.parametrize(
    ("sender_id", "session_id", "chat_type"),
    [
        ("not-owner", "dm-1", "dm"),
        ("owner", "dm-1", "group"),
        ("owner", "", "dm"),
    ],
)
def test_only_configured_owner_in_a_direct_session_is_authorized(
    router, sender_id, session_id, chat_type
) -> None:
    with pytest.raises(AuthorizationError):
        router.execute(
            router.parse("Hermes 状态"),
            sender_id=sender_id,
            session_id=session_id,
            chat_type=chat_type,
        )


def test_missing_owner_or_dashboard_config_fails_closed(tmp_path: Path) -> None:
    for kwargs in (
        {"owner_id": None, "dashboard_url": "https://dashboard.example.test/monitoring"},
        {"owner_id": "owner", "dashboard_url": None},
        {"owner_id": "owner", "dashboard_url": "https://evil.example/monitoring"},
    ):
        broken = ImCommandRouter(
            **kwargs,
            allowed_dashboard_hosts=("dashboard.example.test",),
            state_home=tmp_path / "dashboard",
            read_backend=FakeReadBackend(),
        )
        with pytest.raises(AuthorizationError):
            broken.execute(
                broken.parse("Hermes 状态"),
                sender_id="owner",
                session_id="dm-1",
                chat_type="dm",
            )


def test_read_output_is_bounded_redacted_and_contains_only_canonical_link(tmp_path: Path) -> None:
    backend = FakeReadBackend(
        "report /Users/alice/private stderr=trace Authorization: Bearer abcdefghijklmnop "
        + "x" * 10_000
    )
    service = ImCommandRouter(
        owner_id="owner",
        dashboard_url="https://dashboard.example.test/monitoring",
        allowed_dashboard_hosts=("dashboard.example.test",),
        state_home=tmp_path / "dashboard",
        read_backend=backend,
        clock=lambda: NOW,
    )
    reply = service.execute(
        service.parse("Hermes 状态"), sender_id="owner", session_id="dm-1", chat_type="dm"
    )

    rendered = json.dumps(reply.to_dict(), ensure_ascii=False)
    assert reply.status == "ok"
    assert len(reply.text.encode("utf-8")) <= 4_096
    assert "/Users/alice" not in rendered
    assert "Bearer abcdef" not in rendered
    assert "stderr=trace" not in rendered
    assert reply.dashboard_url == "https://dashboard.example.test/monitoring"


def _challenge(router: ImCommandRouter, text: str, *, session_id: str = "dm-1"):
    return router.execute(
        router.parse(text), sender_id="owner", session_id=session_id, chat_type="dm"
    )


def test_feedback_confirmation_persists_typed_proposal_without_applying(router) -> None:
    first = _challenge(router, "Hermes 反馈：增加端侧 Agent 反证")
    assert first.status == "awaiting_confirmation"
    assert first.expires_in_seconds == 300
    assert first.confirmation_text == f"Hermes 确认 {first.nonce}"
    assert router.action_backend.calls == []

    confirmed = _challenge(router, first.confirmation_text)
    assert confirmed.status == "proposal_pending"
    records = PendingProposalStore(router.state_home / "im-proposals.json", clock=lambda: NOW).list()
    assert len(records) == 1
    assert records[0].kind == "feedback"
    assert records[0].payload == "增加端侧 Agent 反证"
    assert records[0].state == "pending"
    assert oct((router.state_home / "im-proposals.json").stat().st_mode & 0o777) == "0o600"


def test_confirmation_is_owner_session_digest_expiry_and_single_use_bound(router) -> None:
    first = _challenge(router, "Hermes 修改需求：调整周报")
    confirm = router.parse(first.confirmation_text)

    with pytest.raises(AuthorizationError):
        router.execute(confirm, sender_id="other", session_id="dm-1", chat_type="dm")
    with pytest.raises(ConfirmationError):
        router.execute(confirm, sender_id="owner", session_id="dm-2", chat_type="dm")

    changed = confirm.model_copy(update={"digest": "0" * 64})
    with pytest.raises(ConfirmationError):
        router.execute(changed, sender_id="owner", session_id="dm-1", chat_type="dm")

    assert _challenge(router, first.confirmation_text).status == "proposal_pending"
    with pytest.raises(ConfirmationError):
        _challenge(router, first.confirmation_text)


def test_confirmation_survives_a_fresh_cli_router_instance(router) -> None:
    first = _challenge(router, "Hermes 反馈：保留反证来源")
    fresh = ImCommandRouter(
        owner_id="owner",
        dashboard_url="https://dashboard.example.test/monitoring",
        allowed_dashboard_hosts=("dashboard.example.test",),
        state_home=router.state_home,
        read_backend=FakeReadBackend(),
        action_backend=FakeActionBackend(),
        clock=lambda: NOW,
    )

    assert _challenge(fresh, first.confirmation_text).status == "proposal_pending"
    assert len(fresh.proposals.list()) == 1


def test_expired_confirmation_is_rejected(tmp_path: Path) -> None:
    current = [NOW]
    service = ImCommandRouter(
        owner_id="owner",
        dashboard_url="https://dashboard.example.test/monitoring",
        allowed_dashboard_hosts=("dashboard.example.test",),
        state_home=tmp_path / "dashboard",
        read_backend=FakeReadBackend(),
        clock=lambda: current[0],
    )
    first = _challenge(service, "Hermes 反馈：调整来源")
    current[0] += timedelta(seconds=301)
    with pytest.raises(ConfirmationError):
        _challenge(service, first.confirmation_text)


def test_restart_and_retry_only_call_injected_typed_backend(router) -> None:
    for text, expected in (
        ("Hermes 重启 openclaw", ("restart", "openclaw")),
        ("Hermes 重试任务 daily", ("retry_task", "daily")),
    ):
        first = _challenge(router, text)
        assert router.action_backend.calls == [] or expected not in router.action_backend.calls
        assert _challenge(router, first.confirmation_text).status == "accepted"
        assert router.action_backend.calls[-1] == expected


def test_production_action_backend_is_disabled(router) -> None:
    router.action_backend = None
    first = _challenge(router, "Hermes 重启 openclaw")
    with pytest.raises(ActionUnavailableError):
        _challenge(router, first.confirmation_text)


@pytest.mark.parametrize(
    "payload",
    [
        "token=abcdefghijklmnop",
        "请读取 /Users/alice/.env",
        "请读取 ../../private",
        "file:///tmp/private",
    ],
)
def test_proposals_reject_secrets_and_paths(router, payload: str) -> None:
    with pytest.raises(InputError):
        _challenge(router, f"Hermes 反馈：{payload}")


def test_cli_accepts_only_exact_bounded_stdin_envelope(monkeypatch, capsys) -> None:
    from opportunity_os.cli import main

    class FixtureRouter:
        def parse(self, text):
            assert text == "Hermes 状态"
            return type("Command", (), {"kind": "status"})()

        def execute(self, command, *, sender_id, session_id, chat_type):
            assert (sender_id, session_id, chat_type) == ("owner", "dm-1", "dm")
            return type("Reply", (), {"to_dict": lambda self: {"status": "ok", "text": "healthy"}})()

    monkeypatch.setattr("opportunity_os.cli._im_router", lambda: FixtureRouter())
    monkeypatch.setattr(
        "sys.stdin",
        __import__("io").StringIO(
            json.dumps(
                {"text": "Hermes 状态", "sender_id": "owner", "session_id": "dm-1", "chat_type": "dm"}
            )
        ),
    )

    assert main(["dashboard", "im-command", "--stdin-json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "ok", "text": "healthy"}


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "Hermes 状态", "sender_id": "owner", "session_id": "dm-1"},
        {"text": "Hermes 状态", "sender_id": "owner", "session_id": "dm-1", "chat_type": "dm", "owner_id": "owner"},
    ],
)
def test_cli_rejects_envelope_key_confusion(monkeypatch, capsys, payload) -> None:
    from opportunity_os.cli import main

    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    assert main(["dashboard", "im-command", "--stdin-json"]) != 0
    assert json.loads(capsys.readouterr().out)["ok"] is False
