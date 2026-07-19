import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from opportunity_os.automation.healthcheck import HealthCheck, LastHealthProbe
from opportunity_os.dashboard.schemas import ComponentHealth


class Probe:
    def __init__(self, status: str) -> None:
        self.status = status

    def check(self) -> ComponentHealth:
        return ComponentHealth(
            component="hermes", status=self.status,
            checked_at=datetime(2026, 7, 19, tzinfo=timezone.utc), duration_ms=1,
        )


def test_healthcheck_is_aggregate_only_and_reports_recovery(tmp_path) -> None:
    marker = tmp_path / "last.json"
    first = HealthCheck([Probe("down")], marker).run()
    second = HealthCheck([Probe("healthy")], marker).run()

    assert first["ok"] is False and first["recovered"] is False
    assert second["ok"] is True and second["recovered"] is True
    assert set(second) == {"ok", "recovered", "components"}
    assert oct(marker.stat().st_mode & 0o777) == "0o600"
    persisted = json.loads(marker.read_text(encoding="utf-8"))
    assert persisted["version"] == 1
    assert persisted["components"][0]["component"] == "hermes"


def test_empty_probe_set_is_not_healthy() -> None:
    assert HealthCheck([]).run()["ok"] is False


def test_last_health_probe_reads_fresh_marker_without_running_command(tmp_path) -> None:
    marker = tmp_path / "last.json"
    checked_at = datetime.now(timezone.utc)
    HealthCheck([Probe("healthy")], marker).run()

    result = LastHealthProbe(marker, "hermes", now=lambda: checked_at + timedelta(seconds=1)).check()

    assert result.status == "healthy"
    assert result.error_code is None


def test_last_health_probe_returns_unknown_for_missing_stale_or_non_regular_marker(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    missing = LastHealthProbe(tmp_path / "missing.json", "openclaw", now=lambda: now).check()
    assert missing.status == "unknown" and missing.error_code == "health_snapshot_missing"

    marker = tmp_path / "stale.json"
    old = now - timedelta(hours=1)
    marker.write_text(json.dumps({
        "version": 1,
        "ok": True,
        "checked_at": old.isoformat(),
        "components": [{
            "component": "openclaw", "status": "healthy", "checked_at": old.isoformat(),
            "last_success_at": old.isoformat(), "duration_ms": 1, "error_code": None,
        }],
    }), encoding="utf-8")
    stale = LastHealthProbe(marker, "openclaw", now=lambda: now).check()
    assert stale.status == "unknown" and stale.error_code == "health_snapshot_stale"

    fifo = tmp_path / "marker.fifo"
    os.mkfifo(fifo)
    invalid = LastHealthProbe(fifo, "openclaw", now=lambda: now).check()
    assert invalid.status == "unknown" and invalid.error_code == "health_snapshot_invalid"
    with pytest.raises(ValueError, match="health_snapshot_invalid"):
        HealthCheck([Probe("healthy")], fifo).run()
