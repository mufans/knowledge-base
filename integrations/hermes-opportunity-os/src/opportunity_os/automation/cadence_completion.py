"""Domain completion markers for one-shot Hermes cadence invocations."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from opportunity_os.automation.secure_runtime import (
    atomic_json_at,
    open_absolute_directory,
    open_child_directory,
    read_json_at,
)
from opportunity_os.errors import BoundaryError, ValidationError


CADENCES = frozenset({"daily", "weekly", "biweekly", "six-week", "quarterly"})
PERIOD_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,79}$")
RUN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
ARTIFACT_REF_PATTERN = re.compile(r"^(review|experiment):([a-z0-9][a-z0-9_-]{1,79})$")
_REVIEW_PERIOD = {
    "daily": "daily",
    "weekly": "weekly",
    "six-week": "six_week",
    "quarterly": "quarterly",
}


class CadenceCompletionStore:
    """Validate and persist a marker proving the domain work was committed."""

    def __init__(
        self,
        home: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        path = Path(home).expanduser()
        if not path.is_absolute() or ".." in path.parts:
            raise BoundaryError("cadence completion home must be an absolute traversal-free path")
        self.home = path
        self.now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _validate_identity(cadence: str, period_key: str, run_id: str) -> None:
        if cadence not in CADENCES:
            raise ValidationError("cadence is not allowed")
        if not isinstance(period_key, str) or not PERIOD_KEY_PATTERN.fullmatch(period_key):
            raise ValidationError("period_key is invalid")
        if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValidationError("run_id is invalid")

    @staticmethod
    def _marker_name(period_key: str, run_id: str) -> str:
        return f"{period_key}-{run_id}.json"

    def _open_home(self) -> int:
        return open_absolute_directory(self.home)

    @staticmethod
    def _parse_refs(artifact_refs: Sequence[str]) -> tuple[tuple[str, str], ...]:
        if isinstance(artifact_refs, (str, bytes)) or not 1 <= len(artifact_refs) <= 20:
            raise ValidationError("artifact_refs must contain between one and twenty references")
        parsed: list[tuple[str, str]] = []
        rendered: set[str] = set()
        for value in artifact_refs:
            if not isinstance(value, str) or value in rendered:
                raise ValidationError("artifact_refs contain an invalid or duplicate value")
            match = ARTIFACT_REF_PATTERN.fullmatch(value)
            if match is None:
                raise ValidationError("artifact_ref is invalid")
            rendered.add(value)
            parsed.append((match.group(1), match.group(2)))
        return tuple(parsed)

    @staticmethod
    def _read_artifact(home_fd: int, kind: str, identifier: str) -> dict[str, object]:
        directory_fd = open_child_directory(home_fd, f"{kind}s")
        try:
            try:
                payload = read_json_at(directory_fd, f"{identifier}.json")
            except FileNotFoundError as error:
                raise ValidationError("referenced cadence artifact does not exist") from error
            except json.JSONDecodeError as error:
                raise ValidationError("referenced cadence artifact is invalid") from error
        finally:
            os.close(directory_fd)
        if payload.get("id") != identifier:
            raise ValidationError("referenced cadence artifact identity does not match")
        return payload

    @classmethod
    def _validate_required_artifact(
        cls,
        home_fd: int,
        cadence: str,
        refs: tuple[tuple[str, str], ...],
    ) -> None:
        required_kind = "experiment" if cadence == "biweekly" else "review"
        required_found = False
        for kind, identifier in refs:
            payload = cls._read_artifact(home_fd, kind, identifier)
            if kind != required_kind:
                continue
            if kind == "review" and payload.get("period") != _REVIEW_PERIOD[cadence]:
                continue
            required_found = True
        if not required_found:
            raise ValidationError("cadence completion lacks its required domain artifact")

    @staticmethod
    def _open_marker_directory(home_fd: int, cadence: str) -> int:
        cadence_fd = completions_fd = None
        try:
            cadence_fd = open_child_directory(home_fd, "cadence")
            completions_fd = open_child_directory(cadence_fd, "completions")
            return open_child_directory(completions_fd, cadence)
        finally:
            if completions_fd is not None:
                os.close(completions_fd)
            if cadence_fd is not None:
                os.close(cadence_fd)

    @staticmethod
    def _open_invocations_directory(home_fd: int) -> int:
        cadence_fd = None
        try:
            cadence_fd = open_child_directory(home_fd, "cadence")
            return open_child_directory(cadence_fd, "invocations")
        finally:
            if cadence_fd is not None:
                os.close(cadence_fd)

    @staticmethod
    def _artifact_refs_before(home_fd: int) -> list[str]:
        refs: list[str] = []
        for kind in ("review", "experiment"):
            directory_fd = open_child_directory(home_fd, f"{kind}s")
            try:
                for name in os.listdir(directory_fd):
                    if not name.endswith(".json"):
                        continue
                    identifier = name.removesuffix(".json")
                    if ARTIFACT_REF_PATTERN.fullmatch(f"{kind}:{identifier}"):
                        refs.append(f"{kind}:{identifier}")
            finally:
                os.close(directory_fd)
        return sorted(refs)

    def begin(self, cadence: str, period_key: str, run_id: str) -> dict[str, object]:
        """Record the pre-run artifact set so completion cannot reuse old work."""
        self._validate_identity(cadence, period_key, run_id)
        home_fd = self._open_home()
        invocations_fd = None
        try:
            context = {
                "schema_version": 1,
                "cadence": cadence,
                "period_key": period_key,
                "run_id": run_id,
                "artifact_refs_before": self._artifact_refs_before(home_fd),
                "started_at": self.now().astimezone(timezone.utc).isoformat(),
            }
            invocations_fd = self._open_invocations_directory(home_fd)
            atomic_json_at(invocations_fd, f"{run_id}.json", context)
            return context
        finally:
            if invocations_fd is not None:
                os.close(invocations_fd)
            os.close(home_fd)

    def _read_invocation(
        self, home_fd: int, cadence: str, period_key: str, run_id: str
    ) -> dict[str, object]:
        invocations_fd = self._open_invocations_directory(home_fd)
        try:
            try:
                context = read_json_at(invocations_fd, f"{run_id}.json")
            except FileNotFoundError as error:
                raise ValidationError("cadence invocation context does not exist") from error
        finally:
            os.close(invocations_fd)
        expected = {
            "schema_version": 1,
            "cadence": cadence,
            "period_key": period_key,
            "run_id": run_id,
        }
        if any(context.get(key) != value for key, value in expected.items()):
            raise ValidationError("cadence invocation context identity does not match")
        before = context.get("artifact_refs_before")
        if not isinstance(before, list) or any(not isinstance(value, str) for value in before):
            raise ValidationError("cadence invocation artifact baseline is invalid")
        return context

    def complete(
        self,
        cadence: str,
        period_key: str,
        run_id: str,
        artifact_refs: Sequence[str],
    ) -> dict[str, object]:
        self._validate_identity(cadence, period_key, run_id)
        parsed_refs = self._parse_refs(artifact_refs)
        home_fd = self._open_home()
        marker_fd = None
        try:
            context = self._read_invocation(home_fd, cadence, period_key, run_id)
            old_refs = set(context["artifact_refs_before"])
            rendered_refs = {f"{kind}:{identifier}" for kind, identifier in parsed_refs}
            if rendered_refs & old_refs:
                raise ValidationError("cadence completion cannot reference an old artifact")
            self._validate_required_artifact(home_fd, cadence, parsed_refs)
            marker_fd = self._open_marker_directory(home_fd, cadence)
            marker = {
                "schema_version": 1,
                "cadence": cadence,
                "period_key": period_key,
                "run_id": run_id,
                "artifact_refs": [f"{kind}:{identifier}" for kind, identifier in parsed_refs],
                "completed_at": self.now().astimezone(timezone.utc).isoformat(),
            }
            atomic_json_at(marker_fd, self._marker_name(period_key, run_id), marker)
            return marker
        finally:
            if marker_fd is not None:
                os.close(marker_fd)
            os.close(home_fd)

    def read(self, cadence: str, period_key: str, run_id: str) -> dict[str, object]:
        self._validate_identity(cadence, period_key, run_id)
        home_fd = self._open_home()
        marker_fd = None
        try:
            marker_fd = self._open_marker_directory(home_fd, cadence)
            marker = read_json_at(marker_fd, self._marker_name(period_key, run_id))
            expected = {
                "schema_version": 1,
                "cadence": cadence,
                "period_key": period_key,
                "run_id": run_id,
            }
            if any(marker.get(key) != value for key, value in expected.items()):
                raise ValidationError("cadence completion marker identity does not match")
            refs = marker.get("artifact_refs")
            if not isinstance(refs, list):
                raise ValidationError("cadence completion marker artifact_refs are invalid")
            parsed_refs = self._parse_refs(refs)
            self._validate_required_artifact(home_fd, cadence, parsed_refs)
            return marker
        finally:
            if marker_fd is not None:
                os.close(marker_fd)
            os.close(home_fd)
