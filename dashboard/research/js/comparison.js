/* Mini calendar heatmap (used in 10-up grid mode). */
window.MiniHeatmap = (function () {
  function render(host, univ) {
    const posts = univ.posts || [];
    const dayMap = new Map();
    for (const p of posts) {
      if (!p.ts) continue;
      const d = DashUtils.fmt.date(p.ts);
      if (!dayMap.has(d)) dayMap.set(d, []);
      dayMap.get(d).push(p);
    }
    if (!dayMap.size) {
      host.innerHTML = `<div class="empty-state">No date-stamped posts.</div>`;
      return;
    }
    const days = [...dayMap.keys()].sort();
    const all = DashUtils.dateRange(days[0], days[days.length - 1]);
    const cell = 8, gap = 1, leftPad = 4, topPad = 4;
    const startOffset = new Date(all[0] + "T00:00:00Z").getUTCDay();
    const totalCols = Math.ceil((startOffset + all.length) / 7);
    const W = leftPad * 2 + totalCols * (cell + gap);
    const H = topPad * 2 + 7 * (cell + gap);

    const svg = d3.create("svg")
      .attr("viewBox", `0 0 ${W} ${H}`)
      .attr("preserveAspectRatio", "xMinYMin meet");

    all.forEach((d, idx) => {
      const ord = startOffset + idx;
      const col = Math.floor(ord / 7);
      const row = ord % 7;
      const arr = dayMap.get(d) || [];
      const scored = arr.filter(p => p.V != null);
      const meanV = scored.length ? scored.reduce((s, p) => s + p.V, 0) / scored.length : null;
      const fill = arr.length === 0 ? "#EEF0F3" : (meanV == null ? "#D1D5DB" : VADColors.valenceCalendar(meanV));
      svg.append("rect")
        .attr("x", leftPad + col * (cell + gap))
        .attr("y", topPad + row * (cell + gap))
        .attr("width", cell).attr("height", cell)
        .attr("rx", 1.5).attr("fill", fill);
    });

    host.innerHTML = "";
    host.appendChild(svg.node());
  }
  return { render };
})();
