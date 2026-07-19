from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from opportunity_os.dashboard.events import EventHub


@pytest.fixture
def event_hub(tmp_path: Path) -> EventHub:
    return EventHub(tmp_path / "event-cursor")


def test_sse_replays_after_last_event_id(event_hub: EventHub) -> None:
    first = event_hub.publish(
        "component.updated", {"component": "hermes", "status": "healthy"}
    )
    second = event_hub.publish(
        "component.updated", {"component": "openclaw", "status": "unknown"}
    )

    assert [event.id for event in event_hub.replay(first.id)] == [second.id]


def test_sse_rejects_private_body(event_hub: EventHub) -> None:
    with pytest.raises(ValueError, match="event payload"):
        event_hub.publish("review.updated", {"summary": "private free text"})


def test_event_hub_keeps_only_one_thousand_events_in_memory(event_hub: EventHub) -> None:
    for number in range(1_005):
        event_hub.publish("state.invalidated", {"scope": "private_state"})

    retained = event_hub.replay(None)

    assert len(retained) == 1_000
    assert retained[0].id == "6"
    assert retained[-1].id == "1005"


def test_event_hub_persists_only_the_cursor(tmp_path: Path) -> None:
    cursor_path = tmp_path / "event-cursor"
    hub = EventHub(cursor_path)
    hub.publish(
        "component.updated", {"component": "openclaw", "status": "down"}
    )

    assert cursor_path.read_text(encoding="utf-8") == "1\n"
    assert list(tmp_path.iterdir()) == [cursor_path]
    assert "incident" not in cursor_path.read_text(encoding="utf-8")

    restarted = EventHub(cursor_path)
    assert restarted.publish("state.invalidated", {"scope": "private_state"}).id == "2"


def test_subscribe_replays_then_delivers_new_metadata(event_hub: EventHub) -> None:
    first = event_hub.publish("state.invalidated", {"scope": "private_state"})

    async def receive() -> list[str]:
        subscription = event_hub.subscribe(None)
        replayed = await anext(subscription)
        event_hub.publish(
            "component.updated",
            {"component": "openclaw", "status": "healthy"},
        )
        live = await anext(subscription)
        await subscription.aclose()
        return [replayed.id, live.id]

    assert asyncio.run(receive()) == [first.id, "2"]


def test_owner_scoped_events_are_not_visible_to_other_audiences(event_hub: EventHub) -> None:
    owner_a = "a" * 64
    owner_b = "b" * 64
    private = event_hub.publish(
        "component.updated",
        {"component": "hermes", "status": "healthy"},
        audience=owner_a,
    )
    public = event_hub.publish("state.invalidated", {"scope": "private_state"})

    assert [event.id for event in event_hub.replay(None, audience=owner_a)] == [
        private.id,
        public.id,
    ]
    assert [event.id for event in event_hub.replay(None, audience=owner_b)] == [public.id]
    assert [event.id for event in event_hub.replay(None)] == [public.id]
    assert "audience" not in private.wire_payload()
    assert owner_a not in event_hub.cursor_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("review.updated", {"review_id": "review_123e4567-e89b-12d3-a456-426614174000"}),
        ("state.invalidated", {"scope": "private_state", "entity_id": "opaque"}),
        ("state.invalidated", {}),
        ("component.updated", {"component": "hermes"}),
        ("component.updated", {"component": "hermes", "status": "healthy", "extra": 1}),
        ("review updated", {"scope": "private_state"}),
    ],
)
def test_event_hub_enforces_exact_schema_per_event_type(
    event_hub: EventHub, event_type: str, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        event_hub.publish(event_type, payload)


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("state.invalidated", {"scope": "private-acquisition-target"}),
        ("state.invalidated", {"scope": "customer@example.com"}),
        ("state.invalidated", {"scope": "A" * 128}),
        ("component.updated", {"component": "customer@example.com", "status": "healthy"}),
        ("component.updated", {"component": "A" * 128, "status": "healthy"}),
        ("component.updated", {"component": "hermes", "status": "private-target"}),
        ("component.updated", {"component": "hermes", "status": "A" * 128}),
    ],
)
def test_event_schema_rejects_descriptive_email_and_base64_like_values(
    event_hub: EventHub, event_type: str, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="event payload"):
        event_hub.publish(event_type, payload)


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("state.invalidated", {"scope": "private_state"}),
        ("component.updated", {"component": "opportunity_os", "status": "degraded"}),
    ],
)
def test_event_hub_accepts_only_documented_safe_events(
    event_hub: EventHub, event_type: str, payload: dict[str, object]
) -> None:
    assert event_hub.publish(event_type, payload).type == event_type


@pytest.mark.parametrize(
    "removed",
    [
        "conversation.started", "conversation.completed", "conversation.failed",
        "incident.firing", "incident.recovered",
    ],
)
def test_removed_native_duplicate_event_protocols_are_rejected(
    event_hub: EventHub, removed: str
) -> None:
    with pytest.raises(ValueError, match="unsupported event type"):
        event_hub.publish(removed, {})


def test_cursor_write_failure_rolls_back_event_and_identifier(
    monkeypatch, event_hub: EventHub
) -> None:
    original_persist = event_hub._persist_cursor

    def denied() -> None:
        raise PermissionError("cursor path is private")

    monkeypatch.setattr(event_hub, "_persist_cursor", denied)
    with pytest.raises(PermissionError):
        event_hub.publish("state.invalidated", {"scope": "private_state"})

    assert event_hub.replay(None) == []
    monkeypatch.setattr(event_hub, "_persist_cursor", original_persist)
    assert event_hub.publish("state.invalidated", {"scope": "private_state"}).id == "1"
