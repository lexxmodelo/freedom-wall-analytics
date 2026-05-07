/* Methodology pipeline diagram. */
window.PipelineViz = (function () {
  const STAGES = [
    {
      key: "ingest", name: "1. Ingest",
      desc: "Apify Facebook Page Scraper",
      detail: `<p>Whitelisted unauthenticated scrape of public Freedom Wall pages. Only post text, timestamp, engagement metrics retained.</p>
        <pre>{
  "post_id": "0ad32b626e81d9e3",
  "raw_text": "...",
  "timestamp_unix": 1775654160,
  "engagement": { "reactions": 4, "comments": 1, "shares": 0 }
}</pre>`,
    },
    {
      key: "preprocess", name: "2. Preprocess",
      desc: "Anonymise + tokenise",
      detail: `<p>NER (spaCy/Presidio) + regex masking → person names → <code>[REDACTED_NAME]</code>. Department names & campus landmarks redacted. Taglish-preserving tokenisation; stopword removal.</p>
        <pre>{
  "post_id": "0ad32b626e81d9e3",
  "text": "Hi, genuine question required ba full name ang name [REDACTED_NAME] college?",
  "language_detected": "Filipino",
  "region": "CAR"
}</pre>`,
    },
    {
      key: "topic", name: "3. Topic model",
      desc: "BERTopic + UMAP + HDBSCAN",
      detail: `<p>paraphrase-multilingual-MiniLM-L12-v2 embeddings → UMAP (n_neighbors=15, min_dist=0.05, cosine) → HDBSCAN (min_cluster grid 30–100) → c-TF-IDF with custom Taglish stopwords → soft reassignment ≥0.50.</p>
        <pre>{
  "topic_id": 0,
  "size": 1214,
  "keywords": [{"word":"college","score":0.012}, ...]
}</pre>`,
    },
    {
      key: "label", name: "4. LLM label",
      desc: "NIM Llama 3.3 70B",
      detail: `<p>Top-10 keywords + top-5 representative posts → Llama 3.3 70B → 5-word English label. Temperature 0.1; explicit "Noise" fallback for incoherent clusters; "no quotes" guard.</p>
        <pre>USER: Keywords: college, student, life, year, ...
Representative posts: ...
→ "Personal College Life Experiences"</pre>`,
    },
    {
      key: "vad", name: "5. VAD score",
      desc: "Llama 3.3 70B · batch 5",
      detail: `<p>Each post scored on Self-Assessment Manikin (V/A/D, 1-9 each) plus binary sarcasm. Batched 5/request; chain-of-thought sarcasm pre-check influences scoring of true emotion under irony.</p>
        <pre>[
  {"id":"0ad…","V":7,"A":6,"D":7,"sarcasm":false},
  {"id":"7b5…","V":4,"A":7,"D":3,"sarcasm":false}
]</pre>`,
    },
    {
      key: "dash", name: "6. Dashboard",
      desc: "Static HTML · this app",
      detail: `<p>ETL joins preprocessing + topic_modeling + vad_scoring outputs into per-university JSON. Static HTML/JS dashboards consume the JSON in the browser. No backend; Chart.js + D3 + Plotly.</p>
        <pre>dashboard/
  data/_summary.json           ← cross-univ stats
  data/research/&lt;univ&gt;.json    ← posts + topics + UMAP + VAD</pre>`,
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
