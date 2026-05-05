# QUICKSTART — for researchers

This guide gets you from zero to your first labeled topic model in about 30 minutes. No prior BERTopic or NIM API knowledge needed.

If anything in this file is wrong or unclear, ping the lead researcher and edit it — that's how it gets better.

---

## Before you start

You need:

- **A computer with Python 3.11 or 3.12.** (Python 3.13/3.14 may not have wheels for `torch`/`hdbscan` yet on Windows.) Check with `python --version`.
- **An NVIDIA NIM API key** (free). Get one at https://build.nvidia.com → sign up → click your profile → "API Keys" → generate. Copy the `nvapi-...` string somewhere safe; you'll paste it in a moment.
- **The cleaned posts** in `../preprocessing/output/` (already there if you cloned the repo).
- **~10 GB free disk** (for model files + caches) and a **GPU with ≥4 GB VRAM** if you can — otherwise the pipeline auto-falls back to CPU (slower, still works).

---

## One-time setup

Open a terminal in the project folder:

```bash
cd "C:\Users\Alex Evan\Documents\Research\topic_modeling"
```

### 1. Create a virtual environment

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
```

(On macOS/Linux: `python3.11 -m venv .venv && source .venv/bin/activate`)

You should see `(.venv)` at the start of your prompt.

### 2. Install the dependencies

```bash
pip install bertopic sentence-transformers umap-learn hdbscan torch httpx tenacity pyyaml gensim scikit-learn pytest
```

This downloads ~3 GB of ML libraries; takes 5–10 minutes on a reasonable connection. If `torch` fails with a "no matching distribution" error, your Python version is too new — install Python 3.11 from python.org and redo this step.

### 3. Add your API key

```bash
copy .env.example .env
notepad .env
```

Paste your `nvapi-...` key after `NVIDIA_NIM_API_KEY=`, save, close. The `.env` file is git-ignored — it never gets committed.

(If you skip this, the launcher will prompt you to paste the key on first run and save it for you.)

### 4. Smoke-test the install

```bash
pytest tests/ -v
```

You should see **45 passed**. If not, dependencies didn't install cleanly — re-run step 2.

---

## Your first run

```bash
python -m topic_modeling
```

You'll get a menu:

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
Choose:
```

### Step A — Create your researcher config (option `1`)

```
Choose: 1
Researcher ID [researcher_1]: alexx
```

Pick anything short — `alexx`, `mara`, `lead`, whatever. This becomes your config filename.

You'll see all 10 universities. **For your first run pick only one small one** — type `7` (UPB, ~2,300 posts, fastest):

```
Selection: 7
```

The launcher writes `configs/alexx.json`.

### Step B — Run the embedding bake-off (option `2`) — *only the lead researcher does this, once per project*

```
Choose: 2
```

It compares two embedding models on the SLU pilot (3,864 posts) and locks the winner for everyone else. Takes **5–15 minutes** on GPU, **20–40 min** on CPU.

When it's done, `configs/bertopic_config.json` will have a real model name in `embedding_model_id` (no longer `TBD_FROM_BAKEOFF`), and `validation/embedding_bakeoff_report.md` will have the comparison table.

**If you're not the lead researcher**, skip this step — pull the updated `configs/bertopic_config.json` from the lead's branch instead.

### Step C — Run the full pipeline (option `3`)

```
Choose: 3
```

For one university (~2,300 posts) expect:

- Encoding: 1–3 min
- HDBSCAN grid search (12 configs): 2–5 min
- Build BERTopic + soft reassign: 30 sec
- Run DTM (topics over time): 30 sec
- NIM API labeling (≈30 topics, rate-limited 40/min): ~1 min

**Total: ~5–10 min per small university, ~15–30 min for a 30K-post university.**

### Step D — Inspect the output

After it finishes, look at:

```bash
type outputs\CAR-PUB-1\topic_labels.json
```

You should see something like:

```json
[
  {"topic_id": 0, "label": "Cafeteria Food Quality", "flags": [], "retries": 0, ...},
  {"topic_id": 1, "label": "Enrollment Schedule Confusion", "flags": [], ...},
  ...
]
```

If labels look like real student concerns, you're good. If you see lots of `LAZY_LABEL` flags or generic strings, raise it with the lead — the prompt or the corpus may need tuning.

### Step E — Add the rest of your universities

Re-run option `1` and pick all your assigned files (your assignment comes from the lead). Then option `3` again — completed universities are skipped automatically via checkpoints.

---

## Knowing when you're done

Run option `4` (Show status). For each assigned file you should see `[DONE]`:

```
Researcher alexx — assigned files:
  [DONE] FW-07_cleaned.json -> CAR-PUB-1
  [DONE] SLU_cleaned.json -> CAR-PSEC-1
```

Then check `validation/outlier_report.json` — if any university shows `needs_review: true`, look at the reason and either:

- Open `validation/lazy_label_flags.json` to see which labels need human eyes, or
- Use option `5` to clear that university's checkpoint and re-run with different hyperparameters (lead researcher will guide).

---

## What to send the lead researcher when finished

Zip these folders from your `topic_modeling/` directory:

```
outputs/        ← per-university JSON outputs
models/         ← BERTopic .pkl files (one per university)
api_cache/      ← raw NIM responses (audit trail)
checkpoints/    ← your researcher's checkpoint folder
gpu_logs/       ← VRAM peaks
validation/     ← QA reports
```

```bash
# Windows PowerShell:
Compress-Archive -Path outputs,models,api_cache,checkpoints,gpu_logs,validation -DestinationPath alexx_results.zip
```

Send the zip + a one-line summary: which universities you processed, total time, any flags that needed review.

**Do NOT send `.env`** — that's your private API key.

---

## When something goes wrong

| Symptom | What to do |
|---|---|
| `ModuleNotFoundError: No module named 'bertopic'` | You forgot to activate the venv (`.venv\Scripts\activate`) or skipped step 2 |
| `Pre-flight failed: ['Env var NVIDIA_NIM_API_KEY is not set']` | Edit `.env` and paste your key, or run option 2 first (bake-off doesn't need the key) |
| `torch.cuda.OutOfMemoryError` early in encode | The pipeline auto-recovers (16→8→4→CPU). If it still fails, close Chrome and other GPU apps, then re-run |
| `OUTLIER_HIGH` in action_log | Open `validation/outlier_report.json`. The university clustered poorly. Use option 5 to clear it, then ask the lead about the `outlier_recovery` hyperparameter grid |
| `NIM HTTP 429` storms | Edit `configs/<your_id>.json`, change `effective_rpm: 40` → `effective_rpm: 30`, re-run |
| Pipeline crashed mid-run | Just re-run option `3`. Completed universities are skipped; the partial one re-runs from scratch |
| Want to redo one university | Option `5` → pick the code → option `3` again |
| `No module named '_lzma'` or similar arcane import error | Your Python install is missing a system library. Reinstall Python from python.org with all default options checked |

---

## Tips

- **Process small universities first** so you catch problems early. Order: UPB (2.3K) → BSU/UB/LPU-B/UPLB/CSU/SLU/FEU (~3–4K each) → ADMU/UPD (last; 50K+).
- **Keep the terminal window open** — the live log is more readable than tailing the file.
- **Don't multi-task on the GPU** — Chrome with hardware acceleration eats 1–2 GB VRAM and may trigger OOMs.
- **Check `action_log.md`** after every major run — it's the source of truth for what happened. Every decision, every retry, every error.
- **Coffee break time:** the bake-off and ADMU/UPD runs are long. Set them up before lunch.

---

## Quick reference

| Command | What it does |
|---|---|
| `python -m topic_modeling` | Interactive menu (use this 99% of the time) |
| `python -m topic_modeling.run --researcher alexx` | Same as menu option 3 (CLI version) |
| `python -m topic_modeling.run --researcher alexx --bakeoff-only` | Same as menu option 2 |
| `pytest tests/ -v` | Sanity-check the install |
| `type action_log.md` | See what happened in the last run |

That's it. Run option 4 anytime if you forget where you are.
