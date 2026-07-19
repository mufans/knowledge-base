"""Typed, environment-backed settings for dashboard read-only probes."""

import math
import os
from dataclasses import dataclass
from typing import Mapping


DEFAULT_PROBE_TIMEOUT_SECONDS = 5.0
MAX_PROBE_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class DashboardConfig:
    """Configuration which is safe to pass to read-only runtime probes."""

    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not math.isfinite(self.probe_timeout_seconds) or not 0 < self.probe_timeout_seconds <= MAX_PROBE_TIMEOUT_SECONDS:
            raise ValueError(f"probe_timeout_seconds must be finite and between 0 and {MAX_PROBE_TIMEOUT_SECONDS}")

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
            raise ValueError("DASHBOARD_PROBE_TIMEOUT_SECONDS must be a finite number") from error
