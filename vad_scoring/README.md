# vad_scoring/

Dimensional sentiment scoring (Valence, Arousal, Dominance on the SAM 1-9 scale) with integrated sarcasm detection, via NVIDIA NIM Llama 3.3 70B Instruct.

Consumes the per-university outputs of [topic_modeling/](../topic_modeling/) and produces per-post VAD records keyed by `post_id`, joined with the assigned topic label for downstream cross-institution analysis.

See [docs/methodology_changes.md §3.4](../docs/methodology_changes.md) for the prompt design and [docs/plans/vad_scoring_pipeline.md](../docs/plans/vad_scoring_pipeline.md) for the full execution plan.

## Quickstart (per researcher)

```
cd vad_scoring/
cp .env.example .env       # paste your nvapi-... key
python -m vad_scoring      # interactive menu
```

Then in the menu:

1. **Option 1** — Set up your researcher config. The menu asks how many researchers total (1–5), which researcher you are, and distributes the 10 universities across you using LPT bin-packing.
2. **Option 2 or 3** — Smoke-test a single post or single 5-post batch to verify NIM connectivity.
3. **Option 4** — Run the full pipeline for your assigned universities. A 1-batch dry-run runs first; you confirm before committing to the full ~hours-long run.
4. **Option 5** — Resume from the last checkpoint if a run is interrupted (every 100 successful requests).
5. **Option 6** — View progress across all researchers.
6. **Option 7** — Validate output JSONLs against the JSON Schema.
7. **Option 8** — View / edit the few-shot anchors and recompute `prompt_sha256`.
8. **Option 9** *(lead only)* — Merge every researcher's results into `merged_outputs/all_vad_scores.json`.

## Outputs

```
results/researcher_<id>/<UNIV_CODE>_vad_scores.jsonl   ← one JSON per line
checkpoints/researcher_<id>/<UNIV_CODE>_state.json      ← resume state
api_cache/raw_responses_<researcher_id>.jsonl           ← every API call+response (audit)
validation/range_anomalies.json                         ← clamped V/A/D records
validation/sarcasm_flags.json                           ← sarcasm=true with V≥7
validation/pii_violations.jsonl                         ← rejected pre-API
merged_outputs/all_vad_scores.json                      ← lead-only merged dataset
merged_outputs/vad_statistics_per_topic.json            ← per-(univ, topic) summary
action_log.md                                            ← append-only audit trail
```

## Key configuration

- `configs/vad_config.json` — locked global settings (model_id, temperature 0.1, batch_size 5, scale 1-9, prompt_sha256). Do not edit per-researcher.
- `configs/researcher_template.json` — copied to `configs/researcher_<id>.json` by option 1.
- `configs/few_shot_examples.json` — 3 SAM-cube anchors (burnout, rage, sarcastic praise). Editing these invalidates `prompt_sha256` — only edit before a fresh run.
- `configs/vad_output.schema.json` — JSON Schema used by option 7's validator.

## Self-healing behaviors

| Failure | Recovery |
|---|---|
| HTTP 429 | Exponential backoff 1→2→4→8→16s, honor `Retry-After`, max 5 retries |
| HTTP 5xx / network timeout | Same backoff ladder, max 5 retries |
| HTTP 401/403 | Immediate halt, prompt user to check `NVIDIA_NIM_API_KEY` |
| 10 consecutive batch failures | Circuit breaker pauses 5 min then half-opens |
| Non-JSON response | json_repair → regex array extraction → up to 3 parser retries |
| Length mismatch / missing IDs | Re-queue missing posts as singles in next pass |
| V/A/D outside [1,9] | Clamp to nearest valid + flag `range_clamped` (no retry) |
| sarcasm=true AND V≥7 | Flag `sarcasm_high_valence` for HITL review |
| Unmasked PII | Reject pre-API, log to `validation/pii_violations.jsonl` |
| Crash mid-run | Resume from `last_completed_batch + 1` via option 5 |

## Tests

```
pytest tests/
```

Unit tests cover parser repair logic, validator clamping & reconciliation, and distribute bin-packing for 1–5 researchers.
