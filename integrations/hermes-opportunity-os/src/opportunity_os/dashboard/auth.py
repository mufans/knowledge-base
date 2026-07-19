"""Server-side dashboard sessions, one-time bootstrap tokens, and CSRF checks."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import tempfile
import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


SessionKind = Literal["local", "remote"]
LOCAL_SESSION_TTL = timedelta(hours=8)
REMOTE_SESSION_TTL = timedelta(hours=12)
BOOTSTRAP_TTL = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class Session:
    """Resolved server-side session; only the opaque token is stored in the cookie."""

    key: str
    kind: SessionKind
    expires_at: datetime
    csrf_token: str


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session: Session
    token: str


class SessionInfo(BaseModel):
    kind: SessionKind
    expires_at: datetime
    csrf_token: str


class SessionStore:
    """Persist hashed session/bootstrap credentials under the private dashboard home."""

    def __init__(self, home: str | Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.home = Path(home).expanduser().resolve()
        self.path = self.home / "auth.json"
        self.lock_path = self.home / ".auth.lock"
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.home, 0o700)

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.is_file():
            return {"sessions": {}, "bootstraps": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "sessions": dict(payload.get("sessions", {})),
            "bootstraps": dict(payload.get("bootstraps", {})),
        }

    def _write(self, payload: dict[str, dict[str, object]]) -> None:
        descriptor, temp_name = tempfile.mkstemp(prefix=".auth.", suffix=".tmp", dir=self.home)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @contextmanager
    def _transaction(self):
        """Serialize read-modify-write cycles across the CLI and server processes."""
        with self._lock, self.lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(self.lock_path, 0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield self._read()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _purge_expired(self, payload: dict[str, dict[str, object]], now: datetime) -> None:
        sessions = payload["sessions"]
        bootstraps = payload["bootstraps"]
        for key, value in list(sessions.items()):
            if datetime.fromisoformat(value["expires_at"]) <= now:  # type: ignore[index]
                del sessions[key]
        for key, value in list(bootstraps.items()):
            if datetime.fromisoformat(str(value)) <= now:
                del bootstraps[key]

    @staticmethod
    def _session(key: str, payload: object) -> Session:
        data = payload if isinstance(payload, dict) else {}
        return Session(
            key=key,
            kind=data["kind"],  # type: ignore[arg-type]
            expires_at=datetime.fromisoformat(str(data["expires_at"])),
            csrf_token=str(data["csrf_token"]),
        )

    def create_session(self, kind: SessionKind) -> IssuedSession:
        now = self._clock()
        token = secrets.token_urlsafe(32)
        key = self._key(token)
        ttl = LOCAL_SESSION_TTL if kind == "local" else REMOTE_SESSION_TTL
        session = Session(
            key=key,
            kind=kind,
            expires_at=now + ttl,
            csrf_token=secrets.token_urlsafe(32),
        )
        with self._transaction() as payload:
            self._purge_expired(payload, now)
            payload["sessions"][key] = {
                "kind": session.kind,
                "expires_at": session.expires_at.isoformat(),
                "csrf_token": session.csrf_token,
            }
            self._write(payload)
        return IssuedSession(session=session, token=token)

    def resolve(self, token: str | None) -> Session | None:
        if not token:
            return None
        now = self._clock()
        candidate = self._key(token)
        with self._transaction() as payload:
            self._purge_expired(payload, now)
            match = next(
                (key for key in payload["sessions"] if secrets.compare_digest(candidate, key)),
                None,
            )
            self._write(payload)
            if match is None:
                return None
            return self._session(match, payload["sessions"][match])

    def refresh(self, session: Session) -> SessionInfo:
        now = self._clock()
        ttl = LOCAL_SESSION_TTL if session.kind == "local" else REMOTE_SESSION_TTL
        refreshed = Session(
            key=session.key,
            kind=session.kind,
            expires_at=now + ttl,
            csrf_token=session.csrf_token,
        )
        with self._transaction() as payload:
            self._purge_expired(payload, now)
            if session.key not in payload["sessions"]:
                raise KeyError("expired session")
            payload["sessions"][session.key] = {
                "kind": refreshed.kind,
                "expires_at": refreshed.expires_at.isoformat(),
                "csrf_token": refreshed.csrf_token,
            }
            self._write(payload)
        return SessionInfo(
            kind=refreshed.kind,
            expires_at=refreshed.expires_at,
            csrf_token=refreshed.csrf_token,
        )

    def create_bootstrap(self) -> str:
        now = self._clock()
        token = secrets.token_urlsafe(32)
        with self._transaction() as payload:
            self._purge_expired(payload, now)
            payload["bootstraps"][self._key(token)] = (now + BOOTSTRAP_TTL).isoformat()
            self._write(payload)
        return token

    def exchange_bootstrap(self, token: str) -> IssuedSession | None:
        now = self._clock()
        candidate = self._key(token)
        with self._transaction() as payload:
            self._purge_expired(payload, now)
            match = next(
                (key for key in payload["bootstraps"] if secrets.compare_digest(candidate, key)),
                None,
            )
            if match is None:
                self._write(payload)
                return None
            del payload["bootstraps"][match]
            self._write(payload)
        return self.create_session("local")


class CsrfGuard:
    """Validate double-submit headers against the server-side session secret."""

    @staticmethod
    def validate(session: Session, supplied_token: str | None) -> bool:
        return bool(supplied_token) and secrets.compare_digest(session.csrf_token, supplied_token)
