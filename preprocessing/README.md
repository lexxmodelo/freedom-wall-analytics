# Freedom Wall Preprocessing Pipeline

Cleans, anonymizes, and language-classifies Facebook Freedom Wall posts scraped by
[`scraper_project/`](../scraper_project). Produces three regional JSON files
(`metro_manila_posts.json`, `luzon_provincial_posts.json`, `baguio_benguet_posts.json`)
suitable for downstream BERTopic and VAD analysis.

This package is the implementation of the plan at
[`docs/plans/preprocessing_pipeline.md`](../docs/plans/preprocessing_pipeline.md).

## Install

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_lg
```

## Run

```bash
python -m preprocessing.run                                     # default paths
python -m preprocessing.run --limit 500                         # smoke test
python -m preprocessing.run --phases 2,3,8                      # partial rerun
python -m preprocessing.run --input /path --output /path        # custom paths
```

Outputs land in `output/`:

- `metro_manila_posts.json`, `luzon_provincial_posts.json`, `baguio_benguet_posts.json`
- `_qc_report.json` — counts, language histogram, dedup stats
- `_rejected.jsonl` — every dropped post with its rejection reason and phase

## Test

```bash
pytest -v
```

## Folder layout

```
preprocessing/
├── action_log.md            (running log of implementation steps)
├── preprocessing/           (Python package: phases 01-10)
├── configs/
│   ├── schools.yaml         (12-school master dictionary)
│   ├── tagalog_given_names.txt
│   └── stopwords_*.txt
├── fixtures/                (golden input + expected output)
├── tests/
└── output/
```
