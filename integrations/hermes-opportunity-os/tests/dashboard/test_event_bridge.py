from __future__ import annotations

import json
from pathlib import Path

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
