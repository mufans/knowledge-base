"""Aggregate, side-effect-free health checks for native runtimes."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Iterable

from opportunity_os.dashboard.probes import RuntimeProbe


class HealthCheck:
    """Run injected probes and emit only their safe component DTOs."""

    def __init__(self, probes: Iterable[RuntimeProbe], marker: Path | None = None) -> None:
        self._probes = tuple(probes)
        self._marker = marker

    def run(self) -> dict[str, object]:
        components = [probe.check() for probe in self._probes]
        ok = bool(components) and all(item.status == "healthy" for item in components)
        previous = self._swap_marker(ok) if self._marker is not None else None
        return {
            "ok": ok,
            "recovered": previous is False and ok,
            "components": [item.model_dump(mode="json") for item in components],
        }

    def _swap_marker(self, current: bool) -> bool | None:
        assert self._marker is not None
        self._marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self._marker, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            with os.fdopen(descriptor, "r+", encoding="utf-8", closefd=False) as handle:
                try:
                    value = json.load(handle)
                except (json.JSONDecodeError, OSError):
                    value = None
                previous = value.get("ok") if isinstance(value, dict) else None
                handle.seek(0)
                handle.truncate()
                json.dump({"ok": current}, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            return previous if type(previous) is bool else None
        finally:
            os.close(descriptor)
