/* Virtual-scroll post browser for the research dashboard. */
window.PostBrowser = (function () {
  let state = null;

  function render(host, univ) {
    host.innerHTML = "";
    state = {
      univ,
      posts: univ.posts.slice(),
      filtered: univ.posts.slice(),
      sortKey: "ts",
      sortDir: -1,
      expandedId: null,
    };

    const head = document.createElement("div");
    head.className = "th";
    head.innerHTML = `<div data-k="ts">Date</div><div data-k="text">Post (anonymised)</div><div data-k="topic">Topic</div><div class="num" data-k="V">V</div><div class="num" data-k="A">A</div><div class="num" data-k="D">D</div><div data-k="sarc">!</div>`;
    head.querySelectorAll("[data-k]").forEach(el => el.style.cursor = "pointer");
    head.addEventListener("click", (ev) => {
      const k = ev.target.closest("[data-k]")?.dataset.k;
      if (!k) return;
      if (state.sortKey === k) state.sortDir *= -1; else { state.sortKey = k; state.sortDir = 1; }
      sortAndRender();
    });
    host.appendChild(head);

    const body = document.createElement("div");
    body.className = "post-table-body";
    host.appendChild(body);
    state.body = body;

    sortAndRender();
  }

  function applyFilters({ search, topicId, sarcOnly }) {
    if (!state) return 0;
    state.filtered = state.posts.filter(p => {
      if (topicId !== "" && p.topic_id !== Number(topicId)) return false;
      if (sarcOnly && !p.sarcasm) return false;
      if (search) {
        const s = search.toLowerCase();
        if (!(p.text || "").toLowerCase().includes(s)) return false;
      }
      return true;
    });
    sortAndRender();
    return state.filtered.length;
  }

  function sortAndRender() {
    const k = state.sortKey, dir = state.sortDir;
    state.filtered.sort((a, b) => {
      let av, bv;
      switch (k) {
        case "ts": av = a.ts || 0; bv = b.ts || 0; break;
        case "text": av = (a.text || "").length; bv = (b.text || "").length; break;
        case "topic": av = a.topic_id; bv = b.topic_id; break;
        case "sarc": av = a.sarcasm ? 1 : 0; bv = b.sarcasm ? 1 : 0; break;
        default: av = a[k] ?? -99; bv = b[k] ?? -99;
      }
      return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
    });
    renderRows();
  }

  function renderRows() {
    const body = state.body;
    body.innerHTML = "";
    const slice = state.filtered.slice(0, 400);
    const topics = state.univ.topics || [];
    for (const p of slice) {
      const tl = (topics.find(t => t.id === p.topic_id) || {}).label || (p.topic_id === -1 ? "Noise" : `Topic ${p.topic_id}`);
      const td = document.createElement("div");
      td.className = "td";
      const sarc = p.sarcasm ? "🌀" : "";
      const text = escapeHtml(DashUtils.fmt.truncate(p.text, 160));
      td.innerHTML = `
        <div>${DashUtils.fmt.date(p.ts)}</div>
        <div class="text">${text}</div>
        <div><span class="tag" style="background:${DashUtils.topicColor(p.topic_id)}22;color:${DashUtils.topicColor(p.topic_id)};border-color:${DashUtils.topicColor(p.topic_id)}55;">${escapeHtml(DashUtils.fmt.label(tl, 22))}</span></div>
        <div class="num">${p.V ?? "—"}</div>
        <div class="num">${p.A ?? "—"}</div>
        <div class="num">${p.D ?? "—"}</div>
        <div>${sarc}</div>`;
      td.addEventListener("click", () => {
        if (td.classList.contains("expanded")) {
          td.classList.remove("expanded");
          state.expandedId = null;
          renderRows();
          return;
        }
        td.classList.add("expanded");
        td.innerHTML += `<div class="full-text">${escapeHtml(p.text || "")}</div>`;
        state.expandedId = p.post_id;
      });
      body.appendChild(td);
    }
    if (state.filtered.length > 400) {
      const more = document.createElement("div");
      more.className = "td";
      more.style.textAlign = "center";
      more.style.color = "var(--text-muted)";
      more.innerHTML = `<div></div><div>… ${(state.filtered.length - 400).toLocaleString()} more posts. Refine filters above to narrow further.</div><div></div><div></div><div></div><div></div><div></div>`;
      body.appendChild(more);
    }
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  return { render, applyFilters };
})();
