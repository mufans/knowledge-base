"""Persistent, bounded incident hysteresis and restart budgets."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlsplit, urlunsplit

from opportunity_os.automation.secure_runtime import (
    atomic_json_at,
    exclusive_arbitration,
    open_absolute_directory,
    read_json_at,
)
from opportunity_os.errors import BoundaryError, CapacityError, ValidationError


Severity = Literal["P0", "P1", "P2"]
TransitionKind = Literal[
    "healthy", "pending", "firing", "suppressed", "recovering", "recovered"
]

SOURCES = frozenset(
    {
        "openclaw",
        "hermes",
        "opportunity_os",
        "dashboard",
        "ngrok",
        "knowledge_publish",
        "delivery",
        "automation",
    }
)
TASKS = frozenset(
    {
        "gateway",
        "health",
        "daily",
        "weekly",
        "biweekly",
        "six-week",
        "quarterly",
        "sync",
        "publish",
        "delivery",
        "tunnel",
    }
)
ERROR_CLASSES = frozenset(
    {
        "timeout",
        "probe_timeout",
        "probe_unavailable",
        "probe_failed",
        "nonzero_exit",
        "publish_failed",
        "delivery_failed",
        "missing_receipt",
        "process_interrupted",
        "unauthorized_access",
        "privacy_risk",
    }
)
COMPONENTS = frozenset(
    {"openclaw", "hermes", "opportunity_os", "dashboard", "ngrok", "knowledge_publish"}
)
THRESHOLDS: dict[Severity, int] = {"P0": 1, "P1": 2, "P2": 3}
STATE_MAX_BYTES = 512 * 1024
_UUID_ID = re.compile(
    r"^(?:inc|run)_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_NOTIFICATION_KEY = re.compile(
    r"^inc_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}:(?:firing|recovered)$"
)
_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
_IMPACT_BY_SOURCE = {
    "openclaw": ("control_plane_unavailable", "inspect_dashboard"),
    "hermes": ("analysis_unavailable", "retry_task"),
    "opportunity_os": ("analysis_unavailable", "inspect_dashboard"),
    "dashboard": ("control_plane_unavailable", "inspect_dashboard"),
    "ngrok": ("remote_access_unavailable", "verify_access"),
    "knowledge_publish": ("publishing_unavailable", "retry_task"),
    "delivery": ("delivery_unavailable", "verify_delivery"),
    "automation": ("analysis_unavailable", "retry_task"),
}


def validate_allowed_dashboard_hosts(hosts: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(hosts, tuple) or len(hosts) > 16:
        raise ValidationError("dashboard host allowlist is invalid")
    if any(
        not isinstance(host, str)
        or not _HOST.fullmatch(host)
        or host != host.casefold()
        or "." not in host
        or ".." in host
        for host in hosts
    ):
        raise ValidationError("dashboard host allowlist contains a noncanonical host")
    if len(set(hosts)) != len(hosts):
        raise ValidationError("dashboard host allowlist contains duplicates")
    return hosts


def canonical_dashboard_url(value: str, allowed_hosts: tuple[str, ...] = ()) -> str:
    allowed_hosts = validate_allowed_dashboard_hosts(allowed_hosts)
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > 512:
        raise ValidationError("dashboard URL is invalid")
    if any(character.isspace() for character in value):
        raise ValidationError("dashboard URL contains whitespace")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValidationError("dashboard URL port is invalid") from error
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValidationError("dashboard URL may not contain credentials, query, or fragment")
    if port is not None and not 1 <= port <= 65535:
        raise ValidationError("dashboard URL port is outside the valid range")
    if parsed.path != "/monitoring" or not parsed.hostname:
        raise ValidationError("dashboard URL path or host is invalid")
    host = parsed.hostname
    loopback = host in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme == "http":
        if not loopback:
            raise ValidationError("HTTP dashboard URL must be exact loopback")
    elif parsed.scheme == "https":
        if loopback or host not in allowed_hosts or port not in {None, 443}:
            raise ValidationError("HTTPS dashboard host or port is not allowlisted")
    else:
        raise ValidationError("dashboard URL scheme is invalid")
    canonical_host = f"[{host}]" if ":" in host else host
    canonical_netloc = canonical_host if port is None else f"{canonical_host}:{port}"
    canonical = urlunsplit((parsed.scheme, canonical_netloc, parsed.path, "", ""))
    if value != canonical:
        raise ValidationError("dashboard URL must use canonical spelling")
    return canonical


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValidationError("persisted timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValidationError("persisted timestamp is invalid") from error
    return _utc(parsed)


def _validate_key(key: str, error_class: str) -> tuple[str, str, str]:
    if not isinstance(key, str) or key.count(":") != 2:
        raise ValidationError("incident key must be source:task:error_class")
    source, task, key_error = key.split(":")
    if source not in SOURCES or task not in TASKS or key_error not in ERROR_CLASSES:
        raise ValidationError("incident key contains a non-allowlisted value")
    if error_class not in ERROR_CLASSES or error_class != key_error:
        raise ValidationError("error_class must be allowlisted and match the incident key")
    return source, task, key_error


@dataclass(frozen=True, slots=True)
class IncidentTransition:
    kind: TransitionKind
    incident_id: str
    key: str
    severity: Severity
    error_class: str
    notify: bool = False


@dataclass(frozen=True, slots=True)
class IncidentNotification:
    idempotency_key: str
    incident_id: str
    kind: Literal["firing", "recovered"]
    error_code: str
    impact: str
    last_success: datetime | None
    run_id: str
    dashboard_url: str
    suggested_action: str
    created_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "idempotency_key": self.idempotency_key,
            "incident_id": self.incident_id,
            "kind": self.kind,
            "error_code": self.error_code,
            "impact": self.impact,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "run_id": self.run_id,
            "dashboard_url": self.dashboard_url,
            "suggested_action": self.suggested_action,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "IncidentNotification":
        fields = {
            "idempotency_key", "incident_id", "kind", "error_code", "impact",
            "last_success", "run_id", "dashboard_url", "suggested_action", "created_at",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ValidationError("incident notification schema is invalid")
        incident_id = value["incident_id"]
        kind = value["kind"]
        if not isinstance(incident_id, str) or not incident_id.startswith("inc_") or _UUID_ID.fullmatch(incident_id) is None:
            raise ValidationError("notification incident id is invalid")
        if kind not in {"firing", "recovered"} or value["idempotency_key"] != f"{incident_id}:{kind}":
            raise ValidationError("notification idempotency identity is invalid")
        if value["error_code"] not in ERROR_CLASSES:
            raise ValidationError("notification error code is invalid")
        if value["impact"] not in {item[0] for item in _IMPACT_BY_SOURCE.values()}:
            raise ValidationError("notification impact is invalid")
        if value["suggested_action"] not in {item[1] for item in _IMPACT_BY_SOURCE.values()}:
            raise ValidationError("notification action is invalid")
        if not isinstance(value["run_id"], str) or not value["run_id"].startswith("run_") or _UUID_ID.fullmatch(value["run_id"]) is None:
            raise ValidationError("notification run id is invalid")
        last_success = None if value["last_success"] is None else _parse_time(value["last_success"])
        created_at = _parse_time(value["created_at"])
        if not isinstance(value["dashboard_url"], str):
            raise ValidationError("notification dashboard URL is invalid")
        return cls(
            idempotency_key=str(value["idempotency_key"]), incident_id=incident_id,
            kind=kind, error_code=str(value["error_code"]), impact=str(value["impact"]),
            last_success=last_success, run_id=str(value["run_id"]),
            dashboard_url=str(value["dashboard_url"]),
            suggested_action=str(value["suggested_action"]), created_at=created_at,
        )


class _LockedJsonState:
    def __init__(self, path: str | Path, lock_name: str) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise BoundaryError("runtime state path must be absolute and traversal-free")
        if not self.path.name or "/" in self.path.name:
            raise BoundaryError("runtime state file name is invalid")
        self.lock_name = lock_name

    def _directory(self) -> int:
        return open_absolute_directory(self.path.parent)

    def _read(self, directory_fd: int, default: dict[str, object]) -> dict[str, object]:
        try:
            return read_json_at(directory_fd, self.path.name, max_bytes=STATE_MAX_BYTES)
        except FileNotFoundError:
            return default
        except json.JSONDecodeError as error:
            raise ValidationError("runtime state contains invalid JSON") from error

    def _write(self, directory_fd: int, payload: dict[str, object]) -> None:
        atomic_json_at(
            directory_fd, self.path.name, payload, mode=0o600, max_bytes=STATE_MAX_BYTES
        )


class IncidentSentinel(_LockedJsonState):
    """Serialize incident transitions across processes without storing raw errors."""

    def __init__(
        self,
        state_path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
        cooldown: timedelta = timedelta(hours=6),
        ttl: timedelta = timedelta(days=30),
        max_entries: int = 512,
        max_notifications: int = 1024,
        dashboard_url: str = "http://127.0.0.1:8765/monitoring",
        allowed_dashboard_hosts: tuple[str, ...] = (),
    ) -> None:
        super().__init__(state_path, ".incidents.lock")
        if cooldown <= timedelta(0) or ttl <= timedelta(0):
            raise ValidationError("incident cooldown and TTL must be positive")
        if not 1 <= max_entries <= 4096:
            raise ValidationError("incident capacity is out of bounds")
        if not 1 <= max_notifications <= 4096:
            raise ValidationError("incident notification capacity is out of bounds")
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.cooldown = cooldown
        self.ttl = ttl
        self.max_entries = max_entries
        self.max_notifications = max_notifications
        self.allowed_dashboard_hosts = validate_allowed_dashboard_hosts(allowed_dashboard_hosts)
        self.dashboard_url = canonical_dashboard_url(dashboard_url, self.allowed_dashboard_hosts)

    def _load(
        self, directory_fd: int, current: datetime
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
        payload = self._read(
            directory_fd, {"version": 2, "incidents": {}, "notification_outbox": {}}
        )
        migrated_from_v1 = payload.get("version") == 1 and isinstance(payload.get("incidents"), dict)
        if migrated_from_v1:
            payload = {"version": 2, "incidents": payload["incidents"], "notification_outbox": {}}
        if (
            payload.get("version") != 2
            or not isinstance(payload.get("incidents"), dict)
            or not isinstance(payload.get("notification_outbox"), dict)
        ):
            raise ValidationError("incident state schema is invalid")
        records: dict[str, dict[str, object]] = {}
        for key, value in payload["incidents"].items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValidationError("incident state record is invalid")
            error_class = value.get("error_class")
            if not isinstance(error_class, str):
                raise ValidationError("incident error class is invalid")
            _validate_key(key, error_class)
            if value.get("severity") not in THRESHOLDS:
                raise ValidationError("incident severity is invalid")
            incident_id = value.get("incident_id")
            try:
                uuid.UUID(str(incident_id).removeprefix("inc_"), version=4)
            except (ValueError, AttributeError) as error:
                raise ValidationError("incident id is invalid") from error
            if not isinstance(incident_id, str) or not incident_id.startswith("inc_"):
                raise ValidationError("incident id is invalid")
            if value.get("phase") not in {"inactive", "pending", "firing"}:
                raise ValidationError("incident phase is invalid")
            for counter in ("failure_count", "success_count"):
                if not isinstance(value.get(counter), int) or not 0 <= value[counter] <= 1_000_000:
                    raise ValidationError("incident counter is invalid")
            if value.get("last_fired_at") is not None:
                _parse_time(value["last_fired_at"])
            updated = _parse_time(value.get("updated_at"))
            if current - updated <= self.ttl or value.get("phase") == "firing":
                records[key] = value
        outbox: dict[str, dict[str, object]] = {}
        for idempotency_key, value in payload["notification_outbox"].items():
            notification = IncidentNotification.from_dict(value)
            if idempotency_key != notification.idempotency_key:
                raise ValidationError("incident outbox key is invalid")
            canonical_dashboard_url(notification.dashboard_url, self.allowed_dashboard_hosts)
            outbox[idempotency_key] = value
        if migrated_from_v1:
            for key, record in records.items():
                if record.get("phase") != "firing":
                    continue
                incident_id = str(record["incident_id"])
                idempotency_key = f"{incident_id}:firing"
                source = key.split(":", 1)[0]
                impact, action = _IMPACT_BY_SOURCE[source]
                notification = IncidentNotification(
                    idempotency_key=idempotency_key,
                    incident_id=incident_id,
                    kind="firing",
                    error_code=str(record["error_class"]),
                    impact=impact,
                    last_success=None,
                    run_id=f"run_{incident_id.removeprefix('inc_')}",
                    dashboard_url=self.dashboard_url,
                    suggested_action=action,
                    created_at=_parse_time(record["updated_at"]),
                )
                outbox[idempotency_key] = notification.to_dict()
        if len(outbox) > self.max_notifications:
            raise CapacityError("incident notification outbox exceeds capacity")
        return records, outbox

    def _persist(
        self,
        directory_fd: int,
        records: dict[str, dict[str, object]],
        outbox: dict[str, dict[str, object]],
    ) -> None:
        self._write(
            directory_fd,
            {"version": 2, "incidents": records, "notification_outbox": outbox},
        )

    @staticmethod
    def _transition(record: dict[str, object], key: str, kind: TransitionKind, notify: bool = False) -> IncidentTransition:
        return IncidentTransition(
            kind=kind,
            incident_id=str(record["incident_id"]),
            key=key,
            severity=str(record["severity"]),  # type: ignore[arg-type]
            error_class=str(record["error_class"]),
            notify=notify,
        )

    def observe(
        self,
        key: str,
        ok: bool,
        severity: Severity,
        error_class: str,
        *,
        last_success: datetime | None = None,
        run_id: str | None = None,
    ) -> IncidentTransition:
        _validate_key(key, error_class)
        if severity not in THRESHOLDS:
            raise ValidationError("severity must be P0, P1, or P2")
        if not isinstance(ok, bool):
            raise ValidationError("ok must be boolean")
        current = _utc(self.now())
        if last_success is not None:
            last_success = _utc(last_success)
        if run_id is not None and (
            not isinstance(run_id, str)
            or not run_id.startswith("run_")
            or _UUID_ID.fullmatch(run_id) is None
        ):
            raise ValidationError("incident notification run id must be opaque")
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                records, outbox = self._load(directory_fd, current)
                record = records.get(key)
                if record is None:
                    if len(records) >= self.max_entries:
                        raise CapacityError("incident state capacity is exhausted")
                    record = {
                        "incident_id": f"inc_{uuid.uuid4()}",
                        "severity": severity,
                        "error_class": error_class,
                        "phase": "inactive",
                        "failure_count": 0,
                        "success_count": 0,
                        "last_fired_at": None,
                        "updated_at": current.isoformat(),
                    }
                    records[key] = record
                elif record.get("error_class") != error_class or (
                    not ok and record.get("severity") != severity
                ):
                    raise ValidationError("incident identity cannot change severity or error class")

                phase = record.get("phase")
                if phase not in {"inactive", "pending", "firing"}:
                    raise ValidationError("incident phase is invalid")
                record["updated_at"] = current.isoformat()

                if ok:
                    record["failure_count"] = 0
                    if phase == "firing":
                        successes = int(record.get("success_count", 0)) + 1
                        record["success_count"] = successes
                        if successes >= 2:
                            record["phase"] = "inactive"
                            record["success_count"] = 0
                            transition = self._transition(record, key, "recovered", True)
                        else:
                            transition = self._transition(record, key, "recovering")
                    else:
                        record["phase"] = "inactive"
                        record["success_count"] = 0
                        transition = self._transition(record, key, "healthy")
                else:
                    record["success_count"] = 0
                    if phase == "firing":
                        transition = self._transition(record, key, "suppressed")
                    else:
                        if phase == "inactive" and int(record.get("failure_count", 0)) == 0:
                            record["incident_id"] = f"inc_{uuid.uuid4()}"
                        failures = int(record.get("failure_count", 0)) + 1
                        record["failure_count"] = failures
                        last_fired_raw = record.get("last_fired_at")
                        cooled = (
                            last_fired_raw is None
                            or current - _parse_time(last_fired_raw) >= self.cooldown
                        )
                        if failures >= THRESHOLDS[severity] and cooled:
                            record["phase"] = "firing"
                            record["last_fired_at"] = current.isoformat()
                            transition = self._transition(record, key, "firing", True)
                        elif failures >= THRESHOLDS[severity]:
                            record["phase"] = "pending"
                            transition = self._transition(record, key, "suppressed")
                        else:
                            record["phase"] = "pending"
                            transition = self._transition(record, key, "pending")

                if transition.notify:
                    idempotency_key = f"{transition.incident_id}:{transition.kind}"
                    if idempotency_key not in outbox:
                        if len(outbox) >= self.max_notifications:
                            raise CapacityError("incident notification outbox is full")
                        source = key.split(":", 1)[0]
                        impact, action = _IMPACT_BY_SOURCE[source]
                        notification = IncidentNotification(
                            idempotency_key=idempotency_key,
                            incident_id=transition.incident_id,
                            kind=transition.kind,  # type: ignore[arg-type]
                            error_code=transition.error_class,
                            impact=impact,
                            last_success=last_success,
                            run_id=run_id or f"run_{transition.incident_id.removeprefix('inc_')}",
                            dashboard_url=self.dashboard_url,
                            suggested_action=action,
                            created_at=current,
                        )
                        outbox[idempotency_key] = notification.to_dict()
                self._persist(directory_fd, records, outbox)
                return transition
        finally:
            os.close(directory_fd)

    def active_keys(self, source: str, task: str) -> tuple[str, ...]:
        if source not in SOURCES or task not in TASKS:
            raise ValidationError("source and task must be allowlisted")
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                records, _ = self._load(directory_fd, current)
                return tuple(
                    key
                    for key, value in records.items()
                    if key.startswith(f"{source}:{task}:") and value.get("phase") == "firing"
                )
        finally:
            os.close(directory_fd)

    def keys_for(self, source: str, task: str) -> tuple[str, ...]:
        """Return persisted safe keys so successful probes can reset/recover them."""
        if source not in SOURCES or task not in TASKS:
            raise ValidationError("source and task must be allowlisted")
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                records, _ = self._load(directory_fd, current)
                return tuple(key for key in records if key.startswith(f"{source}:{task}:"))
        finally:
            os.close(directory_fd)

    def pending_notifications(self) -> tuple[IncidentNotification, ...]:
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                _, outbox = self._load(directory_fd, current)
                return tuple(IncidentNotification.from_dict(value) for value in outbox.values())
        finally:
            os.close(directory_fd)

    def ack_notification(self, idempotency_key: str) -> bool:
        if not isinstance(idempotency_key, str) or _NOTIFICATION_KEY.fullmatch(idempotency_key) is None:
            raise ValidationError("incident notification idempotency key is invalid")
        current = _utc(self.now())
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                records, outbox = self._load(directory_fd, current)
                removed = outbox.pop(idempotency_key, None) is not None
                if removed:
                    self._persist(directory_fd, records, outbox)
                return removed
        finally:
            os.close(directory_fd)


class RestartBudget(_LockedJsonState):
    """Allow at most one restart per rolling hour and two per rolling 24 hours."""

    def __init__(self, state_path: str | Path, *, max_components: int = len(COMPONENTS)) -> None:
        super().__init__(state_path, ".restart-budget.lock")
        if not 1 <= max_components <= len(COMPONENTS):
            raise ValidationError("restart budget capacity is out of bounds")
        self.max_components = max_components

    def allow(self, component: str, now: datetime) -> bool:
        if component not in COMPONENTS:
            raise ValidationError("restart component is not allowlisted")
        current = _utc(now)
        directory_fd = self._directory()
        try:
            with exclusive_arbitration(directory_fd, self.lock_name):
                payload = self._read(directory_fd, {"version": 1, "components": {}})
                if payload.get("version") != 1 or not isinstance(payload.get("components"), dict):
                    raise ValidationError("restart budget schema is invalid")
                components: dict[str, list[str]] = {}
                for stored_component, stored_attempts in payload["components"].items():
                    if stored_component not in COMPONENTS or not isinstance(stored_attempts, list):
                        raise ValidationError("restart budget record is invalid")
                    parsed_attempts = [_parse_time(item) for item in stored_attempts]
                    if any(value > current for value in parsed_attempts):
                        raise ValidationError("restart budget contains a future attempt")
                    retained = [
                        value for value in parsed_attempts
                        if current - value < timedelta(hours=24)
                    ]
                    if retained:
                        components[stored_component] = [value.isoformat() for value in retained]
                raw = components.get(component, [])
                attempts = [_parse_time(value) for value in raw]
                if attempts and current < max(attempts):
                    raise ValidationError("restart budget timestamps must be monotonic")
                attempts = [value for value in attempts if current - value < timedelta(hours=24)]
                allowed = not any(current - value < timedelta(hours=1) for value in attempts) and len(attempts) < 2
                if allowed:
                    if component not in components and len(components) >= self.max_components:
                        raise CapacityError("restart budget capacity is exhausted")
                    attempts.append(current)
                components[component] = [value.isoformat() for value in attempts]
                self._write(directory_fd, {"version": 1, "components": components})
                return allowed
        finally:
            os.close(directory_fd)
