(() => {
  const dataset = window.__knowledge_home;
  const content = document.querySelector(".md-content__inner");
  const path = location.pathname;
  const isHome = path === "/" || path.endsWith("/index.html") || /\/knowledge-base\/?$/.test(path);
  if (!isHome || !content || !dataset?.articles) return;

  const escape = value => String(value ?? "").replace(/[&<>'"]/g, char => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]
  ));
  const labels = {concepts:"概念", entities:"实体", sources:"来源", syntheses:"综合"};
  const qualityLabels = {high:"高证据", medium:"中证据", low:"待补证"};
  const pageSize = 12;
  let page = 1;
  let query = "";
  let category = "all";
  let quality = "all";
  let topic = "all";

  const card = article => `<a class="kb-card" href="${escape(article.url)}">
    <div class="kb-card-head"><span class="kb-badge kb-quality-${escape(article.evidence_quality)}">${escape(qualityLabels[article.evidence_quality])}</span><time>${escape(article.date)}</time></div>
    <h3>${escape(article.title)}</h3><p>${escape(article.description)}</p>
    ${article.related?.length ? `<div class="kb-related">Related Knowledge · ${escape(article.related.slice(0,2).map(item => item.title).join(" / "))}</div>` : ""}
    <div class="kb-card-foot"><span class="kb-tag">${escape(labels[article.category])}</span>${(article.tags ?? []).slice(0,3).map(tag => `<span class="kb-tag">${escape(tag)}</span>`).join("")}</div>
  </a>`;

  const featured = dataset.articles.filter(item => item.category === "syntheses").slice(0, 3);
  const attention = dataset.articles.filter(item => item.date === dataset.today).slice(0, 3);
  const cross = dataset.articles.filter(item => item.agent_mobile).slice(0, 3);
  const counts = dataset.counts;
  content.innerHTML = `<div class="kb-home">
    <section class="kb-hero"><div><p class="kb-eyebrow">AI AGENT × MOBILE KNOWLEDGE</p><h1>值得追踪，而不是值得堆积</h1><p>按信息增量、证据质量与可执行性发现知识。没有新知识时，系统会安静地不发布。</p></div>
    <div class="kb-summary"><div><strong>${dataset.articles.length}</strong><span>知识页面</span></div><div><strong>${counts.syntheses}</strong><span>综合分析</span></div><div><strong>${dataset.articles.filter(item=>item.agent_mobile).length}</strong><span>Agent × Mobile</span></div><div><strong>${dataset.articles.filter(item=>item.evidence_quality==="high").length}</strong><span>高证据页面</span></div></div></section>
    <section class="kb-section"><div class="kb-section-head"><div><h2>今日值得关注</h2><p>为什么值得：新近更新、证据可追踪、与研究方向相关。</p></div></div><div class="kb-grid">${(attention.length ? attention : dataset.articles.slice(0,3)).map(card).join("")}</div></section>
    <section class="kb-section"><div class="kb-section-head"><div><h2>本周综合分析</h2><p>优先呈现跨来源共同点、冲突与行动建议。</p></div></div><div class="kb-grid">${featured.length ? featured.map(card).join("") : '<div class="kb-empty">本周暂无新的 synthesis；这是正常结果。</div>'}</div></section>
    <section class="kb-section"><div class="kb-section-head"><div><h2>Agent × Mobile 专题</h2><p>端侧 Agent、移动端工程与智能体架构的交叉知识。</p></div></div><div class="kb-grid">${cross.length ? cross.map(card).join("") : '<div class="kb-empty">正在积累交叉证据。</div>'}</div></section>
    <section class="kb-section"><div class="kb-section-head"><div><h2>学习路径</h2><p>从原理、实体到来源与综合判断。</p></div></div><div class="kb-learning"><div class="kb-path"><strong>Agent 架构</strong><span>概念 → OpenClaw / Hermes → 编排综合</span></div><div class="kb-path"><strong>移动端 AI</strong><span>端侧模型 → UI Agent → 工程验证</span></div><div class="kb-path"><strong>证据化研究</strong><span>来源 → 正反证据 → 最小实验</span></div></div></section>
    <section class="kb-section"><div class="kb-section-head"><div><h2>探索全部知识</h2><p>按主题、时间、来源类型和证据质量筛选；每页最多 ${pageSize} 项。</p></div></div>
      <div class="kb-controls"><input id="kb-query" type="search" placeholder="搜索标题、摘要或标签" aria-label="搜索知识">
      <select id="kb-category" aria-label="来源类型"><option value="all">全部类型</option>${Object.entries(labels).map(([value,label])=>`<option value="${value}">${label}</option>`).join("")}</select>
      <select id="kb-quality" aria-label="证据质量"><option value="all">全部证据质量</option><option value="high">高证据</option><option value="medium">中证据</option><option value="low">待补证</option></select>
      <select id="kb-topic" aria-label="研究主题"><option value="all">全部主题</option><option value="cross">Agent × Mobile</option><option value="actionable">含行动建议</option></select></div>
      <div class="kb-grid" id="kb-results"></div><div class="kb-pager"><button id="kb-prev" type="button">上一页</button><span id="kb-page"></span><button id="kb-next" type="button">下一页</button></div>
    </section></div>`;

  const filtered = () => dataset.articles.filter(item => {
    const haystack = `${item.title} ${item.description} ${(item.tags ?? []).join(" ")}`.toLowerCase();
    return (!query || haystack.includes(query))
      && (category === "all" || item.category === category)
      && (quality === "all" || item.evidence_quality === quality)
      && (topic === "all" || (topic === "cross" ? item.agent_mobile : item.actionable));
  });

  const render = () => {
    const items = filtered();
    const pages = Math.max(1, Math.ceil(items.length / pageSize));
    page = Math.min(page, pages);
    const visible = items.slice((page - 1) * pageSize, page * pageSize);
    document.querySelector("#kb-results").innerHTML = visible.length ? visible.map(card).join("") : '<div class="kb-empty">没有符合当前条件的页面。</div>';
    document.querySelector("#kb-page").textContent = `第 ${page} / ${pages} 页 · ${items.length} 项`;
    document.querySelector("#kb-prev").disabled = page === 1;
    document.querySelector("#kb-next").disabled = page === pages;
  };
  document.querySelector("#kb-query").addEventListener("input", event => { query = event.target.value.trim().toLowerCase(); page = 1; render(); });
  document.querySelector("#kb-category").addEventListener("change", event => { category = event.target.value; page = 1; render(); });
  document.querySelector("#kb-quality").addEventListener("change", event => { quality = event.target.value; page = 1; render(); });
  document.querySelector("#kb-topic").addEventListener("change", event => { topic = event.target.value; page = 1; render(); });
  document.querySelector("#kb-prev").addEventListener("click", () => { page -= 1; render(); });
  document.querySelector("#kb-next").addEventListener("click", () => { page += 1; render(); });
  render();
})();
