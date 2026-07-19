from __future__ import annotations

import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opportunity_os.dashboard.approvals import (
    ApprovalService,
    ConflictError,
    ExpiredError,
    IsolationError,
    StateError,
    ValidationError,
)
from opportunity_os.dashboard.audit import AuditLog


OWNER_A = "a" * 64
OWNER_B = "b" * 64
SESSION_A = "c" * 64
SESSION_B = "d" * 64


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def service(tmp_path: Path, clock: MutableClock) -> ApprovalService:
    return ApprovalService(tmp_path / "approvals.json", clock=clock)


def _preview(service: ApprovalService, patch: dict[str, object] | None = None):
    return service.preview(
        "job-1",
        patch or {"enabled": False},
        base_revision="r1",
        owner_id=OWNER_A,
        session_id=SESSION_A,
    )


def test_preview_binds_canonical_digest_and_one_time_nonce(service: ApprovalService) -> None:
    first = _preview(service, {"enabled": False})
    second = _preview(service, {"enabled": False})

    assert first.state == "awaiting_approval"
    assert first.digest == second.digest
    assert first.nonce != second.nonce
    approved = service.approve(
        first.id,
        first.digest,
        nonce=first.nonce,
        owner_id=OWNER_A,
        session_id=SESSION_A,
    )
    assert approved.state == "approved"
    with pytest.raises(StateError):
        service.approve(
            first.id,
            first.digest,
            nonce=first.nonce,
            owner_id=OWNER_A,
            session_id=SESSION_A,
        )


def test_payload_change_invalidates_approval(service: ApprovalService) -> None:
    request = _preview(service)
    approved = service.approve(
        request.id,
        request.digest,
        nonce=request.nonce,
        owner_id=OWNER_A,
        session_id=SESSION_A,
    )

    with pytest.raises(ConflictError):
        service.apply(
            approved.id,
            observed_revision="r2",
            owner_id=OWNER_A,
            session_id=SESSION_A,
        )


@pytest.mark.parametrize("field", ["message", "model", "to", "command", "delete", "token"])
def test_forbidden_task_fields_are_rejected(
    service: ApprovalService, field: str
) -> None:
    with pytest.raises(ValidationError):
        service.preview(
            "job-1",
            {field: "blocked"},
            base_revision="r1",
            owner_id=OWNER_A,
            session_id=SESSION_A,
        )


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"enabled": 1},
        {"enabled": False, "cron": "0 8 * * *"},
        {"cron": "0 8 * * *"},
        {"tz": "Asia/Shanghai"},
        {"cron": "0 8 * * *", "tz": "Asia/Shanghai", "extra": True},
    ],
)
def test_patch_shape_is_exactly_enabled_or_cron_plus_tz(
    service: ApprovalService, patch: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        service.preview(
            "job-1",
            patch,
            base_revision="r1",
            owner_id=OWNER_A,
            session_id=SESSION_A,
        )


def test_run_now_is_a_distinct_request_with_no_mutable_patch(service: ApprovalService) -> None:
    request = service.preview_run_now(
        "job-1",
        base_revision="r1",
        owner_id=OWNER_A,
        session_id=SESSION_A,
    )

    assert request.kind == "run_now"
    assert request.patch == {}
    with pytest.raises(ValidationError):
        service.preview_run_now(
            "job-1",
            base_revision="r1",
            owner_id=OWNER_A,
            session_id=SESSION_A,
            patch={"enabled": False},
        )


def test_approval_is_bound_to_both_owner_and_session(service: ApprovalService) -> None:
    request = _preview(service)

    with pytest.raises(IsolationError):
        service.approve(
            request.id,
            request.digest,
            nonce=request.nonce,
            owner_id=OWNER_B,
            session_id=SESSION_A,
        )
    with pytest.raises(IsolationError):
        service.approve(
            request.id,
            request.digest,
            nonce=request.nonce,
            owner_id=OWNER_A,
            session_id=SESSION_B,
        )


def test_nonce_expires_after_five_minutes(
    service: ApprovalService, clock: MutableClock
) -> None:
    request = _preview(service)
    clock.now += timedelta(minutes=5, microseconds=1)

    with pytest.raises(ExpiredError):
        service.approve(
            request.id,
            request.digest,
            nonce=request.nonce,
            owner_id=OWNER_A,
            session_id=SESSION_A,
        )


def test_tampering_with_persisted_patch_breaks_digest(service: ApprovalService) -> None:
    request = _preview(service)
    payload = json.loads(service.path.read_text(encoding="utf-8"))
    payload["requests"][request.id]["patch"] = {"enabled": True}
    service.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConflictError):
        service.approve(
            request.id,
            request.digest,
            nonce=request.nonce,
            owner_id=OWNER_A,
            session_id=SESSION_A,
        )


def test_apply_runs_once_and_records_terminal_state(service: ApprovalService) -> None:
    request = _preview(service)
    service.approve(
        request.id,
        request.digest,
        nonce=request.nonce,
        owner_id=OWNER_A,
        session_id=SESSION_A,
    )
    calls: list[str] = []

    applied = service.apply(
        request.id,
        observed_revision="r1",
        owner_id=OWNER_A,
        session_id=SESSION_A,
        apply_change=lambda change: calls.append(change.target),
    )

    assert applied.state == "applied"
    assert calls == ["job-1"]
    with pytest.raises(StateError):
        service.apply(
            request.id,
            observed_revision="r1",
            owner_id=OWNER_A,
            session_id=SESSION_A,
        )


def test_private_approval_store_is_atomic_mode_0600_and_bounded(
    service: ApprovalService,
) -> None:
    _preview(service)

    assert stat.S_IMODE(service.path.stat().st_mode) == 0o600
    service.path.write_bytes(b"{" + b"x" * (ApprovalService.MAX_STORE_BYTES + 1))
    with pytest.raises(ValidationError, match="too large"):
        service.list_for(owner_id=OWNER_A, session_id=SESSION_A)


def test_audit_log_keeps_only_opaque_actor_field_diff_and_status(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.append(
        actor=OWNER_A,
        request_id="chg_123e4567-e89b-12d3-a456-426614174000",
        target="job-1",
        status="applied",
        diff={"enabled": {"before": True, "after": False}},
    )

    text = audit.path.read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["actor"] == OWNER_A
    assert record["diff"] == {"enabled": {"after": False, "before": True}}
    assert set(record) == {"at", "actor", "request_id", "target", "status", "diff"}
    assert stat.S_IMODE(audit.path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "diff",
    [
        {"message": {"before": "private body", "after": "other"}},
        {"to": {"before": "owner@example.com", "after": "recipient"}},
        {"token": {"before": None, "after": "sk-secret"}},
        {"enabled": {"before": True, "after": "Authorization: Bearer secret"}},
    ],
)
def test_audit_rejects_payload_recipient_token_or_private_content(
    tmp_path: Path, diff: dict[str, object]
) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")

    with pytest.raises(ValueError):
        audit.append(
            actor=OWNER_A,
            request_id="chg_123e4567-e89b-12d3-a456-426614174000",
            target="job-1",
            status="failed",
            diff=diff,
        )
