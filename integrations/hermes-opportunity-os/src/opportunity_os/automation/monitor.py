"""Crash-safe monitoring outbox and receipt-backed delivery state machine."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal, Protocol, TypeVar

from opportunity_os.automation.secure_runtime import (
    atomic_json_at,
    exclusive_arbitration,
    open_absolute_directory,
    read_json_at,
)
from opportunity_os.dashboard.events import EventHub
from opportunity_os.dashboard.incidents import (
    ERROR_CLASSES,
    IncidentNotification,
    IncidentSentinel,
    IncidentTransition,
    canonical_dashboard_url,
    validate_allowed_dashboard_hosts,
)
from opportunity_os.dashboard.probes import RuntimeProbe
from opportunity_os.errors import BoundaryError, CapacityError, ValidationError


DeliveryState = Literal["generated", "queued", "sending", "delivered", "failed"]
Impact = Literal[
    "control_plane_unavailable",
    "analysis_unavailable",
    "publishing_unavailable",
    "remote_access_unavailable",
    "delivery_unavailable",
]
SuggestedAction = Literal[
    "inspect_dashboard", "retry_task", "verify_access", "verify_delivery", "none"
]

IMPACTS = frozenset(
    {
        "control_plane_unavailable",
        "analysis_unavailable",
        "publishing_unavailable",
        "remote_access_unavailable",
        "delivery_unavailable",
    }
)
SUGGESTED_ACTIONS = frozenset(
    {"inspect_dashboard", "retry_task", "verify_access", "verify_delivery", "none"}
)
DELIVERY_ERRORS = frozenset({"delivery_failed", "missing_receipt"})
OPAQUE_ID = re.compile(
    r"^(?:run|boot|rcpt|delivery|attempt)_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
IDEMPOTENCY_KEY = re.compile(
    r"^(?:inc|boot)_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}:(?:firing|recovered)$"
)
STATE_MAX_BYTES = 1_048_576


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_optional_time(value: object, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"stored {name} is invalid")
    try:
        return _utc(datetime.fromisoformat(value))
    except ValueError as error:
        raise ValidationError(f"stored {name} is invalid") from error


@dataclass(frozen=True, slots=True)
class AlertSummary:
    """Allowlist-only alert data; validation context is never serialized."""

    error_code: str
    impact: Impact
    last_success: datetime | None
    run_id: str
    dashboard_url: str
    suggested_action: SuggestedAction
    allowed_dashboard_hosts: tuple[str, ...] = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        hosts = validate_allowed_dashboard_hosts(self.allowed_dashboard_hosts)
        object.__setattr__(self, "allowed_dashboard_hosts", hosts)
        if self.error_code not in ERROR_CLASSES:
            raise ValidationError("alert error code is not allowlisted")
        if self.impact not in IMPACTS:
            raise ValidationError("alert impact is not allowlisted")
        if self.last_success is not None:
            object.__setattr__(self, "last_success", _utc(self.last_success))
        if not isinstance(self.run_id, str) or OPAQUE_ID.fullmatch(self.run_id) is None:
            raise ValidationError("alert run id must be opaque")
        object.__setattr__(
            self,
            "dashboard_url",
            canonical_dashboard_url(self.dashboard_url, self.allowed_dashboard_hosts),
        )
        if self.suggested_action not in SUGGESTED_ACTIONS:
            raise ValidationError("alert action is not allowlisted")

    def to_dict(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "impact": self.impact,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "run_id": self.run_id,
            "dashboard_url": self.dashboard_url,
            "suggested_action": self.suggested_action,
        }

    @property
    def headline(self) -> str:
        return "曾中断并已恢复" if self.error_code == "process_interrupted" else "系统监控告警"

    @classmethod
    def from_dict(
        cls, value: object, allowed_dashboard_hosts: tuple[str, ...] = ()
    ) -> "AlertSummary":
        fields = {
            "error_code", "impact", "last_success", "run_id", "dashboard_url", "suggested_action"
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ValidationError("stored alert summary schema is invalid")
        last_success = _parse_optional_time(value["last_success"], "last success")
        return cls(
            error_code=str(value["error_code"]),
            impact=str(value["impact"]),  # type: ignore[arg-type]
            last_success=last_success,
            run_id=str(value["run_id"]),
            dashboard_url=str(value["dashboard_url"]),
            suggested_action=str(value["suggested_action"]),  # type: ignore[arg-type]
            allowed_dashboard_hosts=allowed_dashboard_hosts,
        )

    @classmethod
    def from_notification(
        cls, notification: IncidentNotification, allowed_dashboard_hosts: tuple[str, ...]
    ) -> "AlertSummary":
        return cls(
            error_code=notification.error_code,
            impact=notification.impact,  # type: ignore[arg-type]
            last_success=notification.last_success,
            run_id=notification.run_id,
            dashboard_url=notification.dashboard_url,
            suggested_action=notification.suggested_action,  # type: ignore[arg-type]
            allowed_dashboard_hosts=allowed_dashboard_hosts,
        )


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    provider_accepted: bool
    receipt_id: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_accepted, bool):
            raise ValidationError("provider acceptance must be boolean")
        if self.receipt_id is not None and (
            not isinstance(self.receipt_id, str)
            or not self.receipt_id.startswith("rcpt_")
            or OPAQUE_ID.fullmatch(self.receipt_id) is None
        ):
            raise ValidationError("delivery receipt must be opaque")
        if self.error_code is not None and self.error_code not in DELIVERY_ERRORS:
            raise ValidationError("delivery error code is not allowlisted")
        if self.receipt_id is not None and (
            not self.provider_accepted or self.error_code is not None
        ):
            raise ValidationError("a receipt must be an accepted error-free outcome")


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    delivery_id: str
    idempotency_key: str
    state: DeliveryState
    summary: AlertSummary
    receipt_id: str | None
    error_code: str | None
    attempt_token: str | None
    lease_until: datetime | None
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "delivery_id": self.delivery_id,
            "idempotency_key": self.idempotency_key,
            "state": self.state,
            "summary": self.summary.to_dict(),
            "receipt_id": self.receipt_id,
            "error_code": self.error_code,
            "attempt_token": self.attempt_token,
            "lease_until": self.lease_until.isoformat() if self.lease_until else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    record: DeliveryRecord
    attempt_token: str


class DeliveryPort(Protocol):
    def lookup(self, idempotency_key: str) -> str | None: ...

    def send(self, summary: AlertSummary, idempotency_key: str) -> DeliveryAttempt: ...


class DeferredDelivery:
    """Fail closed until an authenticated receipt-capable adapter is injected."""

    def lookup(self, idempotency_key: str) -> str | None:
        return None

    def send(self, summary: AlertSummary, idempotency_key: str) -> DeliveryAttempt:
        return DeliveryAttempt(False, None, "delivery_failed")


T = TypeVar("T")


class DeliveryQueue:
    def __init__(
        self,
        state_path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
        ttl: timedelta = timedelta(days=30),
        lease_duration: timedelta = timedelta(minutes=5),
        max_entries: int = 1024,
        allowed_dashboard_hosts: tuple[str, ...] = (),
    ) -> None:
        self.path = Path(state_path).expanduser()
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise BoundaryError("delivery state path must be absolute and traversal-free")
        if ttl <= timedelta(0) or lease_duration <= timedelta(0) or not 1 <= max_entries <= 4096:
            raise ValidationError("delivery retention bounds are invalid")
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.ttl = ttl
        self.lease_duration = lease_duration
        self.max_entries = max_entries
        self.allowed_dashboard_hosts = validate_allowed_dashboard_hosts(allowed_dashboard_hosts)

    def _directory(self) -> int:
        return open_absolute_directory(self.path.parent)

    def _record(self, value: dict[str, object]) -> DeliveryRecord:
        fields = {
            "delivery_id", "idempotency_key", "state", "summary", "receipt_id", "error_code",
            "attempt_token", "lease_until", "created_at", "updated_at",
        }
        if set(value) != fields:
            raise ValidationError("delivery record schema is invalid")
        state = value["state"]
        delivery_id = value["delivery_id"]
        idempotency_key = value["idempotency_key"]
        if state not in {"generated", "queued", "sending", "delivered", "failed"}:
            raise ValidationError("delivery state is invalid")
        if not isinstance(delivery_id, str) or not delivery_id.startswith("delivery_") or OPAQUE_ID.fullmatch(delivery_id) is None:
            raise ValidationError("stored delivery id is invalid")
        if not isinstance(idempotency_key, str) or IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ValidationError("stored delivery idempotency key is invalid")
        receipt = value["receipt_id"]
        token = value["attempt_token"]
        error_code = value["error_code"]
        if receipt is not None and (
            not isinstance(receipt, str) or not receipt.startswith("rcpt_") or OPAQUE_ID.fullmatch(receipt) is None
        ):
            raise ValidationError("stored delivery receipt is invalid")
        if token is not None and (
            not isinstance(token, str) or not token.startswith("attempt_") or OPAQUE_ID.fullmatch(token) is None
        ):
            raise ValidationError("stored delivery attempt token is invalid")
        if error_code is not None and error_code not in DELIVERY_ERRORS:
            raise ValidationError("stored delivery error code is invalid")
        lease_until = _parse_optional_time(value["lease_until"], "lease")
        try:
            created_at = _utc(datetime.fromisoformat(str(value["created_at"])))
            updated_at = _utc(datetime.fromisoformat(str(value["updated_at"])))
        except ValueError as error:
            raise ValidationError("stored delivery timestamp is invalid") from error
        if state == "sending" and (token is None or lease_until is None):
            raise ValidationError("sending delivery requires a lease and token")
        if state != "sending" and (token is not None or lease_until is not None):
            raise ValidationError("non-sending delivery cannot hold a lease")
        if state == "delivered" and receipt is None:
            raise ValidationError("delivered state requires a receipt")
        return DeliveryRecord(
            delivery_id=delivery_id,
            idempotency_key=idempotency_key,
            state=state,  # type: ignore[arg-type]
            summary=AlertSummary.from_dict(value["summary"], self.allowed_dashboard_hosts),
            receipt_id=receipt,
            error_code=error_code,
            attempt_token=token,
            lease_until=lease_until,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _load(
        self, directory_fd: int, current: datetime
    ) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
        try:
            payload = read_json_at(directory_fd, self.path.name, max_bytes=STATE_MAX_BYTES)
        except FileNotFoundError:
            payload = {"version": 2, "deliveries": {}, "receipts": {}}
        except json.JSONDecodeError as error:
            raise ValidationError("delivery state contains invalid JSON") from error
        if payload.get("version") == 1 and isinstance(payload.get("deliveries"), dict):
            migrated = {}
            for key, value in payload["deliveries"].items():
                if not isinstance(value, dict):
                    raise ValidationError("delivery state record is invalid")
                migrated[key] = {**value, "attempt_token": None, "lease_until": None}
            payload = {"version": 2, "deliveries": migrated, "receipts": {}}
        if (
            payload.get("version") != 2
            or not isinstance(payload.get("deliveries"), dict)
            or not isinstance(payload.get("receipts"), dict)
        ):
            raise ValidationError("delivery state schema is invalid")
        records: dict[str, dict[str, object]] = {}
        for key, value in payload["deliveries"].items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValidationError("delivery state record is invalid")
            record = self._record(value)
            if key != record.delivery_id:
                raise ValidationError("delivery map key is invalid")
            if record.state not in {"delivered", "failed"} or current - record.updated_at <= self.ttl:
                records[key] = value
        expected_receipts = {
            str(value["receipt_id"]): key
            for key, value in records.items()
            if value.get("state") == "delivered"
        }
        if payload["receipts"] and payload["receipts"] != expected_receipts:
            raise ValidationError("delivery receipt index is invalid")
        return records, expected_receipts

    def _persist(
        self,
        directory_fd: int,
        records: dict[str, dict[str, object]],
        receipts: dict[str, str],
    ) -> None:
        atomic_json_at(
            directory_fd,
            self.path.name,
            {"version": 2, "deliveries": records, "receipts": receipts},
            mode=0o600,
            max_bytes=STATE_MAX_BYTES,
        )

    def _mutate(
        self,
        operation: Callable[[dict[str, dict[str, object]], dict[str, str], datetime], T],
    ) -> T:
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, ".deliveries.lock"):
                records, receipts = self._load(directory_fd, current)
                result = operation(records, receipts, current)
                self._persist(directory_fd, records, receipts)
                return result
        finally:
            os.close(directory_fd)

    def generate(self, idempotency_key: str, summary: AlertSummary) -> DeliveryRecord:
        if not isinstance(idempotency_key, str) or IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ValidationError("delivery idempotency key is invalid")
        if not isinstance(summary, AlertSummary):
            raise ValidationError("delivery summary must be validated")
        canonical = AlertSummary.from_dict(summary.to_dict(), self.allowed_dashboard_hosts)

        def operation(records, receipts, current):
            for value in records.values():
                if value.get("idempotency_key") == idempotency_key:
                    existing = self._record(value)
                    if existing.summary.to_dict() != canonical.to_dict():
                        raise ValidationError("idempotency key cannot change delivery payload")
                    return existing
            if len(records) >= self.max_entries:
                raise CapacityError("delivery queue capacity is exhausted")
            delivery_id = f"delivery_{uuid.uuid4()}"
            value = {
                "delivery_id": delivery_id,
                "idempotency_key": idempotency_key,
                "state": "generated",
                "summary": canonical.to_dict(),
                "receipt_id": None,
                "error_code": None,
                "attempt_token": None,
                "lease_until": None,
                "created_at": current.isoformat(),
                "updated_at": current.isoformat(),
            }
            records[delivery_id] = value
            return self._record(value)

        return self._mutate(operation)

    def claim(self, delivery_id: str) -> DeliveryClaim | None:
        def operation(records, receipts, current):
            value = records.get(delivery_id)
            if value is None:
                raise ValidationError("delivery id is unknown")
            record = self._record(value)
            if record.state == "delivered":
                return None
            if record.state == "sending" and record.lease_until is not None and record.lease_until > current:
                return None
            token = f"attempt_{uuid.uuid4()}"
            value.update(
                state="sending",
                error_code=None,
                attempt_token=token,
                lease_until=(current + self.lease_duration).isoformat(),
                updated_at=current.isoformat(),
            )
            return DeliveryClaim(self._record(value), token)

        return self._mutate(operation)

    def complete(
        self, delivery_id: str, attempt: DeliveryAttempt, attempt_token: str
    ) -> DeliveryRecord:
        if not isinstance(attempt, DeliveryAttempt):
            raise ValidationError("delivery attempt must be validated")
        if not isinstance(attempt_token, str) or not attempt_token.startswith("attempt_") or OPAQUE_ID.fullmatch(attempt_token) is None:
            raise ValidationError("delivery attempt token is invalid")

        def operation(records, receipts, current):
            value = records.get(delivery_id)
            if value is None:
                raise ValidationError("delivery id is unknown")
            record = self._record(value)
            if record.state != "sending" or record.attempt_token != attempt_token:
                raise ValidationError("delivery completion has a stale attempt token")
            if attempt.provider_accepted and attempt.receipt_id is not None:
                owner = receipts.get(attempt.receipt_id)
                if owner is not None and owner != delivery_id:
                    raise ValidationError("delivery receipt is already assigned")
                receipts[attempt.receipt_id] = delivery_id
                value.update(
                    state="delivered", receipt_id=attempt.receipt_id, error_code=None,
                    attempt_token=None, lease_until=None, updated_at=current.isoformat(),
                )
            else:
                value.update(
                    state="failed", receipt_id=None,
                    error_code=attempt.error_code or "missing_receipt",
                    attempt_token=None, lease_until=None, updated_at=current.isoformat(),
                )
            return self._record(value)

        return self._mutate(operation)

    def get(self, delivery_id: str) -> DeliveryRecord:
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, ".deliveries.lock"):
                records, _ = self._load(directory_fd, current)
                if delivery_id not in records:
                    raise ValidationError("delivery id is unknown")
                return self._record(records[delivery_id])
        finally:
            os.close(directory_fd)

    def outstanding(self) -> tuple[DeliveryRecord, ...]:
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, ".deliveries.lock"):
                records, _ = self._load(directory_fd, current)
                return tuple(
                    self._record(value)
                    for value in records.values()
                    if value.get("state") != "delivered"
                )
        finally:
            os.close(directory_fd)

    def by_idempotency(self, idempotency_key: str) -> DeliveryRecord | None:
        if not isinstance(idempotency_key, str) or IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ValidationError("delivery idempotency key is invalid")
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, ".deliveries.lock"):
                records, _ = self._load(directory_fd, current)
                for value in records.values():
                    if value.get("idempotency_key") == idempotency_key:
                        return self._record(value)
                return None
        finally:
            os.close(directory_fd)


@dataclass(frozen=True, slots=True)
class MonitorResult:
    transitions: tuple[IncidentTransition, ...]
    deliveries: tuple[DeliveryRecord, ...]
    ok: bool
    unresolved: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "transitions": [asdict(item) for item in self.transitions],
            "deliveries": [item.to_dict() for item in self.deliveries],
            "ok": self.ok,
            "unresolved": list(self.unresolved),
        }


_COMPONENT_TASKS = {
    "openclaw": "health",
    "hermes": "health",
    "opportunity_os": "health",
    "dashboard": "health",
    "ngrok": "tunnel",
    "knowledge_publish": "publish",
}


class Monitor:
    def __init__(
        self,
        *,
        sentinel: IncidentSentinel,
        deliveries: DeliveryQueue,
        probes: tuple[RuntimeProbe, ...],
        delivery: DeliveryPort,
        event_hub: EventHub,
        dashboard_url: str,
        allowed_dashboard_hosts: tuple[str, ...] = (),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.sentinel = sentinel
        self.deliveries = deliveries
        self.probes = probes
        self.delivery = delivery
        self.event_hub = event_hub
        self.allowed_dashboard_hosts = validate_allowed_dashboard_hosts(allowed_dashboard_hosts)
        self.dashboard_url = canonical_dashboard_url(dashboard_url, self.allowed_dashboard_hosts)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _drain_incident_outbox(self) -> None:
        for notification in self.sentinel.pending_notifications():
            summary = AlertSummary.from_notification(notification, self.allowed_dashboard_hosts)
            self.deliveries.generate(notification.idempotency_key, summary)
            self.sentinel.ack_notification(notification.idempotency_key)

    def _attempt(self, record: DeliveryRecord) -> DeliveryRecord | None:
        claim = self.deliveries.claim(record.delivery_id)
        if claim is None:
            return None
        try:
            receipt = self.delivery.lookup(claim.record.idempotency_key)
            if receipt is not None:
                attempt = DeliveryAttempt(True, receipt, None)
            else:
                attempt = self.delivery.send(
                    claim.record.summary, claim.record.idempotency_key
                )
            return self.deliveries.complete(
                claim.record.delivery_id, attempt, claim.attempt_token
            )
        except Exception:
            try:
                return self.deliveries.complete(
                    claim.record.delivery_id,
                    DeliveryAttempt(False, None, "delivery_failed"),
                    claim.attempt_token,
                )
            except ValidationError:
                return self.deliveries.get(claim.record.delivery_id)

    def _process_deliveries(self, attempted_ids: set[str]) -> list[DeliveryRecord]:
        results = []
        for record in self.deliveries.outstanding():
            if record.delivery_id in attempted_ids:
                continue
            attempted_ids.add(record.delivery_id)
            completed = self._attempt(record)
            if completed is not None:
                results.append(completed)
        return results

    def run_once(self) -> MonitorResult:
        transitions: list[IncidentTransition] = []
        delivery_records: list[DeliveryRecord] = []
        attempted_ids: set[str] = set()
        self._drain_incident_outbox()
        delivery_records.extend(self._process_deliveries(attempted_ids))

        for probe in self.probes:
            result = probe.check()
            task = _COMPONENT_TASKS[result.component]
            if result.status == "healthy":
                for key in self.sentinel.keys_for(result.component, task):
                    error_class = key.rsplit(":", 1)[1]
                    transition = self.sentinel.observe(
                        key, True, "P1", error_class, last_success=result.last_success_at
                    )
                    transitions.append(transition)
                    if transition.notify:
                        self.event_hub.publish(
                            "incident.recovered", {"incident_id": transition.incident_id}
                        )
                continue
            error_class = result.error_code if result.error_code in ERROR_CLASSES else "probe_failed"
            severity: Literal["P0", "P1", "P2"]
            if result.status == "unknown":
                severity = "P2"
            elif result.component in {"openclaw", "dashboard"}:
                severity = "P0"
            else:
                severity = "P1"
            transition = self.sentinel.observe(
                f"{result.component}:{task}:{error_class}",
                False,
                severity,
                error_class,
                last_success=result.last_success_at,
            )
            transitions.append(transition)
            if transition.notify:
                self.event_hub.publish(
                    "incident.firing", {"incident_id": transition.incident_id}
                )

        self._drain_incident_outbox()
        delivery_records.extend(self._process_deliveries(attempted_ids))
        unresolved_records = self.deliveries.outstanding()
        unresolved = tuple(record.delivery_id for record in unresolved_records)
        return MonitorResult(
            tuple(transitions), tuple(delivery_records), not unresolved, unresolved
        )

    def boot_hook(
        self,
        boot_id: str,
        *,
        interrupted: bool,
        recovery_probe: RuntimeProbe,
    ) -> DeliveryRecord | None:
        if (
            not isinstance(boot_id, str)
            or not boot_id.startswith("boot_")
            or OPAQUE_ID.fullmatch(boot_id) is None
        ):
            raise ValidationError("boot id must be opaque")
        if not isinstance(interrupted, bool):
            raise ValidationError("interrupted must be boolean")
        if not interrupted or recovery_probe.check().status != "healthy":
            return None
        idempotency_key = f"{boot_id}:recovered"
        summary = AlertSummary(
            error_code="process_interrupted",
            impact="control_plane_unavailable",
            last_success=None,
            run_id=boot_id,
            dashboard_url=self.dashboard_url,
            suggested_action="inspect_dashboard",
            allowed_dashboard_hosts=self.allowed_dashboard_hosts,
        )
        record = self.deliveries.generate(idempotency_key, summary)
        if record.state == "delivered":
            return record
        attempted = self._attempt(record)
        return attempted if attempted is not None else self.deliveries.get(record.delivery_id)
