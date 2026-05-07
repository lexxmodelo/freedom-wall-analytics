/* Canvas-rendered UMAP scatter with d3-quadtree hover. Falls back to topic-position grid if no UMAP coords. */
window.UMAPViz = (function () {
  function render(host, univ) {
    host.innerHTML = "";
    const posts = univ.posts || [];
    const xy = univ.umap_xy;
    const hasUmap = univ.umap_present && Array.isArray(xy) && xy.length === posts.length && xy.every(v => v != null);

    if (!hasUmap) {
      renderFallback(host, univ);
      return;
    }
    renderCanvas(host, posts, xy, univ.topics || []);
  }

  function renderFallback(host, univ) {
    // Gentle "topic constellation" layout — one cluster per topic in a ring.
    const posts = univ.posts || [];
    const topics = (univ.topics || []).sort((a, b) => b.size - a.size);
    if (!posts.length || !topics.length) {
      host.innerHTML = `<div class="placeholder">No topics yet for ${univ.univ_code}.</div>`;
      return;
    }
    const centers = new Map();
    const N = topics.length;
    topics.forEach((t, i) => {
      if (t.id === -1) {
        centers.set(t.id, [0, 0]);
      } else {
        const angle = (2 * Math.PI * i) / Math.max(1, N - 1);
        centers.set(t.id, [Math.cos(angle), Math.sin(angle)]);
      }
    });
    const synth = posts.map(p => {
      const c = centers.get(p.topic_id) || [0, 0];
      const r = 0.18 + Math.random() * 0.18;
      const a = Math.random() * Math.PI * 2;
      return [c[0] + Math.cos(a) * r, c[1] + Math.sin(a) * r];
    });
    renderCanvas(host, posts, synth, univ.topics || [], {
      banner: `UMAP coords pending — showing synthetic topic constellation. Run <code>etl/export_umap_embeddings.py</code> to render the real BERTopic 2-D projection.`,
    });
  }

  function renderCanvas(host, posts, xy, topics, opts = {}) {
    const W = host.clientWidth || 800, H = host.clientHeight || 480;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const canvas = document.createElement("canvas");
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    host.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    // Bounds
    const xs = xy.map(c => c[0]), ys = xy.map(c => c[1]);
    const xMin = d3.min(xs), xMax = d3.max(xs);
    const yMin = d3.min(ys), yMax = d3.max(ys);
    const pad = 30;
    const sx = (xMax - xMin) || 1, sy = (yMax - yMin) || 1;
    const project = (x, y) => [
      pad + ((x - xMin) / sx) * (W - 2 * pad),
      pad + ((yMax - y) / sy) * (H - 2 * pad),
    ];

    const points = posts.map((p, i) => {
      const [px, py] = project(xy[i][0], xy[i][1]);
      return { x: px, y: py, p, color: DashUtils.topicColor(p.topic_id) };
    });

    // Initial draw
    function draw(transform = { k: 1, x: 0, y: 0 }) {
      ctx.save();
      ctx.clearRect(0, 0, W, H);
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.k, transform.k);
      for (const pt of points) {
        ctx.beginPath();
        ctx.fillStyle = pt.color;
        ctx.globalAlpha = 0.55;
        ctx.arc(pt.x, pt.y, 2.3 / Math.sqrt(transform.k), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
      ctx.globalAlpha = 1;
    }
    draw();

    // Quadtree for hover
    const qt = d3.quadtree().x(d => d.x).y(d => d.y).addAll(points);
    const tip = DashUtils.tooltip();
    let transform = { k: 1, x: 0, y: 0 };

    canvas.addEventListener("mousemove", (ev) => {
      const rect = canvas.getBoundingClientRect();
      const mx = (ev.clientX - rect.left - transform.x) / transform.k;
      const my = (ev.clientY - rect.top - transform.y) / transform.k;
      const hit = qt.find(mx, my, 8 / transform.k);
      if (hit) {
        const t = topics.find(t => t.id === hit.p.topic_id);
        const tl = t ? t.label : (hit.p.topic_id === -1 ? "Noise" : `Topic ${hit.p.topic_id}`);
        const vad = hit.p.V == null ? "" : ` · V ${hit.p.V} A ${hit.p.A} D ${hit.p.D}${hit.p.sarcasm ? " · 🌀" : ""}`;
        tip.show(`<b>${tl}</b>${vad}<br>${escapeHtml((hit.p.text || "").slice(0, 180))}…`, ev);
      } else tip.hide();
    });
    canvas.addEventListener("mouseleave", () => tip.hide());

    // Pan/zoom (light)
    let panning = false; let panStart = null;
    canvas.addEventListener("mousedown", (ev) => { panning = true; panStart = { x: ev.clientX - transform.x, y: ev.clientY - transform.y }; canvas.style.cursor = "grabbing"; });
    canvas.addEventListener("mouseup", () => { panning = false; canvas.style.cursor = "grab"; });
    canvas.addEventListener("mousemove", (ev) => {
      if (!panning) return;
      transform.x = ev.clientX - panStart.x;
      transform.y = ev.clientY - panStart.y;
      draw(transform);
    });
    canvas.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const delta = -ev.deltaY * 0.0015;
      const factor = Math.exp(delta);
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
      transform.x = mx - (mx - transform.x) * factor;
      transform.y = my - (my - transform.y) * factor;
      transform.k = Math.max(0.4, Math.min(8, transform.k * factor));
      draw(transform);
    }, { passive: false });

    // Legend
    const legend = document.createElement("div");
    legend.className = "legend";
    const sortedTopics = [...topics].sort((a, b) => b.size - a.size).slice(0, 16);
    legend.innerHTML = sortedTopics.map(t => `
      <div class="legend-row">
        <span class="dot" style="background:${DashUtils.topicColor(t.id)}"></span>
        <span>${escapeHtml(DashUtils.fmt.label(t.label, 26))}</span>
      </div>`).join("");
    host.appendChild(legend);

    if (opts.banner) {
      const b = document.createElement("div");
      b.className = "banner banner-info";
      b.style.position = "absolute";
      b.style.bottom = "12px";
      b.style.left = "12px";
      b.style.right = "260px";
      b.style.margin = 0;
      b.innerHTML = `<span class="b-dot">●</span><div class="banner-body">${opts.banner}</div>`;
      host.appendChild(b);
    }
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  return { render };
})();
