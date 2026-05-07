# VAD Sentiment Scoring Pipeline — Implementation Plan

## Context

The topic modeling phase ([topic_modeling/](topic_modeling/)) is complete: BERTopic clustering + NIM-Llama 3.3 70B labeling produced topic assignments and labels for all 10 universities (37,074 total posts, verified). The next phase is **dimensional sentiment scoring** along Valence/Arousal/Dominance (SAM 1–9 scale) with integrated sarcasm detection, per [methodology_changes.md §3.4](methodology_changes.md). Scores are joined with topic labels for downstream temporal/cross-institution analysis and dashboard publication.

The VAD phase must:
- Reuse existing infrastructure (NIM client, rate limiter, checkpointing, .env, menu pattern, action_log format) from `topic_modeling/` to avoid divergent codebases.
- Run distributed across 1–5 researchers (each with their own NVIDIA NIM key) per [methodology_changes.md §8](methodology_changes.md).
- Self-heal across the 12+ failure modes catalogued in the user request.
- Maintain a strict audit trail (`vad_scoring/action_log.md`) so the thesis methodology section is reproducible.

**Confirmed dataset (counted live):** 37,074 posts across 10 files; Topic −1 outliers total ~4,921 (13.3%, concentrated in MM-PSEC-1 33%, CAR-PNSEC-2 44%, MIN-PUB-1 42%; rest <4%).

**Confirmed user decisions:**
1. Score outliers with topic context = `"Unclassified"` (preserves dataset completeness).
2. Effective rate limit per researcher = **20 RPM** (matches `topic_modeling/configs/researcher_template.json::effective_rpm`).
3. Out-of-range V/A/D → clamp to nearest [1, 9], log warning, **no retry**.

---

## 1. Verified Workload (37,074 posts, batch=5, 20 effective RPM)

Per-university batch counts (ceil(posts/5)):

| FW Alias | Anon Code | Posts | Batches |
|---|---|---:|---:|
| FW-01 (ADMU)  | MM-PSEC-1   | 3,735 | 747 |
| FW-02 (UPD)   | MM-PUB-1    | 3,578 | 716 |
| FW-03 (FEU)   | MM-PNSEC-1  | 3,963 | 793 |
| FW-04 (UPLB)  | PROV-PUB-1  | 3,955 | 791 |
| FW-05 (LPU-B) | CAR-PNSEC-2 | 3,912 | 783 |
| FW-06 (CSU)   | MIN-PUB-1   | 3,998 | 800 |
| FW-07 (UPB)   | CAR-PUB-1   | 2,287 | 458 |
| FW-08 (BSU)   | CAR-PUB-2   | 3,791 | 759 |
| FW-09 (UB)    | CAR-PNSEC-1 | 3,991 | 799 |
| SLU           | CAR-PSEC-1  | 3,864 | 773 |
| **Total**     |             | **37,074** | **7,419** |

Adaptive distribution table (researcher count chosen at runtime in menu option 1):

| Researchers | Universities each | Avg batches each | Time @ 20 RPM |
|---:|---|---:|---:|
| 1 | 10                | 7,419 | ~6.2 hr |
| 2 | 5+5               | ~3,710 | ~3.1 hr |
| 3 | 4+3+3             | ~2,473 | ~2.1 hr |
| 4 | 3+3+2+2           | ~1,855 | ~1.5 hr |
| 5 | 2+2+2+2+2         | ~1,484 | ~1.2 hr |

Distribution algorithm: greedy bin-pack by **batch count** (not university count), so the researcher with FW-07 (small) doesn't finish 30 minutes before peers. Codified in `vad_scoring/topic_modeling/distribute.py::balance_assignments()`.

---

## 2. Folder Structure (created at scaffolding step)

```
vad_scoring/
├── action_log.md                      # Append-only audit trail
├── README.md                          # Quickstart for new researcher
├── .env.example                       # NVIDIA_NIM_API_KEY template
├── vad_scoring/                       # Python package
│   ├── __init__.py
│   ├── __main__.py                    # Interactive menu (9 options)
│   ├── dotenv.py                      # COPY from topic_modeling/dotenv.py
│   ├── io_utils.py                    # COPY from topic_modeling/io_utils.py
│   ├── logging_setup.py               # COPY from topic_modeling/logging_setup.py
│   ├── nim_client.py                  # ADAPT from topic_modeling/labeling.py:
│   │                                  #   TokenBucket, retry/backoff, circuit breaker
│   ├── prompt.py                      # SYSTEM/USER builder + few-shot injection
│   ├── batcher.py                     # Stream-and-chunk-by-5 with topic enrichment
│   ├── parser.py                      # JSON-array extraction + json_repair fallback
│   ├── validator.py                   # Schema + range + PII + consistency checks
│   ├── checkpoint.py                  # Per-(researcher, university) state files
│   ├── distribute.py                  # Adaptive 1–5 researcher bin-pack
│   ├── pipeline.py                    # Top-level orchestrator (per university)
│   ├── merge.py                       # Cross-researcher consolidation
│   └── pii_check.py                   # Pre-API regex sweep
├── configs/
│   ├── vad_config.json                # Global locked settings
│   ├── researcher_template.json       # Per-researcher template
│   └── few_shot_examples.json         # 3 anchors (editable via menu option 8)
├── checkpoints/
│   └── researcher_<id>/<CODE>_state.json
├── results/
│   └── researcher_<id>/<CODE>_vad_scores.jsonl
├── api_cache/
│   └── raw_responses_<researcher_id>.jsonl   # Every API request+response, audit-grade
├── validation/
│   ├── schema_validation_report.json
│   ├── range_anomalies.json
│   ├── sarcasm_flags.json
│   └── pii_violations.jsonl
├── merged_outputs/
│   ├── all_vad_scores.json
│   └── vad_statistics_per_topic.json
└── tests/
    ├── test_parser.py                 # JSON repair + ID-mismatch handling
    ├── test_validator.py              # Range/clamp/schema rules
    └── test_distribute.py             # Bin-pack correctness for 1–5 researchers
```

---

## 3. Critical Files to Modify / Create

| Path | Action | Source pattern |
|---|---|---|
| [vad_scoring/vad_scoring/__main__.py](vad_scoring/vad_scoring/__main__.py) | NEW | Mirror [topic_modeling/topic_modeling/__main__.py](topic_modeling/topic_modeling/__main__.py) — reuse `_menu`, `_input`, `_yesno`, `_multiselect`, `pick_researcher`, `ensure_dotenv` verbatim |
| [vad_scoring/vad_scoring/nim_client.py](vad_scoring/vad_scoring/nim_client.py) | NEW | Adapt the `TokenBucket` + `_post_with_retry` block in `topic_modeling/topic_modeling/labeling.py` (same endpoint, same env var `NVIDIA_NIM_API_KEY`, same exponential backoff 1→2→4→8→16s, same circuit breaker after 10 consecutive failures) |
| [vad_scoring/configs/researcher_template.json](vad_scoring/configs/researcher_template.json) | NEW | Extend [topic_modeling/configs/researcher_template.json](topic_modeling/configs/researcher_template.json) with VAD-specific fields (see §5) |
| [vad_scoring/configs/vad_config.json](vad_scoring/configs/vad_config.json) | NEW | Locked global settings (model_id, temperature, batch_size, prompt_sha256, schema version) |
| [vad_scoring/configs/few_shot_examples.json](vad_scoring/configs/few_shot_examples.json) | NEW | 3 anchors drafted in §7 |
| [vad_scoring/action_log.md](vad_scoring/action_log.md) | NEW | Same `## ACTION-NNN — YYYY-MM-DD — Title` format as [topic_modeling/action_log.md](topic_modeling/action_log.md) |
| [vad_scoring/.env.example](vad_scoring/.env.example) | NEW | `NVIDIA_NIM_API_KEY=nvapi-...` template |
| Repo `.gitignore` | EDIT | Append `vad_scoring/.env`, `vad_scoring/api_cache/`, `vad_scoring/checkpoints/` |

**Reused from topic_modeling (copy verbatim, do not import to keep packages independent — same convention as [topic_modeling/action_log.md ACTION-001](topic_modeling/action_log.md)):**
- `dotenv.py`, `io_utils.py`, `logging_setup.py`
- `TokenBucket` class and `_post_with_retry` from `labeling.py`
- Menu UI helpers from `__main__.py`

**Inputs consumed (read-only):**
- `topic_modeling/outputs/{CODE}/topic_assignments.json` — `[{post_id, topic_id, probability?}]`
- `topic_modeling/outputs/{CODE}/topic_labels.json` — `[{topic_id, label, ...}]`
- `preprocessing/output/{FW-NN}_cleaned.json` — `[{post_id, text, ...}]`
- `topic_modeling/configs/university_mapping.yaml` — file ↔ anon code mapping (single source of truth)

---

## 4. Pipeline Flow (per university, per researcher)

```
load_inputs(univ_code) →                  # join 3 sources by post_id
    [{post_id, text, topic_label}]        # topic_id=-1 → topic_label="Unclassified"
        │
        ▼
pii_check.sweep(posts) →                  # regex for unmasked names/emails/numbers
    rejects to validation/pii_violations.jsonl, never sent to API
        │
        ▼
batcher.chunk(5) →                        # stream-and-yield 5-post groups
        │
        ▼
checkpoint.skip_if_done(batch_idx) →      # resume from last_completed_batch + 1
        │
        ▼
prompt.build(batch, few_shot) →           # SYSTEM + 3 anchors + 5 posts
        │
        ▼
nim_client.post(prompt) →                 # 20 RPM token bucket; retry/backoff
    raw response → api_cache/raw_responses_<rid>.jsonl
        │
        ▼
parser.extract(response) →                # json.loads; on fail, regex-extract array;
                                          # on fail, json_repair; on fail, retry 3x
        │
        ▼
validator.check(parsed, batch) →          # see §6 error matrix
    out-of-range  → clamp + log to range_anomalies.json
    sarcasm+highV → flag to sarcasm_flags.json (accept output)
    length mismatch → identify missing IDs, queue singles for next batch
    duplicate IDs → re-queue full batch
        │
        ▼
results/<rid>/<CODE>_vad_scores.jsonl ← append validated records
        │
        ▼
checkpoint.save(every 100 requests)
        │
        ▼
on university-complete: write per-university summary + log ACTION-NNN
```

---

## 5. Configuration Schema

**`configs/vad_config.json`** (locked, never edited per-researcher):

```json
{
  "schema_version": "vad-v1.0",
  "model_id": "meta/llama-3.3-70b-instruct",
  "model_endpoint": "https://integrate.api.nvidia.com/v1/chat/completions",
  "temperature": 0.1,
  "max_tokens": 600,
  "batch_size": 5,
  "scale_min": 1,
  "scale_max": 9,
  "outlier_topic_label": "Unclassified",
  "score_outliers": true,
  "prompt_sha256": "TBD_AT_FIRST_RUN_AND_FROZEN",
  "few_shot_path": "configs/few_shot_examples.json",
  "checkpoint_frequency_requests": 100,
  "max_post_chars": 1500,
  "max_post_truncation_suffix": " [truncated]"
}
```

**`configs/researcher_template.json`** (mirrors topic_modeling, with VAD additions):

```json
{
  "_comment": "Per-researcher config. Run `python -m vad_scoring` → option 1 to create your own.",
  "researcher_id": "researcher_1",
  "api_key_env_var": "NVIDIA_NIM_API_KEY",
  "assigned_universities": ["MM-PSEC-1", "CAR-PSEC-1"],
  "rate_limit_rpm": 40,
  "effective_rpm": 20,
  "request_timeout_seconds": 30,
  "max_retries": 5,
  "retry_backoff_min_seconds": 1,
  "retry_backoff_max_seconds": 16,
  "circuit_breaker_consecutive_failures": 10,
  "circuit_breaker_pause_minutes": 5,
  "checkpoint_dir": "checkpoints/researcher_1",
  "output_dir": "results/researcher_1",
  "api_cache_path": "api_cache/raw_responses_researcher_1.jsonl"
}
```

**Output JSONL record (one per post):**

```json
{"post_id":"abc123","univ_code":"CAR-PSEC-1","topic_id":3,"topic_label":"Academic Burnout","V":3,"A":7,"D":2,"sarcasm":false,"flags":["range_clamped"],"researcher_id":"researcher_2","model_version":"meta/llama-3.3-70b-instruct","scored_at":"2026-05-06T14:35:12+08:00"}
```

**Checkpoint file (`checkpoints/researcher_<id>/<CODE>_state.json`):**

```json
{
  "task": "vad_scoring",
  "researcher_id": "researcher_2",
  "univ_code": "CAR-PSEC-1",
  "total_batches": 773,
  "last_completed_batch": 154,
  "completed_post_ids_count": 770,
  "failed_post_ids": ["abc123","xyz789"],
  "successful_requests": 154,
  "failed_requests": 2,
  "out_of_range_clamps": 5,
  "sarcasm_flags": 18,
  "started_at": "2026-05-06T14:00:00+08:00",
  "last_updated": "2026-05-06T14:35:12+08:00"
}
```

---

## 6. Error Recovery Matrix (codified in `validator.py` + `nim_client.py`)

| Scenario | Detection | Recovery |
|---|---|---|
| V/A/D outside [1,9] | post-parse range check | **clamp** to nearest valid; flag `range_clamped`; log to `range_anomalies.json`; **no retry** |
| Non-JSON response body | `json.loads()` fails | extract `[...]` via regex; if still fails, `json_repair`; if still fails, retry batch (max 3); after 3, split to singles |
| Length mismatch (<5 or >5) | `len(parsed) != 5` | identify missing/extra `post_id`s; re-queue missing as singles; drop extras with log |
| Duplicate IDs in response | `len(set) != len(list)` | log API anomaly; retry full batch (max 3) |
| Sarcasm=true AND V≥7 | post-parse consistency rule | accept output; flag to `sarcasm_flags.json` for HITL review |
| Unmasked PII detected pre-call | regex for `\b[A-Z][a-z]+ [A-Z][a-z]+\b` not in `[REDACTED_NAME]`, raw emails, raw `09\d{9}` | reject post; log to `pii_violations.jsonl`; never send to API |
| HTTP 429 | response code | exponential backoff 1→2→4→8→16s (max 5 retries); honor `Retry-After` header if present; then circuit-break 5 min |
| Network timeout (>30s) | `requests.exceptions.Timeout` | retry same batch; after 3, split to singles |
| HTTP 401/403 | response code | **immediate halt**; print `"Check NVIDIA_NIM_API_KEY"`; do not consume budget |
| Corrupted checkpoint JSON | `json.JSONDecodeError` on resume | alert user; offer (a) restart university from batch 0, (b) skip university, (c) abort |
| Post >1,500 chars | pre-tokenize length | truncate to last 1,500 chars + ` [truncated]`; log truncation count |
| Already-scored post (resume) | post_id in checkpoint completed set | skip silently |

---

## 7. Few-Shot Anchors (drafted; editable via menu option 8)

`configs/few_shot_examples.json` — 3 anchors covering the diagnostic corners of the SAM cube, drafted from observed Filipino-student-discourse patterns. Each anchor includes a `rationale` field for thesis defensibility:

```json
{
  "version": "v1.0",
  "examples": [
    {
      "id": "anchor_burnout",
      "topic": "Academic Burnout",
      "text": "ang hirap na talaga, di ko na alam if kakayanin pa, sobrang pagod na ako sa lahat ng requirements, parang gusto ko na lang sumuko",
      "scores": {"V": 2, "A": 3, "D": 2, "sarcasm": false},
      "rationale": "Low valence (despair), low arousal (exhausted not agitated), low dominance (helpless surrender) — canonical burnout signature."
    },
    {
      "id": "anchor_rage",
      "topic": "Administrative Frustration",
      "text": "PUTANG INA NA REGISTRAR YAN!! 3 weeks na akong naghihintay ng simpleng signature, walang ginagawa kundi mag-walang ka pakialam!! ang hina!!",
      "scores": {"V": 2, "A": 9, "D": 3, "sarcasm": false},
      "rationale": "Low valence (negative), high arousal (explosive caps + repetition), low dominance (still blocked by gatekeeper) — high-A/low-D rage."
    },
    {
      "id": "anchor_sarcasm",
      "topic": "Faculty Praise",
      "text": "wow ang galing talaga ni prof, 8am class tapos 30 mins late siya everyday tapos absent pag may quiz 👏👏 sobrang professional",
      "scores": {"V": 2, "A": 5, "D": 4, "sarcasm": true},
      "rationale": "Surface positive (\"galing\", clapping emoji, \"professional\") masks negative critique. True valence is low; arousal moderate (annoyance, not rage); dominance modest (vented but powerless to change behavior). Tests sarcasm pre-check from §3.4."
    }
  ]
}
```

---

## 8. JSON Schema for VAD Output (hard validation)

`vad_scoring/configs/vad_output.schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["post_id", "univ_code", "topic_label", "V", "A", "D", "sarcasm",
               "researcher_id", "model_version", "scored_at"],
  "properties": {
    "post_id":       {"type": "string", "minLength": 1},
    "univ_code":     {"type": "string", "pattern": "^(MM|PROV|CAR|MIN)-(PUB|PSEC|PNSEC)-[12]$"},
    "topic_id":      {"type": "integer", "minimum": -1},
    "topic_label":   {"type": "string", "minLength": 1},
    "V":             {"type": "integer", "minimum": 1, "maximum": 9},
    "A":             {"type": "integer", "minimum": 1, "maximum": 9},
    "D":             {"type": "integer", "minimum": 1, "maximum": 9},
    "sarcasm":       {"type": "boolean"},
    "flags":         {"type": "array", "items": {"type": "string"}},
    "researcher_id": {"type": "string"},
    "model_version": {"type": "string"},
    "scored_at":     {"type": "string", "format": "date-time"}
  }
}
```

Validation pass is run by menu option 7 over all result JSONLs and writes `validation/schema_validation_report.json` summarizing failures by type.

---

## 9. Interactive Menu Specification

`python -m vad_scoring` launches the menu (mirrors topic_modeling's launcher). Layout:

```
============================================================
VAD Sentiment Scoring — Interactive Launcher
============================================================
  1. Set up a researcher config (asks: how many researchers? 1-5)
  2. Score a single test post (debug, no checkpoint)
  3. Score a single batch (5 posts, integration test)
  4. Run full pipeline for assigned universities
  5. Resume from last checkpoint
  6. Show progress / list checkpoints
  7. Validate outputs (schema + range + PII)
  8. View / edit few-shot examples
  9. Merge results across all researchers (run by lead only)
  0. Quit
```

Behavioral rules:
- Option 1 **must** be run before 4–5 (enforced by `pick_researcher` returning None if no config exists).
- Option 1 asks `"How many researchers total? (1-5)"`, then `"Which researcher are you? (1-N)"`, then runs `distribute.balance_assignments(N)` and prints the slice this researcher gets — saving the assignment to `configs/researcher_<id>.json`.
- Options 2 and 3 do **not** write checkpoints (pure test mode, but raw responses still go to `api_cache/`).
- Option 4 always runs a 1-batch dry-run first and asks for confirmation before committing.
- Option 5 reads checkpoint files; if assigned universities all show `last_completed_batch == total_batches`, exits with "Nothing to resume."
- Option 8 edits `configs/few_shot_examples.json` interactively; on save, recomputes `prompt_sha256` and warns if pipeline runs already exist (changing anchors mid-run breaks reproducibility).
- Option 9 refuses to run unless **every** researcher's checkpoint shows complete; emits `merged_outputs/all_vad_scores.json` and `vad_statistics_per_topic.json`.

---

## 10. Action Log Format

`vad_scoring/action_log.md` follows the exact same structure as [topic_modeling/action_log.md](topic_modeling/action_log.md):

```markdown
# VAD Scoring Pipeline — Action Log

This file records every implementation step for the vad_scoring phase.
Append-only; newest entries at the bottom. Mirrors topic_modeling/action_log.md.

Plan reference: [docs/plans/vad_scoring_pipeline.md](../docs/plans/vad_scoring_pipeline.md)

---

## ACTION-001 — 2026-05-06 — Scaffold vad_scoring project structure

Created folder tree per plan §2: ...

**Configs written:** ...
**Decisions:** ...
**Errors:** None.
**Next Steps:** ...
```

Runtime events (PIPELINE_INIT, API_TEST, CHECKPOINT, VALIDATION_WARNING, UNIVERSITY_COMPLETE) are logged by `pipeline.py` via `logging_setup.append_action_log()` in the same format. Sample entries from the user request §5 are canonical.

---

## 11. Verification Plan

End-to-end validation before declaring the pipeline production-ready:

1. **Unit tests** (run via `pytest vad_scoring/tests/`):
   - `test_parser.py`: malformed JSON → repair recovery; missing post_id detection; duplicate ID rejection.
   - `test_validator.py`: out-of-range clamping; PII regex coverage; schema validation.
   - `test_distribute.py`: bin-pack correctness for 1, 2, 3, 4, 5 researchers; verify max-min batch delta < 200.

2. **Smoke test (no API)**:
   - `python -m vad_scoring` → option 1 → pick `researcher_1` → assign `CAR-PUB-1` only (smallest, 458 batches).
   - Verify config file written to `configs/researcher_1.json`.

3. **API connectivity**:
   - Option 2 (single test post) → verify NIM returns valid JSON, latency <5s, schema passes.
   - Option 3 (single batch of 5) → verify all 5 IDs returned, all V/A/D ∈ [1,9].

4. **Resume correctness**:
   - Run option 4 on `CAR-PUB-1`, kill process at ~batch 50, run option 5, verify resumes at batch 51 (not 0 or 100).

5. **Inter-rater reliability** (per [methodology_changes.md §8.5](methodology_changes.md)):
   - Before full distributed run, all participating researchers score the same 100-post sample.
   - Compute ICC(2,1) for V, A, D separately. Must be ≥ 0.75. If not, halt and recalibrate prompt.

6. **Full corpus run** (after IRR passes):
   - Each researcher runs option 4 on assigned universities.
   - Lead monitors progress via option 6 across all researchers (reads checkpoint dirs).

7. **Post-merge validation**:
   - Lead runs option 9.
   - Run option 7 over `merged_outputs/all_vad_scores.json` — must show 0 schema failures, total record count = 37,074 (or 37,074 minus PII rejections, with rejection count documented in `pii_violations.jsonl`).
   - Spot-check 50 random records across universities for face validity.

8. **Reproducibility audit**:
   - Verify `vad_config.json::prompt_sha256` matches the SHA computed from the current prompt + few-shot file.
   - Verify every record in `merged_outputs/` has a corresponding row in some `api_cache/raw_responses_*.jsonl`.

---

## 12. Out of Scope (deferred to later phases)

- Dashboard rendering (Flask + Chart.js) — separate phase per [methodology_changes.md §3.1](methodology_changes.md).
- HITL re-scoring of `sarcasm_flags.json` candidates — separate Label Studio export step.
- Cross-language calibration (Cebuano-heavy MIN-PUB-1 may need anchor adaptation) — flag for review after first full run, not pre-emptive.
- Fallback to OpenRouter / Together.ai if NIM free tier breaks — documented in [methodology_changes.md §4.3](methodology_changes.md), implementation deferred until needed.
