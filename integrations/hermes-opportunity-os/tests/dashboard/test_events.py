from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from opportunity_os.dashboard.events import EventHub


@pytest.fixture
def event_hub(tmp_path: Path) -> EventHub:
    return EventHub(tmp_path / "event-cursor")


def test_sse_replays_after_last_event_id(event_hub: EventHub) -> None:
    first = event_hub.publish("component.updated", {"component": "hermes"})
    second = event_hub.publish("incident.firing", {"incident_id": "inc-1"})

    assert [event.id for event in event_hub.replay(first.id)] == [second.id]


def test_sse_rejects_private_body(event_hub: EventHub) -> None:
    with pytest.raises(ValueError, match="event payload"):
        event_hub.publish("review.updated", {"summary": "private free text"})


def test_event_hub_keeps_only_one_thousand_events_in_memory(event_hub: EventHub) -> None:
    for number in range(1_005):
        event_hub.publish("component.updated", {"entity_id": f"component-{number}"})

    retained = event_hub.replay(None)

    assert len(retained) == 1_000
    assert retained[0].id == "6"
    assert retained[-1].id == "1005"


def test_event_hub_persists_only_the_cursor(tmp_path: Path) -> None:
    cursor_path = tmp_path / "event-cursor"
    hub = EventHub(cursor_path)
    hub.publish("incident.firing", {"incident_id": "inc-sensitive-identifier"})

    assert cursor_path.read_text(encoding="utf-8") == "1\n"
    assert list(tmp_path.iterdir()) == [cursor_path]
    assert "incident" not in cursor_path.read_text(encoding="utf-8")

    restarted = EventHub(cursor_path)
    assert restarted.publish("component.updated", {"component": "dashboard"}).id == "2"


def test_subscribe_replays_then_delivers_new_metadata(event_hub: EventHub) -> None:
    first = event_hub.publish("component.updated", {"component": "hermes"})

    async def receive() -> list[str]:
        subscription = event_hub.subscribe(None)
        replayed = await anext(subscription)
        event_hub.publish("incident.recovered", {"incident_id": "inc-1"})
        live = await anext(subscription)
        await subscription.aclose()
        return [replayed.id, live.id]

    assert asyncio.run(receive()) == [first.id, "2"]


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("review.updated", {"entity_id": "review-1", "body": "secret"}),
        ("review.updated", {"entity_id": "review-1", "nested": {"token": "secret"}}),
        ("review updated", {"entity_id": "review-1"}),
        ("review.updated", {"entity_id": "contains spaces"}),
    ],
)
def test_event_hub_rejects_non_metadata_events(
    event_hub: EventHub, event_type: str, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        event_hub.publish(event_type, payload)
