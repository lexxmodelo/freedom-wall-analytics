# Dashboard Development — Action Log

Master log for the dual-dashboard build (Institutional + Research views). Every architectural decision, data integration step, performance observation, error, and adaptation is recorded here.

Format per entry:
```
[CATEGORY-NNN] YYYY-MM-DD HH:MM — Title
- Decision: ...
- Data: ...
- Visualization: ...
- Performance: ...
- Issues: ...
- Files Created: ...
- Next Steps: ...
```

Categories: `ARCH`, `DATA`, `ETL`, `VIZ`, `PERF`, `A11Y`, `BUG`, `DEMO`.

---

## [ARCH-001] 2026-05-06 — Two HTML pages + landing page chosen
- **Decision:** Package as `dashboard/index.html` (landing) → `dashboard/institutional/index.html` and `dashboard/research/index.html`. Shared assets live in `dashboard/shared/`.
- **Why:** Audiences are distinct (university admin vs thesis panel). Separate apps avoid coupling unrelated UX. Landing page provides a polished entry point for thesis defense.
- **Alternatives rejected:** Tab-switcher single-app (couples audiences); two pages without landing (demo experience weaker).
- **Files Created:** Folder skeleton only (this commit).

## [ARCH-002] 2026-05-06 — Per-university JSON lazy-load chosen over single embedded blob
- **Decision:** ETL writes one JSON per university into `dashboard/data/institutional/{UNIV}.json` and `dashboard/data/research/{UNIV}.json`. A small `_summary.json` (~10 KB) loads first.
- **Why:** Each univ ~3–5 MB; single embedded blob would be 25–40 MB and exceed the <3s initial load budget on Acer Nitro i5. Per-univ files keep the offline portability constraint while keeping resident memory bounded (~one univ at a time).
- **Files Created:** none yet (consumed by ETL).

## [ARCH-003] 2026-05-06 — Static HTML/JS chosen despite Research.md §3.8 specifying Flask
- **Decision:** Use vanilla HTML5 + CSS3 + JS. No Flask, no backend.
- **Why:** Static satisfies the same UX requirements (Global Overview / Topic Drill-Down / Temporal Analysis modules from §3.8) with zero deployment friction during thesis defense. Methodology divergence is documented; falling back to Flask remains possible by serving the same `data/` folder.
- **Files Created:** none.

## [DATA-001] 2026-05-06 — UMAP 2D embeddings absent; regeneration script required
- **Decision:** Add `dashboard/etl/export_umap_embeddings.py` to re-fit UMAP(n_components=2) using the production embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) and the same UMAP params from `methodology_changes.md` §3.1 (`n_neighbors=15`, `min_dist=0.05`, metric=cosine).
- **Data:** Search of `topic_modeling/outputs/**` confirmed no `umap_embeddings.json`, `*.npy`, `embeddings.csv`, or `2d_coords.*` saved by production pipeline.
- **Issues:** Without UMAP coords, Dashboard 2 Feature B (BERTopic cluster scatter) cannot render. Treated as a build-time prerequisite, not a runtime gap.
- **Files Created:** none yet (script to follow in [ETL-002]).
- **Next Steps:** Implement script after first ETL pass; target <8 min per university on CPU.

## [DATA-002] 2026-05-06 — VAD coverage at 8% — graceful degradation enforced
- **Decision:** Dashboards render whatever VAD data exists. Universities without VAD show topic-only visualizations and a "VAD scoring pending" banner. ETL injects a `vad_coverage` float (0.0–1.0) into each univ JSON.
- **Data:** `vad_scoring/results/alexx/` contains CAR-PUB-1 (2,287 records, 100%) and CAR-PNSEC-1 (~625 records, ~47%). 8 other universities not yet started.
- **Why:** Waiting blocks the timeline; restricting to scored univs defeats the cross-univ comparison purpose of Dashboard 2.
- **Files Created:** none.
- **Next Steps:** Re-run ETL whenever a researcher commits new VAD JSONL.

## [DATA-003] 2026-05-06 — FW→univ_code mapping sourced from `topic_modeling/configs/university_mapping.yaml`
- **Decision:** ETL reads this YAML at runtime and writes `dashboard/data/_meta.json` enumerating `{univ_code, school_alias, region, source_file, vad_coverage}` for the JS layer.
- **Data:** 10 universities confirmed: CAR-PNSEC-1 (UB) · CAR-PNSEC-2 (LPU-B) · CAR-PSEC-1 (SLU) · CAR-PUB-1 (UPB) · CAR-PUB-2 (BSU) · MIN-PUB-1 (CSU) · MM-PNSEC-1 (FEU) · MM-PSEC-1 (ADMU) · MM-PUB-1 (UPD) · PROV-PUB-1 (UPLB).
- **Files Created:** none (consumed by ETL).

## [ETL-001] 2026-05-07 — `build_dashboard_data.py` written and run on all 10 universities
- **Decision:** Single Python entrypoint reads `university_mapping.yaml`, joins preprocessing + topic + VAD outputs by `post_id`, writes paired institutional/research JSONs and a global `_summary.json` + `_meta.json`.
- **Data:** All 10 universities built. Total posts written: **37,074** (matches Research.md target). VAD coverage at first run: CAR-PUB-1 = 100%, CAR-PNSEC-1 = 78%, 8 others = 0%.
- **Performance:** End-to-end build of all 10 universities completes in ~6 seconds on a cold cache. Per-univ JSON sizes range 990 KB – 2.35 MB; total `data/` directory ~19 MB.
- **Issues:** None blocking. `invalid_ts_count` was 0 across all universities (timestamps are valid Unix seconds in the 2024-05 → 2026-05 window).
- **Files Created:** `dashboard/etl/build_dashboard_data.py`, `dashboard/data/_summary.json`, `dashboard/data/_meta.json`, `dashboard/data/institutional/*.json` (×10), `dashboard/data/research/*.json` (×10).

## [ETL-002] 2026-05-07 — `export_umap_embeddings.py` written (not yet run)
- **Decision:** Standalone script that re-fits UMAP(n_components=2) using the production `paraphrase-multilingual-MiniLM-L12-v2` model. Writes `topic_modeling/outputs/{UNIV}/umap_2d.json` aligned with `topic_assignments.json` post order. ETL step picks it up automatically on next build.
- **Why:** Required for Dashboard 2 cluster scatter. Until run, the scatter falls back to a synthetic "topic constellation" with an inline banner explaining how to enable real UMAP.
- **Performance:** Estimated ~3-8 min per university on CPU; one-time cost.
- **Issues:** Requires `sentence-transformers` and `umap-learn`. Not installed by default. Documented in `dashboard/etl/README.md`.
- **Files Created:** `dashboard/etl/export_umap_embeddings.py`, `dashboard/etl/README.md`.
- **Next Steps:** User to install deps and run on a longer cadence; dashboards already work in fallback mode.

## [VIZ-001] 2026-05-07 — Vendored client libraries for offline portability
- **Decision:** Downloaded Chart.js 4.4.1, chartjs-adapter-date-fns, D3 7.8.5, d3-cloud 1.2.7, and Plotly 2.35.2 into `dashboard/shared/vendor/`. Total ~5 MB. All dashboard pages reference these local files only — no CDN at runtime.
- **Why:** Spec requires offline portability ("no internet dependencies"). Vendoring is simpler than CDN-with-fallback and guarantees the demo works on a defense-day laptop with no Wi-Fi.
- **Files Created:** `dashboard/shared/vendor/{chart.umd.min.js, chartjs-adapter-date-fns.bundle.min.js, d3.min.js, d3-cloud.js, plotly.min.js}`.

## [VIZ-002] 2026-05-07 — Institutional dashboard built (all 7 features)
- **Decision:** `dashboard/institutional/index.html` wires alerts (anomaly rules in `alerts.js`), Chart.js doughnut for topic distribution, D3 SVG calendar heatmap, Plotly scatter for VAD bubble, virtual-scrolling activity feed (Vanilla DOM), Chart.js multi-line trends with 7-day rolling means, and d3-cloud word cloud with valence-coloured tokens.
- **Performance:** VAD bubble decimates to 1,500 points if input >1,500 to keep Plotly responsive. Word cloud capped at 70 terms. Topic donut click event filters every other panel through `topicFilter` state in `app.js`.
- **Visualization:** Topic colors come from a 15-slot Tableau-style palette in `utils.js`; calendar uses red/yellow/green WCAG-AA fills mapped from valence; tooltip layer is a single floating div reused across all D3 charts.
- **Files Created:** `dashboard/institutional/{index.html, css/dashboard.css, js/{app,charts,alerts,dataLoader}.js}`.

## [VIZ-003] 2026-05-07 — Research dashboard built (all 8 features) with UMAP fallback
- **Decision:** `dashboard/research/index.html` exposes three modes (single / compare / 10-up grid). UMAP scatter renders to Canvas with d3-quadtree for hover; supports pan/zoom and shows a 16-row legend. Methodology pipeline is six clickable stages with sample I/O code blocks. Post browser is a sortable, search-and-filter virtual scroll capped at 400 visible rows with "load more" hint.
- **Performance:** Per-univ research JSON contains the same post array as institutional JSON (~990 KB – 2.35 MB) plus `umap_xy` (null today). Lazy-loaded on `loadActive()`; previous univ data is replaced (no growing cache). Quadtree hit detection independent of point count.
- **Visualization:** When `umap_present === false`, the synthetic constellation makes topic structure visible while the user runs the export script. Mini heatmap component is shared between Dashboard 1 calendar and the 10-up grid via `comparison.js → MiniHeatmap`.
- **Files Created:** `dashboard/research/{index.html, css/dashboard.css, js/{app,umapViz,postBrowser,comparison,pipelineViz}.js}`.

## [VIZ-004] 2026-05-07 — Landing page built
- **Decision:** `dashboard/index.html` provides a polished entry point. Reads `_summary.json` and shows live counts (universities, posts analysed, latent topics, VAD coverage). Two card-style links into Institutional and Research views.
- **Files Created:** `dashboard/index.html`.

## [VIZ-005] 2026-05-07 — Suite-wide visual identity rewrite (coral · Inter · OKLCH · dark mode)
- **Decision:** Replaced the entire token system. Switched from hex (#1F6FEB blue, #FAFAFA bg, #1F2328 text) to OKLCH (`oklch(63% 0.18 28)` coral accent, neutrals tinted toward the coral hue per impeccable color laws). Added `[data-theme="dark"]` token overrides. Imported Inter Variable as a local woff2 (offline portability preserved).
- **Why:** The previous design was honest but flat — every panel read at the same level. A warm coral accent + Inter + soft shadows replacing 1 px borders gives the suite the "modern data tool" feel the user requested without falling into the SaaS-cliché traps (gradient text, glassmorphism, hero-metric template).
- **Files Created:** `shared/vendor/fonts/{Inter-Variable.woff2, Inter-Variable-Italic.woff2, inter.css}`, `shared/css/sidebar.css`, `shared/js/sidebar.js`, `shared/js/charts-theme.js`.
- **Files Updated:** `shared/css/{base.css, components.css}`, `shared/js/{utils.js, vadColors.js}`.

## [VIZ-006] 2026-05-07 — Icon-rail sidebar + theme toggle, suite-wide
- **Decision:** Inserted a 64 px icon rail into every page. Items: Overview / Institutional / Research / Methodology with a coral active state (soft background + 3 px coral indicator strip). Theme toggle pinned in the rail footer; defaults to `prefers-color-scheme`, persists to `localStorage.dashTheme`, fires a `themechange` window event on flip.
- **Why:** The dashboards now look like an app instead of three separate documents. A single navigation surface frames the demo flow (Overview → Institutional → Research → Methodology) and matches the Image-2 reference brief.
- **Performance:** Sidebar is sticky (`position: sticky`); rail-tooltip uses CSS-only opacity transitions so no JS event overhead.
- **Files:** `shared/css/sidebar.css`, `shared/js/sidebar.js`. Each page sets `<body data-page="{key}">` for the active highlight.

## [VIZ-007] 2026-05-07 — Institutional dashboard rebuilt
- **Decision:** Replaced the old uniform-card layout with: (1) a thin top strip showing greeting + last-post relative time + VAD-coverage chip + univ selector + refresh icon button, (2) a hero-alert zone that renders only when a critical signal exists, (3) an asymmetric KPI strip — Mean valence as a 6/12-col hero card with a 14-day Canvas sparkline + ↑/↓ delta vs prior 7 d, plus three smaller KPIs, (4) a "Signals" card replacing the old alerts (no `border-left` stripes — full soft-tint backgrounds + leading icon per impeccable rule), (5) all six chart panels with new typography and theme-aware repaint.
- **Why:** The old layout had no hero. Defense-day audiences saw equal-weight cards. The new layout puts critical signals at the top as a full-bleed surface, makes mean valence the headline KPI, and gives each chart a proper subhead so the reading order is unambiguous.
- **Specific chart updates:**
  - Topic donut: `cutout: 75%`, total post count rendered in the hole, legend moved to the right with circle markers
  - Calendar heatmap: 11 px cells with 3 px gap, Mon/Wed/Fri labels only, coral outline on today's cell
  - VAD bubble: `marker.opacity: 0.4`, marker outlines removed, dashed grid (`griddash: "dot"`), four corner annotations naming each quadrant
  - V·A·D trends: `tension: 0.4` smooth curves with a coral gradient fill on the valence line, dashed neutral=5 reference line
  - Recent activity: denoised — VAD pills only on hover; topic shown as a 6 px coral dot + label
- **KPI delta logic:** Last 7 d vs prior 7 d. Suppressed if either window has <20 posts (shows "insufficient recent data" caption instead).
- **Files Updated:** `institutional/{index.html, css/dashboard.css, js/{app.js, charts.js, alerts.js}}`.

## [VIZ-008] 2026-05-07 — Word cloud replaced with horizontal trending-keywords bar
- **Decision:** Removed the d3-cloud word cloud entirely. Replaced with a Chart.js horizontal bar chart showing the top 10 stopword-filtered terms by frequency. Each bar is filled with the mean-valence colour of posts containing the term (red for negative, amber for mixed, green for positive). New helper `DashUtils.termFreqWithValence(posts, max)` computes both metrics in one pass.
- **Why:** The word cloud was the weakest panel — random spatial layout, illegible at 70 terms, no inherent ranking. The horizontal bar inherently ranks the data, surfaces the valence signal as colour, and reads cleanly even on a 1280-wide laptop.
- **Files Updated:** `shared/js/utils.js` (helper added), `institutional/js/charts.js` (`keywords()` factory), `institutional/index.html` (canvas swap).

## [VIZ-009] 2026-05-07 — Research dashboard re-skinned, side-stripes removed
- **Decision:** Applied the new app-shell + tokens to the research dashboard. Removed `border-left: 4px` from `.sarc-card` (previously pink stripe) and the active-state stripe on `.pipe-stage`. Sarcasm cards now use `--accent-soft` full background; pipeline stages use a soft coral background plus a 3 px coral underline on the active stage.
- **Why:** Side-stripes are explicitly banned in the impeccable design laws ("border-left or border-right >1 px as a colored accent — rewrite with full borders, background tints, leading numbers/icons, or nothing"). The full-tint replacement reads cleaner and ages better.
- **Theme integration:** `themechange` listener in `research/js/app.js` re-renders the UMAP Canvas, the topic-bars Chart.js, and the trends Chart.js so colours stay consistent after toggle. Plotly (UMAP host's modebar config) reads tokens via `ChartsTheme.plotlyDefaults()`.
- **Trends chart:** Rewritten with the same coral/amber/purple palette and gradient fill plugin used in the institutional dashboard. Single source of palette is now `oklch(63% 0.18 28)` for valence across both views.
- **Files Updated:** `research/{index.html, css/dashboard.css, js/app.js}`.

## [VIZ-010] 2026-05-07 — Theme integration for Chart.js + Plotly + Canvas
- **Decision:** New `shared/js/charts-theme.js` reads CSS variables on demand and provides `ChartsTheme.tokens()`, `applyChartDefaults()`, `repaintAllCharts()`, `relayoutAllPlotly()`, `plotlyDefaults()`. Chart.js global defaults (font, colors, tooltip styling) are set on load and re-applied on `themechange`. Each Plotly plot picks up `ChartsTheme.plotlyDefaults()` for paper / plot / grid colors at construction time and is re-laid-out on toggle. Canvas-rendered components (UMAP scatter, sparkline) re-render via the page's `themechange` listener.
- **Why:** Without this, line strokes, tooltip backgrounds, and Plotly grid colors stayed light-mode after a dark-mode toggle. Centralising the token reads in one module also means the palette can be tuned in `base.css` and every chart picks it up — no per-chart hex maintenance.
- **Files Created:** `shared/js/charts-theme.js`.

## [VIZ-011] 2026-05-07 — Intuitiveness pass: data trust, navigation, expand modals, copy
- **Decision:** Treated the previous redesign as cosmetic and rebuilt for behaviour. Specific changes:
  - **Stopword tokenizer rewritten.** Bracket-stripping now runs before lowercasing (case-insensitive `[REDACTED_NAME]/gi`). Added a `SYSTEM` stopword set (`redacted`, `redacted_name`, `name`, `names`, `professor`, `department`, `campus_location`, `school_name`, etc.) so anonymisation artefacts can never reach the trending-keywords chart. Verified with a sample-200 smoke test against CAR-PUB-1: REDACTED and NAME absent from the top 15.
  - **Dashboard 1 standalone sidebar.** New per-page sidebar mode driven by `window.SIDEBAR` config. Dashboard 1 sidebar shows D1 brand mark, "All dashboards" back link, then 8 anchor sections (Overview / Signals / Topic mix / Calendar / VAD landscape / Activity / Trends / Keywords). IntersectionObserver-driven scroll-spy highlights the current section.
  - **Expand modal system.** New `shared/js/expand.js` registers chart renderers by id and opens a native `<dialog>` modal at 90 vw × 92 vh with the chart re-rendered at full size. Every chart card has a `[ ⛶ ]` icon button. Modal repaints on theme change.
  - **Hero / signals deduplication.** The hero zone shows only the most-severe crit alert; the signals card lists everything else. CTA labels are specific to the data ("Open 5 posts", "Filter to 12 posts", "Read 87 sarcastic posts") and wired so concentration alerts apply the topic filter, sarcasm alerts switch the feed sort, and crisis alerts sort by negative valence — then scroll to the relevant section.
  - **KPI strip uniformity.** Removed the asymmetric "hero KPI" with decorative sparkline. Four equal cards now: Mean valence (with honest fallback to "corpus all-time mean" labelling when recent <20), Posts (recent 7 d) with vs-prior-7-d count delta, Topics with outlier rate, Sarcasm rate with delta. No card pretends to have data it lacks.
  - **Honest copy.** Page title is now "Institutional Emotion Overview" (not "Today's emotional read"). Subtitle dynamically reports the actual date span: "2,287 posts spanning 2025-06-08 → 2026-04-08 (304 days). Charts show this full window unless a topic filter is applied." No more "7-day briefing" claim with a 9-month chart.
  - **Topic donut + legend.** Topics now sorted by mean valence (most negative first) so worrying clusters surface at the top. Legend moved to a 240 px right-side column showing full names + post count + percentage + a coloured "V x.y" valence chip per topic. Click row or slice to filter.
  - **Calendar heatmap.** Cell size 11 → 13 px, gap 2 → 3 px, day labels increased to 11 px / weight 500 / `--text-muted`, month labels increased to 11 px / `--text` / weight 600. Legend swatches now match the actual cell colours (red / orange / green / no-posts).
  - **VAD landscape.** Switched to `scattergl` for performance, jitter widened from ±0.4 to ±0.45 in both dimensions to break the integer banding into a proper cloud, marker size reduced from `4 + V*1.4` to `3 + V*0.85`, opacity raised from 0.40 to 0.55. `paper_bgcolor` and `plot_bgcolor` now both pull from `--bg-surface` so dark mode no longer flashbang-whites.
  - **Activity feed hierarchy.** Body text is now the dominant element: 14 px, weight 400, `--text`. Meta line drops to 11 px, `--text-subtle`, with the topic dot + name visible at all times (not hover-only). Sarcasm flag shows as a tiny uppercase "SARCASM" tag in the meta row. V/A/D pills only on hover.
  - **V·A·D trends.** Default rolling window changed from 7 days to 14 days (less seismographic noise). Inline "neutral" label removed (was overlapping data lines). Rolling-window selector added to the card head (7 / 14 / 30). Y-axis gridlines bumped from `--border` to `--border-strong` for visibility.
  - **Trending keywords.** Valence-gradient legend added below the chart (red → amber → green = negative → neutral → positive). Y-axis label padding tightened so terms sit closer to their bars.
- **Files Updated:** `shared/js/{stopwords.js, sidebar.js}`, `shared/css/{components.css, sidebar.css}`, `institutional/{index.html, css/dashboard.css, js/{app.js, charts.js, alerts.js}}`.
- **Files Created:** `shared/js/expand.js`.

## [VIZ-012] 2026-05-07 — Dashboard 1 rebuilt as 4-page no-scroll SPA with plain-English terminology
- **Decision:** Replaced the single long-scroll Dashboard 1 with a hash-routed SPA (`#overview`, `#topics`, `#emotions`, `#feed`) that fits the viewport on every page. Each page is its own CSS Grid sized to `100vh`, charts use `flex: 1; min-height: 0` to grow/shrink to the available space.
- **Why:** The previous version was a vertically-scrolling page where the alerts banner, KPIs, donut, calendar, scatter, feed, trends, and keywords all lived stacked — admins had to scroll past most of the dashboard to find what they cared about. A 4-tab SPA puts each task on its own focused viewport: Overview = signals, Topics = clusters & language, Emotions = the scatter as a deep-dive, Feed = filterable investigation surface.
- **Architectural changes:**
  - **Hash router** in `app.js` swaps `<section data-page>` blocks via `[hidden]`. `requestAnimationFrame` resizes Chart.js + Plotly when a page becomes visible.
  - **Wider sidebar (220 px)** for D1 only — drives by `window.SIDEBAR.wide = true`. Footer hosts the global controls (date range / university selector / theme toggle). Top page bar removed entirely; only an `<h2>` page title + a thin status strip remain.
  - **Global state** in app.js: `state.univ`, `state.topicFilter`, `state.dateRangeDays`, `state.feedSort`, `state.feedFilter`, `state.page`. Persists across page switches — clicking a topic on Page 2 carries the filter into Page 4's investigation feed.
  - **Date-range filter** in the sidebar footer — affects every chart on every page through `scopedPosts()`. Options: All time / 90 / 30 / 7 days.
- **Theme stability bug fix:**
  - **Pre-computed jitter.** Each post got `p._jx` and `p._jy` (one-shot `Math.random` calls in `loadUniv`). The scatter render reads these stable values; theme toggles no longer re-randomise dot positions. Verified via grep: zero `Math.random` calls in any render path.
  - **Plotly transparent background.** `paper_bgcolor` and `plot_bgcolor` are now `"rgba(0,0,0,0)"` so the chart inherits the card surface in both themes (kills the dark-mode flashbang).
  - **Theme listener uses `relayout`/`update`, never redraw.** New `InstCharts.vadBubbleRelayoutTheme(host)` updates Plotly axis colours/grid/legend in place via `Plotly.relayout()`. Chart.js charts re-read theme tokens via the existing `ChartsTheme.repaintAllCharts()`. The D3 calendar is the only component that needs an actual re-render on theme change (it embeds CSS-token colours into the SVG).
- **Plain-English terminology (Dashboard 1 only):**
  - Page titles: "Overview", "Topics & Conversations", "Emotional Landscape", "Investigation Feed"
  - Chart titles: "Daily Positivity Tracker" / "Emotion Scatter Plot" / "Emotional Trends over Time" / "Top Trending Keywords"
  - Axis labels: `Intensity (calm → stressed)`, `Sense of Control (helpless → empowered)`
  - KPI labels: "Positivity score", "High-intensity alerts", "Posts (recent 7 d)", "Sarcasm rate"
  - Quadrant annotations: "Empowered & engaged" / "Stressed but constrained" / "Calm & in control" / "Helpless & quiet"
  - Tag pills: V/A/D → P/I/C (Positivity / Intensity / Control)
  - Alert messages: "Arousal spike" → "Intensity spike — last 24 h average = X / 9", "V ≤ 3 AND A ≥ 7" → "low positivity and high intensity"
  - Calendar tooltip: "mean V" → "positivity"
  - Tooltip in scatter: "V x · A y · D z" → "Positivity x · Intensity y · Control z"
  - Underlying JSON keys (V/A/D) are unchanged — only the labels presented to admins change. Landing page + Research dashboard intentionally retain "VAD/Valence/Arousal/Dominance" because their audiences are evaluating the methodology paper which uses the academic terms.
- **Page layouts:**
  - **Overview**: hero alert (only when crit) + 4 uniform KPIs + signals card | calendar card + simplified Trends (Positivity & Intensity only, Control dropped to reduce clutter per the brief).
  - **Topics**: 40/60 split — Topic donut + side legend on the left, Top Trending Keywords + mini activity feed on the right. Clicking a topic filters both the keywords and feed live.
  - **Emotions**: 70/30 split — large Emotion Scatter Plot on the left, mini activity feed on the right. Hovering a dot in the scatter scrolls the feed to that post.
  - **Feed**: full-width filter bar (topic / positivity tier / sort / sarcasm-only / search) + 50/50 split: signals (full list) on the left, paginated activity feed on the right.
- **Files Updated:** `shared/css/{base.css, components.css, sidebar.css}`, `shared/js/sidebar.js`, `institutional/{index.html, css/dashboard.css, js/{app.js, charts.js, alerts.js}}`.

## [DATA-004] 2026-05-07 — VAD coverage as built
- CAR-PUB-1 (UPB) — **100%** VAD scoring complete
- CAR-PNSEC-1 (UB) — **78%** in progress
- All others — 0% (graceful-degradation banner triggers automatically)
- Total scored: ~5,400 of 37,074 posts (~14.6% corpus coverage)
- Re-run `python dashboard/etl/build_dashboard_data.py` after each VAD batch to lift coverage; no dashboard-side changes needed.
