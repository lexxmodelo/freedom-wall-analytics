/* Sidebar with two modes:
   - Suite (default): 64 px icon rail with Overview/Institutional/Research/Methodology
   - Dashboard (window.SIDEBAR config): wider rail with labelled nav and footer controls
     for date range / university / theme. Drives by `data-target` (anchor or hash route). */
(function () {
  const ICON = {
    home:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11.5L12 4l9 7.5"/><path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9"/></svg>`,
    inst:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>`,
    research:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="6"/><line x1="20" y1="20" x2="15.5" y2="15.5"/></svg>`,
    method:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h12"/><path d="M4 12h16"/><path d="M4 18h8"/><circle cx="19" cy="6" r="2"/><circle cx="13" cy="18" r="2"/></svg>`,
    sun:     `<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 3v1.5M12 19.5V21M3 12h1.5M19.5 12H21M5.5 5.5l1 1M17.5 17.5l1 1M5.5 18.5l1-1M17.5 6.5l1-1"/></svg>`,
    moon:    `<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.6A9 9 0 1 1 11.4 3a7 7 0 0 0 9.6 9.6Z"/></svg>`,
    back:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`,
    overview:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>`,
    bell:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 1 1 12 0c0 6 3 6 3 8H3c0-2 3-2 3-8Z"/><path d="M10 21h4"/></svg>`,
    pie:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 12A9.5 9.5 0 1 1 12 2.5V12h9.5Z"/><path d="M22 11A10 10 0 0 0 13 2v9h9Z"/></svg>`,
    cal:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18"/><path d="M8 3v4M16 3v4"/></svg>`,
    vad:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="18" r="2"/><circle cx="13" cy="9" r="2.5"/><circle cx="19" cy="14" r="1.5"/><circle cx="9" cy="13" r="1.5"/></svg>`,
    feed:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16"/><path d="M4 12h12"/><path d="M4 18h8"/></svg>`,
    trend:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><polyline points="3,17 9,11 13,15 21,7"/><polyline points="15,7 21,7 21,13"/></svg>`,
    keys:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="14" y2="12"/><line x1="3" y1="18" x2="18" y2="18"/></svg>`,
    spark:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="9" r="1.5"/><circle cx="13" cy="14" r="2"/><circle cx="18" cy="7" r="1.2"/><circle cx="9" cy="17" r="1"/></svg>`,
  };

  const SUITE_ITEMS = [
    { key: "overview",      label: "Overview",      icon: ICON.home,     href: "overview" },
    { key: "institutional", label: "Institutional", icon: ICON.inst,     href: "institutional" },
    { key: "research",      label: "Research",      icon: ICON.research, href: "research" },
    { key: "methodology",   label: "Methodology",   icon: ICON.method,   href: "methodology" },
  ];

  function pathFor(item) {
    const isNested = /\/(institutional|research)\//.test(location.pathname);
    const up = isNested ? "../" : "";
    if (item === "overview") return `${up}index.html`;
    if (item === "institutional") return `${up}institutional/index.html`;
    if (item === "research") return `${up}research/index.html`;
    if (item === "methodology") return `${up}research/index.html#methodology`;
    return up;
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll(".theme-toggle").forEach(btn => {
      btn.setAttribute("aria-pressed", theme === "dark");
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
    });
  }

  function initTheme() {
    let stored = null;
    try { stored = localStorage.getItem("dashTheme"); } catch (_) {}
    const sysDark = matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(stored || (sysDark ? "dark" : "light"));
  }

  function toggle() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("dashTheme", next); } catch (_) {}
    /* CRITICAL: themechange MUST NOT trigger any data fetch or chart re-creation.
       Listeners should only update colors via Chart.update / Plotly.relayout / D3 re-render. */
    window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: next } }));
  }

  function renderSuite() {
    const active = document.body.dataset.page || "overview";
    return `
      <a href="${pathFor("overview")}" class="rail-brand" aria-label="Freedom Wall Analytics">FW</a>
      <nav class="rail-nav">
        ${SUITE_ITEMS.map(i => `
          <a href="${pathFor(i.href)}" class="rail-item" ${i.href === active ? 'aria-current="page"' : ''}>
            ${i.icon}<span class="rail-tooltip">${i.label}</span>
          </a>`).join("")}
      </nav>
      <div class="rail-foot">
        <button class="theme-toggle" type="button">${ICON.sun}${ICON.moon}<span class="rail-tooltip">Toggle theme</span></button>
      </div>`;
  }

  function renderDashboard() {
    const cfg = window.SIDEBAR;
    const wide = cfg.wide !== false;
    const sections = cfg.sections || [];

    const brandBlock = wide
      ? `<div class="rail-brand-block">
          <div class="rail-brand">${cfg.brandText || "FW"}</div>
          <div class="rail-brand-meta">
            <div class="rail-brand-title">${cfg.title || "Dashboard"}</div>
            <div class="rail-brand-sub">${cfg.subtitle || ""}</div>
          </div>
         </div>`
      : `<div class="rail-brand" aria-label="${cfg.brandLabel || "Dashboard"}">${cfg.brandText || "D1"}</div>`;

    const back = cfg.backHref ? `
      <a href="${cfg.backHref}" class="rail-back-link">
        ${ICON.back}<span>${cfg.backLabel || "Back"}</span>
      </a>` : "";

    const nav = `
      <nav class="rail-nav rail-nav-wide" aria-label="Dashboard sections">
        ${sections.map(s => `
          <a href="${s.href}" class="rail-item rail-anchor" data-target="${s.target || s.href.replace(/^#/, "")}">
            ${ICON[s.icon] || ICON.feed}
            <span class="rail-label">${s.label}</span>
          </a>`).join("")}
      </nav>`;

    const footer = `
      <div class="rail-foot rail-foot-wide">
        ${cfg.footerSlot || ""}
        <button class="theme-toggle theme-toggle-wide" type="button">
          ${ICON.sun}${ICON.moon}
          <span class="rail-label">Theme</span>
        </button>
      </div>`;

    return `${brandBlock}${back}${nav}${footer}`;
  }

  function render() {
    const isDashboard = !!window.SIDEBAR;
    const wide = isDashboard && window.SIDEBAR.wide !== false;
    const inner = isDashboard ? renderDashboard() : renderSuite();
    const railHTML = `
      <aside class="rail ${isDashboard ? 'rail-dashboard' : ''} ${wide ? 'rail-wide' : ''}" aria-label="Primary navigation">
        ${inner}
      </aside>`;

    const existing = Array.from(document.body.childNodes);
    const shell = document.createElement("div");
    shell.className = "shell";
    shell.insertAdjacentHTML("beforeend", railHTML);
    const main = document.createElement("div");
    main.className = "shell-main";
    existing.forEach(n => main.appendChild(n));
    shell.appendChild(main);
    document.body.appendChild(shell);

    document.querySelectorAll(".theme-toggle").forEach(b => b.addEventListener("click", toggle));

    if (isDashboard) wireScrollSpy();
  }

  function wireScrollSpy() {
    const anchors = Array.from(document.querySelectorAll(".rail-anchor"));
    if (!anchors.length) return;
    /* For hash-routed SPAs, the anchor itself is the route — so don't observe; rely
       on hashchange events from app.js to update active state. We just intercept clicks
       to close any modal and let the browser update the hash. */
    if (window.SIDEBAR && window.SIDEBAR.hashRouted) return;

    const setActive = (id) => {
      anchors.forEach(a => {
        const isActive = a.dataset.target === id;
        if (isActive) a.setAttribute("aria-current", "true");
        else a.removeAttribute("aria-current");
      });
    };
    const ids = anchors.map(a => a.dataset.target).filter(Boolean);
    const sections = ids.map(id => document.getElementById(id)).filter(Boolean);
    if (!sections.length) return;
    const obs = new IntersectionObserver((entries) => {
      const visible = entries.filter(e => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (visible.length) setActive(visible[0].target.id);
    }, { rootMargin: "-30% 0px -50% 0px", threshold: [0, 0.25, 0.5, 0.75, 1] });
    sections.forEach(s => obs.observe(s));
    setActive(sections[0].id);

    anchors.forEach(a => {
      a.addEventListener("click", (ev) => {
        const target = document.getElementById(a.dataset.target);
        if (!target) return;
        ev.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  initTheme();
  /* Render synchronously. sidebar.js is loaded at the END of <body>, so all the
     page content is already parsed when this runs; deferring to DOMContentLoaded
     would let later scripts (app.js) query elements (#ctrl-univ etc.) before
     they exist. */
  render();
})();
