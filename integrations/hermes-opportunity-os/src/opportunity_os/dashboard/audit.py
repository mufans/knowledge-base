"""Append-only, field-diff-only audit log for dashboard mutations."""

from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from opportunity_os.sanitizer import contains_secret


_OPAQUE_ACTOR = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_ID = re.compile(
    r"^chg_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_FIELDS = frozenset({"enabled", "cron", "tz"})
_FORBIDDEN_FIELDS = frozenset({"payload", "message", "recipient", "to", "token", "command", "model"})
AuditStatus = Literal["previewed", "approved", "applied", "failed", "conflict"]


class AuditLog:
    """Write one bounded JSON object per line without payload or identity content."""

    MAX_RECORD_BYTES = 4 * 1_024

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")

    @staticmethod
    def _validate_diff(diff: dict[str, object]) -> dict[str, object]:
        if not isinstance(diff, dict) or frozenset(diff) - _ALLOWED_FIELDS:
            raise ValueError("audit diff contains a forbidden field")
        if frozenset(diff) & _FORBIDDEN_FIELDS:
            raise ValueError("audit diff contains private content")
        normalized: dict[str, object] = {}
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
            if field in {"cron", "tz"} and any(
                value is not None
                and (not isinstance(value, str) or len(value.encode("utf-8")) > 256)
                for value in (before, after)
            ):
                raise ValueError("schedule audit values must be bounded strings")
            normalized[field] = {"before": before, "after": after}
        return normalized

    def append(
        self,
        *,
        actor: str,
        request_id: str,
        target: str,
        status: AuditStatus,
        diff: dict[str, object],
    ) -> None:
        if _OPAQUE_ACTOR.fullmatch(actor) is None:
            raise ValueError("audit actor must be opaque")
        if _REQUEST_ID.fullmatch(request_id) is None:
            raise ValueError("audit request id is invalid")
        if _TARGET.fullmatch(target) is None:
            raise ValueError("audit target is invalid")
        if status not in {"previewed", "approved", "applied", "failed", "conflict"}:
            raise ValueError("audit status is invalid")
        record = {
            "actor": actor,
            "at": datetime.now(timezone.utc).isoformat(),
            "diff": self._validate_diff(diff),
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
