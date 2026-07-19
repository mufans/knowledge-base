"""Bounded health snapshots produced by Cron and consumed by the dashboard."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from pydantic import ValidationError

from opportunity_os.dashboard.probes import ComponentName, RuntimeProbe
from opportunity_os.dashboard.schemas import ComponentHealth


MAX_HEALTH_MARKER_BYTES = 64 * 1_024
DEFAULT_MAX_AGE = timedelta(minutes=15)
MARKER_VERSION = 1


class HealthMarkerError(ValueError):
    """A safe marker error whose message never includes a filesystem path."""


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise HealthMarkerError("health_snapshot_missing") from error
    except OSError as error:
        raise HealthMarkerError("health_snapshot_invalid") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_HEALTH_MARKER_BYTES:
            raise HealthMarkerError("health_snapshot_invalid")
        data = os.read(descriptor, MAX_HEALTH_MARKER_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(data) > MAX_HEALTH_MARKER_BYTES:
        raise HealthMarkerError("health_snapshot_invalid")
    return data


def _decode_marker(path: Path) -> tuple[datetime, list[ComponentHealth], bool]:
    try:
        value = json.loads(_read_regular(path).decode("utf-8", errors="strict"))
    except HealthMarkerError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise HealthMarkerError("health_snapshot_invalid") from error
    if not isinstance(value, dict) or set(value) != {
        "version", "ok", "checked_at", "components"
    }:
        raise HealthMarkerError("health_snapshot_invalid")
    if value.get("version") != MARKER_VERSION or type(value.get("ok")) is not bool:
        raise HealthMarkerError("health_snapshot_invalid")
    try:
        checked_at = datetime.fromisoformat(value["checked_at"])
        if checked_at.tzinfo is None:
            raise ValueError
        components = [ComponentHealth.model_validate(item) for item in value["components"]]
    except (TypeError, ValueError, ValidationError) as error:
        raise HealthMarkerError("health_snapshot_invalid") from error
    if not components or len({item.component for item in components}) != len(components):
        raise HealthMarkerError("health_snapshot_invalid")
    return checked_at.astimezone(timezone.utc), components, value["ok"]


class LastHealthMarker:
    """Atomically replace a small public-safe snapshot under an advisory lock."""

    def __init__(self, path: str | Path) -> None:
        requested = Path(path).expanduser()
        self.path = requested.parent.absolute() / requested.name
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")

    def swap(
        self,
        *,
        ok: bool,
        checked_at: datetime,
        components: list[ComponentHealth],
    ) -> bool | None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        try:
            lock_descriptor = os.open(self.lock_path, lock_flags, 0o600)
        except OSError as error:
            raise HealthMarkerError("health_snapshot_unavailable") from error
        try:
            lock_metadata = os.fstat(lock_descriptor)
            if not stat.S_ISREG(lock_metadata.st_mode):
                raise HealthMarkerError("health_snapshot_invalid")
            os.fchmod(lock_descriptor, 0o600)
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            try:
                _, _, previous = _decode_marker(self.path)
            except HealthMarkerError as error:
                if str(error) != "health_snapshot_missing":
                    raise
                previous = None
            payload = {
                "version": MARKER_VERSION,
                "ok": ok,
                "checked_at": checked_at.astimezone(timezone.utc).isoformat(),
                "components": [item.model_dump(mode="json") for item in components],
            }
            rendered = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
            if len(rendered) > MAX_HEALTH_MARKER_BYTES:
                raise HealthMarkerError("health_snapshot_too_large")
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(rendered)
                    handle.write(b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
                temp_name = ""
            except OSError as error:
                raise HealthMarkerError("health_snapshot_unavailable") from error
            finally:
                if temp_name:
                    try:
                        os.unlink(temp_name)
                    except FileNotFoundError:
                        pass
            return previous
        finally:
            os.close(lock_descriptor)


class LastHealthProbe:
    """Read one component from the marker without invoking an external command."""

    def __init__(
        self,
        marker: str | Path,
        component: ComponentName,
        *,
        max_age: timedelta = DEFAULT_MAX_AGE,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._marker = Path(marker)
        self._component = component
        self._max_age = max_age
        self._now = now or (lambda: datetime.now(timezone.utc))

    def check(self) -> ComponentHealth:
        now = self._now().astimezone(timezone.utc)
        try:
            checked_at, components, _ = _decode_marker(self._marker)
        except HealthMarkerError as error:
            return self._unknown(now, str(error))
        age = now - checked_at
        if age < timedelta(0) or age > self._max_age:
            return self._unknown(now, "health_snapshot_stale")
        for component in components:
            if component.component == self._component:
                return component
        return self._unknown(now, "health_component_missing")

    def _unknown(self, checked_at: datetime, error_code: str) -> ComponentHealth:
        return ComponentHealth(
            component=self._component,
            status="unknown",
            checked_at=checked_at,
            duration_ms=0,
            error_code=error_code,
        )


class HealthCheck:
    """Run fixed probes and atomically publish only their safe component DTOs."""

    def __init__(
        self,
        probes: Iterable[RuntimeProbe],
        marker: Path | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._probes = tuple(probes)
        self._marker = LastHealthMarker(marker) if marker is not None else None
        self._now = now or (lambda: datetime.now(timezone.utc))

    def run(self) -> dict[str, object]:
        components = [probe.check() for probe in self._probes]
        ok = bool(components) and all(item.status == "healthy" for item in components)
        previous = (
            self._marker.swap(
                ok=ok,
                checked_at=self._now(),
                components=components,
            )
            if self._marker is not None
            else None
        )
        return {
            "ok": ok,
            "recovered": previous is False and ok,
            "components": [item.model_dump(mode="json") for item in components],
        }
