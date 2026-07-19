export const routes = [
  "overview", "conversations", "signals", "opportunities",
  "tasks", "approvals", "reports", "monitoring",
];

export const eventTypes = Object.freeze([
  "state.invalidated", "component.updated", "incident.firing", "incident.recovered",
  "conversation.started", "conversation.completed", "conversation.failed",
]);

const pageMeta = {
  overview: ["总览", "SYSTEM OVERVIEW", "掌握系统健康、机会组合与下一步行动。"],
  conversations: ["实时会话", "CONVERSATIONS", "在明确的数据边界内连接 OpenClaw 与 Hermes。"],
  signals: ["信号与新鲜度", "SIGNALS & FRESHNESS", "区分 known latest、recommended stable 与待复核信息。"],
  opportunities: ["机会与实验", "OPPORTUNITIES", "用有限容量维护 observe、validate 与 active 组合。"],
  tasks: ["任务与调度", "TASKS & SCHEDULES", "查看 Cron、时区、下一执行和最近结果。"],
  approvals: ["审批中心", "APPROVALS", "所有写操作先预览 Diff，再审批、验证与回滚。"],
  reports: ["报告", "REPORTS", "区分本机私有报告与知识库脱敏发布。"],
  monitoring: ["监控与审计", "MONITORING", "追踪探针、事故、投递和审计元数据。"],
};

const stateCopy = {
  empty: ["等待第一条数据", "系统已连接，当前视图暂无记录。"],
  healthy: ["运行正常", "数据来自刚刚完成的授权读取。"],
  degraded: ["部分能力降级", "仍可查看可用数据；请在监控页定位受影响组件。"],
  disconnected: ["连接已中断", "保留最后一次安全快照，正在指数退避重连。"],
};

function safe(value) {
  return String(value ?? "—").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function normalizedState(state) {
  return Object.hasOwn(stateCopy, state) ? state : "empty";
}

function pageHeader(route, state) {
  const current = normalizedState(state);
  const [title, eyebrow, description] = pageMeta[route];
  const [statusTitle, statusDetail] = stateCopy[current];
  return `<header class="page-header">
    <div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${description}</p></div>
    <div class="state-pill state-${current}"><span aria-hidden="true"></span>${statusTitle}</div>
  </header>
  <aside class="state-banner" data-state="${current}" aria-label="当前视图状态">
    <strong>${statusTitle}</strong><span>${statusDetail}</span>
  </aside>`;
}

function metric(label, value, note = "") {
  return `<article class="metric-card"><span>${label}</span><strong>${safe(value)}</strong><small>${note}</small></article>`;
}

function emptyPanel(title, text) {
  return `<section class="empty-panel"><span class="empty-glyph" aria-hidden="true">◇</span><h2>${title}</h2><p>${text}</p></section>`;
}

function componentState(data) {
  const components = Array.isArray(data?.components) ? data.components : [];
  if (!components.length) return "empty";
  return components.some(item => item.status !== "healthy") ? "degraded" : "healthy";
}

export function renderOverview(data = {}, state = componentState(data)) {
  const counts = data.opportunity_counts ?? {};
  const portfolio = data.portfolio_counts ?? {};
  const capacity = data.portfolio_capacity ?? {observe: 5, validate: 2, active: 1};
  return `<div class="page" data-page="overview" data-state="${normalizedState(state)}">${pageHeader("overview", state)}
    <section class="metrics" aria-label="关键指标">
      ${metric("机会", counts.opportunities ?? 0, "已进入私有机会池")}
      ${metric("实验", counts.experiments ?? 0, "1–14 天验证周期")}
      ${metric("待审批", data.pending_approvals ?? 0, "默认拒绝写入")}
      ${metric("活跃事故", data.active_incidents ?? 0, "去重后的事件")}
    </section>
    <section class="split-grid">
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">PORTFOLIO</p><h2>方向组合</h2></div><span>容量约束</span></div>
        <div class="capacity-row"><b>Observe</b><span>${safe(portfolio.observe ?? 0)} / ${safe(capacity.observe)}</span><progress value="${safe(portfolio.observe ?? 0)}" max="${safe(capacity.observe)}"></progress></div>
        <div class="capacity-row"><b>Validate</b><span>${safe(portfolio.validate ?? 0)} / ${safe(capacity.validate)}</span><progress value="${safe(portfolio.validate ?? 0)}" max="${safe(capacity.validate)}"></progress></div>
        <div class="capacity-row"><b>Active</b><span>${safe(portfolio.active ?? 0)} / ${safe(capacity.active)}</span><progress value="${safe(portfolio.active ?? 0)}" max="${safe(capacity.active)}"></progress></div>
      </article>
      <article class="panel"><div class="panel-heading"><div><p class="eyebrow">NEXT ACTION</p><h2>下一步</h2></div></div>
        <p class="large-copy">${normalizedState(state) === "empty" ? "等待首轮安全读取完成。" : "查看到期复核与降级组件，保持机会组合可执行。"}</p>
        <a class="text-link" href="#monitoring">打开监控与审计 →</a>
      </article>
    </section></div>`;
}

export function renderConversations(data = {}, state = "empty") {
  const task = data.conversation_task;
  const result = task?.result;
  const output = result?.final_text
    ? `<article class="panel" aria-live="polite"><p class="eyebrow">FINAL</p><h2>${safe(task.target)} 最终答复</h2><p class="large-copy">${safe(result.final_text)}</p><small>${safe(result.provider ?? "provider unknown")} · ${safe(result.model ?? "model unknown")} · token ${safe(result.token_status)} · cost ${safe(result.cost_status)}${result.truncated ? " · output truncated" : ""}</small></article>`
    : task
      ? `<article class="panel" aria-live="polite"><p class="eyebrow">TASK</p><h2>${safe(task.status)}</h2><p>任务 ${safe(task.task_id)} 只流转生命周期元数据。</p></article>`
      : emptyPanel("选择研究入口", "会话正文不会进入 SSE、初始 HTML 或浏览器存储。");
  return `<div class="page" data-page="conversations" data-state="${normalizedState(state)}">${pageHeader("conversations", state)}
    <section class="assistant-grid"><article class="assistant-card"><p class="eyebrow">OPENCLAW</p><h2>知识与系统助手</h2><p>查询知识库、任务和系统状态。</p><span>只读入口</span></article>
    <article class="assistant-card accent"><p class="eyebrow">HERMES</p><h2>机会研究员</h2><p>深度分析、方向复盘与历史 Session。</p><span>调用前预览边界</span></article></section>
    <section class="panel" aria-label="调用前边界"><p class="eyebrow">PREFLIGHT</p><h2>调用边界</h2>
      <p><strong>Hermes profile:</strong> opportunity-discovery · <strong>source: tool</strong> · <strong>skills: opportunity-discovery</strong></p>
      <p><strong>Provider / Model:</strong> 运行结果报告前均为 unknown · <strong>Cost status: unknown</strong></p>
      <p><strong>Data scope:</strong> 当前会话与 Opportunity OS 工具边界；不启用 messaging、delivery 或自动写入。</p>
    </section>
    <form id="conversation-form" class="panel" aria-label="提交安全会话">
      <label>研究入口<select name="target"><option value="openclaw">OpenClaw</option><option value="hermes">Hermes</option></select></label>
      <label>Session ID<input name="session_id" value="dashboard-main" maxlength="64" required></label>
      <label>消息<textarea name="message" maxlength="8192" required></textarea></label>
      <button type="submit">提交任务</button>
      <small>最多 8 KiB UTF-8；不启用消息投递或自动写入。</small>
    </form>${output}</div>`;
}

export function renderSignals(data = {}, state = "empty") {
  return `<div class="page" data-page="signals" data-state="${normalizedState(state)}">${pageHeader("signals", state)}
    <section class="metrics">${metric("广域采集", "≥ 80%", "保持反信息茧房")}${metric("定向补充", "≤ 20%", "只增加，不替换")}${metric("到期复核", data.overdue_tech_states ?? 0, "不自动判定失效")}</section>
    ${emptyPanel("尚无最新信号", "采集完成后按 known latest、recommended stable 和 surprise bucket 展示。")}</div>`;
}

export function renderOpportunities(data = {}, state = "empty") {
  const counts = data.opportunity_counts ?? {};
  return `<div class="page" data-page="opportunities" data-state="${normalizedState(state)}">${pageHeader("opportunities", state)}
    <section class="metrics">${metric("机会", counts.opportunities ?? 0, "七维确定性评分")}${metric("实验", counts.experiments ?? 0, "含继续/停止条件")}${metric("Review", counts.reviews ?? 0, "保留正反证据")}</section>
    ${emptyPanel("尚无候选机会", "新的候选会先进入 observe，验证后才占用 active 容量。")}</div>`;
}

export function renderTasks(data = {}, state = "empty") {
  return `<div class="page" data-page="tasks" data-state="${normalizedState(state)}">${pageHeader("tasks", state)}
    ${emptyPanel("暂无任务 DTO", "V1 只允许启停、Cron、时区和 run-now；Payload 与命令不可从网页修改。")}</div>`;
}

export function renderApprovals(data = {}, state = "empty") {
  return `<div class="page" data-page="approvals" data-state="${normalizedState(state)}">${pageHeader("approvals", state)}
    <section class="metrics">${metric("待审批", data.pending_approvals ?? 0, "Digest + ETag + nonce")}${metric("确认窗口", "5 分钟", "一次性 nonce")}${metric("默认策略", "拒绝", "失败自动回滚")}</section>
    ${emptyPanel("审批队列为空", "需要写入的变更会先显示结构化 Diff、影响范围与回滚点。")}</div>`;
}

export function renderReports(data = {}, state = "empty") {
  return `<div class="page" data-page="reports" data-state="${normalizedState(state)}">${pageHeader("reports", state)}
    <section class="report-lanes"><article class="panel"><p class="eyebrow">PRIVATE</p><h2>本机完整报告</h2><p>机会、实验与详细证据仅在授权后按需读取。</p></article>
    <article class="panel"><p class="eyebrow">PUBLIC SAFE</p><h2>知识库脱敏版</h2><p>只显示 Sanitizer 明确允许发布的聚合内容。</p></article></section></div>`;
}

export function renderMonitoring(data = {}, state = componentState(data)) {
  const components = Array.isArray(data.components) ? data.components : [];
  const cards = components.length ? components.map(item => `<article class="component-card"><span class="status-dot status-${safe(item.status)}"></span><div><strong>${safe(item.component)}</strong><small>${safe(item.status)} · ${safe(item.duration_ms)} ms</small></div></article>`).join("") : emptyPanel("等待探针结果", "超时首先标记 unknown，连续失败才进入 degraded 或 down。");
  return `<div class="page" data-page="monitoring" data-state="${normalizedState(state)}">${pageHeader("monitoring", state)}
    <section class="component-grid" aria-label="组件探针">${cards}</section></div>`;
}

const renderers = {
  overview: renderOverview,
  conversations: renderConversations,
  signals: renderSignals,
  opportunities: renderOpportunities,
  tasks: renderTasks,
  approvals: renderApprovals,
  reports: renderReports,
  monitoring: renderMonitoring,
};

let snapshot = {};
let connectionState = "disconnected";
let reconnectDelay = 1_000;
let reconnectTimer = null;
let source = null;
let lastEventId = "";
let csrfToken = "";
let conversationTask = null;

function currentRoute() {
  const route = window.location.hash.slice(1);
  return routes.includes(route) ? route : "overview";
}

function viewState(route) {
  if (connectionState === "disconnected") return "disconnected";
  if (["overview", "monitoring"].includes(route)) return componentState(snapshot);
  const counts = snapshot.opportunity_counts ?? {};
  const hasData = Object.values(counts).some(value => Number(value) > 0);
  return hasData ? componentState(snapshot) : "empty";
}

function renderCurrent({focus = false} = {}) {
  const route = currentRoute();
  const main = document.querySelector("#main-content");
  const data = route === "conversations" ? {...snapshot, conversation_task: conversationTask} : snapshot;
  main.innerHTML = renderers[route](data, viewState(route));
  main.setAttribute("aria-busy", "false");
  document.querySelectorAll("[data-route]").forEach(link => {
    if (link.dataset.route === route) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (focus) main.focus({preventScroll: true});
}

async function fetchSnapshot() {
  const response = await fetch("/api/v1/status", {
    credentials: "same-origin",
    headers: {Accept: "application/json"},
  });
  if (!response.ok) throw new Error(`status_${response.status}`);
  csrfToken = response.headers.get("X-CSRF-Token") || csrfToken;
  snapshot = await response.json();
  connectionState = "connected";
  renderCurrent();
  return snapshot;
}

export async function refreshOverview() {
  return fetchSnapshot();
}

export async function refreshMonitoring() {
  return fetchSnapshot();
}

async function refreshCurrent() {
  return fetchSnapshot();
}

export async function submitConversation(target, sessionId, message, csrf, fetchImpl = fetch) {
  if (!new Set(["openclaw", "hermes"]).has(target)) throw new Error("invalid_conversation_target");
  if (!message.trim() || new TextEncoder().encode(message).length > 8192) {
    throw new Error("invalid_conversation_message");
  }
  const response = await fetchImpl("/api/v1/conversations", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
    },
    body: JSON.stringify({target, session_id: sessionId, message}),
  });
  if (!response.ok) throw new Error(`conversation_${response.status}`);
  return response.json();
}

function validTaskPatch(patch) {
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) return false;
  const keys = Object.keys(patch).sort();
  if (keys.length === 1 && keys[0] === "enabled") return typeof patch.enabled === "boolean";
  return keys.length === 2
    && keys[0] === "cron"
    && keys[1] === "tz"
    && typeof patch.cron === "string"
    && patch.cron.trim().length > 0
    && typeof patch.tz === "string"
    && patch.tz.trim().length > 0;
}

async function postTaskControl(url, body, csrf, fetchImpl) {
  if (!csrf) throw new Error("csrf_required");
  const response = await fetchImpl(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`task_control_${response.status}`);
  return response.json();
}

export async function previewTaskChange(jobId, patch, baseRevision, csrf, fetchImpl = fetch) {
  if (!validTaskPatch(patch)) throw new Error("invalid_task_patch");
  return postTaskControl(
    `/api/v1/tasks/${encodeURIComponent(jobId)}/changes/preview`,
    {patch, base_revision: baseRevision},
    csrf,
    fetchImpl,
  );
}

export async function previewRunNow(jobId, baseRevision, csrf, fetchImpl = fetch) {
  return postTaskControl(
    `/api/v1/tasks/${encodeURIComponent(jobId)}/run-now/preview`,
    {base_revision: baseRevision},
    csrf,
    fetchImpl,
  );
}

export async function approveTaskChange(requestId, digest, nonce, csrf, fetchImpl = fetch) {
  return postTaskControl(
    `/api/v1/approvals/${encodeURIComponent(requestId)}/approve`,
    {digest, nonce},
    csrf,
    fetchImpl,
  );
}

export async function applyTaskChange(requestId, csrf, fetchImpl = fetch) {
  return postTaskControl(
    `/api/v1/approvals/${encodeURIComponent(requestId)}/apply`,
    {},
    csrf,
    fetchImpl,
  );
}

async function refreshConversationTask(taskId) {
  const response = await fetch(`/api/v1/conversations/${encodeURIComponent(taskId)}`, {
    credentials: "same-origin",
    headers: {Accept: "application/json"},
  });
  if (!response.ok) throw new Error(`conversation_task_${response.status}`);
  conversationTask = await response.json();
  if (currentRoute() === "conversations") renderCurrent();
  return conversationTask;
}

function conversationEvent(event) {
  rememberEvent(event);
  let payload;
  try {
    payload = JSON.parse(event.data);
  } catch (_) {
    markDisconnected();
    return;
  }
  if (typeof payload.task_id !== "string") return;
  refreshConversationTask(payload.task_id).catch(markDisconnected);
}

function rememberEvent(event) {
  if (event.lastEventId) lastEventId = event.lastEventId;
}

function attachEventHandlers(eventSource) {
  eventSource.addEventListener("bridge.unavailable", () => {
    eventSource.close();
    markDisconnected();
    scheduleReconnect();
  });
  eventSource.addEventListener("state.invalidated", event => {
    rememberEvent(event);
    refreshCurrent().catch(markDisconnected);
  });
  eventSource.addEventListener("component.updated", event => {
    rememberEvent(event);
    Promise.all([refreshOverview(), refreshMonitoring()]).catch(markDisconnected);
  });
  eventSource.addEventListener("incident.firing", event => {
    rememberEvent(event);
    Promise.all([refreshOverview(), refreshMonitoring()]).catch(markDisconnected);
  });
  eventSource.addEventListener("incident.recovered", event => {
    rememberEvent(event);
    Promise.all([refreshOverview(), refreshMonitoring()]).catch(markDisconnected);
  });
  eventSource.addEventListener("conversation.started", conversationEvent);
  eventSource.addEventListener("conversation.completed", conversationEvent);
  eventSource.addEventListener("conversation.failed", conversationEvent);
}

function markDisconnected() {
  connectionState = "disconnected";
  document.querySelector("#connection-label").textContent = "连接中断 · 正在重试";
  renderCurrent();
}

function scheduleReconnect() {
  window.clearTimeout(reconnectTimer);
  reconnectTimer = window.setTimeout(connectEvents, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, 30_000);
}

function connectEvents() {
  const url = new URL("/api/v1/events", window.location.origin);
  if (lastEventId) url.searchParams.set("last_event_id", lastEventId);
  source = new EventSource(url, {withCredentials: true});
  attachEventHandlers(source);
  source.onopen = () => {
    connectionState = "connected";
    reconnectDelay = 1_000;
    document.querySelector("#connection-label").textContent = "实时连接已加密";
    renderCurrent();
    refreshCurrent().catch(() => {
      source.close();
      markDisconnected();
      scheduleReconnect();
    });
  };
  source.onerror = () => {
    source.close();
    markDisconnected();
    scheduleReconnect();
  };
}

async function exchangeBootstrap() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("bootstrap");
  if (!token) return;
  history.replaceState(null, "", `${window.location.pathname}#overview`);
  const response = await fetch("/auth/local/exchange", {
    method: "POST",
    credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({token}),
  });
  if (!response.ok) throw new Error("bootstrap_failed");
  const session = await response.json();
  csrfToken = session.csrf_token;
}

function installNavigation() {
  window.addEventListener("hashchange", () => renderCurrent({focus: true}));
  document.addEventListener("submit", async event => {
    if (event.target?.id !== "conversation-form") return;
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const accepted = await submitConversation(
        String(form.get("target") ?? ""),
        String(form.get("session_id") ?? ""),
        String(form.get("message") ?? ""),
        csrfToken,
      );
      conversationTask = {task_id: accepted.task_id, target: String(form.get("target")), status: "queued"};
      renderCurrent();
    } catch (_) {
      conversationTask = {task_id: "unavailable", target: "conversation", status: "failed"};
      renderCurrent();
    }
  });
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  installNavigation();
}

async function start() {
  try {
    await exchangeBootstrap();
    if (!routes.includes(window.location.hash.slice(1))) window.location.hash = "overview";
    await refreshCurrent();
    connectEvents();
  } catch (_) {
    markDisconnected();
    reconnectTimer = window.setTimeout(start, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 30_000);
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  start();
}
