/* Theme integration for Chart.js + Plotly.
   Reads CSS variables on demand so a single source of truth. Repaints chart instances on `themechange`. */
(function () {
  function tokens() {
    const cs = getComputedStyle(document.documentElement);
    const get = (k) => cs.getPropertyValue(k).trim();
    return {
      text:        get("--text"),
      muted:       get("--text-muted"),
      subtle:      get("--text-subtle"),
      border:      get("--border"),
      borderStrong:get("--border-strong"),
      surface:     get("--bg-surface"),
      app:         get("--bg-app"),
      bgSubtle:    get("--bg-subtle"),
      accent:      get("--accent"),
      ok:          get("--ok"),
      crit:        get("--crit"),
      warn:        get("--warn"),
    };
  }

  function applyChartDefaults() {
    if (typeof Chart === "undefined") return;
    const t = tokens();
    Chart.defaults.color = t.muted;
    Chart.defaults.font.family = '"Inter", ui-sans-serif, system-ui, sans-serif';
    Chart.defaults.font.size = 11.5;
    Chart.defaults.borderColor = t.border;
    if (Chart.defaults.scale) {
      Chart.defaults.scale.grid = Chart.defaults.scale.grid || {};
      Chart.defaults.scale.grid.color = t.border;
    }
    Chart.defaults.plugins = Chart.defaults.plugins || {};
    Chart.defaults.plugins.legend = Chart.defaults.plugins.legend || {};
    Chart.defaults.plugins.legend.labels = Object.assign({}, Chart.defaults.plugins.legend.labels, {
      color: t.muted, boxWidth: 10, boxHeight: 10, font: { size: 11 },
    });
    Chart.defaults.plugins.tooltip = Object.assign({}, Chart.defaults.plugins.tooltip, {
      backgroundColor: "oklch(20% 0.015 280)",
      titleColor: "oklch(96% 0.005 30)",
      bodyColor: "oklch(96% 0.005 30)",
      borderColor: "transparent",
      padding: 10,
      cornerRadius: 8,
      titleFont: { weight: 600, size: 12 },
      bodyFont: { size: 12 },
      displayColors: false,
    });
  }

  function repaintAllCharts() {
    if (typeof Chart === "undefined") return;
    applyChartDefaults();
    const t = tokens();
    Chart.instances && Object.values(Chart.instances).forEach(ch => {
      if (!ch || !ch.options) return;
      const scales = ch.options.scales || {};
      Object.values(scales).forEach(sc => {
        if (sc.grid)   sc.grid.color   = t.border;
        if (sc.ticks)  sc.ticks.color  = t.muted;
        if (sc.title)  sc.title.color  = t.muted;
      });
      const legendOpts = ch.options.plugins && ch.options.plugins.legend;
      if (legendOpts && legendOpts.labels) legendOpts.labels.color = t.muted;
      /* Active rather than "none" so plugins (neutral line, low-activity shading,
         custom legend swatch) re-execute their afterDraw / generateLabels with
         the new theme tokens. */
      ch.update();
    });
  }

  function relayoutAllPlotly() {
    if (typeof Plotly === "undefined") return;
    const t = tokens();
    document.querySelectorAll(".js-plotly-plot").forEach(el => {
      try {
        Plotly.relayout(el, {
          paper_bgcolor: t.surface,
          plot_bgcolor: t.surface,
          "xaxis.gridcolor": t.border,
          "yaxis.gridcolor": t.border,
          "xaxis.zerolinecolor": t.border,
          "yaxis.zerolinecolor": t.border,
          "xaxis.color": t.muted,
          "yaxis.color": t.muted,
          "legend.font.color": t.muted,
        });
      } catch (_) {}
    });
  }

  function plotlyDefaults() {
    const t = tokens();
    return {
      paper_bgcolor: t.surface,
      plot_bgcolor: t.surface,
      font: { family: '"Inter", ui-sans-serif, system-ui, sans-serif', color: t.muted, size: 11 },
      xaxis: { gridcolor: t.border, zerolinecolor: t.border, linecolor: t.border, color: t.muted, gridwidth: 1 },
      yaxis: { gridcolor: t.border, zerolinecolor: t.border, linecolor: t.border, color: t.muted, gridwidth: 1 },
    };
  }

  applyChartDefaults();
  window.addEventListener("themechange", () => {
    applyChartDefaults();
    repaintAllCharts();
    relayoutAllPlotly();
  });

  window.ChartsTheme = { tokens, applyChartDefaults, repaintAllCharts, relayoutAllPlotly, plotlyDefaults };
})();
