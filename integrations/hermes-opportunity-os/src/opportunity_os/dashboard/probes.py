"""Fixed-command, read-only runtime probes for the dashboard."""

import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol
from pathlib import Path

from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.schemas import ComponentHealth


OPENCLAW_EXECUTABLE_PATH = "/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
ComponentName = Literal["openclaw", "hermes", "opportunity_os", "dashboard", "ngrok", "knowledge_publish"]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Sanitized command outcome; command output is never put in dashboard payloads."""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int


class CommandRunner:
    """Run a fixed argv command without a shell or provider interaction."""

    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult:
        started = time.monotonic()
        environment = (
            {**os.environ, "PATH": OPENCLAW_EXECUTABLE_PATH}
            if argv and Path(argv[0]).name == "openclaw"
            else None
        )
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                check=False,
                env=environment,
                shell=False,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            return CommandResult(
                exit_code=None,
                stdout=_text(error.stdout),
                stderr=_text(error.stderr),
                timed_out=True,
                duration_ms=_duration_ms(started),
            )
        except OSError as error:
            return CommandResult(
                exit_code=None,
                stdout="",
                stderr=str(error),
                timed_out=False,
                duration_ms=_duration_ms(started),
            )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            duration_ms=_duration_ms(started),
        )


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _duration_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


class RuntimeProbe(Protocol):
    """A read-only component health source."""

    def check(self) -> ComponentHealth: ...


class CommandProbe:
    """Map one fixed command result to a public-safe health contract."""

    component: ComponentName
    argv: tuple[str, ...]

    def __init__(self, config: DashboardConfig, runner: CommandRunner) -> None:
        self._config = config
        self._runner = runner

    def check(self) -> ComponentHealth:
        checked_at = datetime.now(timezone.utc)
        result = self._runner.run(self.argv, self._config.probe_timeout_seconds)
        if result.timed_out:
            return ComponentHealth(
                component=self.component,
                status="unknown",
                checked_at=checked_at,
                duration_ms=result.duration_ms,
                error_code="probe_timeout",
            )
        if result.exit_code is None:
            return ComponentHealth(
                component=self.component,
                status="unknown",
                checked_at=checked_at,
                duration_ms=result.duration_ms,
                error_code="probe_unavailable",
            )
        if result.exit_code == 0:
            return ComponentHealth(
                component=self.component,
                status="healthy",
                checked_at=checked_at,
                last_success_at=checked_at,
                duration_ms=result.duration_ms,
            )
        return ComponentHealth(
            component=self.component,
            status="down",
            checked_at=checked_at,
            duration_ms=result.duration_ms,
            error_code="probe_failed",
        )


class OpenClawProbe(CommandProbe):
    """Check only local gateway status with the dedicated Node 22 executable path."""

    component: ComponentName = "openclaw"
    argv = ("openclaw", "gateway", "status")


class HermesProbe(CommandProbe):
    """Validate the local Hermes profile without invoking any provider."""

    component: ComponentName = "hermes"
    argv = ("hermes", "-p", "opportunity-discovery", "config", "check")
