from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from opportunity_os.dashboard.events import EventHub, EventJournalTailer


def _record(action: str, entity_type: str, entity_id: str, **extra: object) -> str:
    return json.dumps(
        {
            "at": "2026-07-19T10:00:00+00:00",
            "action": action,
            "entity_id": entity_id,
            "entity_type": entity_type,
            **extra,
        }
    )


async def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


def test_journal_tailer_skips_history_and_never_forwards_private_record_fields(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "events.jsonl"
    journal.write_text(
        _record("save_review", "review", "private-review-about-acquisition-target") + "\n",
        encoding="utf-8",
    )
    hub = EventHub(tmp_path / "event-cursor")
    tailer = EventJournalTailer(journal, hub, poll_interval=0.01)

    tailer.start()
    assert tailer.poll_once() == 0
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(
            _record(
                "save_opportunity",
                "opportunity",
                "private-opportunity-customer-alice@example.com",
                body="private acquisition plan",
                token="not-for-sse",
            )
            + "\n"
        )

    assert tailer.poll_once() == 1
    [event] = hub.replay(None)
    assert event.type == "state.invalidated"
    assert dict(event.payload) == {"scope": "private_state"}
    wire = json.dumps(event.wire_payload())
    assert "private-opportunity" not in wire
    assert "customer" not in wire
    assert "acquisition" not in wire
    assert "token" not in wire


def test_journal_tailer_handles_half_lines_truncation_rotation_and_unknown_records(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "events.jsonl"
    journal.touch()
    hub = EventHub(tmp_path / "event-cursor")
    tailer = EventJournalTailer(journal, hub, poll_interval=0.01)
    tailer.start()

    first = _record("record_experiment", "experiment", "experiment-private")
    split = len(first) // 2
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(first[:split])
    assert tailer.poll_once() == 0
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(first[split:] + "\n")
    assert tailer.poll_once() == 1

    journal.write_text(
        _record(
            "set_direction",
            "direction",
            "direction-private",
            padding="X" * 512,
        )
        + "\n",
        encoding="utf-8",
    )
    assert tailer.poll_once() == 1

    rotated = tmp_path / "events.jsonl.1"
    journal.replace(rotated)
    journal.write_text(
        _record("record_tech_state", "tech_state", "technology-private")
        + "\n"
        + _record("unknown_action", "review", "ignored-private")
        + "\n",
        encoding="utf-8",
    )
    assert tailer.poll_once() == 1

    assert len(hub.replay(None)) == 3


def test_initial_permission_error_marks_bridge_unavailable(monkeypatch, tmp_path: Path) -> None:
    journal = tmp_path / "events.jsonl"
    journal.touch()
    tailer = EventJournalTailer(journal, EventHub(tmp_path / "event-cursor"))

    def denied() -> None:
        raise PermissionError("private path must not escape")

    monkeypatch.setattr(tailer, "start", denied)

    assert tailer.initialize() is False
    assert tailer.health.state == "unavailable"
    assert tailer.health.error_code == "io_failure"
    assert "private path" not in repr(tailer.health.snapshot())


def test_cursor_failure_marks_unavailable_then_recovers_without_losing_event(
    monkeypatch, tmp_path: Path
) -> None:
    journal = tmp_path / "events.jsonl"
    journal.touch()
    hub = EventHub(tmp_path / "event-cursor")
    tailer = EventJournalTailer(
        journal,
        hub,
        poll_interval=0.01,
        backoff_initial=0.03,
        backoff_max=0.05,
    )
    assert tailer.initialize() is True
    original_persist = hub._persist_cursor
    attempts = 0

    def fail_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("cursor path is private")
        original_persist()

    monkeypatch.setattr(hub, "_persist_cursor", fail_once)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(_record("save_review", "review", "private-review") + "\n")

    async def scenario() -> None:
        task = asyncio.create_task(tailer.run(initialized=True))
        await _wait_until(lambda: tailer.health.state == "unavailable")
        assert hub.replay(None) == []
        assert tailer.health.error_code == "io_failure"
        await _wait_until(lambda: tailer.health.state == "ready" and len(hub.replay(None)) == 1)
        [event] = hub.replay(None)
        assert dict(event.payload) == {"scope": "private_state"}
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert attempts >= 2
    assert tailer.health.state == "stopped"


def test_runtime_journal_poll_permission_error_recovers(monkeypatch, tmp_path: Path) -> None:
    journal = tmp_path / "events.jsonl"
    journal.touch()
    tailer = EventJournalTailer(
        journal,
        EventHub(tmp_path / "event-cursor"),
        poll_interval=0.01,
        backoff_initial=0.03,
        backoff_max=0.05,
    )
    assert tailer.initialize() is True
    original_poll = tailer._poll_once
    attempts = 0

    def unreadable_once() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("journal path is private")
        return original_poll()

    monkeypatch.setattr(tailer, "_poll_once", unreadable_once)

    async def scenario() -> None:
        task = asyncio.create_task(tailer.run(initialized=True))
        await _wait_until(lambda: tailer.health.state == "unavailable")
        assert tailer.health.error_code == "io_failure"
        await _wait_until(lambda: tailer.health.state == "ready" and attempts >= 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert tailer.health.state == "stopped"


def test_shutdown_cancels_immediately_during_capped_backoff(monkeypatch, tmp_path: Path) -> None:
    journal = tmp_path / "events.jsonl"
    journal.touch()
    tailer = EventJournalTailer(
        journal,
        EventHub(tmp_path / "event-cursor"),
        poll_interval=0.01,
        backoff_initial=0.01,
        backoff_max=0.04,
    )

    def always_denied() -> None:
        raise PermissionError("never expose this path")

    monkeypatch.setattr(tailer, "start", always_denied)
    assert tailer.initialize() is False

    async def scenario() -> None:
        task = asyncio.create_task(tailer.run(initialized=False))
        await _wait_until(lambda: tailer.retry_delay == 0.04)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.1)

    asyncio.run(scenario())
    assert tailer.retry_delay == 0.04
    assert tailer.health.state == "stopped"
