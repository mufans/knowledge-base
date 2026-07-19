from datetime import datetime, timedelta, timezone
from pathlib import Path

from opportunity_os.dashboard.auth import CsrfGuard, SessionStore


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def test_bootstrap_token_is_one_time_and_creates_eight_hour_local_session(tmp_path: Path) -> None:
    clock = MutableClock()
    sessions = SessionStore(tmp_path / "dashboard", clock=clock)
    bootstrap = sessions.create_bootstrap()

    issued = sessions.exchange_bootstrap(bootstrap)

    assert issued is not None
    assert issued.session.kind == "local"
    assert issued.session.expires_at == clock.now + timedelta(hours=8)
    assert sessions.exchange_bootstrap(bootstrap) is None
    assert sessions.resolve(issued.token) == issued.session
    assert (tmp_path / "dashboard" / "auth.json").is_file()


def test_expired_bootstrap_token_is_rejected(tmp_path: Path) -> None:
    clock = MutableClock()
    sessions = SessionStore(tmp_path / "dashboard", clock=clock)
    bootstrap = sessions.create_bootstrap()
    clock.now += timedelta(seconds=61)

    assert sessions.exchange_bootstrap(bootstrap) is None


def test_remote_session_lasts_twelve_hours_and_csrf_uses_session_secret(tmp_path: Path) -> None:
    clock = MutableClock()
    sessions = SessionStore(tmp_path / "dashboard", clock=clock)
    issued = sessions.create_session("remote")
    guard = CsrfGuard()

    assert issued.session.expires_at == clock.now + timedelta(hours=12)
    assert guard.validate(issued.session, issued.session.csrf_token)
    assert not guard.validate(issued.session, "incorrect-token")


def test_expired_session_is_removed_from_server_side_store(tmp_path: Path) -> None:
    clock = MutableClock()
    sessions = SessionStore(tmp_path / "dashboard", clock=clock)
    issued = sessions.create_session("local")
    clock.now += timedelta(hours=8, seconds=1)

    assert sessions.resolve(issued.token) is None
