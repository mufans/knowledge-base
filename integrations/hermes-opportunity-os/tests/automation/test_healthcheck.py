from datetime import datetime, timezone

from opportunity_os.automation.healthcheck import HealthCheck
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


def test_empty_probe_set_is_not_healthy() -> None:
    assert HealthCheck([]).run()["ok"] is False
