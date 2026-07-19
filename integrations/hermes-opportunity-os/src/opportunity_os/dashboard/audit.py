"""Append-only, field-diff-only audit log for dashboard mutations."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from opportunity_os.sanitizer import contains_secret
from opportunity_os.dashboard.schedule_validation import normalize_cron, normalize_timezone


_OPAQUE_ACTOR = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_ID = re.compile(
    r"^chg_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_FIELDS = frozenset({"enabled", "cron", "tz"})
_FORBIDDEN_FIELDS = frozenset({"payload", "message", "recipient", "to", "token", "command", "model"})
_OPERATION_ID = re.compile(
    r"^op_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
AuditStatus = Literal[
    "previewed",
    "approved",
    "applying",
    "applied",
    "failed",
    "conflict",
    "expired",
    "indeterminate",
]


class AuditLog:
    """Write one bounded JSON object per line without payload or identity content."""

    MAX_RECORD_BYTES = 4 * 1_024
    MAX_LOG_READ_BYTES = 8 * 1_024 * 1_024

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")

    @staticmethod
    def prepare_diff(diff: dict[str, object]) -> dict[str, object]:
        if not isinstance(diff, dict) or frozenset(diff) - _ALLOWED_FIELDS:
            raise ValueError("audit diff contains a forbidden field")
        if frozenset(diff) & _FORBIDDEN_FIELDS:
            raise ValueError("audit diff contains private content")
        prepared: dict[str, object] = {}
        for field, change in diff.items():
            if not isinstance(change, dict) or frozenset(change) != {"before", "after"}:
                raise ValueError("audit diff must contain before and after only")
            before = change["before"]
            after = change["after"]
            if contains_secret(before) or contains_secret(after):
                raise ValueError("audit diff contains secret content")
            if field == "enabled" and any(
                value is not None and type(value) is not bool for value in (before, after)
            ):
                raise ValueError("enabled audit values must be boolean")
            if field == "cron":
                before = normalize_cron(before) if before is not None else None
                after = normalize_cron(after) if after is not None else None
            if field == "tz":
                before = normalize_timezone(before) if before is not None else None
                after = normalize_timezone(after) if after is not None else None
            before_bytes = json.dumps(
                before, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
            after_bytes = json.dumps(
                after, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
            prepared[field] = {
                "before_sha256": hashlib.sha256(before_bytes).hexdigest(),
                "after_sha256": hashlib.sha256(after_bytes).hexdigest(),
                "summary": "boolean_changed" if field == "enabled" else "schedule_changed",
            }
        return prepared

    @staticmethod
    def _validate_prepared(diff: dict[str, object]) -> dict[str, object]:
        if not isinstance(diff, dict) or frozenset(diff) - _ALLOWED_FIELDS:
            raise ValueError("prepared audit diff contains a forbidden field")
        for field, value in diff.items():
            if not isinstance(value, dict) or frozenset(value) != {
                "before_sha256",
                "after_sha256",
                "summary",
            }:
                raise ValueError("prepared audit diff is invalid")
            if _SHA256.fullmatch(str(value["before_sha256"])) is None or _SHA256.fullmatch(
                str(value["after_sha256"])
            ) is None:
                raise ValueError("prepared audit digest is invalid")
            expected = "boolean_changed" if field == "enabled" else "schedule_changed"
            if value["summary"] != expected:
                raise ValueError("prepared audit summary is invalid")
        return diff

    def append(
        self,
        *,
        actor: str,
        request_id: str,
        target: str,
        status: AuditStatus,
        diff: dict[str, object],
        operation_id: str | None = None,
        prepared: bool = False,
    ) -> bool:
        if _OPAQUE_ACTOR.fullmatch(actor) is None:
            raise ValueError("audit actor must be opaque")
        if _REQUEST_ID.fullmatch(request_id) is None:
            raise ValueError("audit request id is invalid")
        if _TARGET.fullmatch(target) is None:
            raise ValueError("audit target is invalid")
        if status not in {
            "previewed",
            "approved",
            "applying",
            "applied",
            "failed",
            "conflict",
            "expired",
            "indeterminate",
        }:
            raise ValueError("audit status is invalid")
        if operation_id is not None and _OPERATION_ID.fullmatch(operation_id) is None:
            raise ValueError("audit operation id is invalid")
        record = {
            "actor": actor,
            "at": datetime.now(timezone.utc).isoformat(),
            "diff": self._validate_prepared(diff) if prepared else self.prepare_diff(diff),
            "operation_id": operation_id,
            "request_id": request_id,
            "status": status,
            "target": target,
        }
        encoded = (
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        if len(encoded) > self.MAX_RECORD_BYTES:
            raise ValueError("audit record is too large")
        with self.lock_path.open("a+b") as lock_file:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                if operation_id is not None and self.path.is_file():
                    if self.path.stat().st_size > self.MAX_LOG_READ_BYTES:
                        raise ValueError("audit log requires archival")
                    existing = self.path.read_bytes()
                    for line in existing.splitlines():
                        try:
                            prior = json.loads(line)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                        if (
                            prior.get("operation_id") == operation_id
                            and prior.get("status") == status
                        ):
                            return False
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                    0o600,
                )
                try:
                    os.chmod(self.path, 0o600)
                    written = os.write(descriptor, encoded)
                    if written != len(encoded):
                        raise OSError("short audit write")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return True
