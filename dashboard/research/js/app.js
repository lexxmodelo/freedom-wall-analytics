/* Research dashboard controller. */
(async function () {
  const $ = (s) => document.querySelector(s);
  const modeSel = $("#mode-select");
  const univA = $("#univ-a");
  const univB = $("#univ-b");
  const summaryHost = $("#summary-table");
  const singleMode = $("#single-mode");
  const gridMode = $("#grid-mode");

  let summary = null;
  let activeUniv = null;
  let topicChart = null;
  let trendChart = null;

  PipelineViz.render($("#pipeline"), $("#pipeline-detail"));

  summary = await DashUtils.loadJSON("../data/_summary.json");
  const totalTs = $("#ts-total");
  if (totalTs) totalTs.textContent = summary.reduce((a, u) => a + u.post_count, 0).toLocaleString();
  renderSummaryTable();

  window.addEventListener("themechange", () => {
    if (activeUniv) {
      UMAPViz.render($("#umap-host"), activeUniv);
      renderTopicBars();
      renderTrends();
    }
  });

  for (const u of summary) {
    [univA, univB].forEach(sel => {
      const o = document.createElement("option");
      o.value = u.univ_code;
      o.textContent = `${u.univ_code} (${u.school_alias}) — VAD ${(u.vad_coverage*100).toFixed(0)}%`;
      sel.appendChild(o);
    });
  }
  // Default active = highest-coverage univ
  const best = summary.slice().sort((a, b) => b.vad_coverage - a.vad_coverage)[0];
  univA.value = (new URLSearchParams(location.search).get("a")) || best.univ_code;
  univB.value = summary.find(u => u.univ_code !== univA.value).univ_code;

  univA.addEventListener("change", () => loadActive());
  univB.addEventListener("change", () => maybeRenderCompareSecond());
  modeSel.addEventListener("change", onModeChange);

  await loadActive();
  onModeChange();

  function onModeChange() {
    const m = modeSel.value;
    document.querySelectorAll(".compare-only").forEach(el => el.style.display = (m === "compare") ? "" : "none");
    if (m === "grid") {
      singleMode.style.display = "none";
      gridMode.style.display = "";
      renderGrid();
    } else {
      singleMode.style.display = "";
      gridMode.style.display = "none";
      maybeRenderCompareSecond();
    }
  }

  async function maybeRenderCompareSecond() {
    if (modeSel.value !== "compare") {
      $("#umap-host-b").innerHTML = "";
      return;
    }
    const u = await DashUtils.loadJSON(`../data/research/${univB.value}.json`);
    UMAPViz.render($("#umap-host-b"), u);
  }

  async function loadActive() {
    const code = univA.value;
    history.replaceState(null, "", `?a=${code}`);
    activeUniv = await DashUtils.loadJSON(`../data/research/${code}.json`);
    document.title = `${code} — Research View`;
    document.querySelectorAll(".summary-tbl tr").forEach(r => r.classList.toggle("active", r.dataset.code === code));
    $("#active-meta").textContent = `${activeUniv.post_count.toLocaleString()} posts · ${activeUniv.topic_count} topics · VAD ${(activeUniv.vad_coverage*100).toFixed(0)}%`;
    UMAPViz.render($("#umap-host"), activeUniv);
    renderTopicBars();
    renderTrends();
    renderSarcasm();
    renderBrowser();
  }

  function renderSummaryTable() {
    const maxPosts = Math.max(...summary.map(u => u.post_count));
    let html = `<table class="summary-tbl"><thead><tr>
      <th>Code</th><th>Alias</th><th>Region</th>
      <th class="num">Posts</th><th class="num">Topics</th>
      <th class="num">VAD %</th><th>Top topics</th>
    </tr></thead><tbody>`;
    for (const u of summary) {
      const w = (u.post_count / maxPosts) * 80;
      html += `<tr data-code="${u.univ_code}">
        <td><b>${u.univ_code}</b></td>
        <td>${u.school_alias}</td>
        <td>${u.region}</td>
        <td class="num"><span class="bar-bg"><span class="bar" style="width:${w}px;display:inline-block;"></span></span>${u.post_count.toLocaleString()}</td>
        <td class="num">${u.topic_count}</td>
        <td class="num">${(u.vad_coverage*100).toFixed(0)}</td>
        <td>${(u.topics_top3 || []).map(t => `<span class="tag">${escapeHtml(DashUtils.fmt.label(t, 24))}</span>`).join(" ")}</td>
      </tr>`;
    }
    html += "</tbody></table>";
    summaryHost.innerHTML = html;
    summaryHost.querySelectorAll("tr").forEach(tr => {
      tr.addEventListener("click", () => {
        univA.value = tr.dataset.code;
        loadActive();
      });
    });
  }

  function renderTopicBars() {
    if (topicChart) topicChart.destroy();
    const t = ChartsTheme.tokens();
    const sorted = [...activeUniv.topics].sort((a, b) => b.size - a.size);
    topicChart = new Chart($("#topic-bars"), {
      type: "bar",
      data: {
        labels: sorted.map(t => DashUtils.fmt.label(t.label, 22)),
        datasets: [{
          label: "Posts",
          data: sorted.map(t => t.size),
          backgroundColor: sorted.map(t => DashUtils.topicColor(t.id)),
          borderRadius: 6,
          borderSkipped: false,
          maxBarThickness: 18,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 500 },
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: t.border, drawBorder: false }, ticks: { color: t.muted, maxTicksLimit: 5 } },
          y: { grid: { display: false }, ticks: { color: t.text, font: { size: 11.5 } } },
        },
      },
    });
  }

  function renderTrends() {
    if (trendChart) trendChart.destroy();
    const t = ChartsTheme.tokens();
    const dayMap = new Map();
    for (const p of activeUniv.posts) {
      if (!p.ts || p.V == null) continue;
      const d = DashUtils.fmt.date(p.ts);
      if (!dayMap.has(d)) dayMap.set(d, []);
      dayMap.get(d).push(p);
    }
    const ctx = $("#trends-multi").getContext("2d");
    if (!dayMap.size) {
      ctx.font = "13px Inter, sans-serif"; ctx.fillStyle = t.muted;
      ctx.fillText("No VAD-scored posts to plot.", 12, 24);
      return;
    }
    const days = [...dayMap.keys()].sort();
    const all = DashUtils.dateRange(days[0], days[days.length - 1]);
    const meanFor = (k) => all.map(d => {
      const arr = dayMap.get(d) || [];
      return arr.length ? arr.reduce((s, p) => s + p[k], 0) / arr.length : null;
    });
    const C_V = "oklch(63% 0.18 28)";
    const C_A = "oklch(70% 0.13 60)";
    const C_D = "oklch(60% 0.16 280)";
    trendChart = new Chart($("#trends-multi"), {
      type: "line",
      data: {
        labels: all,
        datasets: [
          { label: "Valence",   data: DashUtils.rollingMean(meanFor("V"), 7), borderColor: C_V, fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 },
          { label: "Arousal",   data: DashUtils.rollingMean(meanFor("A"), 7), borderColor: C_A, fill: false, tension: 0.4, pointRadius: 0, borderWidth: 2 },
          { label: "Dominance", data: DashUtils.rollingMean(meanFor("D"), 7), borderColor: C_D, fill: false, tension: 0.4, pointRadius: 0, borderWidth: 2 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 500 },
        scales: {
          x: { ticks: { maxTicksLimit: 7, color: t.muted }, grid: { display: false } },
          y: { min: 1, max: 9, ticks: { stepSize: 2, color: t.muted }, grid: { color: t.border, drawBorder: false } },
        },
        plugins: {
          legend: { position: "top", align: "end", labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: "circle" } },
        },
      },
      plugins: [DashUtils.gradientFillPlugin],
    });
  }

  function renderSarcasm() {
    const list = $("#sarcasm-list");
    const items = (activeUniv.posts || []).filter(p => p.sarcasm).slice(0, 12);
    if (!items.length) {
      list.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1;">${activeUniv.vad_coverage === 0 ? "No VAD scores yet for this university." : "No sarcasm flags in this corpus."}</div>`;
      return;
    }
    list.innerHTML = items.map(p => {
      const t = activeUniv.topics.find(t => t.id === p.topic_id);
      const tl = t ? t.label : (p.topic_id === -1 ? "Noise" : `Topic ${p.topic_id}`);
      const text = escapeHtml(DashUtils.fmt.truncate(p.text, 200));
      const inferred = p.V <= 4 ? "Inferred true tone: negative" : p.V >= 7 ? "Inferred true tone: ironic praise" : "Inferred true tone: ambivalent";
      return `<div class="sarc-card">
        <div class="surface-line">${text}</div>
        <div class="inferred">${inferred} · V ${p.V} · A ${p.A} · D ${p.D}</div>
        <div class="meta"><span class="tag">${escapeHtml(DashUtils.fmt.label(tl, 24))}</span><span class="tag tag-sarc">sarcasm</span></div>
      </div>`;
    }).join("");
  }

  function renderBrowser() {
    PostBrowser.render($("#post-table"), activeUniv);
    const filterTopic = $("#filter-topic");
    filterTopic.innerHTML = `<option value="">All topics</option>` +
      [...activeUniv.topics].sort((a, b) => b.size - a.size).map(t => `<option value="${t.id}">${escapeHtml(DashUtils.fmt.label(t.label, 28))} (${t.size})</option>`).join("");
    const apply = () => {
      const n = PostBrowser.applyFilters({
        search: $("#search").value.trim(),
        topicId: filterTopic.value,
        sarcOnly: $("#filter-sarc").checked,
      });
      $("#browser-count").textContent = `${n.toLocaleString()} of ${activeUniv.post_count.toLocaleString()} posts`;
    };
    $("#search").oninput = apply;
    filterTopic.onchange = apply;
    $("#filter-sarc").onchange = apply;
    apply();
  }

  async function renderGrid() {
    const host = $("#grid-host");
    host.innerHTML = "<div class='empty-state' style='grid-column:1/-1;'>Loading…</div>";
    const out = [];
    for (const s of summary) {
      const u = await DashUtils.loadJSON(`../data/institutional/${s.univ_code}.json`);
      const cell = document.createElement("div");
      cell.className = "mini";
      cell.innerHTML = `
        <div class="title">${u.univ_code} · ${u.school_alias}</div>
        <div class="sub">${u.post_count.toLocaleString()} posts · VAD ${(u.vad_coverage*100).toFixed(0)}%</div>
        <div class="hm"></div>`;
      MiniHeatmap.render(cell.querySelector(".hm"), u);
      out.push(cell);
    }
    host.innerHTML = "";
    out.forEach(c => host.appendChild(c));
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
})();
