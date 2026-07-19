"""Owner-only, typed IM routing for the OpenClaw DingTalk ingress."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import unicodedata
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from opportunity_os.automation.secure_runtime import (
    atomic_json_at,
    exclusive_arbitration,
    open_absolute_directory,
    read_json_at,
)
from opportunity_os.dashboard.incidents import canonical_dashboard_url
from opportunity_os.errors import OpportunityOSError
from opportunity_os.sanitizer import contains_secret


MAX_INPUT_BYTES = 4_096
MAX_REPLY_BYTES = 4_096
MAX_PAYLOAD_BYTES = 2_048
CONFIRMATION_TTL = timedelta(minutes=5)
PROPOSAL_TTL = timedelta(days=14)
MAX_CONFIRMATIONS = 100
MAX_PROPOSALS = 100
MAX_STATE_BYTES = 512 * 1_024

ReadKind = Literal[
    "status",
    "latest_review",
    "directions",
    "opportunity_detail",
    "learning_summary",
    "pending_memory",
    "pending_skills",
]
WriteKind = Literal["feedback", "change_requirement", "restart", "retry_task"]
CommandKind = Literal[
    "status",
    "latest_review",
    "directions",
    "opportunity_detail",
    "learning_summary",
    "pending_memory",
    "pending_skills",
    "feedback",
    "change_requirement",
    "restart",
    "retry_task",
    "confirm",
    "chat_fallback",
]

READ_KINDS = frozenset(
    {
        "status",
        "latest_review",
        "directions",
        "opportunity_detail",
        "learning_summary",
        "pending_memory",
        "pending_skills",
    }
)
PROPOSAL_KINDS = frozenset({"feedback", "change_requirement"})
ACTION_KINDS = frozenset({"restart", "retry_task"})
RESTART_TARGETS = frozenset({"openclaw", "dashboard", "hermes", "ngrok"})
RETRY_TARGETS = frozenset(
    {"daily", "weekly", "biweekly", "six-week", "quarterly", "sync", "publish", "delivery"}
)

_OPPORTUNITY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{24}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LOCAL_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:\.{1,2}/|/(?:Users|home|private|tmp|var|etc|opt)/|[A-Za-z]:[\\/]|file://)",
    re.IGNORECASE,
)
_REDACT_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:/(?:Users|home|private|tmp|var|etc|opt)/[^\s,;]*|[A-Za-z]:[\\/][^\s,;]*)"
)
_STDERR_LINE = re.compile(r"(?im)^.*\bstderr\b.*$")
_CONFIRM_PREFIX = "Hermes 确认 "


class ImError(OpportunityOSError):
    """Base class for fixed-code IM failures."""


class InputError(ImError):
    """The command violates the exact documented grammar or bounds."""


class AuthorizationError(ImError):
    """The server config, sender, chat type, or DM metadata is unauthorized."""


class ConfirmationError(ImError):
    """A confirmation is expired, replayed, changed, or cross-session."""


class ActionUnavailableError(ImError):
    """A production action backend has not been explicitly installed."""


class BackendError(ImError):
    """A backend failed without exposing its diagnostic text to IM."""


class ImCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CommandKind
    payload: str | None = None
    nonce: str | None = None
    digest: str | None = None


class ImReply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[
        "ok", "chat_fallback", "awaiting_confirmation", "proposal_pending", "accepted"
    ]
    text: str
    dashboard_url: str | None = None
    expires_in_seconds: int | None = None
    nonce: str | None = None
    confirmation_text: str | None = None
    proposal_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)


class PendingProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: Literal["feedback", "change_requirement"]
    payload: str
    digest: str
    actor_digest: str
    session_digest: str
    state: Literal["pending"] = "pending"
    created_at: datetime
    expires_at: datetime


class ReadBackend(Protocol):
    def read(self, command: ImCommand) -> str: ...


class ActionBackend(Protocol):
    def execute(self, kind: str, target: str) -> str: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InputError("timestamp_must_be_aware")
    return value.astimezone(timezone.utc)


def _bounded_metadata(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise AuthorizationError(f"invalid_{name}")
    if _CONTROL.search(value) or value.strip() != value:
        raise AuthorizationError(f"invalid_{name}")
    return value


def _validate_payload(value: str) -> str:
    if not value or value.strip() != value or len(value.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise InputError("invalid_payload")
    if _CONTROL.search(value) or contains_secret(value) or _LOCAL_PATH.search(value):
        raise InputError("unsafe_payload")
    return value


def _digest(
    *, kind: str, payload: str, nonce: str, sender_id: str, session_id: str
) -> str:
    canonical = json.dumps(
        {
            "kind": kind,
            "nonce": nonce,
            "payload": payload,
            "sender_id": sender_id,
            "session_id": session_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(b"opportunity-os/im-confirmation/v1\0" + canonical).hexdigest()


def _identity_digest(kind: str, value: str) -> str:
    return hashlib.sha256(
        b"opportunity-os/im-private-identity/v1\0"
        + kind.encode("ascii")
        + b"\0"
        + value.encode("utf-8")
    ).hexdigest()


def _safe_text(value: object) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = _STDERR_LINE.sub("[REDACTED]", text)
    text = _REDACT_PATH.sub("[REDACTED]", text)
    if contains_secret(text):
        # Secret-shaped free text is never partially quoted back to IM.
        text = "[REDACTED]"
    rendered = text.encode("utf-8")
    if len(rendered) <= MAX_REPLY_BYTES:
        return text
    marker = "…[已截断]"
    budget = MAX_REPLY_BYTES - len(marker.encode("utf-8"))
    prefix = rendered[:budget]
    while True:
        try:
            return prefix.decode("utf-8") + marker
        except UnicodeDecodeError:
            prefix = prefix[:-1]


def parse_im_command(text: str) -> ImCommand:
    """Apply NFKC once, then match only the documented Chinese grammar."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise InputError("input_too_large")
    if _CONTROL.search(text):
        raise InputError("invalid_input")
    normalized = unicodedata.normalize("NFKC", text)
    exact: dict[str, CommandKind] = {
        "Hermes 状态": "status",
        "Hermes 最新周报": "latest_review",
        "Hermes 当前方向": "directions",
        "Hermes 最近学到了什么": "learning_summary",
        "Hermes 待审批记忆": "pending_memory",
        "Hermes 待审批Skill": "pending_skills",
    }
    if normalized in exact:
        return ImCommand(kind=exact[normalized])

    detail_prefix = "Hermes 机会详情 "
    if normalized.startswith(detail_prefix):
        opportunity_id = normalized.removeprefix(detail_prefix)
        if _OPPORTUNITY_ID.fullmatch(opportunity_id):
            return ImCommand(kind="opportunity_detail", payload=opportunity_id)
        return ImCommand(kind="chat_fallback")

    for prefix, kind in (
        ("Hermes 反馈:", "feedback"),
        ("Hermes 修改需求:", "change_requirement"),
    ):
        if normalized.startswith(prefix):
            return ImCommand(kind=kind, payload=_validate_payload(normalized.removeprefix(prefix)))

    for prefix, kind, allowed in (
        ("Hermes 重启 ", "restart", RESTART_TARGETS),
        ("Hermes 重试任务 ", "retry_task", RETRY_TARGETS),
    ):
        if normalized.startswith(prefix):
            target = normalized.removeprefix(prefix)
            if target in allowed:
                return ImCommand(kind=kind, payload=target)
            return ImCommand(kind="chat_fallback")

    if normalized.startswith(_CONFIRM_PREFIX):
        nonce = normalized.removeprefix(_CONFIRM_PREFIX)
        if _NONCE.fullmatch(nonce):
            return ImCommand(kind="confirm", nonce=nonce)
        return ImCommand(kind="chat_fallback")
    return ImCommand(kind="chat_fallback")


class _LockedState:
    def __init__(self, path: str | Path, lock_name: str) -> None:
        self.path = Path(path).expanduser().resolve()
        self.lock_name = lock_name

    def _directory(self) -> int:
        return open_absolute_directory(self.path.parent)

    def _read(self, directory_fd: int, *, records_key: str) -> dict[str, object]:
        try:
            value = read_json_at(directory_fd, self.path.name, max_bytes=MAX_STATE_BYTES)
        except FileNotFoundError:
            return {"version": 1, records_key: []}
        if set(value) != {"version", records_key} or value["version"] != 1:
            raise InputError("invalid_im_state")
        records = value[records_key]
        if not isinstance(records, list):
            raise InputError("invalid_im_state")
        return value

    def _write(self, directory_fd: int, payload: dict[str, object]) -> None:
        atomic_json_at(
            directory_fd,
            self.path.name,
            payload,
            mode=0o600,
            max_bytes=MAX_STATE_BYTES,
        )


class ConfirmationStore(_LockedState):
    def __init__(self, path: str | Path, *, clock: Callable[[], datetime]) -> None:
        super().__init__(path, ".im-confirmations.lock")
        self.clock = clock

    def create(self, command: ImCommand, *, sender_id: str, session_id: str) -> tuple[str, str]:
        if command.kind not in PROPOSAL_KINDS | ACTION_KINDS or command.payload is None:
            raise InputError("invalid_confirmation_subject")
        now = _utc(self.clock())
        nonce = secrets.token_urlsafe(18)
        if _NONCE.fullmatch(nonce) is None:  # pragma: no cover - token_urlsafe invariant
            raise BackendError("nonce_generation_failed")
        digest = _digest(
            kind=command.kind,
            payload=command.payload,
            nonce=nonce,
            sender_id=sender_id,
            session_id=session_id,
        )
        record = {
            "kind": command.kind,
            "payload": command.payload,
            "nonce": nonce,
            "digest": digest,
            "sender_id": sender_id,
            "session_id": session_id,
            "created_at": now.isoformat(),
            "expires_at": (now + CONFIRMATION_TTL).isoformat(),
        }
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                state = self._read(directory_fd, records_key="confirmations")
                validated = [_confirmation_record(item) for item in state["confirmations"]]
                records = [item for item in validated if _record_expiry(item) > now]
                if len(records) >= MAX_CONFIRMATIONS:
                    raise InputError("confirmation_capacity_exhausted")
                records.append(record)
                self._write(directory_fd, {"version": 1, "confirmations": records})
        finally:
            os.close(directory_fd)
        return nonce, digest

    def consume(
        self,
        command: ImCommand,
        *,
        sender_id: str,
        session_id: str,
    ) -> tuple[str, str, str]:
        if command.kind != "confirm" or command.nonce is None:
            raise ConfirmationError("invalid_confirmation")
        now = _utc(self.clock())
        result: tuple[str, str, str] | None = None
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                state = self._read(directory_fd, records_key="confirmations")
                records: list[object] = []
                found = False
                for item in state["confirmations"]:
                    record = _confirmation_record(item)
                    if not secrets.compare_digest(record["nonce"], command.nonce):
                        if _record_expiry(record) > now:
                            records.append(record)
                        continue
                    found = True
                    if not secrets.compare_digest(record["sender_id"], sender_id):
                        records.append(record)
                        raise AuthorizationError("owner_mismatch")
                    if not secrets.compare_digest(record["session_id"], session_id):
                        records.append(record)
                        raise ConfirmationError("session_mismatch")
                    if _record_expiry(record) <= now:
                        raise ConfirmationError("confirmation_expired")
                    expected = _digest(
                        kind=record["kind"],
                        payload=record["payload"],
                        nonce=record["nonce"],
                        sender_id=record["sender_id"],
                        session_id=record["session_id"],
                    )
                    if not secrets.compare_digest(expected, record["digest"]):
                        raise ConfirmationError("confirmation_digest_mismatch")
                    if command.digest is not None and not secrets.compare_digest(
                        command.digest, record["digest"]
                    ):
                        records.append(record)
                        raise ConfirmationError("confirmation_digest_mismatch")
                    result = (record["kind"], record["payload"], record["digest"])
                    # Intentionally omit the consumed record: nonce is single use even if the
                    # injected action backend later fails closed.
                self._write(directory_fd, {"version": 1, "confirmations": records})
                if not found or result is None:
                    raise ConfirmationError("confirmation_unknown_or_replayed")
        finally:
            os.close(directory_fd)
        return result


def _record_expiry(value: object) -> datetime:
    if not isinstance(value, dict) or not isinstance(value.get("expires_at"), str):
        raise InputError("invalid_im_state")
    try:
        return _utc(datetime.fromisoformat(value["expires_at"]))
    except ValueError as error:
        raise InputError("invalid_im_state") from error


def _confirmation_record(value: object) -> dict[str, str]:
    fields = {
        "kind",
        "payload",
        "nonce",
        "digest",
        "sender_id",
        "session_id",
        "created_at",
        "expires_at",
    }
    if not isinstance(value, dict) or set(value) != fields or not all(
        isinstance(value[field], str) for field in fields
    ):
        raise InputError("invalid_im_state")
    if value["kind"] not in PROPOSAL_KINDS | ACTION_KINDS:
        raise InputError("invalid_im_state")
    if _NONCE.fullmatch(value["nonce"]) is None or not re.fullmatch(r"[0-9a-f]{64}", value["digest"]):
        raise InputError("invalid_im_state")
    return value


def _proposal_record(value: object) -> PendingProposal:
    try:
        proposal = PendingProposal.model_validate(value)
    except Exception as error:
        raise InputError("invalid_im_state") from error
    if not re.fullmatch(r"imp_[0-9a-f-]{36}", proposal.id):
        raise InputError("invalid_im_state")
    if not all(
        re.fullmatch(r"[0-9a-f]{64}", item)
        for item in (proposal.digest, proposal.actor_digest, proposal.session_digest)
    ):
        raise InputError("invalid_im_state")
    _validate_payload(proposal.payload)
    _utc(proposal.created_at)
    _utc(proposal.expires_at)
    return proposal


class PendingProposalStore(_LockedState):
    def __init__(self, path: str | Path, *, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__(path, ".im-proposals.lock")
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def add(
        self,
        *,
        kind: str,
        payload: str,
        digest: str,
        sender_id: str,
        session_id: str,
    ) -> PendingProposal:
        if kind not in PROPOSAL_KINDS or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise InputError("invalid_proposal")
        payload = _validate_payload(payload)
        now = _utc(self.clock())
        proposal = PendingProposal(
            id=f"imp_{uuid.uuid4()}",
            kind=kind,
            payload=payload,
            digest=digest,
            actor_digest=_identity_digest("sender", sender_id),
            session_digest=_identity_digest("session", session_id),
            created_at=now,
            expires_at=now + PROPOSAL_TTL,
        )
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                state = self._read(directory_fd, records_key="proposals")
                validated = [_proposal_record(item) for item in state["proposals"]]
                records = [
                    item.model_dump(mode="json")
                    for item in validated
                    if item.expires_at > now
                ]
                if len(records) >= MAX_PROPOSALS:
                    raise InputError("proposal_capacity_exhausted")
                records.append(proposal.model_dump(mode="json"))
                self._write(directory_fd, {"version": 1, "proposals": records})
        finally:
            os.close(directory_fd)
        return proposal

    def list(self) -> list[PendingProposal]:
        now = _utc(self.clock())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                state = self._read(directory_fd, records_key="proposals")
                records = [_proposal_record(item) for item in state["proposals"]]
                active = [item for item in records if item.expires_at > now]
                if len(active) != len(records):
                    self._write(
                        directory_fd,
                        {"version": 1, "proposals": [item.model_dump(mode="json") for item in active]},
                    )
                return active
        finally:
            os.close(directory_fd)


class DisabledActionBackend:
    def execute(self, kind: str, target: str) -> str:
        del kind, target
        raise ActionUnavailableError("action_backend_disabled")


class PrivateImReadBackend:
    """Bounded, side-effect-free reads from one configured private state root."""

    MAX_FILE_BYTES = 256 * 1_024

    def __init__(self, private_home: str | Path) -> None:
        self.home = Path(private_home).expanduser().resolve()

    def _json(self, relative: Path) -> object:
        candidate = self.home / relative
        current = self.home
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise BackendError("private_record_unavailable")
        path = candidate.resolve()
        if not path.is_relative_to(self.home) or not path.is_file():
            raise BackendError("private_record_unavailable")
        if path.stat().st_size > self.MAX_FILE_BYTES:
            raise BackendError("private_record_too_large")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise BackendError("private_record_invalid") from error

    def _latest_review(self) -> dict[str, object]:
        directory = self.home / "reviews"
        if not directory.is_dir() or directory.is_symlink():
            raise BackendError("review_unavailable")
        records = [self._json(path.relative_to(self.home)) for path in sorted(directory.glob("*.json"))]
        records = [item for item in records if isinstance(item, dict)]
        if not records:
            raise BackendError("review_unavailable")
        return max(records, key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))))

    def _pending(self, directory_name: str) -> object:
        directory = self.home / directory_name
        if not directory.is_dir() or directory.is_symlink():
            return []
        records = []
        for path in sorted(directory.glob("*.json"))[:100]:
            records.append(self._json(path.relative_to(self.home)))
        return records

    def _count_records(self, directory_name: str) -> int:
        directory = self.home / directory_name
        if not directory.is_dir() or directory.is_symlink():
            return 0
        return sum(path.is_file() and not path.is_symlink() for path in directory.glob("*.json"))

    def read(self, command: ImCommand) -> str:
        try:
            if command.kind == "status":
                return json.dumps(
                    {
                        "opportunity_count": self._count_records("opportunities"),
                        "experiment_count": self._count_records("experiments"),
                        "review_count": self._count_records("reviews"),
                        "tech_state_count": self._count_records("tech_states"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            if command.kind == "latest_review":
                return json.dumps(self._latest_review(), ensure_ascii=False, sort_keys=True)
            if command.kind == "directions":
                portfolio = self._json(Path("portfolio.json"))
                directions = portfolio.get("directions", []) if isinstance(portfolio, dict) else []
                return json.dumps(directions, ensure_ascii=False, sort_keys=True)
            if command.kind == "opportunity_detail" and command.payload is not None:
                return json.dumps(
                    self._json(Path("opportunities") / f"{command.payload}.json"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            if command.kind == "learning_summary":
                review = self._latest_review()
                summary = {
                    key: review.get(key)
                    for key in ("summary", "surprise_signal", "facts", "inferences", "hypotheses")
                    if key in review
                }
                return json.dumps(summary, ensure_ascii=False, sort_keys=True)
            if command.kind == "pending_memory":
                return json.dumps(self._pending("pending_memory"), ensure_ascii=False, sort_keys=True)
            if command.kind == "pending_skills":
                return json.dumps(self._pending("pending_skills"), ensure_ascii=False, sort_keys=True)
        except BackendError:
            raise
        except Exception as error:
            raise BackendError("read_backend_failed") from error
        raise BackendError("unsupported_read_kind")


class ImCommandRouter:
    """Parse exact commands and isolate all mutations behind two-phase confirmation."""

    def __init__(
        self,
        *,
        owner_id: str | None,
        dashboard_url: str | None,
        allowed_dashboard_hosts: tuple[str, ...] = (),
        state_home: str | Path,
        read_backend: ReadBackend,
        action_backend: ActionBackend | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.owner_id = owner_id
        self._configured_dashboard_url = dashboard_url
        self.allowed_dashboard_hosts = allowed_dashboard_hosts
        self.state_home = Path(state_home).expanduser().resolve()
        self.read_backend = read_backend
        self.action_backend = action_backend
        # Compatibility-only observation surface used by the original Task 9 RED
        # contract. Real actions remain exclusively visible on the injected backend.
        self.applied_changes: list[tuple[str, str]] = []
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.confirmations = ConfirmationStore(
            self.state_home / "im-confirmations.json", clock=self.clock
        )
        self.proposals = PendingProposalStore(
            self.state_home / "im-proposals.json", clock=self.clock
        )

    def parse(self, text: str) -> ImCommand:
        return parse_im_command(text)

    def _dashboard_url(self) -> str:
        if self._configured_dashboard_url is None:
            raise AuthorizationError("server_config_missing")
        try:
            return canonical_dashboard_url(
                self._configured_dashboard_url, self.allowed_dashboard_hosts
            )
        except Exception as error:
            raise AuthorizationError("server_config_invalid") from error

    def _authorize(self, *, sender_id: str, session_id: str, chat_type: str) -> tuple[str, str]:
        if self.owner_id is None or not isinstance(self.owner_id, str) or not self.owner_id:
            raise AuthorizationError("server_config_missing")
        sender = _bounded_metadata(sender_id, "sender_id")
        session = _bounded_metadata(session_id, "session_id")
        if chat_type != "dm":
            raise AuthorizationError("direct_message_required")
        if not secrets.compare_digest(self.owner_id, sender):
            raise AuthorizationError("owner_mismatch")
        self._dashboard_url()
        return sender, session

    def execute(
        self,
        command: ImCommand,
        sender_id: str,
        session_id: str,
        chat_type: str = "dm",
    ) -> ImReply:
        if command.kind == "chat_fallback":
            return ImReply(status="chat_fallback", text="chat_fallback")
        sender, session = self._authorize(
            sender_id=sender_id, session_id=session_id, chat_type=chat_type
        )
        dashboard_url = self._dashboard_url()
        if command.kind in READ_KINDS:
            try:
                output = self.read_backend.read(command)
            except ImError:
                raise
            except Exception as error:
                raise BackendError("read_backend_failed") from error
            return ImReply(
                status="ok", text=_safe_text(output), dashboard_url=dashboard_url
            )
        if command.kind in PROPOSAL_KINDS | ACTION_KINDS:
            if command.payload is None:
                raise InputError("missing_payload")
            if command.kind in PROPOSAL_KINDS:
                _validate_payload(command.payload)
            nonce, _digest_value = self.confirmations.create(
                command, sender_id=sender, session_id=session
            )
            confirmation_text = f"{_CONFIRM_PREFIX}{nonce}"
            return ImReply(
                status="awaiting_confirmation",
                text=f"请在 5 分钟内原样回复：{confirmation_text}",
                dashboard_url=dashboard_url,
                expires_in_seconds=300,
                nonce=nonce,
                confirmation_text=confirmation_text,
            )
        if command.kind == "confirm":
            kind, payload, digest = self.confirmations.consume(
                command, sender_id=sender, session_id=session
            )
            if kind in PROPOSAL_KINDS:
                proposal = self.proposals.add(
                    kind=kind,
                    payload=payload,
                    digest=digest,
                    sender_id=sender,
                    session_id=session,
                )
                return ImReply(
                    status="proposal_pending",
                    text="已创建待审批提案，未修改 Cron、Memory 或 Skill。",
                    dashboard_url=dashboard_url,
                    proposal_id=proposal.id,
                )
            backend = self.action_backend or DisabledActionBackend()
            try:
                result = backend.execute(kind, payload)
            except ImError:
                raise
            except Exception as error:
                raise BackendError("action_backend_failed") from error
            return ImReply(
                status="accepted", text=_safe_text(result), dashboard_url=dashboard_url
            )
        raise InputError("unsupported_command")


class ImServerConfig(BaseModel):
    """Private server-side config; no message field can override these values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str
    private_home: Path
    dashboard_url: str
    allowed_dashboard_hosts: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: str | Path) -> "ImServerConfig":
        config_path = Path(path).expanduser()
        try:
            info = config_path.lstat()
        except OSError as error:
            raise AuthorizationError("server_config_missing") from error
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise AuthorizationError("server_config_invalid")
        if info.st_mode & 0o077 or info.st_size > 16 * 1_024:
            raise AuthorizationError("server_config_permissions_invalid")
        try:
            value = json.loads(config_path.read_text(encoding="utf-8"))
            config = cls.model_validate(value)
        except Exception as error:
            raise AuthorizationError("server_config_invalid") from error
        _bounded_metadata(config.owner_id, "owner_id")
        if not config.private_home.is_absolute() or ".." in config.private_home.parts:
            raise AuthorizationError("server_config_invalid")
        try:
            canonical_dashboard_url(config.dashboard_url, config.allowed_dashboard_hosts)
        except Exception as error:
            raise AuthorizationError("server_config_invalid") from error
        return config
