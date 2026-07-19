"""Typed, fixed-argv OpenClaw Cron adapter with privacy-safe DTOs."""

from __future__ import annotations

import hashlib
import json
import fcntl
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from opportunity_os.dashboard.probes import CommandResult
from opportunity_os.dashboard.schedule_validation import normalize_schedule


DEFAULT_OPENCLAW_EXECUTABLE = "/opt/homebrew/bin/openclaw"
READ_TIMEOUT_SECONDS = 10
WRITE_TIMEOUT_SECONDS = 30
_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class TaskAdapterError(RuntimeError):
    """A safe adapter error that contains no OpenClaw output."""


class TaskRunner(Protocol):
    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult: ...


class TaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    enabled: bool
    cron: str | None
    tz: str | None
    updated_at_ms: int
    revision: str
    provider_status: Literal["unknown"] = "unknown"
    cost_status: Literal["unknown"] = "unknown"


class TaskCommandStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    error_code: Literal["timeout", "command_failed", "unavailable"] | None = None
    provider_status: Literal["unknown"] = "unknown"
    cost_status: Literal["unknown"] = "unknown"


class TaskRunsStatus(TaskCommandStatus):
    run_count: int | None = None
    schema_recognized: bool = False


def _safe_job_id(value: str) -> str:
    if _JOB_ID.fullmatch(value) is None:
        raise ValueError("job_id must be a bounded CLI-safe identifier")
    return value


def task_revision(task: dict[str, object]) -> str:
    """Hash canonical full task JSON and its explicit updatedAtMs revision component."""
    if not isinstance(task, dict):
        raise TaskAdapterError("invalid_task_schema")
    updated_at = task.get("updatedAtMs")
    if not isinstance(updated_at, int) or isinstance(updated_at, bool) or updated_at < 0:
        raise TaskAdapterError("invalid_task_schema")
    try:
        canonical = json.dumps(
            task,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TaskAdapterError("invalid_task_schema") from error
    return hashlib.sha256(
        b"opportunity-os/openclaw-task-revision/v1\0"
        + canonical
        + b"\0"
        + str(updated_at).encode("ascii")
    ).hexdigest()


class OpenClawTaskAdapter:
    """Expose only the six documented OpenClaw Cron command shapes."""

    MAX_OUTPUT_BYTES = 1 * 1_024 * 1_024

    def __init__(
        self,
        runner: TaskRunner | None = None,
        *,
        openclaw_path: str = DEFAULT_OPENCLAW_EXECUTABLE,
    ) -> None:
        if openclaw_path != DEFAULT_OPENCLAW_EXECUTABLE:
            raise ValueError(
                f"openclaw_path must be the fixed executable {DEFAULT_OPENCLAW_EXECUTABLE}"
            )
        if runner is None:
            from opportunity_os.dashboard.conversations import BoundedCommandRunner

            runner = BoundedCommandRunner()
        self._runner = runner
        self._openclaw_path = openclaw_path

    def _run(self, argv: tuple[str, ...], timeout: int) -> CommandResult:
        return self._runner.run((self._openclaw_path, "cron", *argv), timeout)

    def _status(self, result: CommandResult) -> TaskCommandStatus:
        if result.timed_out:
            return TaskCommandStatus(
                ok=False,
                exit_code=None,
                timed_out=True,
                duration_ms=result.duration_ms,
                error_code="timeout",
            )
        if result.exit_code is None:
            return TaskCommandStatus(
                ok=False,
                exit_code=None,
                timed_out=False,
                duration_ms=result.duration_ms,
                error_code="unavailable",
            )
        if result.exit_code != 0:
            return TaskCommandStatus(
                ok=False,
                exit_code=result.exit_code,
                timed_out=False,
                duration_ms=result.duration_ms,
                error_code="command_failed",
            )
        return TaskCommandStatus(
            ok=True,
            exit_code=0,
            timed_out=False,
            duration_ms=result.duration_ms,
        )

    def _json(self, result: CommandResult) -> object:
        if result.timed_out:
            raise TaskAdapterError("command_timeout")
        if result.exit_code != 0:
            raise TaskAdapterError("command_failed")
        prefix = result.stdout[: self.MAX_OUTPUT_BYTES + 1]
        if result.stdout_truncated or len(prefix.encode("utf-8")) > self.MAX_OUTPUT_BYTES:
            raise TaskAdapterError("command output exceeded bounded limit")
        try:
            return json.loads(prefix)
        except (json.JSONDecodeError, TypeError) as error:
            raise TaskAdapterError("invalid_json") from error

    @staticmethod
    def _task_summary(task: object) -> TaskSummary:
        if not isinstance(task, dict):
            raise TaskAdapterError("invalid_task_schema")
        job_id = task.get("id")
        enabled = task.get("enabled")
        updated_at = task.get("updatedAtMs")
        if not isinstance(job_id, str):
            raise TaskAdapterError("invalid_task_schema")
        _safe_job_id(job_id)
        if type(enabled) is not bool or not isinstance(updated_at, int) or isinstance(updated_at, bool):
            raise TaskAdapterError("invalid_task_schema")
        schedule = task.get("schedule")
        cron: object = task.get("cron")
        tz: object = task.get("tz")
        if isinstance(schedule, dict):
            cron = schedule.get("expr", schedule.get("cron"))
            tz = schedule.get("tz", schedule.get("timezone"))
        if (cron is None) != (tz is None):
            raise TaskAdapterError("invalid_task_schema")
        if cron is not None and tz is not None:
            try:
                cron, tz = normalize_schedule(cron, tz)
            except ValueError as error:
                raise TaskAdapterError("invalid_task_schema") from error
        return TaskSummary(
            job_id=job_id,
            enabled=enabled,
            cron=cron,
            tz=tz,
            updated_at_ms=updated_at,
            revision=task_revision(task),
        )

    def list(self) -> list[TaskSummary]:
        payload = self._json(self._run(("list", "--all", "--json"), READ_TIMEOUT_SECONDS))
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            raise TaskAdapterError("invalid_task_schema")
        return [self._task_summary(task) for task in jobs]

    def status(self) -> TaskCommandStatus:
        return self._status(self._run(("status",), READ_TIMEOUT_SECONDS))

    def runs(self, job_id: str) -> TaskRunsStatus:
        result = self._run(
            ("runs", "--id", _safe_job_id(job_id), "--limit", "50"),
            READ_TIMEOUT_SECONDS,
        )
        status = self._status(result)
        run_count: int | None = None
        schema_recognized = False
        if status.ok:
            prefix = result.stdout[: self.MAX_OUTPUT_BYTES + 1]
            if not result.stdout_truncated and len(prefix.encode("utf-8")) <= self.MAX_OUTPUT_BYTES:
                try:
                    payload = json.loads(prefix)
                except (json.JSONDecodeError, TypeError):
                    payload = None
                runs = payload.get("runs") if isinstance(payload, dict) else payload
                if isinstance(runs, list):
                    run_count = len(runs)
                    schema_recognized = True
        return TaskRunsStatus(
            **status.model_dump(), run_count=run_count, schema_recognized=schema_recognized
        )

    def edit_enabled(self, job_id: str, enabled: bool) -> TaskCommandStatus:
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        flag = "--enable" if enabled else "--disable"
        return self._status(
            self._run(("edit", _safe_job_id(job_id), flag), WRITE_TIMEOUT_SECONDS)
        )

    def edit_schedule(self, job_id: str, cron: str, tz: str) -> TaskCommandStatus:
        cron, tz = normalize_schedule(cron, tz)
        return self._status(
            self._run(
                ("edit", _safe_job_id(job_id), "--cron", cron, "--tz", tz),
                WRITE_TIMEOUT_SECONDS,
            )
        )

    def run_now(self, job_id: str) -> TaskCommandStatus:
        return self._status(
            self._run(("run", _safe_job_id(job_id)), WRITE_TIMEOUT_SECONDS)
        )


_MutationResult = TypeVar("_MutationResult")


class TaskMutationCoordinator:
    """Serialize attested broker writes and perform the final revision read under flock."""

    def __init__(self, adapter: OpenClawTaskAdapter, lock_dir: str | Path) -> None:
        self.adapter = adapter
        self.lock_dir = Path(lock_dir).expanduser().resolve()
        self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.lock_dir, 0o700)
        self._thread_lock = threading.RLock()

    def _lock_path(self, job_id: str) -> Path:
        safe_id = _safe_job_id(job_id)
        digest = hashlib.sha256(safe_id.encode("ascii")).hexdigest()
        return self.lock_dir / f"task-{digest}.lock"

    def mutate(
        self,
        job_id: str,
        *,
        expected_revision: str,
        mutation: Callable[[], _MutationResult],
        verify: Callable[[TaskSummary], bool],
    ) -> _MutationResult:
        lock_path = self._lock_path(job_id)
        with self._thread_lock, lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                before = next(
                    (task for task in self.adapter.list() if task.job_id == job_id), None
                )
                if before is None:
                    raise TaskAdapterError("task_not_found")
                if before.revision != expected_revision:
                    raise TaskAdapterError("revision_conflict")
                result = mutation()
                after = next(
                    (task for task in self.adapter.list() if task.job_id == job_id), None
                )
                if after is None or not verify(after):
                    raise TaskAdapterError("task_verification_failed")
                return result
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
