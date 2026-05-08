/* Methodology pipeline diagram. Mirrors manuscript Figure 1. */
window.PipelineViz = (function () {
  const STAGES = [
    {
      key: "ingest", name: "1. Ingest",
      desc: "Playwright scraper · 4-strategy fallthrough",
      detail: `<p>Custom Playwright 1.59 scraper over a persistent Chrome context (8 auth cookies). Four strategies in fallthrough order: <code>desktop_graphql_httpx</code> (primary; brief Playwright handshake then HTTPX-replayed pagination, ~1.4&nbsp;GB flat memory) → <code>desktop</code> Playwright scroll → <code>basic_mobile_httpx</code> → <code>basic_mobile</code>. ScrollWatchdog (90&nbsp;s), 500-scroll cap per session, token refresh every 240&nbsp;min, append-only JSONL checkpointing every ~30&nbsp;s. 10 Freedom Wall pages → 38,389 raw posts.</p>
        <pre>{
  "post_id": "0ad32b626e81d9e3",
  "post_url": "https://facebook.com/...",
  "text": "...",
  "timestamp_iso": "2026-05-03T13:34:41+08:00",
  "engagement": { "reactions": 4, "comments": 1, "shares": 0 },
  "source": "graphql"
}</pre>`,
    },
    {
      key: "preprocess", name: "2. Preprocess",
      desc: "10-phase clean · regional anonymise · Cebuano-aware",
      detail: `<p>Ten phases (logical order): field selection → regional anonymisation (5-tier ambiguity scheme: Safe / Capital-only / Ambiguous-drop / Allowlist / Skip-bare; replaces school refs with CAR · NCR · CALABARZON · CARAGA) → NER (spaCy <code>en_core_web_lg</code> + 430-entry Tagalog given-name list + professor regex + department patterns) → noise regex → linguistic normalisation (no machine translation; Taglish preserved) → stopword identification → engagement standardisation → timestamp normalisation → language ID (py3langid + Cebuano override: ceb_ratio ≥ 0.05 against 80-word function set) → SHA-256 exact dedupe + Jaccard ≥ 0.9 near-dedupe + 10-char QC. <b>38,389 raw → 37,074 retained (96.6%).</b></p>
        <pre>{
  "post_id": "376db0582147aa83",
  "source_code": "SLU",
  "text": "Bat Best Script [REDACTED_NAME]? Hindi [REDACTED_NAME] script nila. Lol. [REDACTED_NAME] at [DEPARTMENT].",
  "engagement": { "reactions": 57, "comments": 10, "shares": 0 },
  "timestamp_unix": 1777721450,
  "region": "CAR",
  "language_detected": "Filipino"
}</pre>`,
    },
    {
      key: "topic", name: "3. Topic model + label",
      desc: "BERTopic · XLM-R-Large · UMAP · HDBSCAN · DTM · Llama label",
      detail: `<p>Per-institution BERTopic. <b>XLM-RoBERTa-Large</b> (1024-dim) chosen over <code>paraphrase-multilingual-MiniLM-L12-v2</code> after a controlled bake-off (XLM-R-Large dominated silhouette +0.189 vs −0.069 and outlier rate 0.000 vs 0.137). UMAP (n_neighbors=15, n_components=5, min_dist=0.05, cosine) → HDBSCAN corpus-size-aware grid (default <code>min_cluster_size ∈ {15, 25, 50, 80}</code>, <code>min_samples ∈ {2, 3, 5, 10}</code>) with <code>min_cluster_count_floor = 5</code> guardrail → sub-cluster recovery for &gt;20% outlier clusters → soft reassignment ≥ 0.5 → c-TF-IDF (1, 2-grams) → <code>reduce_topics</code> (target 30, threshold 60) → <b>Dynamic Topic Modeling</b> (monthly bins, Gini ≥ 0.6 = event-driven). Topic labelling decoupled to <b>Llama 3.3 70B Instruct via NVIDIA NIM</b>: SHA-256-locked prompt skeleton, lazy-label blocklist (auto-regen up to 3 attempts), 25 RPM after rate-limit storm.</p>
        <pre>{
  "topic_id": 1,
  "size": 1214,
  "label": "Personal College Life Experiences",
  "keywords": [{"word":"college","score":0.012}, ...],
  "dtm": { "monthly": [...], "gini": 0.68, "event_driven": true }
}</pre>`,
    },
    {
      key: "vad", name: "4. VAD score",
      desc: "Llama 3.3 70B · Few-Shot · single-pass sarcasm",
      detail: `<p>Each post scored on the Self-Assessment Manikin (V/A/D, 1–9) plus a sarcasm boolean using <b>Llama 3.3 70B Instruct via NVIDIA NIM</b> (cloud pivot from the originally-proposed local 4-bit Llama-3-8B; 15–20-day projected local runtime → &lt;12&nbsp;h across 4 researcher accounts). Few-Shot prompt with three SAM-cube anchor exemplars (burnout, rage, sarcasm). Batched 5 posts/request. <b>Single-pass sarcasm-aware</b> design: model internally assesses sarcasm before scoring and reports the underlying emotion, replacing the originally-proposed two-pass flag-then-rescore. Resilience: TokenBucket 20&nbsp;RPM/researcher (half of NIM 40&nbsp;RPM ceiling), 1→2→4→8→16&nbsp;s exponential backoff (5 attempts), CircuitBreaker on 10 consecutive failures, JSON-repair fallback. Workload distributed across 4 researchers via Longest-Processing-Time bin-pack.</p>
        <pre>{
  "post_id": "0ad32b626e81d9e3",
  "univ_code": "CAR-PUB-1",
  "topic_id": 1,
  "topic_label": "Personal College Life Experiences",
  "V": 7, "A": 6, "D": 7,
  "sarcasm": false,
  "flags": [],
  "researcher_id": "researcher_alexx",
  "model_version": "meta/llama-3.3-70b-instruct",
  "scored_at": "2026-05-06T17:51:51+0800"
}</pre>`,
    },
    {
      key: "hitl", name: "5. HITL validation",
      desc: "5% stratified · 8 annotators · ICC ≥ 0.75",
      detail: `<p>All 8 team members annotate a 5% per-institution stratified random sample (n = 1,855) drawn deterministically by post-id hash, loaded into <b>Label Studio</b>. Stratified on institution × academic-term × topic distribution. Calibration on a 100-post training set must hit <b>ICC ≥ 0.75</b> on V, A, and D before main annotation begins (tightened from the originally-proposed 0.70). Reliability reported at three levels: Cohen's Kappa (28 pairs) and Fleiss' Kappa for categorical labels; <b>ICC(2,k)</b> for the three continuous V/A/D dimensions. External-anchor calibration: 50-post sub-sample against NRC-VAD and ANEW lexicons. Corpus-wide outcome: VAD ±1 = <b>91.5%</b>; ICC = 0.886 V, 0.883 A, 0.857 D; sarcasm κ = 0.638; topic-label agreement 93.6%. Limitation: annotators are also authors — accuracy bounds team-internal consistency, not external validity.</p>
        <pre>{
  "annotator_id": "researcher_03",
  "post_id": "7b5ee6b959765a86",
  "model": { "V": 4, "A": 7, "D": 3, "sarcasm": false },
  "human": { "V": 5, "A": 7, "D": 3, "sarcasm": false },
  "within_one": { "V": true, "A": true, "D": true, "all": true }
}</pre>`,
    },
    {
      key: "dash", name: "6. Dashboard",
      desc: "Vanilla HTML/JS · two views · this app",
      detail: `<p>ETL (<code>build_dashboard_data.py</code> + <code>export_umap_embeddings.py</code>) joins preprocessing + topic_modeling + VAD outputs into per-institution JSON (~19&nbsp;MB total; ~6&nbsp;s build). Two views over the same data layer: an <b>Institutional view</b> (4-page hash-routed SPA: Overview, Topics &amp; Conversations, Emotional Landscape, Investigation Feed — Plain-English V/A/D as Positivity / Intensity / Control) targeting university administrators, and this <b>Research view</b> (Single / Compare / Ten-up Grid) targeting the thesis committee. Vanilla HTML5/CSS3/JS, OKLCH dual-theme, vendored Chart.js 4.4.1 + D3 7.8.5 + d3-cloud + Plotly 2.35.2. No backend.</p>
        <pre>dashboard/
  data/_summary.json            ← cross-univ stats
  data/institutional/&lt;code&gt;.json ← KPIs + heatmap + topics + scatter
  data/research/&lt;code&gt;.json     ← posts + topics + UMAP + VAD</pre>`,
    },
  ];

  function render(hostEl, detailEl) {
    hostEl.innerHTML = "";
    const stageEls = [];
    for (const s of STAGES) {
      const div = document.createElement("div");
      div.className = "pipe-stage";
      div.innerHTML = `<div class="name">${s.name}</div><div class="desc">${s.desc}</div>`;
      div.addEventListener("click", () => {
        stageEls.forEach(e => e.classList.remove("active"));
        div.classList.add("active");
        detailEl.innerHTML = `<h4>${s.name} · ${s.desc}</h4>${s.detail}`;
        detailEl.classList.add("show");
      });
      hostEl.appendChild(div);
      stageEls.push(div);
    }
  }
  return { render };
})();
