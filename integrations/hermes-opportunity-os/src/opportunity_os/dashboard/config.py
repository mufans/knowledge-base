"""Typed, environment-backed settings for dashboard read-only probes."""

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_PROBE_TIMEOUT_SECONDS = 5.0
MAX_PROBE_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class DashboardConfig:
    """Typed runtime, storage, and remote-origin settings for the dashboard."""

    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS
    dashboard_home: Path = Path(".dashboard")
    remote_host: str | None = None
    origin_credential: str | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.probe_timeout_seconds) or not 0 < self.probe_timeout_seconds <= MAX_PROBE_TIMEOUT_SECONDS:
            raise ValueError(f"probe_timeout_seconds must be finite and between 0 and {MAX_PROBE_TIMEOUT_SECONDS}")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DashboardConfig":
        """Load the bounded probe timeout without exposing environment contents."""
        values = os.environ if environ is None else environ
        raw_timeout = values.get("DASHBOARD_PROBE_TIMEOUT_SECONDS")
        timeout = DEFAULT_PROBE_TIMEOUT_SECONDS
        if raw_timeout is not None:
            try:
                timeout = float(raw_timeout)
            except ValueError as error:
                raise ValueError("DASHBOARD_PROBE_TIMEOUT_SECONDS must be a finite number") from error
        try:
            return cls(
                probe_timeout_seconds=timeout,
                dashboard_home=Path(values.get("DASHBOARD_HOME", ".dashboard")).expanduser(),
                remote_host=values.get("DASHBOARD_REMOTE_HOST") or None,
                origin_credential=values.get("DASHBOARD_ORIGIN_CREDENTIAL") or None,
            )
        except ValueError as error:
            raise ValueError("DASHBOARD_PROBE_TIMEOUT_SECONDS must be a finite number") from error
