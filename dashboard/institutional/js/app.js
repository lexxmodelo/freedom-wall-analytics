/* Institutional dashboard controller — 4-page hash-routed SPA.
   - Pre-computes scatter jitter once per univ load (theme toggle never moves dots)
   - Theme listener uses Chart.js + Plotly relayout, never full re-render or data refetch
   - Single source of truth for global state (univ, topicFilter, dateRange, feedSort) */
(async function () {
  const $ = (s) => document.querySelector(s);

  /* ── State ─────────────────────────────────────────────────── */
  const state = {
    univ: null,
    topicFilter: null,
    keywordFilter: null,
    selectedPostId: null,
    dateRangeDays: null,
    feedSort: "newest",
    topicsFeedSort: "newest",
    topicsFeedSearch: "",
    /* Alerts & Action Center (Triage): which signal is currently focused,
       which signals the user has dismissed for this session, and the
       per-signal search/sort. */
    triageActiveId: null,
    triageDismissed: new Set(),
    triageSearch: "",
    triageSort: "newest",
    page: "overview",
  };

  /* ── DOM refs ──────────────────────────────────────────────── */
  const ctrlUniv  = $("#ctrl-univ");
  const ctrlRange = $("#ctrl-range");
  const tsRel     = $("#ts-rel");
  const covText   = $("#cov-text");
  const pageTitle = $("#page-title");
  const pageSub   = $("#page-sub");

  /* ── Page metadata ─────────────────────────────────────────── */
  const PAGES = {
    overview: { title: "Overview",        sub: "What is happening right now." },
    topics:   { title: "Topics & Conversations", sub: "What students are talking about." },
    emotions: { title: "Emotional Landscape",     sub: "Positivity, intensity, sense of control across the corpus." },
    feed:     { title: "Alerts & Action Center",  sub: "Triage anomalies one at a time. Click a signal to focus its posts." },
  };

  /* ── Bootstrap ─────────────────────────────────────────────── */
  const meta = await InstData.meta();
  meta.sort((a, b) => a.univ_code.localeCompare(b.univ_code));
  for (const m of meta) {
    const o = document.createElement("option");
    o.value = m.univ_code;
    o.textContent = `${m.univ_code} · ${m.school_alias}`;
    ctrlUniv.appendChild(o);
  }
  const best = meta.slice().sort((a, b) => b.vad_coverage - a.vad_coverage)[0];
  const initialUniv = (new URLSearchParams(location.search).get("u")) || best.univ_code;
  ctrlUniv.value = initialUniv;

  ctrlUniv.addEventListener("change", () => loadUniv(ctrlUniv.value));
  ctrlRange.addEventListener("change", () => {
    const v = ctrlRange.value;
    state.dateRangeDays = v === "all" ? null : Number(v);
    renderActivePage();
  });

  /* CTA context — declared BEFORE the first await loadUniv so renderOverview
     can reference it during initial load without hitting the const TDZ. */
  const ctaCtx = {
    applyTopicFilter(tid) { state.topicFilter = tid; },
    applyFeedSort(mode)   { state.feedSort = mode; state.triageSort = mode; const sel = $("#triage-sort"); if (sel) sel.value = mode; },
    gotoPageForAlert(a) {
      const map = { concentration: "topics", sarcasm: "feed", crisis: "feed", intensity: "emotions" };
      const target = map[a.kind] || "feed";
      location.hash = `#${target}`;
    },
  };

  /* ── Theme: relayout only, no data fetch, no chart redraw ────── */
  window.addEventListener("themechange", () => {
    ChartsTheme.repaintAllCharts();
    const bubble = $("#vad-bubble");
    if (bubble && bubble.layout) InstCharts.vadBubbleRelayoutTheme(bubble);
    const cal = $("#heatmap");
    if (cal && cal.children.length) InstCharts.calendarHeatmap(cal, scopedPosts());
  });

  DashUtils.wireInfoHints();

  /* ── Hash router ───────────────────────────────────────────── */
  function applyHash() {
    let key = (location.hash || "#overview").replace(/^#/, "");
    if (!PAGES[key]) key = "overview";
    state.page = key;
    document.querySelectorAll(".page").forEach(p => p.hidden = p.dataset.page !== key);
    document.querySelectorAll(".rail-anchor").forEach(a => {
      if (a.dataset.target === key) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
    pageTitle.textContent = PAGES[key].title;
    pageSub.textContent = PAGES[key].sub;
    renderActivePage();
    window.requestAnimationFrame(() => {
      Chart.instances && Object.values(Chart.instances).forEach(c => c.resize());
      document.querySelectorAll(`.page:not([hidden]) .js-plotly-plot`).forEach(el => Plotly.Plots.resize(el));
    });
  }
  window.addEventListener("hashchange", applyHash);

  /* ── Load univ ─────────────────────────────────────────────── */
  await loadUniv(initialUniv);
  registerExpandHandlers();
  Expand.wireButtons();
  applyHash();

  $("#trend-window").addEventListener("change", () => {
    if (state.page === "overview") renderTrends();
  });
  /* The legacy global filter bar (#filter-topic etc.) was removed when the
     Feed page became the Alerts & Action Center. Its controls live inside
     the right detail column now and are wired in renderFeedPage(). */

  async function loadUniv(code) {
    state.topicFilter = null;
    document.title = `${code} — Institutional Emotion Overview`;
    history.replaceState(null, "", `?u=${code}${location.hash}`);
    state.univ = await InstData.univ(code);
    state.univ.posts.forEach(p => {
      if (p._jx == null) {
        p._jx = (Math.random() - 0.5) * 0.9;
        p._jy = (Math.random() - 0.5) * 0.9;
      }
    });
    window.__InstUniv = state.univ;
    /* New school year, new alerts: any signals the user dismissed before
       switching universities should NOT carry over to the new dataset. */
    state.triageDismissed = new Set();
    state.triageActiveId = null;
    renderHeader();
    renderActivePage();
  }

  function scopedPosts() {
    const u = state.univ; if (!u) return [];
    let posts = u.posts;
    if (state.dateRangeDays != null) {
      const anchor = posts.reduce((m, p) => p.ts && p.ts > m ? p.ts : m, 0);
      const cutoff = anchor - state.dateRangeDays * 86400;
      posts = posts.filter(p => p.ts && p.ts >= cutoff);
    }
    if (state.topicFilter != null) posts = posts.filter(p => p.topic_id === state.topicFilter);
    if (state.keywordFilter) {
      const kw = state.keywordFilter.toLowerCase();
      posts = posts.filter(p => (p.text || "").toLowerCase().includes(kw));
    }
    return posts;
  }

  /* Topics page derives its donut from the *post-scoped* topic counts so that
     the keyword filter actually re-aggregates the donut, per spec. */
  function scopedTopics() {
    const u = state.univ; if (!u) return [];
    if (state.keywordFilter == null) return u.topics;
    const counts = new Map();
    const sumV = new Map();
    const cntV = new Map();
    for (const p of scopedPosts()) {
      counts.set(p.topic_id, (counts.get(p.topic_id) || 0) + 1);
      if (p.V != null) {
        sumV.set(p.topic_id, (sumV.get(p.topic_id) || 0) + p.V);
        cntV.set(p.topic_id, (cntV.get(p.topic_id) || 0) + 1);
      }
    }
    return u.topics
      .filter(t => (counts.get(t.id) || 0) > 0)
      .map(t => ({
        ...t,
        size: counts.get(t.id) || 0,
        scored: cntV.get(t.id) || 0,
        mean_V: cntV.get(t.id) ? sumV.get(t.id) / cntV.get(t.id) : null,
      }));
  }

  function maxTs(posts) { return posts.reduce((m, p) => p.ts && p.ts > m ? p.ts : m, 0); }

  function renderHeader() {
    const u = state.univ;
    const lastTs = maxTs(u.posts);
    tsRel.textContent = lastTs ? `last post ${DashUtils.fmt.relative(lastTs)}` : "no timestamps";
    const cov = (u.vad_coverage * 100).toFixed(0);
    covText.textContent = `Emotion coverage ${cov}%`;
  }

  function renderActivePage() {
    if (state.page === "overview") renderOverview();
    else if (state.page === "topics") renderTopicsPage();
    else if (state.page === "emotions") renderEmotionsPage();
    else if (state.page === "feed") renderFeedPage();
  }

  /* ── Page 1: Overview ──────────────────────────────────────── */
  function renderOverview() {
    const u = state.univ;
    const posts = scopedPosts();
    const lastTs = maxTs(posts) || maxTs(u.posts);
    const W = 7 * 86400;

    /* KPI: Posts (recent 7 d) with delta */
    const cur7  = u.posts.filter(p => p.ts && lastTs - p.ts >= 0 && lastTs - p.ts < W).length;
    const prev7 = u.posts.filter(p => p.ts && lastTs - p.ts >= W && lastTs - p.ts < 2 * W).length;
    $("#kpi-posts-7d").textContent = DashUtils.fmt.int(cur7);
    if (cur7 + prev7 < 5) {
      $("#kpi-posts-delta").innerHTML = `<span class="kpi-delta-context">total ${DashUtils.fmt.int(u.post_count)} all-time</span>`;
    } else {
      const d = cur7 - prev7;
      const dir = d > 0 ? "up" : (d < 0 ? "down" : "flat");
      const arrow = dir === "up" ? "↑" : dir === "down" ? "↓" : "→";
      $("#kpi-posts-delta").className = `kpi-delta ${dir}`;
      $("#kpi-posts-delta").innerHTML = `<span class="arrow">${arrow}</span><span>${d > 0 ? "+" : ""}${d} vs prior 7 d</span>`;
    }

    const scoredAll = u.posts.filter(p => p.V != null);
    if (scoredAll.length === 0) {
      $("#kpi-v").textContent = "—";
      $("#kpi-v-delta").innerHTML = `<span class="kpi-delta-context">no emotion scores yet</span>`;
      $("#kpi-neg").textContent = "—";
      $("#kpi-neg-delta").innerHTML = "";
      $("#kpi-sarc").textContent = "—";
      $("#kpi-sarc-delta").innerHTML = "";
    } else {
      const corpusV = scoredAll.reduce((s, p) => s + p.V, 0) / scoredAll.length;
      const corpusSarc = scoredAll.filter(p => p.sarcasm).length / scoredAll.length;
      const vWin = DashUtils.windowDelta(u.posts, "V", lastTs);
      const sarcWin = sarcWindow(u.posts, lastTs);
      const negCur  = u.posts.filter(p => p.ts && lastTs - p.ts < W && p.V != null && p.V <= 3).length;
      const negPrev = u.posts.filter(p => p.ts && lastTs - p.ts >= W && lastTs - p.ts < 2 * W && p.V != null && p.V <= 3).length;

      if (vWin.sufficient) {
        $("#kpi-v").textContent = vWin.current.toFixed(2);
        renderDelta($("#kpi-v-delta"), vWin.delta, "absolute");
      } else {
        $("#kpi-v").textContent = corpusV.toFixed(2);
        $("#kpi-v-delta").innerHTML = `<span class="kpi-delta-context">corpus all-time mean</span>`;
      }
      $("#kpi-neg").textContent = DashUtils.fmt.int(negCur);
      if (negCur + negPrev >= 5) {
        renderDelta($("#kpi-neg-delta"), negCur - negPrev, "count", { invert: true });
      } else {
        $("#kpi-neg-delta").innerHTML = `<span class="kpi-delta-context">posts with positivity ≤ 3</span>`;
      }
      $("#kpi-sarc").textContent = (corpusSarc * 100).toFixed(1) + "%";
      if (sarcWin.sufficient) renderDelta($("#kpi-sarc-delta"), sarcWin.delta, "percent", { invert: true });
      else $("#kpi-sarc-delta").innerHTML = `<span class="kpi-delta-context">corpus all-time rate</span>`;
    }

    /* Hero + signal strip */
    const alerts = InstAlerts.compute(u);
    const heroAlert = InstAlerts.renderHero($("#hero-zone"), alerts, u, ctaCtx);
    InstAlerts.renderStrip($("#signal-strip"), alerts, heroAlert, ctaCtx);

    renderSnapshot();
    InstCharts.calendarHeatmap($("#heatmap"), posts);
    renderTrends();
  }

  /* Topic Mood Snapshot — top 5 lowest-positivity topics */
  function renderSnapshot() {
    const host = $("#snapshot-list");
    if (!host) return;
    host.innerHTML = "";
    const u = state.univ;
    const candidates = u.topics
      .filter(t => t.id !== -1)
      .filter(t => t.scored != null && t.scored >= 5)
      .sort((a, b) => (a.mean_V ?? 9) - (b.mean_V ?? 9))
      .slice(0, 6);

    if (!candidates.length) {
      host.innerHTML = `<div class="empty-state">No topics with enough scored posts yet. As emotion scoring fills in, the most concerning topics will surface here.</div>`;
      return;
    }

    for (const t of candidates) {
      host.appendChild(snapshotRowEl(t));
    }
  }

  function snapshotRowEl(t) {
    const row = document.createElement("div");
    row.className = "snap-row";
    const colour = VADColors.valenceCalendar(t.mean_V);
    const fillPct = Math.max(4, Math.min(100, (t.mean_V / 9) * 100));
    const sarcBadge = (t.sarcasm_rate != null && t.sarcasm_rate > 0.15)
      ? `<span class="badge sarc">Sarc ${Math.round(t.sarcasm_rate * 100)}%</span>` : "";
    const intenseBadge = (t.mean_A != null && t.mean_A >= 7)
      ? `<span class="badge intense">↑ Intense ${t.mean_A.toFixed(1)}</span>` : "";
    row.innerHTML = `
      <span class="dot" style="background:${DashUtils.topicColor(t.id)}"></span>
      <div class="body">
        <div class="name" title="${escapeHtml(t.label)}">${escapeHtml(t.label)}</div>
        <div class="meter">
          <div class="bar"><div class="fill" style="width:${fillPct}%; background:${colour};"></div></div>
          <span>${t.size} posts${t.scored < t.size ? ` · ${t.scored} scored` : ""}</span>
        </div>
      </div>
      <div class="right">
        ${sarcBadge || intenseBadge}
        <span class="pos-num" style="color:${colour};">${t.mean_V.toFixed(1)}</span>
      </div>`;
    row.addEventListener("click", () => {
      state.topicFilter = t.id;
      location.hash = "#topics";
    });
    return row;
  }

  function renderTrends() {
    const wnd = Number($("#trend-window").value);
    InstCharts.trends($("#chart-trends"), scopedPosts(), wnd, { simple: true, withVolume: true });
  }

  /* ── Page 2: Topics ────────────────────────────────────────── */
  function renderTopicsPage() {
    const posts = scopedPosts();
    const topics = scopedTopics();

    renderTopicsInsight(topics);

    InstCharts.topicDistribution(
      $("#chart-topics"), topics, $("#donut-num"), $("#topic-legend"),
      (tid) => {
        state.topicFilter = (state.topicFilter === tid) ? null : tid;
        renderTopicsPage();
      },
      state.topicFilter,
    );
    updateTopicFilterIndicator();
    InstCharts.keywords(
      $("#chart-keywords"), posts,
      (word) => {
        state.keywordFilter = (state.keywordFilter === word) ? null : word;
        renderTopicsPage();
      },
      state.keywordFilter,
    );

    /* Context line + feed context */
    const ctxParts = [];
    if (state.topicFilter != null) {
      const t = state.univ.topics.find(t => t.id === state.topicFilter);
      ctxParts.push(`topic “${t?.label || "—"}”`);
    }
    if (state.keywordFilter) ctxParts.push(`keyword “${state.keywordFilter}”`);
    $("#feed-context-topics").textContent = ctxParts.length
      ? `Latest posts in ${ctxParts.join(" + ")}.`
      : "Latest posts across all topics.";

    /* Wire toolbar (idempotent on re-render) */
    wireFeedToolbarOnce();

    /* Apply search + sort */
    let feedPosts = posts.slice();
    const q = (state.topicsFeedSearch || "").trim().toLowerCase();
    if (q) feedPosts = feedPosts.filter(p => (p.text || "").toLowerCase().includes(q));
    renderFeedInto($("#feed-list-topics"), feedPosts.slice(0, 60), state.topicsFeedSort);
  }

  /* Single-sentence callout: combines the dominant topic with the topic
     driving the most negative sentiment (must have ≥10 posts to be
     trustworthy). Hidden when no meaningful signal exists. */
  function renderTopicsInsight(topics) {
    const host = $("#topics-insight");
    if (!host) return;
    const visible = (topics || []).filter(t => t.id !== -1 && t.size > 0);
    if (!visible.length) { host.hidden = true; host.innerHTML = ""; return; }
    const total = visible.reduce((s, t) => s + t.size, 0);
    const top = [...visible].sort((a, b) => b.size - a.size)[0];
    const meaningful = visible.filter(t => t.size >= 10 && t.mean_V != null);
    const lowest = meaningful.length
      ? [...meaningful].sort((a, b) => a.mean_V - b.mean_V)[0]
      : null;
    if (!top) { host.hidden = true; host.innerHTML = ""; return; }
    const pct = ((top.size / total) * 100).toFixed(1);
    let sentence = `<b>${escapeHtml(top.label)}</b> accounts for ${pct}% of recent chatter`;
    if (lowest && lowest !== top) {
      sentence += `, while <b>${escapeHtml(lowest.label)}</b> is driving the most negative sentiment (${lowest.mean_V.toFixed(1)})`;
    } else if (top.mean_V != null) {
      sentence += ` (positivity ${top.mean_V.toFixed(1)})`;
    }
    sentence += ".";
    host.innerHTML = `<span class="ti-icon" aria-hidden="true">💡</span><span class="ti-text">${sentence}</span>`;
    host.hidden = false;
  }

  function wireFeedToolbarOnce() {
    const search = $("#feed-search-topics");
    const sort = $("#feed-sort-topics");
    if (search && !search.dataset.wired) {
      search.dataset.wired = "1";
      search.value = state.topicsFeedSearch;
      let timer = null;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          state.topicsFeedSearch = search.value;
          renderTopicsPage();
        }, 120);
      });
    }
    if (sort && !sort.dataset.wired) {
      sort.dataset.wired = "1";
      sort.value = state.topicsFeedSort;
      sort.addEventListener("change", () => {
        state.topicsFeedSort = sort.value;
        renderTopicsPage();
      });
    }
  }

  function updateTopicFilterIndicator() {
    const el = $("#topic-filter-state");
    if (!el) return;
    const parts = [];
    if (state.topicFilter != null) {
      const t = state.univ.topics.find(t => t.id === state.topicFilter);
      if (t) parts.push(`Topic: <b>${escapeHtml(t.label)}</b> <a href="#" data-clear="topic">clear</a>`);
    }
    if (state.keywordFilter) {
      parts.push(`Keyword: <b>“${escapeHtml(state.keywordFilter)}”</b> <a href="#" data-clear="keyword">clear</a>`);
    }
    el.innerHTML = parts.length ? "Filter — " + parts.join(" · ") : "";
    el.querySelectorAll("a[data-clear]").forEach(a => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (a.dataset.clear === "topic") state.topicFilter = null;
        if (a.dataset.clear === "keyword") state.keywordFilter = null;
        renderTopicsPage();
      });
    });
  }

  /* ── Page 3: Emotions ──────────────────────────────────────── */
  function renderEmotionsPage() {
    const posts = scopedPosts();
    /* If the previously pinned post fell out of the current scope (date range
       or topic filter changed), clear it so the inspector returns to its empty
       state instead of showing a stale post that's no longer on the chart. */
    if (state.selectedPostId != null && !posts.some(p => p.post_id === state.selectedPostId)) {
      state.selectedPostId = null;
    }
    InstCharts.vadBubble($("#vad-bubble"), posts, {
      onClickPoint: (postId) => {
        state.selectedPostId = (state.selectedPostId === postId) ? null : postId;
        renderInspector();
      },
    });
    wireInspectorClearOnce();
    wireVadResetOnce();
    renderEmotionsInsight(posts);
    renderInspector();
  }

  /* In-modal mirror of the inspector — so clicking a dot inside the
     full-screen scatter shows immediate feedback without forcing the user
     to close the modal to see what they pinned. */
  function renderModalPin(pinHost, statusEl) {
    if (!pinHost) return;
    pinHost.innerHTML = "";
    if (state.selectedPostId == null) {
      pinHost.hidden = true;
      if (statusEl) statusEl.hidden = true;
      return;
    }
    const post = state.univ.posts.find(p => p.post_id === state.selectedPostId);
    if (!post) {
      pinHost.hidden = true;
      if (statusEl) statusEl.hidden = true;
      return;
    }
    const tmp = document.createElement("ul");
    renderFeedInto(tmp, [post], "newest");
    const card = tmp.querySelector(".feed-card");
    if (card) {
      card.classList.add("inspector-card");
      pinHost.appendChild(card);
      pinHost.hidden = false;
    }
    if (statusEl) {
      const t = state.univ.topics.find(tt => tt.id === post.topic_id);
      statusEl.textContent = t ? `Pinned · ${t.label}` : "Pinned post";
      statusEl.hidden = false;
    }
  }

  function wireVadResetOnce() {
    const btn = $("#vad-reset");
    if (!btn || btn.dataset.wired) return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", () => {
      const host = $("#vad-bubble");
      if (host && host.layout) {
        /* Lock to the data domain (1–9 with a sliver of padding) instead of
           Plotly's autorange, which extends past the markers and shows a
           wide empty halo around the plot. */
        Plotly.relayout(host, { "xaxis.range": [0.3, 9.7], "yaxis.range": [0.3, 9.7] });
      }
    });
  }

  /* Counts which topics dominate the bottom-right danger zone
     (Intensity ≥ 5 AND Control < 5) and surfaces the top 1–2 drivers
     as a single plain-English alert sentence. */
  function renderEmotionsInsight(posts) {
    const host = $("#emotions-insight");
    if (!host) return;
    const danger = posts.filter(p => p.V != null && p.A >= 5 && p.D < 5);
    if (danger.length < 5) {
      host.hidden = true;
      host.innerHTML = "";
      return;
    }
    const counts = new Map();
    for (const p of danger) counts.set(p.topic_id, (counts.get(p.topic_id) || 0) + 1);
    const ranked = [...counts.entries()]
      .filter(([tid]) => tid !== -1)
      .sort((a, b) => b[1] - a[1]);
    if (!ranked.length) { host.hidden = true; host.innerHTML = ""; return; }
    const total = danger.length;
    const top = ranked[0];
    const topShare = Math.round((top[1] / total) * 100);
    const topName = labelForTopic(top[0]);
    /* One driver, one sentence, one line. Don't pile on a second clause
       that pushes the banner to two rows. */
    host.innerHTML =
      `<span class="ti-icon" aria-hidden="true">💡</span>` +
      `<span class="ti-text"><b style="color:rgba(220,38,38,0.95)">Alert:</b> ` +
      `${topShare}% of posts in the danger zone are driven by <b>${escapeHtml(topName)}</b>.</span>`;
    host.hidden = false;
  }
  function labelForTopic(tid) {
    const t = (state.univ.topics || []).find(t => t.id === tid);
    return t ? t.label : (tid === -1 ? "Noise" : `Topic ${tid}`);
  }

  function wireInspectorClearOnce() {
    const btn = $("#inspector-clear");
    if (!btn || btn.dataset.wired) return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", () => {
      state.selectedPostId = null;
      renderInspector();
    });
  }

  function renderInspector() {
    const empty = $("#inspector-empty");
    const host = $("#inspector-host");
    const sub = $("#inspector-context");
    const clearBtn = $("#inspector-clear");
    if (!host) return;
    /* Remove any previously rendered card so we don't pile them up. */
    host.querySelectorAll(".feed-card").forEach(c => c.remove());

    if (state.selectedPostId == null) {
      if (empty) empty.hidden = false;
      if (sub) sub.textContent = "Click a dot on the scatter to read the student's exact post.";
      if (clearBtn) clearBtn.hidden = true;
      return;
    }

    const post = state.univ.posts.find(p => p.post_id === state.selectedPostId);
    if (!post) {
      state.selectedPostId = null;
      renderInspector();
      return;
    }
    if (empty) empty.hidden = true;
    if (clearBtn) clearBtn.hidden = false;
    if (sub) {
      const t = state.univ.topics.find(tt => tt.id === post.topic_id);
      sub.textContent = t ? `Pinned · ${t.label}` : "Pinned post";
    }

    /* Build a single-card ul so we can reuse renderFeedInto's markup
       conventions, then move the card into the inspector host. */
    const tmp = document.createElement("ul");
    renderFeedInto(tmp, [post], "newest");
    const card = tmp.querySelector(".feed-card");
    if (card) {
      card.classList.add("inspector-card");
      host.appendChild(card);
    }
  }

  /* ── Page 4: Alerts & Action Center ─────────────────────────
     Master-detail triage queue. Each alert from InstAlerts.compute() is
     a row in the left "Signals" column; clicking it focuses the right
     column on the posts driving that specific alert. Dismiss removes
     the signal for this session — a full reload recomputes from data,
     so a real anomaly will re-appear if it persists. */

  /* Stable id so we can track active/dismissed signals across re-renders.
     Two alerts of the same kind on the same topic can't coexist (compute
     dedupes them), so kind+topic is unique enough. */
  function signalId(a) {
    return `${a.kind}-${a.topicId ?? "g"}`;
  }

  /* Posts that are actually driving the given signal — used by the
     detail column. Mirrors what each alert kind logically refers to. */
  function postsForSignal(a) {
    const u = state.univ; if (!u) return [];
    const all = u.posts || [];
    const now = all.reduce((m, p) => p.ts && p.ts > m ? p.ts : m, 0);
    const recent = now ? all.filter(p => p.ts && p.ts >= now - 24 * 3600) : all;
    if (a.kind === "concentration" && a.topicId != null) {
      return recent.filter(p => p.topic_id === a.topicId);
    }
    if (a.kind === "sarcasm" && a.topicId != null) {
      return all.filter(p => p.topic_id === a.topicId && p.sarcasm);
    }
    if (a.kind === "crisis") {
      return recent.filter(p => p.V != null && p.V <= 3 && p.A >= 7);
    }
    if (a.kind === "intensity") {
      return recent.filter(p => p.A != null);
    }
    return recent;
  }

  function renderFeedPage() {
    const u = state.univ;
    const allAlerts = InstAlerts.compute(u);
    /* Tag each alert with its stable id and filter out the ones the
       admin has already dismissed for this session. */
    const alerts = allAlerts
      .map(a => ({ ...a, id: signalId(a) }))
      .filter(a => !state.triageDismissed.has(a.id));

    const allClear = $("#triage-all-clear");
    const grid = $("#triage-grid");

    if (!alerts.length) {
      /* Friendly full-width "All clear" panel — both columns collapse. */
      if (grid) grid.hidden = true;
      if (allClear) {
        allClear.hidden = false;
        const lastTs = (u.posts || []).reduce((m, p) => p.ts > m ? p.ts : m, 0);
        const recent = (u.posts || []).filter(p => p.ts && p.ts >= lastTs - 24 * 3600).length;
        const meta = $("#triage-clear-meta");
        if (meta) meta.textContent = `${recent} posts scanned · ${(u.posts || []).filter(p => p.V != null).length} with emotion scores.`;
      }
      return;
    }

    if (grid) grid.hidden = false;
    if (allClear) allClear.hidden = true;

    /* Auto-select: if no active id or the active one was just dismissed,
       fall through to the highest-priority signal (alerts is already
       sorted crit → warn-strong → warn by InstAlerts.compute). */
    if (!alerts.some(a => a.id === state.triageActiveId)) {
      state.triageActiveId = alerts[0].id;
      state.triageSearch = "";
    }

    renderSignalsList(alerts);
    renderTriageDetail(alerts);
    wireTriageToolbarOnce();
  }

  function renderSignalsList(alerts) {
    const host = $("#signals-list");
    if (!host) return;
    const count = $("#signals-count");
    if (count) count.textContent = alerts.length === 1
      ? `1 anomaly to triage`
      : `${alerts.length} anomalies to triage`;

    host.innerHTML = alerts.map(a => {
      const isActive = a.id === state.triageActiveId;
      const levelClass =
        a.level === "crit"        ? "level-crit"
      : a.level === "warn-strong" ? "level-warn-strong"
      :                             "level-warn";
      const kindIcon =
        a.kind === "crisis"        ? "!"
      : a.kind === "concentration" ? "T"
      : a.kind === "sarcasm"       ? "S"
      : a.kind === "intensity"     ? "↑"
      :                              "•";
      /* The outer element is a div+role=button, NOT a <button>, because we
         need a real <button> inside (the dismiss action) and nested buttons
         are invalid HTML — browsers silently close the outer one. */
      return `
        <div class="signal-card ${levelClass}${isActive ? " is-active" : ""}" data-signal-id="${a.id}" role="button" tabindex="0" aria-pressed="${isActive ? "true" : "false"}">
          <span class="signal-icon" aria-hidden="true">${kindIcon}</span>
          <span class="signal-body">
            <span class="signal-title">${escapeHtml(a.title)}</span>
            <span class="signal-meta">${escapeHtml(a.meta || "")}</span>
          </span>
          <button type="button" class="signal-dismiss" data-dismiss-id="${a.id}" aria-label="Dismiss this signal" title="Dismiss this signal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
          </button>
        </div>`;
    }).join("");

    /* Card click → focus this signal. Dismiss button click → remove it.
       The dismiss button is a child of the card, so we stop the click
       from bubbling up into a focus action. */
    host.querySelectorAll(".signal-card").forEach(card => {
      const focus = (e) => {
        if (e.target.closest(".signal-dismiss")) return;
        const id = card.dataset.signalId;
        if (id && id !== state.triageActiveId) {
          state.triageActiveId = id;
          state.triageSearch = "";
          renderFeedPage();
        }
      };
      card.addEventListener("click", focus);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); focus(e); }
      });
    });
    host.querySelectorAll(".signal-dismiss").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = btn.dataset.dismissId;
        if (!id) return;
        state.triageDismissed.add(id);
        if (state.triageActiveId === id) state.triageActiveId = null;
        renderFeedPage();
      });
    });
  }

  function renderTriageDetail(alerts) {
    const active = alerts.find(a => a.id === state.triageActiveId);
    const titleEl = $("#triage-title");
    const subEl   = $("#triage-sub");
    const list    = $("#triage-feed-list");
    if (!active || !list) return;

    let posts = postsForSignal(active);
    const q = state.triageSearch.trim().toLowerCase();
    if (q) posts = posts.filter(p => (p.text || "").toLowerCase().includes(q));

    /* Header — what the right column is reviewing right now. */
    const kindLabel =
      active.kind === "crisis"        ? "Distress signal"
    : active.kind === "concentration" ? "Topic concentration"
    : active.kind === "sarcasm"       ? "Sarcasm cluster"
    : active.kind === "intensity"     ? "Intensity spike"
    :                                   "Signal";
    if (titleEl) titleEl.textContent = `Reviewing ${posts.length.toLocaleString()} ${posts.length === 1 ? "post" : "posts"}: ${kindLabel}`;
    if (subEl)   subEl.textContent   = active.title;

    /* Reflect persisted search/sort into the inputs (idempotent). */
    const search = $("#triage-search");
    const sort   = $("#triage-sort");
    if (search && search.value !== state.triageSearch) search.value = state.triageSearch;
    if (sort   && sort.value !== state.triageSort)     sort.value   = state.triageSort;

    /* Cap at 200 to keep DOM small; the user can search/sort to find more. */
    renderFeedInto(list, posts.slice(0, 200), state.triageSort);
  }

  function wireTriageToolbarOnce() {
    const search = $("#triage-search");
    const sort   = $("#triage-sort");
    if (search && !search.dataset.wired) {
      search.dataset.wired = "1";
      let timer = null;
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          state.triageSearch = search.value;
          renderFeedPage();
        }, 120);
      });
    }
    if (sort && !sort.dataset.wired) {
      sort.dataset.wired = "1";
      sort.addEventListener("change", () => {
        state.triageSort = sort.value;
        renderFeedPage();
      });
    }
  }

  /* ── Shared feed renderer ──────────────────────────────────── */
  function renderFeedInto(host, basePosts, sort) {
    const posts = basePosts.slice();
    if (sort === "newest") posts.sort((a, b) => (b.ts || 0) - (a.ts || 0));
    else if (sort === "arousal") posts.sort((a, b) => (b.A ?? -1) - (a.A ?? -1));
    else if (sort === "negative") posts.sort((a, b) => (a.V ?? 99) - (b.V ?? 99));
    else if (sort === "sarcasm") posts.sort((a, b) => (b.sarcasm ? 1 : 0) - (a.sarcasm ? 1 : 0) || (b.ts || 0) - (a.ts || 0));

    host.innerHTML = posts.map(p => {
      const t = state.univ.topics.find(t => t.id === p.topic_id);
      const tl = t ? t.label : (p.topic_id === -1 ? "Noise" : `Topic ${p.topic_id}`);
      const topicColor = DashUtils.topicColor(p.topic_id);
      const dot = `<span class="topic-dot" style="background:${topicColor}" title="Topic: ${escapeHtml(tl)}"></span>`;
      const flagged = !!localStorage.getItem(`flagged-post-${p.post_id}`);
      const flaggedBadge = flagged
        ? `<span class="card-flagged" title="You flagged this card as misclassified.">Flagged</span>`
        : "";
      /* Strip the "EntryNNNN" import prefix that some scrapes left at the
         start of post bodies — admins should see the student's words, not
         our row identifier. UUID post_ids are hidden entirely. */
      const cleanText = (p.text || "").replace(/^Entry\s*\d+\s*[:\-–—]?\s*/i, "");
      const escaped = escapeHtml(DashUtils.fmt.truncate(cleanText, 240));
      /* Anonymisation tags like [REDACTED_NAME] are signal but visually loud
         — wrap them in a muted pill so they don't dominate the quote. */
      const styled = escaped.replace(/\[REDACTED_[A-Z_]+\]/g, m =>
        `<span class="redacted-tag" title="A personal name was here — redacted for student privacy.">${m}</span>`);
      const hasScores = p.V != null;
      const sarcChip = p.sarcasm
        ? `<span class="metric metric-sarc" title="Detected as likely sarcasm — the actual sentiment may differ from the words.">~ Sarcasm</span>`
        : "";
      const analysisWell = hasScores ? `
        <div class="analysis-well" aria-label="AI analysis">
          <span class="metric metric-pos" title="Positivity ${p.V}: how positive (high) or negative (low) the post sounds. 1–9 scale."><span class="m-icon" aria-hidden="true">+</span> Positivity <b>${p.V}</b></span>
          <span class="metric metric-int" title="Intensity ${p.A}: how calm (low) or stressed (high) the post sounds. 1–9 scale."><span class="m-icon" aria-hidden="true">⚡</span> Intensity <b>${p.A}</b></span>
          <span class="metric metric-ctrl" title="Sense of Control ${p.D}: how helpless (low) or empowered (high) the writer feels. 1–9 scale."><span class="m-icon" aria-hidden="true">⚓</span> Control <b>${p.D}</b></span>
          ${sarcChip}
        </div>` : "";
      return `<li class="feed-card${flagged ? " is-flagged" : ""}" data-post-id="${p.post_id}">
        <div class="card-top">
          <div class="card-meta">
            ${dot}<span class="topic-name">${escapeHtml(tl)}</span>
            <span class="meta-sep" aria-hidden="true">·</span>
            <time class="post-date">${DashUtils.fmt.relative(p.ts)}</time>
            ${flaggedBadge}
          </div>
          <div class="card-menu-wrap">
            <button class="card-menu-btn" type="button" aria-label="Card options" aria-haspopup="menu" aria-expanded="false" data-action="toggle-menu">⋮</button>
            <ul class="card-menu" role="menu" hidden>
              <li><button type="button" class="menu-item" role="menuitem" data-action="flag">${flagged ? "✓ Flagged for review" : "🚩 Flag misclassification"}</button></li>
            </ul>
          </div>
        </div>
        <div class="quote">${styled}</div>
        ${analysisWell}
      </li>`;
    }).join("") || `<li class="empty-state">No posts in this view.</li>`;

  }

  /* Document-level event delegation for the kebab menu and Flag action.
     This must live above the host element because the Post Inspector moves
     a card from a temporary <ul> into a different host, leaving any
     per-host listener detached. Wiring once on document means the menu
     keeps working anywhere the card lands. */
  function wireCardMenusGlobalOnce() {
    if (document.body.dataset.cardMenuGlobalWired) return;
    document.body.dataset.cardMenuGlobalWired = "1";
    document.addEventListener("click", (e) => {
      const menuBtn = e.target.closest(".feed-card [data-action='toggle-menu']");
      const itemBtn = e.target.closest(".feed-card [data-action='flag']");
      if (menuBtn) {
        e.stopPropagation();
        const wrap = menuBtn.closest(".card-menu-wrap");
        const menu = wrap?.querySelector(".card-menu");
        if (!menu) return;
        const opening = menu.hidden;
        document.querySelectorAll(".card-menu").forEach(m => { if (m !== menu) m.hidden = true; });
        document.querySelectorAll(".card-menu-btn").forEach(b => { if (b !== menuBtn) b.setAttribute("aria-expanded", "false"); });
        menu.hidden = !opening;
        menuBtn.setAttribute("aria-expanded", opening ? "true" : "false");
        return;
      }
      if (itemBtn) {
        e.stopPropagation();
        const card = itemBtn.closest(".feed-card");
        const pid = card?.dataset.postId;
        if (!pid) return;
        const key = `flagged-post-${pid}`;
        const wasFlagged = !!localStorage.getItem(key);
        if (wasFlagged) localStorage.removeItem(key);
        else            localStorage.setItem(key, String(Date.now()));
        card.classList.toggle("is-flagged", !wasFlagged);
        const badgeContainer = card.querySelector(".card-meta");
        const existing = badgeContainer?.querySelector(".card-flagged");
        if (!wasFlagged && !existing && badgeContainer) {
          const span = document.createElement("span");
          span.className = "card-flagged";
          span.title = "You flagged this card as misclassified.";
          span.textContent = "Flagged";
          badgeContainer.appendChild(span);
        } else if (wasFlagged && existing) {
          existing.remove();
        }
        itemBtn.textContent = wasFlagged ? "🚩 Flag misclassification" : "✓ Flagged for review";
        const menu = card.querySelector(".card-menu");
        const btn  = card.querySelector(".card-menu-btn");
        if (menu) menu.hidden = true;
        if (btn) btn.setAttribute("aria-expanded", "false");
        return;
      }
      /* Outside click → close every open menu. */
      document.querySelectorAll(".card-menu").forEach(m => m.hidden = true);
      document.querySelectorAll(".card-menu-btn[aria-expanded='true']")
        .forEach(b => b.setAttribute("aria-expanded", "false"));
    });
  }
  wireCardMenusGlobalOnce();

  /* ── Helpers ───────────────────────────────────────────────── */
  function sarcWindow(posts, anchor) {
    const W = 7 * 86400;
    let cur = 0, curN = 0, prev = 0, prevN = 0;
    for (const p of posts) {
      if (!p.ts || p.sarcasm == null) continue;
      const dt = anchor - p.ts;
      if (dt >= 0 && dt < W) { curN++; if (p.sarcasm) cur++; }
      else if (dt >= W && dt < 2 * W) { prevN++; if (p.sarcasm) prev++; }
    }
    if (curN < 20 || prevN < 20) return { delta: null, sufficient: false };
    return { delta: (cur / curN) - (prev / prevN), sufficient: true };
  }

  /* Render delta below a KPI value. `invert` flips the colour semantics for
     metrics where "going up" is bad (negative posts, sarcasm rate). */
  function renderDelta(host, delta, kind, opts = {}) {
    if (delta == null) { host.innerHTML = ""; return; }
    const dir = delta > 0.005 ? "up" : (delta < -0.005 ? "down" : "flat");
    const arrow = dir === "up" ? "↑" : dir === "down" ? "↓" : "→";
    const sign = delta > 0 ? "+" : "";
    let formatted;
    if (kind === "percent")  formatted = sign + (delta * 100).toFixed(1) + " pp";
    else if (kind === "count") formatted = sign + Math.round(delta);
    else                     formatted = sign + delta.toFixed(2);
    /* Invert colour when "up" is undesirable */
    let cls = dir;
    if (opts.invert && dir === "up") cls = "down";
    else if (opts.invert && dir === "down") cls = "up";
    host.className = `kpi-delta ${cls}`;
    host.innerHTML = `<span class="arrow">${arrow}</span><span>${dir === "flat" ? "flat" : formatted}</span><span class="kpi-delta-context"> vs prior 7 d</span>`;
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  /* ── Expand modal handlers ─────────────────────────────────── */
  function registerExpandHandlers() {
    Expand.register("topics", {
      title: "Topic distribution",
      sub: "Sorted by mean positivity (most negative first). Click a row or slice to filter the dashboard.",
      render(host) {
        host.innerHTML = `
          <div class="topic-split" style="height: 100%;">
            <div class="donut-wrap" style="position: relative; min-height: 480px;">
              <canvas id="exp-topics"></canvas>
              <div class="donut-center" style="width: 100%;"><div class="num" id="exp-donut-num">—</div><div class="lab">posts</div></div>
            </div>
            <div id="exp-topic-legend" class="donut-legend" style="overflow-y: auto;"></div>
          </div>`;
        InstCharts.topicDistribution(
          host.querySelector("#exp-topics"),
          scopedTopics(),
          host.querySelector("#exp-donut-num"),
          host.querySelector("#exp-topic-legend"),
          (tid) => {
            state.topicFilter = (state.topicFilter === tid) ? null : tid;
            renderActivePage();
          },
          state.topicFilter,
        );
      },
      /* Restore the page chart when the modal closes — full re-render keeps
         active state, keyword filter, feed search/sort all in sync. */
      onClose() { if (state.page === "topics") renderTopicsPage(); },
    });
    Expand.register("calendar", {
      title: "Daily Positivity Tracker",
      sub: "Daily mean positivity across the active filter. Hover for details.",
      render(host) { host.innerHTML = `<div id="exp-heatmap" style="padding: 12px;"></div>`; InstCharts.calendarHeatmap(host.querySelector("#exp-heatmap"), scopedPosts()); },
      onClose() { if (state.page === "overview") InstCharts.calendarHeatmap($("#heatmap"), scopedPosts()); },
    });
    Expand.register("vad", {
      title: "Emotion Scatter Plot",
      sub: "Click a dot to pin its post — the pinned card preview appears below the chart and stays in the inspector after you close the modal.",
      render(host) {
        host.innerHTML = `
          <div class="vad-expand">
            <div class="vad-expand-toolbar">
              <button id="exp-vad-reset" class="vad-reset" type="button" aria-label="Reset zoom" title="Reset zoom">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>
                <span>Reset view</span>
              </button>
              <div class="vad-expand-status" id="exp-vad-status" hidden></div>
            </div>
            <div id="exp-vad" class="vad-expand-chart"></div>
            <div id="exp-vad-pin" class="vad-expand-pin" hidden></div>
          </div>`;

        const chartHost = host.querySelector("#exp-vad");
        const statusEl  = host.querySelector("#exp-vad-status");
        const pinHost   = host.querySelector("#exp-vad-pin");
        const resetBtn  = host.querySelector("#exp-vad-reset");

        InstCharts.vadBubble(chartHost, scopedPosts(), {
          /* Side legend frees up vertical space — the modal has plenty of
             horizontal room and gains ~70px of plot-area height. */
          verticalLegend: true,
          onClickPoint: (postId) => {
            state.selectedPostId = (state.selectedPostId === postId) ? null : postId;
            /* Mirror the page-level inspector inside the modal so the user
               sees what they just pinned without closing the modal. */
            renderModalPin(pinHost, statusEl);
            /* Keep the page-level inspector in sync for when they close. */
            if (state.page === "emotions") renderInspector();
          },
        });

        resetBtn.addEventListener("click", () => {
          if (chartHost && chartHost.layout) {
            Plotly.relayout(chartHost, { "xaxis.range": [0.3, 9.7], "yaxis.range": [0.3, 9.7] });
          }
        });

        renderModalPin(pinHost, statusEl);
      },
      onClose() { if (state.page === "emotions") renderEmotionsPage(); },
    });
    Expand.register("trends", {
      title: "Emotional Trends over Time",
      sub: `${$("#trend-window").value}-day rolling means with daily post volume.`,
      render(host) { host.innerHTML = `<div class="chart-wrap" style="height: 100%; min-height: 480px;"><canvas id="exp-trends"></canvas></div>`; InstCharts.trends(host.querySelector("#exp-trends"), scopedPosts(), Number($("#trend-window").value), { simple: false, withVolume: true }); },
      /* CRITICAL: The page chart's underlying instance is destroyed when we render
         into the modal canvas, so we must rebuild the page chart on close. */
      onClose() { if (state.page === "overview") renderTrends(); },
    });
    Expand.register("topics-feed", {
      title: "Recent Activity",
      sub: "Live posts in the active topic and keyword filter.",
      render(host) {
        host.innerHTML = `
          <div class="feed-toolbar feed-toolbar-modal" style="display:flex;gap:8px;align-items:center;margin-bottom:10px;">
            <input type="search" id="exp-feed-search" class="feed-search" placeholder="Search posts…" aria-label="Search recent posts" style="flex:1;" />
            <select id="exp-feed-sort" class="feed-sort" aria-label="Sort posts">
              <option value="newest">Newest</option>
              <option value="negative">Lowest positivity</option>
              <option value="arousal">Highest intensity</option>
              <option value="sarcasm">Sarcasm first</option>
            </select>
          </div>
          <ul id="exp-feed-list" class="feed-list" style="max-height:none;overflow-y:auto;"></ul>`;
        const expSearch = host.querySelector("#exp-feed-search");
        const expSort = host.querySelector("#exp-feed-sort");
        expSearch.value = state.topicsFeedSearch;
        expSort.value = state.topicsFeedSort;
        const renderExp = () => {
          let p = scopedPosts();
          const q = state.topicsFeedSearch.trim().toLowerCase();
          if (q) p = p.filter(x => (x.text || "").toLowerCase().includes(q));
          renderFeedInto(host.querySelector("#exp-feed-list"), p, state.topicsFeedSort);
        };
        let timer = null;
        expSearch.addEventListener("input", () => {
          clearTimeout(timer);
          timer = setTimeout(() => {
            state.topicsFeedSearch = expSearch.value;
            renderExp();
          }, 120);
        });
        expSort.addEventListener("change", () => {
          state.topicsFeedSort = expSort.value;
          renderExp();
        });
        renderExp();
      },
      onClose() { if (state.page === "topics") renderTopicsPage(); },
    });
    Expand.register("keywords", {
      title: "Top Trending Keywords",
      sub: "Top 10 by frequency. Bar colour = mean positivity. Click a bar to filter the dashboard.",
      render(host) {
        host.innerHTML = `<div class="chart-wrap" style="height: 100%; min-height: 480px;"><canvas id="exp-keywords"></canvas></div>`;
        InstCharts.keywords(
          host.querySelector("#exp-keywords"), scopedPosts(),
          (word) => {
            state.keywordFilter = (state.keywordFilter === word) ? null : word;
            renderActivePage();
          },
          state.keywordFilter,
        );
      },
      onClose() { if (state.page === "topics") renderTopicsPage(); },
    });
    Expand.register("snapshot", {
      title: "Topic Mood Snapshot",
      sub: "All topics ranked from most upset (low positivity) to most positive. Click a topic to dig deeper.",
      render(host) {
        host.innerHTML = `<div class="topic-snapshot" id="exp-snapshot" style="max-height: 100%;"></div>`;
        const list = host.querySelector("#exp-snapshot");
        const all = state.univ.topics
          .filter(t => t.id !== -1 && t.scored != null && t.scored >= 5)
          .sort((a, b) => (a.mean_V ?? 9) - (b.mean_V ?? 9));
        if (!all.length) {
          list.innerHTML = `<div class="empty-state">No topics with enough scored posts yet.</div>`;
          return;
        }
        for (const t of all) list.appendChild(snapshotRowEl(t));
      },
      /* No onClose needed — the page snapshot is plain DOM, not Chart.js. */
    });
  }

})();
