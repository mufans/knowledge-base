"""One-shot monitoring orchestration with receipt-backed alert delivery."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal, Protocol
from urllib.parse import urlsplit

from opportunity_os.automation.secure_runtime import (
    atomic_json_at,
    exclusive_arbitration,
    open_absolute_directory,
    read_json_at,
)
from opportunity_os.dashboard.events import EventHub
from opportunity_os.dashboard.incidents import ERROR_CLASSES, IncidentSentinel, IncidentTransition
from opportunity_os.dashboard.probes import RuntimeProbe
from opportunity_os.errors import BoundaryError, CapacityError, ValidationError


DeliveryState = Literal["generated", "queued", "delivered", "failed"]
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
    r"^(?:run|boot|rcpt|delivery)_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
INCIDENT_ID = re.compile(
    r"^inc_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
IDEMPOTENCY_KEY = re.compile(
    r"^(?:inc|boot)_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}:(?:firing|recovered)$"
)
STATE_MAX_BYTES = 1_048_576


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _safe_dashboard_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise ValidationError("dashboard URL is invalid")
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValidationError("dashboard URL may not contain credentials, query, or fragment")
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme == "http" and not loopback:
        raise ValidationError("HTTP dashboard URLs must be loopback")
    if parsed.scheme not in ({"http", "https"} if loopback else {"https"}):
        raise ValidationError("dashboard URL must use HTTPS or loopback HTTP")
    if not parsed.hostname or parsed.path not in {"", "/", "/monitoring"}:
        raise ValidationError("dashboard URL is outside the monitoring allowlist")
    return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class AlertSummary:
    """Allowlist-only alert fields; no exception, path, stderr, or arbitrary text."""

    error_code: str
    impact: Impact
    last_success: datetime | None
    run_id: str
    dashboard_url: str
    suggested_action: SuggestedAction

    def __post_init__(self) -> None:
        if self.error_code not in ERROR_CLASSES:
            raise ValidationError("alert error code is not allowlisted")
        if self.impact not in IMPACTS:
            raise ValidationError("alert impact is not allowlisted")
        if self.last_success is not None:
            object.__setattr__(self, "last_success", _utc(self.last_success))
        if not isinstance(self.run_id, str) or OPAQUE_ID.fullmatch(self.run_id) is None:
            raise ValidationError("alert run id must be opaque")
        object.__setattr__(self, "dashboard_url", _safe_dashboard_url(self.dashboard_url))
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
        """Fixed copy only; incident details never become message prose."""
        if self.error_code == "process_interrupted":
            return "曾中断并已恢复"
        return "系统监控告警"

    @classmethod
    def from_dict(cls, value: object) -> "AlertSummary":
        if not isinstance(value, dict) or set(value) != {
            "error_code", "impact", "last_success", "run_id", "dashboard_url", "suggested_action"
        }:
            raise ValidationError("stored alert summary schema is invalid")
        raw_success = value["last_success"]
        if raw_success is not None and not isinstance(raw_success, str):
            raise ValidationError("stored last success is invalid")
        try:
            last_success = datetime.fromisoformat(raw_success) if isinstance(raw_success, str) else None
        except ValueError as error:
            raise ValidationError("stored last success is invalid") from error
        return cls(
            error_code=str(value["error_code"]),
            impact=str(value["impact"]),  # type: ignore[arg-type]
            last_success=last_success,
            run_id=str(value["run_id"]),
            dashboard_url=str(value["dashboard_url"]),
            suggested_action=str(value["suggested_action"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    provider_accepted: bool
    receipt_id: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_accepted, bool):
            raise ValidationError("provider acceptance must be boolean")
        if self.receipt_id is not None and OPAQUE_ID.fullmatch(self.receipt_id) is None:
            raise ValidationError("delivery receipt must be opaque")
        if self.error_code is not None and self.error_code not in DELIVERY_ERRORS:
            raise ValidationError("delivery error code is not allowlisted")


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    delivery_id: str
    idempotency_key: str
    state: DeliveryState
    summary: AlertSummary
    receipt_id: str | None
    error_code: str | None
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
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class DeliveryPort(Protocol):
    def send(self, summary: AlertSummary) -> DeliveryAttempt: ...


class DeferredDelivery:
    """Fail closed until an authenticated OpenClaw delivery adapter is injected."""

    def send(self, summary: AlertSummary) -> DeliveryAttempt:
        return DeliveryAttempt(False, None, "delivery_failed")


class DeliveryQueue:
    def __init__(
        self,
        state_path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
        ttl: timedelta = timedelta(days=30),
        max_entries: int = 1024,
    ) -> None:
        self.path = Path(state_path).expanduser()
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise BoundaryError("delivery state path must be absolute and traversal-free")
        if ttl <= timedelta(0) or not 1 <= max_entries <= 4096:
            raise ValidationError("delivery retention bounds are invalid")
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.ttl = ttl
        self.max_entries = max_entries

    def _directory(self) -> int:
        return open_absolute_directory(self.path.parent)

    def _load(self, directory_fd: int, current: datetime) -> dict[str, dict[str, object]]:
        try:
            payload = read_json_at(directory_fd, self.path.name, max_bytes=STATE_MAX_BYTES)
        except FileNotFoundError:
            payload = {"version": 1, "deliveries": {}}
        except json.JSONDecodeError as error:
            raise ValidationError("delivery state contains invalid JSON") from error
        if payload.get("version") != 1 or not isinstance(payload.get("deliveries"), dict):
            raise ValidationError("delivery state schema is invalid")
        records = {}
        for key, value in payload["deliveries"].items():
            if not isinstance(key, str) or OPAQUE_ID.fullmatch(key) is None or not isinstance(value, dict):
                raise ValidationError("delivery state record is invalid")
            try:
                updated = _utc(datetime.fromisoformat(str(value["updated_at"])))
            except (KeyError, ValueError) as error:
                raise ValidationError("delivery state timestamp is invalid") from error
            if value.get("state") in {"generated", "queued"} or current - updated <= self.ttl:
                records[key] = value
        return records

    @staticmethod
    def _record(value: dict[str, object]) -> DeliveryRecord:
        expected_fields = {
            "delivery_id",
            "idempotency_key",
            "state",
            "summary",
            "receipt_id",
            "error_code",
            "created_at",
            "updated_at",
        }
        if set(value) != expected_fields:
            raise ValidationError("delivery record schema is invalid")
        try:
            state = str(value["state"])
            created = _utc(datetime.fromisoformat(str(value["created_at"])))
            updated = _utc(datetime.fromisoformat(str(value["updated_at"])))
        except (KeyError, ValueError) as error:
            raise ValidationError("delivery record is invalid") from error
        if state not in {"generated", "queued", "delivered", "failed"}:
            raise ValidationError("delivery state is invalid")
        delivery_id = value["delivery_id"]
        idempotency_key = value["idempotency_key"]
        if not isinstance(delivery_id, str) or OPAQUE_ID.fullmatch(delivery_id) is None:
            raise ValidationError("stored delivery id is invalid")
        if not isinstance(idempotency_key, str) or IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ValidationError("stored delivery idempotency key is invalid")
        receipt = value.get("receipt_id")
        error_code = value.get("error_code")
        if receipt is not None and (not isinstance(receipt, str) or OPAQUE_ID.fullmatch(receipt) is None):
            raise ValidationError("stored delivery receipt is invalid")
        if error_code is not None and error_code not in DELIVERY_ERRORS:
            raise ValidationError("stored delivery error code is invalid")
        return DeliveryRecord(
            delivery_id=delivery_id,
            idempotency_key=idempotency_key,
            state=state,  # type: ignore[arg-type]
            summary=AlertSummary.from_dict(value["summary"]),
            receipt_id=receipt,
            error_code=error_code,
            created_at=created,
            updated_at=updated,
        )

    @staticmethod
    def _persist(directory_fd: int, name: str, records: dict[str, dict[str, object]]) -> None:
        atomic_json_at(directory_fd, name, {"version": 1, "deliveries": records}, mode=0o600)

    def _mutate(self, operation: Callable[[dict[str, dict[str, object]], datetime], DeliveryRecord]) -> DeliveryRecord:
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, ".deliveries.lock"):
                records = self._load(directory_fd, current)
                result = operation(records, current)
                self._persist(directory_fd, self.path.name, records)
                return result
        finally:
            os.close(directory_fd)

    def generate(self, idempotency_key: str, summary: AlertSummary) -> DeliveryRecord:
        if not isinstance(idempotency_key, str) or IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ValidationError("delivery idempotency key is invalid")
        if not isinstance(summary, AlertSummary):
            raise ValidationError("delivery summary must be validated")

        def operation(records: dict[str, dict[str, object]], current: datetime) -> DeliveryRecord:
            for value in records.values():
                if value.get("idempotency_key") == idempotency_key:
                    return self._record(value)
            if len(records) >= self.max_entries:
                raise CapacityError("delivery queue capacity is exhausted")
            delivery_id = f"delivery_{uuid.uuid4()}"
            value: dict[str, object] = {
                "delivery_id": delivery_id,
                "idempotency_key": idempotency_key,
                "state": "generated",
                "summary": summary.to_dict(),
                "receipt_id": None,
                "error_code": None,
                "created_at": current.isoformat(),
                "updated_at": current.isoformat(),
            }
            records[delivery_id] = value
            return self._record(value)

        return self._mutate(operation)

    def queue(self, delivery_id: str) -> DeliveryRecord:
        def operation(records: dict[str, dict[str, object]], current: datetime) -> DeliveryRecord:
            value = records.get(delivery_id)
            if value is None:
                raise ValidationError("delivery id is unknown")
            if value.get("state") in {"generated", "failed"}:
                value.update(state="queued", error_code=None, updated_at=current.isoformat())
            elif value.get("state") not in {"queued", "delivered"}:
                raise ValidationError("delivery transition is invalid")
            return self._record(value)

        return self._mutate(operation)

    def complete(self, delivery_id: str, attempt: DeliveryAttempt) -> DeliveryRecord:
        if not isinstance(attempt, DeliveryAttempt):
            raise ValidationError("delivery attempt must be validated")

        def operation(records: dict[str, dict[str, object]], current: datetime) -> DeliveryRecord:
            value = records.get(delivery_id)
            if value is None:
                raise ValidationError("delivery id is unknown")
            if value.get("state") == "delivered":
                return self._record(value)
            if value.get("state") != "queued":
                raise ValidationError("only queued deliveries can complete")
            if attempt.provider_accepted and attempt.receipt_id is not None:
                value.update(
                    state="delivered",
                    receipt_id=attempt.receipt_id,
                    error_code=None,
                    updated_at=current.isoformat(),
                )
            else:
                value.update(
                    state="failed",
                    receipt_id=None,
                    error_code=attempt.error_code or "missing_receipt",
                    updated_at=current.isoformat(),
                )
            return self._record(value)

        return self._mutate(operation)

    def retry(self, delivery_id: str) -> DeliveryRecord:
        return self.queue(delivery_id)

    def outstanding(self) -> tuple[DeliveryRecord, ...]:
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, ".deliveries.lock"):
                records = self._load(directory_fd, current)
                return tuple(
                    self._record(value)
                    for value in records.values()
                    if value.get("state") in {"generated", "queued", "failed"}
                )
        finally:
            os.close(directory_fd)

    def by_idempotency(self, idempotency_key: str) -> DeliveryRecord | None:
        if IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise ValidationError("delivery idempotency key is invalid")
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, ".deliveries.lock"):
                records = self._load(directory_fd, current)
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

    def to_dict(self) -> dict[str, object]:
        return {
            "transitions": [asdict(item) for item in self.transitions],
            "deliveries": [item.to_dict() for item in self.deliveries],
        }


_COMPONENT_ALERTS: dict[str, tuple[str, Impact, SuggestedAction]] = {
    "openclaw": ("health", "control_plane_unavailable", "inspect_dashboard"),
    "hermes": ("health", "analysis_unavailable", "retry_task"),
    "opportunity_os": ("health", "analysis_unavailable", "inspect_dashboard"),
    "dashboard": ("health", "control_plane_unavailable", "inspect_dashboard"),
    "ngrok": ("tunnel", "remote_access_unavailable", "verify_access"),
    "knowledge_publish": ("publish", "publishing_unavailable", "retry_task"),
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
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.sentinel = sentinel
        self.deliveries = deliveries
        self.probes = probes
        self.delivery = delivery
        self.event_hub = event_hub
        self.dashboard_url = _safe_dashboard_url(dashboard_url)
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _send(self, record: DeliveryRecord) -> DeliveryRecord:
        queued = self.deliveries.queue(record.delivery_id)
        try:
            attempt = self.delivery.send(queued.summary)
        except Exception:
            attempt = DeliveryAttempt(False, None, "delivery_failed")
        return self.deliveries.complete(queued.delivery_id, attempt)

    def _summary(
        self,
        transition: IncidentTransition,
        *,
        last_success: datetime | None,
    ) -> AlertSummary:
        source = transition.key.split(":", 1)[0]
        _, impact, action = _COMPONENT_ALERTS[source]
        return AlertSummary(
            error_code=transition.error_class,
            impact=impact,
            last_success=last_success,
            run_id=f"run_{uuid.uuid4()}",
            dashboard_url=self.dashboard_url,
            suggested_action=action,
        )

    def _notify(
        self,
        transition: IncidentTransition,
        *,
        last_success: datetime | None,
    ) -> DeliveryRecord:
        summary = self._summary(transition, last_success=last_success)
        record = self.deliveries.generate(
            f"{transition.incident_id}:{transition.kind}", summary
        )
        event_type = "incident.firing" if transition.kind == "firing" else "incident.recovered"
        self.event_hub.publish(event_type, {"incident_id": transition.incident_id})
        return self._send(record)

    def run_once(self) -> MonitorResult:
        transitions: list[IncidentTransition] = []
        delivery_records: list[DeliveryRecord] = []
        for outstanding in self.deliveries.outstanding():
            delivery_records.append(self._send(outstanding))

        for probe in self.probes:
            result = probe.check()
            task, _, _ = _COMPONENT_ALERTS[result.component]
            if result.status == "healthy":
                for key in self.sentinel.keys_for(result.component, task):
                    error_class = key.rsplit(":", 1)[1]
                    transition = self.sentinel.observe(key, True, "P1", error_class)
                    transitions.append(transition)
                    if transition.notify:
                        delivery_records.append(
                            self._notify(transition, last_success=result.last_success_at)
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
            key = f"{result.component}:{task}:{error_class}"
            transition = self.sentinel.observe(key, False, severity, error_class)
            transitions.append(transition)
            if transition.notify:
                delivery_records.append(
                    self._notify(transition, last_success=result.last_success_at)
                )
        return MonitorResult(tuple(transitions), tuple(delivery_records))

    def boot_hook(
        self,
        boot_id: str,
        *,
        interrupted: bool,
        recovery_probe: RuntimeProbe,
    ) -> DeliveryRecord | None:
        if not isinstance(boot_id, str) or not boot_id.startswith("boot_") or OPAQUE_ID.fullmatch(boot_id) is None:
            raise ValidationError("boot id must be opaque")
        if not isinstance(interrupted, bool):
            raise ValidationError("interrupted must be boolean")
        if not interrupted or recovery_probe.check().status != "healthy":
            return None
        idempotency_key = f"{boot_id}:recovered"
        if self.deliveries.by_idempotency(idempotency_key) is not None:
            return None
        summary = AlertSummary(
            error_code="process_interrupted",
            impact="control_plane_unavailable",
            last_success=_utc(self.now()),
            run_id=boot_id,
            dashboard_url=self.dashboard_url,
            suggested_action="inspect_dashboard",
        )
        return self._send(self.deliveries.generate(idempotency_key, summary))
