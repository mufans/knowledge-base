"""Typed, environment-backed settings for dashboard read-only probes."""

import os
from dataclasses import dataclass
from typing import Mapping


DEFAULT_PROBE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class DashboardConfig:
    """Configuration which is safe to pass to read-only runtime probes."""

    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.probe_timeout_seconds <= 0:
            raise ValueError("probe_timeout_seconds must be greater than zero")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DashboardConfig":
        """Load the bounded probe timeout without exposing environment contents."""
        values = os.environ if environ is None else environ
        raw_timeout = values.get("DASHBOARD_PROBE_TIMEOUT_SECONDS")
        if raw_timeout is None:
            return cls()
        try:
            return cls(probe_timeout_seconds=float(raw_timeout))
        except ValueError as error:
            raise ValueError("DASHBOARD_PROBE_TIMEOUT_SECONDS must be a positive number") from error
