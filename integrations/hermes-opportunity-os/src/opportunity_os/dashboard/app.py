"""Authenticated FastAPI shell for the loopback Opportunity OS dashboard."""

from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from opportunity_os.dashboard.auth import CsrfGuard, Session, SessionInfo, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.events import DashboardEvent, EventHub, EventJournalTailer
from opportunity_os.dashboard.schemas import DashboardSnapshot


SESSION_COOKIE = "opportunity_dashboard_session"
ORIGIN_CREDENTIAL_HEADER = "x-dashboard-origin-credential"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
SSE_HEARTBEAT_SECONDS = 20
_DASHBOARD_DIR = Path(__file__).resolve().parent

# Remote deployment contract: this process remains loopback-bound. Task 11's
# ngrok policy must strip any browser-supplied value and inject this credential
# on every upstream request. The app trusts it only from a loopback peer.


class DashboardSnapshotReader(Protocol):
    def snapshot(self) -> DashboardSnapshot: ...


@dataclass(frozen=True, slots=True)
class DashboardDependencies:
    read_model: DashboardSnapshotReader
    sessions: SessionStore
    csrf: CsrfGuard
    event_hub: EventHub | None = None
    event_journal_path: Path | None = None
    journal_poll_interval: float = 0.25
    event_tailer: EventJournalTailer | None = None


class BootstrapExchange(BaseModel):
    token: str


def _hostname(value: str) -> str | None:
    try:
        parsed = urlsplit(f"//{value}")
        parsed.port
    except ValueError:
        return None
    if (
        value != value.strip()
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    return parsed.hostname


def _is_same_origin(request: Request, origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
        origin_port = parsed.port
        request_host = request.url.hostname
        request_port = request.url.port
    except ValueError:
        return False
    if parsed.hostname != request_host or origin_port != request_port:
        return False
    if request_host in LOOPBACK_HOSTS:
        return parsed.scheme == "http"
    return parsed.scheme == "https"


def _is_loopback_peer(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ip_address(request.client.host).is_loopback
    except ValueError:
        return request.client.host == "localhost"


def _set_session_cookie(response: Response, token: str, session: Session) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=8 * 60 * 60 if session.kind == "local" else 12 * 60 * 60,
        httponly=True,
        secure=session.kind == "remote",
        samesite="strict",
        path="/",
    )
    response.headers["X-CSRF-Token"] = session.csrf_token


def create_app(config: DashboardConfig, dependencies: DashboardDependencies) -> FastAPI:
    """Create a fail-closed dashboard app with no framework documentation routes."""
    remote_host = config.remote_host.casefold() if config.remote_host else None
    event_hub = dependencies.event_hub or EventHub(config.dashboard_home / "event-cursor")
    event_tailer = dependencies.event_tailer or (
        EventJournalTailer(
            dependencies.event_journal_path,
            event_hub,
            poll_interval=dependencies.journal_poll_interval,
        )
        if dependencies.event_journal_path is not None
        else None
    )
    if event_tailer is not None and event_tailer.event_hub is not event_hub:
        raise ValueError("event tailer and SSE endpoint must share one event hub")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialized = event_tailer.initialize() if event_tailer is not None else False
        task = (
            asyncio.create_task(event_tailer.run(initialized=initialized))
            if event_tailer is not None
            else None
        )
        if task is not None:
            await asyncio.sleep(0)
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.event_hub = event_hub
    app.state.event_bridge = event_tailer
    app.mount("/static", StaticFiles(directory=_DASHBOARD_DIR / "static"), name="static")

    @app.middleware("http")
    async def authentication_boundary(request: Request, call_next):
        host = _hostname(request.headers.get("host", ""))
        if host is None or (host not in LOOPBACK_HOSTS and host.casefold() != remote_host):
            return Response(status_code=400)

        is_local = host in LOOPBACK_HOSTS
        if request.url.path in {"/healthz", "/auth/local/exchange"}:
            if not is_local or not _is_loopback_peer(request):
                return Response(status_code=403)

        if not is_local:
            if not _is_loopback_peer(request):
                return Response(status_code=403)
            supplied = request.headers.get(ORIGIN_CREDENTIAL_HEADER)
            if not supplied or not config.origin_credential or not secrets.compare_digest(
                supplied, config.origin_credential
            ):
                return Response(status_code=401)
            request.state.remote_origin_authenticated = True
        else:
            request.state.remote_origin_authenticated = False

        origin = request.headers.get("origin")
        if origin and not _is_same_origin(request, origin):
            return Response(status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path != "/auth/local/exchange":
            if not origin:
                return Response(status_code=403)

        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/auth/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def require_session(request: Request, response: Response) -> Session:
        session = dependencies.sessions.resolve(request.cookies.get(SESSION_COOKIE))
        if session is not None:
            return session
        if request.state.remote_origin_authenticated:
            issued = dependencies.sessions.create_session("remote")
            _set_session_cookie(response, issued.token, issued.session)
            return issued.session
        raise HTTPException(status_code=401, detail="authentication_required")

    def require_csrf_session(
        session: Session = Depends(require_session),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> Session:
        if not dependencies.csrf.validate(session, csrf_token):
            raise HTTPException(status_code=403, detail="csrf_required")
        return session

    @app.get("/healthz")
    def health() -> dict[str, bool | str]:
        bridge_state = event_tailer.health.state if event_tailer is not None else "disabled"
        return {"ok": bridge_state in {"ready", "disabled"}, "event_bridge": bridge_state}

    @app.get("/", response_class=FileResponse)
    def index(request: Request) -> FileResponse:
        response = FileResponse(_DASHBOARD_DIR / "templates" / "index.html", media_type="text/html")
        if request.state.remote_origin_authenticated:
            session = dependencies.sessions.resolve(request.cookies.get(SESSION_COOKIE))
            if session is None:
                issued = dependencies.sessions.create_session("remote")
                _set_session_cookie(response, issued.token, issued.session)
        return response

    @app.post("/auth/local/exchange", response_model=SessionInfo)
    def local_exchange(exchange: BootstrapExchange, response: Response) -> SessionInfo:
        issued = dependencies.sessions.exchange_bootstrap(exchange.token)
        if issued is None:
            raise HTTPException(status_code=401, detail="invalid_bootstrap")
        _set_session_cookie(response, issued.token, issued.session)
        return SessionInfo(
            kind=issued.session.kind,
            expires_at=issued.session.expires_at,
            csrf_token=issued.session.csrf_token,
        )

    @app.get("/api/v1/status", response_model=DashboardSnapshot)
    def status(_: Session = Depends(require_session)) -> DashboardSnapshot:
        return dependencies.read_model.snapshot()

    @app.get("/api/v1/events")
    def events(
        request: Request,
        _: Session = Depends(require_session),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        cursor = last_event_id or request.query_params.get("last_event_id")
        if cursor is not None and not cursor.isdigit():
            raise HTTPException(status_code=400, detail="invalid_event_cursor")
        if event_tailer is not None and event_tailer.health.state != "ready":
            raise HTTPException(status_code=503, detail="event_bridge_unavailable")

        async def stream():
            active_cursor = cursor
            while True:
                subscription = event_hub.subscribe(active_cursor)
                try:
                    while True:
                        if await request.is_disconnected():
                            return
                        health_snapshot = (
                            event_tailer.health.snapshot() if event_tailer is not None else None
                        )
                        if health_snapshot is not None and health_snapshot.state != "ready":
                            yield 'event: bridge.unavailable\ndata: {"status":"unavailable"}\n\n'
                            return
                        event_task = asyncio.create_task(anext(subscription))
                        health_task = (
                            asyncio.create_task(
                                event_tailer.health.wait_after(health_snapshot.revision)
                            )
                            if event_tailer is not None and health_snapshot is not None
                            else None
                        )
                        waiters = {event_task}
                        if health_task is not None:
                            waiters.add(health_task)
                        done, pending = await asyncio.wait(
                            waiters,
                            timeout=SSE_HEARTBEAT_SECONDS,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if not done:
                            for task in pending:
                                task.cancel()
                                with suppress(asyncio.CancelledError, StopAsyncIteration):
                                    await task
                            yield ": heartbeat\n\n"
                            break
                        if health_task is not None and health_task in done:
                            health_task.result()
                            event_task.cancel()
                            with suppress(asyncio.CancelledError, StopAsyncIteration):
                                await event_task
                            yield 'event: bridge.unavailable\ndata: {"status":"unavailable"}\n\n'
                            return
                        if health_task is not None:
                            health_task.cancel()
                            with suppress(asyncio.CancelledError):
                                await health_task
                        try:
                            event: DashboardEvent = event_task.result()
                        except StopAsyncIteration:
                            if event_tailer is not None and event_tailer.health.state != "ready":
                                yield 'event: bridge.unavailable\ndata: {"status":"unavailable"}\n\n'
                            return
                        active_cursor = event.id
                        data = json.dumps(
                            event.wire_payload(),
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                        yield f"id: {event.id}\nevent: {event.type}\ndata: {data}\n\n"
                finally:
                    await subscription.aclose()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/session/refresh", response_model=SessionInfo)
    def refresh_session(session: Session = Depends(require_csrf_session)) -> SessionInfo:
        return dependencies.sessions.refresh(session)

    return app
