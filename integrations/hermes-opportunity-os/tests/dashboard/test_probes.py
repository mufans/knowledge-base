from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.probes import CommandResult, HermesProbe, OpenClawProbe


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
    assert fake_runner.calls == [(("hermes", "-p", "opportunity-discovery", "config", "check"), 1.0)]


def test_openclaw_probe_uses_only_the_gateway_status_command(
    fake_runner: FakeRunner, dashboard_config: DashboardConfig
) -> None:
    result = OpenClawProbe(dashboard_config, fake_runner).check()

    assert result.component == "openclaw"
    assert result.status == "healthy"
    assert result.error_code is None
    assert fake_runner.calls == [(("openclaw", "gateway", "status"), 1.0)]


@pytest.mark.parametrize("value", ["nan", "inf", "30.1"])
def test_config_rejects_non_finite_or_unbounded_probe_timeouts(value: str) -> None:
    with pytest.raises(ValueError):
        DashboardConfig.from_env({"DASHBOARD_PROBE_TIMEOUT_SECONDS": value})
