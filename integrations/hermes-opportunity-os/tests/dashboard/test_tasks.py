from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opportunity_os.dashboard.app import (
    DashboardDependencies,
    create_app,
    reconcile_incomplete_operations,
    replay_audit_outbox,
)
from opportunity_os.dashboard.approvals import ApprovalService
from opportunity_os.dashboard.audit import AuditLog
from opportunity_os.dashboard.auth import CsrfGuard, SessionStore
from opportunity_os.dashboard.config import DashboardConfig
from opportunity_os.dashboard.probes import CommandResult, OPENCLAW_EXECUTABLE_PATH
from opportunity_os.dashboard.schemas import DashboardSnapshot
from opportunity_os.dashboard.tasks import (
    DEFAULT_OPENCLAW_EXECUTABLE,
    OpenClawTaskAdapter,
    TaskAdapterError,
    TaskMutationCoordinator,
    task_revision,
)


class FakeRunner:
    def __init__(self, result: CommandResult | None = None) -> None:
        self.result = result or CommandResult(0, "", "", False, 7)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, argv: tuple[str, ...], timeout: float) -> CommandResult:
        self.calls.append((argv, timeout))
        return self.result


def _job(**updates: object) -> dict[str, object]:
    job: dict[str, object] = {
        "id": "job-1",
        "name": "private delivery job",
        "enabled": True,
        "schedule": {"kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Shanghai"},
        "payload": {"message": "private body", "to": "private-recipient"},
        "updatedAtMs": 1_721_370_000_000,
    }
    job.update(updates)
    return job


def test_revision_covers_canonical_full_task_and_updated_at() -> None:
    first = _job()
    reordered = {key: first[key] for key in reversed(first)}
    changed_private_payload = _job(payload={"message": "different", "to": "private-recipient"})

    assert task_revision(first) == task_revision(reordered)
    assert task_revision(first) != task_revision(changed_private_payload)
    assert task_revision(first) != task_revision(_job(updatedAtMs=1_721_370_000_001))


def test_list_returns_only_safe_task_fields_and_unknown_cost_provider() -> None:
    runner = FakeRunner(CommandResult(0, json.dumps({"jobs": [_job()]}), "", False, 4))
    tasks = OpenClawTaskAdapter(runner).list()

    assert [task.model_dump(mode="json") for task in tasks] == [
        {
            "job_id": "job-1",
            "enabled": True,
            "cron": "0 8 * * *",
            "tz": "Asia/Shanghai",
            "updated_at_ms": 1_721_370_000_000,
            "revision": task_revision(_job()),
            "provider_status": "unknown",
            "cost_status": "unknown",
        }
    ]
    assert "private body" not in repr(tasks)
    assert "private-recipient" not in repr(tasks)


def test_adapter_uses_only_exact_fixed_commands_and_timeouts() -> None:
    runner = FakeRunner(CommandResult(0, json.dumps({"jobs": [_job()]}), "", False, 1))
    adapter = OpenClawTaskAdapter(runner)

    adapter.list()
    adapter.status()
    adapter.runs("job-1")
    adapter.edit_enabled("job-1", False)
    adapter.edit_enabled("job-1", True)
    adapter.edit_schedule("job-1", "0 9 * * 1", "Asia/Shanghai")
    adapter.run_now("job-1")

    assert runner.calls == [
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "list", "--all", "--json"), 10),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "status"), 10),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "runs", "--id", "job-1", "--limit", "50"), 10),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "edit", "job-1", "--disable"), 30),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "edit", "job-1", "--enable"), 30),
        (
            (
                DEFAULT_OPENCLAW_EXECUTABLE,
                "cron",
                "edit",
                "job-1",
                "--cron",
                "0 9 * * 1",
                "--tz",
                "Asia/Shanghai",
            ),
            30,
        ),
        ((DEFAULT_OPENCLAW_EXECUTABLE, "cron", "run", "job-1"), 30),
    ]
    flattened = [argument for call, _ in runner.calls for argument in call]
    for forbidden in ("--message", "--model", "--to", "rm", "--token"):
        assert forbidden not in flattened


@pytest.mark.parametrize(
    ("cron", "tz"),
    [
        ("private@example.com", "Asia/Shanghai"),
        ("0 8 * * *\rmessage", "Asia/Shanghai"),
        ("0 8 * * * *", "Asia/Shanghai"),
        ("0 8 * * *", "owner@example.com"),
        ("0 8 * * *", "../../etc/passwd"),
    ],
)
def test_adapter_rejects_free_text_schedule_values(cron: str, tz: str) -> None:
    runner = FakeRunner()
    with pytest.raises(ValueError):
        OpenClawTaskAdapter(runner).edit_schedule("job-1", cron, tz)
    assert runner.calls == []


def test_adapter_rejects_alternate_executable_and_cli_option_job_ids() -> None:
    runner = FakeRunner()
    with pytest.raises(ValueError, match="fixed executable"):
        OpenClawTaskAdapter(runner, openclaw_path="/tmp/openclaw")

    adapter = OpenClawTaskAdapter(runner)
    for candidate in ("--help", "job/../../private", "job with spaces", "a" * 129):
        with pytest.raises(ValueError, match="job_id"):
            adapter.run_now(candidate)


def test_task_output_is_bounded_before_json_decode() -> None:
    runner = FakeRunner(
        CommandResult(0, "{" + "x" * (OpenClawTaskAdapter.MAX_OUTPUT_BYTES + 1), "", False, 2)
    )

    with pytest.raises(TaskAdapterError, match="bounded"):
        OpenClawTaskAdapter(runner).list()


def test_nonzero_timeout_and_malformed_output_return_safe_errors() -> None:
    adapter = OpenClawTaskAdapter(FakeRunner(CommandResult(None, "private", "secret", True, 10_000)))
    result = adapter.status()
    assert result.error_code == "timeout"
    assert "private" not in repr(result)
    assert "secret" not in repr(result)
    assert result.provider_status == "unknown"
    assert result.cost_status == "unknown"

    with pytest.raises(TaskAdapterError, match="invalid_json"):
        OpenClawTaskAdapter(FakeRunner(CommandResult(0, "not-json", "", False, 1))).list()


def test_absolute_openclaw_task_command_uses_node22_path_and_shell_false(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        observed.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, '{"jobs":[]}', "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    from opportunity_os.dashboard.probes import CommandRunner

    OpenClawTaskAdapter(CommandRunner()).list()

    assert observed["shell"] is False
    assert observed["env"]["PATH"] == OPENCLAW_EXECUTABLE_PATH
    assert observed["argv"][0] == DEFAULT_OPENCLAW_EXECUTABLE


def test_default_task_runner_is_bounded_and_kills_a_timed_out_process_group(monkeypatch) -> None:
    from opportunity_os.dashboard.conversations import BoundedCommandRunner

    adapter = OpenClawTaskAdapter()
    assert isinstance(adapter._runner, BoundedCommandRunner)
    assert adapter._runner._max_output_bytes <= OpenClawTaskAdapter.MAX_OUTPUT_BYTES


class FakeReadModel:
    def snapshot(self) -> DashboardSnapshot:
        return DashboardSnapshot(
            generated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            components=[],
            opportunity_counts={"opportunities": 0, "experiments": 0, "reviews": 0, "tech_states": 0},
            portfolio_counts={"observe": 0, "validate": 0, "active": 0},
            portfolio_capacity={"observe": 5, "validate": 2, "active": 1},
            latest_review_at=None,
            overdue_tech_states=0,
            pending_approvals=0,
            active_incidents=0,
        )


class MutableTaskAdapter:
    def __init__(self) -> None:
        self.raw = _job()
        self.edits: list[tuple[object, ...]] = []

    def list(self):
        runner = FakeRunner(CommandResult(0, json.dumps({"jobs": [self.raw]}), "", False, 1))
        return OpenClawTaskAdapter(runner).list()

    def status(self):
        return OpenClawTaskAdapter(FakeRunner()).status()

    def runs(self, job_id: str):
        return OpenClawTaskAdapter(FakeRunner()).runs(job_id)

    def edit_enabled(self, job_id: str, enabled: bool):
        self.edits.append(("enabled", job_id, enabled))
        self.raw = {**self.raw, "enabled": enabled, "updatedAtMs": int(self.raw["updatedAtMs"]) + 1}
        return OpenClawTaskAdapter(FakeRunner()).status()

    def edit_schedule(self, job_id: str, cron: str, tz: str):
        self.edits.append(("schedule", job_id, cron, tz))
        self.raw = {
            **self.raw,
            "schedule": {"kind": "cron", "expr": cron, "tz": tz},
            "updatedAtMs": int(self.raw["updatedAtMs"]) + 1,
        }
        return OpenClawTaskAdapter(FakeRunner()).status()

    def run_now(self, job_id: str):
        self.edits.append(("run_now", job_id))
        return OpenClawTaskAdapter(FakeRunner()).status()


class FailingMutationAdapter(MutableTaskAdapter):
    def edit_enabled(self, job_id: str, enabled: bool):
        self.edits.append(("attempted_enabled", job_id, enabled))
        return OpenClawTaskAdapter(
            FakeRunner(CommandResult(2, "", "private failure", False, 1))
        ).status()


def test_task_lock_final_read_rejects_external_race_before_cli(tmp_path: Path) -> None:
    adapter = MutableTaskAdapter()
    expected = adapter.list()[0].revision
    adapter.raw = {**adapter.raw, "updatedAtMs": int(adapter.raw["updatedAtMs"]) + 1}
    coordinator = TaskMutationCoordinator(adapter, tmp_path / "locks")

    with pytest.raises(TaskAdapterError, match="revision_conflict"):
        coordinator.mutate(
            "job-1",
            expected_revision=expected,
            mutation=lambda: adapter.edit_enabled("job-1", False),
            verify=lambda task: task.enabled is False,
        )

    assert adapter.edits == []


def test_same_task_mutations_are_serialized_by_shared_flock(tmp_path: Path) -> None:
    adapter = MutableTaskAdapter()
    coordinator_a = TaskMutationCoordinator(adapter, tmp_path / "locks")
    coordinator_b = TaskMutationCoordinator(adapter, tmp_path / "locks")
    expected = adapter.list()[0].revision
    guard = threading.Lock()
    active = 0
    maximum = 0

    def mutation():
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with guard:
            active -= 1
        return OpenClawTaskAdapter(FakeRunner()).status()

    errors: list[Exception] = []

    def run(coordinator: TaskMutationCoordinator) -> None:
        try:
            coordinator.mutate(
                "job-1",
                expected_revision=expected,
                mutation=mutation,
                verify=lambda _: True,
            )
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=run, args=(item,)) for item in (coordinator_a, coordinator_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert maximum == 1


@pytest.fixture
def api(tmp_path: Path):
    config = DashboardConfig(
        dashboard_home=tmp_path / "dashboard",
        remote_host="assigned.ngrok-free.app",
        origin_credential="origin-secret-for-tests",
    )
    sessions = SessionStore(config.dashboard_home)
    adapter = MutableTaskAdapter()
    approvals = ApprovalService(config.dashboard_home / "approvals.json")
    audit = AuditLog(config.dashboard_home / "audit.jsonl")
    dependencies = DashboardDependencies(
        read_model=FakeReadModel(),
        sessions=sessions,
        csrf=CsrfGuard(),
        task_adapter=adapter,
        approvals=approvals,
        audit_log=audit,
        single_writer_attested=True,
    )
    app = create_app(config, dependencies)

    def authenticated_client() -> tuple[TestClient, str]:
        client = TestClient(
            app,
            base_url="http://127.0.0.1:8765",
            client=("127.0.0.1", 51000),
        )
        response = client.post(
            "/auth/local/exchange", json={"token": sessions.create_bootstrap()}
        )
        assert response.status_code == 200
        return client, response.json()["csrf_token"]

    return authenticated_client, adapter, audit


class FailingAuditLog(AuditLog):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.fail_statuses: set[str] = set()

    def append(self, **kwargs):
        if kwargs["status"] in self.fail_statuses:
            raise OSError("injected audit failure")
        return super().append(**kwargs)


def _control_api(
    tmp_path: Path,
    *,
    single_writer_attested: bool,
    audit: AuditLog | None = None,
    adapter: MutableTaskAdapter | None = None,
):
    config = DashboardConfig(
        dashboard_home=tmp_path / "dashboard",
        remote_host="assigned.ngrok-free.app",
        origin_credential="origin-secret-for-tests",
    )
    sessions = SessionStore(config.dashboard_home)
    adapter = adapter or MutableTaskAdapter()
    approvals = ApprovalService(config.dashboard_home / "approvals.json")
    audit = audit or AuditLog(config.dashboard_home / "audit.jsonl")
    dependencies = DashboardDependencies(
        read_model=FakeReadModel(),
        sessions=sessions,
        csrf=CsrfGuard(),
        task_adapter=adapter,
        approvals=approvals,
        audit_log=audit,
        single_writer_attested=single_writer_attested,
    )
    client = TestClient(
        create_app(config, dependencies),
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 51000),
    )
    response = client.post(
        "/auth/local/exchange", json={"token": sessions.create_bootstrap()}
    )
    assert response.status_code == 200
    return client, response.json()["csrf_token"], adapter, approvals, audit


def _mutation_headers(csrf: str) -> dict[str, str]:
    return {
        "origin": "http://127.0.0.1:8765",
        "x-csrf-token": csrf,
        "content-type": "application/json",
    }


def test_task_api_requires_csrf_then_applies_only_after_exact_approval(api) -> None:
    clients, adapter, audit = api
    client, csrf = clients()
    task = client.get("/api/v1/tasks").json()[0]
    endpoint = "/api/v1/tasks/job-1/changes/preview"
    body = {"patch": {"enabled": False}, "base_revision": task["revision"]}

    assert client.post(endpoint, json=body, headers={"origin": "http://127.0.0.1:8765"}).status_code == 403
    preview = client.post(endpoint, json=body, headers=_mutation_headers(csrf))
    assert preview.status_code == 200
    change = preview.json()
    assert adapter.edits == []

    approved = client.post(
        f'/api/v1/approvals/{change["id"]}/approve',
        json={"digest": change["digest"], "nonce": change["nonce"]},
        headers=_mutation_headers(csrf),
    )
    assert approved.status_code == 200
    assert adapter.edits == []

    applied = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )
    assert applied.status_code == 200
    assert applied.json()["state"] == "applied"
    assert adapter.edits == [("enabled", "job-1", False)]
    audit_text = audit.path.read_text(encoding="utf-8")
    assert "private body" not in audit_text
    assert "private-recipient" not in audit_text


def test_other_session_cannot_approve_change(api) -> None:
    clients, _, _ = api
    owner_client, owner_csrf = clients()
    other_client, other_csrf = clients()
    task = owner_client.get("/api/v1/tasks").json()[0]
    change = owner_client.post(
        "/api/v1/tasks/job-1/changes/preview",
        json={"patch": {"enabled": False}, "base_revision": task["revision"]},
        headers=_mutation_headers(owner_csrf),
    ).json()

    response = other_client.post(
        f'/api/v1/approvals/{change["id"]}/approve',
        json={"digest": change["digest"], "nonce": change["nonce"]},
        headers=_mutation_headers(other_csrf),
    )

    assert response.status_code == 404


def test_run_now_has_independent_empty_patch_approval_flow(api) -> None:
    clients, adapter, _ = api
    client, csrf = clients()
    task = client.get("/api/v1/tasks").json()[0]
    preview = client.post(
        "/api/v1/tasks/job-1/run-now/preview",
        json={"base_revision": task["revision"]},
        headers=_mutation_headers(csrf),
    )

    assert preview.status_code == 200
    assert preview.json()["kind"] == "run_now"
    assert preview.json()["patch"] == {}
    assert client.post(
        "/api/v1/tasks/job-1/run-now/preview",
        json={"base_revision": task["revision"], "patch": {"enabled": False}},
        headers=_mutation_headers(csrf),
    ).status_code == 422
    change = preview.json()
    assert client.post(
        f'/api/v1/approvals/{change["id"]}/approve',
        json={"digest": change["digest"], "nonce": change["nonce"]},
        headers=_mutation_headers(csrf),
    ).status_code == 200
    assert client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    ).status_code == 200
    assert adapter.edits == [("run_now", "job-1")]


def test_api_cas_rejects_target_change_after_approval(api) -> None:
    clients, adapter, audit = api
    client, csrf = clients()
    task = client.get("/api/v1/tasks").json()[0]
    change = client.post(
        "/api/v1/tasks/job-1/changes/preview",
        json={"patch": {"enabled": False}, "base_revision": task["revision"]},
        headers=_mutation_headers(csrf),
    ).json()
    assert client.post(
        f'/api/v1/approvals/{change["id"]}/approve',
        json={"digest": change["digest"], "nonce": change["nonce"]},
        headers=_mutation_headers(csrf),
    ).status_code == 200
    adapter.raw = {**adapter.raw, "updatedAtMs": int(adapter.raw["updatedAtMs"]) + 1}

    response = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )

    assert response.status_code == 409
    assert adapter.edits == []
    records = [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]
    assert records[1]["status"] == "approved"
    assert records[1]["diff"]["enabled"]["summary"] == "boolean_changed"
    assert "before" not in records[1]["diff"]["enabled"]
    assert records[-1]["status"] == "conflict"


def test_single_writer_policy_defaults_closed_without_consuming_approval(tmp_path: Path) -> None:
    client, csrf, adapter, approvals, _ = _control_api(
        tmp_path, single_writer_attested=False
    )
    task = client.get("/api/v1/tasks").json()[0]
    change = client.post(
        "/api/v1/tasks/job-1/changes/preview",
        json={"patch": {"enabled": False}, "base_revision": task["revision"]},
        headers=_mutation_headers(csrf),
    ).json()

    response = client.post(
        f'/api/v1/approvals/{change["id"]}/approve',
        json={"digest": change["digest"], "nonce": change["nonce"]},
        headers=_mutation_headers(csrf),
    )

    assert response.status_code == 503
    assert adapter.edits == []
    stored = approvals.list_for(
        owner_id=next(iter(json.loads(approvals.path.read_text())["requests"].values()))["owner_id"],
        session_id=next(iter(json.loads(approvals.path.read_text())["requests"].values()))["session_id"],
    )[0]
    assert stored.state == "awaiting_approval"
    assert stored.nonce == change["nonce"]


def _approved_change(client: TestClient, csrf: str) -> dict[str, object]:
    task = client.get("/api/v1/tasks").json()[0]
    change = client.post(
        "/api/v1/tasks/job-1/changes/preview",
        json={"patch": {"enabled": False}, "base_revision": task["revision"]},
        headers=_mutation_headers(csrf),
    ).json()
    assert client.post(
        f'/api/v1/approvals/{change["id"]}/approve',
        json={"digest": change["digest"], "nonce": change["nonce"]},
        headers=_mutation_headers(csrf),
    ).status_code == 200
    return change


def _stored_change(approvals: ApprovalService, request_id: str):
    payload = json.loads(approvals.path.read_text(encoding="utf-8"))["requests"][request_id]
    return payload


def test_write_ahead_intent_failure_performs_zero_cli_mutation(tmp_path: Path) -> None:
    audit = FailingAuditLog(tmp_path / "dashboard" / "audit.jsonl")
    client, csrf, adapter, approvals, _ = _control_api(
        tmp_path, single_writer_attested=True, audit=audit
    )
    change = _approved_change(client, csrf)
    audit.fail_statuses.add("applying")

    response = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )

    assert response.status_code == 503
    assert adapter.edits == []
    stored = _stored_change(approvals, str(change["id"]))
    assert stored["state"] == "failed"
    assert stored["audit_pending"] is False
    assert stored["operation_id"]
    records = [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["status"] == "failed"


def test_terminal_audit_failure_reports_applied_pending_and_never_repeats_mutation(
    tmp_path: Path,
) -> None:
    audit = FailingAuditLog(tmp_path / "dashboard" / "audit.jsonl")
    client, csrf, adapter, approvals, _ = _control_api(
        tmp_path, single_writer_attested=True, audit=audit
    )
    change = _approved_change(client, csrf)
    audit.fail_statuses.add("applied")

    first = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )
    second = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )

    assert first.status_code == 200
    assert first.json()["state"] == "applied"
    assert first.json()["audit_pending"] is True
    assert second.status_code == 200
    assert second.json()["operation_id"] == first.json()["operation_id"]
    assert adapter.edits == [("enabled", "job-1", False)]
    audit.fail_statuses.clear()
    assert replay_audit_outbox(approvals, audit) == 1
    assert _stored_change(approvals, str(change["id"]))["audit_pending"] is False
    records = [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]
    terminal = [item for item in records if item["status"] == "applied"]
    assert len(terminal) == 1
    assert terminal[0]["operation_id"] == first.json()["operation_id"]


def test_cli_mutation_exception_persists_failed_terminal_and_audit(tmp_path: Path) -> None:
    adapter = FailingMutationAdapter()
    client, csrf, _, approvals, audit = _control_api(
        tmp_path,
        single_writer_attested=True,
        adapter=adapter,
    )
    change = _approved_change(client, csrf)

    response = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )

    assert response.status_code == 503
    stored = _stored_change(approvals, str(change["id"]))
    assert stored["state"] == "failed"
    assert stored["audit_pending"] is False
    assert adapter.edits == [("attempted_enabled", "job-1", False)]
    records = [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]
    assert records[-2]["status"] == "applying"
    assert records[-1]["status"] == "failed"
    assert records[-1]["operation_id"] == records[-2]["operation_id"]


def _applying_change(
    approvals: ApprovalService,
    adapter: MutableTaskAdapter,
    *,
    run_now: bool = False,
):
    owner = "a" * 64
    session = "b" * 64
    base_revision = adapter.list()[0].revision
    request = (
        approvals.preview_run_now(
            "job-1",
            base_revision=base_revision,
            owner_id=owner,
            session_id=session,
        )
        if run_now
        else approvals.preview(
            "job-1",
            {"enabled": False},
            base_revision=base_revision,
            owner_id=owner,
            session_id=session,
        )
    )
    approvals.approve(
        request.id,
        request.digest,
        nonce=request.nonce,
        owner_id=owner,
        session_id=session,
    )
    applying = approvals.start_apply(
        request.id,
        observed_revision=base_revision,
        owner_id=owner,
        session_id=session,
    )
    return applying, owner, session


def _recovery_stack(tmp_path: Path):
    adapter = MutableTaskAdapter()
    approvals = ApprovalService(tmp_path / "approvals.json")
    audit = AuditLog(tmp_path / "audit.jsonl")
    coordinator = TaskMutationCoordinator(adapter, tmp_path / "locks")
    return adapter, approvals, audit, coordinator


def test_recovery_before_cli_marks_interrupted_without_mutation(tmp_path: Path) -> None:
    adapter, approvals, audit, coordinator = _recovery_stack(tmp_path)
    applying, _, _ = _applying_change(approvals, adapter)
    approvals.mark_intent_written(applying.operation_id)

    assert reconcile_incomplete_operations(approvals, audit, coordinator) == 1

    recovered = json.loads(approvals.path.read_text())["requests"][applying.id]
    assert recovered["state"] == "failed"
    assert recovered["terminal_reason"] == "interrupted_before_mutation"
    assert recovered["operation_phase"] == "terminal"
    assert adapter.edits == []


def test_recovery_after_edit_cli_matching_target_finalizes_applied(tmp_path: Path) -> None:
    adapter, approvals, audit, coordinator = _recovery_stack(tmp_path)
    applying, _, _ = _applying_change(approvals, adapter)
    approvals.mark_intent_written(applying.operation_id)
    approvals.mark_mutation_started(applying.operation_id)
    adapter.raw = {
        **adapter.raw,
        "enabled": False,
        "updatedAtMs": int(adapter.raw["updatedAtMs"]) + 1,
    }

    assert reconcile_incomplete_operations(approvals, audit, coordinator) == 1

    recovered = json.loads(approvals.path.read_text())["requests"][applying.id]
    assert recovered["state"] == "applied"
    assert recovered["terminal_reason"] == "target_already_applied"
    assert recovered["audit_pending"] is False
    assert adapter.edits == []


def test_recovery_started_edit_with_conflicting_state_requires_manual_review(
    tmp_path: Path,
) -> None:
    adapter, approvals, audit, coordinator = _recovery_stack(tmp_path)
    applying, _, _ = _applying_change(approvals, adapter)
    approvals.mark_intent_written(applying.operation_id)
    approvals.mark_mutation_started(applying.operation_id)
    adapter.raw = {
        **adapter.raw,
        "schedule": {"kind": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"},
        "updatedAtMs": int(adapter.raw["updatedAtMs"]) + 1,
    }

    reconcile_incomplete_operations(approvals, audit, coordinator)

    recovered = json.loads(approvals.path.read_text())["requests"][applying.id]
    assert recovered["state"] == "indeterminate"
    assert recovered["manual_review"] is True
    assert recovered["terminal_reason"] == "state_conflict_after_mutation_started"
    assert adapter.edits == []


def test_recovery_never_replays_started_run_now(tmp_path: Path) -> None:
    adapter, approvals, audit, coordinator = _recovery_stack(tmp_path)
    applying, _, _ = _applying_change(approvals, adapter, run_now=True)
    approvals.mark_intent_written(applying.operation_id)
    approvals.mark_mutation_started(applying.operation_id)

    reconcile_incomplete_operations(approvals, audit, coordinator)

    recovered = json.loads(approvals.path.read_text())["requests"][applying.id]
    assert recovered["state"] == "indeterminate"
    assert recovered["manual_review"] is True
    assert recovered["terminal_reason"] == "run_now_may_have_executed"
    assert adapter.edits == []


def test_recovery_terminal_audit_failure_replays_idempotently_later(tmp_path: Path) -> None:
    adapter = MutableTaskAdapter()
    approvals = ApprovalService(tmp_path / "approvals.json")
    audit = FailingAuditLog(tmp_path / "audit.jsonl")
    coordinator = TaskMutationCoordinator(adapter, tmp_path / "locks")
    applying, _, _ = _applying_change(approvals, adapter)
    approvals.mark_intent_written(applying.operation_id)
    approvals.mark_mutation_started(applying.operation_id)
    adapter.raw = {
        **adapter.raw,
        "enabled": False,
        "updatedAtMs": int(adapter.raw["updatedAtMs"]) + 1,
    }
    audit.fail_statuses.add("applied")

    assert reconcile_incomplete_operations(approvals, audit, coordinator) == 1
    stored = json.loads(approvals.path.read_text())["requests"][applying.id]
    assert stored["state"] == "applied"
    assert stored["audit_pending"] is True
    audit.fail_statuses.clear()

    assert reconcile_incomplete_operations(approvals, audit, coordinator) == 0
    assert reconcile_incomplete_operations(approvals, audit, coordinator) == 0
    stored = json.loads(approvals.path.read_text())["requests"][applying.id]
    assert stored["audit_pending"] is False
    records = [json.loads(line) for line in audit.path.read_text().splitlines()]
    assert len([record for record in records if record["status"] == "applied"]) == 1
    assert adapter.edits == []


def test_app_lifespan_reconciles_pre_cli_crash_on_restart(tmp_path: Path) -> None:
    config = DashboardConfig(
        dashboard_home=tmp_path / "dashboard",
        remote_host="assigned.ngrok-free.app",
        origin_credential="origin-secret-for-tests",
    )
    adapter = MutableTaskAdapter()
    approvals = ApprovalService(config.dashboard_home / "approvals.json")
    audit = AuditLog(config.dashboard_home / "audit.jsonl")
    applying, _, _ = _applying_change(approvals, adapter)
    approvals.mark_intent_written(applying.operation_id)
    dependencies = DashboardDependencies(
        read_model=FakeReadModel(),
        sessions=SessionStore(config.dashboard_home),
        csrf=CsrfGuard(),
        task_adapter=adapter,
        approvals=approvals,
        audit_log=audit,
        single_writer_attested=True,
    )

    with TestClient(create_app(config, dependencies)):
        pass

    recovered = json.loads(approvals.path.read_text())["requests"][applying.id]
    assert recovered["state"] == "failed"
    assert recovered["terminal_reason"] == "interrupted_before_mutation"
    assert adapter.edits == []


def test_task_list_lazily_reconciles_pre_cli_crash_without_blocking_read(
    tmp_path: Path,
) -> None:
    client, csrf, adapter, approvals, _ = _control_api(
        tmp_path, single_writer_attested=True
    )
    change = _approved_change(client, csrf)
    stored = _stored_change(approvals, str(change["id"]))
    applying = approvals.start_apply(
        str(change["id"]),
        observed_revision=str(change["base_revision"]),
        owner_id=stored["owner_id"],
        session_id=stored["session_id"],
    )
    approvals.mark_intent_written(applying.operation_id)

    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    recovered = _stored_change(approvals, str(change["id"]))
    assert recovered["state"] == "failed"
    assert recovered["terminal_reason"] == "interrupted_before_mutation"
    assert adapter.edits == []


def test_apply_api_exposes_started_run_now_as_manual_review_without_retry(
    tmp_path: Path,
) -> None:
    client, csrf, adapter, approvals, _ = _control_api(
        tmp_path, single_writer_attested=True
    )
    task = client.get("/api/v1/tasks").json()[0]
    change = client.post(
        "/api/v1/tasks/job-1/run-now/preview",
        json={"base_revision": task["revision"]},
        headers=_mutation_headers(csrf),
    ).json()
    assert client.post(
        f'/api/v1/approvals/{change["id"]}/approve',
        json={"digest": change["digest"], "nonce": change["nonce"]},
        headers=_mutation_headers(csrf),
    ).status_code == 200
    stored = _stored_change(approvals, str(change["id"]))
    applying = approvals.start_apply(
        str(change["id"]),
        observed_revision=task["revision"],
        owner_id=stored["owner_id"],
        session_id=stored["session_id"],
    )
    approvals.mark_intent_written(applying.operation_id)
    approvals.mark_mutation_started(applying.operation_id)

    first = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )
    second = client.post(
        f'/api/v1/approvals/{change["id"]}/apply',
        json={},
        headers=_mutation_headers(csrf),
    )

    assert first.status_code == 200
    assert first.json()["state"] == "indeterminate"
    assert first.json()["manual_review"] is True
    assert first.json()["terminal_reason"] == "run_now_may_have_executed"
    assert second.json()["operation_id"] == first.json()["operation_id"]
    assert adapter.edits == []


def test_frontend_uses_json_csrf_and_exact_patch_allowlist() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the task mutation contract test")
    app_js = Path(__file__).parents[2] / "src" / "opportunity_os" / "dashboard" / "static" / "app.js"
    runner = """
import fs from 'node:fs';
const source = fs.readFileSync(process.argv[1], 'utf8');
const module = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const calls = [];
const fetchImpl = async (url, options) => {
  calls.push({url, options});
  return {ok: true, status: 200, json: async () => ({id: 'chg-1'})};
};
await module.previewTaskChange('job-1', {enabled: false}, 'r1', 'csrf', fetchImpl);
await module.previewRunNow('job-1', 'r1', 'csrf', fetchImpl);
let forbidden = false;
try { await module.previewTaskChange('job-1', {message: 'blocked'}, 'r1', 'csrf', fetchImpl); }
catch (error) { forbidden = error.message === 'invalid_task_patch'; }
console.log(JSON.stringify({calls, forbidden}));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", runner, str(app_js)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["forbidden"] is True
    assert [call["url"] for call in payload["calls"]] == [
        "/api/v1/tasks/job-1/changes/preview",
        "/api/v1/tasks/job-1/run-now/preview",
    ]
    for call in payload["calls"]:
        assert call["options"]["method"] == "POST"
        assert call["options"]["credentials"] == "same-origin"
        assert call["options"]["headers"]["Content-Type"] == "application/json"
        assert call["options"]["headers"]["X-CSRF-Token"] == "csrf"
