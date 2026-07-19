"""Bounded OpenClaw and Hermes conversations with metadata-only persistence."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from opportunity_os.dashboard.events import EventHub
from opportunity_os.dashboard.probes import CommandResult, OPENCLAW_EXECUTABLE_PATH
from opportunity_os.sanitizer import contains_secret, sanitize_public


MAX_MESSAGE_BYTES = 8 * 1_024
MAX_SESSION_ID_LENGTH = 64
OPENCLAW_TIMEOUT_SECONDS = 600
HERMES_TIMEOUT_SECONDS = 1_500
DEFAULT_OPENCLAW_EXECUTABLE = "/opt/homebrew/bin/openclaw"
DEFAULT_HERMES_EXECUTABLE = "hermes"
DEFAULT_MAX_ACTIVE_TASKS = 2
MAX_PROVIDER_OUTPUT_BYTES = 64 * 1_024
DEFAULT_MAX_COMPLETED_TASKS = 100
DEFAULT_COMPLETED_TASK_TTL = timedelta(minutes=15)
_SESSION_UNSAFE = re.compile(r"[^a-z0-9._-]+")
_SAFE_RUNTIME_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_OWNER_ID = re.compile(r"^[0-9a-f]{64}$")


class ConversationRunner(Protocol):
    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult: ...


class ConversationAdapter(Protocol):
    def send(self, session_id: str, message: str) -> "ConversationResult": ...


class ConversationBusyError(RuntimeError):
    """The bounded conversation executor has no safe capacity."""


@dataclass(slots=True)
class _BoundedCapture:
    data: bytearray = field(default_factory=bytearray)
    truncated: bool = False


def _drain_bounded(pipe, capture: _BoundedCapture, maximum: int) -> None:
    try:
        try:
            while chunk := pipe.read(8 * 1_024):
                remaining = maximum - len(capture.data)
                if remaining > 0:
                    capture.data.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    capture.truncated = True
        except (OSError, ValueError):
            pass
    finally:
        try:
            pipe.close()
        except (OSError, ValueError):
            pass


def _decode_capture(capture: _BoundedCapture) -> str:
    return bytes(capture.data).decode("utf-8", errors="ignore")


class BoundedCommandRunner:
    """Drain subprocess pipes while retaining at most a fixed byte count per stream."""

    def __init__(self, *, max_output_bytes: int = MAX_PROVIDER_OUTPUT_BYTES) -> None:
        if not 1 <= max_output_bytes <= MAX_PROVIDER_OUTPUT_BYTES:
            raise ValueError(f"max_output_bytes must be between 1 and {MAX_PROVIDER_OUTPUT_BYTES}")
        self._max_output_bytes = max_output_bytes

    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult:
        started = time.monotonic()
        environment = (
            {**os.environ, "PATH": OPENCLAW_EXECUTABLE_PATH}
            if argv and Path(argv[0]).name == "openclaw"
            else None
        )
        try:
            process = subprocess.Popen(
                argv,
                env=environment,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError:
            return CommandResult(
                exit_code=None,
                stdout="",
                stderr="",
                timed_out=False,
                duration_ms=round((time.monotonic() - started) * 1_000),
            )
        assert process.stdout is not None and process.stderr is not None
        stdout = _BoundedCapture()
        stderr = _BoundedCapture()
        readers = (
            threading.Thread(
                target=_drain_bounded,
                args=(process.stdout, stdout, self._max_output_bytes),
                daemon=True,
            ),
            threading.Thread(
                target=_drain_bounded,
                args=(process.stderr, stderr, self._max_output_bytes),
                daemon=True,
            ),
        )
        for reader in readers:
            reader.start()
        timed_out = False
        exit_code: int | None
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
            process.wait()
            exit_code = None
        for reader in readers:
            reader.join(timeout=1)
        for pipe, reader in zip((process.stdout, process.stderr), readers, strict=True):
            if reader.is_alive():
                pipe.close()
                reader.join(timeout=0.1)
        return CommandResult(
            exit_code=exit_code,
            stdout=_decode_capture(stdout),
            stderr=_decode_capture(stderr),
            timed_out=timed_out,
            duration_ms=round((time.monotonic() - started) * 1_000),
            stdout_truncated=stdout.truncated,
            stderr_truncated=stderr.truncated,
        )


def _validate_owner_id(owner_id: str) -> str:
    if _OWNER_ID.fullmatch(owner_id) is None:
        raise ValueError("owner_id must be an opaque server-side identifier")
    return owner_id


def normalize_session_id(value: str) -> str:
    """Return a bounded CLI-safe session ID without accepting path-like input."""
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    normalized = _SESSION_UNSAFE.sub("-", normalized).strip("-._")
    normalized = normalized[:MAX_SESSION_ID_LENGTH].rstrip("-._")
    if not normalized:
        raise ValueError("session_id must contain an ASCII letter or number")
    return normalized


def _validate_message(message: str) -> str:
    size = len(message.encode("utf-8"))
    if not message.strip():
        raise ValueError("message must not be blank")
    if size > MAX_MESSAGE_BYTES:
        raise ValueError(f"message must not exceed {MAX_MESSAGE_BYTES} UTF-8 bytes")
    return message


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=MAX_MESSAGE_BYTES)

    target: Literal["openclaw", "hermes"]
    session_id: str
    message: str

    @field_validator("session_id")
    @classmethod
    def normalized_session(cls, value: str) -> str:
        return normalize_session_id(value)

    @field_validator("message")
    @classmethod
    def bounded_message(cls, value: str) -> str:
        return _validate_message(value)


class ConversationResult(BaseModel):
    """Browser-safe final answer metadata; raw stderr is intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    final_text: str
    provider: str | None = None
    model: str | None = None
    token_status: Literal["reported", "unknown"]
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_status: Literal["reported", "unknown"]
    exit_code: int | None
    duration_ms: int
    error_code: Literal["timeout", "command_failed", "invalid_output", "adapter_failure"] | None = None
    truncated: bool = False


class ConversationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    target: Literal["openclaw", "hermes"]
    session_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: datetime
    updated_at: datetime
    result: ConversationResult | None = None


class ConversationAccepted(BaseModel):
    task_id: str


def _safe_label(value: object) -> str | None:
    if not isinstance(value, str) or contains_secret(value) or not _SAFE_RUNTIME_LABEL.fullmatch(value):
        return None
    return value


def _token_count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _truncate_utf8(value: str, maximum: int = MAX_PROVIDER_OUTPUT_BYTES) -> tuple[str, bool]:
    """Bound a string without first encoding or copying its unbounded tail."""
    prefix = value[: maximum + 1]
    encoded = prefix.encode("utf-8")
    if len(value) <= maximum and len(encoded) <= maximum:
        return value, False
    bounded = encoded[:maximum].decode("utf-8", errors="ignore")
    return bounded, True


def _first_mapping(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    current = payload
    for key in ("result", "data", "payload"):
        nested = current.get(key)
        if isinstance(nested, dict):
            current = nested
            break
    return current


def _final_text(payload: dict[str, object]) -> str | None:
    payloads = payload.get("payloads")
    if isinstance(payloads, list):
        for item in reversed(payloads):
            if isinstance(item, dict):
                for key in ("text", "final", "final_text"):
                    if isinstance(item.get(key), str):
                        return item[key]  # type: ignore[return-value]
    for key in ("final", "final_text", "text", "response", "output"):
        if isinstance(payload.get(key), str):
            return payload[key]  # type: ignore[return-value]
    return None


def _parse_json_result(
    stdout: str,
) -> tuple[str, str | None, str | None, dict[str, int | None], str, bool] | None:
    try:
        decoded = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    payload = _first_mapping(decoded)
    text = _final_text(payload)
    if text is None:
        return None
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    tokens = {
        "input_tokens": _token_count(usage.get("input_tokens")),
        "output_tokens": _token_count(usage.get("output_tokens")),
        "total_tokens": _token_count(usage.get("total_tokens")),
    }
    raw_cost_status = payload.get("cost_status")
    cost_status = (
        raw_cost_status
        if raw_cost_status in {"reported", "unknown"}
        else "reported" if isinstance(payload.get("cost"), (int, float)) else "unknown"
    )
    bounded_text, text_truncated = _truncate_utf8(text)
    sanitized = sanitize_public(bounded_text)
    return (
        sanitized if isinstance(sanitized, str) else "",
        _safe_label(payload.get("provider")),
        _safe_label(payload.get("model")),
        tokens,
        cost_status,
        text_truncated,
    )


class _BaseConversationAdapter:
    def __init__(self, runner: ConversationRunner) -> None:
        self._runner = runner

    def _execute(
        self,
        *,
        session_id: str,
        argv: tuple[str, ...],
        timeout: int,
        allow_plain_text: bool,
    ) -> ConversationResult:
        normalized_session = normalize_session_id(session_id)
        result = self._runner.run(argv, timeout)
        bounded_stdout, output_truncated = _truncate_utf8(result.stdout)
        output_truncated = output_truncated or result.stdout_truncated
        if result.timed_out:
            return ConversationResult(
                session_id=normalized_session,
                final_text="",
                token_status="unknown",
                cost_status="unknown",
                exit_code=None,
                duration_ms=result.duration_ms,
                error_code="timeout",
                truncated=output_truncated,
            )
        if result.exit_code != 0:
            return ConversationResult(
                session_id=normalized_session,
                final_text="",
                token_status="unknown",
                cost_status="unknown",
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                error_code="command_failed",
                truncated=output_truncated,
            )
        parsed = _parse_json_result(bounded_stdout)
        if parsed is None and allow_plain_text and bounded_stdout.strip():
            plain_text, text_truncated = _truncate_utf8(bounded_stdout.strip())
            sanitized = sanitize_public(plain_text)
            parsed = (
                sanitized if isinstance(sanitized, str) else "",
                None,
                None,
                {"input_tokens": None, "output_tokens": None, "total_tokens": None},
                "unknown",
                text_truncated,
            )
        if parsed is None:
            return ConversationResult(
                session_id=normalized_session,
                final_text="",
                token_status="unknown",
                cost_status="unknown",
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                error_code="invalid_output",
                truncated=output_truncated,
            )
        text, provider, model, tokens, cost_status, text_truncated = parsed
        token_status = "reported" if any(value is not None for value in tokens.values()) else "unknown"
        return ConversationResult(
            session_id=normalized_session,
            final_text=text,
            provider=provider,
            model=model,
            token_status=token_status,
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            total_tokens=tokens["total_tokens"],
            cost_status=cost_status,  # type: ignore[arg-type]
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            truncated=output_truncated or text_truncated,
        )


class OpenClawConversationAdapter(_BaseConversationAdapter):
    def __init__(
        self,
        runner: ConversationRunner,
        *,
        openclaw_path: str = DEFAULT_OPENCLAW_EXECUTABLE,
    ) -> None:
        super().__init__(runner)
        if openclaw_path != DEFAULT_OPENCLAW_EXECUTABLE:
            raise ValueError(
                f"openclaw_path must be the fixed executable {DEFAULT_OPENCLAW_EXECUTABLE}"
            )
        self._openclaw_path = openclaw_path

    def send(self, session_id: str, message: str) -> ConversationResult:
        normalized_session = normalize_session_id(session_id)
        bounded_message = _validate_message(message)
        argv = (
            self._openclaw_path,
            "agent",
            "--session-id",
            normalized_session,
            "--message",
            bounded_message,
            "--timeout",
            str(OPENCLAW_TIMEOUT_SECONDS),
            "--json",
        )
        return self._execute(
            session_id=normalized_session,
            argv=argv,
            timeout=OPENCLAW_TIMEOUT_SECONDS,
            allow_plain_text=False,
        )


class HermesConversationAdapter(_BaseConversationAdapter):
    def __init__(
        self,
        runner: ConversationRunner,
        *,
        hermes_path: str = DEFAULT_HERMES_EXECUTABLE,
    ) -> None:
        super().__init__(runner)
        if hermes_path != DEFAULT_HERMES_EXECUTABLE:
            raise ValueError("hermes_path must be the fixed hermes executable")
        self._hermes_path = hermes_path

    def send(self, session_id: str, message: str) -> ConversationResult:
        normalized_session = normalize_session_id(session_id)
        bounded_message = _validate_message(message)
        argv = (
            self._hermes_path,
            "-p",
            "opportunity-discovery",
            "chat",
            "-Q",
            "-q",
            bounded_message,
            "--source",
            "tool",
            "--skills",
            "opportunity-discovery",
        )
        return self._execute(
            session_id=normalized_session,
            argv=argv,
            timeout=HERMES_TIMEOUT_SECONDS,
            allow_plain_text=True,
        )


class ConversationService:
    """Run bounded conversations asynchronously and persist only session metadata."""

    def __init__(
        self,
        *,
        openclaw: ConversationAdapter,
        hermes: ConversationAdapter,
        event_hub: EventHub,
        sessions_path: str | Path,
        max_active_tasks: int = DEFAULT_MAX_ACTIVE_TASKS,
        max_completed_tasks: int = DEFAULT_MAX_COMPLETED_TASKS,
        completed_ttl: timedelta = DEFAULT_COMPLETED_TASK_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_active_tasks < 1 or max_active_tasks > 16:
            raise ValueError("max_active_tasks must be between 1 and 16")
        if not 1 <= max_completed_tasks <= DEFAULT_MAX_COMPLETED_TASKS:
            raise ValueError(
                f"max_completed_tasks must be between 1 and {DEFAULT_MAX_COMPLETED_TASKS}"
            )
        if completed_ttl <= timedelta(0) or completed_ttl > DEFAULT_COMPLETED_TASK_TTL:
            raise ValueError("completed_ttl must be positive and at most 15 minutes")
        self._adapters = {"openclaw": openclaw, "hermes": hermes}
        self._event_hub = event_hub
        self._sessions_path = Path(sessions_path)
        self._tasks: dict[str, ConversationTask] = {}
        self._task_owners: dict[str, str] = {}
        self._completion_order: dict[str, int] = {}
        self._completion_cursor = 0
        self._active_task_ids: set[str] = set()
        self._max_active_tasks = max_active_tasks
        self._max_completed_tasks = max_completed_tasks
        self._completed_ttl = completed_ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._active_sessions: set[tuple[str, str]] = set()
        self._lock = threading.RLock()

    @property
    def tasks(self) -> dict[str, ConversationTask]:
        with self._lock:
            self._cleanup_completed_locked(self._clock())
            return {key: value.model_copy(deep=True) for key, value in self._tasks.items()}

    def submit(self, request: ConversationRequest, *, owner_id: str) -> str:
        owner = _validate_owner_id(owner_id)
        active_session = (owner, request.session_id)
        now = self._clock()
        task_id = f"conv_{uuid.uuid4()}"
        task = ConversationTask(
            task_id=task_id,
            target=request.target,
            session_id=request.session_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._cleanup_completed_locked(now)
            if (
                len(self._active_sessions) >= self._max_active_tasks
                or active_session in self._active_sessions
            ):
                raise ConversationBusyError("conversation capacity reached")
            self._tasks[task_id] = task
            self._task_owners[task_id] = owner
            self._active_sessions.add(active_session)
            self._active_task_ids.add(task_id)
        thread = threading.Thread(
            target=self._run,
            args=(task_id, request, owner),
            name=f"conversation-{task_id}",
            daemon=True,
        )
        try:
            thread.start()
        except RuntimeError:
            with self._lock:
                self._tasks.pop(task_id, None)
                self._task_owners.pop(task_id, None)
                self._active_sessions.discard(active_session)
                self._active_task_ids.discard(task_id)
            raise
        return task_id

    def get(self, task_id: str, *, owner_id: str) -> ConversationTask:
        owner = _validate_owner_id(owner_id)
        with self._lock:
            self._cleanup_completed_locked(self._clock())
            if task_id not in self._tasks or self._task_owners.get(task_id) != owner:
                raise KeyError(task_id)
            return self._tasks[task_id].model_copy(deep=True)

    def _replace(self, task_id: str, **updates: object) -> ConversationTask:
        with self._lock:
            task = self._tasks[task_id].model_copy(
                update={**updates, "updated_at": self._clock()}
            )
            self._tasks[task_id] = task
            return task

    def _complete_task(
        self,
        task_id: str,
        *,
        status: Literal["succeeded", "failed"],
        result: ConversationResult,
    ) -> ConversationTask:
        with self._lock:
            task = self._tasks[task_id].model_copy(
                update={"status": status, "result": result, "updated_at": self._clock()}
            )
            self._tasks[task_id] = task
            self._completion_cursor += 1
            self._completion_order[task_id] = self._completion_cursor
            return task

    def _run(self, task_id: str, request: ConversationRequest, owner_id: str) -> None:
        try:
            self._replace(task_id, status="running")
            self._publish_lifecycle(
                "conversation.started",
                task_id=task_id,
                target=request.target,
                audience=owner_id,
            )
            try:
                result = self._adapters[request.target].send(request.session_id, request.message)
            except Exception:
                result = ConversationResult(
                    session_id=request.session_id,
                    final_text="",
                    token_status="unknown",
                    cost_status="unknown",
                    exit_code=None,
                    duration_ms=0,
                    error_code="adapter_failure",
                )
            result = self._bounded_result(result)
            succeeded = result.error_code is None and result.exit_code == 0
            status = "succeeded" if succeeded else "failed"
            self._complete_task(task_id, status=status, result=result)
            try:
                self._persist_session(owner_id, task_id, request.target, result, status)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            self._publish_lifecycle(
                "conversation.completed" if succeeded else "conversation.failed",
                task_id=task_id,
                target=request.target,
                audience=owner_id,
            )
            with self._lock:
                self._cleanup_completed_locked(self._clock())
        finally:
            with self._lock:
                self._active_sessions.discard((owner_id, request.session_id))
                self._active_task_ids.discard(task_id)
                self._cleanup_completed_locked(self._clock())

    @staticmethod
    def _bounded_result(result: ConversationResult) -> ConversationResult:
        final_text, truncated = _truncate_utf8(result.final_text)
        if final_text == result.final_text and not truncated:
            return result
        return result.model_copy(
            update={
                "final_text": final_text,
                "truncated": result.truncated or truncated,
            }
        )

    def _cleanup_completed_locked(self, now: datetime) -> None:
        completed = [
            task_id
            for task_id, task in self._tasks.items()
            if task.status in {"succeeded", "failed"} and task_id not in self._active_task_ids
        ]
        expired = {
            task_id
            for task_id in completed
            if now - self._tasks[task_id].updated_at >= self._completed_ttl
        }
        retained = sorted(
            (task_id for task_id in completed if task_id not in expired),
            key=lambda task_id: self._completion_order.get(task_id, 0),
            reverse=True,
        )
        evicted = expired | set(retained[self._max_completed_tasks :])
        for task_id in evicted:
            self._tasks.pop(task_id, None)
            self._task_owners.pop(task_id, None)
            self._completion_order.pop(task_id, None)

    def _publish_lifecycle(
        self,
        event_type: str,
        *,
        task_id: str,
        target: str,
        audience: str,
    ) -> None:
        try:
            self._event_hub.publish(
                event_type,
                {"task_id": task_id, "target": target},
                audience=audience,
            )
        except OSError:
            pass

    def _persist_session(
        self,
        owner_id: str,
        task_id: str,
        target: str,
        result: ConversationResult,
        status: str,
    ) -> None:
        with self._lock:
            payload: dict[str, object] = {"owners": {}}
            if self._sessions_path.is_file():
                decoded = json.loads(self._sessions_path.read_text(encoding="utf-8"))
                if isinstance(decoded, dict) and isinstance(decoded.get("owners"), dict):
                    payload = {"owners": dict(decoded["owners"])}
            owners = payload["owners"]
            assert isinstance(owners, dict)
            owner = owners.setdefault(owner_id, {"sessions": {}})
            if not isinstance(owner, dict) or not isinstance(owner.get("sessions"), dict):
                owner = {"sessions": {}}
                owners[owner_id] = owner
            sessions = owner["sessions"]
            assert isinstance(sessions, dict)
            sessions[result.session_id] = {
                "target": target,
                "last_task_id": task_id,
                "status": status,
                "provider": result.provider,
                "model": result.model,
                "token_status": result.token_status,
                "cost_status": result.cost_status,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "updated_at": self._clock().isoformat(),
            }
            self._atomic_write(payload)

    def _atomic_write(self, payload: dict[str, object]) -> None:
        self._sessions_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".sessions.", suffix=".tmp", dir=self._sessions_path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self._sessions_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
