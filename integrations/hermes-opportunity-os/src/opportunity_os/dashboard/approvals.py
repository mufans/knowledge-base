"""Persisted two-phase approval state machine for bounded dashboard changes."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opportunity_os.dashboard.schedule_validation import normalize_schedule


APPROVAL_TTL = timedelta(minutes=5)
ALLOWED_PATCH_KEYS = frozenset({"enabled", "cron", "tz"})
_OPAQUE_ID = re.compile(r"^[0-9a-f]{64}$")
_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ApprovalError(RuntimeError):
    """Base class for safe approval failures."""


class ValidationError(ApprovalError):
    """A change is outside the exact V1 mutation contract."""


class ConflictError(ApprovalError):
    """The approved digest or base revision no longer matches."""


class ExpiredError(ApprovalError):
    """The five-minute confirmation window elapsed."""


class IsolationError(ApprovalError):
    """A different owner or session attempted to use a change request."""


class StateError(ApprovalError):
    """The requested state transition is invalid or repeated."""


ChangeKind = Literal["task_patch", "run_now"]
ChangeState = Literal[
    "awaiting_approval",
    "approved",
    "applying",
    "applied",
    "failed",
    "expired",
    "conflict",
    "indeterminate",
]
OperationPhase = Literal["intent_pending", "intent_written", "mutation_started", "terminal"]


class ChangeRequest(BaseModel):
    """A digest-bound change request; the nonce never enters audit records."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ChangeKind
    target: str
    patch: dict[str, object]
    base_revision: str
    digest: str
    nonce: str
    owner_id: str
    session_id: str
    state: ChangeState
    created_at: datetime
    expires_at: datetime
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    terminal_at: datetime | None = None
    operation_id: str | None = None
    audit_pending: bool = False
    audit_diff: dict[str, object] = Field(default_factory=dict)
    operation_phase: OperationPhase | None = None
    operation_started_at: datetime | None = None
    terminal_reason: str | None = None
    manual_review: bool = False


def _validate_opaque(value: str, field: str) -> str:
    if _OPAQUE_ID.fullmatch(value) is None:
        raise ValidationError(f"{field} must be an opaque identifier")
    return value


def _validate_target(value: str) -> str:
    if _JOB_ID.fullmatch(value) is None:
        raise ValidationError("target must be a safe OpenClaw job id")
    return value


def _validate_revision(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValidationError("base_revision must be a bounded string")
    return value


def _normalize_patch(patch: dict[str, object]) -> dict[str, object]:
    if not isinstance(patch, dict) or frozenset(patch) - ALLOWED_PATCH_KEYS:
        raise ValidationError("patch contains a forbidden task field")
    keys = frozenset(patch)
    if keys == {"enabled"}:
        if type(patch["enabled"]) is not bool:
            raise ValidationError("enabled must be a boolean")
        return {"enabled": patch["enabled"]}
    if keys == {"cron", "tz"}:
        try:
            cron, tz = normalize_schedule(patch["cron"], patch["tz"])
        except ValueError as error:
            raise ValidationError(str(error)) from error
        return {"cron": cron, "tz": tz}
    raise ValidationError("patch must be exactly enabled or cron plus tz")


def _digest_payload(
    *,
    kind: ChangeKind,
    target: str,
    patch: dict[str, object],
    base_revision: str,
    owner_id: str,
    session_id: str,
) -> str:
    canonical = json.dumps(
        {
            "base_revision": base_revision,
            "kind": kind,
            "owner_id": owner_id,
            "patch": patch,
            "session_id": session_id,
            "target": target,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(b"opportunity-os/change-request/v1\0" + canonical).hexdigest()


def _expected_digest(request: ChangeRequest) -> str:
    return _digest_payload(
        kind=request.kind,
        target=request.target,
        patch=request.patch,
        base_revision=request.base_revision,
        owner_id=request.owner_id,
        session_id=request.session_id,
    )


class ApprovalService:
    """Atomic owner/session state with revision-checked, attestation-gated apply."""

    MAX_STORE_BYTES = 1 * 1_024 * 1_024
    TERMINAL_RETENTION = timedelta(days=7)
    MAX_TERMINAL_REQUESTS = 200
    _TERMINAL_STATES = frozenset(
        {"applied", "failed", "expired", "conflict", "indeterminate"}
    )

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.is_file():
            return {"requests": {}}
        if self.path.stat().st_size > self.MAX_STORE_BYTES:
            raise ValidationError("approval store is too large")
        with self.path.open("rb") as handle:
            raw = handle.read(self.MAX_STORE_BYTES + 1)
        if len(raw) > self.MAX_STORE_BYTES:
            raise ValidationError("approval store is too large")
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
            raise ValidationError("approval store is invalid") from error
        requests = payload.get("requests") if isinstance(payload, dict) else None
        if not isinstance(requests, dict):
            raise ValidationError("approval store is invalid")
        return {"requests": requests}

    def _write(self, payload: dict[str, dict[str, object]]) -> None:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @contextmanager
    def _transaction(self):
        with self._lock, self.lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield self._read()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _load(payload: dict[str, dict[str, object]], request_id: str) -> ChangeRequest:
        raw = payload["requests"].get(request_id)
        if raw is None:
            raise KeyError(request_id)
        try:
            return ChangeRequest.model_validate(raw)
        except ValueError as error:
            raise ConflictError("change request failed integrity validation") from error

    @staticmethod
    def _store(payload: dict[str, dict[str, object]], request: ChangeRequest) -> None:
        payload["requests"][request.id] = request.model_dump(mode="json")

    def _terminalize(self, request: ChangeRequest, state: ChangeState) -> None:
        now = self._clock()
        request.state = state
        request.terminal_at = now
        request.operation_id = request.operation_id or f"op_{uuid.uuid4()}"
        request.audit_pending = True
        request.operation_phase = "terminal"

    def _purge(self, payload: dict[str, dict[str, object]]) -> bool:
        changed = False
        now = self._clock()
        requests = payload["requests"]
        loaded: list[ChangeRequest] = []
        for request_id in list(requests):
            request = self._load(payload, request_id)
            if request.state in {"awaiting_approval", "approved"} and now >= request.expires_at:
                self._terminalize(request, "expired")
                self._store(payload, request)
                changed = True
            loaded.append(request)
        terminal = sorted(
            (
                item
                for item in loaded
                if item.state in self._TERMINAL_STATES and not item.audit_pending
            ),
            key=lambda item: item.terminal_at or item.created_at,
            reverse=True,
        )
        retained_ids = {item.id for item in terminal[: self.MAX_TERMINAL_REQUESTS]}
        cutoff = now - self.TERMINAL_RETENTION
        for request in terminal:
            terminal_at = request.terminal_at or request.created_at
            if request.id not in retained_ids or terminal_at < cutoff:
                del requests[request.id]
                changed = True
        return changed

    @staticmethod
    def _assert_binding(request: ChangeRequest, owner_id: str, session_id: str) -> None:
        if not secrets.compare_digest(request.owner_id, owner_id) or not secrets.compare_digest(
            request.session_id, session_id
        ):
            raise IsolationError("change request is not visible to this owner/session")

    @staticmethod
    def _assert_digest(request: ChangeRequest) -> None:
        expected = _expected_digest(request)
        if not secrets.compare_digest(expected, request.digest):
            raise ConflictError("change request payload changed after preview")

    def preview(
        self,
        target: str,
        patch: dict[str, object],
        *,
        base_revision: str,
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
        audit_diff: dict[str, object] | None = None,
    ) -> ChangeRequest:
        normalized = _normalize_patch(patch)
        return self._preview(
            kind="task_patch",
            target=target,
            patch=normalized,
            base_revision=base_revision,
            owner_id=owner_id,
            session_id=session_id,
            audit_diff=audit_diff or {},
        )

    def preview_run_now(
        self,
        target: str,
        *,
        base_revision: str,
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
        patch: dict[str, object] | None = None,
        audit_diff: dict[str, object] | None = None,
    ) -> ChangeRequest:
        if patch is not None:
            raise ValidationError("run_now does not accept a mutable patch")
        return self._preview(
            kind="run_now",
            target=target,
            patch={},
            base_revision=base_revision,
            owner_id=owner_id,
            session_id=session_id,
            audit_diff=audit_diff or {},
        )

    def _preview(
        self,
        *,
        kind: ChangeKind,
        target: str,
        patch: dict[str, object],
        base_revision: str,
        owner_id: str,
        session_id: str,
        audit_diff: dict[str, object],
    ) -> ChangeRequest:
        now = self._clock()
        target = _validate_target(target)
        base_revision = _validate_revision(base_revision)
        owner_id = _validate_opaque(owner_id, "owner_id")
        session_id = _validate_opaque(session_id, "session_id")
        digest = _digest_payload(
            kind=kind,
            target=target,
            patch=patch,
            base_revision=base_revision,
            owner_id=owner_id,
            session_id=session_id,
        )
        request = ChangeRequest(
            id=f"chg_{uuid.uuid4()}",
            kind=kind,
            target=target,
            patch=patch,
            base_revision=base_revision,
            digest=digest,
            nonce=secrets.token_urlsafe(24),
            owner_id=owner_id,
            session_id=session_id,
            state="awaiting_approval",
            created_at=now,
            expires_at=now + APPROVAL_TTL,
            audit_diff=audit_diff,
        )
        with self._transaction() as payload:
            self._purge(payload)
            self._store(payload, request)
            self._write(payload)
        return request

    def approve(
        self,
        request_id: str,
        digest: str,
        *,
        nonce: str,
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
    ) -> ChangeRequest:
        _validate_opaque(owner_id, "owner_id")
        _validate_opaque(session_id, "session_id")
        with self._transaction() as payload:
            request = self._load(payload, request_id)
            self._assert_binding(request, owner_id, session_id)
            self._assert_digest(request)
            if request.state != "awaiting_approval":
                raise StateError("change request is not awaiting approval")
            if self._clock() >= request.expires_at:
                self._terminalize(request, "expired")
                self._store(payload, request)
                self._write(payload)
                raise ExpiredError("approval nonce expired")
            if not secrets.compare_digest(request.digest, digest) or not secrets.compare_digest(
                request.nonce, nonce
            ):
                raise ConflictError("digest or nonce mismatch")
            request.state = "approved"
            request.approved_at = self._clock()
            request.nonce = "consumed"
            self._store(payload, request)
            self._write(payload)
            return request

    def apply(
        self,
        request_id: str,
        *,
        observed_revision: str,
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
        apply_change: Callable[[ChangeRequest], object] | None = None,
    ) -> ChangeRequest:
        request = self.start_apply(
            request_id,
            observed_revision=observed_revision,
            owner_id=owner_id,
            session_id=session_id,
        )
        try:
            if apply_change is not None:
                apply_change(request)
        except Exception:
            self.finish_apply(
                request_id,
                outcome="failed",
                owner_id=owner_id,
                session_id=session_id,
            )
            raise
        return self.finish_apply(
            request_id,
            outcome="applied",
            owner_id=owner_id,
            session_id=session_id,
        )

    def start_apply(
        self,
        request_id: str,
        *,
        observed_revision: str,
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
    ) -> ChangeRequest:
        _validate_opaque(owner_id, "owner_id")
        _validate_opaque(session_id, "session_id")
        with self._transaction() as payload:
            request = self._load(payload, request_id)
            self._assert_binding(request, owner_id, session_id)
            self._assert_digest(request)
            if request.state != "approved":
                raise StateError("change request is not approved")
            if self._clock() >= request.expires_at:
                self._terminalize(request, "expired")
                self._store(payload, request)
                self._write(payload)
                raise ExpiredError("approval expired before apply")
            if not secrets.compare_digest(request.base_revision, observed_revision):
                self._terminalize(request, "conflict")
                self._store(payload, request)
                self._write(payload)
                raise ConflictError("target revision changed after preview")
            request.state = "applying"
            request.operation_id = request.operation_id or f"op_{uuid.uuid4()}"
            request.audit_pending = False
            request.operation_phase = "intent_pending"
            request.operation_started_at = self._clock()
            request.terminal_reason = None
            request.manual_review = False
            self._store(payload, request)
            self._write(payload)
            return request

    def finish_apply(
        self,
        request_id: str,
        *,
        outcome: Literal["applied", "failed"],
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
    ) -> ChangeRequest:
        with self._transaction() as payload:
            request = self._load(payload, request_id)
            self._assert_binding(request, owner_id, session_id)
            if request.state != "applying":
                raise StateError("change request is not applying")
            self._terminalize(request, outcome)
            request.terminal_reason = "completed" if outcome == "applied" else "mutation_failed"
            if outcome == "applied":
                request.applied_at = self._clock()
            self._store(payload, request)
            self._write(payload)
            return request

    def _mark_phase(self, operation_id: str, phase: OperationPhase) -> ChangeRequest:
        with self._transaction() as payload:
            request = next(
                (
                    self._load(payload, key)
                    for key in payload["requests"]
                    if payload["requests"][key].get("operation_id") == operation_id
                ),
                None,
            )
            if request is None:
                raise KeyError(operation_id)
            if request.state != "applying":
                raise StateError("operation is not applying")
            allowed = {
                "intent_pending": "intent_written",
                "intent_written": "mutation_started",
            }
            if allowed.get(request.operation_phase) != phase:
                raise StateError("operation phase transition is invalid")
            request.operation_phase = phase
            self._store(payload, request)
            self._write(payload)
            return request

    def mark_intent_written(self, operation_id: str | None) -> ChangeRequest:
        if operation_id is None:
            raise StateError("operation id is missing")
        return self._mark_phase(operation_id, "intent_written")

    def mark_mutation_started(self, operation_id: str | None) -> ChangeRequest:
        if operation_id is None:
            raise StateError("operation id is missing")
        return self._mark_phase(operation_id, "mutation_started")

    def recover_operation(
        self,
        operation_id: str,
        *,
        outcome: Literal["applied", "failed", "indeterminate"],
        reason: str,
        manual_review: bool,
    ) -> ChangeRequest:
        """Persist a recovery outcome before any terminal audit is attempted."""
        with self._transaction() as payload:
            request = next(
                (
                    self._load(payload, key)
                    for key in payload["requests"]
                    if payload["requests"][key].get("operation_id") == operation_id
                ),
                None,
            )
            if request is None:
                raise KeyError(operation_id)
            if request.state != "applying":
                return request
            self._terminalize(request, outcome)
            request.terminal_reason = reason
            request.manual_review = manual_review
            if outcome == "applied":
                request.applied_at = self._clock()
            self._store(payload, request)
            self._write(payload)
            return request

    def record_terminal(
        self,
        request_id: str,
        *,
        outcome: Literal["failed", "expired", "conflict"],
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
    ) -> ChangeRequest:
        """Persist a safe terminal outcome when no CLI mutation was started."""
        with self._transaction() as payload:
            request = self._load(payload, request_id)
            self._assert_binding(request, owner_id, session_id)
            if request.state not in {"awaiting_approval", "approved"}:
                raise StateError("change request cannot enter this terminal state")
            self._terminalize(request, outcome)
            self._store(payload, request)
            self._write(payload)
            return request

    def pending_audits(self) -> list[ChangeRequest]:
        with self._transaction() as payload:
            changed = self._purge(payload)
            requests = [self._load(payload, key) for key in sorted(payload["requests"])]
            if changed:
                self._write(payload)
        return [request for request in requests if request.audit_pending]

    def pending_operations(self) -> list[ChangeRequest]:
        with self._transaction() as payload:
            requests = [self._load(payload, key) for key in sorted(payload["requests"])]
        return [request for request in requests if request.state == "applying"]

    def manual_reviews(self) -> list[ChangeRequest]:
        with self._transaction() as payload:
            requests = [self._load(payload, key) for key in sorted(payload["requests"])]
        return [request for request in requests if request.manual_review]

    def mark_audited(self, operation_id: str) -> None:
        with self._transaction() as payload:
            match = next(
                (
                    self._load(payload, key)
                    for key in payload["requests"]
                    if payload["requests"][key].get("operation_id") == operation_id
                ),
                None,
            )
            if match is None:
                raise KeyError(operation_id)
            match.audit_pending = False
            self._store(payload, match)
            self._write(payload)

    def list_for(self, *, owner_id: str, session_id: str) -> list[ChangeRequest]:
        _validate_opaque(owner_id, "owner_id")
        _validate_opaque(session_id, "session_id")
        with self._transaction() as payload:
            changed = self._purge(payload)
            requests = [
                self._load(payload, request_id)
                for request_id in sorted(payload["requests"])
            ]
            if changed:
                self._write(payload)
        return [
            request
            for request in requests
            if secrets.compare_digest(request.owner_id, owner_id)
            and secrets.compare_digest(request.session_id, session_id)
        ]
