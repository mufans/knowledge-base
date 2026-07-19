from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opportunity_os.automation.monitor import (
    AlertSummary,
    DeliveryAttempt,
    DeliveryClaim,
    DeliveryQueue,
    Monitor,
)
from opportunity_os.dashboard.events import EventHub
from opportunity_os.dashboard.incidents import IncidentSentinel
from opportunity_os.dashboard.schemas import ComponentHealth
from opportunity_os.errors import ValidationError


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


@dataclass
class FakeProbe:
    health: ComponentHealth

    def check(self) -> ComponentHealth:
        return self.health


class FakeDelivery:
    def __init__(self, attempts: list[DeliveryAttempt]) -> None:
        self.attempts = attempts
        self.summaries: list[AlertSummary] = []
        self.keys: list[str] = []
        self.receipts: dict[str, str] = {}
        self.lock = threading.Lock()

    def lookup(self, idempotency_key: str) -> str | None:
        with self.lock:
            return self.receipts.get(idempotency_key)

    def send(self, summary: AlertSummary, idempotency_key: str) -> DeliveryAttempt:
        with self.lock:
            self.summaries.append(summary)
            self.keys.append(idempotency_key)
            attempt = self.attempts.pop(0)
            if attempt.receipt_id is not None:
                self.receipts[idempotency_key] = attempt.receipt_id
            return attempt


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
        allowed_dashboard_hosts=("owner.ngrok-free.app",),
    )


def test_delivery_requires_real_receipt_and_retry_is_idempotent(tmp_path: Path) -> None:
    queue = DeliveryQueue(
        tmp_path / "deliveries.json", now=lambda: NOW,
        allowed_dashboard_hosts=("owner.ngrok-free.app",),
    )
    record = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    assert record.state == "generated"
    claim = queue.claim(record.delivery_id)
    assert isinstance(claim, DeliveryClaim)
    assert claim.record.state == "sending"

    # A Cron/provider success flag without an opaque receipt is not delivery proof.
    failed = queue.complete(
        record.delivery_id,
        DeliveryAttempt(provider_accepted=True, receipt_id=None, error_code="missing_receipt"),
        claim.attempt_token,
    )
    assert failed.state == "failed"
    retry_claim = queue.claim(record.delivery_id)
    assert isinstance(retry_claim, DeliveryClaim)
    delivered = queue.complete(
        record.delivery_id,
        DeliveryAttempt(
            provider_accepted=True,
            receipt_id="rcpt_123e4567-e89b-12d3-a456-426614174000",
            error_code=None,
        ),
        retry_claim.attempt_token,
    )
    assert delivered.state == "delivered"
    assert queue.claim(record.delivery_id) is None
    duplicate = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    assert duplicate.delivery_id == record.delivery_id
    assert duplicate.state == "delivered"


def test_delivery_rejects_invalid_state_jump(tmp_path: Path) -> None:
    queue = DeliveryQueue(
        tmp_path / "deliveries.json", now=lambda: NOW,
        allowed_dashboard_hosts=("owner.ngrok-free.app",),
    )
    record = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    with pytest.raises(ValidationError):
        queue.complete(
            record.delivery_id,
            DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None),
            "attempt_123e4567-e89b-12d3-a456-426614174000",
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
        "allowed_dashboard_hosts": ("owner.ngrok-free.app",),
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
        allowed_dashboard_hosts=(),
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
        allowed_dashboard_hosts=(),
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
        allowed_dashboard_hosts=(),
    )
    boot_id = "boot_123e4567-e89b-12d3-a456-426614174000"

    assert monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("down"))) is None
    sent = monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("healthy")))
    assert sent is not None and sent.state == "delivered"
    assert monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("healthy"))).state == "delivered"
    assert monitor.boot_hook(
        "boot_223e4567-e89b-12d3-a456-426614174000",
        interrupted=False,
        recovery_probe=FakeProbe(health("healthy")),
    ) is None
    assert len(delivery.summaries) == 1
    assert delivery.summaries[0].error_code == "process_interrupted"


def test_transactional_incident_outbox_survives_crash_before_delivery_generate(
    tmp_path: Path,
) -> None:
    sentinel = IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW)
    sentinel.observe("hermes:daily:timeout", False, "P1", "timeout")
    sentinel.observe("hermes:daily:timeout", False, "P1", "timeout")
    delivery = FakeDelivery(
        [DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None)]
    )
    monitor = Monitor(
        sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
        deliveries=DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW),
        probes=(), delivery=delivery, event_hub=EventHub(tmp_path / "cursor"),
        dashboard_url="http://127.0.0.1:8765/monitoring",
        allowed_dashboard_hosts=(), now=lambda: NOW,
    )

    result = monitor.run_once()

    assert result.ok is True
    assert len(delivery.keys) == 1
    assert sentinel.pending_notifications() == ()


def test_outbox_replay_after_generate_before_ack_deduplicates_delivery(tmp_path: Path) -> None:
    sentinel = IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW)
    sentinel.observe("hermes:daily:timeout", False, "P1", "timeout")
    sentinel.observe("hermes:daily:timeout", False, "P1", "timeout")
    intent = sentinel.pending_notifications()[0]
    queue = DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW)
    first = queue.generate(intent.idempotency_key, AlertSummary.from_notification(intent, ()))
    delivery = FakeDelivery(
        [DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None)]
    )
    monitor = Monitor(
        sentinel=sentinel, deliveries=queue, probes=(), delivery=delivery,
        event_hub=EventHub(tmp_path / "cursor"),
        dashboard_url="http://127.0.0.1:8765/monitoring",
        allowed_dashboard_hosts=(), now=lambda: NOW,
    )

    result = monitor.run_once()

    assert result.ok is True
    assert result.deliveries[0].delivery_id == first.delivery_id
    assert sentinel.pending_notifications() == ()
    assert len(delivery.keys) == 1


def test_provider_lookup_recovers_send_accepted_before_complete(tmp_path: Path) -> None:
    clock = Clock()
    queue = DeliveryQueue(
        tmp_path / "deliveries.json", now=clock,
        allowed_dashboard_hosts=("owner.ngrok-free.app",), lease_duration=timedelta(seconds=30),
    )
    record = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    claim = queue.claim(record.delivery_id)
    assert claim is not None
    provider = FakeDelivery(
        [DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None)]
    )
    provider.send(claim.record.summary, claim.record.idempotency_key)
    clock.value += timedelta(seconds=31)
    monitor = Monitor(
        sentinel=IncidentSentinel(tmp_path / "incidents.json", now=clock),
        deliveries=queue, probes=(), delivery=provider, event_hub=EventHub(tmp_path / "cursor"),
        dashboard_url="https://owner.ngrok-free.app/monitoring",
        allowed_dashboard_hosts=("owner.ngrok-free.app",), now=clock,
    )

    result = monitor.run_once()

    assert result.ok is True
    assert result.deliveries[0].state == "delivered"
    assert len(provider.summaries) == 1


def test_concurrent_monitors_claim_only_one_provider_send(tmp_path: Path) -> None:
    queue = DeliveryQueue(
        tmp_path / "deliveries.json", now=lambda: NOW,
        allowed_dashboard_hosts=("owner.ngrok-free.app",),
    )
    generated = queue.generate(
        "inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary()
    )
    provider = FakeDelivery(
        [DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None)]
    )

    def run() -> bool:
        monitor = Monitor(
            sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
            deliveries=DeliveryQueue(
                tmp_path / "deliveries.json", now=lambda: NOW,
                allowed_dashboard_hosts=("owner.ngrok-free.app",),
            ),
            probes=(), delivery=provider, event_hub=EventHub(tmp_path / f"cursor-{threading.get_ident()}"),
            dashboard_url="https://owner.ngrok-free.app/monitoring",
            allowed_dashboard_hosts=("owner.ngrok-free.app",), now=lambda: NOW,
        )
        return monitor.run_once().ok

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert any(results)
    assert len(provider.summaries) == 1
    assert queue.get(generated.delivery_id).state == "delivered"


def test_one_monitor_run_attempts_each_failed_delivery_only_once(tmp_path: Path) -> None:
    queue = DeliveryQueue(
        tmp_path / "deliveries.json", now=lambda: NOW,
        allowed_dashboard_hosts=("owner.ngrok-free.app",),
    )
    queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    provider = FakeDelivery([DeliveryAttempt(False, None, "delivery_failed")])
    monitor = Monitor(
        sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
        deliveries=queue, probes=(), delivery=provider, event_hub=EventHub(tmp_path / "cursor"),
        dashboard_url="https://owner.ngrok-free.app/monitoring",
        allowed_dashboard_hosts=("owner.ngrok-free.app",), now=lambda: NOW,
    )

    result = monitor.run_once()

    assert result.ok is False
    assert len(provider.summaries) == 1


def test_receipt_id_cannot_be_reused_by_two_deliveries(tmp_path: Path) -> None:
    queue = DeliveryQueue(
        tmp_path / "deliveries.json", now=lambda: NOW,
        allowed_dashboard_hosts=("owner.ngrok-free.app",),
    )
    first = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    second = queue.generate("inc_223e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    first_claim = queue.claim(first.delivery_id)
    second_claim = queue.claim(second.delivery_id)
    assert first_claim is not None and second_claim is not None
    receipt = "rcpt_123e4567-e89b-12d3-a456-426614174000"
    queue.complete(first.delivery_id, DeliveryAttempt(True, receipt, None), first_claim.attempt_token)
    with pytest.raises(ValidationError, match="receipt"):
        queue.complete(second.delivery_id, DeliveryAttempt(True, receipt, None), second_claim.attempt_token)


def test_expired_claim_rejects_stale_completion_token(tmp_path: Path) -> None:
    clock = Clock()
    queue = DeliveryQueue(
        tmp_path / "deliveries.json", now=clock,
        allowed_dashboard_hosts=("owner.ngrok-free.app",),
        lease_duration=timedelta(seconds=10),
    )
    record = queue.generate("inc_123e4567-e89b-12d3-a456-426614174000:firing", safe_summary())
    stale = queue.claim(record.delivery_id)
    assert stale is not None
    clock.value += timedelta(seconds=11)
    current = queue.claim(record.delivery_id)
    assert current is not None and current.attempt_token != stale.attempt_token

    with pytest.raises(ValidationError, match="stale"):
        queue.complete(
            record.delivery_id,
            DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None),
            stale.attempt_token,
        )


def test_boot_failed_delivery_retries_same_stable_key(tmp_path: Path) -> None:
    provider = FakeDelivery(
        [
            DeliveryAttempt(False, None, "delivery_failed"),
            DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None),
        ]
    )
    monitor = Monitor(
        sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
        deliveries=DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW),
        probes=(), delivery=provider, event_hub=EventHub(tmp_path / "cursor"),
        dashboard_url="http://127.0.0.1:8765/monitoring",
        allowed_dashboard_hosts=(), now=lambda: NOW,
    )
    boot_id = "boot_123e4567-e89b-12d3-a456-426614174000"
    first = monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("healthy")))
    second = monitor.boot_hook(boot_id, interrupted=True, recovery_probe=FakeProbe(health("healthy")))

    assert first is not None and first.state == "failed"
    assert second is not None and second.state == "delivered"
    assert provider.keys == [f"{boot_id}:recovered", f"{boot_id}:recovered"]


def test_concurrent_boot_hooks_share_one_claim_and_one_provider_send(tmp_path: Path) -> None:
    provider = FakeDelivery(
        [DeliveryAttempt(True, "rcpt_123e4567-e89b-12d3-a456-426614174000", None)]
    )
    queue_path = tmp_path / "deliveries.json"
    boot_id = "boot_123e4567-e89b-12d3-a456-426614174000"

    def run() -> str:
        monitor = Monitor(
            sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
            deliveries=DeliveryQueue(queue_path, now=lambda: NOW),
            probes=(), delivery=provider,
            event_hub=EventHub(tmp_path / f"cursor-boot-{threading.get_ident()}"),
            dashboard_url="http://127.0.0.1:8765/monitoring",
            allowed_dashboard_hosts=(), now=lambda: NOW,
        )
        result = monitor.boot_hook(
            boot_id, interrupted=True, recovery_probe=FakeProbe(health("healthy"))
        )
        assert result is not None
        return result.state

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(lambda _: run(), range(2)))

    assert "delivered" in states
    assert len(provider.summaries) == 1


@pytest.mark.parametrize(
    "url,hosts",
    [
        ("https://owner.ngrok-free.app/monitoring", ()),
        ("https://OWNER.ngrok-free.app/monitoring", ("owner.ngrok-free.app",)),
        ("https://owner.ngrok-free.app:444/monitoring", ("owner.ngrok-free.app",)),
        ("https://owner.ngrok-free.app/%6donitoring", ("owner.ngrok-free.app",)),
        (" http://127.0.0.1:8765/monitoring", ()),
        ("http://127.0.0.1:bad/monitoring", ()),
        ("http://127.0.0.1:70000/monitoring", ()),
        ("http://127.0.0.1:0/monitoring", ()),
        ("http://127.0.0.1.evil/monitoring", ()),
    ],
)
def test_monitor_rejects_noncanonical_or_non_allowlisted_dashboard_url(
    tmp_path: Path, url: str, hosts: tuple[str, ...]
) -> None:
    with pytest.raises(ValidationError):
        Monitor(
            sentinel=IncidentSentinel(tmp_path / "incidents.json", now=lambda: NOW),
            deliveries=DeliveryQueue(tmp_path / "deliveries.json", now=lambda: NOW),
            probes=(), delivery=FakeDelivery([]), event_hub=EventHub(tmp_path / "cursor"),
            dashboard_url=url, allowed_dashboard_hosts=hosts, now=lambda: NOW,
        )


def test_monitor_cli_uses_fixture_factory_without_real_probe_delivery_or_restart(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from opportunity_os.automation.monitor import MonitorResult
    from opportunity_os.cli import main

    calls = []

    class FixtureMonitor:
        def run_once(self) -> MonitorResult:
            calls.append("run_once")
            return MonitorResult(transitions=(), deliveries=(), ok=True, unresolved=())

    monkeypatch.setattr("opportunity_os.cli._monitor", lambda args: FixtureMonitor())
    result = main(["monitor", "once", "--home", str(tmp_path / "private"), "--format", "json"])

    assert result == 0
    assert calls == ["run_once"]
    assert json.loads(capsys.readouterr().out) == {
        "deliveries": [], "ok": True, "transitions": [], "unresolved": [],
    }


def test_monitor_once_cli_returns_nonzero_for_deferred_or_unreceipted_delivery(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from opportunity_os.automation.monitor import MonitorResult
    from opportunity_os.cli import main

    class FixtureMonitor:
        def run_once(self) -> MonitorResult:
            return MonitorResult(
                transitions=(), deliveries=(), ok=False,
                unresolved=("delivery_123e4567-e89b-12d3-a456-426614174000",),
            )

    monkeypatch.setattr("opportunity_os.cli._monitor", lambda args: FixtureMonitor())
    result = main(["monitor", "once", "--home", str(tmp_path / "private"), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["ok"] is False
    assert payload["unresolved"] == ["delivery_123e4567-e89b-12d3-a456-426614174000"]


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
