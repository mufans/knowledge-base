export const routes = ["overview", "signals", "opportunities", "tasks", "reports", "monitoring"];
export const eventTypes = Object.freeze(["state.invalidated", "component.updated"]);

const meta = {
  overview: ["总览", "SYSTEM OVERVIEW", "查看机会组合和运行健康。"],
  signals: ["信号与新鲜度", "SIGNALS", "保留广域信息和稳定性分层。"],
  opportunities: ["机会与实验", "OPPORTUNITIES", "跟踪方向、证据与最小实验。"],
  tasks: ["任务与调度", "OPENCLAW CRON", "本页只读；编辑与重跑由 OpenClaw 控制面完成。"],
  reports: ["报告", "REPORTS", "查看本机私有和知识库脱敏输出。"],
  monitoring: ["监控", "HEALTH", "只展示安全探针聚合结果。"],
};

function safe(value) { return String(value ?? "—").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[c]); }
function header(routeName, current) { const [title, eyebrow, detail] = meta[routeName]; return `<header class="page-header"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${detail}</p></div><div class="state-pill state-${safe(current)}">${safe(current)}</div></header>`; }
function metric(label, value, note) { return `<article class="metric-card"><span>${label}</span><strong>${safe(value)}</strong><small>${note}</small></article>`; }
function healthState(data) { const items = data.components ?? []; return items.length && items.every(item => item.status === "healthy") ? "healthy" : items.length ? "degraded" : "empty"; }

export function renderOverview(data = {}, current = healthState(data)) { const counts = data.opportunity_counts ?? {}; return `<div class="page" data-page="overview" data-state="${current}">${header("overview", current)}<section class="metrics">${metric("机会", counts.opportunities ?? 0, "私有机会池")}${metric("实验", counts.experiments ?? 0, "1–14 天")}${metric("技术状态", counts.tech_states ?? 0, "新鲜度跟踪")}</section><article class="panel"><h2>原生能力边界</h2><p>OpenClaw 负责 IM、Cron、网关与重启；Hermes 负责 Session、Memory、Skill 与自我改进审批。</p></article></div>`; }
export function renderSignals(data = {}, current = "empty") { return `<div class="page" data-page="signals" data-state="${current}">${header("signals", current)}<section class="metrics">${metric("广域采集", "≥ 80%", "防止信息茧房")}${metric("定向补充", "≤ 20%", "只增加不替代")}${metric("到期复核", data.overdue_tech_states ?? 0, "不自动判定失效")}</section></div>`; }
export function renderOpportunities(data = {}, current = "empty") { const counts = data.opportunity_counts ?? {}; return `<div class="page" data-page="opportunities" data-state="${current}">${header("opportunities", current)}<section class="metrics">${metric("机会", counts.opportunities ?? 0, "含正反证据")}${metric("Review", counts.reviews ?? 0, "周期性复盘")}</section></div>`; }

function taskRows(data) {
  if (data.loading) return "<p>正在读取 OpenClaw Cron…</p>";
  if (data.error) return `<p class="error-state">暂时无法读取：${safe(data.error)}</p>`;
  if (!data.jobs.length) return "<p>暂无 Cron 任务。</p>";
  return `<div class="task-list">${data.jobs.map(job => {
    const runs = data.runs[job.job_id];
    const schedule = job.cron ? `${safe(job.cron)} · ${safe(job.tz)}` : "非 cron 原生调度";
    const runLabel = runs?.loading ? "读取中…" : runs?.error ? "记录不可用" : runs ? `最近 ${safe(runs.run_count ?? "?")} 次` : "查看运行次数";
    return `<article class="panel"><h3>${safe(job.job_id)}</h3><p>${job.enabled ? "已启用" : "已停用"} · ${schedule}</p><button type="button" data-runs-id="${safe(job.job_id)}">${runLabel}</button></article>`;
  }).join("")}</div>`;
}

export function renderTasks(data = {jobs: [], runs: {}}, current = "empty") {
  const status = data.status;
  const scheduler = status ? (status.scheduler_enabled ? "调度器已启用" : "调度器未启用") : "调度器状态未知";
  const count = status?.job_count ?? data.jobs?.length ?? 0;
  return `<div class="page" data-page="tasks" data-state="${current}">${header("tasks", current)}<section class="metrics">${metric("调度器", scheduler, "OpenClaw 原生状态")}${metric("任务数", count, "只读列表")}</section>${taskRows(data)}<article class="panel"><h2>OpenClaw 原生控制</h2><p>修改、启停和立即运行仅在原生控制面完成。</p><a class="text-link" href="http://127.0.0.1:18789/" target="_blank" rel="noopener noreferrer">打开 OpenClaw Control UI →</a></article><article class="panel"><h2>Hermes 原生运维</h2><p>使用 <code>hermes -p opportunity-discovery dashboard</code> 处理 Session、Memory、Skill 与审批。</p></article></div>`;
}

export function renderReports(data = {}, current = "empty") { return `<div class="page" data-page="reports" data-state="${current}">${header("reports", current)}<article class="panel"><h2>报告分层</h2><p>详细内容保留在私有状态，知识库只接收脱敏版本。</p></article></div>`; }
export function renderMonitoring(data = {}, current = healthState(data)) { const cards = (data.components ?? []).map(item => `<article class="component-card"><strong>${safe(item.component)}</strong><small>${safe(item.status)} · ${safe(item.duration_ms)} ms</small></article>`).join(""); return `<div class="page" data-page="monitoring" data-state="${current}">${header("monitoring", current)}<section class="component-grid">${cards || "<p>等待探针结果。</p>"}</section><p>OpenClaw 原生 Cron failure alert 和钉钉通道负责错误通知。</p></div>`; }

const renderers = {overview: renderOverview, signals: renderSignals, opportunities: renderOpportunities, reports: renderReports, monitoring: renderMonitoring};
let snapshot = {};
let taskData = {status: null, jobs: [], runs: {}, loading: false, error: null};
let connected = false;
let source;
let delay = 1000;
let timer;
let lastEventId = "";
function route() { const value = location.hash.slice(1); return routes.includes(value) ? value : "overview"; }
function render(focus = false) { const main = document.querySelector("#main-content"); const current = connected ? healthState(snapshot) : "disconnected"; main.innerHTML = route() === "tasks" ? renderTasks(taskData, current) : renderers[route()](snapshot, current); main.setAttribute("aria-busy", "false"); document.querySelectorAll("[data-route]").forEach(link => link.toggleAttribute("aria-current", link.dataset.route === route())); if (focus) main.focus({preventScroll:true}); }
async function jsonResponse(response, label) { if (!response.ok) throw new Error(label); return response.json(); }
async function refreshTasks() {
  taskData = {...taskData, loading: true, error: null}; render();
  try {
    const [jobsResponse, statusResponse] = await Promise.all([
      fetch("/api/v1/tasks", {credentials:"same-origin", headers:{Accept:"application/json"}}),
      fetch("/api/v1/tasks/status", {credentials:"same-origin", headers:{Accept:"application/json"}}),
    ]);
    const [jobs, status] = await Promise.all([jsonResponse(jobsResponse, "task_list"), jsonResponse(statusResponse, "task_status")]);
    taskData = {...taskData, jobs, status, loading: false, error: null};
  } catch (error) {
    taskData = {...taskData, loading: false, error: error instanceof Error ? error.message : "task_read_failed"};
  }
  render();
}
async function refreshRuns(jobId) {
  taskData = {...taskData, runs: {...taskData.runs, [jobId]: {loading: true}}}; render();
  try {
    const response = await fetch(`/api/v1/tasks/${encodeURIComponent(jobId)}/runs`, {credentials:"same-origin", headers:{Accept:"application/json"}});
    const runs = await jsonResponse(response, "task_runs");
    taskData = {...taskData, runs: {...taskData.runs, [jobId]: runs}};
  } catch (error) {
    taskData = {...taskData, runs: {...taskData.runs, [jobId]: {error: error instanceof Error ? error.message : "task_runs_failed"}}};
  }
  render();
}
async function refresh() { const response = await fetch("/api/v1/status", {credentials:"same-origin", headers:{Accept:"application/json"}}); snapshot = await jsonResponse(response, "status"); connected = true; render(); if (route() === "tasks") await refreshTasks(); }
function reconnect() { clearTimeout(timer); timer = setTimeout(connect, delay); delay = Math.min(delay * 2, 30000); }
function connect() { const url = new URL("/api/v1/events", location.origin); if (lastEventId) url.searchParams.set("last_event_id", lastEventId); source = new EventSource(url, {withCredentials:true}); eventTypes.forEach(type => source.addEventListener(type, event => { lastEventId = event.lastEventId || lastEventId; refresh().catch(reconnect); })); source.onopen = () => { delay = 1000; connected = true; render(); }; source.onerror = () => { source.close(); connected = false; render(); reconnect(); }; }
async function bootstrap() { const token = new URLSearchParams(location.hash.slice(1)).get("bootstrap"); if (!token) return; history.replaceState(null, "", `${location.pathname}#overview`); const response = await fetch("/auth/local/exchange", {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"}, body:JSON.stringify({token})}); if (!response.ok) throw new Error("bootstrap"); }
if (typeof window !== "undefined") {
  window.addEventListener("hashchange", () => { render(true); if (route() === "tasks") refreshTasks(); });
  window.addEventListener("click", event => { const button = event.target.closest("[data-runs-id]"); if (button) refreshRuns(button.dataset.runsId); });
  bootstrap().then(refresh).then(connect).catch(reconnect);
}
