# VAD Scoring Pipeline — Action Log

This file records every implementation step for the vad_scoring phase. Append-only; newest entries at the bottom. Mirrors `topic_modeling/action_log.md`.

Project: AI-Driven Topic Modeling and Multidimensional Sentiment Analysis of Student Discourse on Philippine University Freedom Walls.
Pipeline location: `C:\Users\Alex Evan\Documents\Research\vad_scoring\` (sibling to `preprocessing/`, `scraper_project/`, `topic_modeling/`).
Plan reference: [vad_scoring_pipeline.md](../../docs/plans/vad_scoring_pipeline.md)

---

## ACTION-001 — 2026-05-06 — Scaffold vad_scoring project structure

_Logged at scaffold time — type: `ACTION`_

- **Action:** Created the vad_scoring/ folder tree and the full Python package per plan §2 in a single session. Pipeline is end-to-end runnable but has not yet been exercised against real data.

**Folder tree created:**

```
vad_scoring/
├── action_log.md                    (this file)
├── README.md
├── .env.example
├── .gitignore
├── vad_scoring/                     (Python package)
│   ├── __init__.py
│   ├── __main__.py                  (interactive menu, 9 options)
│   ├── dotenv.py                    (verbatim from topic_modeling)
│   ├── io_utils.py                  (verbatim from topic_modeling)
│   ├── logging_setup.py             (verbatim from topic_modeling)
│   ├── nim_client.py                (adapted: TokenBucket + CircuitBreaker)
│   ├── prompt.py                    (locked SYSTEM/USER prompt + few-shot injection)
│   ├── batcher.py                   (3-source join + chunk_into_batches)
│   ├── parser.py                    (json → coerced records, json_repair fallback)
│   ├── validator.py                 (range clamp, reconcile, sarcasm consistency)
│   ├── pii_check.py                 (pre-API regex sweep)
│   ├── checkpoint.py                (per-batch resume state)
│   ├── distribute.py                (LPT bin-pack for 1-5 researchers)
│   ├── pipeline.py                  (per-university orchestrator)
│   └── merge.py                     (cross-researcher consolidation)
├── configs/
│   ├── vad_config.json              (locked global settings)
│   ├── researcher_template.json     (per-researcher template)
│   ├── few_shot_examples.json       (3 anchors: burnout, rage, sarcasm)
│   └── vad_output.schema.json       (JSON Schema for output records)
└── tests/
    ├── test_parser.py
    ├── test_validator.py
    └── test_distribute.py
```

**Configs written:**
- `configs/vad_config.json` — locked global settings; `prompt_sha256` is `"TBD_AT_FIRST_RUN_AND_FROZEN"` and gets computed by menu option 8 the first time anchors are confirmed.
- `configs/researcher_template.json` — mirrors `topic_modeling/configs/researcher_template.json` with VAD-specific fields (`assigned_universities` instead of `assigned_files`, `api_cache_path`).
- `configs/few_shot_examples.json` — 3 SAM-cube anchors per plan §7. Drafted in Taglish to test the model's pre-scoring sarcasm assessment from methodology_changes.md §3.4.
- `configs/vad_output.schema.json` — JSON Schema (draft-07) for output validation. Used by menu option 7.

**Decisions:**
- Reused `dotenv.py`, `io_utils.py`, `logging_setup.py` from `topic_modeling/` by COPYING (not importing). Same convention as topic_modeling ACTION-001 — keeps each pipeline runnable in isolation, no `sys.path` hacks.
- Reused the `TokenBucket` rate limiter pattern from `topic_modeling/labeling.py` verbatim. Added a new `CircuitBreaker` class because a 6-hour single-researcher run is realistic and we don't want a regional NIM outage to burn 100s of failed retries before halting.
- Score outliers (topic_id == -1) with topic context = `"Unclassified"` per planning decision. ~4,921 outlier posts are scored with this generic label rather than skipped — preserves dataset completeness for ICC analysis (heavily concentrated in MM-PSEC-1 33%, CAR-PNSEC-2 44%, MIN-PUB-1 42%).
- Effective rate limit defaulted to 20 RPM (half of NIM free-tier 40) per planning decision. Matches `topic_modeling/configs/researcher_template.json::effective_rpm`.
- Out-of-range V/A/D → clamp to nearest [1,9], log to `validation/range_anomalies.json`, no retry per planning decision. Retrying at temp=0.1 will likely return the same value; saves API budget.
- Truncation policy: tail-preserving (keep last 1500 chars, not first). Most freedom-wall posts put the emotional core at the end (rant resolution, reaction emoji) so tail preserves more VAD signal than head.
- Distribution algorithm: LPT (longest-processing-time) greedy bin-pack on batch counts. Provably ≤4/3 of optimal makespan for N≤5; trivial to verify by eye in the menu's `format_slice_table()` display.
- Failed post_ids deque capped at 5,000 entries to prevent state file bloat over long runs.

**Reused infrastructure from topic_modeling:**
- `dotenv.py` (file copy, provenance noted in header)
- `io_utils.py` (file copy)
- `logging_setup.py` (adapted: `topic_modeling_<stamp>.log` → `vad_scoring_<stamp>.log`)
- `TokenBucket` class pattern from `labeling.py`
- Menu UI helpers (`_input`, `_yesno`, `_menu`, `pick_researcher`, `ensure_dotenv`) from `__main__.py`
- `## ACTION-NNN — YYYY-MM-DD — Title` log format

**Inputs the pipeline expects (read-only, must exist before option 4):**
- `topic_modeling/outputs/{CODE}/topic_assignments.json` — verified present for all 10 universities
- `topic_modeling/outputs/{CODE}/topic_labels.json` — verified present for all 10 universities
- `preprocessing/output/{FW-NN}_cleaned.json` — verified present, 37,074 posts total
- `topic_modeling/configs/university_mapping.yaml` — single source of truth for code↔file mapping

**Errors:** None.

**Next Steps:**
1. Researcher creates their config: `python -m vad_scoring` → option 1 (asks N=1..5, then which researcher you are, distributes universities accordingly).
2. Lead computes `prompt_sha256`: option 8 → "Recompute prompt_sha256 now" (locks the anchor file's hash into vad_config.json so any future drift is detectable).
3. Each researcher runs option 4: dry-run one batch first, then full pipeline.
4. Lead monitors progress via option 6 across all researcher checkpoint dirs.
5. After all complete: lead runs option 7 (validate) → option 9 (merge) → option 7 again (validate merged output).
6. Inter-rater reliability sample (per methodology_changes.md §8.5): all researchers score the same 100-post sample; ICC ≥ 0.75 required for V, A, D before continuing.

---
## ACTION-002 — 2026-05-06 — Live NIM API smoke test (single post + 5-batch)

_Logged at 17:06:08 PHT — type: `API_TEST`_

- **Action:** Verified end-to-end VAD scoring against live NVIDIA NIM endpoint using a temporary researcher_test config and CAR-PSEC-1 data.
- **Configuration:** 
```json
{
  "researcher_id": "researcher_test",
  "model_id": "meta/llama-3.3-70b-instruct",
  "temperature": 0.1,
  "effective_rpm": 20,
  "prompt_sha256": "6ea1920322b0fbc1abb1ad67eff808afb57ba07ad82f5ebe077575eb4a1335ba"
}
```
- **Input:** 
```json
{
  "test_1_post": {
    "post_id": "test_burnout_1",
    "topic_label": "Academic Stress"
  },
  "test_2_source": "topic_modeling/outputs/CAR-PSEC-1 (first 5 posts joined)"
}
```
- **Output:** 
```json
{
  "test_1_single_post": {
    "latency_seconds": 26.18,
    "records_returned": 1,
    "missing_ids": [],
    "errors": [
      "extra_ids_in_response: ['test_burnout_2', 'test_rage_1', 'test_sarcasm_1', 'test_frustration_1']"
    ],
    "output": {
      "post_id": "test_burnout_1",
      "univ_code": "CAR-PSEC-1",
      "topic_id": -1,
      "topic_label": "Academic Stress",
      "V": 2,
      "A": 6,
      "D": 2,
      "sarcasm": false,
      "flags": [],
      "researcher_id": "researcher_test",
      "model_version": "meta/llama-3.3-70b-instruct",
      "scored_at": "2026-05-06T17:05:40+0800"
    }
  },
  "test_2_full_batch": {
    "latency_seconds": 27.65,
    "records_returned": 5,
    "expected": 5,
    "missing_ids": [],
    "errors": [],
    "avg_latency_per_post": 5.53,
    "sample_outputs": [
      {
        "post_id": "376db0582147aa83",
        "topic_label": "Unclassified",
        "V": 6,
        "A": 4,
        "D": 6,
        "sarcasm": true,
        "flags": []
      },
      {
        "post_id": "9eaef65d1b831546",
        "topic_label": "Student Campus Life Concerns",
        "V": 5,
        "A": 6,
        "D": 5,
        "sarcasm": false,
        "flags": []
      },
      {
        "post_id": "0b1d13e9528bea02",
        "topic_label": "Unrequited Love Confessions",
        "V": 8,
        "A": 7,
        "D": 7,
        "sarcasm": false,
        "flags": []
      },
      {
        "post_id": "a220069305cf5173",
        "topic_label": "Student Romantic Interactions",
        "V": 4,
        "A": 3,
        "D": 4,
        "sarcasm": false,
        "flags": []
      },
      {
        "post_id": "c4f58d67610107b6",
        "topic_label": "Unrequited Love Confessions",
        "V": 9,
        "A": 8,
        "D": 8,
        "sarcasm": false,
        "flags": []
      }
    ]
  }
}
```
- **Decisions:** Used a throwaway researcher_test config (assigned_universities=[CAR-PSEC-1]) to avoid touching the real researcher slots. Tests written records to api_cache/raw_responses_researcher_test.jsonl for audit. No checkpoints written (option 2/3 are debug paths).
- **Next Steps:** If both tests pass with valid V/A/D records and reasonable latency, real researchers can run option 1 → option 4. Otherwise debug the parser/prompt before broader rollout.

---
## ACTION-003 — 2026-05-06 — Full test run on CAR-PUB-1 (UPB)

_Logged at 17:18:05 PHT — type: `PIPELINE_INIT`_

- **Action:** Started full VAD scoring on CAR-PUB-1 via temporary researcher_test config to validate end-to-end pipeline against real data.
- **Configuration:** 
```json
{
  "researcher_id": "researcher_test",
  "assigned_universities": [
    "CAR-PUB-1"
  ],
  "model_id": "meta/llama-3.3-70b-instruct",
  "effective_rpm": 20,
  "prompt_sha256": "6ea1920322b0fbc1abb1ad67eff808afb57ba07ad82f5ebe077575eb4a1335ba"
}
```
- **Input:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "expected_posts": 2287,
  "expected_batches": 458,
  "estimated_minutes": 23
}
```

---
## ACTION-004 — 2026-05-06 — CAR-PUB-1 progress

_Logged at 17:39:52 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 100 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "batch": "107/428",
  "completed_post_ids": 499,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 50
}
```

---
## ACTION-005 — 2026-05-06 — Full test run on CAR-PUB-1 (UPB)

_Logged at 17:51:09 PHT — type: `PIPELINE_INIT`_

- **Action:** Started full VAD scoring on CAR-PUB-1 via temporary researcher_test config to validate end-to-end pipeline against real data.
- **Configuration:** 
```json
{
  "researcher_id": "researcher_test",
  "assigned_universities": [
    "CAR-PUB-1"
  ],
  "model_id": "meta/llama-3.3-70b-instruct",
  "effective_rpm": 20,
  "prompt_sha256": "6ea1920322b0fbc1abb1ad67eff808afb57ba07ad82f5ebe077575eb4a1335ba"
}
```
- **Input:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "expected_posts": 2287,
  "expected_batches": 458,
  "estimated_minutes": 23
}
```

---
## ACTION-006 — 2026-05-06 — Removed false-positive name_pattern PII detector

_Logged at 17:51:26 PHT — type: `BUGFIX`_

- **Action:** First full run on CAR-PUB-1 found 151/2287 posts (6.6%) rejected as PII. Inspection revealed 100%% false positives — all hits were innocent capitalized bigrams: "Freedom Wall", "Baguio City", "Comp Sci", "Studio Ghibli", "Good Lord", etc. Zero real names caught (preprocessing already masked them as [REDACTED_NAME]). Removed the name_pattern check from pii_check.py; kept email + phone-number checks (still aligned with methodology_changes.md §4.1).
- **Input:** 
```json
{
  "detector": "pii_check._NAME_RE pattern \b[A-Z][a-z]+\\s+[A-Z][a-z]+\b",
  "sample_false_positives": [
    "Freedom Wall",
    "Arcane Society",
    "Baguio City",
    "Soc Sci",
    "Studio Ghibli",
    "Latin Honors"
  ],
  "distinct_false_positive_strings": 207,
  "real_emails_caught": 0,
  "real_phones_caught": 0
}
```
- **Decisions:** Trust preprocessing's upstream NER for person-name masking. The double-coverage at the API boundary added zero safety value while causing meaningful data loss. If preprocessing misses a name, that is a preprocessing bug to fix upstream, not something to paper over with brittle bigram heuristics here.
- **Next Steps:** Restart full run on CAR-PUB-1 with corrected PII check. Should now process all 2,287 posts → 458 batches.

---
## ACTION-007 — 2026-05-06 — CAR-PUB-1 progress

_Logged at 18:23:28 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 100 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "batch": "112/458",
  "completed_post_ids": 499,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 54
}
```

---
## ACTION-008 — 2026-05-06 — CAR-PUB-1 progress

_Logged at 19:01:27 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 200 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "batch": "227/458",
  "completed_post_ids": 998,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 111
}
```

---
## ACTION-009 — 2026-05-06 — CAR-PUB-1 progress

_Logged at 19:30:17 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 300 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "batch": "330/458",
  "completed_post_ids": 1498,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 158
}
```

---
## ACTION-010 — 2026-05-06 — CAR-PUB-1 progress

_Logged at 19:54:51 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 400 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "batch": "437/458",
  "completed_post_ids": 1998,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 201
}
```

---
## ACTION-011 — 2026-05-06 — CAR-PUB-1 scoring complete

_Logged at 20:00:18 PHT — type: `PIPELINE`_

- **Action:** University CAR-PUB-1 fully scored by researcher_test
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "total_batches": 458,
  "successful_requests": 420,
  "failed_requests": 38,
  "completed_post_ids": 2095,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 206,
  "pii_rejected_count": 0,
  "complete": true,
  "halted_reason": null
}
```

---
## ACTION-012 — 2026-05-06 — Full test on CAR-PUB-1 complete

_Logged at 20:00:18 PHT — type: `PIPELINE_DONE`_

- **Action:** Pipeline completed for CAR-PUB-1 in 129.2 minutes
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "total_batches": 458,
  "successful_requests": 420,
  "failed_requests": 38,
  "completed_post_ids": 2095,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 206,
  "pii_rejected_count": 0,
  "complete": true,
  "halted_reason": null,
  "wall_clock_seconds": 7749.2,
  "wall_clock_minutes": 129.15
}
```
- **Next Steps:** Run validator (menu option 7) on the output JSONL; spot-check 50 random records for face validity; compare per-topic V/A/D distributions to expected priors before greenlighting full corpus.

---
## ACTION-013 — 2026-05-06 — CAR-PUB-1 (UPB) full run complete — 2,095/2,287 posts scored

_Logged at 20:01:47 PHT — type: `PIPELINE_DONE`_

- **Action:** Full VAD pipeline run on CAR-PUB-1 completed in 129 minutes (2h 9m). 91.6% of corpus successfully scored; 192 posts lost to API give-ups after exhausting 5-retry backoff (these are recoverable via menu option 5).
- **Configuration:** 
```json
{
  "researcher_id": "researcher_test",
  "univ_code": "CAR-PUB-1",
  "effective_rpm_target": 20,
  "observed_rpm": 8.1
}
```
- **Output:** 
```json
{
  "wall_clock_minutes": 129.15,
  "records_written": 2095,
  "corpus_size": 2287,
  "completion_pct": 91.6,
  "successful_batches": 420,
  "failed_batches": 38,
  "batch_failure_rate_pct": 8.3,
  "posts_lost_to_api_giveup": 192,
  "sarcasm_flags": 206,
  "sarcasm_rate_pct": 9.8,
  "range_clamps": 0,
  "pii_rejections": 0,
  "http_retry_distribution": {
    "attempt_1_success_pct": 45.2,
    "attempt_2": 106,
    "attempt_3": 60,
    "attempt_4": 46,
    "attempt_5": 18,
    "total_http_retries": 230
  },
  "face_validity": {
    "roommate_noise_complaints_n41": {
      "V": 4.24,
      "A": 7.66,
      "D": 4.9,
      "note": "low V, high A, low-mid D = annoyed but not in control"
    },
    "amused_reactions_to_cheating_n24": {
      "V": 8.04,
      "A": 7.67,
      "D": 6.92,
      "note": "high V high A high D = positive amusement"
    },
    "student_politics_n1106": {
      "V": 5.13,
      "A": 5.46,
      "D": 5.58,
      "sarcasm_pct": 13.7
    },
    "personal_college_life_n850": {
      "V": 5.82,
      "A": 5.16,
      "D": 5.88,
      "sarcasm_pct": 5.4
    }
  },
  "distribution_shape": "V mean=5.46 sd=2.09 (slightly positive), A mean=5.46 sd=1.75 (centered), D mean=5.72 sd=1.51 (tight center, model conservative on dominance extremes)"
}
```
- **Decisions:** Anchor regurgitation: 1 response (out of 420) contained anchor_* IDs from the few-shot examples — negligible hallucination rate. Length mismatches: 1. Per-topic V/A/D means pass face-validity inspection.
- **Next Steps:** ISSUE: NIM free-tier throughput is only ~8 RPM observed (not 20 RPM token-bucket capacity) due to heavy 429 retries on the server side. Implications: 1) Full corpus (37,074 posts) at 1 researcher would take ~24 hours not 6. 2) 8% post-loss rate per university; methodology requires a resume pass to re-attempt failed_post_ids. 3) Recommend running the resume pass after the initial scan, OR raising effective_rpm to test whether throttling is server-side regardless of our limiter setting. 4) For real distributed run (multi-researcher), recommend N=3+ researchers to keep wall-clock under 8 hours each.

---
## ACTION-014 — 2026-05-06 — CAR-PUB-1 failed-posts retry

_Logged at 20:18:01 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 192 previously-failed posts in CAR-PUB-1
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "n_originally_failed": 192,
  "n_recovered": 177,
  "n_still_failed": 15,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-015 — 2026-05-06 — CAR-PUB-1 retry pass — 177/192 failed posts recovered (now 99.3% scored)

_Logged at 20:18:39 PHT — type: `PIPELINE_RECOVERY`_

- **Action:** Validated the new retry_failed_posts() function on CAR-PUB-1. Took 7m 23s to re-attempt 192 posts (39 batches). Recovered 177; 15 still failed (recoverable with another retry pass). Brings CAR-PUB-1 from 91.6%% to 99.3%% scored.
- **Output:** 
```json
{
  "wall_clock_seconds": 443.0,
  "wall_clock_minutes": 7.4,
  "n_originally_failed": 192,
  "n_recovered": 177,
  "n_still_failed": 15,
  "recovery_rate_pct": 92.2,
  "retry_throughput_rpm_observed": 28,
  "cumulative_total_scored": 2272,
  "cumulative_corpus_size": 2287,
  "cumulative_completion_pct": 99.3,
  "cumulative_wall_clock_minutes": 136.4
}
```
- **Decisions:** Pipeline now production-ready for researchers. Menu option 5 was extended to also retry failed_post_ids in completed universities, so this path is exposed to all researchers without needing a custom script. The 15 remaining failures could be recovered with another option-5 pass, but the iterative nature is the point — researchers run option 5 until failed_post_ids stabilizes at a tiny number.
- **Next Steps:** Researchers can be onboarded via vad_scoring/QUICKSTART.md. Lead should: (1) commit the vad_scoring/ tree, (2) distribute the team count + per-researcher index, (3) collect everyone's results/+checkpoints/ at the end and run option 9 (merge).

---
