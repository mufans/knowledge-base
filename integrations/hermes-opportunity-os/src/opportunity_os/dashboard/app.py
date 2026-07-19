"""Authenticated FastAPI shell for the loopback Opportunity OS dashboard."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from opportunity_os.dashboard.auth import CsrfGuard, Session, SessionInfo, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.schemas import DashboardSnapshot


SESSION_COOKIE = "opportunity_dashboard_session"
ORIGIN_CREDENTIAL_HEADER = "x-dashboard-origin-credential"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class DashboardSnapshotReader(Protocol):
    def snapshot(self) -> DashboardSnapshot: ...


@dataclass(frozen=True, slots=True)
class DashboardDependencies:
    read_model: DashboardSnapshotReader
    sessions: SessionStore
    csrf: CsrfGuard


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
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    remote_host = config.remote_host.casefold() if config.remote_host else None

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
    def health() -> dict[str, bool]:
        return {"ok": True}

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

    @app.post("/api/v1/session/refresh", response_model=SessionInfo)
    def refresh_session(session: Session = Depends(require_csrf_session)) -> SessionInfo:
        return dependencies.sessions.refresh(session)

    return app
