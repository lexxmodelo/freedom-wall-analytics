# Topic Modeling Pipeline

Per-university BERTopic + decoupled NVIDIA NIM (Llama 3.3 70B Instruct) labeling for the Freedom Wall thesis. Plan: [docs/plans/topic_modeling_pipeline.md](../docs/plans/topic_modeling_pipeline.md).

## Quick Start (per researcher) — interactive

```bash
# 1a. Install GPU torch FIRST from the CUDA index (skip if you have no NVIDIA GPU)
pip install torch --index-url https://download.pytorch.org/whl/cu124

# 1b. Install the rest (NOTE: 'torch' is intentionally absent — already installed above)
pip install bertopic sentence-transformers umap-learn hdbscan httpx tenacity pyyaml gensim scikit-learn pytest

# 2. Verify CUDA is actually working
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# Want to see "2.6.0+cu124 True". If you see "+cpu" or "False" with a GPU on
# your machine, redo step 1a — the default 'pip install torch' on Windows
# silently installs CPU-only and the pipeline runs ~5x slower.

# 3. Add your NIM API key to .env (the launcher will also prompt you on first run)
cp .env.example .env
# Edit .env and paste your nvapi-... key. The .env file is git-ignored.

# 4. Launch the interactive menu
python -m topic_modeling
```

For full step-by-step setup (Python version requirements, troubleshooting), see [QUICKSTART.md](QUICKSTART.md).

The launcher walks you through everything:

```
============================================================
Topic Modeling — Interactive Launcher
============================================================
  1. Set up a researcher config
  2. Run embedding bake-off (one-time)
  3. Run full pipeline (train + label)
  4. Show status / list checkpoints
  5. Clear a checkpoint (force re-run)
  6. GPU / hardware tuning
  0. Quit
```

Typical flow for a new researcher:

1. **Choose 1** → enter your researcher ID (e.g. `researcher_1`) → tick the universities you'll process from a numbered list.
2. **Choose 2** (lead researcher only, one time) → bake-off picks MiniLM vs XLM-RoBERTa-Large on the SLU pilot and locks the winner in `bertopic_config.json`.
3. **Choose 3** → full pipeline: encode, cluster, soft-reassign, DTM, label via NIM, validate, checkpoint after each university.
4. **Choose 4** anytime to see what's done vs pending.

## Non-interactive / scripted use

```bash
python -m topic_modeling.run --researcher researcher_1 --bakeoff-only   # one-time
python -m topic_modeling.run --researcher researcher_1                  # full run
python -m topic_modeling.run --researcher researcher_1 --skip-bakeoff   # if winner already locked
```

## .env support

`topic_modeling/.env` (git-ignored) is auto-loaded on every run. Variables already set in your real shell environment win over `.env` values.

Minimum:

```
NVIDIA_NIM_API_KEY=nvapi-...
```

## What this produces

For each assigned file:

- `models/{CODE}_bertopic_model.pkl`
- `outputs/{CODE}/{topic_assignments,topic_keywords,topic_rep_docs,topic_labels,topic_metadata,topics_over_time}.json`
- `api_cache/labeling_responses/{CODE}/*.json`
- Updates to `action_log.md`, `gpu_logs/vram_usage.jsonl`, `validation/*.json`

## University coverage

10 cleaned files map to 10 anonymized codes (see `configs/university_mapping.yaml`):

| File | Alias | Code | Cluster |
|---|---|---|---|
| FW-01_cleaned.json | ADMU | MM-PSEC-1 | Metro Manila |
| FW-02_cleaned.json | UPD | MM-PUB-1 | Metro Manila |
| FW-03_cleaned.json | FEU | MM-PNSEC-1 | Metro Manila |
| FW-04_cleaned.json | UPLB | PROV-PUB-1 | Luzon Provincial |
| FW-05_cleaned.json | LPU-B | CAR-PNSEC-2 | CAR (extension) |
| FW-06_cleaned.json | CSU | MIN-PUB-1 | Mindanao (extension) |
| FW-07_cleaned.json | UPB | CAR-PUB-1 | CAR |
| FW-08_cleaned.json | BSU | CAR-PUB-2 | CAR |
| FW-09_cleaned.json | UB | CAR-PNSEC-1 | CAR |
| SLU_cleaned.json | SLU | CAR-PSEC-1 | CAR (pilot) |

Cluster-code extensions for LPU-B and CSU are documented in `action_log.md` ACTION-002.

## GPU tuning (optional, per-researcher)

Run **menu option 6** to set this interactively. The launcher auto-detects your GPU (if `torch` is installed) and offers four presets: small (6–8 GB / RTX 4050-4060), medium (10–16 GB / RTX 3080-4080), large (24+ GB / RTX 4090/A100), or no-GPU (CPU only — MiniLM will win the bake-off). A custom option lets you set values manually. Defaults are tuned for a 6 GB card. The settings live in [`configs/gpu_config.json`](configs/gpu_config.json) if you prefer editing the JSON directly.

## Resuming after a crash

The pipeline writes `checkpoints/{researcher_id}/{CODE}_state.json` after each successful university. Re-running the same command (or menu option 3) skips completed universities and continues. Use menu option 5 to force a re-run on a specific university.

## Tests

```bash
pytest tests/ -v
```
