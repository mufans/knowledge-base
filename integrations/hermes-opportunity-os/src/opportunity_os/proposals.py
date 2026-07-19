"""Bounded, crash-safe pending domain proposals behind OpenClaw authentication."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import stat
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal


ProposalKind = Literal["feedback", "change_requirement"]
MAX_TEXT_BYTES = 4_096
MAX_PENDING = 500
MAX_STORE_BYTES = 3 * 1_048_576
TTL = timedelta(days=30)


class ProposalError(ValueError):
    """A stable proposal error containing no filesystem details."""


def normalize_text(value: object) -> str:
    if not isinstance(value, str):
        raise ProposalError("proposal_text_invalid")
    normalized = unicodedata.normalize("NFC", value)
    if (
        not normalized.strip()
        or len(normalized.encode("utf-8")) > MAX_TEXT_BYTES
        or any(ord(character) < 32 and character not in "\n\t" for character in normalized)
        or any(0xD800 <= ord(character) <= 0xDFFF for character in normalized)
    ):
        raise ProposalError("proposal_text_invalid")
    return normalized.strip()


class ProposalStore:
    """Persist pending input under a separate lock and atomic replacement."""

    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        requested = Path(path).expanduser()
        self.path = requested.parent.absolute() / requested.name
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _read(self) -> list[dict[str, object]]:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags)
        except FileNotFoundError:
            return []
        except OSError as error:
            raise ProposalError("proposal_store_unavailable") from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_STORE_BYTES:
                raise ProposalError("proposal_store_invalid")
            rendered = os.read(descriptor, MAX_STORE_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(rendered) > MAX_STORE_BYTES:
            raise ProposalError("proposal_store_invalid")
        if not rendered.strip():
            return []
        try:
            value = json.loads(rendered.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ProposalError("proposal_store_invalid") from error
        records = value.get("proposals") if isinstance(value, dict) else None
        if not isinstance(records, list):
            raise ProposalError("proposal_store_invalid")
        return records

    def add(self, kind: ProposalKind, text: object) -> dict[str, object]:
        if kind not in {"feedback", "change_requirement"}:
            raise ProposalError("proposal_kind_invalid")
        content = normalize_text(text)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        try:
            lock_descriptor = os.open(self.lock_path, lock_flags, 0o600)
        except OSError as error:
            raise ProposalError("proposal_store_unavailable") from error
        try:
            if not stat.S_ISREG(os.fstat(lock_descriptor).st_mode):
                raise ProposalError("proposal_store_invalid")
            os.fchmod(lock_descriptor, 0o600)
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            now = self._now().astimezone(timezone.utc)
            records = self._read()
            earliest = now - TTL
            records = [
                item for item in records
                if isinstance(item, dict)
                and item.get("state") == "pending"
                and earliest <= _timestamp(item.get("created_at")) <= now
            ]
            if len(records) >= MAX_PENDING:
                raise ProposalError("proposal_capacity_reached")
            record: dict[str, object] = {
                "id": f"proposal-{secrets.token_hex(12)}",
                "kind": kind,
                "text": content,
                "state": "pending",
                "created_at": now.isoformat(),
                "expires_at": (now + TTL).isoformat(),
            }
            records.append(record)
            rendered = (
                json.dumps(
                    {"proposals": records},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ) + "\n"
            ).encode("utf-8")
            if len(rendered) > MAX_STORE_BYTES:
                raise ProposalError("proposal_capacity_reached")
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(rendered)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
                temp_name = ""
            except OSError as error:
                raise ProposalError("proposal_store_unavailable") from error
            finally:
                if temp_name:
                    try:
                        os.unlink(temp_name)
                    except FileNotFoundError:
                        pass
            return record
        finally:
            os.close(lock_descriptor)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
