"""Small pending-proposal inbox behind OpenClaw's authenticated owner entry."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal


ProposalKind = Literal["feedback", "change_requirement"]
MAX_TEXT_BYTES = 4_096
MAX_PENDING = 500
TTL = timedelta(days=30)


class ProposalError(ValueError):
    pass


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
    """Persist pending domain input; another native workflow decides what to apply."""

    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        requested = Path(path).expanduser()
        self.path = requested.parent.resolve() / requested.name
        self._now = now or (lambda: datetime.now(timezone.utc))

    def add(self, kind: ProposalKind, text: object) -> dict[str, object]:
        if kind not in {"feedback", "change_requirement"}:
            raise ProposalError("proposal_kind_invalid")
        content = normalize_text(text)
        now = self._now().astimezone(timezone.utc)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            with os.fdopen(descriptor, "r+", encoding="utf-8", closefd=False) as handle:
                rendered = handle.read()
                if rendered.strip():
                    try:
                        value = json.loads(rendered)
                    except json.JSONDecodeError as error:
                        raise ProposalError("proposal_store_invalid") from error
                else:
                    value = {"proposals": []}
                records = value.get("proposals") if isinstance(value, dict) else None
                if not isinstance(records, list):
                    raise ProposalError("proposal_store_invalid")
                earliest = now - TTL
                records = [
                    item for item in records
                    if isinstance(item, dict)
                    and item.get("state") == "pending"
                    and _timestamp(item.get("created_at")) >= earliest
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
                handle.seek(0)
                handle.truncate()
                json.dump({"proposals": records}, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                return record
        finally:
            os.close(descriptor)


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
