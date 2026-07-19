# Hermes × OpenClaw Personal Growth Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a secure real-time dashboard that controls OpenClaw and Hermes, automates opportunity reviews and knowledge-base output, sends reliable DingTalk incidents, and is accessible from any browser through ngrok GitHub OAuth.

**Architecture:** Extend the existing `opportunity_os` Python package with a loopback-only FastAPI broker, typed read/control adapters, SSE, approval and incident state machines, and a vanilla HTML/CSS/JavaScript UI. OpenClaw remains the only production scheduler and DingTalk egress; Hermes runs through fixed non-interactive wrappers and writes only private Opportunity OS state. ngrok provides the external OAuth boundary without exposing OpenClaw credentials or the local port.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic 2, Jinja2, vanilla JavaScript/CSS, pytest, httpx TestClient, JSON/JSONL, OpenClaw 2026.4.26 CLI with Homebrew Node 22, Hermes Agent 0.18.2, ngrok Agent with managed GitHub OAuth, macOS LaunchAgents.

## Global Constraints

- Use an isolated `codex/` Git worktree at execution time; preserve all pre-existing dirty files in the main workspace.
- Never modify `raw/**`; read `purpose.md` before generating Wiki output.
- Append `log.md` for every repository operation; new Wiki pages also update `wiki/syntheses/index.md`.
- Publish only through `/Users/liujun/.openclaw/workspace/scripts/sync_kb.sh`; never manually copy, push, or deploy MkDocs.
- Dashboard and ngrok upstream bind only to `127.0.0.1`/`::1`; OpenClaw Gateway stays loopback-only on port `18789`.
- Browser code never receives OpenClaw Gateway tokens, provider keys, ngrok Authtoken, DingTalk credentials, recipients, or raw task payloads.
- OpenClaw is the only production Cron and DingTalk egress; do not enable Hermes Cron or Hermes messaging.
- V1 task mutations are limited to `enabled`, Cron expression, timezone, and run-now; no delete, model, recipient, arbitrary payload, command, or arbitrary shell editing.
- Broad collection remains at least 80%; targeted additions remain at most 20%; every weekly output includes opposing evidence and a surprise signal.
- Keep Hermes `memory.write_approval=true`, `skills.write_approval=true`, `skills.guard_agent_created=true`, and `onboarding.profile_build="off"`.
- Explicitly set `memory.nudge_interval=0` and `skills.creation_nudge_interval=0` for unattended runs; never use `--yolo`.
- Do not auto-upgrade OpenClaw, Hermes, ngrok, Node, providers, or models.
- Any secret entry pauses execution and uses a visible user terminal or official browser; never accept the secret in chat or print it.
- Before each external configuration mutation, create a verified backup and record secret-free before/after hashes.

---

## File Structure

Repository-owned files:

```text
integrations/hermes-opportunity-os/
├── pyproject.toml
├── src/opportunity_os/
│   ├── cli.py
│   ├── sanitizer.py                 # content-level secret and public-export filtering
│   ├── store.py                     # privacy-safe summaries and existing private state
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── app.py                   # FastAPI factory and route composition
│   │   ├── approvals.py             # change-request state machine, digest, nonce, CAS
│   │   ├── audit.py                 # append-only secret-free audit records
│   │   ├── auth.py                  # ngrok/local bootstrap sessions, CSRF, Host/Origin
│   │   ├── config.py                # typed paths, ports, executable locations
│   │   ├── conversations.py         # OpenClaw/Hermes session orchestration
│   │   ├── events.py                # SSE broker and Last-Event-ID replay
│   │   ├── incidents.py             # failure/recovery/cooldown/restart state
│   │   ├── im.py                    # typed DingTalk/OpenClaw command routing
│   │   ├── probes.py                # read-only runtime probes
│   │   ├── read_model.py            # allowlisted aggregate dashboard DTO
│   │   ├── repositories.py          # side-effect-free private state readers
│   │   ├── schemas.py               # public API DTOs
│   │   ├── tasks.py                 # OpenClaw typed task adapter
│   │   ├── static/app.js
│   │   ├── static/styles.css
│   │   └── templates/index.html
│   └── automation/
│       ├── hermes_runner.py          # fixed cadence, lock, timeout, heartbeat
│       ├── kb_export.py              # private-to-Wiki sanitizer/exporter
│       └── monitor.py                # one-shot incident monitor for OpenClaw Cron
├── deployment/
│   ├── launchagents/
│   │   ├── com.liujun.opportunity-dashboard.plist
│   │   └── com.liujun.opportunity-ngrok.plist
│   ├── ngrok/traffic-policy.example.yml
│   ├── openclaw/install_jobs.py
│   ├── openclaw/skills/hermes-dashboard/SKILL.md
│   └── openclaw/sync_kb.sh
└── tests/
    ├── test_sanitizer.py
    ├── dashboard/
    │   ├── test_app.py
    │   ├── test_approvals.py
    │   ├── test_auth.py
    │   ├── test_conversations.py
    │   ├── test_events.py
    │   ├── test_incidents.py
    │   ├── test_im.py
    │   ├── test_probes.py
    │   ├── test_read_model.py
    │   ├── test_repositories.py
    │   └── test_tasks.py
    ├── automation/
    │   ├── test_hermes_runner.py
    │   ├── test_kb_export.py
    │   └── test_monitor.py
    └── deployment/
        ├── test_install_jobs.py
        ├── test_launchagents.py
        ├── test_openclaw_skill.py
        └── test_sync_kb.py
```

Private deployed state, never committed:

```text
~/.hermes/profiles/opportunity-discovery/opportunity-os/dashboard/
├── approvals.json
├── audit.jsonl
├── incidents.json
├── sessions.json
├── heartbeats/
└── locks/

~/.config/opportunity-dashboard/
├── dashboard.env             # mode 0600, non-provider runtime secrets only
├── ngrok.yml                 # mode 0600, Authtoken reference/config
└── traffic-policy.yml        # mode 0600, owner allowlist + origin credential
```

## Execution Preflight

- [ ] Use `superpowers:using-git-worktrees` to create a clean `codex/hermes-openclaw-dashboard` worktree.
- [ ] Record `git status --short`, `git rev-parse HEAD`, OpenClaw config/Cron hashes, Hermes template/profile hashes, and LaunchAgent state in a private preflight report.
- [ ] Run the existing 65-test baseline with `UV_CACHE_DIR=/private/tmp/hermes-dashboard-uv-cache uv run --directory integrations/hermes-opportunity-os --extra test pytest -q` and require PASS before edits.
- [ ] Run only read-only host probes: `openclaw gateway status`, `openclaw cron list --all --json`, `hermes -p opportunity-discovery config check`, and `opportunity-os doctor`; do not send messages or call a model.

### Task 1: Privacy-safe repositories and sanitizer

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/sanitizer.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/__init__.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/schemas.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/repositories.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/store.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/cli.py`
- Test: `integrations/hermes-opportunity-os/tests/test_sanitizer.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_repositories.py`
- Test: `integrations/hermes-opportunity-os/tests/test_store.py`

**Interfaces:**
- Produces: `contains_secret(value: object) -> bool`, `sanitize_public(value: object) -> object`, `PrivateStateReadRepository.snapshot() -> PrivateStateSnapshot`, and privacy-safe `PrivateStore.system_status() -> dict[str, object]`.
- `PrivateStateSnapshot` contains counts, capacity, latest review metadata, overdue TechState count, event cursor, and no direction titles or summaries.

- [ ] **Step 1: Write failing privacy tests**

```python
def test_public_status_never_returns_directions(store):
    status = store.system_status()
    assert status["portfolio"] == {
        "counts": {"observe": 0, "validate": 0, "active": 0},
        "capacity": {"observe": 5, "validate": 2, "active": 1},
    }
    assert "directions" not in repr(status)

def test_sanitizer_rejects_secret_inside_free_text():
    from opportunity_os.sanitizer import contains_secret
    assert contains_secret("Authorization: Bearer sk-private-value") is True

def test_repository_read_has_no_write_side_effect(tmp_path, initialized_store):
    before = {p: p.stat().st_mtime_ns for p in initialized_store.home.rglob("*") if p.is_file()}
    PrivateStateReadRepository(initialized_store.home).snapshot()
    after = {p: p.stat().st_mtime_ns for p in initialized_store.home.rglob("*") if p.is_file()}
    assert after == before
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
UV_CACHE_DIR=/private/tmp/hermes-dashboard-uv-cache uv run --directory integrations/hermes-opportunity-os --extra test pytest tests/test_sanitizer.py tests/dashboard/test_repositories.py tests/test_store.py -q
```

Expected: FAIL because `sanitizer` and `PrivateStateReadRepository` do not exist and current `system_status()` still returns directions.

- [ ] **Step 3: Implement content scanning and side-effect-free reads**

```python
SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
    re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[=:]\s*\S+"),
    re.compile(r"\b(?:sk|go)-[A-Za-z0-9_-]{12,}\b"),
)

def contains_secret(value: object) -> bool:
    if isinstance(value, dict):
        return any(str(key).casefold() in SENSITIVE_FIELDS or contains_secret(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item) for item in value)
    return isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS)
```

Implement `PrivateStateReadRepository` with direct read-only `Path.read_text()` calls and no `PrivateStore.initialize()`. Change the existing `system_status()` contract itself to return only counts and capacity, so the MCP and CLI cannot accidentally leak full directions; detailed portfolio access remains available only through the separately named `get_portfolio()` method.

- [ ] **Step 4: Run focused and full regression tests**

Expected: focused tests PASS, then all existing and new tests PASS.

- [ ] **Step 5: Commit the privacy foundation**

```bash
git add integrations/hermes-opportunity-os/src integrations/hermes-opportunity-os/tests
git commit -m "fix: add privacy-safe dashboard reads"
```

### Task 2: Typed runtime probes and dashboard read model

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/config.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/schemas.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/probes.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/read_model.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_probes.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_read_model.py`

**Interfaces:**
- Consumes: `PrivateStateReadRepository.snapshot()` from Task 1.
- Produces: `DashboardConfig.from_env()`, `CommandRunner.run(argv, timeout) -> CommandResult`, `RuntimeProbe.check() -> ComponentHealth`, and `DashboardReadModel.snapshot() -> DashboardSnapshot`.

- [ ] **Step 1: Write failing probe and aggregation tests**

```python
def test_timeout_is_unknown_not_down(fake_runner, dashboard_config):
    fake_runner.result = CommandResult(exit_code=None, stdout="", stderr="", timed_out=True, duration_ms=1000)
    result = HermesProbe(dashboard_config, fake_runner).check()
    assert result.status == "unknown"
    assert result.error_code == "probe_timeout"

def test_read_model_never_exposes_paths_or_directions(private_repo, fake_probes):
    payload = DashboardReadModel(private_repo, fake_probes).snapshot().model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "/Users/" not in rendered
    assert "directions" not in rendered
```

- [ ] **Step 2: Run tests and verify missing-type failures**

Run `pytest tests/dashboard/test_probes.py tests/dashboard/test_read_model.py -q`; expect import failures for the new modules.

- [ ] **Step 3: Implement exact health contracts**

```python
class ComponentHealth(BaseModel):
    component: Literal["openclaw", "hermes", "opportunity_os", "dashboard", "ngrok", "knowledge_publish"]
    status: Literal["healthy", "degraded", "down", "unknown"]
    checked_at: datetime
    last_success_at: datetime | None = None
    duration_ms: int
    error_code: str | None = None

class DashboardSnapshot(BaseModel):
    generated_at: datetime
    components: list[ComponentHealth]
    opportunity_counts: dict[str, int]
    portfolio_counts: dict[str, int]
    portfolio_capacity: dict[str, int]
    latest_review_at: datetime | None
    overdue_tech_states: int
    pending_approvals: int
    active_incidents: int
```

Use `asyncio.create_subprocess_exec(*argv)` or `subprocess.run(argv, shell=False)` only. Set the OpenClaw executable environment to `/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` and probe with `openclaw gateway status`; probe Hermes with `hermes -p opportunity-discovery config check`; never invoke a provider-backed command.

- [ ] **Step 4: Run probe/read-model tests and the full suite**

Expected: all tests PASS; timeout remains `unknown`; payload scan contains no absolute user path or private direction data.

- [ ] **Step 5: Commit runtime read models**

```bash
git add integrations/hermes-opportunity-os/src/opportunity_os/dashboard integrations/hermes-opportunity-os/tests/dashboard
git commit -m "feat: add dashboard runtime read model"
```

### Task 3: Loopback web service and authentication boundary

**Files:**
- Modify: `integrations/hermes-opportunity-os/pyproject.toml`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/auth.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/app.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/cli.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_auth.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_app.py`

**Interfaces:**
- Consumes: `DashboardReadModel.snapshot()` from Task 2.
- Produces: `create_app(config, dependencies) -> FastAPI`, `SessionStore`, `CsrfGuard`, and CLI commands `dashboard serve` and `dashboard open`.

- [ ] **Step 1: Add dependencies and failing security tests**

Add exact dependency ranges:

```toml
"fastapi>=0.116,<1",
"uvicorn>=0.35,<1",
"jinja2>=3.1,<4",
```

Add `httpx>=0.28,<1` to the test extra. Test rejected Host, Origin, missing origin credential, missing CSRF, GET mutation, expired bootstrap token, and successful loopback bootstrap exchange.

```python
def test_remote_request_requires_origin_credential(client):
    response = client.get("/api/v1/status", headers={"host": "assigned.ngrok-free.app"})
    assert response.status_code == 401

def test_mutation_requires_csrf(authenticated_client):
    response = authenticated_client.post("/api/v1/session/refresh", json={})
    assert response.status_code == 403
```

- [ ] **Step 2: Lock dependencies and verify tests fail**

Run `uv lock --directory integrations/hermes-opportunity-os`, then focused pytest. Expected: route/auth imports fail.

- [ ] **Step 3: Implement session, bootstrap, Host/Origin, and CSRF guards**

Use 32-byte `secrets.token_urlsafe()` values, server-side session storage beneath the private Dashboard home, constant-time credential comparison, 12-hour remote sessions, 8-hour local sessions, 60-second one-time bootstrap tokens, and HttpOnly `SameSite=Strict` cookies. Define only these unauthenticated routes: `/healthz` and `/auth/local/exchange` from loopback.

```python
@router.get("/api/v1/status", response_model=DashboardSnapshot)
def status(_: Session = Depends(require_session)) -> DashboardSnapshot:
    return dependencies.read_model.snapshot()

@router.post("/api/v1/session/refresh", response_model=SessionInfo)
def refresh_session(session: Session = Depends(require_csrf_session)) -> SessionInfo:
    return dependencies.sessions.refresh(session)
```

- [ ] **Step 4: Verify auth tests and bind behavior**

Run focused tests, then start with `opportunity-os dashboard serve --host 127.0.0.1 --port 8765` against fixture state and verify `lsof` shows no non-loopback listener.

- [ ] **Step 5: Commit the secure web shell**

```bash
git add integrations/hermes-opportunity-os/pyproject.toml integrations/hermes-opportunity-os/uv.lock integrations/hermes-opportunity-os/src integrations/hermes-opportunity-os/tests
git commit -m "feat: add authenticated loopback dashboard service"
```

### Task 4: SSE event hub and eight-page dashboard UI

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/events.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/templates/index.html`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/static/app.js`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/static/styles.css`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/app.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_events.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_app.py`

**Interfaces:**
- Produces: `EventHub.publish(event)`, `EventHub.replay(last_event_id)`, `EventHub.subscribe(last_event_id)`, `/api/v1/events` SSE, and browser modules `renderOverview`, `renderSignals`, `renderOpportunities`, `renderTasks`, `renderApprovals`, `renderReports`, `renderMonitoring`, `renderConversations`.

- [ ] **Step 1: Write failing replay, redaction, and UI smoke tests**

```python
def test_sse_replays_after_last_event_id(event_hub):
    first = event_hub.publish("component.updated", {"component": "hermes"})
    second = event_hub.publish("incident.firing", {"incident_id": "inc-1"})
    assert [event.id for event in event_hub.replay(first.id)] == [second.id]

def test_sse_rejects_private_body(event_hub):
    with pytest.raises(ValueError, match="event payload"):
        event_hub.publish("review.updated", {"summary": "private free text"})
```

- [ ] **Step 2: Run tests and verify failure**

Expected: missing `EventHub` and UI route assertions fail.

- [ ] **Step 3: Implement bounded SSE and accessible vanilla UI**

Keep at most 1,000 metadata-only events in memory and persist the cursor only. Send a 20-second heartbeat comment, honor `Last-Event-ID`, reconnect with exponential backoff, and refetch the relevant DTO after each event. Build responsive desktop/mobile navigation for the eight approved pages; do not embed private data in initial HTML.

```javascript
const routes = ["overview", "conversations", "signals", "opportunities", "tasks", "approvals", "reports", "monitoring"];
const source = new EventSource("/api/v1/events");
source.addEventListener("component.updated", () => refreshOverview());
source.addEventListener("incident.firing", () => Promise.all([refreshOverview(), refreshMonitoring()]));
```

- [ ] **Step 4: Run UI/API tests and manually inspect local rendering**

Expected: SSE replay/redaction tests PASS; all eight navigation targets render empty, healthy, degraded, and disconnected fixture states without console errors.

- [ ] **Step 5: Commit UI and real-time events**

```bash
git add integrations/hermes-opportunity-os/src/opportunity_os/dashboard integrations/hermes-opportunity-os/tests/dashboard
git commit -m "feat: add real-time dashboard interface"
```

### Task 5: OpenClaw and Hermes conversation adapters

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/conversations.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/app.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/static/app.js`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_conversations.py`

**Interfaces:**
- Produces: `OpenClawConversationAdapter.send(session_id, message) -> ConversationResult`, `HermesConversationAdapter.send(session_id, message) -> ConversationResult`, and `ConversationService.submit(request) -> task_id`.
- `ConversationResult` contains `session_id`, final text, provider/model when reported, token/cost status, exit code, duration, and no raw stderr.

- [ ] **Step 1: Write failing fixed-command and timeout tests**

```python
def test_openclaw_adapter_uses_fixed_gateway_agent_command(fake_runner):
    adapter = OpenClawConversationAdapter(fake_runner, openclaw_path="/opt/homebrew/bin/openclaw")
    adapter.send("dashboard-main", "Hermes 状态")
    assert fake_runner.argv == [
        "/opt/homebrew/bin/openclaw", "agent", "--session-id", "dashboard-main",
        "--message", "Hermes 状态", "--timeout", "600", "--json",
    ]

def test_hermes_adapter_never_uses_yolo(fake_runner):
    HermesConversationAdapter(fake_runner).send("research", "分析端侧 Agent")
    assert "--yolo" not in fake_runner.argv
    assert fake_runner.argv[:6] == ["hermes", "-p", "opportunity-discovery", "chat", "-Q", "-q"]
```

- [ ] **Step 2: Run focused tests and verify missing adapter failures**

- [ ] **Step 3: Implement bounded subprocess adapters**

Use `shell=False`, maximum message size 8 KiB, normalized session IDs, 600-second OpenClaw timeout, 1,500-second Hermes daily timeout, no `--deliver`, and `--source tool --skills opportunity-discovery` for Hermes. Stream task lifecycle events; only final sanitized text reaches the browser. Store session metadata, not hidden reasoning or credentials.

- [ ] **Step 4: Verify fake adapters, then run one explicit no-delivery OpenClaw query and one Hermes fixture query**

Expected: both return JSON/final text without DingTalk delivery or private-state mutation; real provider call occurs only after confirming the configured model and expected cost status.

- [ ] **Step 5: Commit conversation routing**

```bash
git add integrations/hermes-opportunity-os/src/opportunity_os/dashboard integrations/hermes-opportunity-os/tests/dashboard
git commit -m "feat: route OpenClaw and Hermes dashboard conversations"
```

### Task 6: Approval, audit, and OpenClaw task controller

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/approvals.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/audit.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/tasks.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/app.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/static/app.js`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_approvals.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_tasks.py`

**Interfaces:**
- Produces: `ChangeRequest`, `ApprovalService.preview/approve/apply`, `AuditLog.append`, and `OpenClawTaskAdapter.list/status/runs/edit_enabled/edit_schedule/run_now`.
- Allowed patch keys are exactly `enabled`, `cron`, and `tz`; run-now has no mutable patch.

- [ ] **Step 1: Write failing state-machine, CAS, and allowlist tests**

```python
def test_payload_change_invalidates_approval(service):
    request = service.preview("job-1", {"enabled": False}, base_revision="r1")
    approved = service.approve(request.id, request.digest, nonce=request.nonce)
    with pytest.raises(ConflictError):
        service.apply(approved.id, observed_revision="r2")

@pytest.mark.parametrize("field", ["message", "model", "to", "command", "delete"])
def test_forbidden_task_fields_are_rejected(service, field):
    with pytest.raises(ValidationError):
        service.preview("job-1", {field: "blocked"}, base_revision="r1")
```

- [ ] **Step 2: Run focused tests and verify failure**

- [ ] **Step 3: Implement deterministic OpenClaw CLI commands**

Use only:

```text
openclaw cron list --all --json
openclaw cron status
openclaw cron runs --id JOB_ID --limit 50
openclaw cron edit JOB_ID --enable|--disable
openclaw cron edit JOB_ID --cron EXPR --tz Asia/Shanghai
openclaw cron run JOB_ID
```

Never pass `--message`, `--model`, `--to`, `rm`, `--token`, or a shell string. Derive `base_revision` from canonical task JSON and `updatedAtMs`; persist field-level audit Diff without payload, recipient, or token.

- [ ] **Step 4: Run approval/task tests plus a read-only real `cron list/status/runs` contract test**

Expected: tests PASS; no production mutation occurs in this step.

- [ ] **Step 5: Commit controlled task mutation**

```bash
git add integrations/hermes-opportunity-os/src/opportunity_os/dashboard integrations/hermes-opportunity-os/tests/dashboard
git commit -m "feat: add approved OpenClaw task controls"
```

### Task 7: Hermes cadence runner, self-improvement controls, and KB exporter

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/automation/__init__.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/automation/hermes_runner.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/automation/kb_export.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/cli.py`
- Modify: `integrations/hermes-opportunity-os/profile/config.yaml`
- Modify: `integrations/hermes-opportunity-os/skills/opportunity-discovery/references/operating-rhythm.md`
- Test: `integrations/hermes-opportunity-os/tests/automation/test_hermes_runner.py`
- Test: `integrations/hermes-opportunity-os/tests/automation/test_kb_export.py`

**Interfaces:**
- Produces: `CadenceRunner.run(cadence, period_key) -> RunRecord`, CLI `automation run`, and `KnowledgeExporter.render/export`.
- Allowed cadence values: `daily`, `weekly`, `biweekly`, `six-week`, `quarterly`.

- [ ] **Step 1: Write failing lock, idempotency, timeout, profile, and export tests**

```python
def test_duplicate_period_is_skipped(runner):
    first = runner.run("weekly", "2026-W29")
    second = runner.run("weekly", "2026-W29")
    assert first.status == "success"
    assert second.status == "skipped_duplicate"

def test_runner_uses_quiet_non_yolo_hermes(fake_runner, runner):
    runner.run("daily", "2026-07-19")
    assert fake_runner.argv[:6] == ["hermes", "-p", "opportunity-discovery", "chat", "-Q", "-q"]
    assert "--yolo" not in fake_runner.argv

def test_public_export_contains_no_private_path_or_secret(exporter, review_fixture):
    rendered = exporter.render(review_fixture)
    assert "/Users/" not in rendered
    assert "Authorization:" not in rendered
```

- [ ] **Step 2: Run focused tests and verify failure**

- [ ] **Step 3: Implement atomic locks, heartbeats, prompts, and safe Profile defaults**

Set in the template:

```yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
  write_approval: true
  nudge_interval: 0
skills:
  guard_agent_created: true
  write_approval: true
  creation_nudge_interval: 0
```

Use `mkdir`-style atomic lock ownership, JSON heartbeat atomic replace, daily timeout 1,500 seconds, weekly timeout 3,000 seconds, and idempotency key `cadence:period_key`. Prompts require broad intake, opposing evidence, surprise, no external action, and improvement proposals instead of Memory/Skill mutation.

- [ ] **Step 4: Implement AGENTS-compliant KB export and run tests**

Exporter writes only `wiki/syntheses/` plus its index and append-only root log, validates the required self-evaluation score, and never touches `raw/` or `docs/`. Test with a temporary knowledge fixture and require no raw mtime changes.

The exporter owns these exact public-safe pages: `个人机会发现仪表盘.md`, `个人机会发现周报-YYYY-MM-DD.md`, `技术新鲜度观察.md`, and `方向实验复盘-YYYY-Www.md`. It also writes private bridge files `openclaw-handoff.json`, `source-feedback.json`, and `experiment-evidence-request.json` with a 14-day TTL. Bridge feedback may add targeted searches up to 20% but cannot remove broad sources.

- [ ] **Step 5: Commit cadence and exporter**

```bash
git add integrations/hermes-opportunity-os/src integrations/hermes-opportunity-os/profile integrations/hermes-opportunity-os/skills integrations/hermes-opportunity-os/tests
git commit -m "feat: automate Hermes reviews and safe KB exports"
```

### Task 8: Incident sentinel, DingTalk delivery state, and recovery notices

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/incidents.py`
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/automation/monitor.py`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/cli.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_incidents.py`
- Test: `integrations/hermes-opportunity-os/tests/automation/test_monitor.py`

**Interfaces:**
- Produces: `IncidentSentinel.observe(key, ok, severity, error_class) -> IncidentTransition`, `RestartBudget.allow(component, now)`, CLI `monitor once`, and a secret-free alert summary.

- [ ] **Step 1: Write failing incident transition tests**

```python
def test_incident_fires_once_and_recovers_once(sentinel):
    assert sentinel.observe("hermes:daily:timeout", False, "P1", "timeout").kind == "pending"
    assert sentinel.observe("hermes:daily:timeout", False, "P1", "timeout").kind == "firing"
    assert sentinel.observe("hermes:daily:timeout", False, "P1", "timeout").kind == "suppressed"
    assert sentinel.observe("hermes:daily:timeout", True, "P1", "timeout").kind == "recovering"
    assert sentinel.observe("hermes:daily:timeout", True, "P1", "timeout").kind == "recovered"

def test_restart_budget_limits_hour_and_day(budget):
    assert budget.allow("openclaw", at("2026-07-19T10:00:00Z")) is True
    assert budget.allow("openclaw", at("2026-07-19T10:30:00Z")) is False
    assert budget.allow("openclaw", at("2026-07-19T12:00:00Z")) is True
    assert budget.allow("openclaw", at("2026-07-19T14:00:00Z")) is False
```

- [ ] **Step 2: Run tests and verify failure**

- [ ] **Step 3: Implement persistent incidents and delivery receipts**

Use key `source:task:error_class`, P0 immediate firing, P1 after two failures, P2 after three, 6-hour cooldown, two-success recovery, one restart/hour, two/day. Alert text contains error code, impact, last success, run-id, dashboard URL, and suggested action; never include raw stderr or paths.

- [ ] **Step 4: Test fake DingTalk outcomes and recovery queueing**

The monitor must distinguish `generated`, `queued`, `delivered`, and `failed`; a successful Cron run without delivery receipt cannot display “pushed”. Add a boot hook mode that emits a single “曾中断并已恢复” after LaunchAgent recovery.

- [ ] **Step 5: Commit monitoring state machines**

```bash
git add integrations/hermes-opportunity-os/src integrations/hermes-opportunity-os/tests
git commit -m "feat: add incident alerts and recovery tracking"
```

### Task 9: OpenClaw DingTalk Skill and typed IM command router

**Required sub-skill:** `superpowers:writing-skills` before creating or editing the OpenClaw Skill.

**Files:**
- Create: `integrations/hermes-opportunity-os/src/opportunity_os/dashboard/im.py`
- Create: `integrations/hermes-opportunity-os/deployment/openclaw/skills/hermes-dashboard/SKILL.md`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/cli.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_im.py`
- Test: `integrations/hermes-opportunity-os/tests/deployment/test_openclaw_skill.py`

**Interfaces:**
- Produces: `ImCommandRouter.parse(text) -> ImCommand`, `ImCommandRouter.execute(command, sender_id, session_id) -> ImReply`, and CLI `dashboard im-command`.
- Read commands: `status`, `latest_review`, `directions`, `opportunity_detail`, `learning_summary`, `pending_memory`, `pending_skills`.
- Write proposals: `feedback`, `change_requirement`, `restart`, and `retry_task`; none applies without a second-phase nonce.

- [ ] **Step 1: Write failing parser, owner, and confirmation tests**

```python
@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Hermes 状态", "status"),
        ("Hermes 最新周报", "latest_review"),
        ("Hermes 当前方向", "directions"),
        ("Hermes 机会详情 opp-1", "opportunity_detail"),
        ("Hermes 最近学到了什么", "learning_summary"),
        ("Hermes 待审批记忆", "pending_memory"),
        ("Hermes 待审批Skill", "pending_skills"),
        ("Hermes 反馈：增加端侧 Agent 反证", "feedback"),
        ("Hermes 修改需求：周报增加失败假设", "change_requirement"),
    ],
)
def test_im_commands_are_typed(router, text, kind):
    assert router.parse(text).kind == kind

def test_non_owner_is_rejected(router):
    with pytest.raises(AuthorizationError):
        router.execute(router.parse("Hermes 状态"), sender_id="not-owner", session_id="dm-1")

def test_write_command_returns_nonce_without_applying(router):
    reply = router.execute(router.parse("Hermes 修改需求：调整周报"), sender_id="owner", session_id="dm-1")
    assert reply.status == "awaiting_confirmation"
    assert reply.expires_in_seconds == 300
    assert router.applied_changes == []
```

- [ ] **Step 2: Run parser/Skill tests and verify failure**

Run `pytest tests/dashboard/test_im.py tests/deployment/test_openclaw_skill.py -q`; expect missing router and Skill failures.

- [ ] **Step 3: Implement fail-closed typed routing**

Normalize only the documented Chinese prefixes, cap input at 4 KiB, require the configured owner sender ID, and return structured text plus a Dashboard link. Read commands call existing read services. Feedback and requirement commands create Task 6 Change Requests; restart/retry require the same sender/session to return an exact 5-minute nonce. Unknown text falls back to normal OpenClaw chat and performs no system mutation.

- [ ] **Step 4: Write and verify the OpenClaw Skill**

The Skill triggers only on `Hermes`-prefixed commands, invokes the exact `opportunity-os dashboard im-command` CLI, never reads `.env` or OpenClaw config, never constructs shell fragments from user text, quotes read-only results, and uses the two-phase reply verbatim. Run the writing-skills validation and hostile prompt tests.

- [ ] **Step 5: Commit IM routing**

```bash
git add integrations/hermes-opportunity-os/src/opportunity_os/dashboard/im.py integrations/hermes-opportunity-os/src/opportunity_os/cli.py integrations/hermes-opportunity-os/deployment/openclaw/skills integrations/hermes-opportunity-os/tests
git commit -m "feat: add owner-only Hermes DingTalk controls"
```

### Task 10: Reliable knowledge sync and OpenClaw job installer

**Files:**
- Create: `integrations/hermes-opportunity-os/deployment/openclaw/sync_kb.sh`
- Create: `integrations/hermes-opportunity-os/deployment/openclaw/install_jobs.py`
- Test: `integrations/hermes-opportunity-os/tests/deployment/test_sync_kb.py`
- Test: `integrations/hermes-opportunity-os/tests/deployment/test_install_jobs.py`

**Interfaces:**
- Produces: strict `sync_kb.sh` with stage JSON result and `build_job_plan(existing_jobs) -> JobPlan`.
- Job plan owns exact names `Hermes Opportunity Daily`, `Hermes Opportunity Weekly`, `Opportunity Monitor`, and only schedule corrections explicitly listed in the design.

- [ ] **Step 1: Write failing shell-fault and schedule-plan tests**

```python
@pytest.mark.parametrize("failed_stage", ["build", "push", "deploy"])
def test_sync_failure_never_reports_success(sync_harness, failed_stage):
    result = sync_harness.run(fail=failed_stage)
    assert result.returncode != 0
    assert result.json["status"] == "failed"
    assert result.json["stage"] == failed_stage
    assert "success" not in result.stdout.casefold()

def test_job_plan_has_one_kb_sync_and_no_sunday_collision(existing_jobs):
    plan = build_job_plan(existing_jobs)
    assert plan.enabled_count("knowledge-base-sync") == 1
    assert plan.schedule("Hermes Opportunity Daily") == ("30 18 * * 1-6", "Asia/Shanghai")
    assert plan.schedule("Hermes Opportunity Weekly") == ("0 19 * * 0", "Asia/Shanghai")

def test_push_policy_is_delta_daily_and_guaranteed_weekly(existing_jobs):
    plan = build_job_plan(existing_jobs)
    assert plan.push_policy("Hermes Opportunity Daily") == "significant_delta_only"
    assert plan.push_policy("Hermes Opportunity Weekly") == "always_after_successful_publish"
```

- [ ] **Step 2: Run deployment tests and verify failure**

- [ ] **Step 3: Implement strict sync behavior**

Use `set -euo pipefail`, `mkdir` lock, explicit owned-path staging, immutable backup of the current `mkdocs.yml`, failure on drift rather than checkout, no global Git config mutation, and a final atomic JSON result. The script must still copy wiki/raw/root files, rebuild indexes, validate links, build, push, and deploy in the exact AGENTS order.

- [ ] **Step 4: Implement dry-run job planning and exact OpenClaw commands**

The installer first runs `openclaw backup create --only-config --verify --output PRIVATE_BACKUP_DIR` and snapshots Cron JSON. It emits, but does not execute until `--apply`, exact `openclaw cron add/edit/enable/disable` argv arrays. Configure failure alerts with `--failure-alert`, explicit destination resolved from the owner DM, `--failure-alert-after 2`, `--failure-alert-cooldown 6h`, `--failure-alert-exclude-skipped`, and no `--best-effort-deliver`.

- [ ] **Step 5: Run fault injection and dry-run against a redacted real Cron snapshot, then commit**

```bash
git add integrations/hermes-opportunity-os/deployment integrations/hermes-opportunity-os/tests/deployment
git commit -m "fix: make opportunity automation and KB sync reliable"
```

### Task 11: ngrok policy, LaunchAgents, and deployment CLI

**Files:**
- Create: `integrations/hermes-opportunity-os/deployment/ngrok/traffic-policy.example.yml`
- Create: `integrations/hermes-opportunity-os/deployment/launchagents/com.liujun.opportunity-dashboard.plist`
- Create: `integrations/hermes-opportunity-os/deployment/launchagents/com.liujun.opportunity-ngrok.plist`
- Modify: `integrations/hermes-opportunity-os/src/opportunity_os/cli.py`
- Test: `integrations/hermes-opportunity-os/tests/deployment/test_launchagents.py`
- Test: `integrations/hermes-opportunity-os/tests/dashboard/test_auth.py`

**Interfaces:**
- Produces: CLI `deployment render --owner-email EMAIL --ngrok-domain DOMAIN --output PRIVATE_DIR`, validated LaunchAgent plists, and a GitHub OAuth Traffic Policy.

- [ ] **Step 1: Write failing policy/plist tests**

```python
def test_ngrok_policy_authenticates_before_allowlist(rendered_policy):
    steps = rendered_policy["on_http_request"]
    assert steps[0]["actions"][0]["type"] == "oauth"
    assert steps[0]["actions"][0]["config"]["provider"] == "github"
    assert steps[1]["actions"][0]["type"] == "deny"

def test_launchagents_are_keepalive_loopback_and_secret_free(plists):
    assert all(item["RunAtLoad"] and item["KeepAlive"] for item in plists)
    rendered = json.dumps(plists)
    assert "AUTHTOKEN" not in rendered
    assert "--host\", \"127.0.0.1" in rendered
```

- [ ] **Step 2: Run deployment tests and verify failure**

- [ ] **Step 3: Implement rendered private configuration**

The committed policy is a schema-valid example with no identity. The deployment command accepts the owner email and assigned domain as arguments, generates a 32-byte origin credential directly into the 0600 private environment/policy, configures managed GitHub OAuth, denies any identity whose email differs, and sets 1-hour maximum session with 10-minute identity refresh. Document the GitHub private-email limitation and fail closed if the identity email is absent.

- [ ] **Step 4: Validate LaunchAgents without loading them**

Run `plutil -lint` on both rendered plists. Dashboard command must be `uv run --directory ... opportunity-os dashboard serve --host 127.0.0.1 --port 8765`; ngrok command must be `ngrok http 8765 --traffic-policy-file PRIVATE_POLICY_PATH`. Logs go to a bounded log directory managed by rotation, never to the repository.

- [ ] **Step 5: Commit deployment templates**

```bash
git add integrations/hermes-opportunity-os/deployment integrations/hermes-opportunity-os/src/opportunity_os/cli.py integrations/hermes-opportunity-os/tests/deployment
git commit -m "feat: add secure dashboard and ngrok deployment"
```

### Task 12: Production deployment, security hardening, and end-to-end verification

**Files:**
- Modify: `integrations/hermes-opportunity-os/README.md`
- Modify: `integrations/hermes-opportunity-os/profile/config.yaml`
- Modify: `wiki/syntheses/index.md` only if exporter creates new pages
- Modify: `log.md` append-only
- Deploy after approval: `~/.hermes/profiles/opportunity-discovery/**`
- Deploy after approval: `~/.openclaw/**`
- Deploy after approval: `~/Library/LaunchAgents/com.liujun.opportunity-*.plist`
- Deploy after visible input: `~/.config/opportunity-dashboard/**`

**Interfaces:**
- Delivers the running Dashboard URL, local status commands, DingTalk commands, rollback bundle, and verification report.

- [ ] **Step 1: Run the complete repository verification before deployment**

```bash
UV_CACHE_DIR=/private/tmp/hermes-dashboard-uv-cache uv run --directory integrations/hermes-opportunity-os --extra test pytest -q
UV_CACHE_DIR=/private/tmp/hermes-dashboard-uv-cache uv run --directory integrations/hermes-opportunity-os opportunity-os --help
rg -n --hidden --glob '!.git/**' --glob '!raw/**' '(go-[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{12,}|AUTHTOKEN=.+|Authorization: Bearer)' .
```

Expected: all tests PASS; CLI lists dashboard/automation/monitor/deployment; secret scan has no real matches.

- [ ] **Step 2: Back up and apply Hermes/OpenClaw safety settings**

Create verified OpenClaw backup and Hermes Profile export. Resolve the DingTalk owner only from `openclaw directory self --channel dingtalk --json` or a trusted existing DM; never print credential values. Apply `dmPolicy=allowlist`, owner `allowFrom`, `groupPolicy=disabled`, and `contextVisibility=allowlist_quote` with `openclaw config set --dry-run` before the real command. Deploy Hermes Profile changes and rerun `config check` plus both MCP tests.

Deploy the tested `hermes-dashboard` OpenClaw Skill into the existing OpenClaw workspace through its documented Skill installation path, then verify every read command, non-owner rejection, and two-phase mutation from a trusted owner DM.

- [ ] **Step 3: Pause for visible ngrok login and Authtoken entry**

Ask the user to create/login to ngrok and run the official `ngrok config add-authtoken` command in a visible terminal. Do not ask for the token in chat. Capture only `ngrok version`, authenticated status, assigned domain, and whether GitHub OAuth returns the owner email.

- [ ] **Step 4: Render/load LaunchAgents and apply OpenClaw jobs**

Install private config with mode 0600 and directories 0700. Load the Dashboard and ngrok LaunchAgents, apply the reviewed OpenClaw job plan, remove the duplicate embedded sync, move Sunday Lint to 20:30, and keep 22:30 as the only KB sync. Confirm `launchctl print` and loopback `lsof` state.

- [ ] **Step 5: Execute security and functional end-to-end tests**

Verify local bootstrap, external GitHub login, non-owner denial, Host/Origin/CSRF/nonce rejection, status accuracy, OpenClaw/Hermes conversations without delivery, task Diff/approval/run-now, Hermes daily/weekly idempotency, sanitized KB output, and GitHub Pages link after the unique sync job.

- [ ] **Step 6: Execute fault and restart tests**

Inject Hermes timeout, task non-zero exit, DingTalk delivery failure, sync build/push/deploy failure, Dashboard stop, and ngrok stop. Confirm one FIRING, cooldown suppression, one RECOVERED, restart budgets, no log deletion, no false success, and no unrelated Git staging. Restart the Mac only after all non-reboot tests pass and user confirms the reboot checkpoint; after login verify all LaunchAgents, Cron, OAuth, DingTalk, and recovery notice.

- [ ] **Step 7: Update operator documentation and status commands**

Document:

```text
opportunity-os dashboard status
opportunity-os monitor once --format json
openclaw gateway status
openclaw cron list --all --json
hermes -p opportunity-discovery config check
hermes -p opportunity-discovery mcp test opportunity_os
launchctl print gui/$UID/com.liujun.opportunity-dashboard
launchctl print gui/$UID/com.liujun.opportunity-ngrok
```

Document DingTalk queries `Hermes 状态`, `Hermes 最新周报`, `Hermes 当前方向`, `Hermes 机会详情 <ID>`, `Hermes 最近学到了什么`, `Hermes 待审批记忆`, `Hermes 待审批Skill`, `Hermes 反馈：...`, and `Hermes 修改需求：...`.

- [ ] **Step 8: Recompute hashes, inspect dirty state, and commit documentation only**

Confirm user pre-existing dirty files are unchanged, append `log.md`, and stage only owned repository files.

```bash
git add integrations/hermes-opportunity-os/README.md integrations/hermes-opportunity-os/profile/config.yaml
git commit -m "docs: add opportunity dashboard operations guide"
```

### Task 13: Final review and branch integration

**Files:** No new production files unless review finds a defect.

- [ ] **Step 1: Use `superpowers:requesting-code-review` for spec and code conformance**
- [ ] **Step 2: Fix only evidence-backed findings with TDD and focused commits**
- [ ] **Step 3: Use `superpowers:verification-before-completion` and rerun the complete suite, security scan, host probes, delivery test, and clean owned diff inspection**
- [ ] **Step 4: Use `superpowers:finishing-a-development-branch` to present merge/PR/retain-worktree choices; do not delete the retained earlier Hermes worktree without user approval**

## Rollback Order

If production validation fails, roll back in this order:

1. Disable newly created OpenClaw Hermes/monitor jobs; do not delete them.
2. Unload ngrok and Dashboard LaunchAgents; loopback OpenClaw remains available.
3. Restore OpenClaw config from the verified backup and confirm the original hash.
4. Restore the previous Hermes Profile export under a new Profile name and run `doctor` before switching.
5. Restore the previous `sync_kb.sh` backup if the strict replacement fails its fixture and live dry-run.
6. Preserve audit, incident, heartbeat, and failure logs; never delete evidence during rollback.

## Final Acceptance Evidence

The completion report must include, without secrets:

- Git commit IDs and exact test counts.
- Local and external Dashboard URLs, with the external hostname but no session query/token.
- LaunchAgent loaded/running state and loopback listeners.
- OpenClaw/Hermes versions, config checks, MCP tests, and Cron names/schedules.
- DingTalk owner-only policy and one actual delivered test message ID/status.
- One synthetic FIRING and RECOVERED incident trace.
- One successful daily or weekly Hermes run with idempotency evidence.
- Generated private report location and sanitized Wiki/GitHub Pages link.
- Before/after config hashes, backup locations, rollback commands, and preserved unrelated dirty files.
