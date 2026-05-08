# Freedom Wall Analytics

AI-driven topic modeling and multidimensional sentiment analysis of student discourse on selected Philippine university Freedom Wall pages.

**Saint Louis University · School of Accountancy, Management, Computing and Information Studies · Thesis 2.**

The repository contains the full pipeline — scraping, anonymization, BERTopic clustering, NVIDIA NIM Llama 3.3 70B labelling, dimensional VAD sentiment scoring, and a two-view browser dashboard — across **ten** Philippine universities tagged Metro Manila / Luzon Provincial / Baguio-Benguet (CAR).

---

## Repository layout

```
.
├── scraper_project/     Playwright + GraphQL Freedom Wall scraper
├── preprocessing/       Cleaning, anonymisation, language tagging, dedup
├── topic_modeling/      BERTopic per-university + NIM Llama 3.3 topic labels
├── vad_scoring/         Per-post Valence/Arousal/Dominance + sarcasm via NIM
├── dashboard/           Browser dashboard (Institutional + Research views)
├── docs/                Thesis proposal, summaries, audit logs, methodology log
└── README.md            ← you are here
```

Each pipeline module has its own `README.md` and `QUICKSTART.md`. This file is the map; the module READMEs are the detail.

---

## Quick start — "I just want to look at the dashboard"

The dashboard is static HTML/JS that reads pre-built JSON files in `dashboard/data/`. No Python deps required to view it.

```bash
cd dashboard
./serve.sh           # macOS / Linux
serve.cmd            # Windows
# then open http://localhost:8765
```

Landing page links to:
- **Institutional view** — single-university dashboard for student-affairs leadership.
- **Research view** — cross-institutional comparison + BERTopic UMAP scatter + post browser for thesis-panel review.

If `dashboard/data/` is missing or empty, see [Refreshing dashboard data](#refreshing-dashboard-data) below.

---

## End-to-end pipeline

```
scraper_project/        →  preprocessing/             →  topic_modeling/             →  vad_scoring/                  →  dashboard/etl/                 →  dashboard/
Facebook Freedom Wall      anonymise + dedup +            per-univ BERTopic +             per-post V/A/D + sarcasm        join + aggregate +                Institutional + Research
public posts               regional partitioning           NIM topic labels                via NIM Llama 3.3                materialise per-univ JSON         browser dashboards
                                                                                          (4 researchers, parallel)
```

| Stage | Input | Output | Driver |
|---|---|---|---|
| Scraping | Public FB pages | `scraper_project/data/{code}.json` | Playwright + GraphQL response interception |
| Preprocessing | Raw scraper JSON | `preprocessing/output/FW-{NN}_cleaned.json` | spaCy + custom regex anonymiser |
| Topic modelling | Cleaned posts | `topic_modeling/outputs/{UNIV}/` | BERTopic + paraphrase-multilingual-MiniLM-L12-v2; NIM Llama 3.3 for labels |
| VAD scoring | Cleaned posts + topic labels | `vad_scoring/results/researcher_*/{UNIV}_vad_scores.jsonl` | NVIDIA NIM Llama 3.3 70B Instruct, SAM 1–9 scale |
| Dashboard ETL | All of the above | `dashboard/data/*.json` | `dashboard/etl/build_dashboard_data.py` |

Universities (10): `CAR-PNSEC-1`, `CAR-PSEC-1`, `CAR-PUB-1`, `CAR-PUB-2`, `MIN-PUB-1`, `MM-PNSEC-1`, `MM-PSEC-1`, `MM-PUB-1`, `PROV-PNSEC-1`, `PROV-PUB-1`. Real names and aliases live in `topic_modeling/configs/university_mapping.yaml`.

---

## Prerequisites

- **Python 3.11+** (3.11 or 3.12 recommended; tested on Windows + Linux).
- **NVIDIA NIM API key** (`nvapi-...`) for topic labelling and VAD scoring. Required for `topic_modeling/` and `vad_scoring/`. Not required for the dashboard or preprocessing.
- **GPU (CUDA 12.4)** strongly recommended for `topic_modeling/`. CPU-only works but is ~5× slower.
- **Playwright + Chromium** for `scraper_project/` only.

Each module ships a `requirements.txt` and `.env.example`. There is no top-level `requirements.txt` because the modules have intentionally separated dependency footprints (the dashboard, for instance, needs nothing).

---

## Setting up a researcher account (VAD scoring)

VAD scoring is split across multiple researchers running in parallel against the NIM API. Each researcher needs their own config and their own NVIDIA API key.

```bash
cd vad_scoring
cp .env.example .env       # paste your nvapi-... key
python -m vad_scoring      # launches the interactive menu
# choose option 1 ("Set up a researcher config") on first run
```

The launcher copies `configs/researcher_template.json` to `configs/researcher_<your_id>.json`, distributes universities across researchers via LPT bin-packing, and writes per-researcher paths under `checkpoints/researcher_<id>/`, `results/researcher_<id>/`, and `api_cache/raw_responses_researcher_<id>.jsonl`.

All `configs/researcher_*.json` files are gitignored except `researcher_template.json`. Your run state stays local.

See [`vad_scoring/README.md`](vad_scoring/README.md) and [`vad_scoring/QUICKSTART.md`](vad_scoring/QUICKSTART.md) for the full menu walk-through.

---

## Running each phase

### Scrape

```bash
cd scraper_project
pip install -r requirements.txt
playwright install chromium
python main.py --targets FW-01 SLU      # specific institutions
python main.py                          # everything in config.py
```

See [`scraper_project/README.md`](scraper_project/README.md) and [`docs/scraper_freeze_postmortem.md`](docs/scraper_freeze_postmortem.md) for the freeze-proof scraper architecture (network interception + periodic browser restart + CDP-driven GC).

### Preprocess

```bash
cd preprocessing
pip install -r requirements.txt
python -m spacy download en_core_web_lg
python -m preprocessing.run                       # full run
python -m preprocessing.run --limit 500           # smoke test
```

Anonymises, deduplicates, classifies language, and partitions posts by region (Metro Manila / Luzon / Baguio). See [`preprocessing/README.md`](preprocessing/README.md).

### Topic modelling

```bash
cd topic_modeling
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install bertopic sentence-transformers umap-learn hdbscan httpx tenacity pyyaml gensim scikit-learn pytest
cp .env.example .env                              # paste nvapi- key
python -m topic_modeling                          # interactive menu
```

Per-university BERTopic with decoupled NIM Llama 3.3 labelling. See [`topic_modeling/QUICKSTART.md`](topic_modeling/QUICKSTART.md).

### VAD scoring

```bash
cd vad_scoring
python -m vad_scoring                             # interactive menu
# Option 4 — full pipeline; Option 5 — resume; Option 9 — merge (lead only)
```

Per-post V/A/D on the SAM 1–9 scale + sarcasm flag, joined to BERTopic labels. See [`vad_scoring/README.md`](vad_scoring/README.md).

---

## Running the dashboard

The dashboard is plain HTML/CSS/JS — no build step. It reads JSON over `fetch()`, which browsers refuse on `file://` pages, so a local HTTP server is required.

```bash
cd dashboard
./serve.sh             # macOS / Linux (port 8765 default; pass arg to override)
serve.cmd              # Windows
```

Then open:
- **Landing** — `http://localhost:8765/`
- **Institutional view** — `http://localhost:8765/institutional/`
- **Research view** — `http://localhost:8765/research/`

The dashboard reads only:

```
dashboard/data/_summary.json          cross-univ overview, loads first
dashboard/data/_meta.json             univ codes, regions, coverage flags
dashboard/data/institutional/{UNIV}.json   per-univ data for Dashboard 1
dashboard/data/research/{UNIV}.json        per-univ data for Dashboard 2 (institutional + UMAP coords)
```

These files are committed to the repo so teammates can serve the dashboard without re-running any pipeline phase.

---

## Refreshing dashboard data

Two ETL scripts in `dashboard/etl/` rebuild the JSON files from the upstream pipeline outputs.

```bash
# 1. Per-univ dashboard JSONs (fast — seconds)
python dashboard/etl/build_dashboard_data.py

# 2. (Optional) UMAP 2-D scatter coords for the Research view
pip install sentence-transformers umap-learn pyyaml
python dashboard/etl/export_umap_embeddings.py

# 3. Re-run #1 to fold in the new UMAP coords
python dashboard/etl/build_dashboard_data.py
```

Build inputs (read by `build_dashboard_data.py`):
- `preprocessing/output/FW-{NN}_cleaned.json`
- `topic_modeling/outputs/{UNIV}/topic_assignments.json` + `topic_keywords.json` + `topic_labels.json` + `topic_metadata.json` + `topics_over_time.json`
- `vad_scoring/results/researcher_*/{UNIV}_vad_scores.jsonl`

If a university has no VAD scores yet, the build still succeeds: `vad_coverage` is set to `0.0` and the dashboard renders a "VAD scoring pending" banner with topic-only views. See [`dashboard/etl/README.md`](dashboard/etl/README.md) for details.

---

## What's tracked vs gitignored

| Path | In git? | Why |
|---|---|---|
| `dashboard/` source (HTML/CSS/JS, ETL scripts) | yes | Source of truth |
| `dashboard/data/*.json` | **yes** | Lets teammates run the dashboard without re-running ETL |
| `docs/` | yes | Thesis proposal, audit logs, methodology log |
| `*/README.md`, `*/QUICKSTART.md`, `*/action_log.md` | yes | Per-module documentation |
| `*/configs/*.json` (templates, schemas, mappings) | yes | Settings shared across the team |
| `vad_scoring/configs/researcher_template.json` | yes | Bootstrap template |
| `vad_scoring/configs/researcher_*.json` | **no** | Per-researcher local config (contains researcher_id, NIM key reference) |
| `vad_scoring/results/`, `checkpoints/`, `api_cache/`, `merged_outputs/` | **no** | Per-run artifacts; large; varies per researcher |
| `topic_modeling/outputs/*/` | **no** | Trained models + topic assignments; large |
| `preprocessing/output/` | **no** | Cleaned post JSONs (~22 MB); regenerable from scraper output |
| `scraper_project/data/*_session.json`, cookies, debug screenshots | **no** | Browser session state, runtime artifacts |
| `*.env` | **no** | API keys |
| `.playwright-cli/`, `.pytest_cache/`, `manuscript/` | **no** | Local tooling caches and drafts |

Onboarding flow for a new teammate who wants the **dashboard**: clone, `cd dashboard`, `./serve.sh`. That's it.

Onboarding flow for a new teammate who wants to **re-run a pipeline phase**: clone, follow the relevant module README, drop your NIM API key into the module's `.env`, and run the interactive launcher. Earlier phases' outputs (preprocessing/topic_modeling) need to be regenerated locally or shared out-of-band — they are not in git.

---

## Documentation

| File | What's in it |
|---|---|
| [`docs/Thesis_Proposal.md`](docs/Thesis_Proposal.md) | Original thesis proposal (Dec 2025) — submitted document, not the final manuscript |
| [`docs/scraper_freeze_postmortem.md`](docs/scraper_freeze_postmortem.md) | Scraper freeze diagnosis + architectural mitigations |
| [`docs/execution_log.md`](docs/execution_log.md) | Pre-implementation engineering audit |
| [`docs/methodology_changes.md`](docs/methodology_changes.md) | Applied revisions: proposal → execution |
| [`docs/plans/`](docs/plans/) | Per-phase implementation plans (preprocessing, topic modeling, VAD, scraper iterations) |
| `*/action_log.md` | Per-module append-only audit trail (decisions, retries, recoveries) |

---

## Ethical & privacy posture

- **Public data only.** The scraper runs without login credentials and skips any page requiring authentication.
- **Anonymisation happens before any computational analysis.** No raw post text reaches BERTopic or the NIM API until the preprocessing pipeline has stripped names, school identifiers, and other PII. Three regional tags only — Metro Manila / Luzon / Baguio — never school names.
- **Data minimisation.** Only post text, timestamps, and engagement counts are collected. No user profiles, no comment threads, no reactions.
- **Academic use only.** This tool is built for the SLU thesis. The aggregated, anonymised dashboard outputs are the only sharable artifact.

---

## Authors

Saint Louis University, Baguio City · School of Accountancy, Management, Computing and Information Studies · Department of Computer Science.

**Researchers (8):**
- Albarida, Ivan A.
- Burgos, Miguel Joshua
- Calera, Earl Daniele S.
- Gapuz, Emil John C.
- Llena, Anthony
- Modelo, Alexx Evan O.
- Salda, Jayson S.
- Viduya, Hans Elijah

**Thesis adviser:** Dr. Randy Domantay

Topic modelling and VAD scoring use the NVIDIA NIM hosted Llama 3.3 70B Instruct endpoint. Embedding model: `paraphrase-multilingual-MiniLM-L12-v2`. Topic clustering: BERTopic.
