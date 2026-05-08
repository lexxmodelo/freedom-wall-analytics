# Quickstart — VAD Scoring Pipeline

For researchers running the VAD (Valence/Arousal/Dominance) scoring phase. Plan to spend **30 min reading this** + a **few hours of unattended runtime** (the pipeline does the work; you mostly babysit).

> **Status:** Validated on the SLU pilot region — full 2,287-post run on `CAR-PUB-1` completed end-to-end. Real-world throughput is ~8 RPM (the NIM free tier throttles harder than its advertised 40 RPM ceiling), so plan for **~5 minutes per 100 posts**.

---

## 0. Before you start

You need:

- A free **NVIDIA NIM API key** — sign up at https://build.nvidia.com → "Generate API Key" → starts with `nvapi-...`
- **Python 3.10+**
- The repo cloned (`preprocessing/output/` is already in git ✓)
- **Topic modeling outputs from the lead's Google Drive** — see step 1 below
- A reliable internet connection. **The run will be 1-3 hours per researcher**, depending on your assignment.

You will be **one of 1–5 researchers** running this pipeline in parallel, each with your own API key, on your own laptop. The lead will tell you `N` (total researchers) and your researcher number.

---

## 1. Get the topic modeling outputs (one-time, 2 min)

The `topic_modeling/outputs/` folder is **not in git** (it's a 3.9 MB artifact bundle of the upstream BERTopic phase). The lead will share a Google Drive link containing a `topic_modeling_outputs.zip` (or similar).

After cloning the repo:

```bash
# from the repo root
cd topic_modeling/
# extract the lead's drive download here so the tree looks like:
#   topic_modeling/outputs/CAR-PSEC-1/topic_assignments.json
#   topic_modeling/outputs/CAR-PSEC-1/topic_labels.json
#   topic_modeling/outputs/CAR-PUB-1/...
#   ... (10 university directories total)
```

Verify it landed correctly:

```bash
ls topic_modeling/outputs/        # should list 10 directories
ls topic_modeling/outputs/CAR-PSEC-1/   # should contain topic_assignments.json + topic_labels.json (and friends)
```

If you don't see all 10 university directories, ping the lead before continuing.

---

## 2. First-time setup (5 min)

```bash
cd vad_scoring/
cp .env.example .env
```

Edit `.env` and paste your key:

```
NVIDIA_NIM_API_KEY=nvapi-YOUR-ACTUAL-KEY-HERE
```

Install dependencies:

```bash
pip install httpx pyyaml pytest
```

Verify the package loads:

```bash
python -c "import vad_scoring; print('OK')"
```

(Optional but recommended) Run the unit tests — should print `46 passed`:

```bash
python -m pytest tests/
```

---

## 3. Configure your researcher slot (2 min)

Launch the menu:

```bash
python -m vad_scoring
```

Pick **option 1 — Set up a researcher config**.

The menu will:

1. Show all 10 active universities and ask **how many researchers total** (1-5). Use the number the lead gave you.
2. Show the proposed split (LPT bin-pack — biggest universities go first to balance load).
3. Ask **which researcher you are** (1 to N).
4. Ask for a save name (default `researcher_<N>`).
5. Write your assignment to `configs/researcher_<id>.json`.

Sample distribution display for N=3:

```
Researcher  | Universities                                  | Batches | Time @ 20 RPM
-----------------------------------------------------------------------------------
R1          | CAR-PSEC-1, CAR-PUB-2, MIN-PUB-1              |    2332 |   117 min
R2          | CAR-PNSEC-1, PROV-PNSEC-1, MM-PSEC-1          |    2329 |   116 min
R3          | CAR-PUB-1, MM-PNSEC-1, MM-PUB-1, PROV-PUB-1   |    2758 |   138 min
```

> ⚠ **Real wall-clock will be 2-3× longer** than the "Time @ 20 RPM" estimate above, because NIM throttles at ~8 RPM in practice. R3's 2,758 batches → ~6 hours of real runtime, not 138 min.

---

## 4. Smoke test (3 min)

**Always run these two before kicking off the full pipeline.** They confirm your API key works and the prompt is being parsed correctly.

- **Option 2 — Score a single test post:** type any sentence + topic, get back a JSON record with V/A/D and sarcasm.
- **Option 3 — Score a single 5-post batch:** pulls 5 real posts from your first assigned university and runs them through. You'll see 5 scored records.

If either fails with `AuthError`, your key is wrong. Fix `.env` and try again.

---

## 5. Run the full pipeline

**Option 4 — Run full pipeline for assigned universities.**

It runs a **1-batch dry-run first** and asks for confirmation before committing. If the dry-run fails, debug it before continuing — don't proceed if scores look wrong.

After confirmation, the pipeline:

- Processes your universities one at a time
- Auto-checkpoints every 100 successful batches → `checkpoints/researcher_<id>/<CODE>_state.json`
- Appends results to `results/researcher_<id>/<CODE>_vad_scores.jsonl` after every batch
- Writes every raw API response to `api_cache/raw_responses_<id>.jsonl` (audit trail)
- Logs per-university completion to `action_log.md`

You can **leave it running** and walk away. Don't put your laptop to sleep — that pauses the run.

### What you'll see in the terminal

```
[CAR-PSEC-1] truncated 108 posts to 1500 chars (tail-preserving)
[CAR-PSEC-1] 3864 posts → 773 batches (after 0 PII rejects)
[CAR-PSEC-1] resuming from batch 0/773
... (long quiet stretch as batches process at ~12 sec each) ...
NIM 429 attempt 1; sleeping 1.0s     ← normal, the limiter handles it
... (more processing) ...
```

### If you need to stop

Just `Ctrl+C` (or close the terminal). State is durable.

---

## 6. Resume after interruption

**Option 5 — Resume from last checkpoint.**

The pipeline automatically:

- Reads each university's state file and resumes from `last_completed_batch + 1`
- Skips any post already in the completed-IDs sidecar (safe against partial writes mid-batch)
- **Also retries the `failed_post_ids` deque** for universities that finished with non-empty failures (a batch can give up after 5 retries; option 5 takes a second pass at those posts)

Run option 5 as many times as you like — each pass shrinks `failed_post_ids` further. Most posts recover within 1-2 retry passes.

---

## 7. Check progress

**Option 6 — Show progress / list checkpoints.**

For every researcher config that exists, prints something like:

```
# researcher_3 (assigned: ['CAR-PUB-1', 'MM-PNSEC-1', 'MM-PUB-1', 'PROV-PUB-1'])
  [DONE]        CAR-PUB-1: 458/458 batches | clamps=0 | sarcasm=206 | failed=38
  [in-progress] MM-PNSEC-1: 247/793 batches | clamps=2 | sarcasm=89  | failed=11
  [pending]     MM-PUB-1
  [pending]     PROV-PUB-1
```

Lead can run option 6 across all researcher configs by copying everyone's config files into `configs/` (or by SSH'ing to each laptop).

---

## 8. Validate your output (1 min)

After every university completes, **option 7 — Validate outputs** scans every JSONL line against the JSON Schema (V/A/D ∈ [1,9], required fields, etc.) and writes a report to `validation/schema_validation_report.json`.

A healthy report looks like:

```json
{
  "researchers_validated": ["researcher_3"],
  "records_scanned": 14591,
  "failures": [],
  "pass_rate": 100.0
}
```

If `failures` is non-empty, fix the underlying issue (usually a bug, since the validator runs at scoring time too) and re-run option 7.

---

## 9. Hand off to the lead

When option 6 shows **`[DONE]`** for every assigned university and option 7 reports **100% pass rate**, you're done. Send the lead:

- `results/researcher_<id>/` (the JSONL files)
- `checkpoints/researcher_<id>/` (proves completeness)
- `api_cache/raw_responses_<id>.jsonl` (audit trail; lead may want this for reproducibility)

The lead will run **option 9 — Merge results** to combine everyone into `merged_outputs/all_vad_scores.json`.

---

## What CAN go wrong (and how the pipeline handles it)

| Symptom | Pipeline response | What you do |
|---|---|---|
| HTTP 429 (rate limited) | Backoff 1→2→4→8→16s, retry up to 5x | Nothing |
| HTTP 5xx / network blip | Same backoff, retry | Nothing |
| HTTP 401 (bad key) | **Halts immediately**, prints `Check NVIDIA_NIM_API_KEY` | Fix `.env`, restart with option 5 |
| Model returns non-JSON | json_repair → regex extract → up to 3 parser retries | Nothing |
| Model returns 4 records instead of 5 | Identifies the missing post_id, queues it as a single in next batch | Nothing |
| V/A/D = 0 or 10 (out of range) | **Clamps to nearest valid value** (1 or 9), flags `range_clamped` | Nothing — review `validation/range_anomalies.json` after |
| 10+ consecutive batch failures | Circuit breaker pauses 5 min, then half-opens | Wait, or Ctrl+C and resume later |
| Crash mid-run | State persists every 100 successful requests | Re-launch, option 5 |
| Some posts end up "lost" after the run completes | They're in `failed_post_ids` in the state file | Run option 5 — the retry path picks them up |
| `FileNotFoundError: ...topic_modeling/outputs/CAR-XXX-N/topic_assignments.json` | You skipped step 1 (or unzipped to the wrong place) | Re-extract the lead's Drive zip into `topic_modeling/` so the tree matches step 1 |

---

## Common questions

**Q: How long will my run actually take?**
Real-world throughput is **~8 RPM** (lower than the 20 RPM the limiter targets, because the NIM server itself throttles). So:

- 500 batches  → ~1 hour
- 1,000 batches → ~2 hours
- 2,500 batches → ~5 hours

Plan accordingly. Most researchers should expect **3-6 hours of total runtime** spread across all assigned universities.

**Q: Will I lose money if I run too long?**
No. NVIDIA NIM is free-tier; rate-limited but never billed.

**Q: Can I edit `configs/few_shot_examples.json` to improve scores?**
Don't unless the lead approves. Editing the anchors invalidates `prompt_sha256` and breaks reproducibility for the thesis. If you spot a mis-anchor, raise it with the team before changing.

**Q: What if I hit `1` or `9` a lot — is that wrong?**
No. The SAM scale is 1-9 by design; extreme scores are valid for genuinely extreme posts. Unless the model is clipping (always returning the same value), trust the distribution. The CAR-PUB-1 pilot showed mean V=5.46, mean A=5.46, mean D=5.72 — healthy spread.

**Q: My run "completed" but `failed=38` shows in option 6. Is that bad?**
~5-10% post-loss per pass is expected on the NIM free tier. Run option 5 — the retry path will recover most of them. A second resume pass usually brings the loss rate to <2%.

**Q: Can I run two researchers off one laptop?**
Yes, but they share your machine's network — they'll compete for the same NIM tier. Better: each researcher uses their own laptop and key. If you must run two on one box, run them sequentially (option 4 finishes researcher_1, then start researcher_2).

---

## Reference: what's in `vad_scoring/`

```
vad_scoring/
├── QUICKSTART.md                 ← this file
├── README.md                     ← short overview
├── action_log.md                 ← every run logged here
├── .env                          ← YOUR KEY (never commit)
├── configs/
│   ├── vad_config.json           ← global locked settings
│   ├── researcher_template.json  ← copied to researcher_<id>.json by option 1
│   ├── few_shot_examples.json    ← 3 SAM-cube anchors (don't edit unilaterally)
│   └── vad_output.schema.json    ← JSON Schema for outputs
├── results/researcher_<id>/      ← YOUR scored JSONLs
├── checkpoints/researcher_<id>/  ← YOUR resume state
├── api_cache/                    ← raw API responses (audit)
├── validation/                   ← anomaly logs
└── merged_outputs/               ← lead-only after option 9
```

---

## Help / troubleshooting

If something doesn't match this guide:

1. Check `action_log.md` — every run logs what it did.
2. Check `_full_test_run.log` if you're tailing one of the test scripts.
3. Re-run option 7 (validate) — usually surfaces output-format bugs.
4. Ask the lead. The pipeline source is heavily commented; `vad_scoring/vad_scoring/pipeline.py` is the orchestrator.

Good luck. Don't be afraid to Ctrl+C — the resume path is solid.
