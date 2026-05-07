/* Shared dashboard utilities. Exposed on window.DashUtils. */
(function () {
  const fmt = {
    int: (n) => (n == null ? "—" : Number(n).toLocaleString()),
    pct: (n, digits = 0) => (n == null ? "—" : (n * 100).toFixed(digits) + "%"),
    num: (n, digits = 2) => (n == null ? "—" : Number(n).toFixed(digits)),
    date: (unix) => unix == null ? "—" : new Date(unix * 1000).toISOString().slice(0, 10),
    datetime: (unix) => unix == null ? "—" : new Date(unix * 1000).toISOString().replace("T", " ").slice(0, 16),
    truncate: (s, max = 80) => !s ? "" : (s.length <= max ? s : s.slice(0, max - 1).trimEnd() + "…"),
    label: (s, max = 18) => !s ? "" : (s.length <= max ? s : s.slice(0, max - 1) + "…"),
    relative: (unix) => {
      if (unix == null) return "—";
      const diff = Date.now() / 1000 - unix;
      if (diff < 60) return "just now";
      if (diff < 3600) return Math.floor(diff / 60) + " min ago";
      if (diff < 86400) return Math.floor(diff / 3600) + " h ago";
      if (diff < 86400 * 7) return Math.floor(diff / 86400) + " d ago";
      return new Date(unix * 1000).toISOString().slice(0, 10);
    },
  };

  const cache = new Map();
  async function loadJSON(path) {
    if (cache.has(path)) return cache.get(path);
    const p = fetch(path).then(r => {
      if (!r.ok) throw new Error(`Failed ${path}: ${r.status}`);
      return r.json();
    });
    cache.set(path, p);
    return p;
  }

  /* Wire global info-hint elements once. Any element with class="info-hint"
     and data-hint="text" shows a floating tooltip on hover or focus. */
  function wireInfoHints() {
    if (window.__infoHintsWired) return;
    window.__infoHintsWired = true;
    const tip = tooltip();
    document.addEventListener("mouseover", (ev) => {
      const t = ev.target.closest(".info-hint");
      if (!t) return;
      tip.show(t.dataset.hint || "", ev);
    });
    document.addEventListener("mouseout", (ev) => {
      const t = ev.target.closest(".info-hint");
      if (t) tip.hide();
    });
    document.addEventListener("focusin", (ev) => {
      const t = ev.target.closest(".info-hint");
      if (!t) return;
      const r = t.getBoundingClientRect();
      tip.show(t.dataset.hint || "", { clientX: r.left + r.width / 2, clientY: r.top });
    });
    document.addEventListener("focusout", (ev) => {
      const t = ev.target.closest(".info-hint");
      if (t) tip.hide();
    });
  }

  function tooltip() {
    let el = document.querySelector(".tooltip");
    if (!el) {
      el = document.createElement("div");
      el.className = "tooltip";
      document.body.appendChild(el);
    }
    return {
      show(html, ev) {
        el.innerHTML = html;
        el.classList.add("show");
        el.style.left = (ev.clientX + 14) + "px";
        el.style.top  = (ev.clientY + 14) + "px";
      },
      move(ev) {
        el.style.left = (ev.clientX + 14) + "px";
        el.style.top  = (ev.clientY + 14) + "px";
      },
      hide() { el.classList.remove("show"); },
    };
  }

  function rollingMean(values, window = 7) {
    const out = new Array(values.length).fill(null);
    let sum = 0, n = 0;
    const buf = [];
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (typeof v === "number") { sum += v; n++; buf.push(v); }
      else { buf.push(null); }
      if (buf.length > window) {
        const drop = buf.shift();
        if (typeof drop === "number") { sum -= drop; n--; }
      }
      out[i] = n > 0 ? sum / n : null;
    }
    return out;
  }

  function groupByDay(posts) {
    const m = new Map();
    for (const p of posts) {
      if (!p.ts) continue;
      const day = fmt.date(p.ts);
      if (!m.has(day)) m.set(day, []);
      m.get(day).push(p);
    }
    return m;
  }

  function dateRange(start, end) {
    const out = [];
    const a = new Date(start + "T00:00:00Z");
    const b = new Date(end + "T00:00:00Z");
    for (let d = new Date(a); d <= b; d.setUTCDate(d.getUTCDate() + 1)) {
      out.push(d.toISOString().slice(0, 10));
    }
    return out;
  }

  /* Topic color — anchored to coral hue, rotates around the wheel. */
  function topicColor(tid) {
    if (tid === -1) return "oklch(70% 0.005 280)"; // noise = neutral grey
    const hues = [28, 200, 145, 290, 75, 240, 12, 170, 260, 50, 320, 110, 220, 30, 180];
    const i = ((tid % hues.length) + hues.length) % hues.length;
    return `oklch(60% 0.16 ${hues[i]})`;
  }

  /* Last 7 d vs prior 7 d delta on a numeric VAD field. Suppressed if either window has <minPosts. */
  function windowDelta(posts, key, anchorTs, minPosts = 20) {
    if (!anchorTs) return { current: null, previous: null, delta: null, sufficient: false };
    const W = 7 * 86400;
    const cur = [], prev = [];
    for (const p of posts) {
      if (!p.ts || p[key] == null) continue;
      const dt = anchorTs - p.ts;
      if (dt >= 0 && dt < W) cur.push(p[key]);
      else if (dt >= W && dt < 2 * W) prev.push(p[key]);
    }
    const sufficient = cur.length >= minPosts && prev.length >= minPosts;
    if (!sufficient) return { current: null, previous: null, delta: null, sufficient: false, n_cur: cur.length, n_prev: prev.length };
    const mean = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;
    const c = mean(cur), p = mean(prev);
    return { current: c, previous: p, delta: c - p, sufficient: true, n_cur: cur.length, n_prev: prev.length };
  }

  /* Render a sparkline into an HTMLCanvasElement. values: array of numbers (nulls allowed). */
  function sparkline(canvas, values, color, opts = {}) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = canvas.clientWidth || canvas.width;
    const H = canvas.clientHeight || canvas.height;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);
    const pts = values.map((v, i) => v == null ? null : [i, v]).filter(Boolean);
    if (pts.length < 2) return;
    const xs = pts.map(p => p[0]);
    const ys = pts.map(p => p[1]);
    const xMin = Math.min(...xs), xMax = Math.max(...xs);
    const yMin = opts.yMin ?? Math.min(...ys);
    const yMax = opts.yMax ?? Math.max(...ys);
    const xPad = 2, yPad = 4;
    const sx = (x) => xPad + ((x - xMin) / Math.max(1, xMax - xMin)) * (W - 2 * xPad);
    const sy = (y) => H - yPad - ((y - yMin) / Math.max(0.0001, yMax - yMin)) * (H - 2 * yPad);
    // Area fill (gradient)
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, color.replace("oklch(", "oklch(").replace(")", " / 0.32)"));
    grad.addColorStop(1, color.replace(")", " / 0)"));
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(sx(pts[0][0]), H - yPad);
    pts.forEach(([x, y]) => ctx.lineTo(sx(x), sy(y)));
    ctx.lineTo(sx(pts[pts.length - 1][0]), H - yPad);
    ctx.closePath();
    ctx.fill();
    // Stroke
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.lineJoin = "round";
    ctx.beginPath();
    pts.forEach(([x, y], i) => {
      const X = sx(x), Y = sy(y);
      if (i === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
    });
    ctx.stroke();
  }

  /* Build a vertical canvas gradient for Chart.js area fill (color → transparent). */
  function lineGradient(ctx, color, height) {
    const g = ctx.createLinearGradient(0, 0, 0, height);
    const start = color.replace(")", " / 0.18)");
    const end = color.replace(")", " / 0)");
    g.addColorStop(0, start);
    g.addColorStop(1, end);
    return g;
  }

  /* Chart.js plugin: fills under a line dataset using lineGradient. */
  const gradientFillPlugin = {
    id: "gradientFill",
    beforeDatasetsDraw(chart) {
      chart.data.datasets.forEach((ds, i) => {
        if (!ds.fill || !ds.borderColor) return;
        const meta = chart.getDatasetMeta(i);
        if (!meta || !meta.dataset) return;
        ds.backgroundColor = lineGradient(chart.ctx, ds.borderColor, chart.chartArea.height);
      });
    },
  };

  function termFreqWithValence(posts, max = 10) {
    if (!window.Stopwords) return [];
    const f = new Map();
    const v = new Map();
    const vc = new Map();
    for (const p of posts) {
      const tokens = new Set(window.Stopwords.tokenize(p.text || ""));
      for (const w of tokens) {
        f.set(w, (f.get(w) || 0) + 1);
        if (p.V != null) {
          v.set(w, (v.get(w) || 0) + p.V);
          vc.set(w, (vc.get(w) || 0) + 1);
        }
      }
    }
    return [...f.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, max)
      .map(([word, count]) => ({
        word,
        count,
        meanV: vc.get(word) ? v.get(word) / vc.get(word) : null,
      }));
  }

  window.DashUtils = {
    fmt, loadJSON, tooltip, wireInfoHints,
    rollingMean, groupByDay, dateRange,
    topicColor,
    windowDelta, sparkline, lineGradient, gradientFillPlugin,
    termFreqWithValence,
  };
})();
