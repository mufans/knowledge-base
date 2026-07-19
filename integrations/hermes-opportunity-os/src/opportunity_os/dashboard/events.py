"""Bounded, metadata-only events for authenticated dashboard SSE clients."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
import threading
from collections import deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Literal


MAX_EVENTS = 1_000
MAX_JOURNAL_READ_BYTES = 64 * 1_024
MAX_JOURNAL_RECORD_BYTES = 16 * 1_024
JOURNAL_ANCHOR_BYTES = 64
_COMPONENTS = frozenset(
    {"openclaw", "hermes", "opportunity_os", "dashboard", "ngrok", "knowledge_publish"}
)
_COMPONENT_STATUSES = frozenset({"healthy", "degraded", "down", "unknown"})
_INVALIDATION_SCOPES = frozenset({"private_state"})
_INCIDENT_ID = re.compile(
    r"^inc_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CONVERSATION_TASK_ID = re.compile(
    r"^conv_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CONVERSATION_TARGETS = frozenset({"openclaw", "hermes"})


def _is_component(value: object) -> bool:
    return isinstance(value, str) and value in _COMPONENTS


def _is_component_status(value: object) -> bool:
    return isinstance(value, str) and value in _COMPONENT_STATUSES


def _is_invalidation_scope(value: object) -> bool:
    return isinstance(value, str) and value in _INVALIDATION_SCOPES


def _is_incident_id(value: object) -> bool:
    return isinstance(value, str) and _INCIDENT_ID.fullmatch(value) is not None


def _is_conversation_task_id(value: object) -> bool:
    return isinstance(value, str) and _CONVERSATION_TASK_ID.fullmatch(value) is not None


def _is_conversation_target(value: object) -> bool:
    return isinstance(value, str) and value in _CONVERSATION_TARGETS


_EVENT_SCHEMAS = {
    "state.invalidated": {"scope": _is_invalidation_scope},
    "component.updated": {"component": _is_component, "status": _is_component_status},
    "incident.firing": {"incident_id": _is_incident_id},
    "incident.recovered": {"incident_id": _is_incident_id},
    "conversation.started": {
        "task_id": _is_conversation_task_id,
        "target": _is_conversation_target,
    },
    "conversation.completed": {
        "task_id": _is_conversation_task_id,
        "target": _is_conversation_target,
    },
    "conversation.failed": {
        "task_id": _is_conversation_task_id,
        "target": _is_conversation_target,
    },
}
_JOURNAL_EVENTS = frozenset(
    {
        ("save_opportunity", "opportunity"),
        ("record_experiment", "experiment"),
        ("set_direction", "direction"),
        ("save_review", "review"),
        ("record_tech_state", "tech_state"),
    }
)


@dataclass(frozen=True, slots=True)
class DashboardEvent:
    """One replayable notification containing identifiers, never entity bodies."""

    id: str
    type: str
    payload: Mapping[str, str]
    at: datetime

    def wire_payload(self) -> dict[str, str]:
        return {
            "event_id": self.id,
            "type": self.type,
            **self.payload,
            "at": self.at.isoformat(),
        }


BridgeState = Literal["starting", "ready", "unavailable", "stopped"]
BridgeErrorCode = Literal["io_failure"]


@dataclass(frozen=True, slots=True)
class BridgeHealthSnapshot:
    state: BridgeState
    error_code: BridgeErrorCode | None
    revision: int


class EventBridgeHealth:
    """In-memory readiness state containing safe enums and no exception details."""

    def __init__(self) -> None:
        self.state: BridgeState = "starting"
        self.error_code: BridgeErrorCode | None = None
        self.revision = 0
        self._changed: asyncio.Event | None = None

    def snapshot(self) -> BridgeHealthSnapshot:
        return BridgeHealthSnapshot(self.state, self.error_code, self.revision)

    def _transition(self, state: BridgeState, error_code: BridgeErrorCode | None = None) -> None:
        if self.state == state and self.error_code == error_code:
            return
        self.state = state
        self.error_code = error_code
        self.revision += 1
        if self._changed is not None:
            self._changed.set()
        self._changed = asyncio.Event()

    def set_ready(self) -> None:
        self._transition("ready")

    def set_unavailable(self, error_code: BridgeErrorCode = "io_failure") -> None:
        self._transition("unavailable", error_code)

    def set_stopped(self) -> None:
        self._transition("stopped")

    async def wait_after(self, revision: int) -> BridgeHealthSnapshot:
        while self.revision <= revision:
            if self._changed is None:
                self._changed = asyncio.Event()
            changed = self._changed
            await changed.wait()
        return self.snapshot()


@dataclass(frozen=True, slots=True)
class _Subscriber:
    queue: asyncio.Queue[DashboardEvent]
    loop: asyncio.AbstractEventLoop


class EventHub:
    """Keep a bounded replay window while persisting only the monotonic cursor."""

    def __init__(self, cursor_path: str | Path, *, max_events: int = MAX_EVENTS) -> None:
        if max_events < 1 or max_events > MAX_EVENTS:
            raise ValueError(f"max_events must be between 1 and {MAX_EVENTS}")
        self.cursor_path = Path(cursor_path)
        self._max_events = max_events
        self._events: deque[DashboardEvent] = deque(maxlen=max_events)
        self._subscribers: set[_Subscriber] = set()
        self._lock = threading.RLock()
        self._cursor = self._read_cursor()

    def _read_cursor(self) -> int:
        if not self.cursor_path.is_file():
            return 0
        raw = self.cursor_path.read_text(encoding="utf-8").strip()
        if not raw.isdigit():
            raise ValueError("event cursor must be a non-negative integer")
        return int(raw)

    def _persist_cursor(self) -> None:
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".event-cursor.", suffix=".tmp", dir=self.cursor_path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(f"{self._cursor}\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.cursor_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _validate(event_type: str, payload: Mapping[str, object]) -> dict[str, str]:
        schema = _EVENT_SCHEMAS.get(event_type)
        if schema is None:
            raise ValueError("event payload uses an unsupported event type")
        if set(payload) != set(schema):
            raise ValueError("event payload keys must exactly match the event schema")
        if any(not validator(payload[key]) for key, validator in schema.items()):
            raise ValueError("event payload contains invalid metadata")
        return {key: str(payload[key]) for key in schema}

    def publish(self, event_type: str, payload: Mapping[str, object]) -> DashboardEvent:
        metadata = self._validate(event_type, payload)
        with self._lock:
            self._cursor += 1
            event = DashboardEvent(
                id=str(self._cursor),
                type=event_type,
                payload=MappingProxyType(metadata),
                at=datetime.now(timezone.utc),
            )
            try:
                self._persist_cursor()
            except OSError:
                self._cursor -= 1
                raise
            self._events.append(event)
            subscribers = tuple(self._subscribers)

        for subscriber in subscribers:
            def enqueue(target: _Subscriber = subscriber) -> None:
                if target.queue.full():
                    target.queue.get_nowait()
                target.queue.put_nowait(event)

            subscriber.loop.call_soon_threadsafe(enqueue)
        return event

    def replay(self, last_event_id: str | None) -> list[DashboardEvent]:
        if last_event_id in (None, ""):
            cursor = 0
        elif last_event_id.isdigit():
            cursor = int(last_event_id)
        else:
            raise ValueError("last_event_id must be a non-negative integer")
        with self._lock:
            return [event for event in self._events if int(event.id) > cursor]

    async def subscribe(self, last_event_id: str | None) -> AsyncIterator[DashboardEvent]:
        subscriber = _Subscriber(asyncio.Queue(maxsize=self._max_events), asyncio.get_running_loop())
        with self._lock:
            replay = self.replay(last_event_id)
            self._subscribers.add(subscriber)
        try:
            for event in replay:
                yield event
            while True:
                yield await subscriber.queue.get()
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)


class EventJournalTailer:
    """Map new private journal records to one content-free invalidation event."""

    def __init__(
        self,
        journal_path: str | Path,
        event_hub: EventHub,
        *,
        poll_interval: float = 0.25,
        backoff_initial: float = 0.25,
        backoff_max: float = 5.0,
    ) -> None:
        if not 0.01 <= poll_interval <= 5:
            raise ValueError("poll_interval must be between 0.01 and 5 seconds")
        if not 0.01 <= backoff_initial <= backoff_max <= 30:
            raise ValueError("backoff must satisfy 0.01 <= initial <= max <= 30 seconds")
        self.journal_path = Path(journal_path).expanduser().resolve()
        self.event_hub = event_hub
        self.poll_interval = poll_interval
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.retry_delay = backoff_initial
        self.health = EventBridgeHealth()
        self._initialized = False
        self._identity: tuple[int, int] | None = None
        self._position = 0
        self._pending = b""
        self._anchor_start = 0
        self._anchor_digest: bytes | None = None

    @staticmethod
    def _file_identity(stat_result: os.stat_result) -> tuple[int, int]:
        return stat_result.st_dev, stat_result.st_ino

    def start(self) -> None:
        """Set the cursor to EOF so service startup never replays historical records."""
        try:
            stat_result = self.journal_path.stat()
        except FileNotFoundError:
            self._identity = None
            self._position = 0
        else:
            self._identity = self._file_identity(stat_result)
            self._position = stat_result.st_size
        self._pending = b""
        self._initialized = True
        self._capture_anchor()

    def initialize(self) -> bool:
        try:
            self.start()
        except OSError:
            self.health.set_unavailable()
            return False
        self.retry_delay = self.backoff_initial
        self.health.set_ready()
        return True

    def _reset_for_file(self, identity: tuple[int, int], *, position: int = 0) -> None:
        self._identity = identity
        self._position = position
        self._pending = b""
        self._capture_anchor()

    def _capture_anchor(self) -> None:
        self._anchor_start = max(0, self._position - JOURNAL_ANCHOR_BYTES)
        try:
            with self.journal_path.open("rb") as handle:
                handle.seek(self._anchor_start)
                value = handle.read(self._position - self._anchor_start)
        except FileNotFoundError:
            self._anchor_digest = None
            return
        self._anchor_digest = hashlib.sha256(value).digest()

    def _anchor_matches(self) -> bool | None:
        if self._anchor_digest is None:
            return self._position == 0
        try:
            with self.journal_path.open("rb") as handle:
                handle.seek(self._anchor_start)
                value = handle.read(self._position - self._anchor_start)
        except FileNotFoundError:
            return None
        return hashlib.sha256(value).digest() == self._anchor_digest

    def _publish_record(self, line: bytes) -> bool:
        if not line.strip() or len(line) > MAX_JOURNAL_RECORD_BYTES:
            return False
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(record, dict):
            return False
        marker = (record.get("action"), record.get("entity_type"))
        if marker not in _JOURNAL_EVENTS:
            return False
        self.event_hub.publish("state.invalidated", {"scope": "private_state"})
        return True

    def _poll_once(self) -> int:
        if not self._initialized:
            self.start()
            return 0
        try:
            stat_result = self.journal_path.stat()
        except FileNotFoundError:
            self._identity = None
            self._position = 0
            self._pending = b""
            self._anchor_digest = None
            return 0

        identity = self._file_identity(stat_result)
        if self._identity is None or identity != self._identity or stat_result.st_size < self._position:
            self._reset_for_file(identity)
        else:
            anchor_matches = self._anchor_matches()
            if anchor_matches is None:
                self._identity = None
                self._position = 0
                self._pending = b""
                self._anchor_digest = None
                return 0
            if not anchor_matches:
                self._reset_for_file(identity)
        if stat_result.st_size == self._position:
            return 0

        try:
            with self.journal_path.open("rb") as handle:
                handle.seek(self._position)
                chunk = handle.read(MAX_JOURNAL_READ_BYTES)
        except FileNotFoundError:
            self._identity = None
            self._position = 0
            self._pending = b""
            self._anchor_digest = None
            return 0
        self._position += len(chunk)
        self._capture_anchor()
        records = (self._pending + chunk).split(b"\n")
        self._pending = records.pop()
        if len(self._pending) > MAX_JOURNAL_RECORD_BYTES:
            self._pending = b""
        return sum(self._publish_record(record) for record in records)

    def poll_once(self) -> int:
        """Read one bounded chunk, rolling back the read cursor on I/O failure."""
        checkpoint = (
            self._identity,
            self._position,
            self._pending,
            self._anchor_start,
            self._anchor_digest,
        )
        try:
            return self._poll_once()
        except OSError:
            (
                self._identity,
                self._position,
                self._pending,
                self._anchor_start,
                self._anchor_digest,
            ) = checkpoint
            raise

    async def run(self, *, initialized: bool = False) -> None:
        needs_initialize = not initialized
        try:
            while True:
                if self.health.state == "unavailable":
                    await asyncio.sleep(self.retry_delay)
                was_unavailable = self.health.state == "unavailable"
                try:
                    if needs_initialize:
                        self.start()
                        needs_initialize = False
                    else:
                        self.poll_once()
                except OSError:
                    self.health.set_unavailable()
                    if was_unavailable:
                        self.retry_delay = min(self.retry_delay * 2, self.backoff_max)
                    else:
                        self.retry_delay = self.backoff_initial
                    continue
                self.retry_delay = self.backoff_initial
                self.health.set_ready()
                await asyncio.sleep(self.poll_interval)
        finally:
            self.health.set_stopped()
