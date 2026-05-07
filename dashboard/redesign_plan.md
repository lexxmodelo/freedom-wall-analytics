# Dashboard Redesign Plan — Suite-Wide Refresh

## Context

The suite currently looks like a clean academic SaaS dashboard: white cards, 1 px borders, blue accent, system fonts, light-mode only. The aesthetic is honest but flat — no visual hierarchy between alerts and the word cloud, type scale is shallow, and every panel reads as the same level of importance. This redesign moves toward the Image-2 reference (warm coral accent, Inter, soft shadows instead of borders, sidebar nav, dark/light mode, KPI deltas, smoother charts).

Scope decisions confirmed:

| Decision | Choice |
|---|---|
| Reach | **Suite-wide** — landing, Institutional, Research |
| Navigation | **Icon-rail sidebar** + theme toggle in footer |
| KPI deltas | **Last 7 d vs prior 7 d** (suppress when either window <20 posts) |
| Word-cloud replacement | **Horizontal bar chart** — top 10 terms by frequency, bar tinted by mean valence |

## Honest tensions with the brief

Two parts of the brief collide with the impeccable design laws. Calling them out so the plan handles them deliberately:

1. **Side-stripe borders are banned.** Current `.alert-row` uses `border-left: 4px` in warn/crit color. The brief asks for soft-red backgrounds — good, that already replaces the stripe. I'll fully remove `border-left` accents anywhere they appear (alerts, sarc-card, pipe-stage in research view) and use background tint + leading icon + full border instead.
2. **Symmetric KPI strips read as the SaaS hero-metric cliché.** The brief's "Total Revenue" reference is exactly the cliché. I'll keep the trend deltas (genuinely useful) but break the symmetry: the leading KPI ("Mean valence" or "Active alerts") gets a larger card with a sparkline; the other three are smaller, denser, no icon. Different shape, same information.

Plus a small craft note: the brief recommends an icon next to every KPI title. I'll only use icons where they add disambiguation (alert count, sarcasm rate). Decorative icons on every KPI tip into the cliché.

## Token system

A single replacement for `shared/css/base.css`. OKLCH values used (per impeccable laws — no `#000`, no `#fff`, neutrals tinted toward the brand hue).

```css
:root {
  /* App surfaces */
  --bg-app:      oklch(98.5% 0.005 30);    /* warm off-white, hint of coral */
  --bg-surface:  oklch(100% 0 0);          /* pure white cards */
  --bg-subtle:   oklch(96% 0.008 30);      /* table heads, wells */
  --bg-elevated: oklch(99% 0.005 30);      /* hover, subtle lifts */

  /* Borders — extremely subtle in light mode */
  --border:        oklch(94% 0.005 30);
  --border-strong: oklch(88% 0.008 30);

  /* Text */
  --text:        oklch(20% 0.015 280);     /* slate-tinted, not pure black */
  --text-muted:  oklch(45% 0.012 280);
  --text-subtle: oklch(60% 0.008 280);

  /* Coral accent (#E55B4B family) */
  --accent:       oklch(63% 0.18 28);
  --accent-hover: oklch(58% 0.18 28);
  --accent-soft:  oklch(94% 0.04 28);
  --on-accent:    oklch(99% 0.005 30);

  /* Status — kept distinct from coral */
  --warn:      oklch(75% 0.15 75);          /* amber */
  --warn-soft: oklch(95% 0.05 75);
  --crit:      oklch(60% 0.20 22);          /* deeper red than coral */
  --crit-soft: oklch(94% 0.04 22);
  --ok:       oklch(60% 0.14 155);
  --ok-soft:  oklch(94% 0.04 155);
  --trend-up:   var(--ok);
  --trend-down: var(--crit);

  /* Type — Inter via local @font-face */
  --font-sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;

  /* Type scale — deeper hierarchy (≥1.25 ratio) */
  --fs-hero: 32px;   /* page title, KPI lead */
  --fs-h1:   24px;
  --fs-h2:   18px;
  --fs-body: 14px;
  --fs-small:12px;
  --fs-micro:11px;
  --tracking-tight: -0.02em;
  --tracking-label: 0.06em;

  /* Geometry */
  --radius-sm: 8px;
  --radius:    12px;
  --radius-lg: 16px;
  --radius-xl: 20px;

  /* Shadows — soft, not 1 px borders */
  --shadow-sm: 0 1px 2px oklch(20% 0.015 280 / 0.04);
  --shadow:    0 4px 16px oklch(20% 0.015 280 / 0.04), 0 1px 2px oklch(20% 0.015 280 / 0.03);
  --shadow-lg: 0 12px 32px oklch(20% 0.015 280 / 0.06), 0 2px 4px oklch(20% 0.015 280 / 0.04);

  /* Sidebar dimensions */
  --rail-w: 64px;

  /* Motion */
  --ease-out:  cubic-bezier(0.22, 1, 0.36, 1);
  --ease-quart: cubic-bezier(0.165, 0.84, 0.44, 1);
}

[data-theme="dark"] {
  --bg-app:      oklch(18% 0.015 280);     /* not pure black; warm-cool slate */
  --bg-surface:  oklch(22% 0.015 280);
  --bg-subtle:   oklch(25% 0.013 280);
  --bg-elevated: oklch(28% 0.013 280);
  --border:        oklch(30% 0.012 280);
  --border-strong: oklch(40% 0.012 280);
  --text:        oklch(96% 0.005 30);
  --text-muted:  oklch(75% 0.008 280);
  --text-subtle: oklch(58% 0.012 280);
  --accent:       oklch(72% 0.16 28);       /* slightly lifted for dim contrast */
  --accent-soft:  oklch(35% 0.10 28 / 0.30);
  --warn:      oklch(82% 0.14 75);
  --warn-soft: oklch(35% 0.10 75 / 0.30);
  --crit:      oklch(70% 0.18 22);
  --crit-soft: oklch(35% 0.10 22 / 0.30);
  --ok:        oklch(72% 0.13 155);
  --ok-soft:   oklch(35% 0.10 155 / 0.30);
  --shadow-sm: 0 1px 2px oklch(0% 0 0 / 0.30);
  --shadow:    0 4px 16px oklch(0% 0 0 / 0.35), 0 1px 2px oklch(0% 0 0 / 0.25);
  --shadow-lg: 0 12px 32px oklch(0% 0 0 / 0.50), 0 2px 4px oklch(0% 0 0 / 0.35);
}
```

## Inter font — offline

Download Inter (Variable, woff2) into `dashboard/shared/vendor/fonts/`:

```
shared/vendor/fonts/
├── Inter-Variable.woff2
├── Inter-Variable-Italic.woff2
└── inter.css                    # @font-face declarations
```

Source: `https://rsms.me/inter/inter.css` adapted to relative paths so the suite stays portable. Two weights via `font-variation-settings`. Total weight ~330 KB woff2.

## App-shell rewrite

The current `.app-shell` is a `max-width: 1400px` container. Replace with a sidebar + content shell:

```
┌─────┬─────────────────────────────────────────┐
│  ▢  │ Greeting · timestamp                    │  ← thin top bar (32 px)
│  ▣  ├─────────────────────────────────────────┤
│  ▢  │                                         │
│  ▢  │           PAGE CONTENT                  │
│  ▢  │                                         │
│     │                                         │
│ 🌗  │                                         │
└─────┴─────────────────────────────────────────┘
 64px
```

Sidebar items: **Overview (home)** · **Institutional** · **Research** · **Methodology** (anchor scroll on Research page). Active state = coral icon, soft coral background. Theme toggle pinned at bottom (sun / moon icon).

`shared/js/sidebar.js` (new) renders the rail into every page. `data-active` attribute on the body decides the highlight. This avoids 3-way HTML duplication. Theme toggle persists choice in `localStorage.dashTheme`; on first load uses `prefers-color-scheme`.

## Per-page changes

### Landing page (`dashboard/index.html`)

- App-shell with sidebar (active: Overview).
- Hero headline scaled to 56 px (display weight 600, tracking -0.02em).
- Stats strip becomes 4 KPI cards with trend deltas (where computable from `_summary.json`).
- Two deck cards: keep two-column on desktop; remove the radial-gradient ribbon (looks generic) — replace with a single coral underline at the bottom of each card.
- Add a tiny "What you'll see" preview row (3 thumbnails of representative charts) above the deck cards.

### Institutional dashboard (the focus)

Layout grid changes (12-col flexible):

```
┌──────────────────────────────────────────────────────────┐
│ Greeting + univ selector + last-updated                  │ ← top strip
├──────────────────────────────────────────────────────────┤
│ HERO ALERT (full width, only renders if any crit alerts) │ ← new
├──────────┬──────────┬──────────┬─────────────────────────┤
│  KPI 1   │  KPI 2   │  KPI 3   │   KPI 4                 │
│  hero    │  smaller │  smaller │   smaller               │ ← varied sizes
│  + spark │          │          │                         │
├──────────┴──────────┴──────────┴─────────────────────────┤
│ Topic donut         │ Calendar of valence                │
│ (75% cutout, total  │ (annotated, "today" marker)        │
│ in centre)           │                                    │
├─────────────────────┼────────────────────────────────────┤
│ VAD bubble          │ Recent activity                    │
│ (quadrant labels)   │ (de-noised cards)                  │
├─────────────────────┼────────────────────────────────────┤
│ V·A·D trends        │ Top trending keywords              │
│ (smooth + gradient) │ (horizontal bars, valence-tinted)  │
├─────────────────────┴────────────────────────────────────┤
│ Footer                                                    │
└──────────────────────────────────────────────────────────┘
```

Per-panel updates:

- **Top strip** — single row: greeting ("Today, MM-PSEC-1") + univ selector + last-updated relative time + manual refresh icon button (right). No more two-line header.
- **Hero alert** — only renders if `alerts.compute()` returns any `crit` items. Soft-red full-bleed surface, large icon, alert title at h1 size, "Review" button on the right that scrolls to relevant panel. If only `warn` items: collapse into the alerts card below (no hero). If empty: show calm-state card with a small green check + reassuring copy.
- **KPI strip** — varied sizing. KPI 1 is wider (spans 2 cols), shows mean valence with a 14-day micro-sparkline drawn on Canvas. KPIs 2-4 are smaller, no sparkline, but each has a `↑/↓ delta vs prior 7 d` line in `--trend-up` or `--trend-down`. Suppress the delta when either window has <20 posts; show a tiny "(insufficient recent data)" caption instead.
- **Alerts card** — renamed "Signals". Each row: full-width soft-coral or soft-amber background (no left stripe), 16 px coral icon, alert title in body weight, "Review →" button right-aligned. Hover lifts the row 1 px via box-shadow.
- **Topic donut** — Chart.js `cutout: '75%'`. Total post count + "posts" label rendered as absolute-positioned div in the center. Legend moved to a clean two-column list below the donut, sorted by size. Click slice → unchanged behavior.
- **Calendar heatmap** — keep D3 SVG but: thinner cells (10 px instead of 13 px), gap 3 px, day labels Mon/Wed/Fri only, month labels in muted small-caps. Add a subtle vertical "today" line and a 4-stop legend below (no posts / negative / mixed / positive).
- **VAD bubble** — Plotly. Set `marker.opacity: 0.4`, remove marker outlines. Replace solid grid with dashed grid (`gridcolor: oklch-converted, gridwidth: 1, dash: 'dot'`). Add four corner annotations as Plotly text annotations: top-right "Empowered & engaged", top-left "Aroused but constrained", bottom-right "Calm & in control", bottom-left "Helpless & calm". Trace count stays per-topic but legend moves below the chart in two rows of small chips.
- **Recent activity** — denoise: drop the V/A/D pill row, leave only the topic chip (now 6 px coral dot + topic label) + body text + timestamp. Sarcasm flag becomes a small 🌀 prefix on the timestamp line. Hover reveals the V/A/D values in a small inline expanded row below the post text.
- **V·A·D trends** — Chart.js with `tension: 0.4` and per-line gradient fill (using a Chart.js plugin function that builds a CanvasGradient on first render). Remove vertical grid; horizontal grid only. Add a thin reference line at y=5 (neutral). Y-axis labels every 2 (1, 3, 5, 7, 9). Add a small "today" tick on the x-axis.
- **Trending keywords** — new component (replaces word cloud). Horizontal Chart.js bar chart, top 10 terms after Taglish/English stopword removal. Bar fill color is the valence color of that term (mean V over posts containing it). Term frequency printed at end of bar. Hover reveals: count + mean V + "appears in N posts".

### Research dashboard

- Same app-shell + sidebar.
- Pipeline diagram becomes more visual: each stage gets a soft coral icon and connecting hairlines (no boxy chips).
- Summary table becomes a sticky-header card with the same coral hover state. Bar visualizations on counts.
- UMAP scatter card gets the new dark-mode-aware background gradient.
- Sarcasm "showcase" cards drop the `border-left: 4px` (banned) and use `--accent-soft` background instead.
- Methodology stage detail block keeps its dark code preview block — but the surrounding card uses the new tokens.

## New / modified files

```
shared/css/base.css                     ← REWRITE: token system, Inter, dark mode
shared/css/components.css               ← REWRITE: cards, KPIs, sidebar, signals, banners
shared/css/sidebar.css                  ← NEW: rail + theme toggle styles
shared/js/sidebar.js                    ← NEW: render rail, theme toggle, persistence
shared/js/charts-theme.js               ← NEW: Chart.js + Plotly default themes that read CSS vars and react to theme switches
shared/js/utils.js                      ← +rolling-window deltas, +sparkline draw helper
shared/vendor/fonts/Inter-*.woff2       ← NEW: Inter Variable + italic, ~330 KB
shared/vendor/fonts/inter.css           ← NEW: @font-face block

dashboard/index.html                    ← REWRITE: hero + sidebar + KPI strip
institutional/index.html                ← REWRITE: hero alert + 12-col layout
institutional/css/dashboard.css         ← REWRITE: per-panel tweaks
institutional/js/charts.js              ← UPDATE: thin donut + center text, smooth gradient line, annotated bubble, replace wordCloud with horizontalBars
institutional/js/alerts.js              ← UPDATE: signals rendering with full-bleed soft tint, no left stripe; +heroAlert() for crits
institutional/js/app.js                 ← UPDATE: KPI delta computation, sparkline, hero-alert render, top-strip layout

research/index.html                     ← UPDATE: sidebar shell, removed `compare-only` styling reuse, soft-tint pipeline stages
research/css/dashboard.css              ← UPDATE: token-driven, drop border-left
research/js/app.js                      ← UPDATE: sidebar init, theme-aware Plotly redraws on toggle

action_log.md                           ← APPEND: redesign entries [VIZ-005…VIZ-010]
```

## Reusable functions added to `shared/js/utils.js`

```js
// Last-7-days vs prior-7-days delta. Returns { current, previous, delta, sufficient }
DashUtils.windowDelta(posts, key, anchorTs)

// Sparkline. Renders a 1-line value series into a small canvas.
DashUtils.sparkline(canvas, values, color)

// Build a Chart.js gradient fill from current theme tokens.
DashUtils.lineGradient(ctx, color, height)
```

## Theme toggle behavior

```js
// Pseudocode for shared/js/sidebar.js
const stored = localStorage.getItem("dashTheme");
const sysDark = matchMedia("(prefers-color-scheme: dark)").matches;
const initial = stored || (sysDark ? "dark" : "light");
document.documentElement.dataset.theme = initial;

toggleEl.addEventListener("click", () => {
  const next = (document.documentElement.dataset.theme === "dark") ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("dashTheme", next);
  window.dispatchEvent(new Event("themechange"));
});
```

Charts re-read CSS variables on `themechange` and call `chart.update()` / `Plotly.relayout()`. This is critical — without it, line/bar charts retain their light-mode stroke colors after a toggle.

## Motion

- Card lift on hover: `transform: translateY(-1px)` + shadow swap, 200 ms `var(--ease-out)`.
- Theme toggle: 200 ms ease-out cross-fade on body background; charts animate via Chart.js built-in.
- Topic donut: animated arc reveal on first paint and on every filter change (Chart.js default, set `animation.duration: 600`).
- Sidebar active-state indicator: soft slide.
- No bounce, no elastic, no decorative motion.

## Accessibility / craft notes

- Hit targets ≥ 32 × 32 px on the rail.
- All status colors meet WCAG AA on their respective backgrounds in both themes (verified via `oklch` lightness contrast — ≥4.5:1).
- `prefers-reduced-motion: reduce` disables hover lifts, donut animation, theme cross-fade.
- Theme toggle is a `<button>` with `aria-pressed` and `aria-label="Switch to dark theme"`.
- Sidebar items are `<a>` with `aria-current="page"` on active.
- Inter font loads with `font-display: swap`.

## Execution order

1. **Tokens + Inter** — rewrite `base.css`, drop in fonts, swap to OKLCH. Verify nothing renders broken (the existing components keep working with new tokens).
2. **Sidebar + theme toggle** — add `sidebar.js`, `sidebar.css`. Inject into landing first; verify theme persistence and toggle event flow before propagating.
3. **Components.css rewrite** — cards, KPIs, signals, banners, tags. This is the biggest file change.
4. **Charts theme module** — `charts-theme.js` so Chart.js + Plotly read tokens and respond to `themechange`.
5. **Landing page** — apply shell + KPIs + hero typography.
6. **Institutional dashboard** — top strip, hero alert, varied KPI strip with deltas + sparkline, then panel-by-panel updates.
7. **Trending keywords** — replace word cloud last (genuine new component).
8. **Research dashboard** — apply shell + token sweep; minor panel tweaks only.
9. **Verification** — toggle theme repeatedly, switch univs, run keyboard + reduced-motion check, run on the data with 0% VAD coverage to confirm degraded states still look intentional.
10. **action_log.md** — close out with VIZ-005…VIZ-010 entries documenting decisions.

Estimated effort: 8–10 hours of focused work, mostly mechanical after the token system lands.

## What I'm explicitly **not** doing

- Not redesigning the post-browser table in Research (current grid is fine).
- Not adding a dashboard-3 or new ETL features — pure UI redesign.
- Not changing chart libraries (Chart.js / D3 / Plotly stay).
- Not introducing a UI framework (vanilla JS still).
- Not adding decorative gradient text / blur backdrops / glassmorphism.
- Not adding entrance animations beyond Chart.js defaults — page-level animations slow the demo.

## Verification

After build:

- Toggle theme 5+ times on each page. No FOUC, all charts repaint correctly.
- Switch universities while in dark mode. KPI deltas, sparkline, donut center text re-render with new data.
- Open Institutional view of a 0% VAD university. Confirm: hero alert hidden, KPI deltas show "—" with tooltip, trends panel shows the friendly empty state, trending keywords still renders (frequency works without VAD).
- Run Lighthouse a11y on Institutional in both themes — target ≥95.
- View on a 1280 × 720 laptop (Acer Nitro target) — sidebar stays, content fits without horizontal scroll.

---

**Ready to execute on your sign-off.** If this plan is right, I'll start with the token system + sidebar (steps 1-2) and check in once the landing page looks correct in both themes; the rest is mostly mechanical from there.
