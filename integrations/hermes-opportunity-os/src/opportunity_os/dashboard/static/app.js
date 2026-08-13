export const routes = ["overview", "signals", "opportunities", "tasks", "reports", "monitoring"];

const POLL_INTERVAL_MS = 60_000;

const pageMeta = {
  overview: ["Knowledge Control Center", "PIPELINE OVERVIEW", "从采集到 Hermes 分析、再到 Wiki 决策的只读总览。"],
  signals: ["证据与质量", "KNOWLEDGE QUALITY", "引用覆盖、拒绝原因、重复候选与信息增量，一眼看清知识库健康度。"],
  opportunities: ["机会与实验", "HERMES LOOP", "跟踪每个机会的状态、正反证据、评分与最小实验。"],
  tasks: ["任务与调度", "OPENCLAW RUNTIME", "只读查看定时任务健康度；控制操作仍由 OpenClaw 原生页面负责。"],
  reports: ["分析转化", "HERMES → WIKI", "研究 dossier、发布转化与近期审计事件。"],
  monitoring: ["服务健康", "SYSTEM HEALTH", "检查采集、分析、同步、发布与外网入口的运行状态。"],
};

const stateOrder = ["candidate", "researched", "validated", "active", "completed", "rejected", "archived"];
const stateLabels = {
  candidate: "候选", researched: "已研究", validated: "已验证", active: "进行中",
  completed: "已完成", rejected: "已拒绝", archived: "已归档",
};

const healthLabels = {
  healthy: "运行正常", degraded: "性能下降", down: "故障", empty: "暂无数据", disconnected: "未连接",
};

const costLabels = { none: "零成本", low: "低成本", medium: "中成本" };

const rejectionLabels = {
  invalid_evidence_contract: "证据契约不合法",
  invalid_evidence_type: "证据类型无效",
  invalid_review_contract: "复盘契约不合法",
  missing_opportunity: "机会缺失",
  invalid_opportunity: "机会数据不合法",
  missing_supporting_evidence: "缺少支持证据",
  missing_opposing_evidence: "缺少反方证据",
  target_path_invalid: "目标路径非法",
  page_type_sections_missing: "页面章节缺失",
  empty_section: "存在空章节",
  evidence_missing: "证据缺失",
  opposing_evidence_missing: "反方证据缺失",
  opposing_evidence_required: "需要反方证据",
  fact_citation_coverage_below_90_percent: "事实引用不足 90%",
  numeric_version_performance_api_coverage_below_100_percent: "数字/API 未全覆盖",
  claim_references_undeclared_evidence: "引用未声明证据",
  purpose_mismatch: "方向不匹配",
  insufficient_information_gain: "信息增量不足",
  insufficient_update_gain: "更新增量不足",
  target_path_required: "缺少目标路径",
  create_target_exists_use_update: "目标已存在应更新",
  update_target_missing: "更新目标缺失",
  duplicate_candidate_use_update: "重复候选应更新",
  broken_local_links: "存在断链",
  unverifiable_code_or_parameters: "代码/参数不可验证",
  obsidian_links_forbidden: "禁用 Obsidian 链接",
  bare_url_forbidden: "存在裸 URL",
  quality_gate_failed: "质量门禁未通过",
  candidate_self_rejected: "候选自拒",
  human_rejected: "人工拒绝",
  human_decision_required: "需要人工决策",
  quality_gate_passed: "质量门禁通过",
};

const detail = {
  opportunities: null,
  reviews: null,
  experiments: null,
  techStates: null,
  events: null,
};
let snapshot = {};
let taskData = { status: null, jobs: [], runs: {}, loading: false, error: null };
let connected = false;
let loaded = false;
let lastUpdatedAt = null;
let pollTimer = null;

function safe(value) {
  return String(value ?? "—").replace(/[&<>'"]/g, character => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[character]
  ));
}

function display(value) {
  return typeof value === "number" ? value.toLocaleString("zh-CN") : safe(value);
}

function route() {
  const value = location.hash.slice(1);
  return routes.includes(value) ? value : "overview";
}

function healthState(data) {
  const components = data.components ?? [];
  if (!components.length) return "empty";
  if (components.some(item => item.status === "down")) return "down";
  if (components.some(item => item.status !== "healthy")) return "degraded";
  return "healthy";
}

function formatPercent(value, emptyText = "—") {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : emptyText;
}

function rejectionLabel(raw) {
  const key = String(raw).split(":")[0];
  return rejectionLabels[key] ?? key;
}

function header(name, state) {
  const [title, eyebrow, description] = pageMeta[name];
  return `<header class="page-header">
    <div class="page-header-copy"><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${description}</p></div>
    <div class="page-actions">
      <button type="button" class="refresh-btn" data-refresh aria-label="刷新数据"><span aria-hidden="true">↻</span>刷新数据</button>
      <span class="state-pill state-${safe(state)}"><i aria-hidden="true"></i>${safe(healthLabels[state] ?? state)}</span>
    </div>
  </header>`;
}

function metric(label, value, note, tone = "") {
  return `<article class="metric-card ${safe(tone)}">
    <span>${safe(label)}</span><strong>${display(value)}</strong><small>${safe(note)}</small>
  </article>`;
}

function badge(value, tone = "") {
  return `<span class="badge ${safe(tone)}">${safe(value)}</span>`;
}

function empty(message) {
  return `<div class="empty-state"><span aria-hidden="true">◇</span><p>${safe(message)}</p></div>`;
}

function bar(label, value, total) {
  const percentage = total > 0 ? Math.round(value / total * 100) : 0;
  return `<div class="bar-row">
    <div><span>${safe(label)}</span><strong>${display(value)}</strong></div>
    <progress value="${percentage}" max="100" aria-label="${safe(label)} ${percentage}%"></progress>
  </div>`;
}

async function fetchJson(path) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {Accept: "application/json"},
  });
  if (response.status === 401) throw new Error("authentication_required");
  if (!response.ok) throw new Error(`${path}:${response.status}`);
  return response.json();
}

async function loadDetails(name) {
  const requests = [];
  const load = (key, path) => {
    if (detail[key] === null) requests.push(fetchJson(path).then(value => { detail[key] = value; }));
  };
  if (["overview", "opportunities", "reports"].includes(name)) {
    load("opportunities", "/api/v1/opportunities");
    load("reviews", "/api/v1/reviews");
    load("experiments", "/api/v1/experiments");
  }
  if (["overview", "signals", "reports"].includes(name)) load("events", "/api/v1/event-log");
  if (name === "signals") load("techStates", "/api/v1/tech-states");
  await Promise.all(requests);
}

function invalidateDetails() {
  Object.keys(detail).forEach(key => { detail[key] = null; });
}

export function renderOverview(data = {}, state = healthState(data)) {
  const metrics = data.pipeline_metrics ?? {};
  const states = data.opportunity_state_counts ?? {};
  const totalStates = Object.values(states).reduce((sum, value) => sum + Number(value), 0);
  const components = data.components ?? [];
  return `<div class="page" data-page="overview">
    ${header("overview", state)}
    <section class="metrics">
      ${metric("今日分析输入", metrics.today_collected ?? 0, "Hermes 同步读取")}
      ${metric("今日发布", metrics.today_published ?? 0, "0 也是成功结果")}
      ${metric("本周转化率", formatPercent(metrics.conversion_rate), "分析输入 → Wiki 更新")}
      ${metric("当前事故", data.active_incidents ?? 0, "degraded / down", data.active_incidents ? "attention" : "")}
    </section>
    <section class="split-grid">
      <article class="panel">
        <div class="panel-heading"><div><p class="eyebrow">PIPELINE HEALTH</p><h2>组件状态</h2></div>
        <span>${components.length} 个探针</span></div>
        <div class="component-list">${components.length ? components.map(item => `
          <div class="component-row"><span class="status-dot status-${safe(item.status)}" aria-hidden="true"></span>
          <div><strong>${safe(item.component)}</strong><small>${safe(item.status)} · ${display(item.duration_ms)} ms</small></div></div>
        `).join("") : empty("等待探针结果")}</div>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="eyebrow">HERMES STATE</p><h2>机会状态分布</h2></div>
        <span>${display(totalStates)} 项</span></div>
        <div class="bar-list">${stateOrder.map(key => bar(stateLabels[key], states[key] ?? 0, totalStates)).join("")}</div>
      </article>
    </section>
    <section class="metrics compact">
      ${metric("研究 dossier", metrics.dossiers ?? 0, "证据已结构化")}
      ${metric("待人工决策", metrics.pending_candidates ?? 0, "不自动公开")}
      ${metric("进行中实验", metrics.active_experiments ?? 0, "最小可验证实验")}
      ${metric("本周拒绝", metrics.rejected ?? 0, "拒绝是正常输出")}
    </section>
  </div>`;
}

export function renderSignals(data = {}, state = "empty") {
  const metrics = data.pipeline_metrics ?? {};
  const reasons = Object.entries(data.rejection_reasons ?? {});
  const technologies = detail.techStates ?? [];
  const citation = metrics.citation_coverage;
  const numeric = metrics.numeric_citation_coverage;
  return `<div class="page" data-page="signals">
    ${header("signals", state)}
    <section class="metrics">
      ${metric("重要事实引用", formatPercent(citation, "需迁移"), citation == null ? "旧页面未标记 Fact，需迁移标注" : "目标 ≥ 90%", citation == null ? "attention" : "")}
      ${metric("数字/API 引用", formatPercent(numeric, "需迁移"), numeric == null ? "旧页面未标记，需迁移标注" : "目标 100%", numeric == null ? "attention" : "")}
      ${metric("Broken links", metrics.broken_links ?? "待检查", "发布要求为 0")}
      ${metric("重复候选", metrics.duplicate_candidates ?? "待检查", "优先更新已有页面")}
    </section>
    <section class="split-grid">
      <article class="panel">
        <div class="panel-heading"><div><p class="eyebrow">REJECTION REASONS</p><h2>内容为何没有发布</h2></div>
        <span>${reasons.length} 类原因</span></div>
        <div class="reason-list">${reasons.length ? reasons.map(([reason, count]) => `
          <div class="reason-row" title="${safe(reason)}">
            <div class="reason-text"><strong>${safe(rejectionLabel(reason))}</strong><small>${safe(reason)}</small></div>
            <span class="reason-count">${display(count)}</span>
          </div>`).join("") : empty("暂无拒绝记录，说明最近的候选都通过了质量门禁。")}</div>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="eyebrow">FRESHNESS</p><h2>技术复核</h2></div><span>${technologies.length} 项</span></div>
        <div class="record-list">${technologies.length ? technologies.slice(0, 12).map(item => `
          <article class="record-card">
            <div><strong>${safe(item.technology)}</strong><small>复核：${safe(item.review_due_at)}</small></div>
            ${badge(item.maturity === "stable" ? "稳定" : item.maturity === "frontier" ? "前沿" : (item.maturity ?? "unknown"))}
          </article>`).join("") : empty("暂无技术状态，采集到新技术后会记录复核周期。")}</div>
      </article>
    </section>
  </div>`;
}

function scoreChip(label, value) {
  const number = Number(value);
  const text = Number.isFinite(number) ? number.toFixed(1) : "—";
  return `<span class="score-chip" title="${safe(label)}评分，0–10 分制"><span>${safe(label)}</span><strong>${text}</strong></span>`;
}

function opportunityCard(item) {
  const support = (item.supporting_evidence ?? []).length;
  const oppose = (item.opposing_evidence ?? []).length;
  const scores = item.scores ?? {};
  const experiment = item.minimum_experiment ?? {};
  const status = stateLabels[item.status] ?? item.status;
  return `<article class="opportunity-card">
    <div class="opportunity-head">
      <div class="opportunity-title"><strong>${safe(item.title ?? item.id)}</strong>
      <small>${safe(item.opportunity_type ?? "未分类")} · ${safe(item.id)}</small></div>
      ${badge(status, `state-${item.status}`)}
    </div>
    <p class="opportunity-summary">${safe(item.summary ?? "暂无摘要")}</p>
    <div class="opportunity-scores">
      ${scoreChip("经验优势", scores.experience_advantage)}
      ${scoreChip("低成本验证", scores.low_cost_validation)}
    </div>
    <div class="opportunity-meta">
      <div class="evidence-counts">${badge(`支持 ${support}`,"support")}${badge(`反方 ${oppose}`,"oppose")}</div>
      ${experiment.title ? `<span class="experiment-hint" title="${safe(experiment.success_metric ?? "")}">最小实验：${safe(experiment.title)}</span>` : ""}
    </div>
  </article>`;
}

function experimentCard(item) {
  const experiment = item.experiment ?? item;
  const evidence = (item.evidence ?? []).length;
  const cost = costLabels[experiment.cost_level] ?? experiment.cost_level ?? "未知成本";
  return `<article class="record-card stacked experiment-card">
    <div class="record-title"><div><strong>${safe(experiment.title ?? item.id)}</strong>
    <small>${safe(experiment.starts_at)} → ${safe(experiment.ends_at)} · ${safe(cost)}</small></div>
    ${badge(evidence ? `证据 ${evidence}` : "无证据")}</div>
    <p>${safe(experiment.success_metric ?? "尚未记录成功指标")}</p>
  </article>`;
}

export function renderOpportunities(data = {}, state = "empty") {
  const opportunities = detail.opportunities ?? [];
  const experiments = detail.experiments ?? [];
  const outcomes = data.user_outcome_counts ?? {};
  return `<div class="page" data-page="opportunities">
    ${header("opportunities", state)}
    <section class="metrics compact">
      ${metric("机会", opportunities.length, "含支持与反方证据")}
      ${metric("实验", experiments.length, "1–14 天")}
      ${metric("采纳", outcomes.adopted ?? 0, "用户结果")}
      ${metric("否定", outcomes.rejected ?? 0, "用于反馈采集")}
    </section>
    <section class="split-grid wide-left">
      <article class="panel">
        <div class="panel-heading"><div><p class="eyebrow">OPPORTUNITIES</p><h2>按生命周期排序</h2></div>
        <span>${opportunities.length} 项</span></div>
        <div class="record-list">${opportunities.length ? opportunities.map(opportunityCard).join("") : empty("暂无机会。采集到新内容后，Hermes 会生成候选机会。")}</div>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="eyebrow">EXPERIMENTS</p><h2>最小实验</h2></div>
        <span>${experiments.length} 项</span></div>
        <div class="record-list">${experiments.length ? experiments.map(experimentCard).join("") : empty("暂无实验；researched 状态下一步应提出最小实验。")}</div>
      </article>
    </section>
  </div>`;
}

function taskRows() {
  if (taskData.loading) return `<div class="loading-box" role="status">正在读取 OpenClaw Cron…</div>`;
  if (taskData.error) return `<div class="error-state" role="alert">任务数据暂不可用：${safe(taskData.error)}。请打开 OpenClaw 原生控制台检查。</div>`;
  if (!taskData.jobs.length) return empty("暂无 Cron 任务");
  return `<div class="task-list">${taskData.jobs.map(job => {
    const run = taskData.runs[job.job_id];
    const runText = run?.loading ? "读取中…" : run?.error ? "运行记录不可用" :
      run ? `最近 ${safe(run.run_count ?? "?")} 次` : "查看运行记录";
    return `<article class="task-card">
      <div><strong>${safe(job.job_name ?? job.job_id)}</strong>
      <small>${job.enabled ? "已启用" : "已停用"} · ${safe(job.cron ?? "native")} · ${safe(job.tz ?? "timezone missing")}</small></div>
      <button type="button" data-runs-id="${safe(job.job_id)}">${runText}</button>
    </article>`;
  }).join("")}</div>`;
}

export function renderTasks(data = {}, state = "empty") {
  const metrics = data.pipeline_metrics ?? {};
  return `<div class="page" data-page="tasks">
    ${header("tasks", state)}
    <section class="metrics compact">
      ${metric("任务失败", metrics.run_failures ?? 0, "Compiler / Hermes")}
      ${metric("Timeout", metrics.run_timeouts ?? 0, "需解释或恢复")}
      ${metric("投递失败", metrics.delivery_errors ?? 0, "不得误报成功")}
      ${metric("任务总数", taskData.status?.job_count ?? taskData.jobs.length, "OpenClaw 只读")}
    </section>
    <section class="split-grid wide-left"><article class="panel"><div class="panel-heading"><div><p class="eyebrow">CRON JOBS</p><h2>核心任务</h2></div></div>${taskRows()}</article>
    <aside class="panel native-links"><p class="eyebrow">DEEP LINKS</p><h2>原生控制面</h2>
      <p>本页不复制控制功能，也不保存原生凭据。</p>
      <a class="action-link" href="http://127.0.0.1:18789/" target="_blank" rel="noopener noreferrer">打开 OpenClaw Control UI</a>
      <div class="command-card"><strong>Hermes</strong><code>hermes -p opportunity-discovery dashboard</code></div>
    </aside></section>
  </div>`;
}

export function renderReports(data = {}, state = "empty") {
  const metrics = data.pipeline_metrics ?? {};
  const reviews = detail.reviews ?? [];
  const events = detail.events ?? [];
  return `<div class="page" data-page="reports">
    ${header("reports", state)}
    <section class="metrics">
      ${metric("本周输入", metrics.week_collected ?? 0, "同步读取 review")}
      ${metric("本周发布", metrics.week_published ?? 0, "创建或更新 Wiki")}
      ${metric("转化率", formatPercent(metrics.conversion_rate), "分析 → Wiki")}
      ${metric("拒绝", metrics.rejected ?? 0, "证据不足时成功停止")}
    </section>
    <section class="split-grid">
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">RECENT REVIEWS</p><h2>近期 Review</h2></div></div>
        <div class="record-list">${reviews.length ? reviews.slice(0, 12).map(item =>
          `<article class="record-card stacked"><div><strong>${safe(item.title ?? item.id)}</strong>
          <small>${safe(item.period)} · ${safe(item.created_at)}</small></div>
          <p>${safe(item.summary)}</p></article>`).join("") : empty("暂无 review")}</div></article>
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">AUDIT TRAIL</p><h2>审计事件</h2></div></div>
        <div class="timeline">${events.length ? events.slice(0, 20).map(item =>
          `<div class="timeline-row"><time>${safe((item.at ?? "").slice(0, 16))}</time>
          <div><strong>${safe(item.action)}</strong><small>${safe(item.entity_id)} · ${safe(item.status ?? "")}</small></div></div>`
        ).join("") : empty("暂无事件")}</div></article>
    </section>
  </div>`;
}

export function renderMonitoring(data = {}, state = healthState(data)) {
  const metrics = data.pipeline_metrics ?? {};
  const components = data.components ?? [];
  return `<div class="page" data-page="monitoring">
    ${header("monitoring", state)}
    <section class="component-grid">${components.length ? components.map(item =>
      `<article class="component-card"><span class="status-dot status-${safe(item.status)}" aria-hidden="true"></span>
      <div><strong>${safe(item.component)}</strong><small>${safe(item.status)} · ${safe(item.error_code ?? "ok")} · ${display(item.duration_ms)} ms</small></div></article>`
    ).join("") : empty("等待健康快照")}</section>
    <section class="metrics compact">
      ${metric("Broken links", metrics.broken_links ?? "待检查", "发布门禁")}
      ${metric("同步失败", metrics.run_failures ?? 0, "失败不会显示成功")}
      ${metric("逾期技术状态", data.overdue_tech_states ?? 0, "等待复核")}
      ${metric("生成时间", (data.generated_at ?? "").slice(0, 16), "UTC")}
    </section>
  </div>`;
}

const renderers = {
  overview: renderOverview,
  signals: renderSignals,
  opportunities: renderOpportunities,
  tasks: renderTasks,
  reports: renderReports,
  monitoring: renderMonitoring,
};

function renderAuthenticationError() {
  const main = document.querySelector("#main-content");
  main.innerHTML = `<section class="auth-state" role="alert"><p class="eyebrow">SESSION EXPIRED</p>
    <h1>需要重新登录</h1><p>当前会话已过期。请重新打开受保护的外网地址完成认证；本机访问可重新运行 dashboard open。</p>
    <button type="button" data-reload>重新尝试</button></section>`;
  main.setAttribute("aria-busy", "false");
}

function renderDataError(error) {
  const main = document.querySelector("#main-content");
  main.innerHTML = `<section class="error-state" role="alert"><h1>数据暂时不可用</h1>
    <p>${safe(error instanceof Error ? error.message : "unknown_error")}</p>
    <button type="button" data-refresh>重试</button></section>`;
  main.setAttribute("aria-busy", "false");
}

function updateConnectionLabel() {
  const label = document.querySelector("#connection-label");
  if (!label) return;
  const foot = label.closest(".sidebar-foot");
  if (connected) {
    const time = lastUpdatedAt ? lastUpdatedAt.toLocaleTimeString("zh-CN", {hour12: false}) : "";
    label.textContent = time ? `数据更新于 ${time}` : "数据已就绪";
    foot?.classList.remove("is-error");
  } else {
    label.textContent = "数据加载失败，稍后自动重试";
    foot?.classList.add("is-error");
  }
}

async function renderPage(focus = false) {
  const main = document.querySelector("#main-content");
  const currentRoute = route();
  main.setAttribute("aria-busy", "true");
  try {
    await loadDetails(currentRoute);
    main.innerHTML = renderers[currentRoute](snapshot, connected ? healthState(snapshot) : "disconnected");
    if (currentRoute === "tasks" && !taskData.loading && !taskData.jobs.length && !taskData.error) {
      refreshTasks();
    }
  } catch (error) {
    if (error instanceof Error && error.message === "authentication_required") {
      renderAuthenticationError();
      return;
    }
    renderDataError(error);
    return;
  }
  main.setAttribute("aria-busy", "false");
  document.querySelectorAll("[data-route]").forEach(link => {
    link.toggleAttribute("aria-current", link.dataset.route === currentRoute);
  });
  updateConnectionLabel();
  if (focus) main.focus({preventScroll: true});
}

async function refreshTasks() {
  taskData = {...taskData, loading: true, error: null};
  renderPage();
  try {
    const [jobsResponse, statusResponse] = await Promise.all([
      fetch("/api/v1/tasks", {credentials:"same-origin", headers:{Accept:"application/json"}}),
      fetch("/api/v1/tasks/status", {credentials:"same-origin", headers:{Accept:"application/json"}}),
    ]);
    if (!jobsResponse.ok || !statusResponse.ok) throw new Error("openclaw_tasks_unavailable");
    taskData = {
      ...taskData,
      jobs: await jobsResponse.json(),
      status: await statusResponse.json(),
      loading: false,
      error: null,
    };
  } catch (error) {
    taskData = {...taskData, loading: false, error: error instanceof Error ? error.message : "task_read_failed"};
  }
  renderPage();
}

async function refreshRuns(jobId) {
  taskData = {...taskData, runs: {...taskData.runs, [jobId]: {loading: true}}};
  renderPage();
  try {
    const runs = await fetchJson(`/api/v1/tasks/${encodeURIComponent(jobId)}/runs`);
    taskData = {...taskData, runs: {...taskData.runs, [jobId]: runs}};
  } catch (error) {
    taskData = {...taskData, runs: {...taskData.runs, [jobId]: {error: error instanceof Error ? error.message : "task_runs_failed"}}};
  }
  renderPage();
}

async function refresh() {
  try {
    snapshot = await fetchJson("/api/v1/status");
    connected = true;
    loaded = true;
    lastUpdatedAt = new Date();
    invalidateDetails();
    await renderPage();
  } catch (error) {
    connected = false;
    if (error instanceof Error && error.message === "authentication_required") {
      renderAuthenticationError();
      return;
    }
    if (!loaded) {
      renderDataError(error);
      return;
    }
    updateConnectionLabel();
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(refresh, POLL_INTERVAL_MS);
}

async function bootstrap() {
  const token = new URLSearchParams(location.hash.slice(1)).get("bootstrap");
  if (!token) return;
  history.replaceState(null, "", `${location.pathname}#overview`);
  const response = await fetch("/auth/local/exchange", {
    method: "POST",
    credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({token}),
  });
  if (!response.ok) throw new Error("authentication_required");
}

if (typeof window !== "undefined") {
  window.addEventListener("hashchange", () => renderPage(true));
  window.addEventListener("click", event => {
    const runs = event.target.closest("[data-runs-id]");
    if (runs) { refreshRuns(runs.dataset.runsId); return; }
    if (event.target.closest("[data-reload]")) { location.reload(); return; }
    if (event.target.closest("[data-refresh]")) { refresh(); }
  });
  bootstrap().then(refresh).then(startPolling).catch(error => {
    if (error instanceof Error && error.message === "authentication_required") renderAuthenticationError();
    else renderDataError(error);
  });
}
