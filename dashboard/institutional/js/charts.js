/* Chart factories. Terminology is plain-English (Positivity / Intensity / Control)
   even though the underlying data still uses V/A/D keys. Charts are theme-aware via
   ChartsTheme.tokens() and react to themechange via Chart.update / Plotly.relayout —
   no full redraw, no random re-jittering. */
window.InstCharts = (function () {
  let topicChart = null;
  let trendChart = null;
  let keywordsChart = null;

  /* Body-attached HTML tooltip for the donut. Escapes the donut-wrap clip
     box so long topic labels aren't truncated, and stays clear of the
     center "N posts" callout by clamping itself to the viewport. */
  function ensureDonutTooltipEl() {
    let el = document.getElementById("donut-tooltip");
    if (el) return el;
    el = document.createElement("div");
    el.id = "donut-tooltip";
    el.className = "donut-tooltip";
    el.setAttribute("role", "tooltip");
    el.style.cssText = "position:fixed;pointer-events:none;opacity:0;transition:opacity 120ms;z-index:1000;";
    document.body.appendChild(el);
    return el;
  }
  function makeDonutTooltipExternal(canvas, sorted, data) {
    return (ctx) => {
      const tip = ensureDonutTooltipEl();
      const tt = ctx.tooltip;
      if (!tt || tt.opacity === 0) {
        tip.style.opacity = "0";
        return;
      }
      const i = tt.dataPoints?.[0]?.dataIndex;
      if (i == null) return;
      const t = sorted[i];
      const total = data.reduce((a, b) => a + b, 0);
      const pct = ((t.size / total) * 100).toFixed(1);
      const v = t.mean_V == null ? "—" : t.mean_V.toFixed(2);
      tip.innerHTML = `
        <div class="dt-title">${escapeForTooltip(t.label)}</div>
        <div class="dt-row"><span>${t.size.toLocaleString()} posts</span><span>${pct}%</span></div>
        <div class="dt-row"><span>Positivity</span><span>${v}</span></div>`;
      tip.style.opacity = "1";

      /* Position in viewport coordinates near the cursor, clamped to screen. */
      const rect = canvas.getBoundingClientRect();
      const px = rect.left + tt.caretX;
      const py = rect.top + tt.caretY;
      tip.style.left = "0px"; tip.style.top = "0px";
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      const margin = 8;
      let x = px + 12, y = py - th - 12;
      if (x + tw > window.innerWidth - margin) x = px - tw - 12;
      if (y < margin) y = py + 16;
      tip.style.left = x + "px";
      tip.style.top  = y + "px";
    };
  }
  function escapeForTooltip(s) {
    return String(s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  /* ── Topic donut + external legend ─────────────────────────── */
  function topicDistribution(canvas, topics, totalNumEl, legendHostEl, onClickTopic, activeTopicId) {
    if (topicChart) topicChart.destroy();
    /* Sort by post volume (largest first) so the legend mirrors what the
       admin actually wants to scan: biggest conversations on top. */
    const sorted = [...topics].sort((a, b) => b.size - a.size);
    const data = sorted.map(t => t.size);
    const colors = sorted.map(t => DashUtils.topicColor(t.id));
    if (totalNumEl) totalNumEl.textContent = data.reduce((a, b) => a + b, 0).toLocaleString();
    topicChart = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: sorted.map(t => t.label),
        datasets: [{
          data, backgroundColor: colors, borderColor: ChartsTheme.tokens().surface,
          borderWidth: 2, hoverOffset: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        cutout: "75%",
        animation: { duration: 600, easing: "easeOutQuart" },
        plugins: {
          legend: { display: false },
          tooltip: {
            enabled: false,
            external: makeDonutTooltipExternal(canvas, sorted, data),
          },
        },
        onClick: (_, els) => {
          if (!els.length) return;
          onClickTopic(sorted[els[0].index].id);
        },
      },
    });

    if (legendHostEl) {
      legendHostEl.innerHTML = "";
      const hasSelection = activeTopicId != null;
      legendHostEl.classList.toggle("has-selection", hasSelection);
      const total = data.reduce((a, b) => a + b, 0);

      /* Tiny header so admins know the trailing pill is "Avg Positivity"
         on a 1–9 scale, without us repeating that label on every row. */
      const header = document.createElement("div");
      header.className = "leg-head";
      header.innerHTML = `<span class="lh-topic">Topic</span><span class="lh-stats">Posts · Avg Positivity (1–9)</span>`;
      legendHostEl.appendChild(header);

      sorted.forEach((t, i) => {
        const pct = ((t.size / total) * 100).toFixed(1);
        const isActive = activeTopicId === t.id;
        const vColor = t.mean_V == null ? null : VADColors.valenceCalendar(t.mean_V);
        const vChip = t.mean_V == null
          ? `<span class="v-chip v-chip-empty">—</span>`
          : `<span class="v-chip" style="background:color-mix(in srgb, ${vColor} 18%, transparent);color:${vColor};">${t.mean_V.toFixed(1)}</span>`;
        const row = document.createElement("div");
        row.className = "leg-row" + (isActive ? " is-active" : "");
        row.dataset.topicId = String(t.id);
        row.setAttribute("role", "button");
        row.setAttribute("tabindex", "0");
        row.setAttribute("aria-pressed", isActive ? "true" : "false");
        row.innerHTML = `
          <span class="dot" style="background:${colors[i]}"></span>
          <div class="leg-body">
            <div class="name">${t.label}</div>
            <div class="leg-stats">
              <span class="count">${t.size.toLocaleString()} <span class="pct">${pct}%</span></span>
              ${vChip}
            </div>
          </div>`;
        row.addEventListener("click", () => onClickTopic(t.id));
        row.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClickTopic(t.id); }
        });
        legendHostEl.appendChild(row);
      });
    }
  }

  /* ── Daily Positivity Tracker (calendar heatmap) ─────────────── */
  function calendarHeatmap(host, posts) {
    host.innerHTML = "";
    const t = ChartsTheme.tokens();
    const dayMap = DashUtils.groupByDay(posts);
    if (!dayMap.size) {
      host.innerHTML = `<div class="empty-state">No date-stamped posts.</div>`;
      return;
    }
    const days = [...dayMap.keys()].sort();
    const allDays = DashUtils.dateRange(days[0], days[days.length - 1]);

    const cell = 13, gap = 3, leftPad = 36, topPad = 26;
    const startOffset = new Date(allDays[0] + "T00:00:00Z").getUTCDay();
    const totalCols = Math.ceil((startOffset + allDays.length) / 7);
    const W = leftPad + totalCols * (cell + gap) + 60;
    const H = topPad + 7 * (cell + gap) + 38;

    const svg = d3.create("svg")
      .attr("viewBox", `0 0 ${W} ${H}`)
      .attr("preserveAspectRatio", "xMinYMin meet")
      .style("width", "100%").style("height", "auto");

    const dayShort = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
    [1, 3, 5].forEach(i => {
      svg.append("text")
        .attr("class", "heatmap-day-label")
        .attr("x", 0).attr("y", topPad + i * (cell + gap) + 10)
        .text(dayShort[i]);
    });

    const tip = DashUtils.tooltip();
    const todayDate = DashUtils.fmt.date(Date.now() / 1000);
    let currentMonth = -1;
    allDays.forEach((d, idx) => {
      const dt = new Date(d + "T00:00:00Z");
      const ord = startOffset + idx;
      const col = Math.floor(ord / 7);
      const row = ord % 7;
      const x = leftPad + col * (cell + gap);
      const y = topPad + row * (cell + gap);
      const arr = dayMap.get(d) || [];
      const scored = arr.filter(p => p.V != null);
      const meanV = scored.length ? scored.reduce((s, p) => s + p.V, 0) / scored.length : null;
      const fill = arr.length === 0 ? t.border : (meanV == null ? t.borderStrong : VADColors.valenceCalendar(meanV));
      svg.append("rect")
        .attr("class", "heatmap-cell" + (d === todayDate ? " heatmap-today" : ""))
        .attr("x", x).attr("y", y).attr("width", cell).attr("height", cell)
        .attr("rx", 2).attr("fill", fill)
        .on("mouseenter", (ev) => {
          const top = arr.length ? arr.reduce((m, p) => {
            m[p.topic_id] = (m[p.topic_id] || 0) + 1;
            return m;
          }, {}) : null;
          let topLabel = "—";
          if (top) {
            const tid = +Object.entries(top).sort((a, b) => b[1] - a[1])[0][0];
            const topic = (window.__InstUniv?.topics || []).find(tt => tt.id === tid);
            topLabel = topic ? topic.label : `Topic ${tid}`;
          }
          tip.show(`<b>${d}</b><br>${arr.length} posts · positivity ${meanV == null ? "—" : meanV.toFixed(2)}<br>top topic: ${topLabel}`, ev);
        })
        .on("mousemove", (ev) => tip.move(ev))
        .on("mouseleave", () => tip.hide());

      if (dt.getUTCMonth() !== currentMonth && (dt.getUTCDate() <= 7 || idx === 0)) {
        currentMonth = dt.getUTCMonth();
        svg.append("text")
          .attr("class", "heatmap-month-label")
          .attr("x", x).attr("y", topPad - 10)
          .text(dt.toLocaleString("en", { month: "short" }));
      }
    });

    const legendY = topPad + 7 * (cell + gap) + 22;
    const stops = [
      ["No posts",  t.border],
      ["Negative",  "oklch(60% 0.20 22)"],
      ["Mixed",     "oklch(78% 0.13 70)"],
      ["Positive",  "oklch(65% 0.14 155)"],
    ];
    let lx = leftPad;
    stops.forEach(([label, c]) => {
      svg.append("rect").attr("x", lx).attr("y", legendY).attr("width", 11).attr("height", 11).attr("rx", 2).attr("fill", c);
      svg.append("text").attr("class", "heatmap-legend").attr("x", lx + 16).attr("y", legendY + 9.5).text(label);
      lx += 88;
    });

    host.appendChild(svg.node());
  }

  /* ── Emotion Scatter Plot ────────────────────────────────────
     Jitter is pre-computed on each post (`p._jx`, `p._jy`) at data load —
     we never call Math.random in render, so theme toggle keeps positions stable. */
  function vadBubble(host, posts, opts = {}) {
    const t = ChartsTheme.tokens();
    const scored = posts.filter(p => p.V != null);
    if (!scored.length) {
      host.innerHTML = `<div class="empty-state">No emotion-scored posts. Charts will appear once scoring completes.</div>`;
      return;
    }
    const sample = scored.length > 1500 ? d3.shuffle(scored.slice()).slice(0, 1500) : scored;
    const grouped = d3.group(sample, p => p.topic_id);
    const traces = [];
    for (const [tid, arr] of grouped) {
      const topic = (window.__InstUniv?.topics || []).find(tt => tt.id === tid);
      const label = topic ? topic.label : (tid === -1 ? "Noise" : `Topic ${tid}`);
      const dotColor = DashUtils.topicColor(tid);
      traces.push({
        type: "scattergl", mode: "markers", name: label,
        x: arr.map(p => p.A + (p._jx ?? 0)),
        y: arr.map(p => p.D + (p._jy ?? 0)),
        customdata: arr.map(p => p.post_id),
        /* Compact two-line tooltip: topic name on top with a colored chip,
           three scores on a muted second line. The full post text only
           shows up in the right-hand inspector when a dot is clicked. */
        text: arr.map(p =>
          `<span style="color:${dotColor};font-size:13px">●</span> <b style="font-size:12.5px">${label.replace(/[<>]/g, "")}</b>` +
          (p.sarcasm ? `  <span style="color:#f0abfc;font-size:11px">· sarcasm</span>` : "") +
          `<br><span style="color:#9ca3af;font-size:11.5px">Intensity ${p.A} · Control ${p.D} · Positivity ${p.V}</span>` +
          `<br><span style="color:#6b7280;font-size:10.5px;font-style:italic">click to pin full post →</span>`
        ),
        hovertemplate: "%{text}<extra></extra>",
        marker: {
          size: arr.map(p => 3 + p.V * 0.85),
          color: dotColor,
          opacity: 0.5,
          line: { width: 0 },
        },
      });
    }
    const defaults = ChartsTheme.plotlyDefaults();
    /* Quadrant interpretation (matches the data: x=Intensity 0–9 calm→stressed,
       y=Control 0–9 helpless→empowered):
         top-right  (stressed + empowered) → engaged / motivated
         top-left   (calm    + empowered) → content / in control
         bottom-left  (calm    + helpless)  → withdrawn / quiet
         bottom-right (stressed + helpless)  → CRISIS ZONE (shaded). */
    const layout = Object.assign({}, defaults, {
      /* Vertical legend needs ~180px of right gutter so the topic names fit. */
      margin: opts.verticalLegend ? { l: 50, r: 200, t: 16, b: 50 } : { l: 50, r: 16, t: 16, b: 50 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      xaxis: Object.assign({}, defaults.xaxis, {
        title: { text: "Intensity (calm → stressed)", font: { size: 11, color: t.muted } },
        range: [0.3, 9.7], dtick: 2, griddash: "dot", gridcolor: t.border, zeroline: false,
      }),
      yaxis: Object.assign({}, defaults.yaxis, {
        title: { text: "Sense of Control (helpless → empowered)", font: { size: 11, color: t.muted } },
        range: [0.3, 9.7], dtick: 2, griddash: "dot", gridcolor: t.border, zeroline: false,
      }),
      /* Legend orientation: bottom-horizontal by default to match the
         narrow page-level card. The modal expand passes opts.verticalLegend
         to flip it to a side panel, freeing up vertical chart space. */
      legend: opts.verticalLegend
        ? { font: { size: 11, color: t.muted }, orientation: "v", x: 1.02, y: 1, xanchor: "left", yanchor: "top" }
        : { font: { size: 10, color: t.muted }, orientation: "h", y: -0.18, x: 0 },
      /* Compact, dark, rounded tooltip — replaces the wide bar-of-death. */
      hoverlabel: {
        bgcolor: "#111827",
        bordercolor: "#111827",
        font: { color: "#f3f4f6", size: 12, family: "Inter, system-ui, sans-serif" },
        align: "left",
      },
      hovermode: "closest",
      shapes: [
        /* Crisis-zone shade (bottom-right: stressed + helpless). The shape
           sits behind the markers so dots stay readable. */
        { type: "rect", xref: "x", yref: "y",
          x0: 5, y0: 0.3, x1: 9.7, y1: 5,
          fillcolor: "rgba(220, 38, 38, 0.06)",
          line: { width: 0 }, layer: "below" },
        /* Crosshairs at 5/5 — solid + slightly darker so they read as
           real quadrant boundaries, not just gridlines. */
        { type: "line", xref: "x", yref: "y", x0: 5, x1: 5, y0: 0.3, y1: 9.7,
          line: { color: t.border, width: 1.5 }, layer: "below" },
        { type: "line", xref: "x", yref: "y", x0: 0.3, x1: 9.7, y0: 5, y1: 5,
          line: { color: t.border, width: 1.5 }, layer: "below" },
      ],
      /* Pin labels to the four corners of the *plot area* (paper coords)
         so they don't drift when the user zooms the data range. */
      annotations: [
        { xref: "paper", yref: "paper", x: 1, y: 1, text: "Engaged & motivated", showarrow: false,
          xanchor: "right", yanchor: "top", xshift: -10, yshift: -10,
          font: { size: 11, color: t.subtle } },
        { xref: "paper", yref: "paper", x: 0, y: 1, text: "Calm & in control", showarrow: false,
          xanchor: "left", yanchor: "top", xshift: 10, yshift: -10,
          font: { size: 11, color: t.subtle } },
        { xref: "paper", yref: "paper", x: 1, y: 0, text: "Stressed & helpless", showarrow: false,
          xanchor: "right", yanchor: "bottom", xshift: -10, yshift: 10,
          font: { size: 11, color: "rgba(220, 38, 38, 0.95)" } },
        { xref: "paper", yref: "paper", x: 0, y: 0, text: "Withdrawn & quiet", showarrow: false,
          xanchor: "left", yanchor: "bottom", xshift: 10, yshift: 10,
          font: { size: 11, color: t.subtle } },
      ],
    });
    /* scrollZoom = wheel/trackpad zoom; dragmode "pan" makes the default
       click-drag a pan (more natural than box-zoom). Box-zoom stays one
       click away in the modebar. */
    layout.dragmode = "pan";
    Plotly.react(host, traces, layout, {
      displaylogo: false,
      responsive: true,
      scrollZoom: true,
      displayModeBar: "hover",
      modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toImage"],
    });
    /* Plotly samples container size during render. When the chart lives in
       a flex container that hasn't fully resolved (e.g. inside a freshly
       opened <dialog>), the captured size can be far smaller than the
       final layout. Schedule a few staggered Plots.resize calls so we
       catch up after the browser finishes its layout pass. */
    [50, 200, 600].forEach(ms => setTimeout(() => {
      try { Plotly.Plots.resize(host); } catch (_) { /* host may have been replaced */ }
    }, ms));
    /* Stash the host so the page-level Reset View button can find it. */
    host.__hasReset = true;
    if (opts.onClickPoint) {
      host.removeAllListeners && host.removeAllListeners("plotly_click");
      host.on("plotly_click", (ev) => {
        const pid = ev.points && ev.points[0] && ev.points[0].customdata;
        if (pid) opts.onClickPoint(pid);
      });
    }
  }

  /* Theme-only update for the bubble — no redraw, just relayout colors. Preserves jitter.
     Annotation index 2 is the "Stressed & helpless" danger label and stays red regardless
     of theme; the crosshair shapes (indices 1 & 2) repaint to the active border colour. */
  function vadBubbleRelayoutTheme(host) {
    if (!host || !host.layout) return;
    const t = ChartsTheme.tokens();
    Plotly.relayout(host, {
      "xaxis.gridcolor": t.border,
      "yaxis.gridcolor": t.border,
      "xaxis.color": t.muted,
      "yaxis.color": t.muted,
      "xaxis.title.font.color": t.muted,
      "yaxis.title.font.color": t.muted,
      "legend.font.color": t.muted,
      "annotations[0].font.color": t.subtle,
      "annotations[1].font.color": t.subtle,
      "annotations[3].font.color": t.subtle,
      "shapes[1].line.color": t.border,
      "shapes[2].line.color": t.border,
    });
  }

  /* ── Emotional Trends over Time ──────────────────────────────────
     Mixed chart: rolling-mean lines on the primary axis, daily post-volume
     bars on a secondary axis below. The volume bars give admins a clear
     read of where the lines are confident (lots of posts) vs sparse
     (vacation, scraper down). All days in the corpus date range are
     present on the x-axis — no visual gaps to misinterpret. */
  function trends(canvas, posts, windowDays = 14, opts = {}) {
    if (trendChart) trendChart.destroy();
    const t = ChartsTheme.tokens();
    /* Build day map across ALL posts (not just scored), so the volume bars
       reflect activity even when emotion scoring is incomplete. */
    const allDayMap = DashUtils.groupByDay(posts);
    const scoredDayMap = DashUtils.groupByDay(posts.filter(p => p.V != null));
    if (!allDayMap.size) {
      const ctx = canvas.getContext("2d");
      ctx.font = "13px Inter, sans-serif"; ctx.fillStyle = t.muted;
      ctx.fillText("No date-stamped posts to plot.", 12, 24);
      return;
    }
    const days = [...allDayMap.keys()].sort();
    const all = DashUtils.dateRange(days[0], days[days.length - 1]);
    const meanFor = (key) => all.map(d => {
      const arr = scoredDayMap.get(d) || [];
      return arr.length ? arr.reduce((s, p) => s + p[key], 0) / arr.length : null;
    });
    const volumeData = all.map(d => (allDayMap.get(d) || []).length);
    const maxVolume = Math.max(1, ...volumeData);

    const C_V = "oklch(63% 0.18 28)";
    const C_A = "oklch(70% 0.13 60)";
    const C_D = "oklch(60% 0.16 280)";
    const C_VOL = "oklch(70% 0.04 280)";  // muted neutral so it sits BEHIND the lines

    /* Compute "low activity" zones — runs of days where volume is below 25%
       of the corpus median. Used to shade the chart so admins know not to
       read the line too literally there. */
    const median = (() => {
      const sorted = volumeData.filter(v => v > 0).slice().sort((a, b) => a - b);
      return sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    })();
    const lowThresh = Math.max(1, median * 0.25);
    const lowZones = [];
    let zoneStart = -1;
    for (let i = 0; i < volumeData.length; i++) {
      const isLow = volumeData[i] < lowThresh;
      if (isLow && zoneStart === -1) zoneStart = i;
      if (!isLow && zoneStart !== -1) {
        if (i - zoneStart >= 5) lowZones.push([zoneStart, i - 1]);
        zoneStart = -1;
      }
    }
    if (zoneStart !== -1 && volumeData.length - zoneStart >= 5) lowZones.push([zoneStart, volumeData.length - 1]);

    /* spanGaps: false — break the line where the rolling window has zero scored
       posts. The rolling mean already smooths over single-day gaps, so the line
     stays continuous over normal activity. It only breaks during genuine low-
     activity zones — making it visually obvious that no data exists there
     instead of misleading the eye with an interpolated line. */
    const datasets = [
      { type: "line", label: "Positivity", data: DashUtils.rollingMean(meanFor("V"), windowDays), borderColor: C_V, fill: true,  tension: 0.4, pointRadius: 0, borderWidth: 2, yAxisID: "y", order: 1, spanGaps: false },
      { type: "line", label: "Intensity",  data: DashUtils.rollingMean(meanFor("A"), windowDays), borderColor: C_A, fill: false, tension: 0.4, pointRadius: 0, borderWidth: 2, yAxisID: "y", order: 2, spanGaps: false },
      { type: "line", label: "Control",    data: DashUtils.rollingMean(meanFor("D"), windowDays), borderColor: C_D, fill: false, tension: 0.4, pointRadius: 0, borderWidth: 2, yAxisID: "y", order: 3, spanGaps: false },
      { type: "bar",  label: "Posts / day", data: volumeData, backgroundColor: C_VOL, borderWidth: 0, yAxisID: "y2", order: 10, barPercentage: 1.0, categoryPercentage: 0.95 },
    ];
    const datasetsToUse = opts.simple
      ? datasets.filter(d => d.label !== "Control")
      : datasets;
    if (!opts.withVolume) datasetsToUse.splice(datasetsToUse.findIndex(d => d.label === "Posts / day"), 1);

    /* Custom legend builder. Hides "Posts / day" (the bar series), then appends
       a synthetic swatch for the low-activity shading so it's properly part of
       the chart legend instead of free-floating text on the canvas. */
    function buildLegendLabels(chart) {
      const tokensNow = ChartsTheme.tokens();
      const defaults = Chart.defaults.plugins.legend.labels.generateLabels(chart);
      const out = defaults.filter(l => l.text !== "Posts / day");
      if (opts.withVolume && lowZones.length) {
        out.push({
          text: "Low activity (vacation / no scrape)",
          fillStyle: tokensNow.bgSubtle || "oklch(96% 0.008 30)",
          strokeStyle: tokensNow.borderStrong,
          lineWidth: 1,
          hidden: false,
          datasetIndex: -1,  // not bound to a dataset
        });
      }
      return out;
    }

    trendChart = new Chart(canvas, {
      data: { labels: all, datasets: datasetsToUse },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 600 },
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { ticks: { maxTicksLimit: 8 }, grid: { drawBorder: false } },
          y:  { position: "left",  min: 1, max: 9, ticks: { stepSize: 2 }, grid: { drawBorder: false }, title: { display: true, text: "Score (1-9)", font: { size: 10 } } },
          y2: { position: "right", min: 0, max: maxVolume * 4, ticks: { display: false }, grid: { display: false }, display: opts.withVolume !== false },
        },
        plugins: {
          legend: {
            position: "top", align: "end",
            labels: {
              boxWidth: 10, boxHeight: 10, padding: 10,
              usePointStyle: false,
              generateLabels: buildLegendLabels,
            },
            onClick(e, item, legend) {
              /* Clicks on the synthetic "Low activity" item should be no-ops */
              if (item.datasetIndex < 0) return;
              return Chart.defaults.plugins.legend.onClick.call(this, e, item, legend);
            },
          },
          tooltip: {
            mode: "index", intersect: false,
            callbacks: {
              label: (ctx) => {
                if (ctx.dataset.label === "Posts / day") return `${ctx.parsed.y} posts that day`;
                if (ctx.parsed.y == null) return null;
                return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}`;
              },
            },
          },
        },
      },
      plugins: [DashUtils.gradientFillPlugin, {
        id: "neutralLine",
        afterDraw(chart) {
          /* Read tokens FRESH on every draw so theme toggle picks up new colours
             without needing to rebuild the chart instance. */
          const tk = ChartsTheme.tokens();
          const { ctx, chartArea, scales } = chart;
          const y = scales.y.getPixelForValue(5);
          ctx.save();
          ctx.strokeStyle = tk.borderStrong;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(chartArea.left, y);
          ctx.lineTo(chartArea.right, y);
          ctx.stroke();
          ctx.restore();
        },
      }, {
        /* Shade long stretches of low activity. The label moved to the legend. */
        id: "lowActivityZones",
        beforeDatasetsDraw(chart) {
          if (!opts.withVolume) return;
          const { ctx, chartArea, scales } = chart;
          if (!lowZones.length) return;
          const tk = ChartsTheme.tokens();
          ctx.save();
          ctx.fillStyle = tk.bgSubtle || "oklch(96% 0.008 30 / 0.45)";
          for (const [a, b] of lowZones) {
            const x0 = scales.x.getPixelForValue(a);
            const x1 = scales.x.getPixelForValue(b);
            ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.bottom - chartArea.top);
          }
          ctx.restore();
        },
      }],
    });
  }

  /* ── Top Trending Keywords ───────────────────────────────────── */
  function keywords(canvas, posts, onClickKeyword, activeKeyword) {
    if (keywordsChart) keywordsChart.destroy();
    const t = ChartsTheme.tokens();
    const terms = DashUtils.termFreqWithValence(posts, 10);
    if (!terms.length) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.font = "13px Inter, sans-serif"; ctx.fillStyle = t.muted;
      ctx.fillText("Not enough text to extract terms.", 12, 24);
      return;
    }
    const labels = terms.map(t => t.word);
    const data = terms.map(t => t.count);
    const baseColors = terms.map(t => t.meanV == null ? t.borderStrong : VADColors.valenceWord(t.meanV));
    const colors = baseColors.map((c, i) => {
      if (activeKeyword == null) return c;
      return labels[i] === activeKeyword ? c : c + "55"; /* dim non-selected via alpha */
    });
    const borderColors = baseColors.map((c, i) =>
      activeKeyword != null && labels[i] === activeKeyword ? c : "transparent"
    );
    keywordsChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          data, backgroundColor: colors, borderColor: borderColors, borderWidth: 2,
          borderRadius: 6, borderSkipped: false, maxBarThickness: 22,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 500 },
        layout: { padding: { left: 4, right: 14 } },
        scales: {
          x: {
            grid: { color: t.border, drawBorder: false, lineWidth: 1 },
            ticks: { color: t.muted, maxTicksLimit: 5 },
          },
          y: { grid: { display: false }, ticks: { color: t.text, font: { size: 12.5, weight: 500 }, padding: 4 } },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const term = terms[ctx.dataIndex];
                const v = term.meanV == null ? "no scored posts" : `mean positivity ${term.meanV.toFixed(2)}`;
                const cta = onClickKeyword ? " · click to filter" : "";
                return `${term.count} mentions · ${v}${cta}`;
              },
            },
          },
        },
        onHover: (ev, els) => {
          if (!onClickKeyword) return;
          ev.native && (ev.native.target.style.cursor = els.length ? "pointer" : "default");
        },
        onClick: (_, els) => {
          if (!onClickKeyword || !els.length) return;
          onClickKeyword(labels[els[0].index]);
        },
      },
    });
  }

  return { topicDistribution, calendarHeatmap, vadBubble, vadBubbleRelayoutTheme, trends, keywords };
})();
