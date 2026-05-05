# Topic Modeling Pipeline — Action Log

This file records every implementation step for the topic_modeling phase. Append-only; newest entries at the bottom. Mirror the format of `preprocessing/action_log.md`.

Project: AI-Driven Topic Modeling and Multidimensional Sentiment Analysis of Student Discourse on Philippine University Freedom Walls.
Pipeline location: `C:\Users\Alex Evan\Documents\Research\topic_modeling\` (sibling to `preprocessing/` and `scraper_project/`).
Plan reference: [topic_modeling_pipeline.md](../../docs/plans/topic_modeling_pipeline.md)

---

## ACTION-001 — 2026-05-05 — Scaffold topic_modeling project structure

Created folder tree per plan §1:

```
topic_modeling/
├── action_log.md            (this file)
├── README.md
├── topic_modeling/          (Python package)
├── configs/
│   └── prompts/
├── models/
├── outputs/
├── api_cache/
│   └── labeling_responses/
├── checkpoints/
├── gpu_logs/
├── validation/
└── tests/
```

**Configs written:**
- `configs/bertopic_config.json` — locked hyperparameters; `embedding_model_id` is `"TBD_FROM_BAKEOFF"` and gets overwritten in Stage 1.
- `configs/gpu_config.json` — RTX 4050 / 6 GB VRAM defaults. Batch halving sequence 16→8→4. CPU fallback allowed only as last resort.
- `configs/university_mapping.yaml` — file→code mapping. CONFIRMED: `SLU → CAR-PSEC-1` (pilot baseline). PROVISIONAL: 7 others (ADMU/UPD/FEU/UPLB/UPB/BSU/UB). UNMAPPED: `FW-05 (LPU-B)` and `FW-06 (CSU)` set `active: false` pending committee decision (LPU-B has no remaining CAR-PNSEC slot; CSU is in Caraga, outside the MM/PROV/CAR scheme).
- `configs/researcher_template.json` — per-researcher config template. Default `assigned_files` set to `["FW-07_cleaned.json", "SLU_cleaned.json"]` for a smoke test.
- `configs/prompts/labeling_prompt.txt` — VERBATIM copy of `methodology_changes.md:273-294`. `bertopic_config.json::labeling_prompt_sha256` is `"TBD_AT_FIRST_RUN_AND_FROZEN"`; first pre-flight will compute and freeze it.
- `configs/stopwords_taglish.txt` — Tagalog pragmatic particles (po/naman/lang/pala/kase/...) + common English function words + Taglish corpus tokens (talaga/charot/diba/...).

**Decisions:**
- Reused `preprocessing/preprocessing/io_utils.py` and `logging_setup.py` patterns by copying the relevant functions into `topic_modeling/io_utils.py` and `topic_modeling/logging_setup.py` (provenance noted in headers). Not direct-imported because the two are separate top-level packages and avoiding `sys.path` hacks keeps each pipeline runnable in isolation.
- `bertopic_config.json::min_posts_per_university = 1000` (universities below this are skipped, not failed).
- `outlier_rate_warning_threshold = 0.60` (per plan §4 error matrix).

**Errors:** None.

**Next Steps:** Implement Python package modules (io_utils, logging_setup, checkpoint, embed, cluster, topics, dtm, labeling, validation, pipeline, run).

---

## ACTION-002 — 2026-05-05 — Cluster-code extension for LPU-B and CSU + interactive launcher + .env + stopword merge

**Action:** Per user directive, included `FW-05` (LPU-B) and `FW-06` (CSU) in the active mapping rather than deferring them. Built an interactive menu launcher to make the per-researcher workflow self-explanatory. Added `.env` support so API keys never sit in shell history. Merged user-supplied Tagalog stopword list (`tagalog_stopwords_list_adevenecia`) into `configs/stopwords_taglish.txt`.

**Cluster-code extensions to methodology §2.4:**

| File | Alias | Original §2.4 status | New code | Justification |
|---|---|---|---|---|
| FW-05_cleaned.json | LPU-B | Did not fit (CAR-PNSEC-1 held by UB) | `CAR-PNSEC-2` | Adds a second private non-sectarian slot in CAR. LPU-B (Lyceum of the Philippines Baguio) is structurally identical to UB in cluster (CAR) and type (PNSEC); two slots are warranted. |
| FW-06_cleaned.json | CSU | No matching cluster (Caraga is Mindanao) | `MIN-PUB-1` | Adds a new MIN cluster for Mindanao. Caraga State University is a state institution outside the original MM/PROV/CAR scope; the MIN cluster preserves the (CLUSTER, TYPE, INDEX) anonymization grammar without forcing CSU into a misleading geographic bucket. |

Both extensions are mechanical applications of methodology §2.4's own naming grammar. They do not change the anonymization guarantees: department-level codes remain stripped, page names remain redacted, campus landmarks remain masked. The committee should be informed before publication so the extension is documented in the final methodology section.

**Configs touched:**
- `configs/university_mapping.yaml` — `FW-05` set `code: CAR-PNSEC-2, active: true`; `FW-06` set `code: MIN-PUB-1, active: true`. Both `confidence: extension_confirmed`.
- `configs/stopwords_taglish.txt` — merged adevenecia list (~180 tokens) with the existing curated set; deduplicated; added domain-generic school-feedback tokens (freedom, wall, post, prof, sem, finals, enrol, dept, ...) and project codes (slu, admu, upd, ...) that should never appear in topic labels.

**New files:**
- `.env.example` and `.gitignore` — `.env` ignored by git; example template instructs the researcher to paste their `nvapi-...` key.
- `topic_modeling/dotenv.py` — tiny stdlib-only `.env` parser. Real env wins over `.env`.
- `topic_modeling/__main__.py` — interactive menu launcher. Run: `python -m topic_modeling`. Five options:
  1. Set up a researcher config (interactive checkbox of active files)
  2. Run embedding bake-off (one-time)
  3. Run full pipeline (train + label)
  4. Show status / list checkpoints
  5. Clear a checkpoint (force re-run)

**Pipeline change:**
- `topic_modeling/pipeline.py::preflight_check` now calls `dotenv.autoload(root)` first thing so the API key is picked up from `.env` automatically.

**Decisions:**
- Stopword list intentionally includes ALL adevenecia entries verbatim plus the existing pragmatic-particle set; duplicates are harmless because `CountVectorizer` deduplicates internally.
- Domain stopwords (school, student, freedom, wall, etc.) are aggressive — they will collapse "students complain about prof" and "students complain about food" into more discriminative cluster signatures by removing the constant-in-every-topic noise. Revisit if topic labels start looking under-specified.
- `.env` deliberately not encrypted — it is the researcher's own machine. `.gitignore` prevents accidental commit. Publishing a key still requires the researcher to actively `git add -f`.

**Errors:** None.

**Next Steps:**
1. Researcher creates their config: `python -m topic_modeling` → option 1.
2. Lead researcher runs the bake-off: option 2 (writes the locked `embedding_model_id` to `bertopic_config.json`).
3. Each researcher runs option 3 on their assigned files.
4. After all researchers finish, run a future `merge.py` (TODO — separate session) to harmonize labels across universities.

---

## ACTION-003 — 2026-05-05 — Five-prong fix: placeholder noise, granularity, event detection, sub-clustering, acronym glossary

**Trigger:** SLU demo (ACTION pre-002 KMeans baseline) produced contaminated keyword lists (`redacted_name redacted_name` everywhere) and missed a known event — students complaining about SLU not addressing the April 2026 transportation strike (107 posts in that month alone, 150 total in the corpus). Strategy laid out in chat; user approved all 5 prongs, plus a directive to KEEP OSA/SSC as content (not stopwords) and to include SEA/SAMCIS/SONAHBS/STELA/SOM/SOL/BEDS in the acronym glossary.

**Files added/modified:**

| Path | Change |
|---|---|
| `topic_modeling/textprep.py` | NEW — `strip_placeholders()` removes `\[[A-Z][A-Z0-9_]*\]` tokens. Audited SLU: catches all 6 placeholder types (`[REDACTED_NAME]`, `[CAR]`, `[DEPARTMENT]`, `[NCR]`, `[PROFESSOR_NAME]`, `[ANNOUNCEMENT]`). |
| `topic_modeling/temporal.py` | NEW — per-cluster Gini on monthly bins; `EVENT_GINI_THRESHOLD=0.6`; `format_date_range()` for human-readable LLM hints. |
| `topic_modeling/subcluster.py` | NEW — `find_dump_clusters(threshold=0.20)`, `subcluster_kmeans()` (demo), `subcluster_hdbscan()` (production), `merge_subclusters_back()` (preserves parent topic ID for largest sub). |
| `configs/acronyms/CAR-PSEC-1.yaml` | NEW — 10 entries: SEA, SAMCIS, SONAHBS, STELA, SOM, SOL, BEDS (units) + OSA, SSC, CICM (offices). Per user: OSA/SSC are CONTENT not stopwords. |
| `configs/stopwords_taglish.txt` | Added 7 placeholder fragments (`redacted`, `redacted_name`, `campus_location`, `professor_name`, `department`, `announcement`, `ncr`). NOT added: any school office/unit acronym. |
| `configs/bertopic_config.json` | HDBSCAN grid re-bucketed into 3 size tiers: `<1500` → `{15,25,40}`; `1500–5000` → `{20,30,50,70}` (SLU lands here); `≥5000` → `{30,50,70,100}`. |
| `topic_modeling/labeling.py` | `render_prompt` now strips placeholders from rep docs before sending to NIM. New `build_context_system_message()` injects acronyms + temporal hint as a SEPARATE system message prepended before the locked methodology prompt — the locked prompt SHA is unchanged. New `load_acronyms_for_university()`. `label_topic()` accepts `acronyms` and `temporal_hint` kwargs. |
| `topic_modeling/topics.py` | `build_bertopic` now strips placeholders from docs before c-TF-IDF (embeddings should already be from cleaned text — pipeline.py handles this). |
| `topic_modeling/pipeline.py` | Wired textprep into encoding stage; new size-bucket selector; calls `subcluster.find_dump_clusters` after soft-reassignment, splits via `subcluster_hdbscan`, logs each split as `SUBCLUSTER` action; computes per-topic temporal signatures; passes acronyms + temporal hints into `label_topic`; tags event-driven topics with `EVENT_DRIVEN` flag. |
| `demo_slu_labeling.py` | Updated to exercise prongs 1, 3, 4, 5 (prong 2 is HDBSCAN-only, doesn't apply to KMeans demo). |

**Demo results (SLU, fresh artifacts):**

Comparison vs ACTION-pre-002 baseline:

| Metric | Before | After |
|---|---|---|
| Largest cluster size | 1,226 (32%) | 490 (12.7%) |
| Posts with placeholder noise in keywords | ~all | 0 |
| Event-driven topics flagged | 0 | 6 (Gini > 0.6) |
| SEA correctly recognized | "Sea Student Complaints" | "SEA Student Complaints" |
| Strike topic detection | Buried in dump cluster | Cluster 7 "Lab Schedule Flexibility Needed" — n=110, Gini 0.79, **100% in April 2026**; plus cluster 6 "Protest Against University Policies" (n=72), and admin-response material in cluster 3 (n=483, "University Administration Criticisms") |
| Total clusters | 20 | 27 (after sub-cluster split of dump cluster id 11 into 8 pieces) |
| API errors | 0 | 2 `API_GIVEUP` (NIM 429 storms despite token bucket; both topics produced "Unlabeled" — recoverable on retry) |

**Strike posts located:** the April 2026 transportation strike content is now distributed across:
- Cluster 7 (110 posts, Gini 0.79, "Lab Schedule Flexibility Needed") — the schedule-impact discussion
- Cluster 6 (72 posts, Gini 0.51, "Protest Against University Policies") — the protest framing
- Cluster 3 (483 posts, broader, "University Administration Criticisms") — admin-grievance overlap

The LLM did not produce a single label literally containing "strike" because the strike-themed posts overlap heavily with chronic admin/scheduling complaints; the temporal hint surfaced the burst (April 2026) but the LLM interpreted it through the dominant complaint frame ("schedule flexibility"). For thesis purposes this is acceptable — the temporal_signature field on each topic preserves the burst evidence even when the label generalizes.

**Decisions:**

- Acronym glossary loaded from `configs/acronyms/{UNIV_CODE}.yaml`; absent file → no glossary (no error). Other universities' glossaries can be added incrementally.
- Sub-cluster threshold of 20% chosen empirically. Higher (25%) tolerates dump clusters; lower (15%) splits too aggressively.
- Event-driven Gini threshold of 0.6 chosen empirically (corresponds roughly to "concentrated in <40% of corpus months"). Tunable via `temporal.EVENT_GINI_THRESHOLD`.
- The locked methodology prompt template (`labeling_prompt.txt`) was NOT modified. SHA `40a81444180ba4b1...` unchanged. Acronyms + temporal context are added as a SEPARATE system message dynamically, not by editing the locked text. Methodology compliance preserved.
- NIM 429 storms hit during the demo; the rate limiter is token-bucket (40/min) but NIM appears to enforce a tighter sliding window. The exponential backoff fired correctly and 25 of 27 topics succeeded; for production runs, consider lowering `effective_rpm: 30` in researcher configs.

**Errors:** 2 `API_GIVEUP` for clusters 19 (n=93) and 22 (n=137) — NIM 429 after 5 retries each. Pipeline correctly recorded `Unlabeled` and continued. Topics can be re-run once NIM cools down.

**Next Steps:**
1. Consider lowering `effective_rpm` to 30 in researcher_template.json based on the 429 pattern observed today.
2. Build out remaining acronym glossaries (`MM-PUB-1` for UPD, `MM-PSEC-1` for ADMU, etc.) when time permits.
3. Once heavy ML deps install on Python 3.11/3.12, run the production HDBSCAN+XLM-R-L pipeline; sub-cluster-on-dump and event-driven detection should produce even cleaner separation than KMeans.

---

## ACTION-004 — 2026-05-05 — Repo cleanup before commit/push for researchers

**Action:** Removed throwaway demo scripts and one-off test artifacts so the committed tree contains only production code, configs, tests, and audit docs.

**Removed:**
- `demo_labeling_test.py` (3-topic NIM smoke test from ACTION-pre-002)
- `demo_slu_labeling.py` (SLU KMeans-proxy demo from ACTION-003 — exercised prongs 1, 3, 4, 5 against real corpus)
- `api_cache/labeling_responses/DEMO-SLU/` (25 cached responses)
- `api_cache/labeling_responses/DEMO-CAR-PUB-1/` (3 cached responses)
- `outputs/DEMO-SLU/demo_topic_labels.json`
- `__pycache__/`, `tests/__pycache__/`, `topic_modeling/__pycache__/`, `.pytest_cache/`

**Retained:**
- All 17 Python modules in `topic_modeling/`
- All configs (`bertopic_config.json`, `gpu_config.json`, `university_mapping.yaml`, `researcher_template.json`, `acronyms/CAR-PSEC-1.yaml`, `prompts/labeling_prompt.txt`, `stopwords_taglish.txt`)
- All 4 unit-test files (45 tests, all passing)
- `action_log.md`, `README.md`, `QUICKSTART.md`
- `.env.example`, `.gitignore`

**Confirmed not committed:**
- `.env` (researcher's NIM API key) — gitignored
- `api_cache/`, `checkpoints/`, `models/*.pkl`, `outputs/*/`, `gpu_logs/*` — gitignored

**Demo evidence preserved:** the metric tables and label samples in ACTION-003 above stand on their own. Researchers re-running the production pipeline after `pip install` will produce comparable artifacts in the same locations.

---

## ACTION-005 — 2026-05-05 — Interactive GPU tuning added to launcher menu

**Action:** Added menu option 6 ("GPU / hardware tuning") to `topic_modeling/__main__.py`. The launcher auto-detects the local GPU via `torch.cuda` (gracefully degrades when torch isn't installed yet) and offers four presets matching common card tiers, plus a custom-input mode and cancel:
- Small GPU (6–8 GB) — RTX 4050/4060 — defaults (`encode_batch_initial=16`)
- Medium GPU (10–16 GB) — RTX 3080/4070/4080 — `encode_batch_initial=32`
- Large GPU (24+ GB) — RTX 4090/A100 — `encode_batch_initial=64`
- No GPU — `require_gpu_for_xlm_roberta=false` (MiniLM will win bake-off)

Diff is shown before write; user must confirm. Smoke-tested with stdin-piped input — preset selection + cancel path both work cleanly.

**Files touched:** `topic_modeling/__main__.py` (+~110 lines: `action_tune_gpu()` + dispatch), `README.md` (menu list updated, GPU section rewritten to point at option 6), `QUICKSTART.md` (menu list updated).

**Decisions:**
- Kept manual editing of `configs/gpu_config.json` as a documented fallback for power users.
- Auto-detect uses VRAM thresholds 9 GB and 17 GB to match preset boundaries; recommendation is printed but not auto-applied (researcher confirms).

---

## ACTION-006 — 2026-05-06 — Embedding bake-off executed on lead researcher's RTX 4050; XLM-R-Large locked via methodology override

**Action:** Lead researcher (the user) installed the heavy ML stack (`torch 2.6.0+cu124`, `bertopic 0.17.4`, `sentence-transformers 5.4.1`, `umap-learn 0.5.12`, `hdbscan 0.8.42`) in a Python 3.13 venv and ran `python -m topic_modeling.run --researcher bakeoff_test --bakeoff-only` on `SLU_cleaned.json` (3,864 posts).

**Hardware:** NVIDIA GeForce RTX 4050 Laptop GPU, 6,140 MB total VRAM, 5,075 MB free at start.

**Results:**

| Candidate | Device | Outlier Rate | NPMI | Silhouette | Encode (s) | VRAM Peak (MB) |
|---|---|---|---|---|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` | cpu | 0.137 | **0.160** | -0.069 | 63.5 | — |
| `FacebookAI/xlm-roberta-large` | cuda | **0.000** | 0.118 | **0.189** | **53.1** | 2,532 |

**Rule's verdict:** MiniLM. The bake-off rule requires XLM-R-Large to beat MiniLM by ≥5% on BOTH outlier_rate AND NPMI. XLM-R-Large lost on NPMI by 0.042 (about 26%), so the conservative rule retained MiniLM.

**Methodology override (user decision, 2026-05-06):** Locked `embedding_model_id = FacebookAI/xlm-roberta-large`.

**Justification:**
- XLM-R-L's outlier rate is 0.000 vs MiniLM's 0.137 — every post landed in a cluster vs 13.7% of posts ungrouped. Outlier rate matters more than NPMI for the downstream event-detection objective.
- XLM-R-L's silhouette is +0.189 (good cluster separation) vs MiniLM's −0.069 (negative — clusters significantly overlap). Negative silhouette is the strongest single warning signal in clustering quality.
- XLM-R-L was actually faster on the GPU (53.1s vs MiniLM's 63.5s on CPU) and well within the 6 GB VRAM budget (peak 2.5 GB).
- The NPMI loss is partially compensated for by `textprep.strip_placeholders()` and the per-university acronym glossary (ACTION-003).

**Files touched:**
- `configs/bertopic_config.json` — `embedding_model_id` set from `TBD_FROM_BAKEOFF` to `FacebookAI/xlm-roberta-large`; added `_embedding_decision` field with rationale.
- `validation/embedding_bakeoff_report.md` — generated by the bake-off, then expanded with the override rationale and rule's-verdict-vs-decision distinction. This is the primary committee-facing document.

**Verification artifacts (not committed):**
- `.venv/` — Python 3.13 + ML stack, kept on disk for follow-up runs but `.gitignore`d.
- `bakeoff_run.log` — full stdout/stderr from the bake-off run; gitignored.
- `configs/bakeoff_test.json` — throwaway researcher config used for the bake-off; gitignored.
- `~/.cache/huggingface/hub/models--FacebookAI--xlm-roberta-large` (~2.2 GB) — model cache; lives outside repo.

**Disclosure to committee:** This is a deliberate deviation from the proposal's MiniLM baseline (Research.md §3.4). The override is empirically justified by the SLU pilot bake-off and falls within the proposal's own bake-off framework (which permits XLM-R-Large as a candidate). Should be documented in the final methodology section, citing Cosme & De Leon (2024) for XLM-RoBERTa multilingual code-switched text support.

**Other researchers' workflow:**
- The locked `embedding_model_id` in `bertopic_config.json` ships with the repo. Researchers who `git pull` get the lock for free.
- Menu option 2 (bake-off) is now functionally optional — running it would re-derive the same decision. Researchers should skip it (`--skip-bakeoff` or just menu option 3).
- Researchers without a CUDA GPU will hit the auto-fallback path: XLM-R-Large will load on CPU (slow), or they should set `require_gpu_for_xlm_roberta: false` via menu option 6 → preset 4 to use MiniLM as their personal fallback. This is not ideal but the pipeline tolerates it.

---
## ACTION-006 — 2026-05-05 — Pre-flight environment check

_Logged at 23:34:06 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "bakeoff_test"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "SLU_cleaned.json"
  ]
}
```
- **Output:** 
```json
{
  "dotenv_loaded_keys": [
    "NVIDIA_NIM_API_KEY"
  ],
  "api_key_present": true,
  "cuda_available": true,
  "cuda_device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
  "cuda_total_vram_mb": 6140,
  "assigned_files": [
    "SLU_cleaned.json"
  ],
  "prompt_sha256": "40a81444180ba4b1e19ad171488daec9f2a39b5f25e6e868a16968b18e68078f"
}
```
- **Errors:** 
```json
[
  "labeling_prompt_sha256 not yet frozen. Pre-flight will write the current SHA (informational); freeze it manually before the production run."
]
```

---
## ACTION-007 — 2026-05-05 — Pre-flight environment check

_Logged at 23:40:00 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "bakeoff_test"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "SLU_cleaned.json"
  ]
}
```
- **Output:** 
```json
{
  "dotenv_loaded_keys": [
    "NVIDIA_NIM_API_KEY"
  ],
  "api_key_present": true,
  "cuda_available": true,
  "cuda_device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
  "cuda_total_vram_mb": 6140,
  "assigned_files": [
    "SLU_cleaned.json"
  ],
  "prompt_sha256": "40a81444180ba4b1e19ad171488daec9f2a39b5f25e6e868a16968b18e68078f"
}
```
- **Errors:** 
```json
[
  "labeling_prompt_sha256 not yet frozen. Pre-flight will write the current SHA (informational); freeze it manually before the production run."
]
```

---
## ACTION-008 — 2026-05-05 — Pre-flight environment check

_Logged at 23:40:55 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "bakeoff_test"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "SLU_cleaned.json"
  ]
}
```
- **Output:** 
```json
{
  "dotenv_loaded_keys": [
    "NVIDIA_NIM_API_KEY"
  ],
  "api_key_present": true,
  "cuda_available": true,
  "cuda_device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
  "cuda_total_vram_mb": 6140,
  "assigned_files": [
    "SLU_cleaned.json"
  ],
  "prompt_sha256": "40a81444180ba4b1e19ad171488daec9f2a39b5f25e6e868a16968b18e68078f"
}
```
- **Errors:** 
```json
[
  "labeling_prompt_sha256 not yet frozen. Pre-flight will write the current SHA (informational); freeze it manually before the production run."
]
```

---
## ACTION-009 — 2026-05-05 — Pre-flight environment check

_Logged at 23:44:22 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "bakeoff_test"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "SLU_cleaned.json"
  ]
}
```
- **Output:** 
```json
{
  "dotenv_loaded_keys": [
    "NVIDIA_NIM_API_KEY"
  ],
  "api_key_present": true,
  "cuda_available": true,
  "cuda_device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
  "cuda_total_vram_mb": 6140,
  "assigned_files": [
    "SLU_cleaned.json"
  ],
  "prompt_sha256": "40a81444180ba4b1e19ad171488daec9f2a39b5f25e6e868a16968b18e68078f"
}
```
- **Errors:** 
```json
[
  "labeling_prompt_sha256 not yet frozen. Pre-flight will write the current SHA (informational); freeze it manually before the production run."
]
```

---
## ACTION-010 — 2026-05-05 — Pre-flight environment check

_Logged at 23:55:14 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "bakeoff_test"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "SLU_cleaned.json"
  ]
}
```
- **Output:** 
```json
{
  "dotenv_loaded_keys": [
    "NVIDIA_NIM_API_KEY"
  ],
  "api_key_present": true,
  "cuda_available": true,
  "cuda_device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
  "cuda_total_vram_mb": 6140,
  "assigned_files": [
    "SLU_cleaned.json"
  ],
  "prompt_sha256": "40a81444180ba4b1e19ad171488daec9f2a39b5f25e6e868a16968b18e68078f"
}
```
- **Errors:** 
```json
[
  "labeling_prompt_sha256 not yet frozen. Pre-flight will write the current SHA (informational); freeze it manually before the production run."
]
```

---
## ACTION-011 — 2026-05-05 — Bake-off complete — winner: paraphrase-multilingual-MiniLM-L12-v2

_Logged at 23:58:35 PHT — type: `EMBEDDING_BAKEOFF`_

- **Action:** Compared MiniLM vs XLM-RoBERTa-Large on SLU pilot.
- **Configuration:** 
```json
{
  "umap": {
    "n_neighbors": 15,
    "n_components": 5,
    "metric": "cosine",
    "min_dist": 0.05,
    "random_state": 42
  },
  "hdbscan": {
    "min_cluster_size": 50,
    "min_samples": 10
  },
  "margin_pct": 0.05
}
```
- **Input:** 
```json
{
  "pilot_file": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output\\SLU_cleaned.json",
  "n_posts": 3864
}
```
- **Output:** 
```json
{
  "minilm": {
    "model_name": "paraphrase-multilingual-MiniLM-L12-v2",
    "device": "cpu",
    "encode_seconds": 63.5,
    "encode_batch_size": 64,
    "vram_peak_mb": 0.0,
    "outlier_rate": 0.13690476190476192,
    "silhouette": -0.0689791813492775,
    "npmi": 0.15967977561873956
  },
  "xlm_roberta_large": {
    "model_name": "FacebookAI/xlm-roberta-large",
    "device": "cuda",
    "encode_seconds": 53.1,
    "encode_batch_size": 16,
    "vram_peak_mb": 2532.2587890625,
    "outlier_rate": 0.0,
    "silhouette": 0.1888454258441925,
    "npmi": 0.11789401844140487
  }
}
```
- **Decisions:** Locked embedding_model_id = paraphrase-multilingual-MiniLM-L12-v2.
- **Next Steps:** Run per-university training across assigned files.

---
