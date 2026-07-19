"""Authenticated FastAPI shell for the loopback Opportunity OS dashboard."""

from __future__ import annotations

import asyncio
import hashlib
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
from pydantic import BaseModel, ConfigDict

from opportunity_os.dashboard.approvals import (
    ApprovalError,
    ApprovalService,
    ChangeRequest,
    ConflictError,
    ExpiredError,
    IsolationError,
    StateError,
    ValidationError,
)
from opportunity_os.dashboard.audit import AuditLog
from opportunity_os.dashboard.auth import CsrfGuard, Session, SessionInfo, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.conversations import (
    ConversationAccepted,
    ConversationBusyError,
    ConversationRequest,
    ConversationService,
    ConversationTask,
)
from opportunity_os.dashboard.events import DashboardEvent, EventHub, EventJournalTailer
from opportunity_os.dashboard.schemas import DashboardSnapshot
from opportunity_os.dashboard.tasks import (
    TaskAdapterError,
    TaskCommandStatus,
    TaskRunsStatus,
    TaskSummary,
    TaskMutationCoordinator,
)


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


class DashboardTaskAdapter(Protocol):
    def list(self) -> list[TaskSummary]: ...

    def status(self) -> TaskCommandStatus: ...

    def runs(self, job_id: str) -> TaskRunsStatus: ...

    def edit_enabled(self, job_id: str, enabled: bool) -> TaskCommandStatus: ...

    def edit_schedule(self, job_id: str, cron: str, tz: str) -> TaskCommandStatus: ...

    def run_now(self, job_id: str) -> TaskCommandStatus: ...


@dataclass(frozen=True, slots=True)
class DashboardDependencies:
    read_model: DashboardSnapshotReader
    sessions: SessionStore
    csrf: CsrfGuard
    event_hub: EventHub | None = None
    event_journal_path: Path | None = None
    journal_poll_interval: float = 0.25
    event_tailer: EventJournalTailer | None = None
    conversation_service: ConversationService | None = None
    task_adapter: DashboardTaskAdapter | None = None
    approvals: ApprovalService | None = None
    audit_log: AuditLog | None = None
    single_writer_attested: bool = False
    task_coordinator: TaskMutationCoordinator | None = None


class BootstrapExchange(BaseModel):
    token: str


class TaskPatchPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch: dict[str, object]
    base_revision: str


class RunNowPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: str


class ApprovalConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digest: str
    nonce: str


class EmptyMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeRequestResponse(BaseModel):
    """Browser DTO deliberately excludes owner and session bindings."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    target: str
    patch: dict[str, object]
    base_revision: str
    digest: str
    nonce: str | None
    state: str
    expires_at: str
    operation_id: str | None
    audit_pending: bool
    operation_phase: str | None
    terminal_reason: str | None
    manual_review: bool


def _change_response(change: ChangeRequest, *, include_nonce: bool) -> ChangeRequestResponse:
    return ChangeRequestResponse(
        id=change.id,
        kind=change.kind,
        target=change.target,
        patch=change.patch,
        base_revision=change.base_revision,
        digest=change.digest,
        nonce=change.nonce if include_nonce else None,
        state=change.state,
        expires_at=change.expires_at.isoformat(),
        operation_id=change.operation_id,
        audit_pending=change.audit_pending,
        operation_phase=change.operation_phase,
        terminal_reason=change.terminal_reason,
        manual_review=change.manual_review,
    )


def replay_audit_outbox(approvals: ApprovalService, audit: AuditLog) -> int:
    """Idempotently append durable terminal outcomes and clear pending markers."""
    replayed = 0
    for change in approvals.pending_audits():
        if change.operation_id is None or change.state not in {
            "applied",
            "failed",
            "expired",
            "conflict",
            "indeterminate",
        }:
            continue
        audit.append(
            actor=change.owner_id,
            request_id=change.id,
            target=change.target,
            status=change.state,
            diff=change.audit_diff,
            operation_id=change.operation_id,
            prepared=True,
        )
        approvals.mark_audited(change.operation_id)
        replayed += 1
    return replayed


def reconcile_incomplete_operations(
    approvals: ApprovalService,
    audit: AuditLog,
    coordinator: TaskMutationCoordinator,
) -> int:
    """Classify in-flight operations by read-only task state; never replay a mutation."""
    reconciled = 0
    for change in approvals.pending_operations():
        if change.operation_id is None:
            continue

        def classify(current: TaskSummary) -> ChangeRequest:
            pre_mutation = change.operation_phase in {"intent_pending", "intent_written"}
            if change.kind == "run_now":
                if pre_mutation:
                    return approvals.recover_operation(
                        change.operation_id,
                        outcome="failed",
                        reason="interrupted_before_mutation",
                        manual_review=False,
                    )
                return approvals.recover_operation(
                    change.operation_id,
                    outcome="indeterminate",
                    reason="run_now_may_have_executed",
                    manual_review=True,
                )
            target_matches = all(
                getattr(current, field) == expected
                for field, expected in change.patch.items()
            )
            if target_matches:
                return approvals.recover_operation(
                    change.operation_id,
                    outcome="applied",
                    reason="target_already_applied",
                    manual_review=False,
                )
            if pre_mutation and secrets.compare_digest(
                current.revision, change.base_revision
            ):
                return approvals.recover_operation(
                    change.operation_id,
                    outcome="failed",
                    reason="interrupted_before_mutation",
                    manual_review=False,
                )
            return approvals.recover_operation(
                change.operation_id,
                outcome="indeterminate",
                reason="state_conflict_after_mutation_started",
                manual_review=True,
            )

        try:
            coordinator.inspect(change.target, classify)
            reconciled += 1
        except (OSError, TaskAdapterError, ApprovalError):
            continue
    try:
        replay_audit_outbox(approvals, audit)
    except (OSError, ValueError, ApprovalError):
        pass
    return reconciled


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
    owner_seed = (
        config.origin_credential.encode("utf-8")
        if config.origin_credential
        else b"loopback-single-owner"
    )
    owner_scope = hashlib.sha256(
        b"opportunity-os/dashboard-owner/v1\0" + owner_seed
    ).hexdigest()
    event_hub = dependencies.event_hub or EventHub(config.dashboard_home / "event-cursor")
    task_coordinator = dependencies.task_coordinator or (
        TaskMutationCoordinator(
            dependencies.task_adapter, config.dashboard_home / "task-locks"
        )
        if dependencies.task_adapter is not None
        else None
    )
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
        if dependencies.approvals is not None and dependencies.audit_log is not None:
            try:
                if dependencies.single_writer_attested and task_coordinator is not None:
                    reconcile_incomplete_operations(
                        dependencies.approvals,
                        dependencies.audit_log,
                        task_coordinator,
                    )
                replay_audit_outbox(dependencies.approvals, dependencies.audit_log)
            except (OSError, ValueError, ApprovalError):
                pass
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
            response.headers["X-CSRF-Token"] = session.csrf_token
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

    def control_services() -> tuple[DashboardTaskAdapter, ApprovalService, AuditLog]:
        if (
            dependencies.task_adapter is None
            or dependencies.approvals is None
            or dependencies.audit_log is None
        ):
            raise HTTPException(status_code=503, detail="task_control_unavailable")
        return dependencies.task_adapter, dependencies.approvals, dependencies.audit_log

    def require_attested_writer() -> TaskMutationCoordinator:
        if not dependencies.single_writer_attested or task_coordinator is None:
            raise HTTPException(status_code=503, detail="single_writer_not_attested")
        return task_coordinator

    def require_drained_outbox(approvals: ApprovalService, audit: AuditLog) -> None:
        try:
            replay_audit_outbox(approvals, audit)
        except Exception as error:
            raise HTTPException(status_code=503, detail="audit_outbox_unavailable") from error

    def require_reconciled_operations(
        approvals: ApprovalService,
        audit: AuditLog,
        coordinator: TaskMutationCoordinator,
    ) -> None:
        reconcile_incomplete_operations(approvals, audit, coordinator)
        if approvals.pending_operations():
            raise HTTPException(status_code=503, detail="operation_recovery_pending")
        if approvals.manual_reviews():
            raise HTTPException(status_code=503, detail="operation_manual_review_required")
        require_drained_outbox(approvals, audit)

    def safe_control_error(error: Exception) -> HTTPException:
        if isinstance(error, (KeyError, IsolationError)):
            return HTTPException(status_code=404, detail="change_request_not_found")
        if isinstance(error, ExpiredError):
            return HTTPException(status_code=410, detail="approval_expired")
        if isinstance(error, (ConflictError, StateError)):
            return HTTPException(status_code=409, detail="approval_conflict")
        if isinstance(error, ValidationError | ValueError):
            return HTTPException(status_code=422, detail="invalid_task_change")
        if isinstance(error, TaskAdapterError):
            return HTTPException(status_code=503, detail="openclaw_task_unavailable")
        if isinstance(error, ApprovalError):
            return HTTPException(status_code=409, detail="approval_failed")
        return HTTPException(status_code=503, detail="task_control_failed")

    def current_task(adapter: DashboardTaskAdapter, job_id: str) -> TaskSummary:
        try:
            task = next((item for item in adapter.list() if item.job_id == job_id), None)
        except Exception as error:
            raise safe_control_error(error) from error
        if task is None:
            raise HTTPException(status_code=404, detail="task_not_found")
        return task

    def task_diff(task: TaskSummary, patch: dict[str, object]) -> dict[str, object]:
        before = {"enabled": task.enabled, "cron": task.cron, "tz": task.tz}
        return {
            field: {"before": before[field], "after": value}
            for field, value in patch.items()
        }

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

    @app.get("/api/v1/tasks", response_model=list[TaskSummary])
    def tasks(_: Session = Depends(require_session)) -> list[TaskSummary]:
        adapter, approvals, audit = control_services()
        if dependencies.single_writer_attested and task_coordinator is not None:
            try:
                reconcile_incomplete_operations(approvals, audit, task_coordinator)
            except Exception:
                pass
        try:
            return adapter.list()
        except Exception as error:
            raise safe_control_error(error) from error

    @app.get("/api/v1/tasks/status", response_model=TaskCommandStatus)
    def task_status(_: Session = Depends(require_session)) -> TaskCommandStatus:
        adapter, _, _ = control_services()
        try:
            return adapter.status()
        except Exception as error:
            raise safe_control_error(error) from error

    @app.get("/api/v1/tasks/{job_id}/runs", response_model=TaskRunsStatus)
    def task_runs(job_id: str, _: Session = Depends(require_session)) -> TaskRunsStatus:
        adapter, _, _ = control_services()
        try:
            return adapter.runs(job_id)
        except Exception as error:
            raise safe_control_error(error) from error

    @app.post(
        "/api/v1/tasks/{job_id}/changes/preview",
        response_model=ChangeRequestResponse,
    )
    def preview_task_change(
        job_id: str,
        preview: TaskPatchPreview,
        session: Session = Depends(require_csrf_session),
    ) -> ChangeRequestResponse:
        adapter, approvals, audit = control_services()
        task = current_task(adapter, job_id)
        if not secrets.compare_digest(task.revision, preview.base_revision):
            raise HTTPException(status_code=409, detail="task_revision_conflict")
        try:
            change = approvals.preview(
                job_id,
                preview.patch,
                base_revision=preview.base_revision,
                owner_id=owner_scope,
                session_id=session.key,
                audit_diff=audit.prepare_diff(task_diff(task, preview.patch)),
            )
            audit.append(
                actor=owner_scope,
                request_id=change.id,
                target=job_id,
                status="previewed",
                diff=task_diff(task, change.patch),
            )
            return _change_response(change, include_nonce=True)
        except Exception as error:
            raise safe_control_error(error) from error

    @app.post(
        "/api/v1/tasks/{job_id}/run-now/preview",
        response_model=ChangeRequestResponse,
    )
    def preview_run_now(
        job_id: str,
        preview: RunNowPreview,
        session: Session = Depends(require_csrf_session),
    ) -> ChangeRequestResponse:
        adapter, approvals, audit = control_services()
        task = current_task(adapter, job_id)
        if not secrets.compare_digest(task.revision, preview.base_revision):
            raise HTTPException(status_code=409, detail="task_revision_conflict")
        try:
            change = approvals.preview_run_now(
                job_id,
                base_revision=preview.base_revision,
                owner_id=owner_scope,
                session_id=session.key,
                audit_diff={},
            )
            audit.append(
                actor=owner_scope,
                request_id=change.id,
                target=job_id,
                status="previewed",
                diff={},
            )
            return _change_response(change, include_nonce=True)
        except Exception as error:
            raise safe_control_error(error) from error

    @app.post(
        "/api/v1/approvals/{request_id}/approve",
        response_model=ChangeRequestResponse,
    )
    def approve_change(
        request_id: str,
        confirmation: ApprovalConfirmation,
        session: Session = Depends(require_csrf_session),
    ) -> ChangeRequestResponse:
        adapter, approvals, audit = control_services()
        coordinator = require_attested_writer()
        require_reconciled_operations(approvals, audit, coordinator)
        try:
            existing = next(
                (
                    item
                    for item in approvals.list_for(
                        owner_id=owner_scope, session_id=session.key
                    )
                    if item.id == request_id
                ),
                None,
            )
            if existing is None:
                raise KeyError(request_id)
            if existing.state == "expired":
                try:
                    replay_audit_outbox(approvals, audit)
                finally:
                    raise ExpiredError("approval expired")
            change = approvals.approve(
                request_id,
                confirmation.digest,
                nonce=confirmation.nonce,
                owner_id=owner_scope,
                session_id=session.key,
            )
            audit.append(
                actor=owner_scope,
                request_id=change.id,
                target=change.target,
                status="approved",
                diff=change.audit_diff,
                prepared=True,
            )
            return _change_response(change, include_nonce=False)
        except Exception as error:
            raise safe_control_error(error) from error

    @app.post(
        "/api/v1/approvals/{request_id}/apply",
        response_model=ChangeRequestResponse,
    )
    def apply_change(
        request_id: str,
        _: EmptyMutation,
        session: Session = Depends(require_csrf_session),
    ) -> ChangeRequestResponse:
        adapter, approvals, audit = control_services()
        coordinator = require_attested_writer()
        try:
            reconcile_incomplete_operations(approvals, audit, coordinator)
            change = next(
                (
                    item
                    for item in approvals.list_for(
                        owner_id=owner_scope, session_id=session.key
                    )
                    if item.id == request_id
                ),
                None,
            )
            if change is None:
                raise KeyError(request_id)
            if change.state in {
                "applied",
                "failed",
                "expired",
                "conflict",
                "indeterminate",
            }:
                try:
                    replay_audit_outbox(approvals, audit)
                except Exception:
                    pass
                refreshed = next(
                    (
                        item
                        for item in approvals.list_for(
                            owner_id=owner_scope, session_id=session.key
                        )
                        if item.id == request_id
                    ),
                    change,
                )
                if refreshed.state == "expired":
                    raise ExpiredError("approval expired")
                if refreshed.state == "conflict":
                    raise ConflictError("task revision conflict")
                if refreshed.state == "failed":
                    raise StateError("task mutation previously failed")
                if refreshed.state == "indeterminate":
                    return _change_response(refreshed, include_nonce=False)
                return _change_response(refreshed, include_nonce=False)
            if change.state == "applying":
                raise HTTPException(status_code=503, detail="operation_recovery_pending")
            require_reconciled_operations(approvals, audit, coordinator)
            started: ChangeRequest | None = None

            def mutate() -> TaskCommandStatus:
                nonlocal started
                started = approvals.start_apply(
                    request_id,
                    observed_revision=change.base_revision,
                    owner_id=owner_scope,
                    session_id=session.key,
                )
                try:
                    audit.append(
                        actor=owner_scope,
                        request_id=started.id,
                        target=started.target,
                        status="applying",
                        diff=started.audit_diff,
                        operation_id=started.operation_id,
                        prepared=True,
                    )
                    approvals.mark_intent_written(started.operation_id)
                except Exception:
                    approvals.finish_apply(
                        request_id,
                        outcome="failed",
                        owner_id=owner_scope,
                        session_id=session.key,
                    )
                    raise
                if started.kind == "run_now":
                    approvals.mark_mutation_started(started.operation_id)
                    result = adapter.run_now(started.target)
                    if not result.ok:
                        raise TaskAdapterError("run_now_failed")
                    return result
                if frozenset(started.patch) == {"enabled"}:
                    approvals.mark_mutation_started(started.operation_id)
                    result = adapter.edit_enabled(
                        started.target, bool(started.patch["enabled"])
                    )
                else:
                    approvals.mark_mutation_started(started.operation_id)
                    result = adapter.edit_schedule(
                        started.target,
                        str(started.patch["cron"]),
                        str(started.patch["tz"]),
                    )
                if not result.ok:
                    raise TaskAdapterError("task_edit_failed")
                return result

            try:
                coordinator.mutate(
                    change.target,
                    expected_revision=change.base_revision,
                    mutation=mutate,
                    verify=lambda observed: all(
                        getattr(observed, field) == expected
                        for field, expected in change.patch.items()
                    ),
                )
            except Exception as mutation_error:
                if started is not None:
                    current = next(
                        (
                            item
                            for item in approvals.list_for(
                                owner_id=owner_scope, session_id=session.key
                            )
                            if item.id == request_id
                        ),
                        None,
                    )
                    if current is not None and current.state == "applying":
                        approvals.finish_apply(
                            request_id,
                            outcome="failed",
                            owner_id=owner_scope,
                            session_id=session.key,
                        )
                elif isinstance(mutation_error, TaskAdapterError) and str(
                    mutation_error
                ) == "revision_conflict":
                    approvals.record_terminal(
                        request_id,
                        outcome="conflict",
                        owner_id=owner_scope,
                        session_id=session.key,
                    )
                try:
                    replay_audit_outbox(approvals, audit)
                except Exception:
                    pass
                if isinstance(mutation_error, TaskAdapterError) and str(
                    mutation_error
                ) == "revision_conflict":
                    raise ConflictError("target revision changed after preview") from mutation_error
                raise
            applied = approvals.finish_apply(
                request_id,
                outcome="applied",
                owner_id=owner_scope,
                session_id=session.key,
            )
            try:
                replay_audit_outbox(approvals, audit)
            except Exception:
                pass
            applied = next(
                (
                    item
                    for item in approvals.list_for(
                        owner_id=owner_scope, session_id=session.key
                    )
                    if item.id == request_id
                ),
                applied,
            )
            return _change_response(applied, include_nonce=False)
        except Exception as error:
            raise safe_control_error(error) from error

    @app.get("/api/v1/events")
    def events(
        request: Request,
        session: Session = Depends(require_session),
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
                subscription = event_hub.subscribe(active_cursor, audience=session.key)
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

    @app.post(
        "/api/v1/conversations",
        response_model=ConversationAccepted,
        status_code=202,
    )
    def submit_conversation(
        conversation: ConversationRequest,
        session: Session = Depends(require_csrf_session),
    ) -> ConversationAccepted:
        if dependencies.conversation_service is None:
            raise HTTPException(status_code=503, detail="conversation_service_unavailable")
        try:
            task_id = dependencies.conversation_service.submit(
                conversation, owner_id=session.key
            )
        except ConversationBusyError as error:
            raise HTTPException(
                status_code=429, detail="conversation_capacity_reached"
            ) from error
        return ConversationAccepted(task_id=task_id)

    @app.get("/api/v1/conversations/{task_id}", response_model=ConversationTask)
    def conversation_task(
        task_id: str,
        session: Session = Depends(require_session),
    ) -> ConversationTask:
        if dependencies.conversation_service is None:
            raise HTTPException(status_code=503, detail="conversation_service_unavailable")
        try:
            return dependencies.conversation_service.get(task_id, owner_id=session.key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="conversation_task_not_found") from error

    return app
