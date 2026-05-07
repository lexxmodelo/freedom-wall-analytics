# Topic Modeling Phase — Implementation Plan

## Context

The preprocessing phase has produced 10 cleaned per-school JSON files in `preprocessing/output/` (FW-01..FW-09 + SLU, ~37K posts after dedup/QC, with `post_id`, `text`, `timestamp_unix`, `region`, `language_detected` fields). The next phase is **per-university topic modeling** with decoupled LLM labeling, per `methodology_changes.md` §3.1 and §3.3.

This plan creates a new `topic_modeling/` directory containing a researcher-agnostic, self-healing, audit-logged pipeline that:

1. **Bakes off two embedding models** (paraphrase-multilingual-MiniLM-L12-v2 vs XLM-RoBERTa-Large) on the SLU pilot, then locks the winner for the full corpus — resolving the conflict between the user's prompt (XLM-R-L) and the approved methodology (MiniLM).
2. Trains **per-university BERTopic models** with grid-searched HDBSCAN/UMAP hyperparameters, soft-clustering reassignment (≥0.50), and DTM (topics-over-time).
3. Decouples labeling: BERTopic emits keywords + representative docs; the **NVIDIA NIM API (Llama 3.3 70B Instruct, T=0.1, 40 RPM)** generates labels via the prompt locked in `methodology_changes.md:273-294`.
4. Supports **1–5 researchers** running the same code on disjoint university subsets via per-researcher config files.
5. Logs every decision, configuration, retry, and error to a sacred `topic_modeling/action_log.md` (mirroring the format of `preprocessing/action_log.md`).

**Key decisions confirmed by user (this conversation):**
- Embedding: comparative bake-off, pick winner by NPMI + outlier rate.
- Scope: generic pipeline for 1–5 researchers (not hardcoded to one).
- File→code mapping: add `university_mapping.yaml` now; SLU→CAR-PSEC-1 (pilot baseline) confirmed; remaining 9 files flagged for user confirmation before full execution.
- DTM: included in the default pipeline.

**Out of scope for this plan:** VAD scoring (separate downstream phase), dashboard, HITL Label Studio export, scraper/preprocessing changes.

---

## 1. Folder Structure

To be created at the repo root:

```
topic_modeling/
├── action_log.md                          # SACRED — every action timestamped
├── README.md                              # Quick-start for researchers
├── configs/
│   ├── bertopic_config.json               # Shared hyperparameters (locked)
│   ├── gpu_config.json                    # CUDA settings, batch sizes, OOM recovery thresholds
│   ├── university_mapping.yaml            # FW-XX / SLU → anonymized code (MM-PUB-1, CAR-PSEC-1, ...)
│   ├── researcher_template.json           # Template for per-researcher config
│   ├── stopwords_taglish.txt              # Custom Taglish stopwords for c-TF-IDF
│   └── prompts/
│       └── labeling_prompt.txt            # Verbatim prompt from methodology_changes.md:273-294
├── topic_modeling/                        # Python package (mirrors preprocessing/preprocessing/)
│   ├── __init__.py
│   ├── pipeline.py                        # Orchestrator
│   ├── run.py                             # CLI entry point
│   ├── embed.py                           # Embedding model loader + bake-off
│   ├── cluster.py                         # UMAP + HDBSCAN + grid search
│   ├── topics.py                          # BERTopic wrapper, c-TF-IDF, soft-cluster reassignment
│   ├── dtm.py                             # Dynamic Topic Modeling (topics_over_time)
│   ├── labeling.py                        # NIM API client + prompt rendering + validation
│   ├── validation.py                      # Lazy-label/duplicate/Taglish detection
│   ├── checkpoint.py                      # Resume support
│   ├── logging_setup.py                   # Reuse preprocessing pattern
│   └── io_utils.py                        # JSON/JSONL helpers (reuse preprocessing/io_utils.py if importable)
├── models/
│   └── {UNIV_CODE}_bertopic_model.pkl     # One per university (e.g., CAR-PSEC-1_bertopic_model.pkl)
├── outputs/
│   ├── {UNIV_CODE}/
│   │   ├── topic_assignments.json         # post_id → topic_id (+ probability, soft-reassigned flag)
│   │   ├── topic_keywords.json            # topic_id → top-10 c-TF-IDF keywords
│   │   ├── topic_rep_docs.json            # topic_id → top-5 representative post_ids + texts
│   │   ├── topic_labels.json              # topic_id → LLM label (+ retries, flags, response_hash)
│   │   ├── topic_metadata.json            # per-topic stats: size, NPMI, silhouette, density
│   │   └── topics_over_time.json          # DTM output: topic_id × month_bin → frequency
├── api_cache/
│   └── labeling_responses/{UNIV_CODE}/{topic_id}.json   # Raw NIM responses for audit
├── checkpoints/
│   └── {RESEARCHER_ID}/{UNIV_CODE}_state.json           # Resume state
├── gpu_logs/
│   └── vram_usage.jsonl                   # Per-university VRAM peaks (for OOM debugging)
├── validation/
│   ├── outlier_report.json                # Per-university outlier rate (target <60%)
│   ├── lazy_label_flags.json              # Topics with generic labels needing human review
│   ├── label_consistency_check.json       # Cross-university label deduplication report
│   └── embedding_bakeoff_report.md        # MiniLM vs XLM-R-L decision document
└── tests/
    ├── test_labeling_prompt.py            # Snapshot test of prompt template (prevents drift)
    ├── test_validation_filters.py         # Lazy-label / Taglish / duplicate detectors
    ├── test_checkpoint_resume.py          # Crash + resume integrity
    └── test_label_dedup.py                # Cross-researcher harmonization
```

**Reusable utilities from `preprocessing/preprocessing/`:**
- `io_utils.py` — `load_jsonl`, `write_json` (atomic), `dump_qc_report`
- `logging_setup.py` — logger configuration pattern
- `pipeline.py` — `@dataclass PipelineConfig` and phase-runner pattern (line 50–63)

If direct import is awkward (separate package), copy the functions and note provenance in `topic_modeling/io_utils.py` header.

---

## 2. Pipeline Stages (Step-by-Step)

### Stage 0 — Pre-flight
1. Verify Python ≥3.10, install: `bertopic`, `sentence-transformers`, `umap-learn`, `hdbscan`, `torch` (CUDA build), `httpx`, `tenacity`, `pyyaml`, `pytest`.
2. `torch.cuda.is_available()` check; log GPU name, CUDA version, total VRAM, free VRAM.
3. Validate `NVIDIA_NIM_API_KEY` env var (no key → fail fast with clear error).
4. Validate `university_mapping.yaml` exists and every input file in `preprocessing/output/` has a mapping.
5. Validate `prompts/labeling_prompt.txt` matches the methodology-locked text (SHA256 against committed reference).

### Stage 1 — Embedding Bake-off (one-time, on SLU only)
- Load `SLU_cleaned.json`.
- Encode with **MiniLM** (CPU, batch_size=64) → cluster with default UMAP+HDBSCAN(min_cluster=50) → record NPMI, silhouette, outlier rate, wall time.
- Encode with **XLM-RoBERTa-Large** (GPU, batch_size=16, fall back to 8/4 on OOM) → identical clustering → same metrics.
- Write `validation/embedding_bakeoff_report.md` comparing both. Decision rule: **lower outlier rate wins; ties broken by higher NPMI**. If XLM-R-L wins by <5% on both metrics, choose MiniLM (cheaper, no GPU dependency, matches Research.md baseline).
- Lock the winner in `bertopic_config.json` as `embedding_model_id`. Log decision in `action_log.md` with both metric tables.

### Stage 2 — Per-University BERTopic Training
For each `(file, univ_code)` in the researcher's assigned subset:
1. Load posts; filter `post_id`, `text`, `timestamp_unix`, `language_detected`.
2. Skip universities with `<1000 posts` (log SKIPPED with reason; configurable threshold).
3. Encode with locked embedder (GPU if XLM-R-L; CPU if MiniLM).
4. UMAP: `n_neighbors=15, n_components=5, metric=cosine, min_dist=0.05, random_state=42`.
5. HDBSCAN grid search: `min_cluster_size ∈ {30, 50, 70, 100}` × `min_samples ∈ {5, 10, 15}` (12 combos).
   - Selection: highest combined score = 0.5×NPMI + 0.3×silhouette + 0.2×(1 − outlier_rate).
6. Build BERTopic with `representation_model=None`, `calculate_probabilities=True` (needed for soft reassignment).
7. **Soft-cluster reassignment** of outliers (`topic_id == -1`) where max probability ≥ 0.50 — reassign to the highest-probability topic. Log count and rate.
8. Extract per-topic top-10 c-TF-IDF keywords (Taglish stopwords applied) and top-5 representative docs (BERTopic's `get_representative_docs`).
9. **DTM**: `topic_model.topics_over_time(docs, timestamps, nr_bins=monthly)` → `topics_over_time.json`.
10. Persist model: `models/{UNIV_CODE}_bertopic_model.pkl` (with `safetensors` for embeddings if size matters).
11. Write all `outputs/{UNIV_CODE}/*.json`.
12. Record VRAM peak in `gpu_logs/vram_usage.jsonl`.
13. Checkpoint: write `checkpoints/{RESEARCHER_ID}/{UNIV_CODE}_state.json` after each successful university.

### Stage 3 — LLM Topic Labeling (NIM API)
For each topic in each university the researcher trained:
1. Render prompt from `prompts/labeling_prompt.txt` with `[KEYWORDS]` (joined, comma-separated) and `[DOCUMENTS]` (newline-separated, truncated to 280 chars each).
2. Token-bucket rate limiter: 40 RPM, refilling at 40/min.
3. POST to `https://integrate.api.nvidia.com/v1/chat/completions`, `model=meta/llama-3.3-70b-instruct`, `temperature=0.1`, `max_tokens=20`, timeout=30s.
4. **Validate response:**
   - Strip whitespace and surrounding quotes (programmatic, log when stripped).
   - ≤5 words? Else flag as `OVERLENGTH` and truncate to first 5 words.
   - ASCII-only? Else flag `TAGLISH_OUTPUT`, retry once with explicit "Reply in English only." prepended.
   - Matches lazy-label regex (`r"^(general|various|misc|other|topic\s*\d+|noise)"i` + a curated lazy-phrase list)? Flag `LAZY_LABEL`.
5. Cache raw response → `api_cache/labeling_responses/{UNIV_CODE}/{topic_id}.json` (request payload + response body + headers + timestamp + sha256 of input).
6. After all topics in a university are labeled, run **intra-university dedup**: if two topics have identical labels, append a disambiguating keyword: `"{label} ({top_keyword})"`. Log every disambiguation.
7. Write `topic_labels.json` with: `topic_id`, `label`, `flags[]`, `retries`, `response_hash`, `nim_model_version` (from response headers).

### Stage 4 — Per-Researcher Validation
- Compute outlier rate per university; if >60%, log `OUTLIER_HIGH` and recommend hyperparameter retry (do not auto-rerun; require human approval).
- Aggregate `lazy_label_flags.json` (count per university).
- Verify all topic IDs in `topic_assignments.json` have entries in `topic_labels.json`.
- Verify every `post_id` appears exactly once in `topic_assignments.json`.

### Stage 5 — Cross-Researcher Merge (separate `merge.py`, run by lead researcher)
- Concatenate all `outputs/{UNIV_CODE}/topic_*.json` from every researcher's branch/output bundle.
- **Cross-university label harmonization:** embed all labels with the same locked embedder; cluster labels (cosine sim ≥0.85) → propose canonical label (most frequent among the cluster, longer wins on tie).
- Write `validation/label_consistency_check.json` with proposed merges; require human ratification before applying.
- Final unified outputs: `topic_modeling/outputs/_merged/topic_taxonomy.json`.

---

## 3. Python Pseudocode (key modules)

### `embed.py` — embedding loader with GPU/CPU branching
```python
def load_embedder(cfg) -> SentenceTransformer:
    name = cfg["embedding_model_id"]
    device = "cuda" if cfg["use_gpu"] and torch.cuda.is_available() else "cpu"
    log_action("EMBED_LOAD", model=name, device=device, free_vram=free_vram_mb())
    model = SentenceTransformer(name, device=device)
    return model

def encode_with_oom_fallback(model, docs, initial_batch=32, min_batch=4):
    batch = initial_batch
    while batch >= min_batch:
        try:
            return model.encode(docs, batch_size=batch, show_progress_bar=True,
                                convert_to_numpy=True, normalize_embeddings=True)
        except torch.cuda.OutOfMemoryError:
            log_action("OOM_RECOVERY", batch_from=batch, batch_to=batch//2)
            torch.cuda.empty_cache()
            batch //= 2
    # Last resort: CPU
    log_action("CPU_FALLBACK", reason="GPU OOM at min batch", quality_impact="3-5x slower")
    model = model.to("cpu")
    return model.encode(docs, batch_size=64, show_progress_bar=True, convert_to_numpy=True)
```

### `cluster.py` — grid search
```python
def grid_search_hdbscan(embeddings, grid):
    results = []
    for mcs in grid["min_cluster_size"]:
        for ms in grid["min_samples"]:
            umap_emb = run_umap(embeddings, seed=42)
            labels = HDBSCAN(min_cluster_size=mcs, min_samples=ms,
                             metric="euclidean", cluster_selection_method="eom",
                             prediction_data=True).fit_predict(umap_emb)
            metrics = {
                "outlier_rate": (labels == -1).mean(),
                "silhouette": silhouette_score(umap_emb[labels != -1], labels[labels != -1])
                              if (labels != -1).sum() > 1 else 0.0,
                "npmi": compute_npmi(labels, docs),  # via gensim CoherenceModel
            }
            score = 0.5*metrics["npmi"] + 0.3*metrics["silhouette"] + 0.2*(1 - metrics["outlier_rate"])
            results.append({"mcs": mcs, "ms": ms, **metrics, "score": score})
    best = max(results, key=lambda r: r["score"])
    log_action("GRID_SEARCH", grid=grid, results=results, chosen=best)
    return best
```

### `labeling.py` — NIM client with retries
```python
@retry(stop=stop_after_attempt(5),
       wait=wait_exponential(multiplier=1, min=1, max=16),
       retry=retry_if_exception_type((httpx.TimeoutException, RateLimitError)))
def call_nim(prompt: str, cfg) -> str:
    rate_limiter.acquire()  # blocks until token available
    resp = client.post(NIM_URL, json={
        "model": "meta/llama-3.3-70b-instruct",
        "messages": parse_prompt(prompt),
        "temperature": 0.1,
        "max_tokens": 20,
    }, timeout=30)
    if resp.status_code == 429:
        raise RateLimitError(resp.headers.get("retry-after", 5))
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def label_topic(univ_code, topic_id, keywords, rep_docs, cfg):
    prompt = render_prompt(keywords, rep_docs)
    flags, retries = [], 0
    label = call_nim(prompt, cfg).strip().strip('"').strip("'")
    if has_non_ascii(label):
        flags.append("TAGLISH_OUTPUT")
        retries += 1
        label = call_nim("Reply in English only.\n" + prompt, cfg).strip().strip('"').strip("'")
    if word_count(label) > 5:
        flags.append("OVERLENGTH"); label = " ".join(label.split()[:5])
    if is_lazy_label(label):
        flags.append("LAZY_LABEL")
    cache_response(univ_code, topic_id, prompt, label, flags)
    return {"topic_id": topic_id, "label": label, "flags": flags, "retries": retries}
```

### `pipeline.py` — orchestrator skeleton
```python
def run(cfg: TopicModelingConfig):
    preflight_check(cfg)
    if cfg.run_bakeoff: run_embedding_bakeoff(cfg)
    embedder = load_embedder(cfg)
    for univ_file in cfg.assigned_files:
        univ_code = mapping[univ_file]
        if checkpoint_exists(univ_code, cfg.researcher_id):
            log_action("RESUME", univ=univ_code); continue
        try:
            posts = load_jsonl(univ_file)
            if len(posts) < cfg.min_posts: log_action("SKIP", reason="too_few_posts"); continue
            embeddings = encode_with_oom_fallback(embedder, [p["text"] for p in posts])
            best_params = grid_search_hdbscan(embeddings, cfg.grid)
            topic_model = build_bertopic(embeddings, posts, best_params, cfg)
            soft_reassign_outliers(topic_model, posts, threshold=0.50)
            keywords = topic_model.get_topics()
            rep_docs = topic_model.get_representative_docs()
            dtm_out = topic_model.topics_over_time(docs=[p["text"] for p in posts],
                                                  timestamps=[p["timestamp_unix"] for p in posts],
                                                  nr_bins=monthly_bins(posts))
            labels = [label_topic(univ_code, tid, kws, rep_docs[tid], cfg)
                      for tid, kws in keywords.items() if tid != -1]
            dedupe_labels_intra_univ(labels)
            persist_all(univ_code, topic_model, posts, keywords, rep_docs, labels, dtm_out)
            write_checkpoint(univ_code, cfg.researcher_id)
        except Exception as e:
            log_action("UNIV_FAILED", univ=univ_code, error=str(e), traceback=tb())
            continue  # don't abort whole run
    write_validation_reports(cfg)
```

---

## 4. Error Handling Matrix

| Scenario | Detection | Recovery |
|---|---|---|
| `torch.cuda.is_available()` is False but config requires GPU | Pre-flight | Abort with clear message; suggest `device="cpu"` only if MiniLM was chosen |
| CUDA OOM on `model.encode()` | `torch.cuda.OutOfMemoryError` | `empty_cache()` → halve batch (32→16→8→4); if still OOM at 4, fall back to CPU and log `CPU_FALLBACK` with quality/time warning |
| HDBSCAN assigns >60% to topic -1 | Outlier rate metric | Log `OUTLIER_HIGH`; retry grid with `min_cluster_size ∈ {15, 20, 25}`; if still >60%, persist anyway and flag for human review |
| University has <1000 posts | Length check pre-train | Skip + log `SKIP_LOW_VOLUME`; do not crash |
| NIM HTTP 429 (rate limit) | Status code | Tenacity exponential backoff 1s/2s/4s/8s/16s, max 5; if `retry-after` header present, honor it instead |
| NIM HTTP 5xx | Status code | Same backoff; after 5 retries, log `API_5XX_GIVEUP` and skip topic (label=`Unlabeled`, flag for retry pass) |
| NIM timeout (30s) | `httpx.TimeoutException` | Same backoff |
| NIM returns Taglish label | `not label.isascii()` or curated Tagalog particle regex | Retry once with English-only directive; if still non-ASCII, accept and flag `TAGLISH_OUTPUT` |
| NIM wraps label in quotes | `label.startswith(('"',"'"))` | Strip programmatically; log `STRIPPED_QUOTES` |
| Two topics in one university get identical labels | exact match in label list | Append `(top_keyword)` to both, ensuring distinct |
| NIM returns malformed/empty response | empty content / JSON parse fail | Retry with full prompt; if persistent, label=`Unlabeled`, flag `MALFORMED_OUTPUT` |
| Network failure mid-batch | `httpx.NetworkError` | Tenacity retries; if checkpoint was just written, resume continues from there |
| Process crash mid-university | No detection — recovery via `checkpoint.py` | On restart, re-load checkpoint; skip universities marked complete; re-run partial university from scratch (BERTopic clustering is fast enough) |
| API key invalid (HTTP 401) | Status code | Abort immediately with clear message; do NOT retry |
| `university_mapping.yaml` missing entry for input file | Pre-flight loop | Abort with explicit list of unmapped files |
| Lazy label pattern matches | `is_lazy_label(label)` regex + curated list | Persist label with flag `LAZY_LABEL`; surface in `validation/lazy_label_flags.json` for human review (not auto-retried — lazy may be correct for genuinely diffuse topics) |
| NIM model version drift mid-run | `response.headers["x-model-version"]` differs across cached responses | Log `MODEL_VERSION_DRIFT`; results remain valid but flag in final report |

---

## 5. Quality Assurance Checklist

A topic model output is **acceptable** for downstream use if all the following hold for that university:

- [ ] Outlier rate (post-soft-reassignment) ≤ 60%.
- [ ] At least 5 topics with ≥10 posts each.
- [ ] No more than 30% of topics flagged `LAZY_LABEL`.
- [ ] Average c-TF-IDF coherence (NPMI) ≥ 0.10.
- [ ] Every `post_id` in input appears exactly once in `topic_assignments.json`.
- [ ] Every topic_id in assignments has a corresponding label.
- [ ] All API responses cached (count of cache files == count of topics labeled).
- [ ] No `MODEL_VERSION_DRIFT` flag, OR drift is documented and bracketed by date.
- [ ] DTM produced ≥3 monthly bins (unless university has <90 days of post history — then log).

A model failing any of the above is marked **NEEDS_REVIEW** in `validation/outlier_report.json` and excluded from the merged taxonomy until manually approved.

---

## 6. Merge Strategy (Cross-Researcher)

1. Each researcher tarballs their `outputs/`, `models/`, `api_cache/`, `validation/`, `checkpoints/{researcher_id}/`, and `gpu_logs/` and uploads to a shared location.
2. Lead researcher runs `merge.py`:
   - Concatenate all `topic_assignments.json` files (no key collision since post_ids are globally unique from preprocessing).
   - Concatenate all `topic_labels.json`, namespacing topic_ids as `{UNIV_CODE}-{topic_id}`.
   - **Label harmonization:** embed all labels with the locked embedder; agglomerative cluster with cosine distance threshold 0.15 (≥0.85 similarity); for each cluster, propose canonical label (highest c-TF-IDF score across constituent topics; ties broken by frequency).
   - Write `validation/label_consistency_check.json` with: cluster id, member labels, proposed canonical, member topic_ids, requires_human_review flag.
   - **Do not auto-apply** harmonization — output a CSV that the team reviews and ratifies before the final taxonomy is frozen.
3. After ratification, `apply_harmonization.py` rewrites labels in a `_merged/` output directory, preserving originals.

---

## 7. Logging Format (`action_log.md`)

Mirror `preprocessing/action_log.md`'s `## ACTION-NNN — YYYY-MM-DD — <title>` structure. Sample entries:

```markdown
## ACTION-001 — 2026-05-05 — Topic modeling scaffold initialized
- **Action:** Created topic_modeling/ folder structure, configs, and stub modules.
- **Configuration:** N/A
- **Input:** preprocessing/output/ (10 files, 37,074 posts)
- **Output:** topic_modeling/ tree as specified in plan §1
- **Decisions:** Reused preprocessing/io_utils.py pattern; copied (not imported) to keep package self-contained.
- **Next Steps:** Run embedding bake-off on SLU.

## ACTION-002 — 2026-05-05 — GPU & environment verification
- **Action:** Pre-flight check of CUDA, model dependencies, NIM API key.
- **Configuration:** torch 2.x + CUDA 12.x; bertopic 0.16.x
- **Input:** N/A
- **Output:** GPU=NVIDIA GeForce RTX 4050, CUDA=12.4, total_vram=6144 MB, free_vram=5811 MB; NVIDIA_NIM_API_KEY=valid (HTTP 200 on test call)
- **Errors:** None
- **Next Steps:** Bake-off.

## ACTION-003 — 2026-05-05 — Embedding bake-off (SLU pilot)
- **Action:** Compared paraphrase-multilingual-MiniLM-L12-v2 (CPU) vs FacebookAI/xlm-roberta-large (GPU) on SLU_cleaned.json (3,864 posts).
- **Configuration:** UMAP(15,5,cosine,0.05,seed=42); HDBSCAN(min_cluster=50,min_samples=10).
- **Input:** SLU_cleaned.json
- **Output:**
  | Model | Outlier Rate | NPMI | Silhouette | Wall Time |
  |---|---|---|---|---|
  | MiniLM (CPU) | 0.42 | 0.13 | 0.28 | 6 min |
  | XLM-R-Large (GPU bs=16) | 0.31 | 0.18 | 0.34 | 9 min |
- **Decisions:** XLM-R-Large wins on both metrics by >5%. Locked as embedding_model_id. VRAM peak 4.8 GB.
- **Errors:** None (no OOM at batch_size=16).
- **Next Steps:** Train per-university models for assigned subset.

## ACTION-007 — 2026-05-05 — OOM during MM-PUB-1 encoding
- **Action:** OOM at batch_size=16 on 30,000 posts; recovery executed.
- **Configuration:** XLM-R-Large GPU, batch sequence 16→8→4 (success at 4).
- **Errors:** torch.cuda.OutOfMemoryError once at batch=16, once at batch=8.
- **Decisions:** Set initial_batch=8 in gpu_config.json for universities >20K posts.
- **Next Steps:** Continue.

## ACTION-012 — 2026-05-05 — NIM 429 storm at researcher_3
- **Action:** Hit 12 consecutive 429s on labeling for CAR-PUB-1 around 14:32 PHT.
- **Configuration:** rate_limit_rpm=40, batch=1.
- **Errors:** HTTP 429 ×12; backoff fired (1s..16s); circuit breaker did NOT trip (10 consecutive only — these were interleaved with successes).
- **Decisions:** Time-of-day contention with another researcher's key under same upstream pool. Reduced effective_rpm to 35 in researcher_3.json. Will revisit if persists.
- **Next Steps:** Continue.
```

---

## 8. XLM-RoBERTa-Large Justification (for thesis methodology section, contingent on bake-off outcome)

> The original proposal (Research.md §3.4) specified `paraphrase-multilingual-MiniLM-L12-v2` as the embedding model for BERTopic, chosen for its efficiency on Taglish code-switching. During the topic modeling phase, we conducted an empirical bake-off against `FacebookAI/xlm-roberta-large` (550M parameters, 1024-dimensional embeddings) on the SLU pilot corpus (3,864 posts). XLM-RoBERTa-Large is the encoder backbone underlying many subsequent multilingual NLP advances and substantially extends the multilingual transformer family that Cosme and De Leon (2024) showed to outperform English-only models on code-switched Filipino text. Although Cruz and Cheng (2021) established RoBERTa-Tagalog as the Philippine baseline, RoBERTa-Tagalog is monolingual and cannot embed English fragments in Taglish without information loss; XLM-RoBERTa-Large preserves both Tagalog and English semantics in a single 1024-dimensional space. The bake-off measured outlier rate (post-HDBSCAN), NPMI coherence, and silhouette score under identical UMAP/HDBSCAN settings; the model with lower outlier rate (tie-broken by higher NPMI) was locked for the full corpus. Where XLM-RoBERTa-Large was selected, the GPU memory cost (4.8 GB peak on RTX 4050) was managed through dynamic batch-size reduction and per-university processing.

(If the bake-off selects MiniLM, replace the paragraph with: *"The bake-off confirmed that paraphrase-multilingual-MiniLM-L12-v2 is sufficient: XLM-RoBERTa-Large did not improve outlier rate or NPMI by more than 5%, and the proposal-specified MiniLM was retained for reproducibility and CPU portability."*)

---

## 9. Critical-Question Resolutions

| Question | Resolution in this plan |
|---|---|
| 44% outlier rate from pilot acceptable? | No — target ≤60% post-soft-reassignment. Soft-cluster reassignment at threshold 0.50 + grid search are the primary mitigations. >60% triggers `OUTLIER_HIGH` and a hyperparameter retry. |
| Per-university vs global model with ~4K posts | Per-university per methodology §3.1. Universities with <1000 posts are skipped (logged). Universities with 1000–3000 posts get a smaller HDBSCAN grid (`min_cluster_size ∈ {15, 25, 40}`) auto-selected by a size-bucket rule in `cluster.py`. |
| Label consistency across researchers | Solved in Stage 5 merge: embed all labels with locked embedder, cluster ≥0.85 cosine sim, propose canonical, **require human ratification** before applying. |
| Topic drift / DTM | Included in default pipeline (Stage 2.9), monthly bins, output `topics_over_time.json` per university. |
| Reproducibility / random seed | UMAP `random_state=42`; HDBSCAN is deterministic given input; embedder pinned by exact HuggingFace revision SHA in `bertopic_config.json`; NIM `temperature=0.1` and cached responses. |
| Embedding model justification | §8 above; bake-off-driven, not hand-waved. |

---

## 10. Critical Files to Create/Modify

**Create (all under `topic_modeling/`):**
- `action_log.md`, `README.md`
- `configs/bertopic_config.json`, `configs/gpu_config.json`, `configs/university_mapping.yaml`, `configs/researcher_template.json`, `configs/stopwords_taglish.txt`, `configs/prompts/labeling_prompt.txt`
- `topic_modeling/{__init__,pipeline,run,embed,cluster,topics,dtm,labeling,validation,checkpoint,logging_setup,io_utils}.py`
- `tests/test_{labeling_prompt,validation_filters,checkpoint_resume,label_dedup}.py`

**Reuse (no modification):**
- `preprocessing/preprocessing/io_utils.py` — copy `load_jsonl`, `write_json`, `dump_qc_report` patterns
- `preprocessing/preprocessing/logging_setup.py` — copy logger config
- `preprocessing/preprocessing/pipeline.py:50-63` — copy `@dataclass` config pattern

**Reference (read-only):**
- `methodology_changes.md:273-294` — labeling prompt (must match SHA256)
- `methodology_changes.md:438-462` — researcher distribution (template only; this plan supports 1–5)
- `Research.md:961-997` — original BERTopic configuration

**Do not modify:** anything in `preprocessing/`, `scraper_project/`, or repo root.

---

## 11. Verification Plan

End-to-end verification before declaring the phase complete:

1. **Dry-run on SLU only** with both embedders (bake-off). Inspect `embedding_bakeoff_report.md` manually; confirm winner is sensible.
2. **Single-university real run** on a small file (e.g., FW-07, 2,287 posts). Confirm:
   - All output JSONs created and well-formed.
   - `topic_assignments.json` covers all 2,287 post_ids exactly once.
   - `topic_labels.json` has one entry per non-outlier topic.
   - `topics_over_time.json` is non-empty.
   - `api_cache/labeling_responses/` contains one file per labeled topic.
   - No FATAL entries in `action_log.md`.
3. **Crash-resume test** (in `tests/test_checkpoint_resume.py`): start a run, kill it after one university completes, restart — confirm second university starts fresh and first is skipped.
4. **Unit tests** all green: `pytest topic_modeling/tests/ -v`.
5. **Lazy-label rate sanity:** on the dry run, expect 5–15% lazy labels. >30% means the prompt or representative-doc selection is broken.
6. **NIM cache audit:** spot-check 5 cached responses to confirm the prompt rendered correctly (no unfilled `[KEYWORDS]` placeholders) and the response was unmodified by the validator.
7. **Pre-merge dry-run** with two researchers' simulated outputs on FW-07 + SLU; confirm `merge.py` produces a coherent harmonization report.
8. **Methodology compliance check:** verify `prompts/labeling_prompt.txt` SHA256 matches the verbatim text in `methodology_changes.md:273-294`.

Only after all eight pass is the topic_modeling phase considered ready for full-corpus execution by the researcher team.
