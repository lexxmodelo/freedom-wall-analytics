# Preprocessing Pipeline — Action Log

This file records every implementation step for the Freedom Wall preprocessing pipeline. Append-only; newest entries at the bottom.

Project: thesis on AI-Driven Topic Modeling and Multidimensional Sentiment Analysis of Student Discourse on Philippine University Freedom Walls.
Pipeline location: `C:\Users\Alex Evan\Documents\Research\preprocessing\` (sibling to `scraper_project/`).
Plan reference: [preprocessing_pipeline.md](../../docs/plans/preprocessing_pipeline.md)

---

## ACTION-001 — 2026-05-05 — Scaffold project structure

Created folder tree per plan §Folder layout:

```
preprocessing/
├── action_log.md            (this file)
├── preprocessing/           (Python package)
├── configs/
├── fixtures/
├── tests/
├── output/
└── scripts/
```

Verified before scaffolding:
- 5 of 12 universities are scraped: `FW-01=ADMU`, `FW-02=UPD`, `FW-03=FEU`, `FW-04=UPLB`, `SLU=SLU` (confirmed by inspecting the `post_url` and indexing-hashtag `#XXXFreedomWallNNN` of the first record in each JSONL).
- `FW-02 = UPD` (UP Diliman), not UPLB — the original prompt's note was a transcription slip; resolved per `scraper_project/config.py:TARGETS`.
- CSU = **Caraga State University** (confirmed by user); plan's `Cagayan State` alternative dropped.
- Most posts have `timestamp_raw: null` — adapted Phase 08 to emit `timestamp_unix: null` rather than reject posts when no parseable timestamp exists. QC report records the missing-timestamp count for advisor review.

Next: write `configs/schools.yaml` (12-school dictionary, CSU=Caraga, FW-02=UPD).

---

## ACTION-002 — 2026-05-05 — Implement configs

- `configs/schools.yaml` — 12-school dictionary. Confidence flags retained
  for advisor review (LPU-B/UB low; UPLB/CSU/UPB/BSU medium; rest high).
  CSU set to Caraga State per user confirmation.
  FW-02=UPD (per scraper_project/config.py:TARGETS, NOT UPLB).
  Includes `ambiguous_mascots` (Maroons/Lions/Eagles → drop, no region tag),
  `generic_location_allowlist` (Manila/Baguio/Cebu/Davao — never replaced),
  and `scraper_code_to_region` for source-based region fallback.
- `configs/stopwords_tagalog.txt` — pragmatic particles for phase06 flagging.
- `configs/stopwords_english.txt` — standard English closed-class words.
- `configs/tagalog_given_names.txt` — ~430-entry seed name list for phase04
  NER layer 2. Sourced from common Filipino given-name patterns; expand as
  the corpus reveals false negatives.

---

## ACTION-003 — 2026-05-05 — Implement Python package (phases 01-10)

Wrote 14 modules under `preprocessing/preprocessing/`:

- `__init__.py`, `logging_setup.py`, `io_utils.py`, `regex_lib.py`
- `schools.py` (YAML loader + replacement-table builder; 97 rules from 12 schools)
- `name_lists.py` (Tagalog given-name regex + department keyword/acronym patterns)
- `phase01_select.py` through `phase10_dedupe_qc.py` (all 10 phases)
- `pipeline.py` (orchestrator, runs phases in order: 01, 02, 04, 03, 05–10)
- `run.py` (CLI: `python -m preprocessing.run`, supports --limit / --phases / --verbose)

Runtime ordering deviates from numeric ordering: NER (phase04) runs BEFORE
noise reduction (phase03) so spaCy keeps the casing/punctuation it depends
on for entity recall. This is documented in `pipeline.py` and the plan.

---

## ACTION-004 — 2026-05-05 — Test scaffolding + golden fixture

- `fixtures/golden_input.jsonl` — 14 hand-crafted posts covering: hashtags
  (ADMU/UPD/FEU/UPLB/SLU), location markers (Katipunan, Sunken Garden,
  Maryheights, Los Baños, Morayta), mascots (Tamaraws, La Salle), professor
  reference (Sir Reyes), Filipino given name (Maria Cruz), pure-media,
  too-short, exact-duplicate pair, English-only, pure-Filipino, cross-uni
  comparison (ADMU vs DLSU).
- 7 test files (`tests/test_*.py`):
  - `test_phase02_anonymize.py` — 13 parametric replacement cases + 3 edge cases
  - `test_phase03_regex.py` — 7 regex-cleaning cases
  - `test_phase08_timestamps.py` — 4 timestamp parser cases incl. HKT suffix
  - `test_phase09_language.py` — 4 language detection cases
  - `test_pipeline_e2e.py` — full pipeline against golden fixture
  - `test_no_school_leaks.py` — hard assertion on output JSON files

---

## ACTION-005 — 2026-05-05 — Install deps, fix bugs, smoke test

Installed (Python 3.14): PyYAML, py3langid, datasketch, pytest. spaCy
deferred — no Python 3.14 wheels yet. Pipeline gracefully degrades without
spaCy (NER layers 2–4 still active via name list, professor regex, dept
keywords).

Bugs found and fixed:

1. **`scraper_project.utils.parse_absolute_timestamp` returns ISO string,
   not datetime** — phase08 was calling `.tzinfo` on a string. Added
   `_coerce_to_datetime` wrapper that handles either form.
2. **`Submitted:` mid-string not stripped** — original regex required
   line-start; relaxed to `\bSubmitted\s*:\s*` anywhere (just the prefix
   word; trailing signature falls through to phase04 NER).
3. **Acronym replacements were case-sensitive** — real posts use lowercase
   "admu", "slu", "uplb". Added `re.IGNORECASE` to the bare-acronym pattern.
4. **Standalone `#DLSU`/`#AnimoLaSalle` hashtags survived** — per-school
   regex only catches `#XXXFreedomWall...`. Added catch-all `#\w+` stripper
   in phase03 (runs AFTER per-school replacement so school-related hashtags
   become region tags first).
5. **Bare "Animo" missing from DLSU mascots** — added "Animo" and "Lady
   Archers" to schools.yaml.

Test results after fixes: **35 passed, 0 failed.**

---

## ACTION-006 — 2026-05-05 — Full corpus run (no limit)

Processed all 5 JSONL files end-to-end. Outputs in `output/`.

| Metric | Value |
|---|---|
| Posts in | 20,018 |
| Posts kept | 19,271 |
| Posts rejected | 37 |
| Exact duplicates dropped | 625 |
| Near duplicates dropped (Jaccard ≥ 0.9) | 85 |
| Cross-university posts | 97 |
| Region via source-code fallback | 91 |
| Posts missing timestamp | 19,268 |
| Runtime | ~42 seconds |

Region split: Metro Manila 11,284 · Luzon/Provincial 4,019 · Baguio/Benguet 3,968.
Language split: Filipino 6,944 · Taglish 6,524 · English 5,515 · Other 258 · Unknown 30.

**No-leak test passes on all three output files.**

Notes for advisor / next steps:

- **Almost all timestamps are missing** (19,268 of 19,271). The scraper
  populates `timestamp_iso: null` and `timestamp_raw: null` for the vast
  majority of posts. Downstream temporal analysis will need either a scraper
  fix or an alternative timestamp source (e.g. scraping the post page
  individually for the date stamp).
- **Other (258) and Unknown (30) language posts** — likely a mix of pure
  emoji/short-text posts and regional dialects. Currently kept in output;
  the dialect filter in phase09 only fires when py3langid explicitly
  classifies as ilo/pam/ceb/war/hil. May want to revisit thresholds after
  the advisor reviews a sample.
- **Source-code fallback region used for 91 posts** — these had zero school
  identifiers in their text. Routed by their JSONL's region (e.g. an
  FW-04.jsonl post with a generic complaint goes to Luzon/Provincial).
- **DLSU/PUP not yet scraped** (per scraper_project/config.py). Their
  schools.yaml entries are ready; pipeline will pick them up automatically
  once their JSONL files appear in `scraper_project/data/`.

When spaCy 3.x supports Python 3.14 (or via a 3.11 conda env), install
`spacy` + `python -m spacy download en_core_web_lg` to enable NER layer 1.
The pipeline will pick it up automatically — no code change needed.
