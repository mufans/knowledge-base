# Hermes 个人方向与机会发现系统实施计划

> **Required sub-skill:** `superpowers:executing-plans`；实现功能与修复时同时遵循 `superpowers:test-driven-development`，完成声明前遵循 `superpowers:verification-before-completion`。

**Goal:** 在不修改 OpenClaw 生产配置、不写入知识库 `raw/`、不把私人数据放进 Git 仓库的前提下，部署 Hermes v0.18.2 独立 Profile，并交付可持久化、可验证、反信息茧房、稳定优先的机会发现工作流。

**Architecture:** OpenClaw 继续负责广域采集；仓库新增一个无秘密的 `opportunity_os` Python 包和独立 MCP Server。MCP Server 只读知识库，所有 Opportunity、Experiment、Direction、Review、TechState 写入 Hermes Profile 的私有目录。Hermes 仅加载专用 Skill 和两个 MCP Server，主模型为 OpenCode Go `deepseek-v4-flash`，fallback 为 DeepSeek 官方 `deepseek-v4-flash`。

**Tech Stack:** Hermes Agent 0.18.2、uv 管理的 Python 3.12、Python 标准库、FastMCP、pytest、YAML 配置、JSON/JSONL 私有状态。

**Authoritative version baseline (2026-07-19):**

- Hermes latest stable release: `v2026.7.7.2` / package `0.18.2`。
- Hermes built-in providers: `opencode-go` with `OPENCODE_GO_API_KEY`; `deepseek` with `DEEPSEEK_API_KEY`。
- OpenCode Go endpoint/model: `https://opencode.ai/zen/go/v1/chat/completions`, `deepseek-v4-flash`。
- DeepSeek endpoint/model: `https://api.deepseek.com`, `deepseek-v4-flash`。
- Hermes current fallback shape: top-level `fallback_providers` list。

---

## 1. Safety baseline and exact boundaries

**Read-only checks:**

- `git status --short`
- `shasum -a 256 ~/.openclaw/openclaw.json`
- `find ~/.openclaw/cron -type f -maxdepth 2 -print0 | sort -z | xargs -0 shasum -a 256`
- `command -v uv docker hermes`
- `uv --version`; `docker version`; existing `hermes version` if present

**Persist outside Git:**

- Hermes profile: `~/.hermes/profiles/opportunity-discovery/`
- Private OS state: `~/.hermes/profiles/opportunity-discovery/opportunity-os/`
- Secrets: `~/.hermes/profiles/opportunity-discovery/.env`

**Repository files allowed to change:**

- `integrations/hermes-opportunity-os/**`
- `docs/superpowers/specs/2026-07-19-hermes-opportunity-discovery-os-design.md`
- `docs/superpowers/plans/2026-07-19-hermes-opportunity-discovery-os.md`
- append-only `log.md`

**Forbidden mutations:**

- `~/.openclaw/**`
- `raw/**`
- existing `wiki/**`
- API keys in repository, process arguments, logs, shell history, test fixtures, or captured output
- production cron/gateway/messaging setup

At the end, recompute OpenClaw hashes and compare them byte-for-byte with this baseline.

## 2. Build the deterministic core with TDD

Create the package:

```text
integrations/hermes-opportunity-os/
├── README.md
├── pyproject.toml
├── mcp_server.py
├── src/opportunity_os/
│   ├── __init__.py
│   ├── cli.py
│   ├── errors.py
│   ├── freshness.py
│   ├── models.py
│   ├── reports.py
│   ├── scoring.py
│   ├── signals.py
│   └── store.py
├── skills/opportunity-discovery/
│   ├── SKILL.md
│   └── references/
│       ├── data-contracts.md
│       ├── freshness-policy.md
│       ├── operating-rhythm.md
│       ├── safety-policy.md
│       └── source-policy.md
└── tests/
    ├── fixtures/knowledge/raw/inbox/2026-07-18-技术动态.md
    ├── fixtures/knowledge/raw/inbox/2026-07-19-跨领域信号.md
    ├── test_cli.py
    ├── test_freshness.py
    ├── test_models.py
    ├── test_reports.py
    ├── test_scoring.py
    ├── test_signals.py
    └── test_store.py
```

### 2.1 Models and score

Write failing tests first for:

- `Signal`, `Evidence`, `Opportunity`, `Experiment`, `Direction`, `Review`, `TechState` serialization and validation.
- Evidence type is exactly `fact`, `inference`, or `hypothesis`.
- Opportunity score uses exact weights: `25/20/15/15/10/10/5` and rejects values outside `0..10`.
- Direction status is `observe`, `validate`, or `active`.
- Tech maturity is `frontier` or `stable`.
- Stable promotion requires all five gates: official stable release, complete docs, compatibility test, no severe known issue, rollback path.

Run and expect failure:

```bash
uv run --directory integrations/hermes-opportunity-os pytest tests/test_models.py tests/test_scoring.py tests/test_freshness.py -q
```

Implement the smallest code to pass, then rerun the same command expecting all tests green.

### 2.2 Broad signal reader

Write failing tests that prove:

- `raw/inbox` is only read; no files are opened in write mode.
- default listing has no personal-goal or project filter.
- newest files are returned first with stable pagination.
- Markdown title, date, source links, category hint and excerpt are extracted.
- path traversal and files outside `raw/inbox` are rejected.
- explicit query filters are allowed only when the caller asks; default collection remains broad.

Run failing tests, implement `signals.py`, rerun until green.

### 2.3 Private store and invariants

Write failing tests that prove:

- state is atomically written beneath the configured private home only.
- every mutation appends a redacted event to `events.jsonl`.
- Opportunity cards require positive and opposing evidence, invalidation condition, 1–2 week minimum experiment, continue criterion, and stop criterion.
- portfolio caps are enforced: observe ≤5, validate ≤2, active ≤1; active may be zero.
- experiment evidence may support or contradict an opportunity.
- a daily review requires at least one `surprise` item.
- a weekly review enforces presentation counts close to 40/40/20, allowing integer rounding.
- no record accepts fields named `api_key`, `token`, `password`, `secret`, exact cash amount, private contact, or application message.
- tech state cannot overwrite a stable baseline with an unverified frontier record.

Run failing tests, implement `store.py`, rerun until green.

### 2.4 Reports and CLI

Write failing tests for:

- `opportunity-os init --home PATH` creates the private layout and initial portfolio.
- `opportunity-os doctor` validates the knowledge root is readable and private home is outside the knowledge repo.
- `opportunity-os signals --days 14 --limit 80 --format json` emits broad, traceable signals.
- `opportunity-os status --format json` reports counts and invariants without private content.
- `opportunity-os render-review REVIEW_ID` renders Chinese Markdown with Fact/Inference/Hypothesis, surprise, positive/opposing evidence, experiment and freshness sections.
- `opportunity-os snapshot` creates a local rollback archive outside Git without secrets.

Implement `reports.py` and `cli.py`, then run:

```bash
uv run --directory integrations/hermes-opportunity-os pytest -q
uv run --directory integrations/hermes-opportunity-os opportunity-os --help
```

Expected: all tests pass; CLI help lists `init`, `doctor`, `signals`, `status`, `render-review`, `snapshot`.

Commit repository core only after tests pass:

```bash
git add -f integrations/hermes-opportunity-os
git commit -m "feat: add opportunity discovery core"
```

Do not stage unrelated existing worktree changes.

## 3. Build and test the dedicated MCP server

`mcp_server.py` exposes typed tools:

- `list_signals(days=14, limit=80, offset=0, query=None)`
- `get_signal(relative_path)`
- `save_opportunity(title, opportunity_type, summary, presentation_bucket, supporting_evidence, opposing_evidence, invalidation_conditions, experience_fit, experiment, continue_criteria, stop_criteria, scores)`
- `list_opportunities(status=None)`
- `record_experiment(opportunity_id, title, hypothesis, started_at, ends_at, cost_level, success_metric, continue_criteria, stop_criteria, evidence)`
- `set_direction(direction_id, title, status, opportunity_ids, rationale, next_review_at)`
- `get_portfolio()`
- `record_tech_state(technology, known_latest, recommended_stable, maturity, official_sources, observed_at, review_due_at, confidence, stable_gates, rollback_path)`
- `save_review(period, title, summary, opportunity_ids, surprise_signal, presentation_counts, proposed_experiment_ids, facts, inferences, hypotheses)`
- `render_review(review_id)`
- `system_status()`

Environment:

- `KNOWLEDGE_BASE_PATH` points to the current knowledge repo.
- `OPPORTUNITY_OS_HOME` points to the private profile state.

Add failing tests around every tool's successful case and invariant rejection. Test the server import and MCP tool registration. Run:

```bash
uv run --directory integrations/hermes-opportunity-os pytest -q
uv run --directory integrations/hermes-opportunity-os python -c "import mcp_server; print(mcp_server.mcp.name)"
```

Expected server name: `opportunity-discovery-os`.

## 4. Author the Hermes skill and safety identity

Create `skills/opportunity-discovery/SKILL.md` with official Hermes frontmatter:

- name: `opportunity-discovery`
- concise description ≤60 characters
- macOS/Linux platforms
- requires MCP toolset
- non-secret config keys for knowledge and private home

The procedure must:

1. start with broad `list_signals` and never use user relevance as collection admission;
2. separate facts, inferences and hypotheses;
3. search opposing evidence before saving a card;
4. create 3–5 cards, at least one surprise, and 40/40/20 weekly presentation mix;
5. propose only 1–2 week low-cost experiments;
6. enforce direction capacity;
7. keep `known_latest` and `recommended_stable` separate;
8. prohibit publishing, applications, messages, payments, deletion, credential access and OpenClaw mutation;
9. write only through the MCP tools;
10. report uncertainty and source dates.

Reference files contain the exact schemas, source hierarchy, cadence, stable-promotion gates and safety rules. Add a static skill linter test for frontmatter, description length, required sections and prohibited capabilities.

## 5. Install Hermes 0.18.2 in an isolated uv environment

Request filesystem/network approval because this writes under `~/.local` and `~/.hermes` and downloads packages. Install the pinned package with Python 3.12:

```bash
uv tool install --python 3.12 "hermes-agent==0.18.2"
```

If `hermes` is not in the current PATH, use the absolute launcher returned by `uv tool dir --bin` and do not edit shell startup files.

Verify:

```bash
hermes version
hermes doctor
```

Expected: package version `0.18.2`; Python interpreter reports `3.12.x`. Record warnings but do not install optional messaging/browser integrations unless required by this profile.

## 6. Create the private Profile and runtime safely

Create without bundled skills and without a shell alias:

```bash
hermes profile create opportunity-discovery --no-skills --no-alias --description "发现个人技术、职业、产品与跨领域机会，使用可回滚的低成本实验验证方向。"
```

If the profile already exists, inspect it first, create a local profile export backup, and update only files owned by this plan; never delete it.

Initialize state:

```bash
uv run --directory integrations/hermes-opportunity-os opportunity-os init \
  --home ~/.hermes/profiles/opportunity-discovery/opportunity-os \
  --knowledge-root "/Users/liujun/Nutstore Files/我的坚果云/knowledge"
```

Install the skill into:

```text
~/.hermes/profiles/opportunity-discovery/skills/productivity/opportunity-discovery/
```

Copy only the reviewed Skill and references; the repository remains the source template, while personal state remains private.

Create `SOUL.md` specifying Chinese output, opportunity-discovery mission, anti-cocoon policy, evidence labels, stable-first policy and human approval boundaries.

Create `config.yaml` with:

```yaml
model:
  provider: opencode-go
  default: deepseek-v4-flash
  context_length: 1000000
fallback_providers:
  - provider: deepseek
    model: deepseek-v4-flash
agent:
  max_turns: 24
  disabled_toolsets:
    - terminal
    - file
    - browser
    - delegation
    - cronjob
    - messaging
memory:
  memory_enabled: true
  user_profile_enabled: false
  write_approval: true
skills:
  guard_agent_created: true
  write_approval: true
approvals:
  mode: manual
display:
  language: zh
  tool_progress: new
onboarding:
  profile_build: "off"
mcp_servers:
  opportunity_os:
    command: uv
    args: ["run", "--directory", "/Users/liujun/Nutstore Files/我的坚果云/knowledge/integrations/hermes-opportunity-os", "python", "mcp_server.py"]
    env:
      KNOWLEDGE_BASE_PATH: "/Users/liujun/Nutstore Files/我的坚果云/knowledge"
      OPPORTUNITY_OS_HOME: "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os"
  knowledge:
    command: uv
    args: ["run", "--directory", "/Users/liujun/Nutstore Files/我的坚果云/knowledge/mcp_server", "python", "server.py"]
    env:
      KNOWLEDGE_BASE_PATH: "/Users/liujun/Nutstore Files/我的坚果云/knowledge"
```

Do not configure any Hermes Cron; OpenClaw remains the only production scheduler.

Offline verification:

```bash
hermes -p opportunity-discovery config check
hermes -p opportunity-discovery profile show opportunity-discovery
hermes -p opportunity-discovery skills list
hermes -p opportunity-discovery mcp list
hermes -p opportunity-discovery mcp test opportunity_os
hermes -p opportunity-discovery mcp test knowledge
hermes -p opportunity-discovery prompt-size --json
```

Expected: exactly the dedicated skill plus both MCP servers; terminal/file/browser/delegation/cron/messaging absent from the profile tools.

## 7. Hidden API key entry

Start a PTY command that disables echo and reads both keys directly into the profile `.env` using an in-memory process. The command must not include either key as an argument and must restore terminal echo on exit. Pause and tell the user when the prompt displays:

```text
OpenCode Go API Key:
DeepSeek API Key:
```

The helper writes with mode `0600` and exact variable names:

```dotenv
OPENCODE_GO_API_KEY=由隐藏输入写入的值
DEEPSEEK_API_KEY=由隐藏输入写入的值
```

Never print, partially mask, hash, count, or inspect the key values. Verification is limited to:

- file permissions are `0600`;
- both variable names are present exactly once;
- values are non-empty, checked inside the helper with no value output;
- `.env` path is outside the repository.

## 8. Provider smoke tests and fallback test

Run a minimal primary call:

```bash
hermes -p opportunity-discovery chat --quiet --max-turns 1 \
  --provider opencode-go --model deepseek-v4-flash \
  -q "只回复 PRIMARY_OK"
```

Run a minimal fallback-provider direct call:

```bash
hermes -p opportunity-discovery chat --quiet --max-turns 1 \
  --provider deepseek --model deepseek-v4-flash \
  -q "只回复 FALLBACK_OK"
```

Expected: each returns only its marker. Do not log provider response metadata that could include headers.

Validate automatic fallback configuration offline from parsed config and, if Hermes provides a safe built-in fallback diagnostics command, run it. Do not intentionally invalidate or overwrite a real key to force failure.

## 9. End-to-end opportunity discovery run

Use existing recent OpenClaw outputs through `opportunity_os.list_signals`; do not modify them. Start Hermes from the private profile directory so the knowledge repo's `AGENTS.md` is not injected as a writable workspace rule.

Run:

```bash
hermes -p opportunity-discovery chat --quiet --max-turns 24 \
  --skills opportunity-discovery \
  -q "执行首次每周机会发现：广泛读取最近14天信号，保存3到5张完整机会卡，至少一张为意外发现；保存方向组合与一份weekly review。不要对外行动。最后只返回review id和三行摘要。"
```

Verify through the deterministic CLI, not by trusting prose:

```bash
uv run --directory integrations/hermes-opportunity-os opportunity-os doctor --home "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os" --knowledge-root "/Users/liujun/Nutstore Files/我的坚果云/knowledge"
uv run --directory integrations/hermes-opportunity-os opportunity-os status --home "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os" --format json
uv run --directory integrations/hermes-opportunity-os opportunity-os render-review --home "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os" --latest
```

Acceptance checks:

- 3–5 complete Opportunity cards;
- supporting and opposing evidence on every card;
- at least one surprise;
- source paths/dates and invalidation conditions;
- one proposed 1–2 week experiment with continue/stop criteria;
- direction limits respected;
- SmartInspector and Skill are not default main axes;
- private files exist only under the profile;
- `raw/` and OpenClaw hashes unchanged.

If model output violates a deterministic constraint, use the MCP validation error as feedback for one repair run. Do not silently relax validators.

## 10. Freshness/stability seed and review cadence

Use official current data verified during this implementation to save initial `TechState` records for:

- Hermes Agent: `known_latest=0.18.2`, `recommended_stable=0.18.2` only after local install tests pass.
- OpenCode Go model catalog: `known_latest` includes `deepseek-v4-flash`, with review due in 14 days because models/limits may change.
- DeepSeek API: `known_latest=deepseek-v4-flash`, with legacy aliases marked for 2026-07-24 retirement.

Each record includes official URL, observed date, review due date, confidence, rollback path and all Stable gates. Any untested update remains Frontier.

Create local, disabled-by-default cadence templates in the private directory for daily, weekly, two-week experiment, six-week portfolio and quarterly zero-base review. They are documentation/prompts only, not Hermes or OpenClaw scheduled jobs.

## 11. Audit, rollback and documentation

Update `integrations/hermes-opportunity-os/README.md` with:

- architecture and privacy boundary;
- normal commands for daily/weekly/six-week/quarterly use;
- provider selection and fallback behavior;
- how to update the Hermes version conservatively;
- how to snapshot/restore private state;
- how to disable the profile without touching OpenClaw;
- explicit note that no scheduler is installed.

Create a private snapshot:

```bash
uv run --directory integrations/hermes-opportunity-os opportunity-os snapshot --home "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os"
```

Run repository tests and secret scans:

```bash
uv run --directory integrations/hermes-opportunity-os pytest -q
rg -n --hidden --glob '!.git/**' --glob '!raw/**' '(go-[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{12,}|OPENCODE_GO_API_KEY=.+|DEEPSEEK_API_KEY=.+)' .
git diff --check
git status --short
```

The scan may match documentation placeholders only; inspect every match and ensure no real-looking value exists.

Recompute and compare:

- `~/.openclaw/openclaw.json` hash;
- every file under `~/.openclaw/cron/` hash;
- `raw/` tracked/untracked status relative to the baseline;
- unrelated dirty files from the initial `git status`.

Append an implementation entry to `log.md`, but stage only the exact new line if unrelated log changes make safe staging impossible; otherwise leave it unstaged and report why.

Commit only owned repository files after verification:

```bash
git add -f integrations/hermes-opportunity-os docs/superpowers/specs/2026-07-19-hermes-opportunity-discovery-os-design.md docs/superpowers/plans/2026-07-19-hermes-opportunity-discovery-os.md
git commit -m "feat: deploy Hermes opportunity discovery OS"
```

## 12. Final self-review checklist

- Every approved design object has a schema and persistence route.
- Every design invariant has a deterministic test, not just a prompt rule.
- No placeholder file/path/interface remains in executable code.
- OpenCode Go and DeepSeek use official built-in Hermes provider IDs.
- The profile is isolated and private; no personal opportunity data is in Git.
- Knowledge access is read-only through MCP; `raw/` unchanged.
- No Hermes cron and no OpenClaw mutation.
- Surprise and 40/40/20 are enforced at review save time.
- Frontier cannot replace Stable without gates.
- Provider and end-to-end smoke tests pass.
- API keys never appear in command arguments, logs, output, repo, or Git diff.
- Rollback snapshot exists and restore steps are documented.
