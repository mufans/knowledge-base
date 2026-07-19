"""Bounded, metadata-only events for authenticated dashboard SSE clients."""

from __future__ import annotations

import asyncio
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


MAX_EVENTS = 1_000
_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_METADATA_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")
_METADATA_KEYS = frozenset(
    {
        "approval_id",
        "component",
        "entity_id",
        "incident_id",
        "report_id",
        "status",
        "task_id",
    }
)


@dataclass(frozen=True, slots=True)
class DashboardEvent:
    """One replayable notification containing identifiers, never entity bodies."""

    id: str
    type: str
    payload: Mapping[str, str | int]
    at: datetime

    def wire_payload(self) -> dict[str, str | int]:
        return {
            "event_id": self.id,
            "type": self.type,
            **self.payload,
            "at": self.at.isoformat(),
        }


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
    def _validate(event_type: str, payload: Mapping[str, object]) -> dict[str, str | int]:
        if not _EVENT_TYPE.fullmatch(event_type):
            raise ValueError("event type must be a dotted metadata event name")
        if not payload or not set(payload).issubset(_METADATA_KEYS):
            raise ValueError("event payload must contain approved metadata fields only")
        sanitized: dict[str, str | int] = {}
        for key, value in payload.items():
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ValueError("event payload values must be scalar metadata")
            if isinstance(value, int):
                if value < 0:
                    raise ValueError("event payload integers must be non-negative")
            elif not _METADATA_VALUE.fullmatch(value):
                raise ValueError("event payload text must be an identifier")
            sanitized[key] = value
        return sanitized

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
            self._events.append(event)
            self._persist_cursor()
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
