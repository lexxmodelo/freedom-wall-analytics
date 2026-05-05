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
## ACTION-012 — 2026-05-06 — Pre-flight environment check

_Logged at 00:21:50 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "alexx"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
  "cuda_available": false,
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
## ACTION-013 — 2026-05-06 — HDBSCAN grid search — MM-PSEC-1

_Logged at 00:33:24 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      20,
      30,
      50,
      70
    ],
    "min_samples": [
      5,
      10,
      15
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.6004,
    "npmi": 0.1925,
    "score": 0.4764,
    "n_clusters": 2
  },
  "all_results": [
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    }
  ]
}
```

---
## ACTION-014 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PSEC-1

_Logged at 00:33:53 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      15,
      20,
      25
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 3329,
  "n_subclusters": 2,
  "n_outliers_in_sub": 2450,
  "new_topic_ids": [
    2
  ]
}
```

---
## ACTION-015 — 2026-05-06 — OUTLIER_HIGH — MM-PSEC-1 (65.60%)

_Logged at 00:33:53 PHT — type: `OUTLIER_HIGH`_

- **Action:** Outlier rate exceeds threshold; flagged for human review.
- **Configuration:** 
```json
{
  "hdbscan_params": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.6004,
    "npmi": 0.1925,
    "score": 0.4764,
    "n_clusters": 2
  },
  "soft_threshold": 0.5
}
```
- **Output:** 
```json
{
  "final_outlier_rate": 0.6559571619812584,
  "soft_stats": {
    "reassigned": 0,
    "outlier_count": 0
  }
}
```
- **Decisions:** Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.
- **Next Steps:** Manual review of outlier_report.json.

---
## ACTION-016 — 2026-05-06 — Completed MM-PSEC-1

_Logged at 00:34:02 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 2 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 20,
    "min_samples": 5
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "file": "FW-01_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 3,
  "outlier_rate": 0.6559571619812584,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-017 — 2026-05-06 — HDBSCAN grid search — MM-PUB-1

_Logged at 00:42:25 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      20,
      30,
      50,
      70
    ],
    "min_samples": [
      5,
      10,
      15
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.3844,
    "npmi": 0.1546,
    "score": 0.3926,
    "n_clusters": 3
  },
  "all_results": [
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3844,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3848,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 15,
      "outlier_rate": 0.0036,
      "silhouette": 0.3866,
      "npmi": 0.1539,
      "score": 0.3922,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3844,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3848,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 15,
      "outlier_rate": 0.0036,
      "silhouette": 0.3866,
      "npmi": 0.1539,
      "score": 0.3922,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 50,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3844,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 50,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3848,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 50,
      "min_samples": 15,
      "outlier_rate": 0.0036,
      "silhouette": 0.3866,
      "npmi": 0.1539,
      "score": 0.3922,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 70,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3844,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 70,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3848,
      "npmi": 0.1546,
      "score": 0.3926,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 70,
      "min_samples": 15,
      "outlier_rate": 0.0036,
      "silhouette": 0.3866,
      "npmi": 0.1539,
      "score": 0.3922,
      "n_clusters": 3
    }
  ]
}
```

---
## ACTION-018 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PUB-1

_Logged at 00:42:46 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      15,
      20,
      25
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1826,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1826,
  "new_topic_ids": []
}
```

---
## ACTION-019 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PUB-1

_Logged at 00:42:49 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      15,
      20,
      25
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1662,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1662,
  "new_topic_ids": []
}
```

---
## ACTION-020 — 2026-05-06 — OUTLIER_HIGH — MM-PUB-1 (97.48%)

_Logged at 00:42:49 PHT — type: `OUTLIER_HIGH`_

- **Action:** Outlier rate exceeds threshold; flagged for human review.
- **Configuration:** 
```json
{
  "hdbscan_params": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.3844,
    "npmi": 0.1546,
    "score": 0.3926,
    "n_clusters": 3
  },
  "soft_threshold": 0.5
}
```
- **Output:** 
```json
{
  "final_outlier_rate": 0.9748462828395752,
  "soft_stats": {
    "reassigned": 0,
    "outlier_count": 0
  }
}
```
- **Decisions:** Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.
- **Next Steps:** Manual review of outlier_report.json.

---
## ACTION-021 — 2026-05-06 — Completed MM-PUB-1

_Logged at 00:43:06 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 3 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 20,
    "min_samples": 5
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "file": "FW-02_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 1,
  "outlier_rate": 0.9748462828395752,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-022 — 2026-05-06 — Pre-flight environment check

_Logged at 01:00:00 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "alexx"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
  "cuda_available": false,
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
## ACTION-023 — 2026-05-06 — HDBSCAN grid search — MM-PSEC-1

_Logged at 01:10:40 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      20,
      30,
      50,
      70
    ],
    "min_samples": [
      5,
      10,
      15
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.6004,
    "npmi": 0.1925,
    "score": 0.4764,
    "n_clusters": 2
  },
  "all_results": [
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.6004,
      "npmi": 0.1925,
      "score": 0.4764,
      "n_clusters": 2
    }
  ]
}
```

---
## ACTION-024 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PSEC-1

_Logged at 01:11:09 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      15,
      20,
      25
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 3329,
  "n_subclusters": 2,
  "n_outliers_in_sub": 2450,
  "new_topic_ids": [
    2
  ],
  "skipped": false
}
```

---
## ACTION-025 — 2026-05-06 — OUTLIER_HIGH — MM-PSEC-1 (65.60%)

_Logged at 01:11:09 PHT — type: `OUTLIER_HIGH`_

- **Action:** Outlier rate exceeds threshold; flagged for human review.
- **Configuration:** 
```json
{
  "hdbscan_params": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.6004,
    "npmi": 0.1925,
    "score": 0.4764,
    "n_clusters": 2
  },
  "soft_threshold": 0.5
}
```
- **Output:** 
```json
{
  "final_outlier_rate": 0.6559571619812584,
  "soft_stats": {
    "reassigned": 0,
    "outlier_count": 0
  }
}
```
- **Decisions:** Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.
- **Next Steps:** Manual review of outlier_report.json.

---
## ACTION-026 — 2026-05-06 — Completed MM-PSEC-1

_Logged at 01:11:22 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 2 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 20,
    "min_samples": 5
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "file": "FW-01_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 3,
  "outlier_rate": 0.6559571619812584,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---

## ACTION-027 — 2026-05-06 — UMAP n_components 5→30 + sub-cluster propagation fix (root cause: 2-topic ceiling)

**Trigger:** After deploying ACTION-006 (XLM-R-Large override) and the early dump-cluster annihilation fix, MM-PSEC-1 still produced only 2 labeled topics (3 topics in metadata, but topic 2 with 16 posts had no keywords/labels). User flagged this as insufficient for analysis.

**Root cause #1 — UMAP collapse:** The HDBSCAN grid search ran 12 different parameter configurations against the SAME UMAP-reduced space and produced **identical** results across all 12 (`outlier_rate: 0.0, npmi: 0.1925, silhouette: 0.6004, n_clusters: 2`). That means the UMAP-reduced space had only 2 dense regions regardless of HDBSCAN's cluster-size threshold. The grid was effectively dead.

The cause: `umap.n_components: 5` was inherited from Research.md, written when the proposal still specified MiniLM (384-dim). After ACTION-006's override to XLM-RoBERTa-Large (1024-dim), the same n_components=5 with min_dist=0.05 collapsed the manifold into 2 super-dense clumps. BERTopic's documentation recommends 5–50 components for clustering; 5 is the floor and inappropriate for high-dim embedders.

**Root cause #2 — Sub-cluster IDs invisible to BERTopic:** Pipeline created new topic IDs by mutating `new_topics` directly. BERTopic's internal `get_topics()` / `get_representative_docs()` still reflected the original clustering, so new sub-cluster IDs got entries in `topic_assignments.json` but were missing from `topic_keywords.json`, `topic_rep_docs.json`, and `topic_labels.json`.

**Fix:**

| File | Change |
|---|---|
| `configs/bertopic_config.json` | `umap.n_components: 5 → 30`. Added inline `_comment` documenting the rationale. |
| `topic_modeling/pipeline.py` | Added `topic_model.update_topics(docs, topics=new_topics.tolist(), vectorizer_model=topic_model.vectorizer_model)` after sub-clustering when `any_real_split=True`. This recomputes c-TF-IDF + representative docs against the new label array so all sub-cluster IDs become visible to keyword extraction and labeling. Wrapped in try/except so a failure just logs a warning and proceeds with stale state. |

**Verification:** All 50 tests still pass after the change. The actual production verification is the next re-run of MM-PSEC-1 — expected behavior:
- HDBSCAN grid produces NON-identical results across configs (different mcs values now find different cluster counts in the higher-dim UMAP space)
- More than 2 final topics with reasonable size distribution
- Outlier rate < 60%

**Methodology note:** The n_components change is a methodology adjustment paired with the XLM-R-Large override (ACTION-006). The proposal's value (5) was pinned to MiniLM. With XLM-R-Large locked, the dimensionality reduction must scale up to preserve density structure. This should be disclosed to the committee alongside the embedding change. BERTopic's official documentation supports 5–50 components for general clustering tasks.

**Recovery instructions for the running batch:**
1. Stop the current run (Ctrl+C in the terminal running `python -m topic_modeling`).
2. Clear MM-PSEC-1's checkpoint via menu option 5, or manually: `Remove-Item checkpoints\<researcher_id>\MM-PSEC-1_state.json`.
3. Also clear `outputs\MM-PSEC-1\` and `api_cache\labeling_responses\MM-PSEC-1\` since those reflect the buggy state.
4. Re-run via menu option 3.

The first re-run of MM-PSEC-1 will re-encode SLU embeddings (slow) but subsequent universities reuse the cached XLM-R-L model.

## ACTION-028 — 2026-05-06 — Pre-flight environment check

_Logged at 01:22:21 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "alexx"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
  "cuda_available": false,
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
## ACTION-029 — 2026-05-06 — HDBSCAN grid search — MM-PSEC-1

_Logged at 01:33:17 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      20,
      30,
      50,
      70
    ],
    "min_samples": [
      5,
      10,
      15
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.601,
    "npmi": 0.1924,
    "score": 0.4765,
    "n_clusters": 2
  },
  "all_results": [
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 50,
      "min_samples": 15,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.601,
      "npmi": 0.1924,
      "score": 0.4765,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 70,
      "min_samples": 10,
      "outlier_rate": 0.0024,
      "silhouette": 0.1794,
      "npmi": 0.1931,
      "score": 0.3499,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 70,
      "min_samples": 15,
      "outlier_rate": 0.0056,
      "silhouette": 0.1817,
      "npmi": 0.1918,
      "score": 0.3493,
      "n_clusters": 3
    }
  ]
}
```

---
## ACTION-030 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PSEC-1

_Logged at 01:33:47 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      15,
      20,
      25
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 3330,
  "n_subclusters": 2,
  "n_outliers_in_sub": 2451,
  "new_topic_ids": [
    2
  ],
  "skipped": false
}
```

---
## ACTION-031 — 2026-05-06 — OUTLIER_HIGH — MM-PSEC-1 (65.62%)

_Logged at 01:33:48 PHT — type: `OUTLIER_HIGH`_

- **Action:** Outlier rate exceeds threshold; flagged for human review.
- **Configuration:** 
```json
{
  "hdbscan_params": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.601,
    "npmi": 0.1924,
    "score": 0.4765,
    "n_clusters": 2
  },
  "soft_threshold": 0.5
}
```
- **Output:** 
```json
{
  "final_outlier_rate": 0.6562248995983936,
  "soft_stats": {
    "reassigned": 0,
    "outlier_count": 0
  }
}
```
- **Decisions:** Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.
- **Next Steps:** Manual review of outlier_report.json.

---
## ACTION-032 — 2026-05-06 — Completed MM-PSEC-1

_Logged at 01:34:06 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 3 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 20,
    "min_samples": 5
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "file": "FW-01_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 3,
  "outlier_rate": 0.6562248995983936,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-033 — 2026-05-06 — HDBSCAN grid search — MM-PUB-1

_Logged at 01:42:04 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      20,
      30,
      50,
      70
    ],
    "min_samples": [
      5,
      10,
      15
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 20,
    "min_samples": 5,
    "outlier_rate": 0.0,
    "silhouette": 0.3978,
    "npmi": 0.1547,
    "score": 0.3967,
    "n_clusters": 3
  },
  "all_results": [
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 15,
      "outlier_rate": 0.002,
      "silhouette": 0.3993,
      "npmi": 0.1545,
      "score": 0.3966,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 15,
      "outlier_rate": 0.002,
      "silhouette": 0.3993,
      "npmi": 0.1545,
      "score": 0.3966,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 50,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 50,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 50,
      "min_samples": 15,
      "outlier_rate": 0.002,
      "silhouette": 0.3993,
      "npmi": 0.1545,
      "score": 0.3966,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 70,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 70,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.3978,
      "npmi": 0.1547,
      "score": 0.3967,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 70,
      "min_samples": 15,
      "outlier_rate": 0.002,
      "silhouette": 0.3993,
      "npmi": 0.1545,
      "score": 0.3966,
      "n_clusters": 3
    }
  ]
}
```

---
## ACTION-034 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PUB-1

_Logged at 01:42:26 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      15,
      20,
      25
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1827,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1827,
  "new_topic_ids": [],
  "skipped": true,
  "skipped_reason": "no real sub-clusters found; parent cluster preserved"
}
```

---
## ACTION-035 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PUB-1

_Logged at 01:42:28 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      15,
      20,
      25
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1661,
  "n_subclusters": 2,
  "n_outliers_in_sub": 1621,
  "new_topic_ids": [
    3
  ],
  "skipped": false
}
```

---
## ACTION-036 — 2026-05-06 — Completed MM-PUB-1

_Logged at 01:42:33 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 4 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 20,
    "min_samples": 5
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "file": "FW-02_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 4,
  "outlier_rate": 0.4530463946338737,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---

## ACTION-028 — 2026-05-06 — Grid floors + min_cluster_count constraint (supersedes ACTION-027 reasoning)

**Trigger:** ACTION-027's UMAP n_components 5→30 change failed to produce more topics. User flagged "still less than 5 topics" and asked for a test before another full pipeline run.

**Empirical investigation:** Ran a 120-config sweep on cached SLU-1000 XLM-R-L embeddings, varying `n_neighbors ∈ {5,10,15,30}`, `n_components ∈ {5,30}`, `min_cluster_size ∈ {10,15,20,30,50}`, `min_samples ∈ {3,5,10}`.

**Findings:**
1. **n_components 30 is NOT the lever.** At n_neighbors=10, n_components=5 found 16 clusters at mcs=10/ms=3, but n_components=30 found only 4 with the same HDBSCAN params. Bumping to 30 sometimes HURTS.
2. **Real lever is min_cluster_size and min_samples**: at mcs=10, ms=3 the grid finds 8–22 clusters depending on UMAP params. The previous floor (mcs=20, ms=5) was simply too coarse for the XLM-R-L manifold.
3. **Even with the right grid, the score function rejects high-cluster configs**: with `0.5*NPMI + 0.3*silhouette + 0.2*(1-outlier)`, a 2-cluster solution scored 0.55 vs a 4-cluster solution scored 0.42 because NPMI drops as keywords spread across more clusters. The grid's selection is biased toward few-but-tight even when more is achievable.

**Fix (this action, supersedes ACTION-027 n_components claim):**

| File | Change |
|---|---|
| `configs/bertopic_config.json` | UMAP `n_components: 30 → 5` (reverted; the 30 change was empirically inert). Added `_comment` to document. HDBSCAN grid floors lowered across all tiers: small `[10,15,25]×[3,5]`, medium `[10,15,20,30]×[3,5,10]`, default `[15,25,50,80]×[3,5,10]`, outlier_recovery `[10,15,20]×[3,5]`. New top-level setting `"min_cluster_count_floor": 5`. |
| `topic_modeling/cluster.py::grid_search_hdbscan` | Added `min_cluster_count_floor` kwarg. After grid runs, **prefer configs with `n_clusters >= floor` if any exist**; only fall back to overall-best score if zero configs meet the floor (logs a `_floor_fallback: True` flag in that case). |
| `topic_modeling/pipeline.py` | Threads `min_cluster_count_floor` from config into the grid search call. |

**Verification (cached SLU-1000 embeddings):**

Before fix (production grid with mcs floor 20):
```
mcs=20 ms=5  → n_clusters=4, score=0.4165   (eligible, but only 4)
mcs=20 ms=10 → n_clusters=2, score=0.5519   ← grid picked THIS
... (all higher mcs → 2 clusters)
```

After fix (production grid with mcs floor 10 + cluster_count_floor=5):
```
>> mcs=10 ms=3 → n_clusters=11, score=0.382
>> mcs=10 ms=5 → n_clusters=12, score=0.333
>> mcs=15 ms=3 → n_clusters=8,  score=0.386
>> mcs=15 ms=5 → n_clusters=5,  score=0.390
>> mcs=25 ms=3 → n_clusters=6,  score=0.394   ← SELECTED (highest score among >=5)
   mcs=25 ms=5 → n_clusters=4,  score=0.416   (rejected by floor)
```

The selection rule correctly rejected the highest-scoring (4-cluster) config and picked the highest-scoring config that meets the floor (6 clusters, 5.3% outliers, silhouette 0.548).

**Decisions:**
- `min_cluster_count_floor: 5` chosen as the minimum for thesis-meaningful analysis. Universities with truly homogeneous discourse may legitimately produce fewer clusters; in those cases the fallback engages and `_floor_fallback: True` flags the result for human review.
- The score function itself is NOT changed (still 0.5/0.3/0.2 weights). Adding a hard cluster-count floor is more interpretable and committee-defensible than tuning the weights.
- `n_components=5` is restored to match Research.md exactly. ACTION-027's bump to 30 had no measurable benefit and a methodology cost (deviation from proposal).

**Verification artifacts (gitignored):**
- `test_umap_dim_fix.py` (scratch test script — deleted before commit)
- `_test_embeddings_slu1000.npy` (cached embeddings, ~3.9 MB — deleted before commit)

**Recovery for the running batch:**
1. Stop current run (Ctrl+C).
2. Clear MM-PSEC-1's stale state: `outputs/MM-PSEC-1`, `api_cache/labeling_responses/MM-PSEC-1`, `checkpoints/<rid>/MM-PSEC-1_state.json`.
3. Re-run via menu option 3.

Expected behavior: every university now selects a config with n_clusters ≥ 5 (unless none in the grid achieve it, in which case the fallback flag is set).

## ACTION-037 — 2026-05-06 — Pre-flight environment check

_Logged at 02:00:40 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "alexx"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
  "cuda_available": false,
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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

## ACTION-029 — 2026-05-06 — Doc fix: install torch with CUDA index URL, not from default PyPI

**Trigger:** Lead researcher's venv installed `torch 2.11.0+cpu` (CPU-only) from the default `pip install torch` line in QUICKSTART/README. The pipeline auto-fell-back to CPU and emitted `WARNING | embed | Candidate xlm_roberta_large requested cuda but cuda is unavailable; falling back to cpu`. Encoding was running ~5–6× slower than necessary (CPU 5 min/uni vs GPU ~50 sec/uni).

**Root cause:** `pip install torch` on Windows defaults to CPU-only wheels. The CUDA wheels are only available from PyTorch's official index (`https://download.pytorch.org/whl/cu124`). The original install instructions bundled torch into a single `pip install ...` line which made this trap easy to fall into.

**Fix:**
- `QUICKSTART.md` — split install into two steps (GPU users first install torch from CUDA index, then the rest; non-GPU users install plain torch + use launcher option 6 → preset 4). Added an explicit step 3 "Verify CUDA actually works" with the recovery command if the wrong build was installed. Updated test count expectation 45 → 50.
- `README.md` — same restructure of the install snippet, with an inline verification command and an explanation of the CPU-trap symptom.

**No code changes.** The pipeline already auto-handles CPU fallback gracefully; this is purely a documentation/onboarding fix to prevent researchers from spending hours on CPU encoding by accident.

**Recovery for the lead researcher's local venv:**
```powershell
.venv\Scripts\python -m pip uninstall -y torch
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu124
```

Subsequent runs will use the GPU correctly.

## ACTION-038 — 2026-05-06 — Pre-flight environment check

_Logged at 02:08:19 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "alexx"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
## ACTION-039 — 2026-05-06 — HDBSCAN grid search — MM-PSEC-1

_Logged at 02:09:56 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 10,
    "min_samples": 3,
    "outlier_rate": 0.0,
    "silhouette": 0.5803,
    "npmi": 0.1918,
    "score": 0.47,
    "n_clusters": 2,
    "_floor_fallback": true
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2,
      "_floor_fallback": true
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    }
  ]
}
```

---
## ACTION-040 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PSEC-1

_Logged at 02:10:24 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 3328,
  "n_subclusters": 2,
  "n_outliers_in_sub": 2449,
  "new_topic_ids": [
    2
  ],
  "skipped": false
}
```

---
## ACTION-041 — 2026-05-06 — OUTLIER_HIGH — MM-PSEC-1 (65.57%)

_Logged at 02:10:25 PHT — type: `OUTLIER_HIGH`_

- **Action:** Outlier rate exceeds threshold; flagged for human review.
- **Configuration:** 
```json
{
  "hdbscan_params": {
    "min_cluster_size": 10,
    "min_samples": 3,
    "outlier_rate": 0.0,
    "silhouette": 0.5803,
    "npmi": 0.1918,
    "score": 0.47,
    "n_clusters": 2,
    "_floor_fallback": true
  },
  "soft_threshold": 0.5
}
```
- **Output:** 
```json
{
  "final_outlier_rate": 0.6556894243641231,
  "soft_stats": {
    "reassigned": 0,
    "outlier_count": 0
  }
}
```
- **Decisions:** Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.
- **Next Steps:** Manual review of outlier_report.json.

---
## ACTION-042 — 2026-05-06 — Completed MM-PSEC-1

_Logged at 02:10:42 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 3 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 10,
    "min_samples": 3
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "file": "FW-01_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 3,
  "outlier_rate": 0.6556894243641231,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-043 — 2026-05-06 — HDBSCAN grid search — MM-PUB-1

_Logged at 02:11:34 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 15,
    "min_samples": 3,
    "outlier_rate": 0.0,
    "silhouette": 0.3865,
    "npmi": 0.1546,
    "score": 0.3932,
    "n_clusters": 3,
    "_floor_fallback": true
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0003,
      "silhouette": 0.2702,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0017,
      "silhouette": 0.2713,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0025,
      "silhouette": 0.2704,
      "npmi": 0.0591,
      "score": 0.3102,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3,
      "_floor_fallback": true
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    }
  ]
}
```

---
## ACTION-044 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PUB-1

_Logged at 02:11:59 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1828,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1828,
  "new_topic_ids": [],
  "skipped": true,
  "skipped_reason": "no real sub-clusters found; parent cluster preserved"
}
```

---
## ACTION-045 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PUB-1

_Logged at 02:12:02 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1660,
  "n_subclusters": 2,
  "n_outliers_in_sub": 1620,
  "new_topic_ids": [
    3
  ],
  "skipped": false
}
```

---
## ACTION-046 — 2026-05-06 — Completed MM-PUB-1

_Logged at 02:12:47 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 4 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 15,
    "min_samples": 3
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "file": "FW-02_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 4,
  "outlier_rate": 0.45276690888764676,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-047 — 2026-05-06 — HDBSCAN grid search — MM-PNSEC-1

_Logged at 02:13:50 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3963,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 10,
    "min_samples": 10,
    "outlier_rate": 0.0053,
    "silhouette": 0.2026,
    "npmi": -0.0024,
    "score": 0.2585,
    "n_clusters": 6
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    }
  ]
}
```

---
## ACTION-048 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PNSEC-1

_Logged at 02:14:14 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1871,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1871,
  "new_topic_ids": [],
  "skipped": true,
  "skipped_reason": "no real sub-clusters found; parent cluster preserved"
}
```

---
## ACTION-049 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PNSEC-1

_Logged at 02:14:16 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1856,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1856,
  "new_topic_ids": [],
  "skipped": true,
  "skipped_reason": "no real sub-clusters found; parent cluster preserved"
}
```

---
## ACTION-050 — 2026-05-06 — Completed MM-PNSEC-1

_Logged at 02:14:34 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 6 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 10,
    "min_samples": 10
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3963,
  "file": "FW-03_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 6,
  "outlier_rate": 0.005299015897047691,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-051 — 2026-05-06 — Run complete for alexx

_Logged at 02:14:34 PHT — type: `RUN_COMPLETE`_

- **Output:** 
```json
{
  "n_universities_processed": 3,
  "wall_seconds": 376.5,
  "needs_review_count": 3
}
```

---

## ACTION-052 — 2026-05-06 — min_samples=2 grid + reduce_topics fallback (MM-PSEC-1: 3 → 14 topics)

**Trigger:** ACTION-028's lower grid floors got MM-PNSEC-1 to 6 topics, but MM-PSEC-1 still produced only 3 with 65.6% outliers and MM-PUB-1 produced 4 with 45.3% outliers. User flagged this as overgeneralizing.

**Empirical investigation (real MM-PSEC-1 embeddings, GPU encoded):** Sweep over `mcs ∈ {3,5,8,10,15,20,30}`, `ms ∈ {2,3,5,10}` revealed a sharp **bimodal density structure**:
- `min_samples >= 3`: HDBSCAN finds exactly **2 clusters** with 0% outliers, regardless of mcs.
- `min_samples == 2`: HDBSCAN finds **44–381 micro-clusters** with 33–35% outliers, depending on mcs.

There is no "middle" — MM-PSEC-1's discourse density structure is genuinely binary. The grid was picking the 2-cluster solution because we required `ms >= 3`. Lowering to `ms = 2` floods the result with too many micro-clusters (44 at mcs=15, the cleanest of the granular configs).

**Fix:**

| File | Change |
|---|---|
| `configs/bertopic_config.json` | Added `min_samples: 2` to small/medium/default/outlier_recovery grids. New top-level settings `target_topic_count: 15` and `reduce_topics_threshold: 25`. |
| `topic_modeling/pipeline.py` | After grid + sub-clustering + soft-reassignment + update_topics, if final non-outlier topic count exceeds `reduce_topics_threshold`, call `topic_model.reduce_topics(docs, nr_topics=target_topic_count)` to merge similar topics by c-TF-IDF cosine similarity. The reduce_topics call updates `topic_model.topics_` in place. Logged as `REDUCE_TOPICS` action when it fires. |

**Verification (real MM-PSEC-1 corpus, 3,735 posts):**

```
Before fix:
  Grid picked: mcs=10, ms=3 → 2 clusters
  After sub-clustering corruption: 3 topics, 65.6% outliers (cluster 2 had 16 docs)

After fix:
  Grid picked: mcs=15, ms=2 → 44 clusters (the only eligible config under floor=5)
  reduce_topics(15): 44 → 14 topics
  Final: 14 topics, 33.5% outliers
```

Sample of new topic themes (granular, thesis-meaningful):
- topic 9: survey/participation requests
- topic 10: chemistry class complaints (course-specific — was buried before)
- topic 12: dating discussions
- topic 13: looking-for-friends posts

The 33.5% outlier rate is higher than other universities (MM-PNSEC-1: 0.5%) but reflects the genuinely scattered nature of MM-PSEC-1's corpus — those 1,250 outlier posts don't fit any dense theme even at ms=2.

**Decisions:**
- `target_topic_count: 15` chosen as a thesis-meaningful target. Universities can naturally have fewer (MM-PNSEC-1 has 6); the threshold of 25 means reduce_topics only fires for over-fragmented corpora.
- `min_samples=2` is a known HDBSCAN edge case (smallest meaningful value). Adding it to the grid trades risk of micro-fragmentation for granularity recovery on bimodal corpora.
- `reduce_topics` is BERTopic's standard topic-merging utility (cosine-similarity over c-TF-IDF vectors). Methodology-defensible — it's documented in the BERTopic paper as the canonical way to control topic count.

**Recovery for the running batch:**
```powershell
# Stop the run (Ctrl+C), then:
Remove-Item -Recurse -Force outputs\MM-PSEC-1, outputs\MM-PUB-1, api_cache\labeling_responses\MM-PSEC-1, api_cache\labeling_responses\MM-PUB-1
Remove-Item checkpoints\<rid>\MM-PSEC-1_state.json, checkpoints\<rid>\MM-PUB-1_state.json
python -m topic_modeling   # option 3
```

Universities that already produced reasonable counts (MM-PNSEC-1 at 6) do not need re-running.

## ACTION-053 — 2026-05-06 — Pre-flight environment check

_Logged at 02:32:25 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "lexx2"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json"
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
    "FW-01_cleaned.json",
    "FW-02_cleaned.json"
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
## ACTION-054 — 2026-05-06 — HDBSCAN grid search — MM-PSEC-1

_Logged at 02:33:54 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      2,
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 15,
    "min_samples": 2,
    "outlier_rate": 0.3349,
    "silhouette": 0.4141,
    "npmi": -0.0218,
    "score": 0.2463,
    "n_clusters": 44
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 2,
      "outlier_rate": 0.3293,
      "silhouette": 0.4044,
      "npmi": -0.1064,
      "score": 0.2022,
      "n_clusters": 87
    },
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 2,
      "outlier_rate": 0.3349,
      "silhouette": 0.4141,
      "npmi": -0.0218,
      "score": 0.2463,
      "n_clusters": 44
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    }
  ]
}
```

---
## ACTION-055 — 2026-05-06 — Reduced topics in MM-PSEC-1 from 44 → 14

_Logged at 02:34:13 PHT — type: `REDUCE_TOPICS`_

- **Configuration:** 
```json
{
  "target_topic_count": 15,
  "reduce_threshold": 25
}
```
- **Output:** 
```json
{
  "n_topics_before": 44,
  "n_topics_after": 14
}
```

---
## ACTION-056 — 2026-05-06 — Completed MM-PSEC-1

_Logged at 02:34:52 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 14 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 15,
    "min_samples": 2
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "file": "FW-01_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 14,
  "outlier_rate": 0.3349397590361446,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-057 — 2026-05-06 — HDBSCAN grid search — MM-PUB-1

_Logged at 02:35:43 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      2,
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 15,
    "min_samples": 2,
    "outlier_rate": 0.0,
    "silhouette": 0.3865,
    "npmi": 0.1546,
    "score": 0.3932,
    "n_clusters": 3,
    "_floor_fallback": true
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.2702,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0003,
      "silhouette": 0.2702,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0017,
      "silhouette": 0.2713,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0025,
      "silhouette": 0.2704,
      "npmi": 0.0691,
      "score": 0.3152,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 15,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3,
      "_floor_fallback": true
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    }
  ]
}
```

---
## ACTION-058 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PUB-1

_Logged at 02:36:02 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1828,
  "n_subclusters": 2,
  "n_outliers_in_sub": 1000,
  "new_topic_ids": [
    3
  ],
  "skipped": false
}
```

---
## ACTION-059 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PUB-1

_Logged at 02:36:04 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1660,
  "n_subclusters": 2,
  "n_outliers_in_sub": 1603,
  "new_topic_ids": [
    4
  ],
  "skipped": false
}
```

---
## ACTION-060 — 2026-05-06 — OUTLIER_HIGH — MM-PUB-1 (72.75%)

_Logged at 02:36:05 PHT — type: `OUTLIER_HIGH`_

- **Action:** Outlier rate exceeds threshold; flagged for human review.
- **Configuration:** 
```json
{
  "hdbscan_params": {
    "min_cluster_size": 15,
    "min_samples": 2,
    "outlier_rate": 0.0,
    "silhouette": 0.3865,
    "npmi": 0.1546,
    "score": 0.3932,
    "n_clusters": 3,
    "_floor_fallback": true
  },
  "soft_threshold": 0.5
}
```
- **Output:** 
```json
{
  "final_outlier_rate": 0.7275013974287311,
  "soft_stats": {
    "reassigned": 0,
    "outlier_count": 0
  }
}
```
- **Decisions:** Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.
- **Next Steps:** Manual review of outlier_report.json.

---
## ACTION-061 — 2026-05-06 — Completed MM-PUB-1

_Logged at 02:36:33 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 5 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 15,
    "min_samples": 2
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "file": "FW-02_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 5,
  "outlier_rate": 0.7275013974287311,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-062 — 2026-05-06 — Run complete for lexx2

_Logged at 02:36:33 PHT — type: `RUN_COMPLETE`_

- **Output:** 
```json
{
  "n_universities_processed": 2,
  "wall_seconds": 249.3,
  "needs_review_count": 2
}
```

---

## ACTION-053 — 2026-05-06 — Granular mode (target 30, threshold 60) + cross-university summary generator

**Trigger:** User asked why the SLU pilot study (10k+ posts, June 2024 → April 2025, repo: lexxmodelo/Final-Project) produced 40+ topics including ones with ~10 posts, while the current pipeline yields 14 max via reduce_topics.

**Diagnosis (three compounding factors):**
1. **Corpus size effect:** Topic count scales roughly with log(corpus_size) for HDBSCAN. The pilot's 10k posts produced ~50% more natural clusters than current 3.7k-post corpora.
2. **Embedder choice:** Pilot used MiniLM (384-dim, semantically less compressive); current uses XLM-RoBERTa-Large (1024-dim, more compressive). XLM-R-L groups posts that MiniLM keeps as separate clusters. This is the bake-off trade-off documented in ACTION-006.
3. **reduce_topics aggression:** Pilot used vanilla BERTopic with no `reduce_topics` call. Our pipeline forced merging at threshold 25 → target 15, collapsing genuine granular signal (e.g. MM-PSEC-1's 44 raw topics → 14 final).

**Fix (granular mode):**

| File | Change |
|---|---|
| `configs/bertopic_config.json` | `target_topic_count: 15 → 30`, `reduce_topics_threshold: 25 → 60`. Reduce_topics now only fires on EXTREME over-fragmentation (e.g. ms=2 producing 90+ tiny clusters), preserving granular signal for typical corpora. Comment block in the file documents how to switch to merged mode for cleaner committee summaries. |
| `QUICKSTART.md` | Added "Topic granularity" section with three knob settings — granular (default), merged (15 topics), maximum-granular (no merge cap). |

**New: cross-university summary generator:**

| File | Change |
|---|---|
| `topic_modeling/summary.py` | NEW. `write_cross_university_summary()` walks every active mapping in `university_mapping.yaml`, gathers metrics from each university's `topic_metadata.json` + `topic_labels.json` + `topics_over_time.json`, plus corpus stats (n_posts, top languages, date range), and writes `validation/cross_university_summary.md` with: (a) a per-university comparison table, (b) aggregate min/median/max stats, (c) a "how to read topic-count variation" section explicitly framing differences as a thesis FINDING rather than a methodological flaw. |
| `topic_modeling/pipeline.py` | After all per-researcher outputs are written and the existing validation reports run, calls `summary.write_cross_university_summary(...)`. The summary regenerates on every run, so it always reflects the current state of `outputs/` (across universities completed by ANY researcher). |

**Sample summary table fields:**
- Code, Alias, Region (anonymized cluster code + plaintext alias for own-team reading)
- Posts, Top languages, Date range (corpus-level context)
- Topics, Outlier %, NPMI, Silhouette (clustering quality)
- Lazy labels %, Event-driven %, API fails (labeling quality)

**Key methodology note in the summary:** "For fair cross-university comparison prefer outlier_rate, NPMI, and event_driven %. Raw topic count alone should be interpreted alongside these metrics in the thesis discussion."

**Decisions:**
- Default to granular mode (target 30) so the pipeline matches the pilot's behavior out of the box. The pilot's success establishes a precedent that committee will recognize.
- The summary generator runs on every pipeline invocation (not gated to the final researcher) so partial progress is visible without waiting for all 4 researchers to finish.
- Topic-count differences are explicitly framed in the summary as a finding, not noise — preserves methodological transparency.

**No code regressions:** all 50 tests still pass.

**To re-process universities under the new defaults:**
```powershell
# Clear the affected universities' checkpoints (option 5 in the launcher), then re-run option 3.
# Universities already producing ≥5 topics (MM-PNSEC-1) need not be re-run unless the user wants
# the more granular pre-reduce result.
```

## ACTION-063 — 2026-05-06 — Pre-flight environment check

_Logged at 02:57:03 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "alexx"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
## ACTION-064 — 2026-05-06 — HDBSCAN grid search — MM-PSEC-1

_Logged at 02:58:37 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      2,
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 15,
    "min_samples": 2,
    "outlier_rate": 0.3349,
    "silhouette": 0.4141,
    "npmi": -0.0223,
    "score": 0.2461,
    "n_clusters": 44
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 2,
      "outlier_rate": 0.3293,
      "silhouette": 0.4044,
      "npmi": -0.1062,
      "score": 0.2023,
      "n_clusters": 87
    },
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 2,
      "outlier_rate": 0.3349,
      "silhouette": 0.4141,
      "npmi": -0.0223,
      "score": 0.2461,
      "n_clusters": 44
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0,
      "silhouette": 0.5803,
      "npmi": 0.1918,
      "score": 0.47,
      "n_clusters": 2
    }
  ]
}
```

---
## ACTION-065 — 2026-05-06 — Completed MM-PSEC-1

_Logged at 03:04:33 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 44 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 15,
    "min_samples": 2
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3735,
  "file": "FW-01_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 44,
  "outlier_rate": 0.3349397590361446,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-066 — 2026-05-06 — HDBSCAN grid search — MM-PUB-1

_Logged at 03:05:24 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      2,
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 15,
    "min_samples": 2,
    "outlier_rate": 0.0,
    "silhouette": 0.3865,
    "npmi": 0.1546,
    "score": 0.3932,
    "n_clusters": 3,
    "_floor_fallback": true
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.2702,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0003,
      "silhouette": 0.2702,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0017,
      "silhouette": 0.2713,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0025,
      "silhouette": 0.2704,
      "npmi": 0.0524,
      "score": 0.3068,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 15,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3,
      "_floor_fallback": true
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    }
  ]
}
```

---
## ACTION-067 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PUB-1

_Logged at 03:05:45 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1828,
  "n_subclusters": 2,
  "n_outliers_in_sub": 1000,
  "new_topic_ids": [
    3
  ],
  "skipped": false
}
```

---
## ACTION-068 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PUB-1

_Logged at 03:05:47 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1660,
  "n_subclusters": 2,
  "n_outliers_in_sub": 1603,
  "new_topic_ids": [
    4
  ],
  "skipped": false
}
```

---
## ACTION-069 — 2026-05-06 — OUTLIER_HIGH — MM-PUB-1 (72.75%)

_Logged at 03:05:47 PHT — type: `OUTLIER_HIGH`_

- **Action:** Outlier rate exceeds threshold; flagged for human review.
- **Configuration:** 
```json
{
  "hdbscan_params": {
    "min_cluster_size": 15,
    "min_samples": 2,
    "outlier_rate": 0.0,
    "silhouette": 0.3865,
    "npmi": 0.1546,
    "score": 0.3932,
    "n_clusters": 3,
    "_floor_fallback": true
  },
  "soft_threshold": 0.5
}
```
- **Output:** 
```json
{
  "final_outlier_rate": 0.7275013974287311,
  "soft_stats": {
    "reassigned": 0,
    "outlier_count": 0
  }
}
```
- **Decisions:** Persisting result; recommend rerun with hdbscan_grid.outlier_recovery.
- **Next Steps:** Manual review of outlier_report.json.

---
## ACTION-070 — 2026-05-06 — Completed MM-PUB-1

_Logged at 03:06:01 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 5 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 15,
    "min_samples": 2
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "file": "FW-02_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 5,
  "outlier_rate": 0.7275013974287311,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-071 — 2026-05-06 — HDBSCAN grid search — MM-PNSEC-1

_Logged at 03:07:05 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      2,
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3963,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 10,
    "min_samples": 10,
    "outlier_rate": 0.0053,
    "silhouette": 0.2026,
    "npmi": -0.0024,
    "score": 0.2585,
    "n_clusters": 6
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 2,
      "outlier_rate": 0.0038,
      "silhouette": 0.1964,
      "npmi": -0.0153,
      "score": 0.2505,
      "n_clusters": 8
    },
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 2,
      "outlier_rate": 0.0013,
      "silhouette": 0.2011,
      "npmi": -0.0183,
      "score": 0.2509,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 2,
      "outlier_rate": 0.0013,
      "silhouette": 0.2011,
      "npmi": -0.0183,
      "score": 0.2509,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 2,
      "outlier_rate": 0.0013,
      "silhouette": 0.2011,
      "npmi": -0.0183,
      "score": 0.2509,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    }
  ]
}
```

---
## ACTION-072 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PNSEC-1

_Logged at 03:07:29 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1871,
  "n_subclusters": 2,
  "n_outliers_in_sub": 1725,
  "new_topic_ids": [
    6
  ],
  "skipped": false
}
```

---
## ACTION-073 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PNSEC-1

_Logged at 03:07:32 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1856,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1856,
  "new_topic_ids": [],
  "skipped": true,
  "skipped_reason": "no real sub-clusters found; parent cluster preserved"
}
```

---
## ACTION-074 — 2026-05-06 — Completed MM-PNSEC-1

_Logged at 03:08:03 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 7 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 10,
    "min_samples": 10
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3963,
  "file": "FW-03_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 7,
  "outlier_rate": 0.4405753217259652,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-075 — 2026-05-06 — Run complete for alexx

_Logged at 03:08:03 PHT — type: `RUN_COMPLETE`_

- **Output:** 
```json
{
  "n_universities_processed": 3,
  "wall_seconds": 662.3,
  "needs_review_count": 3
}
```

---

## ACTION-054 — 2026-05-06 — First granular-mode batch run (alexx, 3 NCR universities) — results + issues identified

**What was done:** Cleared all stale state for `MM-PSEC-1`, `MM-PUB-1`, `MM-PNSEC-1` (outputs, api_cache, alexx checkpoints) and ran `python -m topic_modeling.run --researcher alexx --skip-bakeoff` end-to-end with granular mode (`target_topic_count: 30`, `reduce_topics_threshold: 60`).

**Results table (also in `validation/cross_university_summary.md`):**

| Code | Alias | Posts | Top languages | Topics | Outliers | NPMI | Silhouette | API fails |
|---|---|---|---|---|---|---|---|---|
| MM-PSEC-1 | ADMU | 3,735 | English 76% | **44** | 33.5% | -0.022 | 0.414 | **9** |
| MM-PNSEC-1 | FEU | 3,963 | Taglish 38% Filipino 32% | 7 | 44.1% | -0.002 | 0.203 | 0 |
| MM-PUB-1 | UPD | 3,578 | Filipino 36% Taglish 29% | 5 | 72.8% | 0.155 | 0.387 | 0 |

**Sample MM-PSEC-1 labels (granular signal preserved as intended):**
- Student Complaints About AEGIS (SLU-specific publication ref)
- Neurodivergent Student Concerns
- Professor Review Skepticism
- Ateneo Student Stereotypes
- Performative Male Stereotypes
- ACET Exam Anxiety Tips (admission-test-specific)
- Concierto Event Support Requests
- IARFA Student Council Elections (event-driven, FEU)
- Tech University Tuition Concerns (event-driven, FEU)

This matches the granularity of the SLU pilot study, including small (10–30 post) topics with course-specific signal.

**Issues identified:**

1. **NIM rate-limit failures on MM-PSEC-1 (9/44 topics unlabeled).** The token-bucket rate limiter at 40 RPM cannot keep up with NVIDIA NIM's enforced sliding-window limits during sustained calls on granular runs. Topics 22, 24, 27, 28, 35, 38, 39, 40, 43 all gave up after 5 retries each (16s exponential backoff exhausted). The remaining 35 topics labeled cleanly. The 9 failed topics still have valid `topic_assignments.json` and `topic_keywords.json` — they just lack labels.

2. **MM-PNSEC-1 outlier rate regression (0.5% → 44.1%).** Earlier runs of MM-PNSEC-1 (when `n_components` was briefly bumped to 30 in ACTION-027) produced 6 topics with 0.5% outliers. The current run with `n_components: 5` (reverted in ACTION-028) produces 7 topics with 44.1% outliers. FEU's well-balanced trilingual corpus benefits from higher dimensionality; the SLU-1000 test that informed ACTION-028 was insufficient evidence to revert globally.

3. **MM-PUB-1 floor fallback (3 → 5 topics).** UPD has genuinely flat density structure: max 4 clusters at any HDBSCAN config. Floor=5 fallback fired correctly. Sub-clustering split one cluster into 3, ending at 5 final topics with 72.8% outliers. This is a corpus characteristic, not a tunable.

**Cross-university summary auto-generated** at `validation/cross_university_summary.md` (per ACTION-053 spec), including the "how to read topic-count variation" framing.

**Action items handed to ACTION-055 (next entry):**
- Lower `effective_rpm: 40 → 25` to give NIM headroom on granular runs.
- Add a label-retry utility so the 9 unlabeled topics can be filled in without re-clustering / re-encoding.
- Test `n_components: 5 vs 15` on cached MM-PNSEC-1 embeddings; apply if it recovers the previous 0.5% outlier rate.

## ACTION-076 — 2026-05-06 — Retry labels for alexx (1 universities)

_Logged at 03:13:11 PHT — type: `LABEL_RETRY`_

- **Action:** Re-ran NIM labeling for any topic with label='Unlabeled' or API_GIVEUP/MALFORMED_OUTPUT flags.
- **Configuration:** 
```json
{
  "effective_rpm": 25
}
```
- **Output:** 
```json
[
  {
    "univ_code": "MM-PSEC-1",
    "n_retried": 9,
    "n_recovered": 9,
    "n_still_failed": 0
  }
]
```

---
## ACTION-077 — 2026-05-06 — Pre-flight environment check

_Logged at 03:18:33 PHT — type: `PREFLIGHT`_

- **Configuration:** 
```json
{
  "researcher_id": "alexx"
}
```
- **Input:** 
```json
{
  "input_dir": "C:\\Users\\Alex Evan\\Documents\\Research\\preprocessing\\output",
  "assigned_files": [
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
    "FW-01_cleaned.json",
    "FW-02_cleaned.json",
    "FW-03_cleaned.json"
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
## ACTION-078 — 2026-05-06 — Resume — MM-PSEC-1 already complete

_Logged at 03:18:48 PHT — type: `RESUME`_

- **Action:** Found checkpoint at C:\Users\Alex Evan\Documents\Research\topic_modeling\checkpoints\alexx\MM-PSEC-1_state.json.
- **Input:** 
```json
{
  "university_code": "MM-PSEC-1",
  "researcher": "alexx"
}
```

---
## ACTION-079 — 2026-05-06 — HDBSCAN grid search — MM-PUB-1

_Logged at 03:19:52 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      2,
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 15,
    "min_samples": 2,
    "outlier_rate": 0.0,
    "silhouette": 0.3865,
    "npmi": 0.1546,
    "score": 0.3932,
    "n_clusters": 3,
    "_floor_fallback": true
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.2702,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0003,
      "silhouette": 0.2702,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0017,
      "silhouette": 0.2713,
      "npmi": 0.0229,
      "score": 0.2925,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0025,
      "silhouette": 0.2704,
      "npmi": 0.0623,
      "score": 0.3118,
      "n_clusters": 4
    },
    {
      "min_cluster_size": 15,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3,
      "_floor_fallback": true
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 2,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0,
      "silhouette": 0.3865,
      "npmi": 0.1546,
      "score": 0.3932,
      "n_clusters": 3
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0006,
      "silhouette": 0.3861,
      "npmi": 0.1543,
      "score": 0.3929,
      "n_clusters": 3
    }
  ]
}
```

---
## ACTION-080 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PUB-1

_Logged at 03:20:13 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1828,
  "n_subclusters": 2,
  "n_outliers_in_sub_kept_in_parent": 1000,
  "new_topic_ids": [
    3
  ],
  "skipped": false
}
```

---
## ACTION-081 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PUB-1

_Logged at 03:20:16 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1660,
  "n_subclusters": 2,
  "n_outliers_in_sub_kept_in_parent": 1603,
  "new_topic_ids": [
    4
  ],
  "skipped": false
}
```

---
## ACTION-082 — 2026-05-06 — Completed MM-PUB-1

_Logged at 03:20:22 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 5 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 15,
    "min_samples": 2
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3578,
  "file": "FW-02_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 5,
  "outlier_rate": 0.0,
  "lazy_pct": 0.0,
  "needs_review": false
}
```

---
## ACTION-083 — 2026-05-06 — HDBSCAN grid search — MM-PNSEC-1

_Logged at 03:21:27 PHT — type: `GRID_SEARCH`_

- **Configuration:** 
```json
{
  "grid_key": "medium_corpus_1500_to_5000",
  "grid": {
    "min_cluster_size": [
      10,
      15,
      20,
      30
    ],
    "min_samples": [
      2,
      3,
      5,
      10
    ]
  }
}
```
- **Input:** 
```json
{
  "n_posts": 3963,
  "embedding_dim": 1024
}
```
- **Output:** 
```json
{
  "best": {
    "min_cluster_size": 10,
    "min_samples": 10,
    "outlier_rate": 0.0053,
    "silhouette": 0.2026,
    "npmi": -0.0024,
    "score": 0.2585,
    "n_clusters": 6
  },
  "all_results": [
    {
      "min_cluster_size": 10,
      "min_samples": 2,
      "outlier_rate": 0.0038,
      "silhouette": 0.1964,
      "npmi": -0.0133,
      "score": 0.2515,
      "n_clusters": 8
    },
    {
      "min_cluster_size": 10,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 10,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 10,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 2,
      "outlier_rate": 0.0013,
      "silhouette": 0.2011,
      "npmi": -0.0183,
      "score": 0.2509,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 15,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 2,
      "outlier_rate": 0.0013,
      "silhouette": 0.2011,
      "npmi": -0.0183,
      "score": 0.2509,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 20,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 2,
      "outlier_rate": 0.0013,
      "silhouette": 0.2011,
      "npmi": -0.0183,
      "score": 0.2509,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 3,
      "outlier_rate": 0.0015,
      "silhouette": 0.201,
      "npmi": -0.0107,
      "score": 0.2546,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 5,
      "outlier_rate": 0.0013,
      "silhouette": 0.2004,
      "npmi": -0.0084,
      "score": 0.2557,
      "n_clusters": 6
    },
    {
      "min_cluster_size": 30,
      "min_samples": 10,
      "outlier_rate": 0.0053,
      "silhouette": 0.2026,
      "npmi": -0.0024,
      "score": 0.2585,
      "n_clusters": 6
    }
  ]
}
```

---
## ACTION-084 — 2026-05-06 — Sub-clustered dump cluster 0 in MM-PNSEC-1

_Logged at 03:21:51 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 0,
  "n_members": 1871,
  "n_subclusters": 2,
  "n_outliers_in_sub_kept_in_parent": 1725,
  "new_topic_ids": [
    6
  ],
  "skipped": false
}
```

---
## ACTION-085 — 2026-05-06 — Sub-clustered dump cluster 1 in MM-PNSEC-1

_Logged at 03:21:54 PHT — type: `SUBCLUSTER`_

- **Configuration:** 
```json
{
  "recovery_params": {
    "min_cluster_size": [
      10,
      15,
      20
    ],
    "min_samples": [
      2,
      3,
      5
    ]
  }
}
```
- **Output:** 
```json
{
  "dump_cluster_id": 1,
  "n_members": 1856,
  "n_subclusters": 0,
  "n_outliers_in_sub": 1856,
  "new_topic_ids": [],
  "skipped": true,
  "skipped_reason": "no real sub-clusters found; parent cluster preserved"
}
```

---
## ACTION-086 — 2026-05-06 — Completed MM-PNSEC-1

_Logged at 03:22:42 PHT — type: `UNIV_COMPLETE`_

- **Action:** Trained BERTopic, labeled 7 topics, ran DTM.
- **Configuration:** 
```json
{
  "hdbscan": {
    "min_cluster_size": 10,
    "min_samples": 10
  },
  "embedding_model": "FacebookAI/xlm-roberta-large"
}
```
- **Input:** 
```json
{
  "n_posts": 3963,
  "file": "FW-03_cleaned.json"
}
```
- **Output:** 
```json
{
  "n_topics": 7,
  "outlier_rate": 0.005299015897047691,
  "lazy_pct": 0.0,
  "needs_review": true
}
```

---
## ACTION-087 — 2026-05-06 — Run complete for alexx

_Logged at 03:22:42 PHT — type: `RUN_COMPLETE`_

- **Output:** 
```json
{
  "n_universities_processed": 2,
  "wall_seconds": 251.7,
  "needs_review_count": 1
}
```

---

## ACTION-055 — 2026-05-06 — Three fixes for the granular-mode batch issues from ACTION-054

**Trigger:** ACTION-054 identified three issues. This action addresses all three.

### Fix 1: Lower default `effective_rpm` from 40 → 25

**Files:** `configs/researcher_template.json`, `configs/alexx.json`.

**Why:** NIM's free-tier RPM enforcement is sliding-window, not strict per-minute. At sustained 40 RPM the bucket exhausts and 429 storms hit. 25 RPM gives ~37% headroom — verified to work on the retry pass.

**Trade-off:** ~60% slower labeling (40 → 25 calls/min). For granular runs (44+ topics on MM-PSEC-1) the labeling-only stage goes from ~70 sec to ~110 sec — negligible vs the ~50 sec encoding stage.

### Fix 2: Add `topic_modeling.retry_labels` utility

**File:** `topic_modeling/retry_labels.py` (new module).

**What:** A standalone CLI that reads existing `topic_keywords.json` + `topic_rep_docs.json` + `topic_labels.json` for a researcher's universities, finds topics where `label == "Unlabeled"` or flags include `API_GIVEUP` / `MALFORMED_OUTPUT`, and re-runs ONLY those through NIM with the (now-lowered) effective_rpm.

**Usage:**
```
python -m topic_modeling.retry_labels --researcher alexx
python -m topic_modeling.retry_labels --researcher alexx --univ MM-PSEC-1
```

Preserves existing temporal_signature + EVENT_DRIVEN flags from the original run. Atomically rewrites topic_labels.json in-place (no clustering/encoding work).

**Verification:** ran `--univ MM-PSEC-1` against the 9 unlabeled topics from ACTION-054. **9/9 recovered** with effective_rpm=25:
- topic 22: 'Struggling with Personal Relationships'
- topic 24: 'University Student Social Dynamics'
- topic 27: 'Parking Issues on Campus' (specific!)
- topic 28: 'Special Interest Group Inquiries'
- topic 35: 'University Student Grievances'
- topic 38: 'Expatriate Marriage Concerns' (specific!)
- topic 39: 'University Enrollment Process Issues'
- topic 40: 'Lost College Social Connections'
- topic 43: 'Student University Complaints'

A `LABEL_RETRY` action was auto-logged into action_log.md (ACTION number set by log_action helper).

### Fix 3: Sub-cluster pass `-1` should map to PARENT, not global `-1`

**File:** `topic_modeling/subcluster.py::merge_subclusters_back`.

**Root cause investigation:** Tested n_components 5/15/30 on MM-PNSEC-1 cached embeddings via `test_ncomp_mmpnsec.py`. All three n_components values produced ~6 clusters with ~0% outliers in the GRID stage. So the 44.1% outlier rate seen in ACTION-054 was NOT from UMAP dimensionality — it was the SUB-CLUSTER pass.

**Bug:** When sub-clustering a dump cluster, HDBSCAN sometimes produces a mix of `-1` (sub-noise) + real sub-cluster IDs. The previous logic mapped sub-pass `-1` to **global -1**, removing those documents from their valid parent cluster and inflating the outlier rate. For MM-PNSEC-1 with mcs=10/ms=10 this turned a clean 0.5%-outlier result into 44.1% outliers.

**Fix:** Sub-pass `-1` now maps to the **parent cluster id** (`dump_cluster_id`). Rationale: those documents already belonged to a valid coarse-grained cluster; HDBSCAN's failure to find FINER structure for them shouldn't downgrade them to outliers. They still belong to the parent's theme.

**Test updated:** `test_split_with_some_outliers` in `tests/test_subcluster_safety.py` now expects sub-noise → parent (was: sub-noise → global -1). All 50 tests still pass.

**Verification (re-ran MM-PUB-1 + MM-PNSEC-1 with the fix; MM-PSEC-1 preserved via checkpoint):**

| University | Before fix (ACTION-054) | After fix (this action) |
|---|---|---|
| MM-PUB-1 | 5 topics, **72.8% outliers** | 5 topics, **0.0% outliers** |
| MM-PNSEC-1 | 7 topics, **44.1% outliers** | 7 topics, **0.5% outliers** |

Same topic counts and labels (event-driven detection on FEU still surfaces Tech Tuition Concerns + IARFA Student Council Elections). The fix does not change which topics are found — only correctly preserves cluster membership for documents that the sub-pass couldn't fine-grain.

### Updated cross-university summary

`validation/cross_university_summary.md` regenerated automatically. Aggregate stats:
- **Topics per university**: min 5, median 7, max 44
- **Outlier rate**: min 0.0%, median 0.5%, max 33.5%
- **NPMI**: min -0.022, median -0.002, max 0.155

The 33.5% outlier on MM-PSEC-1 is a CORPUS characteristic (English-dominated bimodal density), not a bug — confirmed by the ms=2 grid sweep in ACTION-052.

### What's left

7 universities remain (CAR cluster + MIN-PUB-1 + PROV-PUB-1 + SLU itself). All should run cleanly with these three fixes in place. The lead researcher (alexx) can either:
1. Add them to assigned_files in alexx.json and re-run, OR
2. Distribute them among the other 4 researchers per the methodology §8.2 plan.

