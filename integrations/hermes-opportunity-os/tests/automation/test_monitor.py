from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from opportunity_os.automation.monitor import (
    AlertSummary,
    DeliveryAttempt,
    DeliveryQueue,
    Monitor,
)
from opportunity_os.dashboard.events import EventHub
from opportunity_os.dashboard.incidents import IncidentSentinel
from opportunity_os.dashboard.schemas import ComponentHealth
from opportunity_os.errors import ValidationError


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


@dataclass
class FakeProbe:
    health: ComponentHealth

    def check(self) -> ComponentHealth:
        return self.health


class FakeDelivery:
    def __init__(self, attempts: list[DeliveryAttempt]) -> None:
        self.attempts = attempts
        self.summaries: list[AlertSummary] = []

    def send(self, summary: AlertSummary) -> DeliveryAttempt:
        self.summaries.append(summary)
        return self.attempts.pop(0)


def health(status: str, *, error_code: str | None = None) -> ComponentHealth:
    return ComponentHealth(
        component="hermes",
        status=status,
        checked_at=NOW,
        last_success_at=NOW if status == "healthy" else None,
        duration_ms=5,
        error_code=error_code,
    )


def safe_summary() -> AlertSummary:
    return AlertSummary(
        error_code="timeout",
        impact="analysis_unavailable",
        last_success=NOW,
        run_id="run_123e4567-e89b-12d3-a456-426614174000",
        dashboard_url="https://owner.ngrok-free.app/monitoring",
        suggested_action="retry_task",
    )


def test_delivery_requires_real_receipt_and_retry_is_idempotent(tmp_path: Path) -> None:
    queue = DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW)
    record = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    assert record.state == "generated"
    assert queue.queue(record.delivery_id).state == "queued"

    # A Cron/provider success flag without an opaque receipt is not delivery proof.
    failed = queue.complete(
        record.delivery_id,
        DeliveryAttempt(provider_accepted=True, receipt_id=None, error_code="missing_receipt"),
    )
    assert failed.state == "failed"
    assert queue.retry(record.delivery_id).state == "queued"
    delivered = queue.complete(
        record.delivery_id,
        DeliveryAttempt(
            provider_accepted=True,
            receipt_id="rcpt_123e4567-e89b-12d3-a456-426614174000",
            error_code=None,
        ),
    )
    assert delivered.state == "delivered"
    assert queue.retry(record.delivery_id).state == "delivered"
    duplicate = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    assert duplicate.delivery_id == record.delivery_id
    assert duplicate.state == "delivered"


def test_delivery_rejects_invalid_state_jump(tmp_path: Path) -> None:
    queue = DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW)
    record = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    with pytest.raises(ValidationError):
        queue.complete(
            record.delivery_id,
            DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"error_code": "stderr: token=secret"},
        {"impact": "customer acquisition details"},
        {"run_id": "/Users/person/private.log"},
        {"dashboard_url": "http://evil.example/monitoring"},
        {"dashboard_url": "https://user:secret@example.com/?token=x"},
        {"suggested_action": "run rm -rf"},
    ],
)
def test_alert_summary_accepts_only_safe_enums_opaque_ids_and_allowed_urls(changes) -> None:
    values = {
        "error_code": "timeout",
        "impact": "analysis_unavailable",
        "last_success": NOW,
        "run_id": "run_123e4567-e89b-12d3-a456-426614174000",
        "dashboard_url": "https://owner.ngrok-free.app/monitoring",
        "suggested_action": "retry_task",
    }
    values.update(changes)
    with pytest.raises(ValidationError):
        AlertSummary(**values)


def test_monitor_once_uses_injected_probe_and_delivery_and_emits_metadata_only(
    tmp_path: Path,
) -> None:
    hub = EventHub(tmp_path / "event-cursor")
    delivery = FakeDelivery(
        [DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None)]
    )
    monitor = Monitor(
        sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
        deliveries=DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW),
        probes=(FakeProbe(health("down", error_code="probe_failed")),),
        delivery=delivery,
        event_hub=hub,
        dashboard_url="http://127.0.0.1:8765/monitoring",
        now=lambda: NOW,
    )

    first = monitor.run_once()
    second = monitor.run_once()

    assert first.transitions[0].kind == "pending"
    assert second.transitions[0].kind == "firing"
    assert second.deliveries[0].state == "delivered"
    assert len(delivery.summaries) == 1
    event = hub.replay(None)[0]
    assert event.type == "incident.firing"
    assert set(event.payload) == {"incident_id"}
    assert "probe_failed" not in json.dumps(event.wire_payload())


def test_monitor_recovery_needs_two_real_probe_successes_and_notifies_once(tmp_path: Path) -> None:
    probe = FakeProbe(health("down", error_code="probe_failed"))
    delivery = FakeDelivery(
        [
            DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None),
            DeliveryAttempt(True, "rcpt_223e4567-e89b-12d3-a456-426614174000", None),
        ]
    )
    hub = EventHub(tmp_path / "cursor")
    monitor = Monitor(
        sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
        deliveries=DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW),
        probes=(probe,), delivery=delivery, event_hub=hub,
        dashboard_url="http://localhost:8765/monitoring", now=lambda: NOW,
    )
    monitor.run_once()
    monitor.run_once()
    probe.health = health("healthy")
    assert monitor.run_once().transitions[0].kind == "recovering"
    assert monitor.run_once().transitions[0].kind == "recovered"
    assert monitor.run_once().transitions[0].kind == "healthy"
    assert [event.type for event in hub.replay(None)] == ["incident.firing", "incident.recovered"]
    assert len(delivery.summaries) == 2


def test_boot_hook_is_once_per_opaque_boot_id_and_never_fakes_recovery(tmp_path: Path) -> None:
    delivery = FakeDelivery(
        [DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None)]
    )
    monitor = Monitor(
        sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
        deliveries=DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW),
        probes=(), delivery=delivery, event_hub=EventHub(tmp_path / "cursor"),
        dashboard_url="http://127.0.0.1:8765/monitoring", now=lambda: NOW,
    )
    boot_id = "boot_123e4567-e89b-12d3-a456-426614174000"

    assert monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("down"))) is None
    sent = monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("healthy")))
    assert sent is not None and sent.state == "delivered"
    assert monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("healthy"))) is None
    assert monitor.boot_hook(
        "boot_223e4567-e89b-12d3-a456-426614174000",
        interrupted=False,
        recovery_probe=FakeProbe(health("healthy")),
    ) is None
    assert len(delivery.summaries) == 1
    assert delivery.summaries[0].error_code == "process_interrupted"


def test_monitor_cli_uses_fixture_factory_without_real_probe_delivery_or_restart(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from opportunity_os.automation.monitor import MonitorResult
    from opportunity_os.cli import main

    calls = []

    class FixtureMonitor:
        def run_once(self) -> MonitorResult:
            calls.append("run_once")
            return MonitorResult(transitions=(), deliveries=())

    monkeypatch.setattr("opportunity_os.cli._monitor", lambda args: FixtureMonitor())
    result = main(["monitor", "once", "--home", str(tmp_path / "private"), "--format", "json"])

    assert result == 0
    assert calls == ["run_once"]
    assert json.loads(capsys.readouterr().out) == {"deliveries": [], "transitions": []}


def test_boot_hook_cli_uses_fixture_recovery_probe_and_never_runs_restart(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from opportunity_os.cli import main

    calls = []

    class FixtureMonitor:
        probes = (FakeProbe(health("healthy")),)

        def boot_hook(self, boot_id, *, interrupted, recovery_probe):
            calls.append((boot_id, interrupted, recovery_probe))
            return None

    fixture = FixtureMonitor()
    monkeypatch.setattr("opportunity_os.cli._monitor", lambda args: fixture)
    boot_id = "boot_123e4567-e89b-12d3-a456-426614174000"
    result = main(
        [
            "monitor", "boot-hook", "--home", str(tmp_path / "private"),
            "--boot-id", boot_id, "--interrupted", "--format", "json",
        ]
    )

    assert result == 0
    assert calls == [(boot_id, True, fixture.probes[0])]
    assert json.loads(capsys.readouterr().out) == {"delivery": None}
