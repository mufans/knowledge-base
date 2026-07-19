from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opportunity_os.dashboard.incidents import IncidentSentinel, RestartBudget
from opportunity_os.errors import BoundaryError, CapacityError, ValidationError


UTC = timezone.utc
NOW = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def test_incident_fires_once_and_recovers_once_across_instances(tmp_path: Path) -> None:
    clock = Clock()
    path = tmp_path / "private" / "dashboard" / "incidents.json"
    first = IncidentSentinel(path, now=clock)

    assert first.observe("hermes:daily:timeout", False, "P1", "timeout").kind == "pending"
    firing = IncidentSentinel(path, now=clock).observe(
        "hermes:daily:timeout", False, "P1", "timeout"
    )
    assert firing.kind == "firing"
    assert firing.notify is True
    assert first.observe("hermes:daily:timeout", False, "P1", "timeout").kind == "suppressed"
    assert first.observe("hermes:daily:timeout", True, "P1", "timeout").kind == "recovering"
    recovered = IncidentSentinel(path, now=clock).observe(
        "hermes:daily:timeout", True, "P1", "timeout"
    )
    assert recovered.kind == "recovered"
    assert recovered.notify is True
    assert first.observe("hermes:daily:timeout", True, "P1", "timeout").kind == "healthy"

    assert path.stat().st_mode & 0o777 == 0o600
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize(
    ("severity", "failures_before_fire"), [("P0", 1), ("P1", 2), ("P2", 3)]
)
def test_severity_thresholds(tmp_path: Path, severity: str, failures_before_fire: int) -> None:
    sentinel = IncidentSentinel(tmp_path / severity / "incidents.json", now=lambda: NOW)
    outcomes = [
        sentinel.observe("openclaw:gateway:probe_failed", False, severity, "probe_failed").kind
        for _ in range(failures_before_fire)
    ]
    assert outcomes[-1] == "firing"
    assert outcomes[:-1] == ["pending"] * (failures_before_fire - 1)


def test_reopened_incident_obeys_six_hour_cooldown(tmp_path: Path) -> None:
    clock = Clock()
    sentinel = IncidentSentinel(tmp_path / "incidents.json", now=clock)
    key = "knowledge_publish:sync:publish_failed"
    assert sentinel.observe(key, False, "P0", "publish_failed").kind == "firing"
    assert sentinel.observe(key, True, "P0", "publish_failed").kind == "recovering"
    assert sentinel.observe(key, True, "P0", "publish_failed").kind == "recovered"
    clock.value += timedelta(hours=5, minutes=59)
    assert sentinel.observe(key, False, "P0", "publish_failed").kind == "suppressed"
    clock.value += timedelta(minutes=2)
    assert sentinel.observe(key, False, "P0", "publish_failed").kind == "firing"


@pytest.mark.parametrize(
    ("key", "severity", "error_class"),
    [
        ("hermes:daily:timeout:private", "P1", "timeout"),
        ("Hermes:daily:timeout", "P1", "timeout"),
        ("hermes:customer-report:timeout", "P1", "timeout"),
        ("hermes:daily:stderr says secret", "P1", "stderr says secret"),
        ("hermes:daily:timeout", "P4", "timeout"),
        ("hermes:daily:timeout", "P1", "execution_error"),
    ],
)
def test_incident_key_and_fields_reject_free_text_and_mismatches(
    tmp_path: Path, key: str, severity: str, error_class: str
) -> None:
    with pytest.raises(ValidationError):
        IncidentSentinel(tmp_path / "incidents.json").observe(
            key, False, severity, error_class
        )


def test_incident_state_is_bounded_and_ttl_pruned(tmp_path: Path) -> None:
    clock = Clock()
    path = tmp_path / "incidents.json"
    sentinel = IncidentSentinel(path, now=clock, max_entries=2, ttl=timedelta(days=1))
    sentinel.observe("hermes:daily:timeout", False, "P1", "timeout")
    sentinel.observe("hermes:weekly:timeout", False, "P1", "timeout")
    with pytest.raises(CapacityError):
        sentinel.observe("hermes:quarterly:timeout", False, "P1", "timeout")

    clock.value += timedelta(days=2)
    assert sentinel.observe("hermes:quarterly:timeout", False, "P1", "timeout").kind == "pending"
    assert len(json.loads(path.read_text(encoding="utf-8"))["incidents"]) == 1


def test_incident_state_refuses_symlink_parent_and_symlink_file(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(BoundaryError):
        IncidentSentinel(linked / "incidents.json").observe(
            "hermes:daily:timeout", False, "P1", "timeout"
        )

    state = real / "incidents.json"
    target = real / "target.json"
    target.write_text("{}", encoding="utf-8")
    state.symlink_to(target)
    with pytest.raises(BoundaryError):
        IncidentSentinel(state).observe("hermes:daily:timeout", False, "P1", "timeout")


def test_restart_budget_is_persistent_concurrent_and_uses_rolling_utc_windows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "restart-budget.json"
    assert RestartBudget(path).allow("openclaw", NOW) is True
    assert RestartBudget(path).allow("openclaw", NOW + timedelta(minutes=30)) is False
    assert RestartBudget(path).allow("openclaw", NOW + timedelta(hours=2)) is True
    assert RestartBudget(path).allow("openclaw", NOW + timedelta(hours=4)) is False
    assert RestartBudget(path).allow("openclaw", NOW + timedelta(hours=25)) is True
    assert path.stat().st_mode & 0o777 == 0o600

    concurrent_path = tmp_path / "concurrent-budget.json"
    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(
            pool.map(
                lambda _: RestartBudget(concurrent_path).allow("dashboard", NOW),
                range(8),
            )
        )
    assert allowed.count(True) == 1


@pytest.mark.parametrize(
    "component,at",
    [
        ("custom component", NOW),
        ("../../openclaw", NOW),
        ("openclaw", datetime(2026, 7, 19, 10, 0)),
    ],
)
def test_restart_budget_rejects_free_text_and_naive_time(
    tmp_path: Path, component: str, at: datetime
) -> None:
    with pytest.raises(ValidationError):
        RestartBudget(tmp_path / "budget.json").allow(component, at)
