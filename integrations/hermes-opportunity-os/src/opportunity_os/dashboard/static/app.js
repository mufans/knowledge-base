export const routes = ["overview", "signals", "opportunities", "tasks", "reports", "monitoring"];
export const eventTypes = Object.freeze(["state.invalidated", "component.updated", "incident.firing", "incident.recovered"]);

const meta = {
  overview: ["总览", "SYSTEM OVERVIEW", "查看机会组合和运行健康。"],
  signals: ["信号与新鲜度", "SIGNALS", "保留广域信息和稳定性分层。"],
  opportunities: ["机会与实验", "OPPORTUNITIES", "跟踪方向、证据与最小实验。"],
  tasks: ["任务与调度", "OPENCLAW CRON", "本页只读；编辑与重跑由 OpenClaw 控制面完成。"],
  reports: ["报告", "REPORTS", "查看本机私有和知识库脱敏输出。"],
  monitoring: ["监控", "HEALTH", "只展示安全探针聚合结果。"],
};

function safe(value) { return String(value ?? "—").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[c]); }
function header(route, state) { const [title, eyebrow, detail] = meta[route]; return `<header class="page-header"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${detail}</p></div><div class="state-pill state-${safe(state)}">${safe(state)}</div></header>`; }
function metric(label, value, note) { return `<article class="metric-card"><span>${label}</span><strong>${safe(value)}</strong><small>${note}</small></article>`; }
function state(data) { const items = data.components ?? []; return items.length && items.every(item => item.status === "healthy") ? "healthy" : items.length ? "degraded" : "empty"; }

export function renderOverview(data = {}, current = state(data)) { const counts = data.opportunity_counts ?? {}; return `<div class="page" data-page="overview" data-state="${current}">${header("overview", current)}<section class="metrics">${metric("机会", counts.opportunities ?? 0, "私有机会池")}${metric("实验", counts.experiments ?? 0, "1–14 天")}${metric("技术状态", counts.tech_states ?? 0, "新鲜度跟踪")}</section><article class="panel"><h2>原生能力边界</h2><p>OpenClaw 负责 IM、Cron、网关与重启；Hermes 负责 Session、Memory、Skill 与自我改进审批。</p></article></div>`; }
export function renderSignals(data = {}, current = "empty") { return `<div class="page" data-page="signals" data-state="${current}">${header("signals", current)}<section class="metrics">${metric("广域采集", "≥ 80%", "防止信息茧房")}${metric("定向补充", "≤ 20%", "只增加不替代")}${metric("到期复核", data.overdue_tech_states ?? 0, "不自动判定失效")}</section></div>`; }
export function renderOpportunities(data = {}, current = "empty") { const counts = data.opportunity_counts ?? {}; return `<div class="page" data-page="opportunities" data-state="${current}">${header("opportunities", current)}<section class="metrics">${metric("机会", counts.opportunities ?? 0, "含正反证据")}${metric("Review", counts.reviews ?? 0, "周期性复盘")}</section></div>`; }
export function renderTasks(data = {}, current = "empty") { return `<div class="page" data-page="tasks" data-state="${current}">${header("tasks", current)}<article class="panel"><h2>OpenClaw 原生控制</h2><p>仪表盘仅通过固定命令读取 list/status/runs，不包含 Cron 写入代码。</p><a class="text-link" href="http://127.0.0.1:18789/" target="_blank" rel="noopener noreferrer">打开 OpenClaw Control UI →</a></article><article class="panel"><h2>Hermes 原生运维</h2><p>使用 <code>hermes -p opportunity-discovery dashboard</code> 处理 Session、Memory、Skill 与审批。</p></article></div>`; }
export function renderReports(data = {}, current = "empty") { return `<div class="page" data-page="reports" data-state="${current}">${header("reports", current)}<article class="panel"><h2>报告分层</h2><p>详细内容保留在私有状态，知识库只接收脱敏版本。</p></article></div>`; }
export function renderMonitoring(data = {}, current = state(data)) { const cards = (data.components ?? []).map(item => `<article class="component-card"><strong>${safe(item.component)}</strong><small>${safe(item.status)} · ${safe(item.duration_ms)} ms</small></article>`).join(""); return `<div class="page" data-page="monitoring" data-state="${current}">${header("monitoring", current)}<section class="component-grid">${cards || "<p>等待探针结果。</p>"}</section><p>OpenClaw 原生 Cron failure alert 和钉钉通道负责错误通知。</p></div>`; }

const renderers = {overview: renderOverview, signals: renderSignals, opportunities: renderOpportunities, tasks: renderTasks, reports: renderReports, monitoring: renderMonitoring};
let snapshot = {}; let connected = false; let source; let delay = 1000; let timer; let lastEventId = "";
function route() { const value = location.hash.slice(1); return routes.includes(value) ? value : "overview"; }
function render(focus = false) { const main = document.querySelector("#main-content"); const current = connected ? state(snapshot) : "disconnected"; main.innerHTML = renderers[route()](snapshot, current); main.setAttribute("aria-busy", "false"); document.querySelectorAll("[data-route]").forEach(link => link.toggleAttribute("aria-current", link.dataset.route === route())); if (focus) main.focus({preventScroll:true}); }
async function refresh() { const response = await fetch("/api/v1/status", {credentials:"same-origin", headers:{Accept:"application/json"}}); if (!response.ok) throw new Error("status"); snapshot = await response.json(); connected = true; render(); }
function reconnect() { clearTimeout(timer); timer = setTimeout(connect, delay); delay = Math.min(delay * 2, 30000); }
function connect() { const url = new URL("/api/v1/events", location.origin); if (lastEventId) url.searchParams.set("last_event_id", lastEventId); source = new EventSource(url, {withCredentials:true}); eventTypes.forEach(type => source.addEventListener(type, event => { lastEventId = event.lastEventId || lastEventId; refresh().catch(reconnect); })); source.onopen = () => { delay = 1000; connected = true; render(); }; source.onerror = () => { source.close(); connected = false; render(); reconnect(); }; }
async function bootstrap() { const token = new URLSearchParams(location.hash.slice(1)).get("bootstrap"); if (!token) return; history.replaceState(null, "", `${location.pathname}#overview`); const response = await fetch("/auth/local/exchange", {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"}, body:JSON.stringify({token})}); if (!response.ok) throw new Error("bootstrap"); }
if (typeof window !== "undefined") { window.addEventListener("hashchange", () => render(true)); bootstrap().then(refresh).then(connect).catch(reconnect); }
