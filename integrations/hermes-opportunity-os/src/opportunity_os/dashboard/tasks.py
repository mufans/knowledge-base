"""Privacy-safe, read-only OpenClaw Cron adapter.

OpenClaw owns schedule editing and execution.  This module deliberately exposes
only list/status/runs through fixed argv calls for the aggregate dashboard.
"""

from __future__ import annotations

import json
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from opportunity_os.dashboard.probes import CommandResult, CommandRunner
from opportunity_os.dashboard.schedule_validation import normalize_cron, normalize_timezone


DEFAULT_OPENCLAW_EXECUTABLE = "/opt/homebrew/bin/openclaw"
READ_TIMEOUT_SECONDS = 10
_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class TaskAdapterError(RuntimeError):
    """Safe adapter error that never includes command output."""


class TaskRunner(Protocol):
    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult: ...


class TaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    enabled: bool
    cron: str | None
    tz: str | None
    updated_at_ms: int
    provider_status: Literal["unknown"] = "unknown"
    cost_status: Literal["unknown"] = "unknown"


class TaskCommandStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    error_code: Literal[
        "timeout", "command_failed", "unavailable", "scheduler_disabled"
    ] | None = None
    provider_status: Literal["unknown"] = "unknown"
    cost_status: Literal["unknown"] = "unknown"


class TaskRunsStatus(TaskCommandStatus):
    run_count: int | None = None
    schema_recognized: bool = False


class TaskSchedulerStatus(TaskCommandStatus):
    scheduler_enabled: bool | None = None
    job_count: int | None = None
    next_wake_at_ms: int | None = None
    schema_recognized: bool = False


def _safe_job_id(value: str) -> str:
    if _JOB_ID.fullmatch(value) is None:
        raise ValueError("job_id must be a bounded CLI-safe identifier")
    return value


class OpenClawTaskAdapter:
    """Read OpenClaw Cron metadata without duplicating its control plane."""

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
        self._runner = runner or CommandRunner()
        self._openclaw_path = openclaw_path

    def _read(self, argv: tuple[str, ...]) -> CommandResult:
        return self._runner.run(
            (self._openclaw_path, "cron", *argv), READ_TIMEOUT_SECONDS
        )

    @staticmethod
    def _status(result: CommandResult) -> TaskCommandStatus:
        if result.timed_out:
            return TaskCommandStatus(
                ok=False, exit_code=None, timed_out=True,
                duration_ms=result.duration_ms, error_code="timeout",
            )
        if result.exit_code is None:
            return TaskCommandStatus(
                ok=False, exit_code=None, timed_out=False,
                duration_ms=result.duration_ms, error_code="unavailable",
            )
        if result.exit_code != 0:
            return TaskCommandStatus(
                ok=False, exit_code=result.exit_code, timed_out=False,
                duration_ms=result.duration_ms, error_code="command_failed",
            )
        return TaskCommandStatus(
            ok=True, exit_code=0, timed_out=False, duration_ms=result.duration_ms
        )

    def _json(self, result: CommandResult) -> object:
        if result.timed_out:
            raise TaskAdapterError("command_timeout")
        if result.exit_code != 0:
            raise TaskAdapterError("command_failed")
        encoded = result.stdout.encode("utf-8")
        if result.stdout_truncated or len(encoded) > self.MAX_OUTPUT_BYTES:
            raise TaskAdapterError("command_output_too_large")
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as error:
            raise TaskAdapterError("invalid_json") from error

    @staticmethod
    def _task_summary(task: object) -> TaskSummary:
        if not isinstance(task, dict):
            raise TaskAdapterError("invalid_task_schema")
        job_id = task.get("id")
        enabled = task.get("enabled")
        updated_at = task.get("updatedAtMs")
        if (
            not isinstance(job_id, str)
            or type(enabled) is not bool
            or not isinstance(updated_at, int)
            or isinstance(updated_at, bool)
            or updated_at < 0
        ):
            raise TaskAdapterError("invalid_task_schema")
        _safe_job_id(job_id)
        schedule = task.get("schedule")
        cron: object = task.get("cron")
        tz: object = task.get("tz")
        if isinstance(schedule, dict):
            kind = schedule.get("kind")
            if kind in {None, "cron"}:
                cron = schedule.get("expr", schedule.get("cron"))
                tz = schedule.get("tz", schedule.get("timezone"))
            else:
                cron = None
                tz = None
        if cron is None and tz is not None:
            raise TaskAdapterError("invalid_task_schema")
        if cron is not None:
            try:
                cron = normalize_cron(cron)
                tz = normalize_timezone(tz) if tz is not None else None
            except ValueError as error:
                raise TaskAdapterError("invalid_task_schema") from error
        return TaskSummary(
            job_id=job_id,
            enabled=enabled,
            cron=cron,
            tz=tz,
            updated_at_ms=updated_at,
        )

    def list(self) -> list[TaskSummary]:
        payload = self._json(self._read(("list", "--all", "--json")))
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            raise TaskAdapterError("invalid_task_schema")
        return [self._task_summary(task) for task in jobs]

    def status(self) -> TaskSchedulerStatus:
        result = self._read(("status", "--json"))
        command = self._status(result)
        if not command.ok:
            return TaskSchedulerStatus(**command.model_dump())
        payload = self._json(result)
        if not isinstance(payload, dict):
            raise TaskAdapterError("invalid_status_schema")
        enabled = payload.get("enabled")
        jobs = payload.get("jobs")
        next_wake = payload.get("nextWakeAtMs")
        if (
            type(enabled) is not bool
            or not isinstance(jobs, int)
            or isinstance(jobs, bool)
            or jobs < 0
            or (
                next_wake is not None
                and (
                    not isinstance(next_wake, int)
                    or isinstance(next_wake, bool)
                    or next_wake < 0
                )
            )
        ):
            raise TaskAdapterError("invalid_status_schema")
        return TaskSchedulerStatus(
            ok=enabled,
            exit_code=0,
            timed_out=False,
            duration_ms=result.duration_ms,
            error_code=None if enabled else "scheduler_disabled",
            scheduler_enabled=enabled,
            job_count=jobs,
            next_wake_at_ms=next_wake,
            schema_recognized=True,
        )

    def runs(self, job_id: str) -> TaskRunsStatus:
        result = self._read(
            ("runs", "--id", _safe_job_id(job_id), "--limit", "50")
        )
        status = self._status(result)
        run_count: int | None = None
        schema_recognized = False
        if status.ok and not result.stdout_truncated:
            encoded = result.stdout.encode("utf-8")
            if len(encoded) <= self.MAX_OUTPUT_BYTES:
                try:
                    payload = json.loads(result.stdout)
                except (json.JSONDecodeError, TypeError):
                    payload = None
                runs = payload.get("runs") if isinstance(payload, dict) else payload
                if isinstance(runs, list):
                    run_count = len(runs)
                    schema_recognized = True
        return TaskRunsStatus(
            **status.model_dump(),
            run_count=run_count,
            schema_recognized=schema_recognized,
        )
