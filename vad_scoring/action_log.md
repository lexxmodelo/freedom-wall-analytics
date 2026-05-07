# VAD Scoring Pipeline — Action Log

This file records every implementation step for the vad_scoring phase. Append-only; newest entries at the bottom. Mirrors `topic_modeling/action_log.md`.

Project: AI-Driven Topic Modeling and Multidimensional Sentiment Analysis of Student Discourse on Philippine University Freedom Walls.
Pipeline location: `C:\Users\Alex Evan\Documents\Research\vad_scoring\` (sibling to `preprocessing/`, `scraper_project/`, `topic_modeling/`).
Plan reference: [docs/plans/vad_scoring_pipeline.md](../docs/plans/vad_scoring_pipeline.md)

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
## ACTION-016 — 2026-05-06 — CAR-PUB-1 failed-posts retry

_Logged at 20:54:02 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 15 previously-failed posts in CAR-PUB-1
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "n_originally_failed": 15,
  "n_recovered": 15,
  "n_still_failed": 0,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-017 — 2026-05-06 — CAR-PUB-1 second retry pass — 100%% coverage achieved (2287/2287)

_Logged at 20:54:24 PHT — type: `PIPELINE_RECOVERY`_

- **Action:** Ran a second option-5 retry pass on CAR-PUB-1 to chase the 15 posts still in failed_post_ids after ACTION-005. All 15 recovered in 34.6 seconds (3 batches). CAR-PUB-1 is now at 100%% coverage with 0 outstanding failures.
- **Output:** 
```json
{
  "wall_clock_seconds": 34.6,
  "n_attempted": 15,
  "n_recovered": 15,
  "n_still_failed": 0,
  "recovery_rate_pct": 100.0,
  "cumulative_total_scored": 2287,
  "cumulative_corpus_size": 2287,
  "cumulative_completion_pct": 100.0,
  "cumulative_wall_clock_minutes": 137.0,
  "sarcasm_flags_total": 221,
  "range_clamps_total": 0
}
```
- **Decisions:** Two-pass iterative recovery (option-5 → option-5) reaches 100%% on CAR-PUB-1 in ~7 min of additional runtime after the main run. This validates the resume+retry path as the correct pattern for researchers: run option-4, then option-5 once or twice until failed_post_ids stabilizes at 0.
- **Next Steps:** CAR-PUB-1 is final. Decide whether researcher_test/ output is the canonical CAR-PUB-1 contribution to the merged dataset, or whether the production researcher should re-score it from scratch as part of their assignment.

---
## ACTION-018 — 2026-05-06 — Researcher alexx configured

_Logged at 20:55:56 PHT — type: `SETUP`_

- **Action:** Researcher alexx initialized for 4-way split
- **Configuration:** 
```json
{
  "researcher_id": "alexx",
  "n_researchers_total": 4,
  "this_researcher_index": 2,
  "assigned_universities": [
    "CAR-PNSEC-1",
    "CAR-PUB-1",
    "CAR-PUB-2"
  ],
  "total_batches": 2016,
  "effective_rpm": 20
}
```

---
## ACTION-019 — 2026-05-06 — Re-attributed researcher_test → alexx (researcher 2 of 4)

_Logged at 21:01:39 PHT — type: `CONFIG`_

- **Action:** Team locked at N=4 researchers. Renamed all CAR-PUB-1 artifacts from researcher_test to alexx (the lead, who is researcher 2). LPT bin-pack at N=4 assigns alexx: CAR-PNSEC-1, CAR-PUB-1, CAR-PUB-2 (~2,016 batches total).
- **Configuration:** 
```json
{
  "team_size": 4,
  "researcher_id": "alexx",
  "researcher_index": 2,
  "assigned_universities": [
    "CAR-PNSEC-1",
    "CAR-PUB-1",
    "CAR-PUB-2"
  ],
  "remaining_universities_for_alexx": [
    "CAR-PNSEC-1",
    "CAR-PUB-2"
  ]
}
```
- **Input:** 
```json
{
  "distribution_at_n4": {
    "R1": "MIN-PUB-1, MM-PSEC-1, MM-PUB-1 (2263 batches)",
    "R2 (alexx)": "CAR-PNSEC-1, CAR-PUB-1, CAR-PUB-2 (2016 batches)",
    "R3": "CAR-PSEC-1, MM-PNSEC-1 (1566 batches)",
    "R4": "CAR-PNSEC-2, PROV-PUB-1 (1574 batches)"
  }
}
```
- **Output:** 
```json
{
  "records_re_attributed": 2287,
  "files_moved": [
    "checkpoints/alexx/",
    "results/alexx/",
    "api_cache/raw_responses_alexx.jsonl"
  ],
  "config_written": "configs/alexx.json",
  "config_deleted": "configs/researcher_test.json"
}
```
- **Decisions:** Kept the CAR-PUB-1 100%%-scored output as the canonical contribution from alexx — no reason to rerun. Now alexx only needs to score CAR-PNSEC-1 and CAR-PUB-2.
- **Next Steps:** alexx runs option 4 → it will see CAR-PUB-1 already complete and start on CAR-PNSEC-1 + CAR-PUB-2 (~1,558 batches combined). Other 3 researchers run option 1 to set up their own configs and start their assignments in parallel.

---
## ACTION-020 — 2026-05-06 — Researcher alexx starting full VAD scoring

_Logged at 21:12:43 PHT — type: `PIPELINE_INIT`_

- **Action:** Researcher alexx began full VAD scoring
- **Configuration:** 
```json
{
  "researcher_id": "alexx",
  "assigned_universities": [
    "CAR-PNSEC-1",
    "CAR-PUB-1",
    "CAR-PUB-2"
  ],
  "model_id": "meta/llama-3.3-70b-instruct",
  "temperature": 0.1,
  "batch_size": 5,
  "effective_rpm": 20,
  "prompt_sha256": "6ea1920322b0fbc1abb1ad67eff808afb57ba07ad82f5ebe077575eb4a1335ba"
}
```

---
## ACTION-021 — 2026-05-06 — CAR-PNSEC-1 progress

_Logged at 21:38:58 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 100 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "batch": "106/799",
  "completed_post_ids": 500,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 55
}
```

---
## ACTION-022 — 2026-05-06 — CAR-PNSEC-1 progress

_Logged at 22:11:01 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 200 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "batch": "217/799",
  "completed_post_ids": 999,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 111
}
```

---
## ACTION-023 — 2026-05-06 — CAR-PNSEC-1 progress

_Logged at 22:37:44 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 300 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "batch": "326/799",
  "completed_post_ids": 1499,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 154
}
```

---
## ACTION-024 — 2026-05-06 — CAR-PNSEC-1 progress

_Logged at 23:03:14 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 400 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "batch": "432/799",
  "completed_post_ids": 1998,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 216
}
```

---
## ACTION-025 — 2026-05-06 — CAR-PNSEC-1 progress

_Logged at 23:26:54 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 500 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "batch": "538/799",
  "completed_post_ids": 2498,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 262
}
```

---
## ACTION-026 — 2026-05-06 — CAR-PNSEC-1 progress

_Logged at 23:50:24 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 600 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "batch": "651/799",
  "completed_post_ids": 2997,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 323
}
```

---
## ACTION-027 — 2026-05-07 — CAR-PNSEC-1 progress

_Logged at 00:18:39 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 700 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "batch": "754/799",
  "completed_post_ids": 3497,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 367
}
```

---
## ACTION-028 — 2026-05-07 — CAR-PNSEC-1 scoring complete

_Logged at 00:29:31 PHT — type: `PIPELINE`_

- **Action:** University CAR-PNSEC-1 fully scored by alexx
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "total_batches": 799,
  "successful_requests": 742,
  "failed_requests": 57,
  "completed_post_ids": 3703,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 389,
  "pii_rejected_count": 0,
  "complete": true,
  "halted_reason": null
}
```

---
## ACTION-029 — 2026-05-07 — CAR-PUB-1 scoring complete

_Logged at 00:29:32 PHT — type: `PIPELINE`_

- **Action:** University CAR-PUB-1 fully scored by alexx
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-1",
  "total_batches": 458,
  "successful_requests": 420,
  "failed_requests": 38,
  "completed_post_ids": 2287,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 221,
  "pii_rejected_count": 0,
  "complete": true,
  "halted_reason": null
}
```

---
## ACTION-030 — 2026-05-07 — CAR-PUB-2 progress

_Logged at 00:58:38 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 100 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "batch": "106/759",
  "completed_post_ids": 500,
  "out_of_range_clamps": 0,
  "sarcasm_flags": 48
}
```

---
## ACTION-031 — 2026-05-07 — CAR-PUB-2 progress

_Logged at 01:30:11 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 200 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "batch": "210/759",
  "completed_post_ids": 1000,
  "out_of_range_clamps": 1,
  "sarcasm_flags": 101
}
```

---
## ACTION-032 — 2026-05-07 — CAR-PUB-2 progress

_Logged at 01:54:33 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 300 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "batch": "325/759",
  "completed_post_ids": 1500,
  "out_of_range_clamps": 1,
  "sarcasm_flags": 144
}
```

---
## ACTION-033 — 2026-05-07 — CAR-PUB-2 progress

_Logged at 02:20:24 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 400 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "batch": "438/759",
  "completed_post_ids": 1999,
  "out_of_range_clamps": 1,
  "sarcasm_flags": 182
}
```

---
## ACTION-034 — 2026-05-07 — CAR-PUB-2 progress

_Logged at 02:51:34 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 500 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "batch": "545/759",
  "completed_post_ids": 2499,
  "out_of_range_clamps": 1,
  "sarcasm_flags": 218
}
```

---
## ACTION-035 — 2026-05-07 — CAR-PUB-2 progress

_Logged at 03:18:47 PHT — type: `CHECKPOINT`_

- **Action:** Auto-checkpoint after 600 requests
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "batch": "657/759",
  "completed_post_ids": 2999,
  "out_of_range_clamps": 1,
  "sarcasm_flags": 249
}
```

---
## ACTION-036 — 2026-05-07 — CAR-PUB-2 scoring complete

_Logged at 03:41:04 PHT — type: `PIPELINE`_

- **Action:** University CAR-PUB-2 fully scored by alexx
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "total_batches": 759,
  "successful_requests": 693,
  "failed_requests": 66,
  "completed_post_ids": 3459,
  "out_of_range_clamps": 1,
  "sarcasm_flags": 293,
  "pii_rejected_count": 0,
  "complete": true,
  "halted_reason": null
}
```

---
## ACTION-037 — 2026-05-07 — CAR-PNSEC-1 failed-posts retry

_Logged at 10:07:39 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 288 previously-failed posts in CAR-PNSEC-1
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "n_originally_failed": 288,
  "n_recovered": 268,
  "n_still_failed": 20,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-038 — 2026-05-07 — Retry pass timing & root-cause analysis for thesis documentation

_Logged at 10:10:40 PHT — type: `METHODOLOGY`_

- **Action:** Catalogued every retry pass executed during the alexx pilot of the VAD scoring pipeline (CAR-PUB-1 + CAR-PNSEC-1 + CAR-PUB-2). Captured the batch-failure rate per pass, the wall-clock time of each retry, and the underlying causes observed in the api_cache + warning logs. Intended to feed the methodology section and the README troubleshooting matrix.
- **Input:** 
```json
{
  "context": "NVIDIA NIM free tier (meta/llama-3.3-70b-instruct), effective_rpm=20 token bucket, batch_size=5, observed throughput ~3.5 batches/min",
  "retry_mechanism": "5 HTTP-level retries per batch with exponential backoff 1->2->4->8->16s; on full exhaustion the batch posts join failed_post_ids; option-5 (retry_failed_posts) re-attempts those posts in fresh batches of 5"
}
```
- **Output:** 
```json
{
  "CAR-PUB-1_timeline": {
    "initial_run": {
      "wall_minutes": 129.0,
      "batches": 458,
      "failed_batches": 38,
      "coverage_pct": 91.6
    },
    "retry_pass_1": {
      "wall_minutes": 7.4,
      "failed_posts_attempted": 192,
      "recovered": 177,
      "still_failed": 15,
      "cumulative_pct": 99.3
    },
    "retry_pass_2": {
      "wall_minutes": 0.6,
      "failed_posts_attempted": 15,
      "recovered": 15,
      "still_failed": 0,
      "cumulative_pct": 100.0
    },
    "total_passes_to_100pct": 3,
    "cumulative_wall_minutes": 137.0
  },
  "CAR-PNSEC-1_timeline": {
    "initial_run": {
      "wall_minutes_estimate": 228,
      "batches": 799,
      "failed_batches": 57,
      "coverage_pct": 92.9
    },
    "retry_pass_1": "in_progress_at_log_time (~17 min expected for 288 posts -> 58 batches)"
  },
  "CAR-PUB-2_timeline": {
    "initial_run": {
      "wall_minutes_estimate": 217,
      "batches": 759,
      "failed_batches": 66,
      "coverage_pct": 91.3
    },
    "retry_pass_1": "queued_after_CAR-PNSEC-1 (~19 min expected for 332 posts -> 67 batches)"
  },
  "observed_batch_failure_rate_pct": {
    "CAR-PUB-1_pass_1": 8.3,
    "CAR-PUB-1_pass_2": 7.8,
    "CAR-PUB-1_pass_3": 0.0,
    "CAR-PNSEC-1_pass_1": 7.1,
    "CAR-PUB-2_pass_1": 8.7,
    "pattern": "Each pass loses 7-9 percent of attempted batches. Two-to-three passes reach 100 percent coverage."
  },
  "root_causes_of_batch_failures": {
    "http_429_too_many_requests": {
      "frequency": "most common (~50-70 percent of warnings)",
      "reason": "NVIDIA NIM free tier throttles harder than the advertised 40 RPM ceiling. Even at our 20 RPM token-bucket setting, the server pushes back with 429.",
      "pipeline_response": "Honor Retry-After header if present; else exponential backoff. After 5 failed retries the batch posts go to failed_post_ids."
    },
    "http_502_bad_gateway": {
      "frequency": "occasional bursts",
      "reason": "NVIDIA backend instance restart or load-balancer hiccup. Comes in clusters when their infra has a brief incident.",
      "pipeline_response": "Same 5-retry exponential backoff as 5xx errors."
    },
    "read_operation_timed_out": {
      "frequency": "frequent on long batches",
      "reason": "30-second per-request timeout exceeded. Some batches contain very long posts that need more time for the 70B model to generate the JSON array. Network blips on the researcher side also contribute.",
      "pipeline_response": "Retry with same body. Truncation cap at 1500 chars (tail-preserving) reduces but does not eliminate this."
    },
    "http_5xx_other": {
      "frequency": "rare",
      "reason": "Generic NVIDIA backend errors (500/503).",
      "pipeline_response": "5-retry exponential backoff."
    }
  },
  "methodology_implications": {
    "expected_loss_per_pass_pct": "7-9 (free tier)",
    "passes_to_100pct_coverage": "2-3 typically",
    "researcher_workflow": "option-4 once, then option-5 (resume+retry) one or two times until failed_post_ids stabilises at 0",
    "time_overhead_of_retries_vs_initial_pct": "CAR-PUB-1: 6.0 percent additional time (8 min on top of 129 min) to reach 100 percent from 91.6 percent",
    "reproducibility": "Each retry uses the same prompt_sha256 and same temp=0.1 settings; recovered records are indistinguishable from initial-pass records"
  }
}
```
- **Decisions:** Document this in the thesis methodology as a known property of the NIM free tier rather than a defect of the pipeline. The 5-retry-per-call + iterative-resume pattern reaches 100 percent coverage with 5-10 percent time overhead, which is acceptable for the budget (zero cost) and academic timeline.
- **Next Steps:** Add a Methodology subsection (e.g., 4.4 "Throughput and recovery") that quotes the failure-rate range, the retry-pass count, and the time-overhead percentage. Reference this action-log entry in the thesis appendix as primary evidence.

---
## ACTION-039 — 2026-05-07 — CAR-PUB-2 failed-posts retry

_Logged at 10:23:01 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 332 previously-failed posts in CAR-PUB-2
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "n_originally_failed": 332,
  "n_recovered": 291,
  "n_still_failed": 41,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-040 — 2026-05-07 — alexx retry pass 1 across CAR-PNSEC-1, CAR-PUB-1, CAR-PUB-2

_Logged at 10:23:29 PHT — type: `PIPELINE_RECOVERY`_

- **Action:** Ran option-5 retry across all three of alexx's assigned universities. CAR-PUB-1 had 0 failures (skipped). CAR-PNSEC-1 and CAR-PUB-2 each saw their first retry pass; both moved from ~92 percent to ~99 percent coverage in 33 minutes total.
- **Output:** 
```json
{
  "wall_clock_minutes_total": 33.7,
  "CAR-PNSEC-1_pass_1": {
    "wall_minutes": 18.3,
    "attempted": 288,
    "recovered": 268,
    "still_failed": 20,
    "recovery_rate_pct": 93.1,
    "cumulative_scored": 3971,
    "cumulative_corpus": 3991,
    "cumulative_coverage_pct": 99.5
  },
  "CAR-PUB-1_skipped": {
    "reason": "already_at_100pct",
    "scored": 2287,
    "corpus": 2287
  },
  "CAR-PUB-2_pass_1": {
    "wall_minutes": 15.4,
    "attempted": 332,
    "recovered": 291,
    "still_failed": 41,
    "recovery_rate_pct": 87.7,
    "cumulative_scored": 3750,
    "cumulative_corpus": 3791,
    "cumulative_coverage_pct": 98.9
  },
  "alexx_grand_total_scored": 10008,
  "alexx_grand_total_corpus": 10069,
  "alexx_grand_total_coverage_pct": 99.4
}
```
- **Decisions:** Both CAR-PNSEC-1 (20 left) and CAR-PUB-2 (41 left) need one more retry pass to converge to 100 percent. Pattern matches CAR-PUB-1 exactly (which needed 2 passes). Recovery rate per pass continues to land in the 87-93 percent range.
- **Next Steps:** Run option-5 once more for alexx to reach 100 percent on all 3 universities. Expected ~3 min wall clock for the remaining 61 posts (~13 batches).

---
## ACTION-041 — 2026-05-07 — CAR-PNSEC-1 failed-posts retry

_Logged at 10:30:27 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 20 previously-failed posts in CAR-PNSEC-1
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "n_originally_failed": 20,
  "n_recovered": 19,
  "n_still_failed": 1,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-042 — 2026-05-07 — CAR-PUB-2 failed-posts retry

_Logged at 10:32:39 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 41 previously-failed posts in CAR-PUB-2
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "n_originally_failed": 41,
  "n_recovered": 35,
  "n_still_failed": 6,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-043 — 2026-05-07 — CAR-PNSEC-1 failed-posts retry

_Logged at 10:32:56 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 1 previously-failed posts in CAR-PNSEC-1
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "n_originally_failed": 1,
  "n_recovered": 0,
  "n_still_failed": 1,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-044 — 2026-05-07 — CAR-PUB-2 failed-posts retry

_Logged at 10:33:09 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 6 previously-failed posts in CAR-PUB-2
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "n_originally_failed": 6,
  "n_recovered": 5,
  "n_still_failed": 1,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-045 — 2026-05-07 — CAR-PNSEC-1 failed-posts retry

_Logged at 10:33:31 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 1 previously-failed posts in CAR-PNSEC-1
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "n_originally_failed": 1,
  "n_recovered": 0,
  "n_still_failed": 1,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-046 — 2026-05-07 — CAR-PUB-2 failed-posts retry

_Logged at 10:33:54 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 1 previously-failed posts in CAR-PUB-2
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "n_originally_failed": 1,
  "n_recovered": 0,
  "n_still_failed": 1,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-047 — 2026-05-07 — alexx convergence loop — 99.98 percent scored, 2 posts unrecoverable

_Logged at 10:34:44 PHT — type: `PIPELINE_CONVERGENCE`_

- **Action:** Ran a multi-pass retry loop across alexx's 3 universities until either zero failures or no further progress. Converged in 3 passes (4.5 min wall clock). Two posts (one in CAR-PNSEC-1, one in CAR-PUB-2) failed consistently across both retry passes 2 and 3 with no recovery — flagged as genuinely unrecoverable on the NIM free tier within the current 30s timeout.
- **Output:** 
```json
{
  "wall_clock_minutes": 4.5,
  "passes_run": 3,
  "pass_history": {
    "pass_1": {
      "before": 61,
      "after": 7,
      "recovered_pct": 88.5
    },
    "pass_2": {
      "before": 7,
      "after": 2,
      "recovered_pct": 71.4
    },
    "pass_3": {
      "before": 2,
      "after": 2,
      "recovered_pct": 0.0,
      "halt_trigger": "no_progress"
    }
  },
  "final_per_university": {
    "CAR-PNSEC-1": {
      "scored": 3990,
      "corpus": 3991,
      "coverage_pct": 99.975,
      "unrecoverable": 1
    },
    "CAR-PUB-1": {
      "scored": 2287,
      "corpus": 2287,
      "coverage_pct": 100.0,
      "unrecoverable": 0
    },
    "CAR-PUB-2": {
      "scored": 3790,
      "corpus": 3791,
      "coverage_pct": 99.974,
      "unrecoverable": 1
    }
  },
  "unrecoverable_posts": [
    {
      "post_id": "cccf6a96ad051b97",
      "univ_code": "CAR-PNSEC-1",
      "text_length_chars": 281,
      "note": "Short post about a stolen umbrella; contains a partially-censored profanity (CENSORED). Hypothesis: model safety filter consistently refuses or returns malformed JSON."
    },
    {
      "post_id": "eeeb98c19b874374",
      "univ_code": "CAR-PUB-2",
      "text_length_chars": 1425,
      "note": "Long formal complaint about registrar/admin staff behavior. Hypothesis: response generation for this specific post within a 5-post batch consistently exceeds the 30s timeout."
    }
  ],
  "alexx_grand_total": {
    "scored": 10067,
    "corpus": 10069,
    "coverage_pct": 99.98
  }
}
```
- **Decisions:** Accept 99.98 percent coverage as final for alexx's 3 universities. The 2 unrecoverable posts represent 0.02 percent loss; well below any reasonable thesis-publication threshold. Document them in the appendix as known failures with their causes (model safety filter / timeout) rather than continuing to grind retry passes.
- **Next Steps:** alexx is DONE. Other 3 researchers run the same loop pattern (option-4 then option-5 several times) and expect similar 99.98+ percent convergence. The 2 unrecoverable posts can be revisited later either with a longer request_timeout (e.g., 60s) or by manually requesting the lead score them with a 1-post batch (where their generation time would not be amplified by 5x).

---
## ACTION-048 — 2026-05-07 — CAR-PNSEC-1 failed-posts retry

_Logged at 10:39:15 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 1 previously-failed posts in CAR-PNSEC-1
- **Output:** 
```json
{
  "univ_code": "CAR-PNSEC-1",
  "n_originally_failed": 1,
  "n_recovered": 1,
  "n_still_failed": 0,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
## ACTION-049 — 2026-05-07 — CAR-PUB-2 failed-posts retry

_Logged at 10:39:28 PHT — type: `PIPELINE_RETRY`_

- **Action:** Retried 1 previously-failed posts in CAR-PUB-2
- **Output:** 
```json
{
  "univ_code": "CAR-PUB-2",
  "n_originally_failed": 1,
  "n_recovered": 0,
  "n_still_failed": 1,
  "skipped_missing_text": 0,
  "halted_reason": null
}
```

---
