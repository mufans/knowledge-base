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

from pydantic import BaseModel, ConfigDict


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
    "awaiting_approval", "approved", "applying", "applied", "failed", "expired"
]


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
        cron = patch["cron"]
        tz = patch["tz"]
        if not isinstance(cron, str) or not cron.strip() or len(cron.encode("utf-8")) > 256:
            raise ValidationError("cron must be a bounded non-empty string")
        if not isinstance(tz, str) or not tz.strip() or len(tz.encode("utf-8")) > 128:
            raise ValidationError("tz must be a bounded non-empty string")
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
    """Atomic, owner/session-scoped approval storage with compare-and-swap apply."""

    MAX_STORE_BYTES = 1 * 1_024 * 1_024

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
    ) -> ChangeRequest:
        normalized = _normalize_patch(patch)
        return self._preview(
            kind="task_patch",
            target=target,
            patch=normalized,
            base_revision=base_revision,
            owner_id=owner_id,
            session_id=session_id,
        )

    def preview_run_now(
        self,
        target: str,
        *,
        base_revision: str,
        owner_id: str = "0" * 64,
        session_id: str = "0" * 64,
        patch: dict[str, object] | None = None,
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
        )
        with self._transaction() as payload:
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
            if self._clock() > request.expires_at:
                request.state = "expired"
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
        _validate_opaque(owner_id, "owner_id")
        _validate_opaque(session_id, "session_id")
        with self._transaction() as payload:
            request = self._load(payload, request_id)
            self._assert_binding(request, owner_id, session_id)
            self._assert_digest(request)
            if request.state != "approved":
                raise StateError("change request is not approved")
            if not secrets.compare_digest(request.base_revision, observed_revision):
                raise ConflictError("target revision changed after preview")
            request.state = "applying"
            self._store(payload, request)
            self._write(payload)
            try:
                if apply_change is not None:
                    apply_change(request)
            except Exception:
                request.state = "failed"
                self._store(payload, request)
                self._write(payload)
                raise
            request.state = "applied"
            request.applied_at = self._clock()
            self._store(payload, request)
            self._write(payload)
            return request

    def list_for(self, *, owner_id: str, session_id: str) -> list[ChangeRequest]:
        _validate_opaque(owner_id, "owner_id")
        _validate_opaque(session_id, "session_id")
        with self._transaction() as payload:
            requests = [
                self._load(payload, request_id)
                for request_id in sorted(payload["requests"])
            ]
        return [
            request
            for request in requests
            if secrets.compare_digest(request.owner_id, owner_id)
            and secrets.compare_digest(request.session_id, session_id)
        ]
