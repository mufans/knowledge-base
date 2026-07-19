from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.probes import (
    HERMES_EXECUTABLE,
    CommandResult,
    DashboardProbe,
    HermesProbe,
    NgrokProbe,
    OpenClawProbe,
)
from opportunity_os.deployment.remote_access import NgrokStatus


@dataclass
class FakeRunner:
    result: CommandResult = field(
        default_factory=lambda: CommandResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            timed_out=False,
            duration_ms=12,
        )
    )
    calls: list[tuple[tuple[str, ...], float]] = field(default_factory=list)

    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append((argv, timeout))
        return self.result


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def dashboard_config() -> DashboardConfig:
    return DashboardConfig(probe_timeout_seconds=1.0)


def test_timeout_is_unknown_not_down(fake_runner: FakeRunner, dashboard_config: DashboardConfig) -> None:
    fake_runner.result = CommandResult(
        exit_code=None,
        stdout="",
        stderr="",
        timed_out=True,
        duration_ms=1000,
    )

    result = HermesProbe(dashboard_config, fake_runner).check()

    assert result.status == "unknown"
    assert result.error_code == "probe_timeout"
    assert fake_runner.calls == [((HERMES_EXECUTABLE, "-p", "opportunity-discovery", "config", "check"), 1.0)]


def test_openclaw_probe_uses_only_the_gateway_status_command(
    fake_runner: FakeRunner, dashboard_config: DashboardConfig
) -> None:
    result = OpenClawProbe(dashboard_config, fake_runner).check()

    assert result.component == "openclaw"
    assert result.status == "healthy"
    assert result.error_code is None
    assert fake_runner.calls == [(("openclaw", "gateway", "status"), 1.0)]


def test_dashboard_probe_uses_only_loopback_http(fake_runner: FakeRunner, dashboard_config: DashboardConfig) -> None:
    result = DashboardProbe(dashboard_config, fake_runner).check()

    assert result.component == "dashboard" and result.status == "healthy"
    assert fake_runner.calls == [((
        "/usr/bin/curl", "--fail", "--silent", "--show-error", "--max-time", "3",
        "http://127.0.0.1:8765/",
    ), 1.0)]


class FakeNgrokStatus:
    def __init__(self, count: int = 1, error: bool = False) -> None:
        self.count = count
        self.error = error

    def read(self) -> NgrokStatus:
        if self.error:
            raise RuntimeError("unavailable")
        return NgrokStatus(running=True, tunnel_count=self.count)


def test_ngrok_probe_requires_exactly_one_tunnel(dashboard_config: DashboardConfig) -> None:
    assert NgrokProbe(dashboard_config, FakeNgrokStatus()).check().status == "healthy"  # type: ignore[arg-type]
    failed = NgrokProbe(dashboard_config, FakeNgrokStatus(count=0)).check()  # type: ignore[arg-type]
    assert failed.status == "down" and failed.error_code == "probe_failed"
    unavailable = NgrokProbe(dashboard_config, FakeNgrokStatus(error=True)).check()  # type: ignore[arg-type]
    assert unavailable.status == "down" and unavailable.error_code == "probe_failed"


@pytest.mark.parametrize("value", ["nan", "inf", "30.1"])
def test_config_rejects_non_finite_or_unbounded_probe_timeouts(value: str) -> None:
    with pytest.raises(ValueError):
        DashboardConfig.from_env({"DASHBOARD_PROBE_TIMEOUT_SECONDS": value})
