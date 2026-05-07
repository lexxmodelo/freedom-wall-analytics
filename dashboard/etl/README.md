# Dashboard ETL

Builds the JSON files consumed by `dashboard/institutional/` and `dashboard/research/`. Two scripts:

| Script | Purpose | Run when |
|---|---|---|
| `build_dashboard_data.py` | Join `preprocessing/output/*.json` + `topic_modeling/outputs/{UNIV}/*.json` + `vad_scoring/results/**/*.jsonl` into per-university dashboard JSONs. | After any pipeline output changes (new VAD batch, re-labeled topics, etc.). Cheap — completes in seconds. |
| `export_umap_embeddings.py` | Regenerate 2-D UMAP coordinates for the BERTopic cluster scatter. Production BERTopic doesn't export these. | Once per university. Re-run only if embeddings or UMAP params change. |

## Quick start

```bash
# 1. Build per-university dashboard JSONs (fast)
python dashboard/etl/build_dashboard_data.py

# 2. (Optional) Generate UMAP 2-D coords — slower, requires extra deps
pip install sentence-transformers umap-learn pyyaml
python dashboard/etl/export_umap_embeddings.py

# 3. Re-build dashboard JSONs to pick up the new UMAP coords
python dashboard/etl/build_dashboard_data.py
```

Output structure:

```
dashboard/data/
├── _summary.json            # cross-univ stats, loads first
├── _meta.json               # univ codes, aliases, regions, coverage flags
├── institutional/{UNIV}.json
└── research/{UNIV}.json     # institutional + umap_xy[]
```

## Targeting one university

Both scripts accept `--univ` (repeatable):

```bash
python dashboard/etl/build_dashboard_data.py --univ CAR-PUB-1
python dashboard/etl/export_umap_embeddings.py --univ CAR-PUB-1 --univ MM-PUB-1
```

## Inputs

- `preprocessing/output/FW-{NN}_cleaned.json` (and `SLU_cleaned.json`) — anonymised post text + `timestamp_unix`.
- `topic_modeling/configs/university_mapping.yaml` — file → `univ_code` mapping.
- `topic_modeling/outputs/{UNIV}/` — `topic_assignments`, `topic_keywords`, `topic_labels`, `topic_metadata`, `topics_over_time`.
- `vad_scoring/results/{researcher}/{UNIV}_vad_scores.jsonl` — raw per-researcher VAD scores. The build script aggregates these and keeps the latest `scored_at` per `post_id`.

## Graceful degradation

If a university has no VAD scores yet, the build still succeeds: `vad_coverage` is set to `0.0`, VAD fields are `null`, and the dashboards render a "VAD scoring pending" banner with topic-only views. As more researchers commit JSONL files into `vad_scoring/results/`, simply re-run `build_dashboard_data.py`.
